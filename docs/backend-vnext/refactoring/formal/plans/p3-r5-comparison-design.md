# P3-R5 Comparison Design Baseline

状态：Accepted design baseline；accepted detail plan；S0-S1 complete；implementation authorization pending

取代说明（2026-09-27）：§4 的流程词汇、§5 的 identity gate 与 continuation、§6.1 的单侧 `INITIAL_SNAPSHOT`
与 §6.3 的受信 flow context 由 [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md)（comparison 入口去流程化）与 [ADR 0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)（项目身份与数据替换）取代；
比较在规范域进行（[ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)）。历史正文不改写。

日期：2026-08-20

Owner：Backend vNext Comparison Capability

上游设计：[P3 Capability Foundation Design](p3-capability-foundation-design.md)

上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)

相关 contract：[Comparison Contract](../../../contracts/comparison.md)、[Risk Contract](../../../contracts/risk.md)、[Comparison Surface Contract](../../../contracts/comparison-surface.md)

本文是 P3-R5 的正式设计基线，不是 execution plan，也不授权实现。精确 wire 字段、artifact
manifest、fixture、budget 和 implementation step 必须在下一阶段的 R5 detail plan/S0 freeze
中冻结。本文记录已经讨论收口的架构语义以及不得被实现重新解释的边界。

## 1. Objective

R5 将 immutable before/current snapshot artifacts 转换为可复用、可审计、可重放的 comparison
facts 和 records closure，供后续 risk、surface、bundle 和 flow 使用。

```text
immutable SnapshotTableArtifact pair
  -> identity applicability / assessment gate
  -> comparison execution
  -> ComparisonFacts + optional ComparisonRecordsClosure
  -> downstream risk / surface / bundle
```

R5 的目标是稳定 comparison capability，不是把 upload、submit、workspace、repository、HTTP
或风险业务流程塞入 comparison 内部。

## 2. Authority and conflict resolution

语义优先级如下：

1. 本设计基线与用户确认的 R5 决策；
2. R4/R3 public artifact、reader、canonical encoding 和 storage contracts；
3. 现有 comparison、surface、risk contracts；
4. legacy 实现和 fixture 作为行为 oracle。

`CanonicalizationManifest` 在 R5 中只作为 opaque storage identity/binding。R5 不 import R4
private modules，不从 canonical storage 反推 comparison columns，也不把 R4 physical identity
提升为业务 stable key。

如果现有非 formal capability 文档与本文冲突，必须先同步 owning contract 或记录明确迁移，
不能通过兼容分支长期维护两套语义。本轮已修正 identity 文档中 `UNVERIFIABLE` 的旧宽松描述。

## 3. Scope and non-goals

### 3.1 In scope

- immutable before/current `SnapshotTableArtifact` 和 public reader closure；
- `FULL` / `MODIFIED_ONLY` 输入完整性语义；
- `DETAILED` / `DATASET_REPLACEMENT` comparison execution mode；
- `ALL_CHANGES` / `UPDATE_ONLY` table artifact scope；
- standard、keyless、ordered、schema、blank 和 records 语义；
- bounded execution、artifact publication、digest、replay guarantee 和 neutral core cache；
- `INITIAL_SNAPSHOT`、FULL 双 pair、history/archive applicability 的 envelope 语义；
- 为未来 static risk 预留独立 capability 与统一 aggregation contract seam。

### 3.2 Out of scope

- SourcePackage/SQL 解析和 source materialization；
- Repository/Dolt 写入、HTTP、Workspace、Submit、Archive 和 Operation Runtime；
- Risk provider 的当前 production implementation；
- Surface、Bundle 和业务 projection 的 production integration；
- static risk rules、risk provider registry 和 risk flow policy 的实现；
- cache retention、eviction、quota、跨服务分布式 cache 或授权状态持久化策略。

## 4. Input and execution vocabulary

> 由 [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md) 取代（见文首取代说明）。

这些字段属于不同维度，不能互相替代：

| 维度 | 值 | 含义 |
| --- | --- | --- |
| input completeness | `FULL` / `MODIFIED_ONLY` | 输入是否已经形成完整 before/current pair |
| comparison mode | `DETAILED` / `DATASET_REPLACEMENT` | 是否执行普通实体对齐和记录计算 |
| artifact scope | `ALL_CHANGES` / `UPDATE_ONLY` | 是否保留 INSERT/DELETE records |
| view kind | `PAIR_COMPARISON` / `INITIAL_SNAPSHOT` | 是否存在 directed before/current comparison |
| identity applicability | `REQUIRED` / `NOT_APPLICABLE` | 是否运行 project identity capability |

