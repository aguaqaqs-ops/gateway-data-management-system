# S2b kickoff（已批准，A 已交付，B 恢复推进）

状态：APPROVED / A–B COMPLETE / C STARTING；2026-11-06。已审技术候选 `1a4adaae05`，独立报告 `8b4be7434b`；[A 任务单](p6-s2b-a-kickoff.md)固定产品 `db7767ffbb`、handoff `b625d775e0`、独立审核 `83b927207a`，A GO。[B 任务单](p6-s2b-b-kickoff.md)固定产品 `b820321c1e`、[handoff](p6-s2b-b-handoff.md) `ac59ffeb79`、[独立审核](p6-s2b-b-delivery-review.md) `0dc93c09a9`，B GO、无未关闭 blocking，06 占用释放、两角色结束；旧不合格日志仍只作诊断。按 DC86 启动 [C](p6-s2b-c-kickoff.md)，新实施者 Sol/high、新审核者 Sol/max；D/E 仍按前置顺序推进。S2b 整体尚未退出。

2026-11-06 收尾进展：S2a 已退出，附注 `p6-s2a-exit` 指向 `53b676a6298d408ccda3a85ee73c7ea223a2311a`；实际门禁、最终闭包/镜像绑定及独立审核见该 tag 注释与[收尾审核](p6-s2a-closeout-review.md)。本稿当前消费者与 mapping 核对以退出源码为准；本轮日期与数据工具信息见 §8.7 和[容量输入报告](p6-s2b-capacity-input-census.md)。该历史收尾记录本身不授权产品；当前 A 授权见 DC85。

2026-11-05 更新（DC81）：owner 已解除 S2a exit 对基准整体 exit 的依赖，并安排新会话推进 S2a 收尾与 S2b 讨论。完整基准由原线独立跟踪；先推进已定功能，允许测量后小范围定向返工，开发验证按影响面收敛。本文仍为待审核准备稿，不将未知性能数值冒称通过，也不自动取消 W2 等退出条款。

2026-11-06 补充（DC81）：owner 明确当前性能指标并非硬性门槛，可结合实测与物理限制讨论合理性。下文 W2 公式保留为当前目标的评估方法；未达或未知时交付事实、约束及调整方案供 owner 决定，不自动阻断所有开发，也不自行放行。具体 W2 测量时点已由下述 DC83 收口；正确性、资源上限、取消/截止、租约和实际业务失败的处置不变。本补充不是整体 kickoff 或产品实施授权。

2026-11-06 时点确认（DC83）：owner 已选择 S2b 功能退出与 W2 性能复核分开。保留 30 秒目标和既有统计口径，CT108 可用时补完整路径测量、最迟 S6 收口；未知不记通过。正确性、恢复、资源边界与必要门禁仍在 S2b 最终候选完成。允许后续小范围定向返工，具体产品实施仍需本 kickoff 收口。

2026-11-06 时点确认（DC84）：Owner 接受容量分阶段收口：先复用输入/保守公式，再做纯 mapping/kernel，之后测真实 IPC；worker 接线前以已实现 kernel+IPC 的 FULL 驻留/临时预约定 M，接线后复核实际 worker 峰值。DC84 也明确 W1 在 S2b 开始做诊断；若 CT108 到功能退出仍无窗口，可最迟延期至 S6。此决定不推迟 t1–t4 正确性，不代表全阶段产品实施授权。

源码基线：S2a 退出附注指向 `53b676a6298d408ccda3a85ee73c7ea223a2311a`；本轮设计和容量候选为 main `d368413861dbcce10691fb65e8dbaba2a208af68`。本轮工具脚本仅用于有限设计输入，不改产品数据路径。映射候选与普查结果分别见[Arrow 映射设计](p6-s2b-arrow-mapping-design.md)和[容量输入小样本普查](p6-s2b-capacity-input-census.md)。

## 1. 开工边界与待补输入

节点补充（DC82，2026-11-06）：owner 新增 06 作为后端日常开发测试节点，07 作为前端 mock 开发测试节点。06 的 Rust、Contract/focused 与小规模 Compose 可按本地占用自主进行；04/06/07 同宿主且 Owner 确认日常资源宽裕。节点就绪见[核对报告](p6-node-06-07-readiness.md)。06 不承接权威全量 runner、正式性能测量或默认全旅程；不操作 CT108 冻结 worktree、tag、inputs、volume 或 evidence。

