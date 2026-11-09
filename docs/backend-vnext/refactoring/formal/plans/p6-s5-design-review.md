# S5 设计独审归档

本文件逐字保留独立审核原件。R1候选`309571984d96d171e9b0c3e24a9cb82ec64c2ead`结论为DESIGN_CHANGES_REQUIRED；修订已交原审核者连续复审，尚不宣称DESIGN_CLEAR。任何设计结论均不构成S5产品实施或退出授权。

R1外置原件：`/home/dev/gdds-test-tmp/p6-s5-design-review/review-r1.md`；SHA256：`363cfcf24f6503923c2849e8b45b358ac2b617bdd01770623ae2df24eba16cad`。以下原文未改写。

---

# Phase 6 S5 独立设计审核 R1

结论：**DESIGN_CHANGES_REQUIRED**。固定候选存在三项可在现有授权范围内修正的设计问题；不需要扩大真实验收范围或另行改变业务 Contract。修订并由本审核者连续复审后，才可给出 DESIGN_CLEAR；任何设计结论均不代表产品 GO。

## 1. 固定对象与审核方法

- Candidate：`309571984d96d171e9b0c3e24a9cb82ec64c2ead`。
- Base：`4c648965286ec751c4395cd6111f11838610299c`。
- 只读 detached worktree：`/home/dev/gdds-s5-design-review-r1`。开始与报告前核 HEAD、detached 状态、index/worktree/untracked；`git status --porcelain=v1` 均为空。
- `legacy` 指向 `/home/dev/gateway-data-management-system/legacy`。
- Candidate Rust tree：`e2a901417b19259ece669637a41545e774261445`，保持已退出产品边界。
- 区间仅改八份文档，没有产品源码修改。本人没有修改被审 worktree，没有创建子审核者，没有运行测试、编译、lint、镜像构建、真实数据旅程或容量原型，也没有 push/tag。
- 本报告由本轮独立审核者编写。协调者提供的定位线索均以固定候选的源码或 owning Contract 复核，未将其意见直接当作证据。

直接输入包括 AGENTS、testing conventions、S5 discussion prompt/design/kickoff/coordination/review prompt；总设计与执行计划的 S5、缓存、计数、阶段和验证条款；DC38–43、47、55、91、97、98，以及恢复分界的 DC94；S3/S4 handoff/exit 原审及 S3 §9 与相关实现审核的输入边界；Comparison/Risk/Surface/Bundle 与 artifact 读写约束；Canonical Storage、Shared Canonical Encoding、Operation Lifecycle、Repository Service 的相关 authority、编码、恢复和请求边界；比例化/Rust 政策与 ADR0009/0012/0013；Q18、BE-d、前端交接的当前 consumer 范围。历史阶段只核本阶段依赖边界，没有重审 S3/S4 全阶段结论或复跑其证据。

源码只读核查集中于 History compare_jobs 的 distinct commits/materialize/checkpoint 恢复，repository-ref materialization 与 exact-commit canonical table access，pair planning/production/native/records/artifacts，risk_evaluation/_engine，客户端 Parquet export 与 SQLite cache/protection，Submit finalize transaction、Archive Head Contract，以及 Repository client catalog/Arrow/retry。对声明仍待实施的新接口只作可实现性审核，不把设计描述视为已经存在的产品行为。

## 2. 必须修订的问题

### R1 — P1：风险事件重放前移时间检查，改变已冻结控制语义

位置：`docs/backend-vnext/refactoring/formal/plans/p6-s5-design.md:157`，§5。

候选写成每次 emit 前检查取消、截止、table/pair 时间，然后检查 cap、等级过滤和编号输出。实际 `vnext/backend/src/gateway_backend/capabilities/risk_evaluation/_engine.py:442–489` 的顺序为：cap（同时触界时 pair 优先）→记录候选→等级过滤→必要输出预约及 append/编号→`_check_table`。被过滤事件直接 return，不执行该 emit 的 table 时间检查。S3 design §9.2 已明确保留原控制位置。

这不是无关紧要的实现选择。在 cap 与时间同时触界、仅有过滤候选、或最后一条可见候选越过时间阈值时，检查前移会改变错误优先级、降级/丢弃结果及标注流。命中缓存仍需检查当前控制状态，但不能据此改动既有时间 Contract。

最小修订：§5 按现 emit 路径逐项明确原顺序，冷执行和重放共用该控制实现；closure 仍在原事件位置核当前闭合。批次边界的 operation cancel/deadline 检查单独说明，不能替代或前移 table/pair 计时检查。实现阶段在 Risk owner 的 focused 向量覆盖 cap/时间同时触界、过滤候选和末条 emit，沿用原期望，不更新 golden 来接受语义变化。无需新增真实旅程。

### R2 — P1：PREPARED 被误当作导入包已经冻结的恢复分界

位置：同设计 §6.2，188 行；§7，206–207 行。