`MODIFIED_ONLY` 不是 sparse delta input。它必须先恢复 pinned baseline，形成完整 before/current
pair；恢复失败时不能猜测缺失行是删除。

`DETAILED`、`DATASET_REPLACEMENT` 是执行方式，不是 comparison 后的两种展示标签。
`DATASET_REPLACEMENT` 只由明确的 `DIFFERENT_PROJECT` assessment 产生；不得由普通 schema
差异或任意 caller 参数伪造。

## 5. Identity gate and continuation

> 由 [ADR 0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md) 与 [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md) 取代：身份评估由独立 `project_identity` capability 产出，不设 continuation 门，
> 身份确认在 AcceptSubmit 收集（见文首取代说明）。

`ProjectIdentityAssessment` 由独立 capability 拥有，R5 只消费 immutable assessment。
`version-manager-overlap/v1` 的分类为：

- 明确有交集：`SAME_PROJECT`；
- 两侧可比较且交集为空：`DIFFERENT_PROJECT`；
- 无法可靠比较：`UNVERIFIABLE`；
- trusted history/archive context 显式声明：`NOT_APPLICABLE`。

### 5.1 UNVERIFIABLE

`UNVERIFIABLE` 是两阶段 fail-closed：

1. 确认前只发布 assessment/diagnostic gate；不执行 comparison、risk、surface、business
   projection，不发布 READY 或 `ComparisonFacts`。
2. 前端确认 `ALLOW_DETAILED_ON_UNVERIFIABLE` 后，受信 orchestrator 重新校验 workspace、
   upload generation、snapshot digests、assessment-set digest、actor policy 和 policy
   version，再以显式 policy 调用 DETAILED comparison。

assessment/bundle 必须分别表达 `requires_continuation_confirmation` 与
`requires_submit_confirmation`；前者控制继续计算，后者控制不可逆 submit，不能共用一个
confirmation bit。

确认后的结果仍保留 `project_identity_status = UNVERIFIABLE`，`comparison_mode = DETAILED`，
overall 为 `DEGRADED`，并保留 `PROJECT_IDENTITY_UNVERIFIABLE` diagnostic。

普通用户得到的是可撤销的 server-side policy allowance，不得到 trusted caller 身份。policy
撤回不静默改写已生成 preview，但会阻止新的 continuation 或 submit。submit 使用独立 action
`ACCEPT_UNVERIFIABLE_DETAILED_RESULT`，绑定最新 preview/bundle/assessment digests，并在
submit 时再次检查当前 policy。

### 5.2 DATASET_REPLACEMENT

replacement 不做普通 row alignment，不调用 detailed records writer 或 comparison risk row
rules。输出 before/current dataset facts、replacement reason、assessment digest，
`records_ref = none`。同名表的 before/current 侧独立浏览，空表与缺表必须区分。

## 6. Initial snapshot and pair aggregation

### 6.1 INITIAL_SNAPSHOT

> 由 [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md) 取代：初始基线恒为空，以零表 `before` 传入，不再有单侧视图。

单侧初始展示使用独立 applicability，而不是伪装成 `UNCHANGED` 或
`BUSINESS_EQUIVALENT`：

```text
view_kind = INITIAL_SNAPSHOT
comparison_applicability = NOT_APPLICABLE
before = none
current = initial snapshot
comparison_facts = none
comparison_records = none
```

当前侧可以生成 business projection。未来 static risk 可以独立运行；不生成 diff records 或
comparison risk。数据 artifact 的可用性和风险 artifact 的可用性分别表达，不能用“没有
before”表示“没有变化”。建议使用独立的 `data_status` 与 risk status：snapshot/materialization/
projection 失败时不能发布数据结果；static risk provider 失败时不发布部分 annotation，保留
`STATIC_RISK_UNAVAILABLE`，数据 preview 可用但 aggregate/bundle 为 `DEGRADED`。

### 6.2 FULL pair set

FULL 结果按 pair 独立保存：

```text
baseline_to_initial   optional
initial_to_modified   primary
```