S2a 与 S1c 已退出；源码消费者与 Arrow mapping 已按 S2a exit 重核。容量输入第一小步完成，M 数值与 worker memory envelope 尚留给 DC84 指定的实现后测量门。独立审核和 Owner kickoff 确认已完成，A 节按 DC85 交付并通过独立审核。DC81 下基准未交付的 DC63 子段不是所有功能开工前置；未测条目保持 unknown。W1/W2/W3 时点按 DC84/DC83 和本节 §6 明列，t1–t4 正确性端到端仍是 S2b 退出内容。

| 输入 | 本次结果 | 剩余闭合点 |
| --- | --- | --- |
| 上传、历史、恢复消费者 | §2 已列保留/替换/删除边界及权威测试 owner；FULL 两侧与精确 commit 读取纳入 | 实施时按每个真实 consumer 切换；不得整文件盲删 |
| Arrow 映射 | profile、metadata 键、canonical 列序、null/offset 规范及独立向量来源见映射设计 | 技术审核后纳入 Owner kickoff 确认 |
| 容量输入 | 06 的 t1 + 两行类型 fixture 结果见容量报告；仅 raw parser buffers | Writer/FULL 实测与 M 定值按 DC84 分阶段；当前没有 IPC/RSS/M 结论 |
| N/M 与 worker | §5 给出 N 配置候选、M 接口和缺口、共享池 startup 与真实取消链 | M 数值在 worker wiring 前定；startup/cancellation 由后续 worker slice 验证 |
| DC63 子段 | §4 保持 pending/unknown，不以 step 总时长替代 | 原基准线交付后更新，不挡首个 mapping/kernel slice |
| W1/W2/W3 与正确性 | §6 明列各自时点；t1–t4 正确性不可省略 | CT108 计时按独占窗口，正确性按节点职责；预约或等窗口，不暗中豁免 |

## 2. 上传侧数据使用方

这里的“原始表”指 SQL reader 的 parser rows 和业务物化中间值；不包括 SourcePackage、规范表 IPC、composite 结果或客户端 Parquet。`application/preview_jobs.py::_sql_materialization_request` 使用 `READERS_REQUIRED` 且不传 artifact store；`_materialize_uploaded_side` 先组合业务数据，再做规范 projection，最后由 `materialize_projected_snapshot(..., artifact_store=store)` 持久化规范产物。S2b 不增加原始 parser 表落盘，也不删除后续 canonical artifact。

以下路径相对 `vnext/backend/src/gateway_backend/`。`保留` 表示仍有真实消费者；`替换` 只改变实现边界；只有所有 caller 切换并且 Contract 向量在位后才删除被替代算法。

