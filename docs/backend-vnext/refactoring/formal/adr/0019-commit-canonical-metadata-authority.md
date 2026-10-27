# ADR 0019: Commit Canonical Metadata Authority

状态：Accepted（repository owner 于 2026-09-27 按 P5 架构收口 Entry Brief §5 接受；此前为 Proposed：2026-09-25 决定，2026-09-26 按 S0 独立审核、两份 r2 独立复审与 DC10–DC27 修订，2026-09-27 按 r3 复审修正）

日期：2026-09-25；修订 2026-09-26、2026-09-27；接受 2026-09-27

决策 owner：Backend vNext Snapshot Materialization / Submission Application / History Application

关联阶段：P5 架构收口 S2a、S2b；取代 P3-R3 hidden summary 条款与 5E 设计 §6.6 的相应部分；澄清
[ADR 0016](0016-graceful-lifecycle-and-integrity-recovery.md) 的 incident 适用范围

详细设计：[P5 架构收口详细设计](../plans/p5-arch-closure-design.md) §4.9、§5；依据
[S0 独立审核报告](../plans/p5-arch-closure-s0-independent-docs-review.md)、r2 独立复审
（[第一份](../plans/p5-arch-closure-s0-independent-rereview.md)、[第二份](../plans/p5-arch-closure-s0-independent-rereview-2.md)）、r3 独立复审
（[第一份](../plans/p5-arch-closure-s0-independent-rereview-r3.md)、[第二份](../plans/p5-arch-closure-s0-independent-rereview-r3-2.md)）与
[S0 Owner 决议记录](../plans/p5-arch-closure-s0-owner-decisions.md)

## Context

- P3-R3 规定 Repository-ref 物化以 hidden FINAL SnapshotSummary 为权威，缺失即失败，不从 catalog 与行重建。
- 实际上全仓没有写入方（R3-D02 一直延期），HTTP Arrow adapter 改为从行重建 summary，版本字段取运行时常量，`capabilities/snapshot_materialization/repository_ref.py` 随后再读一遍全表做交叉校验。结果是：
  - 每次物化都要全表读两遍；
  - 交叉校验等于同一数据读两次；
  - 无法得知 commit 是按哪版规则生成的；
  - 5E-S2 围绕这项校验建立的 integrity incident 机制，没有可靠的证据来源。
- `NO_CANONICAL_CHANGE` 用的是 Preview bundle digest 与“基线自比流水线”的 bundle digest；该流水线在 AcceptSubmit 预检中执行。
- 每个 Submission 已经持久化了 `CanonicalizationManifest` 的 ref 与 digest，finalize 时由 `canonicalization-manifest` owner 长期保护。
- S0 独立审核补充确认：
  - r1 按节点 commit 元数据中的规则集校验 History，与 Ruleset Activation §5 冲突，并需要规则集全序与历史规则集持久化；
  - compose harness 与供给 mapping 允许把非空 commit 作为初始 BaselineNode；
  - 现有状态摘要不含 schema，拟议的无变化判定会误拒合法的 schema 更新；
  - 删除 hidden summary 后，Repository 读取不一致的处置需要写明。
- r2 复审补充：Ruleset Activation §5 末句与 DC11 的恢复失败冲突；Preview 捕获规则集的时点没有定义；manifest artifact digest 不符的处置没有定义；E 中历史 manifest 的解码被当前版本常量锁定。

## Decision

1. **commit 规范元数据的权威是 Backend 持有的 `CanonicalizationManifest`**，经 Submission 取得。
   - `CommitCanonicalMetadataPort` 以 `(repository_id, commit_id)` 为键，只经该 Repository 的 Submission 与 BaselineNode 记录解析，并限定在 operation 冻结的 scope 内；返回取自 manifest 的存储身份（`storage_projection_version`、每表 `raw_content_digest`、source/canonical schema digest、行数与规则侧 StorageRuleView）、规则集 provenance，以及现有 `SubmitAttempt.snapshot_digest`；无法解析时稳定失败（`COMMIT_CANONICAL_METADATA_MISSING`）。这些每表身份是 Preview、History 与 Submit 的结构性过滤输入，表摘要不能脱离 schema、存储视图、行数与投影版本单独使用；
   - 读取 manifest artifact 时 digest 与 Submission 记录不符：稳定失败（`COMMIT_CANONICAL_METADATA_DIGEST_MISMATCH`），附诊断、结构化日志与指标，不创建持久 incident（DC25）；
   - durable manifest 的 contract、storage projection 与 ruleset 版本必须匹配当前基线；S1a 不读取旧 manifest。现有 control DB 与测试 Repository 数据按本仓库前提删除并重建，不做兼容解码或数据迁移；
   - Repository 中不写隐藏表，Repository wire 不变。
