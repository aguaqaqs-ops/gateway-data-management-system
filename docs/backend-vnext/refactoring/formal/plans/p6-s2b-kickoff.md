# S2b kickoff 设计输入（准备稿）

状态：DRAFT；2026-11-04，p6-backend-design。尚未提交 kickoff 审核、整体 kickoff 未获 owner 确认、未发实施提示词。DC76 的 UTC/输入范围已获 owner 确认，映射细则已形成设计候选，仍待审核。

2026-11-05 更新（DC81）：owner 已解除 S2a exit 对基准整体 exit 的依赖，并安排新会话推进 S2a 收尾与 S2b 讨论。完整基准由原线独立跟踪；先推进已定功能，允许测量后小范围定向返工，开发验证按影响面收敛。本文仍为待审核准备稿，不将未知性能数值冒称通过，也不自动取消 W2 等退出条款。

2026-11-06 补充（DC81）：owner 明确当前性能指标并非硬性门槛，可结合实测与物理限制讨论合理性。下文 W2 公式保留为当前目标的评估方法；未达或未知时交付事实、约束及调整方案供 owner 决定，不自动阻断所有开发，也不自行放行。具体 W2 测量时点已由下述 DC83 收口；正确性、资源上限、取消/截止、租约和实际业务失败的处置不变。本补充不是整体 kickoff 或产品实施授权。

2026-11-06 时点确认（DC83）：owner 已选择 S2b 功能退出与 W2 性能复核分开。保留 30 秒目标和既有统计口径，CT108 可用时补完整路径测量、最迟 S6 收口；未知不记通过。正确性、恢复、资源边界与必要门禁仍在 S2b 最终候选完成。允许后续小范围定向返工，具体产品实施仍需本 kickoff 收口。

引用基线：main `ebb0047383300a3754a4be6a6a78f72286600c83`。本文的源码事实、[交接 §1/§2.3](p6-backend-session-handoff.md)、[DC37–DC73](p6-s0-owner-decisions.md)、[设计](p6-design.md)、[执行计划](p6-execution-plan.md) 均指此提交；不是对 S2a 候选或证据的审核。S2a exit 尚未出现在本次 main 中，正式 kickoff 前必须在合入后的提交重核路径。

映射补充单独引用 main `580f57fd01d1` 与 S2a 候选 `3b3d9c97bc`，见[映射设计 §1–§6](p6-s2b-arrow-mapping-design.md)；不把本文旧路径盘点冒充合入后的最终核对。

## 1. 开工边界与待补输入

节点补充（DC82，2026-11-06）：owner 新增 06 作为后端日常开发测试节点，07 作为前端 mock 开发测试节点。06 的 Rust、Contract/focused 与小规模 Compose 可以与独立宿主 CT108 的正式测量并行；04/06/07 同宿主且 Owner 确认资源宽裕，06/07 日常自主并行，不设常规整宿主互斥或向原基准线申请窗口；实际干扰时协调。节点就绪情况见[核对报告](p6-node-06-07-readiness.md)。新增节点解除日常调试窗口争用，不替代下列 kickoff、S2a exit、资源预算或独立审核前置，不迁移 t4/正式测量。

S2a exit、S1c exit、原始表使用方核对和必要磁盘估算完成，kickoff 经独立审核后由 owner 确认，才可发实施提示词。DC81 已解除 S2a 对基准整体 exit 的等待，故不再由这一依赖串行阻塞本阶段。基准尚未交付的 DC63 子段明确登记为待补，不填零或用旧 step 总时长代替，也不据此阻塞与其无关的设计/实施范围；W2 时点已由 DC83 确认分离，其他场景不自动豁免。