| 路径/消费者 | 当前职责 | S2b 边界、owner 与覆盖 |
| --- | --- | --- |
| `application/preview_jobs.py::_materialize_uploaded_side` → `_sql_materialization_request` → `capabilities/snapshot_materialization/compose.py::materialize_business_snapshot` | parser output、XML 与 composite 业务组装；`snapshot_materialization/_catalog.py::extract_special_device_catalog` 负责目录提取 | Rust 承接 SQL 标量物化、过滤及适用诊断；Python composite/XML orchestration 保留。过滤前校验全部 device 行的 gid/dev_addr/description 类型及非-NULL 约束（合法空 description 保留），并保留“原设备表是否非空/特殊命中数”，避免非空但零命中被误诊为空表。point 表过滤前校验 gid/name/dev_addr 三列存在、所有 dev_addr 类型；命中行再校验 gid/name 值。沿用原 Contract 诊断码。owner：`test_snapshot_materialization_business.py`、`test_composite_signal_contracts.py`、`test_composite_signal_bind.py`；覆盖过滤前坏普通行和 0 命中语义。 |
| `capabilities/storage_projection/project.py::project_canonical_table_set` | keyed、keyless、ordered、浏览角色、伪 gid 和 canonical row-layout 投影 | Rust/kernel 替换逐行 projection，保留 `project_canonical_table_set` 对业务 caller 的接口或一次性改 caller。owner：`test_storage_projection_contracts.py`、`test_storage_projection_integrity.py`；空表、重复行、ordered 顺序和摘要各由适用 Contract 覆盖。 |
| `application/preview_jobs.py::_materialize_all_sides`、`_materialize_uploaded_side` | MODIFIED_ONLY 的 MODIFIED；FULL 的 INITIAL 与 MODIFIED；DATASET_REPLACEMENT 的完整两侧 | INITIAL/MODIFIED 每侧走同一 kernel；首侧结果与第二侧物化及后续 compare 同时存活的生命周期纳入 M。owner：`test_preview_job_materialize.py`、`test_comparison_replacement.py`；不能只验 MODIFIED。 |
| Preview checkpoint：`_side_binding_document`、`_materialized_preview_inputs_from_checkpoint`、`_bound_from_side_document`；History 的同类 binding functions | 规范 manifest、row refs、storage facts、canonical closure 持久化与恢复 | writer/reference 更新 owner 描述但保留外层 DDL/export layout；reader 按外层 canonical column name 重排物理列。T1 前按现有 Preview 恢复策略读取/重建，T1 后遵守冻结边界。owner：`test_preview_job_materialize.py` 与 `test_history_compare_jobs.py`。 |
| `application/pair_pipeline.py`、identity assessment、ordered 单侧 facts | 读取 bound canonical rows；ordered 未变化时仍消费当前侧行 | 由 IPC handle 重建相同 Arrow 输入；不得把依赖 pair 的摘要前移到上传 kernel。owner：pair/identity/ordered capability Contract tests。 |
| `preview_jobs.py::surface_artifact_closure`、History assembly、Repository export/replay | 面向客户端的 Parquet surface/records/risk/canonical tables；import replay 的 `storage_projection/import_replay.py::materialize_canonical_source_rows` | 内部 IPC 不替换客户端 Parquet 或 DTO；导出按外层 row-layout。import replay 是 `project.py` helper 的真实消费者，删除前必须切换该 caller。owner：snapshot export cache、`test_storage_projection_import_replay.py`、Repository import/export Contract。 |
| 精确 commit artifacts：`preview_jobs.py::_materialize_baseline_commit`、`history/compare_jobs.py::_materialize_commit`；Repository publication：`infrastructure/repository_write/import_publication.py` → `materialize_repository_ref` | Preview baseline/History exact commit 使用 `ARTIFACTS_REQUIRED`；Repository publication 使用 `READERS_REQUIRED`。三者复用通用 repository-ref materializer，但只有前两者请求 canonical artifacts | 保留两种 policy 与通用 repository materializer，按实际 caller 逐个迁移；不能因上传 raw parser 表不落盘而删除。新 reader owner 的 handle 不越过引用绑定的确切 commit。owner：`test_repository_ref_materialization_protocol.py`、`test_repository_ref_materialization_digest.py`。 |
| Submit T1/PREPARED：`application/submission/import_builder.py`、submit prepare/recovery | T1 冻结的 canonical modified closure 与 PREPARED 冻结导入包 | T1 后缺失不从 SourcePackage、parent 或新 ruleset 重建；稳定失败且 main 不前移；PREPARED 后复用冻结包。owner：`test_submit_import_builder.py`、`test_submit_job_prepare.py`；generic CAS/recovery 继续由 `test_operation_job_recovery.py` 所有。 |
| `snapshot_materialization/_digest.py::{row_content_hash,raw_content_digest_of}` | 实际 consumer 在 `materialize.py`、`compose.py`、`repository_ref.py`、`artifact.py`、`storage_projection/project.py` | 逐 caller 迁移至现有 Shared Kernel framing/批量摘要原语后，删除被替代 Python 算法及只为它保留的 probe/mock；不整文件盲删，也不改 raw file SHA 完整性职责。owner：Shared Kernel vector/Contract + 各调用面既有 digest tests。 |
| 已提交 canonical artifacts 的 Preview/Submit/History read | 精确 commit 快照 | 新 `CanonicalTableStore`/`ArtifactReadHandle` 由 Python 持有 mmap/fd 和生命周期；同一映射分块校验 raw SHA，arrays/readers 先于 mapping 关闭；内存实现走 BufferReader 同协议。miss/corruption 按精确 Dolt commit 校验回填。owner：IPC handle reopen/close/borrow/error Contract 与 `test_snapshot_artifact_roundtrip.py`、`test_snapshot_artifact_faults.py`；不机械复制 S2a Python reader adapter 测试。 |

共用读路径的真实需求是规范表/精确 commit；没有发现另一个要求持久保存 parser 原始表的 consumer。`business_schema_digest_of` 的现有 digest 包含 table_name 且列序无关，保持原算法；canonical IPC 不额外写 instance table name，也不承诺跨 table name 去重。内容地址和实际 export layout 的界线见映射设计 §3。

## 3. 磁盘估算输入与公式

DC76：输入保证 UTC 导出，来源/类型保持现有范围；约 100 MB SQL 是少数已知输入，不是上限。当前有界测量使用既有 t1 和已跟踪两行类型 fixture，结果与限制见[容量输入报告](p6-s2b-capacity-input-census.md)。它测的是 S2a parser buffers；不把约 158.7 MB V6 合成输入、SQL 压缩包长度或 t1 比例当作 canonical IPC、完整路径或大表高水位。