- 没有业务 baseline 时不生成 baseline pair；
- baseline 恢复失败时，该 pair 为 `BASELINE_PAIR_UNAVAILABLE`，整体最多 `DEGRADED`；
- primary pair 继续独立执行；
- primary pair 失败时整体为 `FAILED`；
- 每个 pair 独立拥有 facts、records、diagnostics 和 closure；
- 不将两个 pair 合并成跨三版本 records。

FULL 多 pair 使用一个 assessment-set digest；任一适用 pair 为 `UNVERIFIABLE` 时等待一次
确认。`NOT_APPLICABLE` pair 不触发 identity assessment，也不产生 replacement。

### 6.3 History compare and archive replay

> 由 [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md) 取代：History 视图与身份适用性由 Application 决定，comparison 不再接收受信 flow context。

history compare 与 archive replay 由受信 flow context 设置 `identity_applicability =
NOT_APPLICABLE`。普通客户端不能自由声明该值。此类比较不自动执行 project identity
assessment，也不生成 `DATASET_REPLACEMENT`。

## 7. Comparison facts and records

权威 public record 是 `ROW_MODIFIED`。旧前端所需的逐字段 UPDATE 展示是从该 record 派生的
`FieldChange` 视图，不建立第二个权威 record contract：

```text
FieldChange:
  table_name
  row_identity
  column_name
  before_value   # typed, null preserved
  current_value  # typed, null preserved
  change_kind = UPDATE
```

小结果可提供 typed before/current values；大结果使用 bounded Parquet records artifact。字段
值按 column schema 解释，不转成字符串；identity 和 digest 使用 canonical scalar encoding。

`UPDATE_ONLY` 抑制 INSERT/DELETE records，但保留 suppressed counts、`ROW_MODIFIED` 和派生
FieldChange。key 变化不能伪装成普通 field update；keyless 只有 deterministic multiset
matching 成功时才生成 field changes。

## 8. Schema, key and ordered semantics

- 字段顺序、display name、canonical name 大小写变化不算 schema change；
- 仅 ignored column 变化为 `SCHEMA_ONLY_CHANGED`；
- 非 ignored、非 key 字段增删为 `SCHEMA_CHANGED`，可继续比较兼容交集；
- selected column 的 type/nullability 变化为 `SCHEMA_CHANGED`，该字段不生成普通 FieldChange；
- 默认只允许 exact canonical scalar type，不做隐式 widening/coercion；
- effective key 增删、类型变化或来源变化为 `SCHEMA_CHANGED + ROW_ALIGNMENT_UNAVAILABLE`，
  不使用备用 key；
- key 未变且仍有兼容 selected columns 时，可继续有限 row diff，并单独输出 `SCHEMA_CHANGE`。

ordered comparison 可以分别输出内容和位置语义：

- `CONTENT_UPDATE` / `ORDERED_ROW_MODIFIED`；
- `MOVE` / `ORDERED_ROW_MOVED`；
- `ORDERED_POSITION_CHANGED` 只表示绝对 `no` 改变但相对顺序未变。

没有 stable key 时不推断 move，不退回 positional comparison。重放保证为 `EXACT`、`PARTIAL` 或
`UNSUPPORTED`，由 ordered facts 明确发布。

## 9. Physical identity and blank rows

R4 pseudo gid 是持久 physical `StorageRowKey`，不是跨 snapshot 的业务 stable key。R5 不从
pseudo gid 反推业务身份，也不引入跨 snapshot durable blank lineage。

SQL source 中 `4_000_000_000..4_294_967_295` 是 reserved-range，必须拒绝；只有受信
`CANONICAL_DOLT` reader 返回该范围并附带 blank provenance 时才是合法 physical key。

blank 由 source blank marker 或 `PSEUDO_BLANK` provenance 识别：

- 除 `gid/no` 外的属性允许变化，但 comparison 完全忽略；不判非法、不进 blank signature、
  digest 或 `ROW_MODIFIED`；
- blank 只比较 real-row backbone interval 内的 occupancy/count；
- blank 不产生 move，不建立普通 row identity；
- 同 interval 仅 `no` 重编号且 occupancy 不变时不产生 blank record；
- occupancy/interval 变化可独立产生 `BLANK_DELETE_INTERVAL` 和
  `BLANK_INSERT_INTERVAL`，不建立 move 配对；
- blank records 按 interval 聚合，只记录 interval/position/count/occupancy digest，不携带
  被忽略 payload；replay 只保证 occupancy/interval 语义。

## 10. Artifact, publication and resource boundary