| 输入 | 本次准备结果 | 正式 kickoff 前的闭合方式 |
| --- | --- | --- |
| 原始表使用方 | §2 给出当前 main 调用链与替代来源 | S2a 合入后按新 HEAD 重核，包括 FULL 与恢复 |
| 规范存储磁盘 | §3 给出计算口径；缺映射后的实际字节与当前可用容量 | 由获安排的设计输入普查在专用节点输出数字，不在开发机运行产品 |
| DC63 第 1 项 | §4 登记待基准交付，未宣称差距消除 | 原基准线后续交付；DC81 下不再作为全部开发开工前置，相关退出验收安排须明确 |
| Arrow 映射 / DC76 输入 | 独立设计候选已写，UTC 与少数约 100 MB 输入已确认 | 核对转换、metadata/版本与确定性，技术审核后纳入 kickoff |
| DC72 第 6 项 / DC78 | §5 给出唯一 Rust 路径、清理、池与 N/M 接线边界；ADR/reference 定位已同步 | 定 N/M 数值、消费者/覆盖移交清单与恢复验收；交 kickoff 审核 |
| W2 性能复核 | §6 保留评估公式；DC83 已确认与功能退出分开 | CT108 可用时测，最迟 S6；不作为 S2b 功能开工/退出前置 |

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

初次输入为单仓库短期每周约 5 版；owner 随后补充初始维护窗口可批量上传，并给出以下压力情景。它们不外推为年均，年均值也不代表上传、Preview、失败重试或 History 的次数；这些活动及 FULL 双侧另外计入对应负载。

| 压力情景 | 业务性质 | 用于设计的边界 |
| --- | --- | --- |
| 单项目一天 5 版 | 假设最极端，尚未实际发生 | 同仓库版本/写入串行约束、短期 SourcePackage/TTL/临时空间；不是已测负载或常态 |
| 500 个仓库同日上传 | 跨仓库极端集中到达场景 | 总上传/落盘与计算积压；不等于 500 路计算并发，日内到达分布未定 |

两个情景不默认组合为 500×5 次提交，不视为所有输入均 100 MB；如后续做组合敏感性分析，应标明新增假设。owner 后续确认允许后台处理到次日，500 个上传通常分散在当天，不会全部挤在单次处理的数分钟窗口；具体到达曲线和次日完成时点尚未量化。到达窗口、排队等待与实际处理时间分别记录，不把“通常分散”当作均匀到达保证。

容量按以下三层计算，不把 SQL 字节等同落盘字节：

1. **当前状态常驻**：逐仓库核对实际当前 head 引用，按 scope 内实际允许的去重统计规范 IPC，加上当前 Dolt/control metadata。DC42 正式引用不会因一两个月不提交而自动过期；低频仓库的 head 仍占磁盘，不等于一直占满 RAM。不假定跨仓库去重。
2. **durable 历史增长**：按每次接受提交实际新增的 SourcePackage、Dolt 物理增量和元数据计算；SourcePackage 不能按 Dolt 的差分比例折算。基线历史量与年度新增分开，按年数参数外推，不引入保留年限或自动删历史政策。外部备份副本成本另列，不隐藏也不在本阶段实现备份。
3. **短期高水位**：当前 active Preview/Attempt、尚未过 TTL 的旧表、History/diff/export 缓存、上传/staging 与工作临时文件。按实际活跃集合及集中更新场景计算，不把全部仓库乘上 FULL 工作内存，也不凭年均次数认定 TTL 内只有一个版本。

敏感性示例（不是容量预测）：若平均每次提交恰新增 10 MB durable SourcePackage，首版每年新增约 60–120 GB、长期约 600–1,200 GB（十进制单位），尚未包含初始导入、Dolt、IPC、元数据、临时与备份。实际平均值未测；100 MB 是少数 SQL 输入，不能直接替代此参数，也不能假定每个版本只增加差分 SQL。

下一步普查先交付小/中/大及大表集中分布的单位成本，记录真实 SourcePackage bytes、IPC、Dolt 新建与变更增量、FULL/恢复/临时峰值。再给 1,000/10,000 仓库在测得大小分布下的容量区间，并参数化评估 500 仓库同日上传的积压空间。S2b 不在测试节点创建 500/1,000/10,000 份仓库作新门禁；生产总容量与并发验证按 DC37 留给 Phase 7，参考节点可用空间也不能冒充生产磁盘规格。

### 3.2 横向扩展的衔接（方向已确认，具体选型留待 Phase 7）