估算对象是**未压缩规范 IPC**，不是 SQL 压缩包大小或 parser RSS。mapping §4 固定 Arrow profile，[容量报告](p6-s2b-capacity-input-census.md)给每列初始公式；只有 A 的纯内存 codec 与 B/C 的实际业务 kernel/store 完成后，才可把逐表列数、fixed-width/bitmap、offset/payload、批次/framing/alignment 校准成 canonical bytes。文件身份沿用设计 §8.2 五项：projection version、business schema digest、row count、table digest、mapping version；引用集合按真实 scope 去重，不把不同 table name 合并。

```text
C = bytes(unique(head ∪ active Preview ∪ frozen Attempt ∪ retained TTL canonical files))
D_peak = C + exported Parquet/cache + SourcePackage + Dolt + control metadata
         + temporary write/staging high-water + retained evidence/volume copies
required_increment = D_peak - already_present_bytes + agreed_reserve
capacity_ok = required_increment <= currently_available_bytes
```

集合以同一时刻的实际引用和 TTL 情景建立；FULL 双侧、旧 head、新 head、仍受保护的 Attempt 可同时存在。临时文件与最终文件 rename 不重复算两份常驻副本，但计入发布前新旧文件共存的高水位。跨项目按实际 scope 的共享规则计算，不能假定全局去重。输出还要分列 cleanup/TTL 前后体积。

历史资料 `p6-node-init-report.md`（记录日期 2026-10-24）给 ct108 295 G 可用，只是旧节点容量参考，不是当前剩余量或生产预算。V6 的 158.7 MB SQL 与 569–753 MiB RSS 不能换算成规范 IPC。t1 parser 的 measured counts/bytes 已提供第一单位输入，但 canonical IPC、FULL 两侧峰值和生产引用分布仍未测，故磁盘总量与 M 仍 OPEN；见 DC84 分阶段闭合，不增加当前全旅程普查。

本次报告的输出为匿名计数与 buffer 字节，不含行内容；具体节点、时间、commit、输入摘要及 log SHA 已集中在报告。后续 IPC/FULL 校准再输出逐类物理字节、scope 去重引用数量、临时高水位及场景活跃 Preview/Attempt/TTL。CT108 正式测量仍独占；节点被占用时预约等待，不迁移其冻结材料。预算超限按设计 §17 停止交 Owner，讨论压缩或容量；不自行引入容量淘汰。

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

接下来的 S2b mapping/IPC 阶段先测实际输出类型/行数、文件 bytes 与 FULL/恢复/临时峰值，再关闭单任务 M 和必要容量区间；DC84 不要求在新 writer 之前伪测。历史 SourcePackage、Dolt 新建/变更增量和生产引用分布属于后续容量交付，不能由两个小样本外推。S2b 不创建 500/1,000/10,000 份仓库作门禁；生产总容量与并发验证按 DC37 留给 Phase 7，参考节点可用空间不能冒充生产磁盘规格。

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

## 5. Rust 接入、N/M 与执行控制

整体 kickoff 已获 Owner 确认，A 按 DC85 完成交付，B–E 已按 DC86 获逐节实施授权；本节定义全部切片的边界和验证顺序。DC78 要求一个 Rust 生产路径：`parse → business validation/materialization → canonical projection/hash → IPC`；不留生产 Python fallback、旧格式双读/双写或用户可选引擎 flag。迁移期间可在测试/开发验证中对照 Python frozen semantics；独立向量和 Contract 落地、所有 real consumers 切换后，删除被替代算法、差分入口及只服务旧实现的 mock/test。保留 Python orchestration、PyO3/Arrow adapter、composite/XML 业务、错误传播与实际恢复消费者。

### 5.1 N 配置与共享池

候选设置属于 worker startup 的进程级 kernel runtime，不是每次调用的自由参数：

| 项 | 候选值 |
| --- | --- |
| 设置名 | `GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_THREADS` |
| 含义/单位 | 一个 operation worker 进程内共享的 Rust Rayon 与 PyArrow CPU/I/O pool 线程数 `N` |
| 默认值 | `1`，保守的正确性默认；完整路径资源允许时，以 `4` 作为首个调优比较点，不预称最佳值 |
| 接受范围 | 整数 `1..=256`；256 是现有 Rust adapter `MAX_PARSER_THREADS` 的技术上界，不是推荐配置 |

Worker bootstrap 在注册/派发任何 kernel operation 之前显式调用一次 runtime initializer，固定该 `N`；当前 Rust `OnceLock` 池沿用同一个 N。`parse_sql` 及之后的 kernel adapter 不再带可自由改变的 `pool_threads=1` 默认值，不以假 parse 初始化；无初始化或与已建池 N 冲突时启动失败。pyarrow 的 CPU/I/O pool 同步设为相同 N；每次 operation、每表、FULL 每侧都不建池。N=1 与 N>1 验收分进程运行（或在独立 core unit 内创建各自池），不破坏 `OnceLock` 不变量。

