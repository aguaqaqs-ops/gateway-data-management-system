# S2b kickoff 设计输入（准备稿）

状态：DRAFT；2026-11-04，p6-backend-design。尚未提交 kickoff 审核、整体 kickoff 未获 owner 确认、未发实施提示词。DC76 的 UTC/输入范围已获 owner 确认，映射细则已形成设计候选，仍待审核。

引用基线：main `ebb0047383300a3754a4be6a6a78f72286600c83`。本文的源码事实、[交接 §1/§2.3](p6-backend-session-handoff.md)、[DC37–DC73](p6-s0-owner-decisions.md)、[设计](p6-design.md)、[执行计划](p6-execution-plan.md) 均指此提交；不是对 S2a 候选或证据的审核。S2a exit 尚未出现在本次 main 中，正式 kickoff 前必须在合入后的提交重核路径。

映射补充单独引用 main `580f57fd01d1` 与 S2a 候选 `3b3d9c97bc`，见[映射设计 §1–§6](p6-s2b-arrow-mapping-design.md)；不把本文旧路径盘点冒充合入后的最终核对。

## 1. 开工边界与待补输入

S2a exit、S1c exit、原始表使用方核对和磁盘估算完成，kickoff 经独立审核后由 owner 确认，才可发实施提示词。基准尚未交付的 DC63 子段不得填零或用旧 step 总时长代替。

| 输入 | 本次准备结果 | 正式 kickoff 前的闭合方式 |
| --- | --- | --- |
| 原始表使用方 | §2 给出当前 main 调用链与替代来源 | S2a 合入后按新 HEAD 重核，包括 FULL 与恢复 |
| 规范存储磁盘 | §3 给出计算口径；缺映射后的实际字节与当前可用容量 | 由获安排的设计输入普查在专用节点输出数字，不在开发机运行产品 |
| DC63 第 1 项 | §4 登记待基准交付，未宣称差距消除 | owner 转交基准 handoff 的提交和子段清单 |
| Arrow 映射 / DC76 输入 | 独立设计候选已写，UTC 与少数约 100 MB 输入已确认 | 核对转换、metadata/版本与确定性，技术审核后纳入 kickoff |
| DC72 第 3、6 项 | §5 给出 flag、池与 N/M 的接线边界 | 定 N/M 配置范围、默认值与恢复绑定；再交 kickoff 审核 |
| W2 检查点 | §6 给出程序判定要求 | S2b 实测，按设计 §16.1 停止规则 |

## 2. 上传侧数据使用方

这里的“原始表”指 SQL 解析/业务物化后、规范投影前的行；不包括 SourcePackage、规范表 IPC、面向客户端的 Parquet。当前 `application/preview_jobs.py::_sql_materialization_request` 已使用 `READERS_REQUIRED`，不传 artifact_store；`_materialize_uploaded_side` 在投影后才调用 `materialize_projected_snapshot(..., artifact_store=store)`。因此“删除原始表 Parquet”在当前生产上传路径首先是确认不再引入重复写入，不能把后续规范产物当作无用原始副本删掉。

以下路径相对 `vnext/backend/src/gateway_backend/`，源码引用均为本页基线。