2. **初始 BaselineNode 恒为空提交**（DC17）：零表规范状态，`canonical_binding` 取运行期规则集；物化时断言 catalog 中没有用户表，不满足即稳定失败（`INITIAL_BASELINE_NOT_EMPTY`）。不支持预置数据的初始库。
3. **Repository-ref 物化使用 commit metadata，并按需读取行。**
   - provider 协议删除 hidden summary；`canonical_binding` 由 Application 按 commit 元数据提供；descriptor 由 catalog 构造；
   - 调用方可指定需要行数据的表集合。物化仍校验 catalog 的完整表集合，并为未选中的表按 catalog 与 manifest 身份构造 descriptor，但不打开其行 reader；空集合表示本次不读任何表行。所有 descriptor 使用同一 Snapshot digest 算法；即使 binding 来自已提交 Submission，也按表名、schema 摘要、比较键、行数与 manifest 的 `raw_content_digest` 计算，不沿用 SubmitAttempt 的 `snapshot_digest`。选中表仍按 manifest 校验行数与 `raw_content_digest`；
   - 选中的表验证 catalog 行数、实际行数与 manifest 的 `raw_content_digest`；行数不一致时稳定失败（`REPOSITORY_ROW_COUNT_MISMATCH`），摘要不一致时稳定失败（`REPOSITORY_SNAPSHOT_DIGEST_MISMATCH`）；
   - adapter 只负责传输，不计算摘要；标量解码由 snapshot_materialization 的编码 owner 负责，与投影侧编码一致。
4. **不做读回校验。** 规范编码的一致性由共享编码、真实 Dolt 同一性测试、契约与 golden 测试以及 Repository STRUCTURAL 校验保证。
5. **规范状态摘要与无变化判定。**
   - 规范状态摘要由每表的 business schema digest（列名、规范类型、可空性、有序主键，与列序无关）、行数与 `raw_content_digest` 组成（DC13）；它取代 E 中由 Preview bundle digest 派生的 canonical business digest（r1 曾提议用 `raw_state_digest`）；
   - Preview 计算上传 MODIFIED 侧与基线侧的规范状态摘要，二者都持久化到 PreviewResult；
   - AcceptSubmit 先做陈旧判定：基线漂移、缺少规范状态摘要，或投影所用规则集 digest 与运行期不同，都返回 `PREVIEW_DERIVED_STALE`（DC11）；通过后两侧摘要相等即 `NO_CANONICAL_CHANGE`；AcceptSubmit 不再物化基线。
6. **规则集语义**（DC10、DC11）：
   - Preview 与 History 的比较语义使用运行期规则集；commit 规范元数据提供存储身份与 provenance；比较始终按列名与有效键对齐，schema 差异来源按两侧存储规则事实标记（Canonical Storage §7）；
   - Preview 与 History 都在受理时冻结运行期规则集 digest（Preview 写入 job payload，DC24）；每步执行前比较，不同即稳定失败（`PREVIEW_RULESET_VERSION_MISMATCH`、`HISTORY_RULESET_VERSION_MISMATCH`），由用户重跑；History 受理指纹包含该 digest，激活后以同一幂等键重放返回 `409 IDEMPOTENCY_CONFLICT`；
   - Submit 在 T1 冻结规范产物之后（含 PREPARED）只使用冻结产物，不依赖运行期规则集（DC23）。