“T2 与 PREPARED 重试复用原 prepare/import 包”和“PREPARED 后缺原 canonical 副本沿原冻结包恢复”的表述不成立。`docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md:156–175` 已按 DC94 明确：T1 接受后 Attempt 就是 PREPARED，此时可能尚无 prepare checkpoint、尚未生成包。只有 prepare checkpoint 持久化后，导入包及 raw SHA 才成为固定恢复来源。

若实施者按候选状态名分支，会在 T1 后但 checkpoint 前误寻并不存在的包，或为了恢复去重建冻结输入；也会使“缺 canonical 稳定失败”和“复用冻结包”两行互相冲突。此处涉及不可逆 effect 前的来源选择，不是可选 cache miss。

最小修订：显式按三段写明：T1 前；T1 后至 prepare checkpoint 持久化前；prepare checkpoint 持久化后（含 EFFECT_PENDING）。中间段缺冻结规范文件稳定失败，不用 parent、新 ruleset、SourcePackage 或计算 cache 替代；尚未发表 checkpoint 的纯计算沿既有机制处理。后一段复用原包/ref/raw SHA/effect key，包缺失不得重建或换 key。引用 DC94 和上述 owning Contract，不更改现有状态机与恢复实现。

### R3 — P2：neutral 格式对实际消费者与 batch 约束的描述有确定错误

位置：同设计 §4.1，115–123 行；§6.1，171 行；kickoff §A 的 Rust 源码定位。

保留 facts 序、artifact 序与风险投影的总体方案可实现，但“每个 standard/ordered/blank 族均有三视图、最多九视图”没有对应当前 consumer。`vnext/rust/gateway-compute-python/src/comparison_records.rs:254–338` 的 `prepare_risk_batches` 只消费 STANDARD facts-order；Ordered 结果也取其 `standard_records/standard_facts_order`。ORDERED、BLANK 没有独立 risk-record 投影消费者。该文件 `risk_schema` 的确切 schema 为 `record_kind: Utf8 non-null`、`row_identity: FixedSizeBinary(32) nullable`、`changed_columns: List(item Utf8 nullable) non-null`，不是按三族 artifact schema 各推导一个风险视图。

此外，“现上限 1024 个 batch”将行数误作批次数。`gateway-compute-core/src/records/builders.rs:163–164` 在每批 1024 行时 flush；backend `capabilities/comparison/artifacts.py` 的对应校验也是每 batch 的 num_rows。现有记录上限 2,000,000 允许超过 1024 个 batch。误用该上限可能让合法大结果被错误拒绝、失去缓存，或促使实现 rechunk 后破坏当前 Parquet raw bytes。实际 core records 源码目录为 `gateway-compute-core/src/records/`，不是 `src/comparison/records/`。

最小修订：载荷定义为各族 facts/artifact 视图加一个 STANDARD facts-order 风险投影，即最多 3 facts + 3 artifact + 1 risk（不要求空族实际落文件）；同步 member_refs 上限/闭合说明，直接写明风险 schema 和消费者。manifest 保存实际原 batch row_count 序列，保持每 batch 至多 1024 行及现记录上限，不虚构现有 batch 数量限制；若为 optional manifest 另设容量上限，明确这是 cache 不保留条件而非产品接受范围。修正源码路径。无需改客户端 Parquet、风险规则或扩大持久机制。

## 3. 逐项设计判定与实现关注点