owner 于 2026-11-04 确认 §3.1 的容量分层、独立突发场景与本节扩展方向，授权落成方案。该确认不指定生产硬件数量、磁盘规格、N/M 数值或完成时限；不是整体 kickoff 的审核通过或开工授权。

仓库独立性使跨仓库分配工作具有可行性；先按测得单位成本评估有限槽位和排队所需吞吐，再判断单机资源或跨机扩展。评估指标分开记录到达率、接受上传的存储/网络预算、处理服务时间、等待时间和完成时限，不能直接用 500/day 推出机器数。

候选方向是按项目/仓库归属把执行与所需状态分配给明确的服务分区；具体分区单位、路由与迁移方式留待 Phase 7 设计。单仓库继续遵守 writer 串行、expected-parent/main CAS、幂等及租约恢复。必须同时评估 control DB、artifact 可达性、RS root 独占与磁盘/网络带宽，不能只横向增加 worker 数。当前 worker 是单 executor，DC37 已要求多 worker 重审启动租约；RS runtime 取得 root lock。现有部署不能因此宣称支持任意副本共享同一数据目录，S2b 不新增这些机制。

owner 后续确认生产按多个 worker 考虑、日常交互优先。worker 数量不等于有效计算槽位 K，更不等于单任务线程数 N；总预算需覆盖多个 M、RS/数据库、运行时及 I/O 余量。Phase 7 候选采用领取新任务时的优先级与批量任务保底份额/有界等待，防止低优先级永久饥饿，不中断正在进行的事务或提交。允许跨日完成还需核对排队与执行的截止时间、租约恢复和上传产物保护期；这是新增部署能力的验证，不放宽 Phase 6 的单任务门槛。

压力验证先覆盖分散到达、合理短时突发及批量处理期间的日常请求，观察交互延迟、批量积压消退与资源上界。只有需要验证准入/背压时，再以明确场景评估集中到达；500 个请求到达也不要求 500 个任务同时执行。不追加当前基准测量，不现在启动规模压力测试。

## 4. DC63 子段差距交接

DC63 第 1 项接受了 S1b 的 step 级限制：t4 History 312.889 s → 361.051 s，其中 materialize 216.440 s、assemble 142.544 s。它们属于不同分层，不能拿来断言 checkpoint 或 bundle 子段已经变快/变慢。

等待 owner 转交基准阶段的：checkpoint 读取、整表 Parquet 导出、bundle 组装、V5b 四段、完整 step 与残差；每项附产品提交、工具提交、输入、日志/JSON/摘要及可比性说明。建立“原子子段 → 所属 step → S1a 参考 → 当前基准 → 差距 → S2b/S3/其他已授权阶段 → 证据来源”表。父子段不得重复求和，未测量标 unknown。S2b 对应 IPC 读取/复用和写后回读消除；S3 对应逐行记录与 ordered 单侧计算。无法归因不自动扩大产品插桩或 worker runtime 范围。

O1 与 `BLOCK_STARTUP_FATAL` 留在 worker runtime 维护，不并入本阶段。

## 5. Rust 接入、旧实现清理与配置设计输入