7. **删除以 hidden summary 为生产者的 History compare integrity incident**（DC9）：记录、受理阻断、ack 路由、Operation 与 History DTO 字段、只为 incident 存在的诊断字段、control DB 表，以及对应测试与测试支撑钩子。
   - Repository 读取不一致按依赖异常处理：普通 FAILED，附诊断、日志与指标，不创建持久 incident（DC19）；
   - ADR 0016 与 Operation Lifecycle §4 的 incident 范围澄清为：Repository 返回值与 Backend 持有的期望值相矛盾，以及 CAS/结果歧义；Backend artifact store 的读回校验失败按稳定失败处理（DC25；候选文本见详细设计附录 B.3）；
   - 不删除 History projection/queries 使用的 `HistoryIntegrityFailure`，它表示历史事实与分页游标的一致性，与本机制无关；
   - ADR 0016 的 Operation integrity（`scan_active_integrity`、worker startup 扫描、control DB 完整性检查）不受影响。

## Alternatives

- **按原设计在 Dolt 中写隐藏 summary 表**：放弃。Repository 会混入业务专属表，需要从业务 catalog 过滤，而且与已持久化的 manifest 重复。
- **不设任何摘要权威**：放弃。无变化判定仍需全量读基线，也无法回答 commit 的规则版本。
- **Submit 完成时做一次读回校验**：暂不采用。它是唯一有依据的读回场景（ADR 0017 类漂移），代价是每次提交多一次全量读；如再次出现写入形态漂移，按下方重开条件处理。
- **按节点 commit 元数据中的规则集比较 History（r1）**：放弃。需要规则集全序与历史规则集持久化，并与 Ruleset Activation §5 冲突。
- **Repository 读取不一致创建持久 incident**：放弃（DC19）。它不与 Backend 持有的期望值矛盾，重试与诊断足以处置。
- **manifest artifact digest 不符时创建持久 incident**：放弃（DC25）。损坏的是 Backend 自有 artifact，control DB 中的权威 digest 未变；稳定失败并附诊断、日志与指标即可处置。

## Consequences

- Preview 与 History 的未变化普通表由 commit manifest 元数据短路，不读取基线行或派发行比较；变化表仍由 Repository-ref materializer 校验并读取。未变化 ordered 表只读取 pair 的 current 侧规范行以填充既有逻辑与 occupancy facts。AcceptSubmit 不执行比较流水线。
- 5E-S2 的 integrity 机制与 v6 表被移除（在 5E slice exit 之后执行）。
- 未来的 `SYSTEM_MIGRATION` commit 必须同时登记 manifest。
- control DB 新增前向 migration；compose harness 的初始基线改为空提交。（注：control DB schema 规则由 G3 取代，见设计 DC6。）
- Business Lifecycle 升至 3.1.0；Ruleset Activation §1 与 §5（DC23）、Operation Lifecycle §4 与 ADR 0016 的候选文本已于 2026-09-27 随 S0 接受并入（详细设计附录 A、B）。

## Required Verification

- Repository-ref 子集读取：catalog 仍完整校验，未选择表不打开 reader，空选择读取零表，选中表验证行数与 `raw_content_digest`，`snapshot_id` 确定性。
- `CommitCanonicalMetadataPort` 只在所属 Repository 与冻结 scope 内解析；manifest digest 不符时稳定失败；旧 contract/storage/ruleset 版本的 durable manifest 稳定拒绝（唯一 owner：`test_storage_projection_publication.py`）。
- 初始基线非空时稳定失败。
- `NO_CANONICAL_CHANGE` 判定；陈旧 Preview（基线漂移、缺摘要、规则集不同）被拒绝。
- ADDITIVE 激活后旧基线仍可 Preview；Preview/History 在激活后恢复时稳定失败，Preview 包括受理后、materialize 前发生激活的情形。
- 删除 integrity 后 OpenAPI 与路由测试同步更新；ADR 0016 的 Operation integrity 测试不变且通过。

## Reopen conditions

- 出现 Repository 写入形态与 Backend 规范形态漂移的可复现故障，此时评估在 Submit 完成时读回。
- 出现不经 Submit 产生的业务 commit，且无法登记 manifest。
- 需要从 Repository 独立恢复 commit 元数据（例如 control DB 丢失后的重建）。
- 需要预置数据的初始库（重开 DC17）。
- Repository 读取不一致出现需要持久追踪的运维需求（重开 DC19）。