| 使用者/实际路径 | 当前消费 | S2b 的来源与验收 |
| --- | --- | --- |
| `capabilities/snapshot_materialization/compose.py::materialize_business_snapshot`、`extract_special_device_catalog` | SQL reader 中 device 与特殊点表，XML 解析结果，构造 composite 派生表 | Arrow 过滤命中行后交 Python；XML 保持现行能力；逐值、诊断、composite 结果一致 |
| `capabilities/storage_projection/project.py::project_canonical_table_set` | business table_set、规则；包括 keyed、keyless、ordered、浏览角色 | Rust 内直接承接 Arrow；所有选中表都经过适用的物化与投影检查，空表也覆盖 |
| `application/preview_jobs.py::_materialize_all_sides` | MODIFIED_ONLY 的 MODIFIED；FULL 的 INITIAL/MODIFIED 及基线 | 两个上传侧分别进入同一 kernel；基线仍按精确 commit；不因只测 MODIFIED 漏 INITIAL |
| `_side_binding_document`、`_materialized_preview_inputs_from_checkpoint`、`_bound_from_side_document` | 投影后的 bound 表 manifest/row refs、storage facts、canonical closure | checkpoint 保存规范表引用与必要描述；读取 IPC 重建能力输入；T1 前缺失按设计重跑 Preview，从 SourcePackage 重算 |
| `application/pair_pipeline.py`、identity assessment、ordered 单侧 facts | bound 规范表行与描述；未变化 ordered 仍读当前侧行 | 从规范表 Arrow 读取；保留本次有效 pair 策略，不把依赖 pair 的摘要提前放到上传 kernel |
| `application/preview_jobs.py::surface_artifact_closure`、History 对应组装 | surface、records、风险、规范整表的导出引用，DATASET_REPLACEMENT 两侧 | IPC 是内部存储；客户端仍取 Parquet，导出缓存键仍用完整 row-layout 身份；验证全部表/全部侧引用 |
| T1、`application/submission/import_builder.py`、Submit 恢复 | 冻结的 MODIFIED 规范闭包与 manifest，PREPARED 后导入包 | T1 后缺失不能拿 SourcePackage、parent 或新 ruleset 重建；稳定失败且 main 不前移；PREPARED 后沿用冻结导入包 |
| 已提交表 Preview/Submit/History 读取 | 精确 commit 的表 | 健康副本 mmap；miss/损坏经 Dolt 校验回填，不改变原始表持久化结论 |

原始 reader 的内存使用方确实存在；本次没有发现它们需要独立持久原始表。正式 kickoff 重核应同时搜索直接引用与拼接路径，并列出通用 `ARTIFACTS_REQUIRED` API 的生产调用者，避免删除 Repository 物化仍使用的共享能力。不是仅凭“raw”文本搜索证明可删。

验收按真实调用路径参数化覆盖：MODIFIED_ONLY、FULL、DATASET_REPLACEMENT；首次/原样/少量/几乎全变；keyed/keyless/ordered、BROWSE_ONLY/SNAPSHOT_ONLY、空表、composite；正常执行与 checkpoint 恢复。用程序检查顶层及逐表状态、表集合、摘要、closure 引用闭合和诊断，不只检查一张表或进程 exit 0。每个不变量复用一个权威 owner，不做所有维度的笛卡尔积。

## 3. 磁盘估算输入与公式