- DC78 取消生产回退与双路径开关；Rust 接入覆盖“解析→业务物化/检查→规范投影→表摘要”的整条上传路径，不能只换 parser 再逐行转 Python。S2a test-only 入口只在替换验证期间使用；S2b 完成接入、差分和唯一生产路径验收后删除被替代 Python 算法及临时入口，不延期到 S6。
- MODIFIED_ONLY 与 FULL 两侧均走 Rust，采用单一规范 IPC/引用语义及输出 Contract。重启读取现有 checkpoint 与规范产物，失败沿用取消、重试与稳定诊断，不改走 Python；不新增引擎选择字段或双格式兼容。T1 后冻结边界不变。替换期 Python 参照计算语义冻结；不得为了差分通过改语义。
- 删除前将关键预期落实为经核实的固定向量与 Contract/性质测试，不能由当前 Rust 输出直接生成期待值后自证。删除仅为旧实现存在的依赖、mock 和重复算法用例，保留实际 Python 编排、PyO3/Arrow 适配、错误传播和端到端恢复测试；逐项核对其他生产消费者，避免误删共享能力。ADR 0001、ADR 0010、Rust policy 的长期 reference 要求已按 owner 后续授权同步；实际消费者与覆盖移交清单仍是 kickoff 技术闭合项。
- 复用 S2a adapter 的进程共享有界 Rayon 池；worker startup 在任何 kernel 调用前固定 N；pyarrow CPU/I/O 池同时按 N 配置。不得每调用、每表或 FULL 每侧建池，parser L3 继续使用同池。worker 接线测试归 S2b，adapter 复用测试仍归 S2a。
- 测试默认 N=1；测量起点 N=4 是预算假设，整条路径加速曲线之后暂定、S6 定稿。N/M 默认值、单位、上下界、部署 env 名称在 kickoff 定稿，当前不冒填 M。M 覆盖整份驻留输入、输出与 IPC 缓冲、每线程临时内存；并行任务估算总和不得越界，单表超额稳定失败。
- 无效配置启动即拒绝；所有 kernel 释放 GIL、检查取消/截止时间；预算拒绝为稳定诊断。N=1/N、parser 分块大小做确定性比较；替换期差分与最终单实现回归分别记录，不保留两 flag 测试矩阵。
- RS 并发读取的完整调度仍归 S5，S2b 接入存储兜底须守现有容量/取消/截止边界，不提前引入 Phase 7 跨 operation 队列。
- Rust 新依赖只用 DC47 已准许的集合；锁定输入变化按 DC67 在 CT201 构建依赖层，经 LAN 预填充实际使用节点，离线构建。Compose/settings 接线和 Rust 变更触发镜像门禁。

### 5.1 N/M 的下一步定稿范围（设计建议，待审核）

- N=4 作为完整路径的测量起点，测试默认 N=1；依据加速曲线、峰值内存与 RS 容量再暂定。1,000/10,000 个仓库不对应同量线程或常驻内存。跨 operation 的槽位数 K、多 worker 和公平排队仍属于 Phase 7。
- M 是计算准入预算，不是进程 RSS 的严格封顶值。常驻输入/已读取基线、输出/IPC 缓冲与运行中各任务的临时预约必须合计；共享常驻项只计一次。FULL 同时驻留的两侧与排序/复制高水位都要计入，不能套用 parser 的平均倍数。超出预算的单任务稳定拒绝，不默默关闭检查。
- 配置 M 时还需为 Python/runtime、RS/Dolt、OS/page cache 及部署中其他进程留出空间；计算预算、实际进程峰值和容器/主机限制分别报告，不把计算预约当作实际 RSS。具体默认值、上限与余量在单位测量后填写，不现在凭 100 MB 输入猜一个 GiB 数。
- 集中到达场景为 500 仓库同日上传，另有单项目 5 版/日的假设压力；owner 允许后台处理到次日、要求多个 worker 与日常交互优先。具体日内集中程度、worker 数量和完成时点尚未量化。仍可完成单任务映射、单位成本与参数化磁盘预算；峰值吞吐与排队承诺在 Phase 7 按工作量和时限确定，不按仓库数盲目增加 N/M。

## 6. W2 与验收清单（提交审核的草案）

| 不变量 | 程序判定 | owner 层 |
| --- | --- | --- |
| 业务结果保值 | t1–t4 所有生产路径的表集合/业务摘要/records/risk 一致；仅按 DC64 第 4 项显式归一实例字段 | 端到端 comparator |
| IPC 读取/引用 | raw SHA 校验；头前移与正式引用同事务；共享保护与 TTL；四种恢复状态分别断言精确来源/终态/main | 存储与 Submit 各自语义测试 |
| Arrow 映射 | 映射设计 §5 的声明/值往返、SET/JSON/BIT/时间边界、固定向量及线程/chunk 确定性；不以物理 SHA 替代业务摘要 | 映射 owner，复用既有标量向量 |
| 结构性过滤 | 设计 §16.2 全部适用于本阶段的公式；W2 基线行读取/行比较为 0，规范内容命中不重写 | capability/application 计数测试 |
| 完整生产接线 | 唯一 Rust 路径；实际 worker/Compose 使用指定 N/M；不经 Python 逐行往返；取消/预算拒绝/重启恢复；旧算法及重复测试清理 | worker 接线与数据路径测试 |
| W2 可达性（独立性能复核，非功能 exit 条件） | 下式、样本完整性及逐段归因均由程序给出；未知不记通过，最迟 S6 | benchmarks |