### 5.2 M 接口、预约与仍待测量的数值

| 项 | 候选值/边界 |
| --- | --- |
| 设置名 | `GATEWAY_BACKEND_OPERATION_WORKER_KERNEL_MEMORY_BUDGET_BYTES` |
| 单位 | bytes，M 是单个 operation 的计算准入预约，不是 RSS 严格上限 |
| 格式/下界 | 正整数且 `M > 0`；worker 接线前作为 required setting，缺失/非法值拒绝启动 |
| 默认/上界 | 目前不填数值默认与上界。writer/FULL 峰值尚未实现测量，且现有部署未声明 worker memory envelope 和固定 runtime reserve；必须在 DC84 worker 接线前门以实际实现测量与部署 envelope 定出，`M <= envelope - reserve` |

预算按一个 worker process 的实际生命周期预约：SourcePackage/SQL input 中实际持有的 bytes；parser buffers 按共享 backing allocation 去重；Rust canonical output、伪列/composite、排序/索引与 filter 暂存；IPC write buffers、文件内容以及 `Vec → PyBytes` 复制重叠；本 operation 打开的 mmap/ArtifactReadHandle 及其 Arrow views 按 pin/lifetime 对完整被引用 bytes 保守预约，同一 mapping 共享引用只算一次；FULL 两侧同时保留的结果、baseline 与发布前 staging 都纳入峰值。未被当前 operation 打开/读取的全局 artifact 只占磁盘，不作为本次 M 的 RAM。

reservation 必须在分配/增长前申请；共享 backing buffer 只预约一次；若增长后总预约将超过 M，稳定拒绝该次增长并返回既有错误诊断，丢弃未完成产物，不能先分配完整对象再检查。现 `max_in_flight=1` 意味着每进程最多一个 active operation；若未来并发设置变化，worker 总预约为每个 active operation 的 M 之和加共享基础项。M 不等于进程 RSS，实际 RSS/page cache/cgroup limit 与 reservation 分开取证。无法给出有界容量的单表在 publish 前稳定拒绝；不靠关预算通过。

DC84 的测量顺序：A slice 交付唯一 in-memory IPC codec 后，以固定 vectors 实测其 bytes/profile overhead；B 产出真实 canonical rows；C 复用同一 codec 接 store/ref/recovery，并测业务 IPC 与 FULL/临时重叠。随后、worker wiring 前固定 M/default/max 和 growth rejection；最后接 worker并复核实际峰值。当前尚缺的是新 codec/真实业务 buffers 与文件 bytes，以及部署 envelope/reserve 数字，不是再跑更大 SQL 样本。该缺口不阻止首个 codec/kernel slice，但阻止把猜测 M 接进 worker。

### 5.3 取消、截止时间与发布边界

现 `ExecutionControl` 只有 `cancel_requested`、`drain_requested`、`lease_lost`，`ParserInvocationContext.deadline_monotonic` 可选；不存在固定 operation deadline。现 Preview `build_materialize_inputs_handler` 没把 control 传给 `_materialize_all_sides`/`_materialize_uploaded_side`，History `_materialize_commit` 使用 `NeverCancel()`。接线需要使实际调用链成为 `ExecutionControl → operation handler → Preview/History materializer → cancellation probe → Rust adapter/core`，同时传到 projection/materialization 的 probe。

probe `is_set()` 可在 cancel、drain 或 lease_lost 任一状态到达时停止长 kernel；返回后由 caller 读取原始 control 状态分类，不能把三类都压成用户取消。cancel 继续走 operation cancellation contract；drain 遵循 worker handoff/排空语义；lease_lost 复用 `LeaseSession` 禁止发布 checkpoint、正式 artifact 引用或业务终态。尚未挂接的临时产物沿用现有清理规则，不新增逐次文件写入的租约证明。当前没有 operation 固定截止时传 `deadline_monotonic=None`；caller 日后有真实 finite deadline 时原样使用单调时钟并由 worker 集成测试注入。不得拿可续租的 `lease_deadline`、`drain_deadline` 或 10-minute benchmark ceiling 造一个 kernel operation timeout。

### 5.4 分阶段实施和验证 owner

