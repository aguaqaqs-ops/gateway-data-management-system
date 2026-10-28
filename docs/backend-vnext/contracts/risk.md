# Risk Contract

> 当前实现合同为 `backend-vnext/risk/v2`：schema-only additions 不产生 schema-change 风险，整表新增/删除风险证据带表行数。

本文定义 backend vNext 第一版 risk engine contract。Risk 只消费 `ComparisonFacts` 和可选 records artifacts，输出 flow-neutral `RiskEvaluation`、`RiskReport` 和可选 annotation artifacts。

S2 已实现 bounded Python reference evaluator、canonical annotation artifacts 和 immutable
risk annotation closure。执行入口为调用方注入 frozen `RiskRulesetSnapshot` 的
`evaluate_risk(...)`；不使用 mutable registry 或 implicit ruleset fallback。

旧实现中的 `RiskLevel`、`RiskTarget`、`RiskReason`、`RiskAnnotation`、`RiskRuleRegistry`、standard/structural/ordered basic rule 思路可以作为业务语义参考；vNext contract 不依赖旧 `risk`、`compare`、`comparison_surface` 或 `workbench` 模块。

Ordered risk 的旧功能映射见 `../contracts/ordered-diff.md`。vNext 模块边界可以简化，但 IEC104 ordered tail/middle/move 风险分级需要恢复。

## 范围

Risk contract 负责：

- 接收 `ComparisonFacts`。
- 按调用方传入的 `RiskRulesetSnapshot` 计算风险事实。
- 输出 `RiskEvaluation`、`RiskReport` 和可选 `RiskAnnotationArtifact`。
- 为 surface / bundle 提供稳定风险输入。

Risk contract 不负责：

- 计算 diff。
- 读取 SourcePackage、SqlDumpSource 或 RepositoryRef。
- 写 repository 或创建 commit/ref。
- 推进 Workspace、Submission、History request 等业务状态。
- 组装 ComparisonSurface 或 WorkbenchBundle。
- 定义 ordered table diff algorithm；有序表 diff contract 见 `ordered-diff.md`。

## 对象链路

```text
ComparisonFacts + optional ComparisonRecords access
  -> RiskEvaluationInput
  -> RiskFacts per table
  -> RiskRule evaluation
  -> RiskEvaluation
  -> RiskReport + optional RiskAnnotationArtifact
  -> Surface / Bundle
```

S2 result envelope：

```text
RiskEvaluationResult:
  status: READY | DEGRADED | FAILED | CANCELLED
  risk_evaluation optional
  risk_report optional
  annotation_artifacts optional
  risk_closure optional
  cache_diagnostics
  diagnostics
```

`FAILED` 和 `CANCELLED` 不得暴露 risk evaluation、report、annotation ref 或 closure。
普通 table `DEGRADED` 继续输出其他表的 risk，并在 closure 中保留显式 no-record entry。

规则：

- Risk 是 directed comparison 的下游能力，方向由 `ComparisonFacts.direction` 决定。
- Risk 不改变 `ComparisonFacts`。
- Risk 输出必须保持 flow-neutral；upload、submit、history compare 等 flow 只能作为调用上下文 metadata，不进入 risk digest。
- Flow 负责选择 risk ruleset；risk capability 只应用传入的 ruleset。
- `RiskExecutionPolicy` 固定 S0 的 table、annotation、JSON、artifact、diagnostic 和 wall-time
  budgets；execution context 的 cancellation/deadline 不进入 semantic digest。

## RiskEvaluationInput

```text
RiskEvaluationInput:
  comparison_facts
  records_access optional
  risk_ruleset: RiskRulesetSnapshot
  risk_contract_version
  risk_model_version
  requested_tables optional
  risk_options
  artifact_policy
  cache_policy optional
```

`records_access`：

- 指向 operation-local 或 cache-restored comparison records closure。
- 通过同一个 access 暴露 ordered records lookup，供 ordered semantic rule 读取对应 table 的 records artifacts。
- 第一版 risk rules 默认只依赖 `ComparisonFacts` 的 table facts、row counts、schema changes 和 diagnostics。
- 只有明确需要 changed columns、ordered evidence 或 row-level evidence 的规则才读取 records artifacts。

`risk_options` 第一版：

```text
risk_options:
  include_low_risk: true | false
  include_unknown: true | false
  annotation_detail_policy:
    COUNTS_ONLY | TARGETS_ONLY | TARGETS_WITH_EVIDENCE
```

规则：

- `risk_options` 进入 `risk_evaluation_digest`。
- operation id、flow id、workspace id、history request id、host path 不进入 digest。
- artifact refs 不进入 digest；artifact content/manifest digest 可进入 risk result digest。