```text
reachable = no_unknown_segments
            AND all_reductions_have_evidence_and_named_stage
            AND no_overlapping_or_excess_reductions
            AND W2_measured_candidate - sum(remaining_reduction_upper_bounds) <= 30 seconds
```

W2 按设计 §16.3 的 1 次预热 + 3 次测量、中位数及范围，受理到 READY；DC66 基准单次例外不能泛化。各削减上界不得超过所属实测段，未归因项不能填 0 后放行；W2 不做行比较，S3 的比较加速不得记入。程序按实际资料区分有依据的可达结论、待补和未达目标，附原因；未知不填零、不记 PASS。DC83 下该复核不阻塞 S2b 功能 exit，CT108 可用时补、最迟 S6；未达目标带实测、约束和调整方案交 owner。后续版本结果绑定实际候选，不冒充 S2b 历史版本已测。本阶段测 W1–W3；W4 数据路径正确性仍由测试与端到端对照覆盖，不新增 W4 性能取证阶段。

真实数据拟沿用执行计划范围：05 t1–t3、ct108 t4 端到端与 2× t4 W1–W3；具体运行路径清单在正式 kickoff 中列全，退出前 owner 按 DC33 确认。代码审核先于完整证据（W2 设计输入例外按 DC64）；runner、离线缓存、节点单飞、日志及停止规则沿用 AGENTS。

## 7. 确认记录

- kickoff 审核：待 owner 转交，引用审核提交后记录。
- owner 确认：DC76 输入约定与设计准备、DC77 容量方案与 Phase 7 扩展方向、DC83 的 W2 时点分离已确认；整体 kickoff 未确认，映射技术审核、实测容量与配置定稿待办。
- 实施提示词：未发；S2a exit 前只准备。

## 8. 本次文档提交检查（不是阶段取证）

本次仅改设计文档，不触发镜像重建，也不声明当前 HEAD 的容器门禁通过。05 的 clean 已提交主 checkout `84c3d91a1a978c788edacf99b326ba2b8886b0ea` 与引用基线具有相同 `vnext` tree `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。按提交前要求，在 05 以受控 uv wrapper、offline/no-sync 运行五包 ruff/mypy，2026-11-04T01:19:34Z–01:19:54Z，exit 0；使用节点已有缓存，未下载依赖。节点占用已释放。

日志：05 `/home/dev/gdds-test-tmp/p6-backend-design-static-20261104T011934Z.log`；SHA256 `82fc3ae29af5262800e519eb8934b47a769cb95d283861ca89e2b1bcae01a9ae`。此为文档提交的静态检查记录，不是 S2a 实施审核、闭包 carried 或 S2b 证据判定。

### 8.1 DC77 容量输入补充的提交检查

本轮仅修改设计/DC/计划正文/kickoff，检查起点 main `0ca504375809`；不触发镜像重建，不声明新 image revision 或 carried。05 clean 已提交 checkout `55e6c0083c6e3a05dc97dad86974afd645d89a8e` 与本轮 main 的 `vnext` tree 同为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。2026-11-04T13:14:23Z–13:14:25Z，在 `gw-dms-test-05` 获取节点占用，以受控 uv wrapper、`UV_OFFLINE=1`、`--no-sync` 完成五包 ruff/mypy，exit 0、起止 HEAD 相同；使用节点本地预填充环境，无代理、无下载，检查后释放占用。未运行容量普查、pytest 或 Compose。

日志：05 `/home/dev/gdds-test-tmp/p6-dc77-capacity-static-20261104T131423Z.log`；SHA256 `3aa5dd3a0af75b0c9a4d3c2aa60326b015828873ce70ec1f4c1ff5f9504c973a`。容量单位成本和生产部署容量仍未验证。

### 8.2 DC77 峰值补充的提交检查

文档检查起点 main `8d908d03629d`，仅设计/DC/计划正文/kickoff 变化，不触发镜像重建，不声明新容器门禁或 carried。05 同 §8.1 的 clean checkout/`vnext` tree，2026-11-04T13:18:04Z–13:18:06Z，取得节点占用后以受控 uv wrapper、offline/no-sync、本地预填充环境跑五包 ruff/mypy，exit 0；起止 HEAD 为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`，无代理/下载，完成后释放占用。未跑规模、性能或产品测试。