| 审查项 | 本轮独立判断与依据 |
| --- | --- |
| 1. History metadata-demand/恢复 | §2 将 authority 校验置于 cache 前，并按有向 A→B/B→C、distinct exact commits 建需求集合，方向正确。现 repository_ref 和 canonical table access 证明 catalog、descriptor、storage projection 可以分离描述与读行。实施 A/B 必须把当前 load_table 中的绑定校验保留到 describe/ensure_rows 的对应 owner，不能因未读行漏 schema/count/FINAL 校验。checkpoint 缓存提示不作为权威，assemble 重新 lookup 后补需行，避免冷暖窗口缺文件成为错误完成。未见另一个设计阻塞。 |
| 2. 完整 task identity | TableTaskInputV1 同时驱动实际 native 输入与缓存投影，比手写 cache 字段白名单可靠；§3 已覆盖两侧 effective key/storage view/projection/schema/count/rules/profile/diagnostics/detail/scope。精确 commit 在合法 FINAL authority 校验后才退出内容 key；business schema 内表名保留，因此没有承诺跨不同表名强制命中。字段分类与 NotCacheable 是实施 A 的关键证据，当前不把尚未实现类型当作已证明无遗漏。 |
| 3. neutral/digest | Rust `records/facts.rs` 的事实记录确实不含 table_name，table/core 外层绑定独立，含 typed frames、blank entity_key_kind 和事实序。保留 artifact 序及原 batch 边界后，新统一 handle 可以重算当前 table/core/records 闭合而不重建 StandardComputation；不能仅拷旧 Parquet。R3 须先修正具体载荷。事实 JCS 的 owner validator 是待实施入口，现 artifact validator 不能被误称已具备全部 facts-row 校验。 |
| 4. 风险 | 完整事件、过滤前 cap、pair 优先、不同 degraded 累计、每次 CHECK_RECORDS_CLOSURE、当前编号、禁止截断前缀和不为缓存多算均符合实际 engine 需求；R1 是确定的控制顺序错误。diff hit/risk miss 从恢复 STANDARD facts-order 执行，具有源码消费者依据。 |
| 5. cache 生命周期 | entries + uses + 既有 protection 有真实消费者：跨 operation 复用与 Submit 精确 touch。root read session→短 DB、lookup pin→文件校验、发布完整成员后登记、条件失效旧版本，可以与现 SQLite protection/ArtifactStore 协作。reader 有独立 pin，替换 writer 不需另造 singleflight/journal。TTL 只影响性能，manifest/raw/schema/count 对 derived cache 足够，不要求同 euid 恶意生产者证明。 |
| 6. T3/恢复/Head | 通过 attempt.preview_result_id 解析真实 producer，并只 touch matching scope/key/manifest；已过期/缺失不补造。窄 SAVEPOINT 只吞已知 optional cache 载荷/约束异常，IOERR/CORRUPT/FULL/BUSY、外层回滚、CAS/scope/未知异常继续传播，与原 finalize 事务边界相容。合法 FINALIZED replay 不续 TTL；Repository main CAS 与 Archive BaselineHead 分开，未新增跨服务原子性承诺。R2 须修恢复分段。 |
| 7. M/N/取消/retry | §8 已覆盖 metadata、mapping、FFI、capacity、索引、native 输出、IPC/Parquet/export bytes 及最后 consumer，命中不是零预算。optional 保留优先释放、原必要计算只重新准入一次，符合 S3 安全模型。N1 的 C=min(N,8) 为 1，显式 context 和有界队列避免线程隐式继承问题。三次 retry 应明确属于现 client 单次请求重试策略，禁止新增外层 HTTP 重试相乘；原 durable step 的 retryable failure/recovery 仍由 Lifecycle owner 决定，不应误读为 S5 全新全局三次状态机。此为实现说明，未发现需另造 retry 机制的依据。 |
| 8. records/bundle/边界 | §4.2/§10 正确区分真实 records library 语义读取与 bundle raw/ref/closure 策略；存在 native records handle 和批量 validator 的实际扩展路径。未虚构 records HTTP API，未以 bundle raw SHA 代替 records 语义验证。facade/import guard 与 core 无 DB/filesystem 方向符合 Rust policy。Q18、BE-d 输入不等于 FE3c 签收，本轮不代签。 |
| 9. H1/H3/计数 | §9 将零比较限定为完整 task 命中且资源可恢复，将零 Dolt 再限定为 canonical/export 合并需求满足；FULL baseline→modified 首次未计算可 miss。metadata、读取尝试、dispatch、kernel、restore、validate/rebind 分开计，未把 native restore 隐藏为零 native。H2/三节点由 C focused 承担，无理由复制真实容量矩阵。 |
| 10. A–E/证据范围 | A 固定 owner/schema/独立向量，B 接输入与需求，C 接真实消费者，D 事务与恢复，E 门禁和最小真实 t1，依赖可交付。标准 t1 v1/v2 合法存量可以复用；冷/新 operation 暖 History、真实 records reader 与完整 tar 必要，FULL/三节点/坏 cache/恢复 focused 足够。若存量与新唯一 schema 不相容，只补合法最小前置，不转成兼容层或每状态全旅程。carried 仍需同源实际通过和闭包比较，失败/未知不能作通过。 |
| 11. 当前治理 | DC91/DC97 统一池与按改动选择证据没有移除专用节点、占用、离线、clean/锁文件、五包静态、Rust 工具链、scope/事务和最终项目六包门禁。AGENTS 仍有旧“完整 runner 一次”绝对化语句，testing conventions 保留历史约 1490 项/12 秒及过去 S3 ready 措辞，宜按 Owner 本轮授权清理当前执行说明，避免与现行比例化口径冲突；历史 handoff/原审应原样保留。该清理不是新增验收要求。 |

## 4. 关闭条件与容器决定

下一固定 clean detached 候选应逐项修正 R1–R3，并对当前执行说明做上述有限清理。由本审核者核新 SHA、文档差异及原 finding 关闭依据；不要求为这轮文档修订运行产品测试或新增性能、容器、真实数据证据。实现阶段仍须按 A–E 各 owner 承担既定 focused 与最终门禁，不能用本报告代替。

本轮只文档，不触发镜像重建。当前 HEAD 未声明任何新产品 gate，通过的历史 image/source-tree 身份仍只属于既有 S3/S4 原证据，本审核没有重算或新增 carried。没有剩余需要 Owner 选择的业务取舍；三项修订均是恢复现行冻结语义和修正实际源码事实。