## RiskRulesetSnapshot

```text
RiskRulesetSnapshot:
  risk_ruleset_id
  risk_ruleset_version
  risk_ruleset_digest
  risk_model_version
  rules:
    - rule_id
      rule_version
      target_scope
      severity_policy
      params optional
```

规则：

- Flow/operation 负责选择 ruleset/profile。
- Capability 不根据 flow name 自动切换 ruleset。
- `risk_ruleset_digest` 由 ruleset 内容和 ruleset contract version 计算。
- `risk_ruleset_digest` 进入 `risk_evaluation_digest` 和 future risk cache key。
- ruleset 必须由调用方注入 frozen `RiskRulesetSnapshot`；S2 不创建 registry，也不使用 implicit fallback。
- v1 额外固定 `UNKNOWN_CHANGE_TARGET`（`UNKNOWN`）规则，用于任何未被显式规则覆盖的 change target；未知目标不得静默丢弃。

## RiskFacts

`RiskFacts` 是 risk engine 从 `ComparisonFacts` 派生出的 table-level risk input。

```text
RiskFacts:
  comparison_digest
  table_name
  table_status
  risk_scope:
    TABLE | STANDARD_ROWS | ORDERED_TABLE | DEGRADED_TABLE
  schema_changes optional
  row_change_stats optional
  degraded: true | false
  degraded_reasons
  records_ref optional
  semantic_facts optional
  diagnostics
```

`row_change_stats`：

```text
row_change_stats:
  row_added_count optional
  row_deleted_count optional
  row_modified_count optional
```

`semantic_facts` 是扩展点：

```text
semantic_facts:
  kind
  payload
  semantic_contract_version
```

第一版：

- 普通表使用 `STANDARD_ROWS`。
- schema-only / table added / table deleted 使用 `TABLE`。
- key missing、duplicate key、ordered unsupported 等使用 `DEGRADED_TABLE`。
- ordered table provider 未接入或 degraded 时使用 `DEGRADED_TABLE`；provider 接入后应恢复 ordered semantic risk。

后续 ordered diff provider 完成后，可增加：

```text
semantic_facts:
  kind: ORDERED_TABLE
  move_count
  middle_insert_delete_count
  tail_insert_delete_count
  position_changed_count
  replay_guarantee
  ordered_diagnostics
```