DC76：输入保证 UTC 导出，来源/类型保持现有范围；约 100 MB SQL 是已知少数大输入，不是上限。普查按[映射设计 §5](p6-s2b-arrow-mapping-design.md#5-验收与容量输入)区分总量增长与少数大表增长，记录文件/字段/语句/行数预算。现有约 158.7 MB 的 V6 合成解析记录不代表完整上传路径或大表分布已验证；不要求 owner 立即提供新样本，不扩大当前基准测量。

估算对象是**未压缩规范 IPC**，不是 SQL 压缩包大小，也不是 V6 峰值 RSS。先确定设计 §8.1 的 Arrow 映射 v1，再由节点普查逐表给出：行数、各固定宽度 buffer、validity bitmap、变长 offsets（large 类型用 8 字节）、实际值字节、IPC schema/metadata/alignment。按内容地址对物理文件去重；不能只拿平均行宽乘行数，也不能把不同 schema 的同内容表误去重。

```text
C = bytes(unique(head ∪ active Preview ∪ frozen Attempt ∪ retained TTL canonical files))
D_peak = C + exported Parquet/cache + SourcePackage + Dolt + control metadata
         + temporary write/staging high-water + retained evidence/volume copies
required_increment = D_peak - already_present_bytes + agreed_reserve
capacity_ok = required_increment <= currently_available_bytes
```

集合以同一时刻的实际引用和 TTL 情景建立；FULL 双侧、旧 head、新 head、仍受保护的 Attempt 可同时存在。临时文件与最终文件 rename 不重复算两份常驻副本，但计入发布前新旧文件共存的高水位。跨项目按实际 scope 的共享规则计算，不能假定全局去重。输出还要分列 cleanup/TTL 前后体积。

历史资料 `p6-node-init-report.md`（本页基线，记录日期 2026-10-24）给 ct108 295 G 可用，只是容量参考，不是当前预算。V6 的 158.7 MB SQL 与 569–753 MiB RSS 也不能换算成规范 IPC。**目前没有足以填出可信 GiB 总数的已交付输入，磁盘核对项保持 OPEN。**

普查交付最小字段：节点/时间/提交、数据档及输入摘要、映射版本、逐类物理字节、引用去重前后数量、临时高水位、可用字节、场景中项目与活跃 Preview/Attempt 数、TTL、预留空间及程序判定。只输出计数与摘要，不输出行内容。参考节点计时占用期间不运行普查；05 可先做正确性/尺寸普查，ct108 空闲后只读核容量。预算超限按设计 §17 停止交 owner，讨论 LZ4 或容量；不自行引入容量淘汰。

### 3.1 仓库规模与长期容量（DC77，设计输入已确认）

| 情景 | 独立设备仓库数 | 单仓库年均提交 | 全体年均提交 |
| --- | ---: | ---: | ---: |
| 首版 | 1,000 | 6–12 | 6,000–12,000 |
| 长期 | 10,000 | 6–12 | 60,000–120,000 |

短期极端为单仓库每周约 5 版，不外推为全年 260 版；是否同时发生在多仓库尚未知。年均值不代表均匀到达，也不代表上传、Preview、失败重试或 History 的次数；这些活动及 FULL 双侧另外计入对应负载。

容量按以下三层计算，不把 SQL 字节等同落盘字节：

1. **当前状态常驻**：逐仓库核对实际当前 head 引用，按 scope 内实际允许的去重统计规范 IPC，加上当前 Dolt/control metadata。DC42 正式引用不会因一两个月不提交而自动过期；低频仓库的 head 仍占磁盘，不等于一直占满 RAM。不假定跨仓库去重。
2. **durable 历史增长**：按每次接受提交实际新增的 SourcePackage、Dolt 物理增量和元数据计算；SourcePackage 不能按 Dolt 的差分比例折算。基线历史量与年度新增分开，按年数参数外推，不引入保留年限或自动删历史政策。外部备份副本成本另列，不隐藏也不在本阶段实现备份。
3. **短期高水位**：当前 active Preview/Attempt、尚未过 TTL 的旧表、History/diff/export 缓存、上传/staging 与工作临时文件。按实际活跃集合及集中更新场景计算，不把全部仓库乘上 FULL 工作内存，也不凭年均次数认定 TTL 内只有一个版本。

敏感性示例（不是容量预测）：若平均每次提交恰新增 10 MB durable SourcePackage，首版每年新增约 60–120 GB、长期约 600–1,200 GB（十进制单位），尚未包含初始导入、Dolt、IPC、元数据、临时与备份。实际平均值未测；100 MB 是少数 SQL 输入，不能直接替代此参数，也不能假定每个版本只增加差分 SQL。

下一步普查先交付小/中/大及大表集中分布的单位成本，记录真实 SourcePackage bytes、IPC、Dolt 新建与变更增量、FULL/恢复/临时峰值。再给 1,000/10,000 仓库在测得大小分布下的容量区间。S2b 不在测试节点创建 1,000/10,000 份仓库作新门禁；生产总容量与并发验证按 DC37 留给 Phase 7，参考节点可用空间也不能冒充生产磁盘规格。

## 4. DC63 子段差距交接

DC63 第 1 项接受了 S1b 的 step 级限制：t4 History 312.889 s → 361.051 s，其中 materialize 216.440 s、assemble 142.544 s。它们属于不同分层，不能拿来断言 checkpoint 或 bundle 子段已经变快/变慢。

等待 owner 转交基准阶段的：checkpoint 读取、整表 Parquet 导出、bundle 组装、V5b 四段、完整 step 与残差；每项附产品提交、工具提交、输入、日志/JSON/摘要及可比性说明。建立“原子子段 → 所属 step → S1a 参考 → 当前基准 → 差距 → S2b/S3/其他已授权阶段 → 证据来源”表。父子段不得重复求和，未测量标 unknown。S2b 对应 IPC 读取/复用和写后回读消除；S3 对应逐行记录与 ordered 单侧计算。无法归因不自动扩大产品插桩或 worker runtime 范围。

O1 与 `BLOCK_STARTUP_FATAL` 留在 worker runtime 维护，不并入本阶段。

## 5. flag、共享池与配置设计输入

- 生产 flag 覆盖“解析→业务物化/检查→规范投影→表摘要”的整条上传路径，不能只换 parser 再逐行转 Python。S2a test-only 入口保留作差分支持，不是生产 flag。
- 提议 Python/Rust 两分支共用同一规范 IPC/引用语义及输出 Contract；flag 只选择计算实现，不选择两种持久格式。MODIFIED_ONLY 与 FULL 两侧都接线。Python 参照计算语义冻结；不得为了差分通过改语义。flag 选择在一次 operation 内保持一致，跨重启读取同一规范产物；具体绑定利用现有受理/恢复上下文，确需新字段先补设计。
- 复用 S2a adapter 的进程共享有界 Rayon 池；worker startup 在任何 kernel 调用前固定 N；pyarrow CPU/I/O 池同时按 N 配置。不得每调用、每表或 FULL 每侧建池，parser L3 继续使用同池。worker 接线测试归 S2b，adapter 复用测试仍归 S2a。
- 测试默认 N=1；测量起点 N=4 是预算假设，整条路径加速曲线之后暂定、S6 定稿。N/M 默认值、单位、上下界、部署 env 名称在 kickoff 定稿，当前不冒填 M。M 覆盖整份驻留输入、输出与 IPC 缓冲、每线程临时内存；并行任务估算总和不得越界，单表超额稳定失败。
- 无效配置启动即拒绝；所有 kernel 释放 GIL、检查取消/截止时间；预算拒绝为稳定诊断。flag 两值、N=1/N、parser 分块大小都做确定性比较。S6 删除生产 flag。
- RS 并发读取的完整调度仍归 S5，S2b 接入存储兜底须守现有容量/取消/截止边界，不提前引入 Phase 7 跨 operation 队列。
- Rust 新依赖只用 DC47 已准许的集合；锁定输入变化按 DC67 在 CT201 构建依赖层，经 LAN 预填充实际使用节点，离线构建。Compose/settings 接线和 Rust 变更触发镜像门禁。

### 5.1 N/M 的下一步定稿范围（设计建议，待审核）

- N=4 作为完整路径的测量起点，测试默认 N=1；依据加速曲线、峰值内存与 RS 容量再暂定。1,000/10,000 个仓库不对应同量线程或常驻内存。跨 operation 的槽位数 K、多 worker 和公平排队仍属于 Phase 7。
- M 是计算准入预算，不是进程 RSS 的严格封顶值。常驻输入/已读取基线、输出/IPC 缓冲与运行中各任务的临时预约必须合计；共享常驻项只计一次。FULL 同时驻留的两侧与排序/复制高水位都要计入，不能套用 parser 的平均倍数。超出预算的单任务稳定拒绝，不默默关闭检查。
- 配置 M 时还需为 Python/runtime、RS/Dolt、OS/page cache 及部署中其他进程留出空间；计算预算、实际进程峰值和容器/主机限制分别报告，不把计算预约当作实际 RSS。具体默认值、上限与余量在单位测量后填写，不现在凭 100 MB 输入猜一个 GiB 数。
- 单次处理成本和仓库总量已有设计输入；集中维护的一批数量/时间窗口尚待 owner 补充。即使该项暂未知，仍可完成单任务映射、单位成本与参数化磁盘预算；不据此提前承诺峰值吞吐或重开 Phase 7 调度实现。

## 6. W2 与验收清单（提交审核的草案）

| 不变量 | 程序判定 | owner 层 |
| --- | --- | --- |
| 业务结果保值 | t1–t4 所有生产路径的表集合/业务摘要/records/risk 一致；仅按 DC64 第 4 项显式归一实例字段 | 端到端 comparator |
| IPC 读取/引用 | raw SHA 校验；头前移与正式引用同事务；共享保护与 TTL；四种恢复状态分别断言精确来源/终态/main | 存储与 Submit 各自语义测试 |
| Arrow 映射 | 映射设计 §5 的声明/值往返、SET/JSON/BIT/时间边界、两计算分支及线程/chunk 确定性；不以物理 SHA 替代业务摘要 | 映射 owner，复用既有标量向量 |
| 结构性过滤 | 设计 §16.2 全部适用于本阶段的公式；W2 基线行读取/行比较为 0，规范内容命中不重写 | capability/application 计数测试 |
| 完整生产接线 | 两 flag 的上述路径；实际 worker/Compose 使用指定 N/M；不经 Python 逐行往返；取消/预算拒绝 | worker 接线与数据路径测试 |
| W2 可达性 | 下式、样本完整性及逐段归因均由程序给出 | benchmarks |

```text
reachable = no_unknown_segments
            AND all_reductions_have_evidence_and_named_stage
            AND no_overlapping_or_excess_reductions
            AND W2_S2b - sum(remaining_reduction_upper_bounds) <= 30 seconds
```

W2 按设计 §16.3 的 1 次预热 + 3 次测量、中位数及范围，受理到 READY；DC66 基准单次例外不能泛化。各削减上界不得超过所属实测段，未归因项不能填 0 后放行；W2 不做行比较，S3 的比较加速不得记入。程序输出 CONTINUE/STOP 和原因；STOP 交 owner。本阶段测 W1–W3；W4 数据路径正确性仍由测试与端到端对照覆盖，不新增 W4 性能取证阶段。

真实数据拟沿用执行计划范围：05 t1–t3、ct108 t4 端到端与 2× t4 W1–W3；具体运行路径清单在正式 kickoff 中列全，退出前 owner 按 DC33 确认。代码审核先于完整证据（W2 设计输入例外按 DC64）；runner、离线缓存、节点单飞、日志及停止规则沿用 AGENTS。

## 7. 确认记录

- kickoff 审核：待 owner 转交，引用审核提交后记录。
- owner 确认：DC76 输入约定与设计准备已确认；整体 kickoff 未确认，映射技术审核待办。
- 实施提示词：未发；S2a exit 前只准备。

## 8. 本次文档提交检查（不是阶段取证）

本次仅改设计文档，不触发镜像重建，也不声明当前 HEAD 的容器门禁通过。05 的 clean 已提交主 checkout `84c3d91a1a978c788edacf99b326ba2b8886b0ea` 与引用基线具有相同 `vnext` tree `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。按提交前要求，在 05 以受控 uv wrapper、offline/no-sync 运行五包 ruff/mypy，2026-11-04T01:19:34Z–01:19:54Z，exit 0；使用节点已有缓存，未下载依赖。节点占用已释放。

日志：05 `/home/dev/gdds-test-tmp/p6-backend-design-static-20261104T011934Z.log`；SHA256 `82fc3ae29af5262800e519eb8934b47a769cb95d283861ca89e2b1bcae01a9ae`。此为文档提交的静态检查记录，不是 S2a 实施审核、闭包 carried 或 S2b 证据判定。

### 8.1 DC77 容量输入补充的提交检查

本轮仅修改设计/DC/计划正文/kickoff，检查起点 main `0ca504375809`；不触发镜像重建，不声明新 image revision 或 carried。05 clean 已提交 checkout `55e6c0083c6e3a05dc97dad86974afd645d89a8e` 与本轮 main 的 `vnext` tree 同为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。2026-11-04T13:14:23Z–13:14:25Z，在 `gw-dms-test-05` 获取节点占用，以受控 uv wrapper、`UV_OFFLINE=1`、`--no-sync` 完成五包 ruff/mypy，exit 0、起止 HEAD 相同；使用节点本地预填充环境，无代理、无下载，检查后释放占用。未运行容量普查、pytest 或 Compose。

日志：05 `/home/dev/gdds-test-tmp/p6-dc77-capacity-static-20261104T131423Z.log`；SHA256 `3aa5dd3a0af75b0c9a4d3c2aa60326b015828873ce70ec1f4c1ff5f9504c973a`。容量单位成本和生产部署容量仍未验证。
