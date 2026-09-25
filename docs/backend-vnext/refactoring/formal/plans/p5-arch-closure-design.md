# P5 架构收口详细设计

状态：**DRAFT — 待独立文档审核；实现未授权**

日期：2026-09-25

Owner：Backend vNext Architecture（收口牵头）；各项语义归属见 §11

入口：[Entry Brief](p5-arch-closure-s0-entry-brief.md) → 本文 → [执行计划](p5-arch-closure-execution-plan.md)

上游：[P5 §2A / §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-guardrails)、
[Architecture](../architecture/architecture-and-refactoring-plan.md)、
[Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)、
[Business Lifecycle 3.0.0](../contracts/business-lifecycle-and-state.md)、
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[P3-R4 设计](p3-r4-storage-projection-design.md)、[P3-R5 设计](p3-r5-comparison-design.md)、
[5E 设计](p5-5e-history-compare-design.md)；本轮提案 ADR
[0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
[0019](../adr/0019-commit-canonical-metadata-authority.md)、
[0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
[0021](../adr/0021-flow-neutral-comparison-entry.md)。

标记：**E** = 已实现事实（源码 @ `2172369803`，除注明外未经本轮运行验证）；**D** = 已接受设计；
**P** = 本设计提案。

## 1. 目标、决定与非目标

目标：在 P5 整体 exit 前完成 §2A 收口：

1. 关闭 §2A.4 与 §2A.4.1 已确认问题，使 `tests/architecture_baseline.py` 清空，或剩余条目逐条
   具备 owner、理由和后续阶段；
2. 纠正本轮核对确认的语义缺陷（§2.1 R1–R6），使 Preview、Submit、History 在同一规范业务状态上
   得出一致结论；
3. 交付 §2A.3 要求的代表性链路测量与 Phase 6 候选。

Repository owner 决定（2026-09-25，本文据此设计，不再重开）：

| ID | 决定 | ADR |
| --- | --- | --- |
| DC1 | 所有比较在规范域进行；表规则的比较语义由 table_rules 的 `ComparisonRuleView` 提供；删除 `comparison_projection` 占位。Preview 只展示规范业务状态的差异，被规则丢弃的列和 SKIP 表不参与、不显示 | 0018 |
| DC2 | 以 Backend 持有的 `CanonicalizationManifest` 作为 commit 规范元数据权威；不在 Dolt 写隐藏表；不做读回校验；删除 hidden summary 重建并收缩 5E integrity incident 机制 | 0019 |
| DC3 | 项目身份沿用旧设计三段式语义；“无法判定”的继续确认在 Submit 受理时收集，不设 Preview 暂停门；两个确认动作分开校验；“不同项目”不可改判 | 0020 |
| DC4 | composite_signal / `logics.xml` 接入 P5 业务物化；`composite_signal_point` 保留 `formula_ast_json`、`point_name` 但只以 `formula_digest` 比较 | 0018（列处置） |
| DC5 | 撤销 §2A.2 对 R5 流程词汇的保留约定；comparison 只接收两侧规范快照、规则集、执行模式和选项 | 0021 |
| DC6 | 新项目无历史数据：可以直接改变 contract、checkpoint/payload、canonical bytes 与 digest；不建设兼容层或双读路径 | — |

非目标：Phase 6 Rust 实现；新的 Repository effect、API 或 wire 变化；HA、外部 DB；legacy 数据迁移；
性能通过阈值；在线 ruleset 迁移；5E slice 范围内的任何改动（5E slice exit 之前不改动其候选树）。

兼容性（DC6）：control DB 通过新增前向 migration 修改 schema，不做数据回填；开发/测试环境的
control DB 与 Repository 数据可以重建。所有 golden 与 digest 随语义变化一次性更新。

## 2. 当前事实与问题映射

### 2.1 本轮新确认的语义缺陷

| ID | 事实（E） | 影响 | 归属工作流 |
| --- | --- | --- | --- |
| R1 | Preview 上传侧是原始 SQL 快照（DDL 主键、全部列），基线侧读自 Repository，是规范形态（显式键为主键、忽略列已丢弃、无 SKIP 表）。用 capability 公开入口实验：`com_cfg` 两侧内容相同，FULL `baseline_to_initial` 与 MODIFIED_ONLY 主 pair 均为 `DEGRADED`（`CURRENT_ONLY_COLUMNS`、`EFFECTIVE_KEY_CHANGED`） | 基线非空后，52 条规则中 19 条显式键、13 条带忽略列、8 条 SKIP 所覆盖的表在 Preview 中系统性降级或误报 | W1 |
| R2 | 表规则的比较语义未生效：`BROWSE_ONLY`、`SNAPSHOT_ONLY`、`UPDATE_ONLY` 在任何链路都没有使用；History 在 `B/application/history/compare_jobs.py::_project_table_policy` 只投影 ordered 与忽略列；Preview/Submit 不传 `table_policies` | 与 R4 设计 §4.3 规定的比较含义不一致；同一对 commit 在 Preview 与 History 结果可不同 | W1 |
| R3 | `NO_CANONICAL_CHANGE` 比较 Preview bundle digest 与 `compute_baseline_canonical_bundle_digest`（基线自比流水线的 bundle digest）；AcceptSubmit T1 经 `BaselineCanonicalDigestPort` 物化基线 | 受 R1 影响基本不会命中；T1 承担整条比较流水线的成本 | W2 |
| R4 | `B/infrastructure/repository_read/http_arrow.py::_hidden_summary_from_streaming_tables` 从行重建 hidden summary，版本字段取运行时常量；`repository_ref.py` 随后再读一遍全表做交叉校验；全仓无 hidden summary 写入方 | 违反 P3-R3“不从 catalog/rows 重建”；每次物化全表读两遍并逐行 `to_pylist()`；无法得知 commit 的规则版本 | W2 |
| R5 | 上传包中的 `/comps/logic/logics.xml` 被暂存（`optional_xml_document_ref`）但从不解析；Preview/Submit 走纯 SQL 物化，`composite_logic_source_digest` 恒为空 | `logics.xml` 修改静默丢失，不进入规范业务状态 | W5 |
| R6 | Preview 以 `_PreviewIdentityAssessment` 固定 `SAME_PROJECT`；独立 identity capability 不存在；comparison 的 `DATASET_REPLACEMENT` 只返回无 facts 的 `CHANGED`；risk 无任何处理 | 跨项目误传无法识别；identity gate 等分支无生产者 | W4 |

### 2.2 既有清单映射

§2A.4 各行与 §2A.4.1 各项、以及 `tests/architecture_baseline.py` 的分组（`A<n>`/`N-*`），在 §9 映射到
具体修复与阶段。不能由 import 规则判定的问题（R1–R6、编排复制、用例放置、UoW 枢纽）由本文及执行
计划的测试 owner 跟踪。

## 3. 目标结构

```text
table_access ─┐
composite_signal ─> snapshot_materialization（原始快照、Repository 规范快照、摘要定义、artifact）
table_rules ───────> storage_projection（规范投影：规范快照 + CanonicalizationManifest + import 包）
table_rules（ComparisonRuleView） ─┐
snapshot_materialization ──────────┴─> comparison（规范对规范；DETAILED | DATASET_REPLACEMENT）
snapshot_materialization ─> project_identity（新）
comparison ─> risk_evaluation ─> surface_assembly ─> bundle_assembly
```

- 删除 `comparison_projection`、`business_projection` 占位与架构测试中对应 owner、DAG 边。
- 新增 `project_identity`，上游仅 `snapshot_materialization`。
- `comparison` 上游改为 `table_rules`、`snapshot_materialization`。
- capability 公共面统一为包 facade（`__init__`）与 `contracts`；`contracts` 必须是 owner 内叶子，
  不得 lazy import 本 owner 执行实现（关闭 A7）。架构测试的 capability DAG 规则同步放行上游 facade。
- Application 负责流程拓扑（FULL/MODIFIED_ONLY、pair 列表、History 视图）、执行模式选择、确认与
  事务；capability 不再出现流程词汇（DC5）。

## 4. W1 规范域比较与比较规则视图（ADR 0018）

### 4.1 规范快照

规范快照（P）是在规则集 R 下、形态与 storage projection 输出一致的 `SnapshotTableSet`：只含保留列，
以规范键为主键和比较键，不含 SKIP/OMIT 表，ordered 表已分配伪 gid。它携带
`canonical_binding = (storage_projection_version, ruleset_id, ruleset_version, ruleset_digest)`。

有两个生产者：

1. `storage_projection` 从原始快照投影（Preview 上传侧）；
2. `snapshot_materialization.repository_ref` 从 Repository commit 读取（Preview 基线侧、History 全部节点）。

**规范快照同一性不变量**：同一规范内容无论由哪个生产者得到，每表 `compare_schema_digest`、
`raw_content_digest` 与快照 `raw_state_digest` 完全相等。该不变量是 R1、R3 修复与提前退出的前提；
若 SQL 解析路径与 Arrow 读取路径对同一值的编码不同，应在编码 owner（snapshot_materialization
`scalar_encoding` / ADR 0017 映射）修正，不得在比较侧特判。

### 4.2 storage_projection 规范快照输出

- 新增公开入口（P）`project_canonical_table_set(request) -> CanonicalProjectionResult`：输入原始
  `SnapshotTableSet` 与 `TableRulesetSnapshot`，输出规范表（符合 snapshot_materialization 契约的
  descriptor + reader）、`CanonicalizationManifest` 与诊断。复用 E 中的
  `materialize_canonical_source_rows` 与 `derive_storage_rule_view`，不复制规则。
- 规范形态不支持的类型、键或表（E：`UNSUPPORTED_TABLE` 等）在 Preview 即失败，与 Submit 一致。
- Application 用 snapshot_materialization 的既有公开发布入口（E：`publish_ready_tables` /
  `publish_snapshot_table_artifact`）把规范表持久化为 `SnapshotTableArtifact`；manifest 由
  storage_projection 既有发布路径（E：`publish.py`）持久化。
- 新增公开入口（P）`render_repository_import_package(canonical_table_set, manifest) -> bytes`，
  供 Submit 从规范快照直接生成 import 包（§4.7），不再对原始快照二次投影。

### 4.3 table_rules 比较规则视图与列处置

`TableRuleRecord` 增加 `compare_excluded_columns`（P）：保留在存储中，但不参与值比较。
`ignored_columns` 维持 R4 语义（`DROP_FROM_STORAGE`）。两者必须不相交，且都不能是规范键或 ordered
身份列；违反时规则集校验失败。

`ComparisonRuleView`（P，与 E 中的 `StorageRuleView` 对称）逐表给出：

```text
canonical_table
comparison_role: STANDARD | ORDERED | BROWSE_ONLY | SNAPSHOT_ONLY
artifact_scope: ALL_CHANGES | UPDATE_ONLY        # ordered 表固定为 ordered 语义
compare_excluded_columns: canonical tuple
ordered: order_key, stable_key_candidates, row_identity_key, blank_row_policy   # 仅 ORDERED
comparison_rule_digest
```

`ComparisonRuleSet`（P）= 规则集 digest + 按规范表名解析视图的函数；未匹配表按 resolver 既有回退规则
（E：`STANDARD_RAW_PK_FALLBACK`）。ordered 参数从规则投影（`position_column`、`stable_key_candidates`），
IEC104 的 `gid/no` 默认值只在 table_rules 注册表中出现，不再出现在 comparison 契约默认值或 Application 中。

角色语义沿用 [R4 设计 §4.3](p3-r4-storage-projection-design.md)：

| 规则角色 | 规范快照 | 比较语义 |
| --- | --- | --- |
| SKIP | 不含该表 | 不比较 |
| SNAPSHOT_ONLY | 含该表 | 不产出比较事实与记录 |
| BROWSE_ONLY | 含该表 | 只给表级存在性与两侧行数事实，不产出记录，不参与行级风险 |
| STANDARD_DIFF | 含该表 | 普通比较，`UPDATE_ONLY` 按表收窄产物 |
| ORDERED_DIFF | 含该表 | ordered 比较 |

`SNAPSHOT_ONLY` 与 `BROWSE_ONLY` 的具体事实形态在 S2 按 legacy 行为 oracle 核对后冻结；
`version_manager` 等表的浏览仍通过快照 artifact 提供。

DC4 的规则变更：`composite_signal_point` 的忽略列改为 `dev_addr`、`device_gid`、`point_payload_json`；
`formula_ast_json`、`point_name` 移入 `compare_excluded_columns`；值比较只用 `formula_digest`。
不参与比较的列在记录中照常携带前后值用于展示，但不决定 `MODIFIED`。

### 4.4 comparison 消费方式

- 公共输入见 §6。comparison 按 `ComparisonRuleView` 逐表决定角色、产物范围、排除列与 ordered 参数；
  `ComparisonTablePolicy` 降为 comparison 内部派生类型，不再是调用方输入，也不再由 Application 编解码。
- 两侧 `canonical_binding.ruleset_digest` 必须等于 `ComparisonRuleSet` 的 digest，否则返回稳定失败
  `RULESET_BINDING_MISMATCH`。V1 只有一个激活规则集；跨规则集比较按
  [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md) 重开。
- 提前退出沿用 E 的 `raw_content_digest` 相等判定，依赖 §4.1 不变量。

### 4.5 Preview

`materialize_inputs`：

1. 上传侧：staging → 业务物化（SQL + 可选 `logics.xml`，§8）→ 原始 artifact → 规范投影 → 规范 artifact
   与 manifest artifact；
2. 基线侧：从 BaselineHead 的 exact commit 读取规范快照（§5.2），`canonical_binding` 来自 commit 规范
   元数据（§5.1）；
3. 项目身份评估（§7.2）；
4. checkpoint 记录原始与规范 artifact ref、manifest ref、规则集 digest、身份评估结果。

`assemble_preview` 只比较规范快照；`publish_preview` 在 PreviewResult 中持久化规范状态摘要（§5.3）、
上传 MODIFIED 侧 manifest ref 与身份结论（§7.5）。三步 JobDefinition 不变。

Preview 不再展示被规则丢弃的列与 SKIP 表（DC1）。原始 SourcePackage 仍完整保留。

### 4.6 History

- `materialize_inputs` 冻结规则集 digest（替代 5E 的逐表 `table_policies` checkpoint）；恢复时由运行期
  规则集派生视图并校验 digest 相等，不等则稳定失败。
- 删除 `_project_table_policy`、`_policy_to_checkpoint_dict`、`_table_policies_from_checkpoint`。
- 每个节点的 `canonical_binding` 来自 commit 规范元数据（§5.1）。

### 4.7 Submit

- AcceptSubmit T1 把 Preview 的规范 artifact 与 manifest 的保护责任连同原始 artifact 一起转移给
  Attempt（沿用 E 的 pin 转移模式）。
- `prepare_import` 用 §4.2 的 `render_repository_import_package` 从规范快照生成 import 包，
  不再对原始快照重新投影。Preview 比较的内容与写入 Repository 的内容因此同源。
- 包根 `repository_import_artifact.py` 中的 `SubmitImportPublicationAdapter` 消失：Application 调用
  capability 入口并经 `ArtifactStorePort` 写入 bytes（关闭 A6 中该项）。
- Repository wire、verification policy 与 T1/T2/T3 恢复语义不变。

## 5. W2 commit 规范元数据与单遍读取（ADR 0019）

### 5.1 commit 规范元数据权威

- Submission commit：`Submission.canonicalization_manifest_ref/digest`（E 已持久化；manifest 含
  `storage_projection_version`、规则集 id/version/digest 与逐表规范摘要）。
- 供给时的初始空 BaselineNode：定义为“空规范状态”（零表），与规则集无关；读取时 Application 以运行期
  规则集填充 `canonical_binding`。
- Application 新增端口 `CommitCanonicalMetadataPort`（P）：在已授权 scope 内按 commit 返回上述元数据，
  由 control DB adapter 实现。
- 未来 `SYSTEM_MIGRATION` commit 必须同时登记 manifest，否则不得进入 Preview 或 History 比较（重开条件）。

### 5.2 Repository 规范快照单遍读取

- `RepositoryRefMaterializationRequest` 增加 `canonical_binding`（由 Application 提供）。
- provider 协议删除 `read_hidden_summary`；删除 `HiddenFinalSummary` 与 `HIDDEN_SUMMARY_*` 诊断码。
- 物化对每张表只读一次：同一遍内计算描述符摘要并写入 artifact。catalog 行数与实际读取行数不一致时，
  返回普通 `FAILED`（`REPOSITORY_ROW_COUNT_MISMATCH`）。
- `snapshot_id` 由 `(repository_id, commit_id)` 确定性派生。
- HTTP Arrow adapter 只负责传输，按 record batch 交付，不计算任何摘要，不导入 capability 私有模块
  （关闭 A2 中 `http_arrow` 的三条）。Python 行对象只在 snapshot_materialization 中转换一次；
  Arrow 原生摘要计算作为 Phase 6 候选（§13）。

### 5.3 无规范变化判定

- 规范状态摘要 = 规范快照的 `raw_state_digest`，定义由 snapshot_materialization 契约拥有。
- Preview 同时计算上传 MODIFIED 侧与基线侧的规范状态摘要，二者都持久化进 PreviewResult。
- AcceptSubmit 比较二者，相等即 `NO_CANONICAL_CHANGE`，不再物化基线。Preview 过期由现有的 Baseline
  漂移检查拒绝，因此 Preview 记录的基线摘要在受理时有效。
- `Submission.canonical_business_digest` 改为 MODIFIED 侧规范状态摘要。
- 删除 `BaselineCanonicalDigestPort`、`compute_baseline_canonical_bundle_digest` 及 `http/runtime.py` 中
  对应的适配器。

### 5.4 History 规则集校验

History 受理与执行时，所有节点的 commit 规范元数据规则集 digest 必须等于运行期规则集 digest；否则沿用
E 的稳定失败码 `HISTORY_RULESET_VERSION_MISMATCH`，但判据改为真实元数据，不再依赖运行时常量。

### 5.5 收缩 5E integrity incident

hidden summary 删除后，5E-S2 以 `HIDDEN_SUMMARY_*` 与“catalog 对 summary”结构不一致为生产者的
class (c) integrity incident 不再有生产者（P，取代 [5E 设计 §6.6](p5-5e-history-compare-design.md)
的相应部分）：

- 删除 History compare integrity 记录与受理阻断（`has_pending_integrity_for_commit`）；
- 删除 `POST /v1/history-compares/{operation_id}/integrity-ack` 路由、`http/orchestration/history_integrity.py`；
- 删除 `compare_jobs.py` 中 integrity 判定与发布函数；
- 以新 migration 删除对应 control DB 表；
- 删除对应测试 owner（`test_history_compare_integrity.py` 等）。

读取不一致作为普通 FAILED 加诊断处理。ADR 0016 的 Operation integrity 不受影响。
该删除只在 5E slice exit 之后进行。

## 6. W3 comparison 公共面去流程化（ADR 0021）

公共输入（P）：

```text
ComparisonRequest(
  pair_id,                      # 调用方给出的不透明 id
  before: CanonicalSnapshotInput,
  current: CanonicalSnapshotInput,
  rule_set: ComparisonRuleSet,
  mode: DETAILED | DATASET_REPLACEMENT,
  options, contract_versions)
plan_comparison(request) -> ComparisonPlan | FailedResult
compare_plan(plan) -> DetailedFactsResult | DatasetReplacementResult | FailedResult | CancelledResult
publish_records_closure / open / restore / rewrite       # 记录闭包 API 保持
```

- 删除 `PairViewKind`、`PairRole`、`InputCompleteness`、`IdentityApplicability`、`IdentityStatus`
  （移入 project_identity）、`ContinuationAction`、`BaselineReconstruction*`、
  `TrustedFlowApplicabilityBinding`、`UnverifiableContinuationBinding`、`IdentityGateBlockedResult`、
  `InitialSnapshotResult`、`ProjectIdentityAssessment` 协议（移入 project_identity）。
- 删除从生产入口不可达的 `PythonReferenceBatchProvider`/`RustArrowBatchProvider` 公共导出；Phase 6
  需要时由 owner 按实际热点重新设计（§2A.3“不预建 provider framework”）。
- 初始空基线作为零表 `before` 传入，不再需要单侧视图。
- FULL 与 MODIFIED_ONLY 的 pair 拓扑、pair 标签与 History 视图全部由 Application 决定。
- surface 的身份标注改由 Application 在 `SurfaceAssemblyInput` 中提供，不再取自 comparison facts。
- 本条撤销 §2A.2 “R5 已接受的 pair/view/applicability 词汇保留”的约定（ADR 0021 接受后同步修订 §2A.2）。

## 7. W4 项目身份与数据替换（ADR 0020）

### 7.1 project_identity capability

- 规则 `version-manager-overlap/v1` 沿用旧设计 §version-manager-overlap/v1：读取两侧规范快照的
  `version_manager` 表，排除 `no` 列，其余列按规范名排序后规范化比较完整条目；
  有交集为 `SAME_PROJECT`，双方都有可比条目但无交集为 `DIFFERENT_PROJECT`，缺表、空表、列集合不一致
  或读取失败为 `UNVERIFIABLE`。
- 输出 `ProjectIdentityAssessment`（schema/rule version、status、两侧快照摘要、计数、条目集合摘要、
  assessment digest），不包含原始行。
- 流程中立：不感知 Preview、pair 或确认。

### 7.2 适用范围（Application）

| 上传模式 | pair | 适用性 |
| --- | --- | --- |
| FULL | baseline → initial | before 为供给时的初始空基线时 `NOT_APPLICABLE`，否则评估 |
| FULL | initial → modified | 评估 |
| MODIFIED_ONLY | baseline → modified | before 为初始空基线时 `NOT_APPLICABLE`，否则评估 |

对初始空基线评估必然得到 `UNVERIFIABLE`，这会使每个项目的首次提交都成为异常节点，因此显式规定为
`NOT_APPLICABLE`（P）。History compare 不做身份评估（沿用 D）。

### 7.3 模式选择与 Preview 结果

- `DIFFERENT_PROJECT` → `DATASET_REPLACEMENT`；其余 → `DETAILED`。
- `UNVERIFIABLE` 额外附诊断 `PROJECT_IDENTITY_UNVERIFIABLE`。
- Preview 始终完成并 READY，不设暂停门（DC3）。
- 已判定为 `DIFFERENT_PROJECT` 的 pair 不因后续局部失败回退为详细比较（沿用旧设计）。

### 7.4 能力补齐

- comparison 的 `DATASET_REPLACEMENT` 按旧设计产出表级事实：双方都存在记为 `REPLACED`
  （deleted = before 行数，inserted = current 行数），仅一侧存在记为 `DELETED_TABLE`/`ADDED_TABLE`；
  不调用详细比较、records writer 或行级风险。
- risk 对替换 pair 产出比较级 `HIGH`，原因码 `PROJECT_IDENTITY_MISMATCH`、`DATASET_REPLACEMENT`；
  不产出表或行级标注。
- surface 的替换展示与 replacement summary 已实现（E），补测试；bundle 对替换 pair 的同名表导出两侧快照。

### 7.5 持久事实（A 类）

- `PreviewResult`：`identity_assessment_set_digest`，以及逐 pair 的 `(pair_id, status, mode, assessment_ref)`。
- `SubmitAttempt` / `Submission`：身份确认记录 `(action, assessment_set_digest, reason, actor_id, confirmed_at)`，
  actor 与时间只来自 session 与服务端时钟；Submission 在 finalize 时从 Attempt 复制，之后不可变。
- Archive：身份异常处置事件（§7.7）。

### 7.6 Submit 受理

`AcceptSubmitCommand` 增加 `identity_confirmations`（P），每项为
`{action, assessment_set_digest, reason}`：

- Preview 含 `DIFFERENT_PROJECT` pair 时必须包含 `ACCEPT_DATASET_REPLACEMENT`；
  含 `UNVERIFIABLE` pair 时必须包含 `ACCEPT_UNVERIFIABLE_DETAILED_RESULT`；
  两者分别校验，不能互相替代；不需要时不得出现。
- `assessment_set_digest` 必须等于 current PreviewResult；reason 去除首尾空白后长度为 1–1000。
- 缺少或多余返回 `409 PROJECT_IDENTITY_CONFIRMATION_REQUIRED`；摘要不符返回
  `409 PROJECT_IDENTITY_CONFIRMATION_MISMATCH`。
- 确认内容进入请求指纹；same key/same fingerprint 重放返回原结果。
- 校验在 T1 事务内与现有 preview/baseline/占用校验一起执行，不产生额外外部调用。

### 7.7 Review、Archive 与 History

- Review 读取面展示身份异常与确认记录（只读）。
- Archive 新增 `ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION`：
  - `PreviewArchivePlan` 对所选 Submission 若带身份确认记录则派生该异常；
  - subject digest 绑定 `submission_id`、candidate digest、preview bundle digest 与 assessment set digest；
  - 处置动作 `ACKNOWLEDGE_IDENTITY_EXCEPTION`，reason 必填；
  - StartArchive 要求最新处置为肯定，沿用 `/v1/archive-anomaly-resolutions` 与 `anomaly_resolution_refs`。
- 既有 `ArchiveAnomalyResolutionEvent` 的 `sibling_submission_id`/`sibling_candidate_digest` 泛化为
  `target_submission_id`/`target_candidate_digest`（DC6，无兼容）。
- History 节点派生 `identity_exception` 标记（只读投影，不新增持久事实）。

## 8. W5 composite_signal 接入

- Preview 上传侧改用 `materialize_business_snapshot`（E，P3-R3 已实现并测试）：SQL 加可选 `logics.xml`；
  缺失 `logics.xml` 时按 D 使用稳定 EMPTY 来源；XML 摘要或 EMPTY 标记进入快照身份。
- `logics.xml` 存在但解析失败或违反 composite 业务不变量时，Preview FAILED 并附明确诊断（P，沿用 P3-R3）。
  这修订 P5 §6.1 中“XML 增强可降级”对 `logics.xml` 的适用：该文件的内容属于规范业务状态，降级会造成
  静默丢失。
- `composite_signal_point` 经规范投影进入存储、比较和风险，规则按 §4.3 变更。
- **停止条件**：派生表主键含 `TEXT` 列 `source_table`。若 Dolt 拒绝 `TEXT` 主键，由 storage_projection owner
  以 ADR 规定键列字符串类型的规范化（例如有界 `VARCHAR`），不得在 Application 或 composite 侧绕开。

## 9. W6 边界与结构修复

| 基线分组 / 问题 | 目标 | 阶段 |
| --- | --- | --- |
| A1 wire DTO 进入业务 port | `application/submission/ports.py` 只返回业务结果；Repository wire 编解码移入 `infrastructure/repository_write`；保持请求证据字节、实际发送与恢复语义一致 | S1 |
| A2 私有模块导入 | HTTP admission 改用 `source_package_staging` 公开的受限成员枚举入口；`http_arrow` 三条随 §5.2 关闭 | S1 / S2 |
| A3 事务→job 反向调用 | checkpoint 保护释放下沉到 submission 用例内的下层模块 | S1 |
| A5 nominal ref 倒挂 | Submission 领域持有自身的包引用值对象；`artifacts` 不导入 domain；转换函数移至 `application/submission` | S1 |
| A6 包根模块 | 删除重复的 `canonicalization_manifest.py`/`canonicalization_cells.py`；import 包媒体类型只由 storage_projection 契约定义，adapter 测试断言与 wire 常量一致；`repository_import_artifact.py` 随 §4.7 消失；`compute.py`、`canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash` 并登记 Phase 6 延期；`synthetic_w2.py` 移至 `tests/support` | S1 / S2 |
| A7 contracts 跳板 | 公共面改为 facade + contracts，contracts 为叶子；DAG 测试放行上游 facade | S1 |
| A8 绕过 facade | Application 只从 facade 或 contracts 导入 | S1 |
| A9 / N-dead 不可达代码 | 删除 `cache/comparison_core`、`comparison/provider`、`snapshot_materialization/cache`、两个占位 capability；`external_target_sync` 登记延期（真实外部目标出现时重开）；composite 与 XML 模块在 S3 变为可达；synthetic job 与 external effect 桩移出生产包和 worker 装配 | S1 / S3 / S5 |
| N-http-composition | 抽出 `bootstrap/composition.py`，由 HTTP 与 worker 共用；job registry 由 Application 构建，worker 不再导入 `http.runtime` | S1 |
| N-http-bypass | `http/history_reader.py` 移至 `infrastructure/control_db`；`http/dependencies.py` 的只读 store 改为经 bootstrap 注入的 adapter；设置常量由组合根注入；HTTP 不导入 capability 与 wire 类型 | S1 |
| N-infra-usecase | adapter 只依赖 Application 的 ports/contracts/errors；`compare_bindings` 编解码与 abort 码移入对应 contracts | S1 |
| N-operations-private | `operations.contracts` 提供公开校验函数 | S1 |
| Preview/History 受理用例在 HTTP | 移入 `application/workspace/preview.py` 与 `application/history/compare.py`；HTTP 只保留 DTO 映射与准入 | S1 |
| job 模块复制 | 抽出 Application 内共享的 step 构建模块与 pair 流水线（bind/plan/compare/publish/risk/surface）；Snapshot/Summary 编解码归 snapshot_materialization contracts | S1（W1 之前完成，避免 W1 双改） |
| UoW 枢纽 | 按 owner 拆分：共享的最小控制事务协议由 Application 平台模块持有，workspace、submission、archive、history 各自声明所需 port；组合在 bootstrap/infrastructure 完成 | S1 |
| 运行时环（N-cycles） | 各自在 owner 内解除 | S1 |

S1 只做结构修复、不改行为：所有 golden、digest 与 compose 旅程结果保持不变，作为后续语义变更的回归基准。

## 10. 持久化、HTTP 与部署影响

- control DB 新增前向 migration，不做数据回填（DC6）：
  - PreviewResult 增加规范状态摘要、manifest ref 与身份结论；
  - SubmitAttempt/Submission 增加身份确认记录；
  - archive 事件字段泛化并增加 subject kind；
  - 删除 History compare integrity 表。
- HTTP：
  - Preview 结果读取增加身份结论与规范变化标记；
  - Submit 受理请求增加 `identity_confirmations` 及两个 409 错误码；
  - Archive 异常处置接受新 subject kind；
  - 删除 integrity-ack 路由；
  - OpenAPI 测试随之更新。
- artifact 保留：规范 artifact 与 manifest 与原始 `SnapshotTableArtifact` 同等 pin，并在 T1 转移给 Attempt
  （P5 §9 规则不变）。
- 镜像与 Compose：Dockerfile、依赖、entrypoint 与 Compose 均不变；各语义阶段的 compose 旅程需要更新并
  重跑，按执行计划 §5 在阶段末重建 current HEAD 镜像。

## 11. 语义 owner 与需修订的文档

| 语义 | Owner | 需修订（ADR 接受后） |
| --- | --- | --- |
| 规范快照、规范状态摘要、Repository 单遍物化 | Snapshot Materialization | P3-R3 设计 hidden summary 条款（由 ADR 0019 取代） |
| 规范投影、manifest、import 包渲染、媒体类型 | Storage Projection | Contract Taxonomy ownership matrix（删除 Comparison Projection 行） |
| `ComparisonRuleView`、列处置 | Table Rules | R4 设计 §4.2 追加 `compare_excluded_columns` |
| comparison 输入与替换模式 | Comparison | P3-R5 设计 identity gate 与流程词汇相关条款；P5 §2A.2 |
| 项目身份评估 | Project Identity（新） | Contract Taxonomy ownership matrix 新增行 |
| Preview/Submit/Archive 身份确认与持久事实 | 对应 Application | Business Lifecycle 3.1.0（附录 A 候选） |
| History integrity 收缩 | History Application | 5E 设计 §6.6 标注取代 |
| 目标 DAG | Backend Architecture | Architecture §7.1/§7.2；`tests/test_architecture.py` owner 集合与 DAG |

## 12. 测试归属

| 不变量 | 唯一 owner（P） |
| --- | --- |
| 规范快照同一性（SQL 投影与 Repository 读取对同一内容摘要相等） | `test_canonical_snapshot_identity.py`（unit，用 fake provider）+ S2 compose 旅程 |
| 同内容原始上传与规范基线 → 全表 UNCHANGED | `test_comparison_canonical_domain.py`（由本轮实验改写） |
| `ComparisonRuleView` 派生与列处置校验 | `test_table_rules_comparison_view.py`（共享参数表） |
| 角色语义（BROWSE_ONLY/SNAPSHOT_ONLY/UPDATE_ONLY/ordered） | `test_comparison_rule_roles.py` |
| 规则集 binding 不一致失败 | `test_comparison_planning.py` |
| Repository 单遍物化与行数不一致失败 | `test_repository_ref_materialization_protocol.py` |
| `NO_CANONICAL_CHANGE` 由规范状态摘要判定 | `test_submit_transactions.py` |
| 身份规则 v1 | `test_project_identity.py` |
| 替换事实、比较级风险 | `test_comparison_replacement.py`、`test_risk_contracts.py` |
| 身份确认受理、重放与错误 | `test_submit_transactions.py`、`test_http_auth_matrix.py`（错误码参数表） |
| Archive 身份异常处置 | `test_archive_transactions.py` |
| composite 业务物化与规则 | `test_preview_job_materialize.py`、`test_storage_projection_core.py` |
| import 边界 | `test_architecture.py` + `tests/architecture_baseline.py` |
| 端到端 | 既有 compose 旅程扩展：重复提交同内容得到 `NO_CANONICAL_CHANGE`；规则表在非空基线上的 Preview；仅改 `logics.xml`；跨项目上传→确认→审核→处置→归档 |

同构错误使用模块级参数表；纯规则与解析测试不引入 Dolt（AGENTS）。

## 13. 性能输入（§2A.3、§2A.5 第 3 项）

S5 选择 FULL 上传（非空基线）→ Submit → History compare 这条链路，用代表性数据记录端到端耗时，并拆分为
Repository I/O、Arrow→Python 转换、规范投影、摘要计算、比较、artifact 读写几部分，形成 Phase 6 候选
（预期包括 Arrow 原生行摘要与 canonical row hash Rust 路径）。遵守
[Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)：不设通过阈值，
不建设新的 benchmark 平台。

## 14. 停止条件与开放项

出现以下情况时停止对应阶段并回到 owner 处理：

1. 规范快照同一性不变量无法由编码 owner 修正，需要比较侧特判；
2. Dolt 拒绝 `TEXT` 主键且需要超出 storage_projection 的方案（§8）；
3. legacy oracle 显示 BROWSE_ONLY/SNAPSHOT_ONLY 的比较形态与 R4 §4.3 冲突；
4. 需要 Preview 暂停确认、改判“不同项目”或跨规则集比较（分别重开 ADR 0020、Ruleset 迁移契约）；
5. 出现需要兼容旧数据的真实部署（重开 DC6）；
6. 身份确认需要 Review 阶段的独立交互（本设计只做只读展示）。

## 附录 A：Business Lifecycle 3.1.0 补充候选

以下为候选文本，独立审核通过后由 owner 并入
[Business Lifecycle](../contracts/business-lifecycle-and-state.md) 并将版本升至 3.1.0；接受前不改变 3.0.0。

1. §2 PreviewResult 的不可变绑定增加：上传 MODIFIED 侧与基线侧规范状态摘要、MODIFIED 侧
   CanonicalizationManifest 引用、身份评估集摘要与逐 pair 身份结论/执行模式。比较在规范域进行：
   被规则丢弃的列与 SKIP 表不属于比较对象。
2. §3 “canonical business digest” 定义为规范状态摘要；`NO_CANONICAL_CHANGE` 为 PreviewResult 中两侧
   规范状态摘要相等。Preview 含 `DIFFERENT_PROJECT` 或 `UNVERIFIABLE` pair 时，AcceptSubmit 必须携带
   对应的、彼此独立的身份确认；确认记录随 Attempt 冻结并复制到 Submission，不可变。
3. §4 Review 只读展示身份确认记录。
4. §5 AnomalyResolution 增加身份异常 subject；带身份确认记录的 Submission 被选为归档对象时必须有
   带理由的肯定处置。
5. §6 History 比较要求所有节点具有同一规则集的 commit 规范元数据；初始空 BaselineNode 为空规范状态。