| 切片（只在 kickoff 获批后） | 改动边界 | 每步验证/复用 |
| --- | --- | --- |
| A. Mapping + 纯内存 codec | Rust Arrow 59.1 schema/value metadata 与唯一 IPC codec，产出 arrays/file bytes；不接 ArtifactStore、mmap、worker 或 operation config | 06 Rust focused + backend mapping Contract；独立 SET/Shared Kernel vectors；N=1/N、empty/null/batch/file bytes determinism。arrow-ipc/arrow-select 当前属 core dev-deps，转生产依赖时核 Cargo.lock/features、按 DC67 预填依赖并按 AGENTS 判断镜像闭包 |
| B. 业务 kernel | 在 A codec 上接物化/完整诊断/特殊设备与点表过滤/composite、canonical projection/hash；Python consumers 切换前继续工作 | 06 对应 Rust/backend focused；复用 composite、projection、repository-ref/export/replay Contract；替换期对照旧 frozen semantics，最终不留双实现 |
| C. Store/ref/recovery | 仅复用 A 的 codec；`CanonicalTableStore.open(ref, bound_descriptor) -> ContextManager[ArtifactReadHandle]`、raw SHA、atomic put、mmap、reference、恢复与 TTL。Handle 不暴露路径，只给 schema/batch reader；同 ref reopen 是独立 handle，close 幂等且 closed read 稳定失败 | 06 backend storage/SQLite integration、真实文件系统；exact commit fallback、protected/FULL/T1/PREPARED；引用与 head 同事务；C 测实际业务 IPC/FULL，worker 前确定 M |
| D. Worker/所有 operation callers | startup N/M、Preview FULL 两侧、History exact commit、Submit/recovery、cancel/drain/lease 分类 | 06 worker/Preview/History/Submit integration；实际 control 进入 kernel、EOF/cancel-before-publish、M growth/reject/overlap。改 settings/env/startup/image boundary 时重建最终候选并跑 Compose gate |
| E. 单路径与删除 | 最后一批 callers 迁移后删除旧 Python 核心算法与 diff-only入口；检索剩余 import/consumer | 06 focused/静态 consumer search；最终候选 04 按 S2b stage gate 跑权威 runner，Rust 必须覆盖；包沿用需满足 AGENTS closure。Stage exit 的 container result 必须绑定最终 HEAD：当前 HEAD gate，或符合 AGENTS 的同节点镜像等价 carried |

C 的 TTL 复用现有 artifact protection 与 expiry/lookup 约定：当前 BaselineHead、冻结 Attempt 等强引用在其 owner 释放前不按 TTL 过期；释放最后一个强引用时在同一事务登记/触达 TTL owner，lookup 按 expires_at_us 拒绝过期条目，遵循 `sqlite_snapshot_export_cache` 的 lookup/put/touch 模式；共享对象只有在全部强引用已释放且不存在未过期 TTL 保护时才可清理。新增 BaselineHead owner 不要求重建保护机制；若需补 lookup/expiry 字段，直接改唯一 baseline schema 和 Contract，不建新发布/证据状态机。

2026-11-06 C 前置源码核对：DC42 的正式引用只绑定业务 BaselineHead，推进点是 Business Lifecycle Contract §5 的 `StartArchive`（`application/archive/start.py`），不是 Submit finalize；P6 design §8.2/§15 的旧措辞已订正。C 在现有 Archive Head CAS 事务内移交引用，Submit finalize 仍只结束其冻结引用并按适用 TTL 保留派生副本，不改业务 Head。不得在归档事务内重新物化、调用 Repository import 或添加长文件读取；缺失的已提交派生副本仍由真实读者按精确 commit 回填。C 的独立审核须核对初始化/回填与 Archive 的正式引用 owner，以及 Submit finalize、abort 等释放点的 TTL 衔接。旧讨论和 S5 diff/risk 设计中的同类“finalize 移动 head”措辞不构成 S2b 授权，S5 按其真实引用 owner 另行收口。

S2a 的三个 Python-only reader 生命周期证明要移交给真实 owner：old single-consumer/reopen/close → C 的 `ArtifactReadHandle` 独立 reopen、close 幂等及关闭后失败；stream error → C 的 IPC reader 失效且没有可发布产物；EOF/cancel → D 的真实 worker 在 EOF/publish 前检查 cancellation/control。对应测试放在实际 storage/worker Contract owner 中，不机械搬旧 adapter runtime mock/test。

共享池 initialization 不另建 runtime 平台；artifact handle 不改变 publication state machine。dependency/lock/Rust base image 变化按 AGENTS 的 CT201 构建与 LAN 预填流程；测试节点离线，不在 CT201 跑产品/测试。即使 Arrow 版本保持 59.1，dev-deps 转 production closure 也要按锁、feature 与实际镜像闭包判定；阶段 exit 仍需最终 HEAD image bind 或正式 carried。

## 6. 验收与时点矩阵