正式 public records closure 使用 immutable canonical Parquet 全量文件；JSON 仅用于 metadata、
facts 和 diagnostics，JSONL 只能作为内部临时 spool。分页属于 reader API，opaque page token
绑定 manifest digest、table、sort policy 和最后 canonical sort key，不按行号分页。

执行使用 pair/table/runtime 分层 bounded budgets：

- HASH 超内存时 AUTO 可切 SQLite；
- SQLite、spill、records 或 per-table budget 超限时当前表 `DEGRADED`，丢弃 partial artifact，
  其他表继续；
- 用户取消/deadline 不发布 `ComparisonFacts` 或 records closure；
- reader/key/schema 问题可形成完整表级 `DEGRADED`；
- writer/manifest/digest/closure 校验失败为 pair-level `FAILED`，不发布 READY；
- `ComparisonFacts` 只有 planned tables 都有终态、closure 完整、transient resources 关闭、
  digest 完成后才能发布。

benchmark 只记录 workload、cold/cache、HASH/SQLite、duration、CPU/RSS、spill、artifact bytes、
records count 和 cancellation latency；当前不设固定性能 gate。

## 11. Cache layering

允许复用 neutral comparison core，但不直接复用带 identity/authorization 的 final facts。

```text
neutral comparison core cache
comparison risk cache
static risk cache
```

neutral core key 至少绑定 before/current snapshot digests、comparison semantic options、ruleset/
projection/scalar/ordered/blank contract versions、scope 和 algorithm version。core value 必须
是 canonical facts/records closure，不包含 flow identity、authorization、submit state 或 host
path。

restore 后必须重新绑定 comparison mode、identity status、assessment digest、continuation policy
version、final facts digest，并重新建立 operation-local artifact closure、risk aggregation 和
surface/bundle digest。cache hit 不授予任何 continuation/submit 权限。

`SAME_PROJECT` 与已确认继续的 `UNVERIFIABLE` 可以复用同一 DETAILED core；
`DATASET_REPLACEMENT` 不复用 DETAILED core。

## 12. Future static risk seam

static risk 与 diff risk 采用“计算能力独立、结果统一聚合”：

```text
comparison_risk  -> comparison risk artifacts
static_risk      -> static snapshot risk artifacts
risk_aggregation -> unified RiskReport / RiskReportSet
surface/bundle   -> aggregated risk contract
```

`comparison_risk` 消费 `ComparisonFacts`/comparison records；`static_risk` 消费 immutable
`SnapshotTableArtifact`/public reader closure，不依赖 comparison。两者共享 `RiskSource`、
`RiskAnnotation`、`RiskReason`、`RiskTarget`、artifact closure 和 aggregation contract，但不
合并成带大量 optional input 的 provider DTO。

digest/cache 分层为 `comparison_risk_digest`、`static_risk_digest` 和
`risk_report_set_digest`。static risk 不改变 `ComparisonFacts`，diff risk 不改变 static risk
artifact。`INITIAL_SNAPSHOT` 可以只有 static risk；各 provider 可独立失败，aggregation 保留
source 和 diagnostics。

R5 只预留 contract seam，不实现 static risk rules、provider registry 或 production aggregation。

## 13. Acceptance and reopen conditions

R5 detail plan 必须将本文规则落成：

- public type/field owner 和 version；
- table/pair/operation failure matrix；
- blank、ordered、schema、keyless、UNVERIFIABLE 和 cache fixture matrix；
- exact resource budgets 和 cancellation behavior；
- HASH/SQLite canonical equivalence；
- records manifest/replay and artifact closure tests；
- architecture forbidden-import tests；
- comparison-only risk compatibility and future static-risk seam tests。

在以下情况发生时，必须 reopen R5 design，而不能在实现中静默选择：

- `UNVERIFIABLE` 被改成自动继续，或普通 caller 能伪造 `NOT_APPLICABLE`；
- pseudo gid 被提升为跨 snapshot 业务 stable key；
- blank ignored payload 开始影响 comparison digest 或 row records；
- replacement 开始使用普通 row alignment/records/risk annotations；
- static risk 反向修改 `ComparisonFacts` 或被塞入 comparison input 的 optional 字段；
- cache hit 能绕过 identity confirmation、policy recheck 或 submit binding；
- partial artifact 能被发布为 READY；
- R5 引入 HTTP、Workspace、Submit、Repository/Dolt 或 Operation Runtime production dependency。