`position_changed_count` follows [R5 §8](../refactoring/formal/plans/p3-r5-comparison-design.md#8-schema-key-and-ordered-semantics): it counts skeleton rows only and excludes moved rows.

## RiskLevel

第一版沿用旧实现的等级形状：

```text
RiskLevel:
  HIGH
  MEDIUM_HIGH
  UNKNOWN
  MEDIUM_LOW
  LOW
```

排序建议：

```text
LOW < MEDIUM_LOW < UNKNOWN < MEDIUM_HIGH < HIGH
```

规则：

- `UNKNOWN` 表示当前规则无法精确判定，不等于安全。
- `UNKNOWN` 只能来自 risk engine 明确产出的 annotation / table risk，例如 degraded、
  unsupported 或规则无法覆盖但需要人工审阅的变更。缺少 annotation 不得序列化为
  `UNKNOWN`。
- degraded / unsupported / missing semantic provider 默认不应降为 LOW。
- `RiskReport.overall` 取最高风险等级。

## RiskTarget

```text
RiskTarget:
  target_type:
    COMPARISON
    TABLE
    ROW
    ROW_PAIR
    ROW_INTERVAL
  table_name optional
  row_identity optional
  before_row_identity optional
  current_row_identity optional
  changed_columns optional
  position optional
  position_range optional
  coverage optional
```

第一版 target：

- `TABLE`：表新增、表删除、schema change、degraded table。
- `ROW`：row added / row deleted。
- `ROW_PAIR`：row modified。
- `COMPARISON`：全局风险或 evaluation-level diagnostic。

`ROW_INTERVAL` 预留给 ordered table provider 完成后的 interval/move/position risk。

## RiskReason

```text
RiskReason:
  reason_code
  message
  rule_id
  evidence optional
```

规则：

- `reason_code` 是稳定机器可读值。
- `message` 是诊断/展示辅助，不进入风险身份。
- `evidence` 不应包含 host path 或敏感大 payload。

## RiskAnnotation

```text
RiskAnnotation:
  annotation_id
  risk_level
  target
  reasons
  diagnostics optional
```

规则：

- `annotation_id` 在同一 `RiskEvaluation` 内稳定。
- annotation 可以写入 artifact；`RiskReport` 可只保留 annotation ref 和 summary。
- 大量 row-level annotations 不应全部内联到 `RiskReport`。

## RiskEvaluation

```text
RiskEvaluation:
  risk_evaluation_digest
  risk_contract_version
  risk_model_version
  risk_ruleset_digest
  comparison_digest
  summary
  table_risks:
    - RiskTableRisk
  annotation_refs optional
  diagnostics
```

`risk_evaluation_digest` 输入：

- `comparison_digest`。
- `risk_contract_version`。
- `risk_model_version`。
- `risk_ruleset_digest`。
- `risk_options`。
- table risk digests。
- annotation artifact manifest digests。

不进入 digest：

- risk evaluation id。
- operation id。
- flow id。
- workspace/submission/history request id。
- host path。
- artifact refs。
- diagnostics。

## RiskTableRisk

```text
RiskTableRisk:
  table_name
  risk_level
  reason_codes
  annotation_count
  annotation_ref optional
  source_table_status
  diagnostics optional
```

规则：

- 表级 risk summary 可被 surface/sidebar/bundle 直接消费。
- 没有 `RiskTableRisk` 表示该表没有风险 annotation；前端兼容 payload 应序列化为
  `risk_level: null`、`annotation_count: 0`、空 `reason_codes`，不显示风险徽标。
- `annotation_ref` 不进入 digest；annotation artifact manifest digest 可以进入 table risk digest。

## RiskReport

`RiskReport` 是可展示/可下载的风险摘要，不是前端 surface。

```text
RiskReport:
  risk_report_contract_version
  risk_evaluation_digest
  overall:
    risk_level
    reason_codes
  tables:
    - RiskTableRisk
  annotation_refs
  diagnostics
```

规则：

- `RiskReport` 不包含 ComparisonRecords full payload。
- `RiskReport` 不定义 UI layout。
- `RiskReport.tables` 只包含真实风险表；无风险表不应为了 UI 完整性补 `UNKNOWN`。
- 对外发布的 annotation payload 必须保持 `RiskAnnotationArtifact.content_payload()` 的规范
  JSON 内容，不得追加 `view_id`、`risk_model_version` 等发布期字段导致 content digest
  与源 artifact 不一致。view scope 由 `ComparisonSurface` / bundle ref 所在 pair 决定。
- Upload preview 与 history comparison 中，任何公开的 `annotation_ref` / manifest ref 都
  必须闭合为真实 `backend-vnext/risk-annotations/v1` artifact。placeholder 或空 sidecar
  不属于合法 risk annotation artifact。
- surface / bundle 可以引用 RiskReport，但不能要求 risk engine 理解前端结构。

## Legacy Risk Simplification

vNext risk contract 简化旧实现的输入输出形状，但保留成熟的风险业务语义。

保留：

- `RiskLevel` 等级形状和 highest-risk aggregation。
- `RiskTarget` / `RiskReason` / `RiskAnnotation` 的核心语义。
- structural / standard row / degraded / ordered placeholder rules 的业务含义。
- rule registry、rule id、ruleset digest、rule model export 的思路。
- 表新增/删除、schema changed、row add/delete/modify、unknown/degraded 等用户可见风险。

不保留：

- 旧 `RiskEngine` 直接消费 `TableCompareResult` 的输入形状。
- 旧 risk contract import 旧 compare enum。
- `PreviewBundleContext`、sidebar projection、surface refs、workbench bundle refs。
- 为旧前端服务的 UI layout、tab、sidebar 或 bundle-specific projection。
- ordered basic rule 的旧输出形状；第一版只保留 ordered unsupported review-required 风险。

简化后的责任：

```text
ComparisonFacts + optional records access + RiskRulesetSnapshot
  -> RiskEvaluation
  -> RiskReport + optional RiskAnnotationArtifact
```

规则：

- `RiskReport` 是风险摘要，不是 surface/sidebar。
- `RiskAnnotation` 只表达 target、level、reason 和 optional diagnostics。
- surface、bundle、frontend 或 adapter 可以从 `RiskReport` / `RiskAnnotationArtifact` 派生导航和展示投影。
- 不为了复刻旧 bundle 文件结构把 UI projection 写回 risk core。

旧功能覆盖通过 contract tests 保证，而不是通过保持旧输入输出同构保证。

覆盖项：

| 旧风险能力 | vNext 来源 |
| --- | --- |
| 表新增/删除风险 | `RiskFacts(TABLE)` + structural rules |
| schema changed 风险 | schema risk facts + structural rules |
| row add/delete/modify 风险 | `RiskFacts(STANDARD_ROWS)` + standard rules |
| degraded / unknown 风险 | `RiskFacts(DEGRADED_TABLE)` + degraded rules |
| risk-only 浏览 | `RiskReport` + `RiskAnnotationArtifact` |
| table-level annotation | `RiskTarget(TABLE)` |
| row / row pair annotation | `RiskTarget(ROW)` / `RiskTarget(ROW_PAIR)` |
| overall risk | highest-risk aggregation |
| ordered unsupported | `ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED` |

## 第一版规则集建议

第一版最小 rules：

| Rule | 输入 | 默认风险 |
| --- | --- | --- |
| `TABLE_ADDED` | `ADDED_TABLE`；证据 `row_count` 为新增表行数 | `MEDIUM_LOW` |
| `TABLE_DELETED` | `DELETED_TABLE`；证据 `row_count` 为删除表行数 | `MEDIUM_HIGH` |
| `SCHEMA_CHANGED` | schema changes | `MEDIUM_HIGH` |
| `ROW_ADDED` | added rows | `MEDIUM_LOW` |
| `ROW_DELETED` | deleted rows | `MEDIUM_LOW` |
| `ROW_MODIFIED` | modified rows | `MEDIUM_HIGH` |
| `KEY_DEGRADED` | missing/duplicate/effective key changed | `UNKNOWN` |
| `ORDERED_DIFF_UNSUPPORTED` | ordered table provider missing/degraded | `UNKNOWN` |
| `COMPARISON_FAILED` | comparison failed | `HIGH` |

规则：

- 默认风险等级可由 `RiskRulesetSnapshot` 调整。
- `schema_evolution=COLUMNS_ADDED` 不产生 `SCHEMA_CHANGED` 风险；`COLUMNS_REMOVED` 与 `INCOMPATIBLE` 按 schema-change 规则评估。
- `ORDERED_DIFF_UNSUPPORTED` 的默认 reason code 建议为 `ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED`。
- ignored columns 不直接产生 row risk；可作为 diagnostics 或 LOW notice。

## Ordered Table 扩展

Risk 不定义 ordered diff algorithm；ordered facts 来自 `ORDERED_TABLE_COMPARE`。

ordered provider 未接入或 degraded 时：

- 如果 comparison 输出 ordered unsupported/degraded，risk 输出 `UNKNOWN` + review-required reason。
- 不把普通 key-based fallback 伪装成 ordered semantic risk。

ordered provider 接入后，第一版 ordered risk 需要恢复旧分级：

| Reason code | 默认风险 | Target |
| --- | --- | --- |
| `ORDERED_REPLACEMENT` | `MEDIUM_LOW` | `ROW_PAIR` |
| `ORDERED_MOVE` | `MEDIUM_HIGH` | `ROW` |
| `ORDERED_MIDDLE_INSERT_DELETE` | `MEDIUM_HIGH` | `ROW` / `ROW_INTERVAL` |
| `ORDERED_MIDDLE_BLANK_INTERVAL` | `MEDIUM_HIGH` | `ROW_INTERVAL` |
| `ORDERED_TAIL_INSERT_DELETE` | `LOW` | `ROW` / `ROW_INTERVAL` |
| `ORDERED_TAIL_BLANK_INTERVAL` | `LOW` | `ROW_INTERVAL` |
| `ORDERED_NAME_UPDATE` | `LOW` | `ROW` |
| `ORDERED_CONTENT_UPDATE` | `MEDIUM_LOW` | `ROW` |
| `ORDERED_RISK_UNKNOWN` | `UNKNOWN` | `TABLE` / `ROW` |

规则：

- `ROW_INTERVAL` 用于 tail/middle interval 和 blank interval 定位。
- reason code、默认风险和 target 需要与 `contracts/ordered-diff.md` 保持一致。
- Surface/bundle 只消费 risk output，不重新判定 tail/middle/move 风险。

## 非目标

第一版不定义：

- Ordered diff compute algorithm。
- ComparisonSurface / WorkbenchBundle 结构。
- risk cache 具体存储和 cleanup。
- 前端 annotation layout。
- 人工审核状态机。
- 跨项目 risk 聚合。

## 验收标准

- 同一 `ComparisonFacts`、risk ruleset、contract version 和 options 下，重复 evaluation 得到相同 `risk_evaluation_digest`。
- Risk capability 不 import 旧业务模块。
- Risk capability 不读取 SourcePackage、RepositoryRef 或 repository server。
- Risk capability 不生成 ComparisonSurface 或 WorkbenchBundle。
- degraded/unsupported 表能产生 review-required risk。
- ordered unsupported 不被误判为 LOW。
- 大量 annotations 可以落 artifact，RiskReport 只保留 summary/ref。