| 类别 | 必须验证 | owner/节点与时点 |
| --- | --- | --- |
| Mapping/value contract | Int/decimal/float/null/BIT/ENUM/SET/JSON/time、空表/全 NULL、声明/metadata/type 一致、列序置换得到同 bytes 且 reader 按外层 layout 重排、N/chunk 确定性 | mapping/Shared Kernel vectors + backend Contract；06 focused |
| 业务结果与诊断 | keyed/keyless/ordered、重复行/composite；全部 device 行和 point 列过滤前验证；FULL INITIAL+MODIFIED、MODIFIED_ONLY、DATASET_REPLACEMENT 的表集合/摘要/records/risk/diagnostics | application/capability owner；每个不变量一权威测试，最终端到端 t1–t4 |
| IPC 生命周期与恢复 | SHA/metadata 损坏拒绝；独立 handle reopen/close/借用边界；stream error 后 reader 无可发布物；head+正式引用同事务；protected/TTL/shared ref；PREPARED/T1 冻结；miss/corruption 精确 commit 回填 | storage owner + Submit/Preview/History owner；06 filesystem/SQLite integration |
| W2 结构计数 | 复用设计 §16.2 适用公式；W2 baseline 行读取/比较为 0，规范内容命中不重写；计数不由性能样本替代 | capability/application count Contract；06 focused |
| 资源与执行控制 | invalid N/M startup；同池无冲突；reservation 先于增长；FULL 两侧/M 计算拒绝；actual worker cancel/drain/lease_lost 区分；finite deadline 注入；没有 deadline 就 None | worker owner；06 worker Integration，M 在 C 完成且接线前确定。lease_lost 复用 `LeaseSession` 安全发布边界 |
| 真实业务正确性 | S2b 涉及的 t1–t4 Preview/History/Submit 生产路径正确性端到端 | t1–t3 在 05，t4 在 CT108，按现节点职责；CT108 忙时预约/等待，或先取得 Owner 对替代节点的明确授权。性能延期不豁免 t4 正确性 |
| Final authority/container | 最终候选的 runner package closure（Rust 必须覆盖）；S2b stage exit 的 container result 必须绑定最终 HEAD，即当前候选验证或满足 AGENTS 的同节点正式 carried。触及 Compose/startup/env/health/signal/volume 等边界时重建该 HEAD 并跑相应 gate | 04 权威节点做最终 stage gate；正式门禁过程 clean/committed、按 node/cache/日志规则。06 不冒充权威结果 |

### 6.1 W1–W4 与结构性指标

- **W1**：S2b 开始做诊断；CT108 无窗口且到功能 exit 仍不可用时，可按 DC84 延后，最迟 S6 收口。正式计时仍独占 CT108。
- **W2**：DC83 保留 30 秒目标和统计口径，CT108 可用时做完整路径测量，最迟 S6；未知不 PASS，不阻挡 S2b 功能 exit。计算仍按设计 §16.3 的 1 次预热 + 3 次测量、中位数/范围；未归因削减不填 0，S3 的比较加速不计入 W2。
- **W3**：按原计划从 S3 起测，S6 留下证据；不得因 W2 分离而默默豁免。
- **W4**：W4 lease failure 已复现但根因未定，作为独立问题保留；不假设 kernel/IPC 改造会修复它。真实业务 lease failure 仍按故障处置，不因 W1/W2 时点变更豁免。
- **正确性**：t1–t4 端到端仍属于 S2b；W1/W2/W3 的正式性能窗口不改变 05/CT108 正确性节点责任。

W2 可达性保留原公式，用于性能复核而非功能 exit：

```text
reachable = no_unknown_segments
            AND all_reductions_have_evidence_and_named_stage
            AND no_overlapping_or_excess_reductions
            AND W2_measured_candidate - sum(remaining_reduction_upper_bounds) <= 30 seconds
```

正确性、恢复、资源上限、取消/截止、安全发布与必要门禁均须在 S2b 功能候选关闭；只有 W2/W1 特定计时可按 DC83/DC84 时点排期。

## 7. 确认记录

- kickoff 审核：候选 `1a4adaae05` 的独立结论为 READY_FOR_OWNER，无剩余技术 Finding；报告源提交 `4074ffa821`，合入 main 为 `8b4be7434b`。审核结论与授权分开；Owner 随后以 DC85 批准 kickoff 及 A。
- owner 已确认：DC76 输入约定；DC77 容量分层/Phase 7 方向；DC83 W2 与功能 exit 分离；DC84 容量分步与 W1 最迟 S6。整体 kickoff 及 A 实施已按 DC85 确认。
- M 数值/默认/部署 envelope：按 DC84 在 IPC + FULL 生命周期测量后、worker 接线前定；不是阻止首个 mapping/kernel slice 的新样本前置。
- 后续授权：Owner 已按 DC86 授权逐节推进 B–E，每节新建 Sol/high 实施者；B 已由 Astra/high 审核完成，C–E 新独立审核者为 Sol/xhigh 或 max（DC86 最新补充），C 因事务/CAS 与冻结恢复选择 max；额外角色必须先交 Owner 说明原因、模型和思考强度并获确认。A、B 两节角色均已结束，C 按固定前置交接启动，D/E 依次推进。