日志：05 `/home/dev/gdds-test-tmp/p6-dc77-burst-static-20261104T131804Z.log`；SHA256 `9ad6647806ed1564e2339761c4532ea08d54dd889136109a7241c66fa3b9c7fd`。

### 8.3 DC77 方案确认的提交检查

文档检查起点 main `93ac7539c987`；仅记录 owner 对容量方案与扩展方向的确认，不触发镜像重建，不声明新容器门禁或 carried。05 同 §8.1 的 clean checkout/`vnext` tree，2026-11-04T14:46:08Z–14:46:09Z，取得节点占用后以受控 uv wrapper、offline/no-sync、本地预填充环境完成五包 ruff/mypy，exit 0；起止 HEAD 为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`，无代理/下载，完成后释放占用。未运行容量或性能测量。

日志：05 `/home/dev/gdds-test-tmp/p6-dc77-confirm-static-20261104T144608Z.log`；SHA256 `fa2398b69b31e85e24880bfe42dd5a7813659dda4e80d79f550f16340f02731c`。

### 8.4 DC78 单实现与清理约定的提交检查

本轮只修改 DC、设计、计划正文与 kickoff/映射候选；检查时 main 为 `e03c46fd6b9418d0cc84c961921d8cb35576d7a9`，未改产品、ADR/policy、测试治理或审核报告，不触发镜像重建。05 clean checkout 起止 HEAD 为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`，与 main 的 `vnext` tree 同为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。2026-11-04T14:59:19Z–14:59:20Z，取得节点占用后以受控 uv wrapper、offline/no-sync、本地预填充环境完成五包 ruff/mypy，exit 0，无代理/下载，完成后释放占用。此为文档提交检查，不是 Rust 替换验收、性能收益或 carried 结论。

日志：05 `/home/dev/gdds-test-tmp/p6-dc78-static-20261104T145919Z.log`；SHA256 `67143a9e9fc410725a1bf601903230403139f44a26f373a7f34f5373cfca8adc`。

### 8.5 DC78 架构文字同步的提交检查

owner 授权按需修改设计文档及提交/推送后，定向同步 ADR 0001、ADR 0010、Rust policy 与相关计划中的 reference 生命周期。检查起点 main `4bdc1b03fc90bb68dc29830ce22fec0d917b3ca9`；纯设计文字，不触发镜像重建，不改变产品或测试治理。05 使用 §8.4 同一 clean checkout 和相同 `vnext` tree，2026-11-04T15:05:43Z–15:05:44Z，持有本会话节点占用，以受控 uv wrapper、offline/no-sync、本地预填充环境运行五包 ruff/mypy，exit 0；无代理/下载，起止 HEAD 相同，完成后释放占用。不作实现证据或性能结论。

日志：05 `/home/dev/gdds-test-tmp/p6-dc78-architecture-static-20261104T150543Z.log`；SHA256 `1624779e770e496d9afad9e59acddd7ace41c6659163027f66ef8c4ce62e096f`。

### 8.6 DC77 处理窗口与调度方向补充的提交检查

检查起点 main `7ce8e02acd5328801b5c2e3715c4389939827ab7`；仅修改 DC77、Phase 7 计划正文与本稿，不触发镜像重建，不新增规模测试。05 同 §8.4 的 clean checkout/`vnext` tree，2026-11-04T15:15:01Z–15:15:03Z，持有本会话节点占用，以受控 uv wrapper、offline/no-sync、本地预填充环境完成五包 ruff/mypy，exit 0；起止 HEAD 相同，无代理/下载，检查后释放占用。不声明当前产品支持多 worker 或跨日积压处理。