## 8. 文档与准备工具检查记录（不是阶段取证）

本节开头及 §8.1–§8.6 是 2026-11-04 的历史记录，保留原提交与日志；当前收口检查见 §8.7，不以旧源码 tree 冒充本轮检查依据。

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

### 8.7 本轮收口与准备工具检查

本轮增加有界容量普查工具 `583b69c838`，其计数字段类型修复为 `f5dafdfce8`；不改生产调用路径。06 clean 提交 `a3f49290628` 的两份样本均 exit 0，五个 Python 包各自 Ruff/mypy 通过；同次工具单独 mypy 的失败保留。修复后在 06 clean `d368413861` 定向重做工具 Ruff、显式 mypy 和 shell 语法检查，全部通过。审核确认类型修复不改变计数，样本仍绑定原实际运行提交，不重新标作新提交实测。

运行时段、完整 SHA、输入/扩展身份和结果见[容量输入报告](p6-s2b-capacity-input-census.md)。随后修改仅为设计文档，复用这些同代码静态检查；本轮准备不触发镜像重建，不声明新的产品容器门禁或 carried。最后实际产品容器身份仍引用 `p6-s2a-exit` 的退出记录；这里不将其冒称为当前准备工具提交的新门禁。06 的占用已释放，未运行完整 runner、完整真实数据旅程或新合成输入生成。

## 9. 本轮 kickoff 交付状态（2026-11-06）

本轮按 `p6-s2a-exit^{commit}=53b676a6298d408ccda3a85ee73c7ea223a2311a` 重核 S2b 源码消费者，完成保留/替换边界、Arrow file profile、metadata 与独立 SET vector 约定，并在 06 用 t1 + 已跟踪两行 fixture 完成有界 raw parser buffer 普查。实测、推导、未知和全部日志摘要集中在[容量输入报告](p6-s2b-capacity-input-census.md)。

kickoff 技术候选分为 A mapping + 纯内存 codec、B 业务 kernel、C store/ref/recovery、D worker/consumer wiring、E 唯一生产路径与旧算法清理。每步 owner、验证和阶段门见 §5.4/§6。首节 A 可在没有 worker、ArtifactStore 或生产 M 的情况下实现固定 mapping/profile bytes vectors；后续 M 按 DC84 在实际业务 IPC/FULL 测量之后、D worker 接线之前确定。

本稿及相关 mapping/capacity 文档已通过独立技术审核，Owner 随后以 DC85 确认 kickoff 及首节 A 范围；A 产品与独立审核已按页首固定提交交付。DC63 子段、正式 W1/W2/W3 计时和 W4 lease 诊断按 §4/§6 保持各自状态，不用未知值代替。A 的局部 bytes 和资源验证不代表 FULL、worker RSS、生产 M 或性能目标通过；后续切片及阶段退出仍按本文原定范围办理。

### 9.1 设计、实施与审核分工

Owner 于本轮确认主设计持续协调，每小节新建实施者与独立审核者；B 审核者保持 GPT-6-Astra/high，C–E 按最新安排改 GPT-6.1-Sol/xhigh 或 max；实施者原定 GPT-6-Luna/max，S2b 已按 DC86 最新补充调整为 GPT-6.1-Sol/high；小节结束停止这两个角色，下节重新创建，不复用前节上下文代替交接。若系统不能删除会话或需要手工新开/交接，明确报告，不反复尝试。

设计者可以直接维护设计、计划、决议和任务说明；审核者可以直接修正文档事实、链接、措辞及已确认决议的一致性，记录修改并由设计者复核。实质性的设计或验收变更先与设计者对齐。产品代码和测试代码原则上由实施者修改、审核者独立复审；明确的小问题允许双方直接沟通闭环，不能通过改写日志、证据或放宽验收来消除 Finding。文档按文件或章节交接编辑权，避免并发覆盖。

目标不合理、真实业务场景缺口、设计冲突或多轮修复不能收敛时，停止受影响的小节并带具体事实与推荐方案交 Owner 讨论；明确的小问题继续自主处理。未经明确授权不推送，不改写已被引用的提交。