日志：05 `/home/dev/gdds-test-tmp/p6-dc77-scheduling-static-20261104T151501Z.log`；SHA256 `ad3161b7cd914cf416c6097cf97eb265a610ca074fb3330492f8fb5b5eadf347`。

## 9. 本轮收口任务单（2026-11-06，待下一节独立审核）

Owner 已授权本会话推进 S2a 收尾及 S2b kickoff 收口。采用主设计持续协调、每小节新建实施者（GPT-6-Luna/max）与独立审核者（GPT-6-Astra/high）的分工；审核者只读，明确小问题可以直接交实施者修复并复审。每节保留固定提交、交接及审核结论后停止复用该组 agent。系统限制明确报告，不反复重试；不因此扩大产品实施授权。

当前源码核对为 S2a 整合候选 `38ccf8234fa559c47146ed93d054354201a4953a`，并非已退出 main；S2a exit 后由新一组实施/审核者核最终差异。本节新增事实及待交付内容如下：

| 收口项 | 已核事实 / 下一步交付 | 验证边界 |
| --- | --- | --- |
| 消费者与删除清单 | Preview `_materialize_baseline_commit` 与 History `_materialize_commit` 仍以 `ARTIFACTS_REQUIRED` 调用 `materialize_repository_ref`；不能因上传侧不持久原始表就删其共享能力。特殊设备提取定义在 `snapshot_materialization/_catalog.py`，由 `compose.py` 调用 | 逐项列出保留、替换、删除及恢复消费者；保留 FULL 两侧与精确 commit 读取 |
| Arrow 映射 | 现有映射候选继续审核；明确 metadata 单一键名、声明/物理 schema 一致、写入 profile、small/large 阈值及独立预期来源 | 不新建第二套生产 Python IPC 算法；不强制分配数 GiB 证明阈值分支 |
| 覆盖移交 | S2a handoff §9 的三项 Python-only reader 生命周期测试不等于 Rust 已覆盖；旧 adapter 的缺省 budget 字段行为在生产接入前须明确 | 新实际消费者拥有生命周期、预算和失败语义测试；旧算法删除前落实独立向量/Contract |
| 容量输入 | 先交付基于现有样本的有界尺寸普查方案，按实际映射核 buffer/IPC、scope 内去重、FULL/冻结/TTL/导出和临时高水位；分别标明实测、推导和未知 | 可在 06 做设计输入定向检查，未授权重生成整套输入、规模压测或完整真实旅程；不操作 CT108 冻结资源 |
| N/M 与 worker 接线 | adapter 已有进程共享池，尚不能把这一点当作 worker startup 接线已完成；现有部分调用使用 `NeverCancel()`，需明确实际 operation 的取消/截止传递链 | N 测试为 1、测量起点 4；M 依据普查与驻留/临时预约制定，不凭 SQL 文件大小猜值，不把 M 说成 RSS 硬上限 |
| 性能待办 | DC83 已确认 W2 与功能退出分开；其他场景须在最终矩阵中明确区分正确性、结构计数和正式计时 | 不因 W2 决议默默取消 W1/W3 或必要真实数据正确性验证；未知值与实际产品版本保留 |

建议的产品实施切片为：映射/固定向量 → Rust 物化/投影/摘要 → IPC 存储与引用/恢复 → worker 与全部消费者接线 → 唯一生产路径切换、旧实现删除和最终受影响门禁。切片顺序及每步范围在消费者/容量核对和独立 kickoff 审核后定稿；本清单目前只授权准备，不是上述产品切片的开工指令。存储和 Rust 模块已有明确消费者，不为未来 MCP 预建无消费者框架。

本轮设计更新不改产品、测试或容器边界，不声明当前 HEAD 已通过容器门禁。主线 `vnext/` 仍与 06 节点启用时已检查的 `667c6852d` 相同，五包 Ruff/mypy 复用 [节点核对记录](p6-node-06-07-readiness.md) §4/§6 的同代码结果；不为纯文档重复全量 runner 或数据旅程。
