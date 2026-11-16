# Risk Contract

> 当前实现合同为 `backend-vnext/risk/v2`：严格证明共有值未变的纯增删列不产生 schema 风险；整表新增/删除风险证据带表行数。

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
| `TABLE_ADDED` | `ADDED_TABLE`；证据 `row_count` 为新增表行数 | `LOW` |
| `TABLE_DELETED` | `DELETED_TABLE`；证据 `row_count` 为删除表行数 | `MEDIUM_HIGH` |
| `SCHEMA_CHANGED` | schema changes | `MEDIUM_HIGH` |
| `ROW_ADDED` | added rows | `MEDIUM_LOW` |
| `ROW_DELETED` | deleted rows | `MEDIUM_LOW` |
| `ROW_MODIFIED` | modified rows except name/description-only | `MEDIUM_HIGH` |
| `STANDARD_NAME_UPDATE` | standard row changes confined to name/description | `LOW` |
| `KEY_DEGRADED` | missing/duplicate/effective key changed | `UNKNOWN` |
| `ORDERED_DIFF_UNSUPPORTED` | ordered table provider missing/degraded | `UNKNOWN` |
| `COMPARISON_FAILED` | comparison failed | `HIGH` |

规则：

- 默认风险等级可由 `RiskRulesetSnapshot` 调整。
- 风险使用 Comparison v4 的统一投影：已证明的纯增删列不产生 `SCHEMA_CHANGED`；未知结构变化可投影为 `SCHEMA_ONLY_CHANGED`，不能仅凭 `COLUMNS_ADDED` 名称免除风险。兼容 ENUM/SET 演进及真实共有值变化按原行/content 口径；其余可见 `COLUMNS_REMOVED` 与 `INCOMPATIBLE` 继续按 schema-change 规则评估。
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
| `ORDERED_MIDDLE_INSERT_DELETE` | `MEDIUM_HIGH`；表名匹配通道命名且含 `yk` 时 `HIGH` | `ROW` / `ROW_INTERVAL` |
| `ORDERED_MIDDLE_BLANK_INTERVAL` | `MEDIUM_HIGH`；表名匹配通道命名且含 `yk` 时 `HIGH` | `ROW_INTERVAL` |
| `ORDERED_TAIL_INSERT_DELETE` | `LOW` | `ROW` / `ROW_INTERVAL` |
| `ORDERED_TAIL_BLANK_INTERVAL` | `LOW` | `ROW_INTERVAL` |
| `ORDERED_NAME_UPDATE` | `LOW` | `ROW` |
| `ORDERED_CONTENT_UPDATE` | `MEDIUM_LOW` | `ROW` |
| `ORDERED_RISK_UNKNOWN` | `UNKNOWN` | `TABLE` / `ROW` |

规则：

- `ROW_INTERVAL` 用于 tail/middle interval 和 blank interval 定位。
- reason code、默认风险和 target 需要与 `contracts/ordered-diff.md` 保持一致。
- Surface/bundle 只消费 risk output，不重新判定 tail/middle/move 风险。

当前 ruleset v8 对有序表使用专项规则，不重复应用普通行风险。`ORDERED_ROW_MOVED` 逐行产生 `ORDERED_MOVE`。有序比较层在同一对骨架锚点之间忽略空点；两侧非空新增/删除数量相同且该区间无移动实体时，按相对顺序给新增行附上删除行身份与原位置。风险层核对对应删除记录后配成 `ORDERED_REPLACEMENT`，目标位置取新增侧 `no`；有空点变化而缺少可信配对证据时不按相同绝对 `no` 猜测替换。无空点变化时保留相同 `no` 的配对。单独的新增、删除按该位置是否超出另一侧实际最大 `no` 区分尾部与中间。修改列仅由 `name`、`description` 中一个或两个字段组成时使用 LOW 专项，包含其他列时使用 `ORDERED_CONTENT_UPDATE`。无法确定修改列、缺少必要记录或仅有不可解释的位置变化时输出 `ORDERED_RISK_UNKNOWN`；非 EXACT 的有序或空点重放也输出 UNKNOWN，degraded 沿用 review-required 诊断。

对 `BLANK_INSERT_INTERVAL` 和 `BLANK_DELETE_INTERVAL` 分别读取改后侧或改前侧的最后保留有效位置：证据完整且该位置不存在或小于区间 start 时为尾部 LOW，否则为中间 MEDIUM_HIGH。保留有效点包括移动行，不包括 canonical blank 或本侧纯增删位置；证据不完整产生 ORDERED_RISK_UNKNOWN。区间可能跨越非骨架行或稀疏 no，row_count 是两侧空点数净差的绝对值，而非范围跨度；风险 target 表示受影响区域，evidence.count 保留净变化数，不将整个范围声称为逐点变化。

对中间普通行增删和中间空点增删，有序表名经 Table Rules 通道名解析器匹配 `b数字_n数字_...` 或 `b数字_c数字_...` 且含小写字面 `yk` 时使用 HIGH 专项规则；其余表保持 MEDIUM_HIGH，尾部、移动与替换规则不变。此风险选择只依表名和有序事实，不依赖 Navigation 的通道注册归属；Owner 已确认两者口径可暂时不同。单表候选 key 绑定该匹配结果，规则参数及 HIGH 专项由 ruleset digest 与 validator 核对。边界或记录证据不足仍按原契约报告 UNKNOWN。


风险输入按表携带 `ordered_tail_bounds={before_max_position,current_max_position,before_last_retained_position,current_last_retained_position,complete}`。两侧扫描排除实际增删记录位置并核对记录数量、位置及非降级证据；候选 key 绑定当前表的边界和完整性。History 缓存命中仍须恢复必要 reader。Preview assemble-state v11、History assemble-state v8 由 checkpoint 解码器核对。

风险读取与缓存：Comparison handle 的 `risk_record_batches(family)` 对 STANDARD、ORDERED、BLANK 分别返回最小 typed Arrow facts 投影；ORDERED 直接遍历原生 `ordered_facts_order`，BLANK 直接遍历 `blank_facts_order`（相邻稳定锚顺序，不另按位置排序）。ORDERED 保留 kind、identity、两侧 position、changed_columns，以及仅新增行可有的 replacement_before_identity/position；BLANK 保留 kind、两侧区间端点和净 row_count。每批最多 1024 行，构建前向原生 operation 预约，封存前完成构建，Arrow buffer 保留 owner/lease 至最后消费者退出。Artifact 视图及其排序不变。风险按规则族重读这些视图：移动、修改、已证明的替换、剩余新增/删除、空白区间；同族标注遵循 facts 序，替换与剩余增删按位置输出，配对索引和每批 Python 转换均先预约必要内存，必要时回收可选风险候选。

`comparison-table-cache/v3` 由任务身份与恢复 codec 核对，拒绝没有替换配对列的旧风险投影；持久闭包最多九个视图（三族 facts、artifact、risk），恢复保留原批次边界与顺序，仍受同 operation M 约束。风险候选沿用既有有序事件回放，v8 ruleset、适用性/尾部边界及完整比较任务身份使旧规则/旧比较缓存身份不能命中；标注编号、过滤与 cap 始终由当前 emit 决定。`COUNTS_ONLY` 对专项原因按首次出现次序聚合为 TABLE/ROW_COUNTS，行/替换计一项，空白区间计净变化行数；不发布逐条标注文件。v3 防止读取缺少配对证据的旧视图，由 comparison cache 恢复器核对；v8 防止旧风险规则复用，由风险规则校验器核对。

前端配合：`ROW_INTERVAL` 标注没有普通行身份，消费者应按 evidence 中的 `side` 及 `position_range` 将风险映射到对应快照的 `no` 区间，同时保留表级和视图级汇总；新增的 `ORDERED_*` reason code 需要对应的用户文案。此项不由后端行 locator 推断，也不在本次改动前端。

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

## Arrow 消费与完整候选复用

风险规则继续由 Python 拥有。当前比较计算可将内存 Arrow records 按表/批交风险消费，仅转换规则需要的列；不要求重建整份 ComparisonRecord tuple，不以先写 Parquet 再读回作为当前风险计算输入。计数/schema 风险仍直接消费 facts。

语言/传输替换不得改变表与规则遍历顺序、target/reason/severity、标注排序及编号、单表限制、pair 上限、截断/降级或组合信号语义。风险行规则使用现 facts 的记录顺序，不能以产物排序替代。单表纯候选按包含完整 comparison/risk 规则主体及版本的 key 复用；pair 上限、标注编号、表名/显示名和组合信号在当前汇总步骤绑定。纯候选仍受单表资源限制，失败/取消不缓存。接口及覆盖移交见 [S3 设计](../refactoring/formal/plans/p6-s3-design.md)和 [S5 设计](../refactoring/formal/plans/p6-s5-design.md)。

S3 风险上限重放必须保留当前控制流：在等级过滤前检查上限，同时触达 table/pair 上限时 pair 优先。`_TableBudgetExceeded` 异常分支产生单表 degraded outcome，但不增加后续 pair 的 `total_annotations`；正常返回 outcome 才累加，其中包括诊断数量/字节预检直接返回的 degraded。pair 超限丢弃全部部分标注，不是截取前 K 项。缓存命中仍执行当前 pair 的 closure 检查与当前取消/时间检查，不能复用先前验证结论；本段仅澄清现行语义，非修复算法行为。

内部风险输入为小型 table facts 加同一 operation 的只读 records handle。行规则按 standard facts 序请求最少列（kind、identity、changed columns及该规则需要的值）；无行规则时不取行批，ordered 降级还要综合 extension status、`TABLE_DEGRADED` 存在性和 diagnostics。候选事件流按现规则顺序保留每个 `Emit(rule_id,target_without_binding,evidence)`，包括最终被等级过滤的事件；`CheckRecordsClosure` 等控制步骤仍在原位置按当前 pair 执行。诊断预算预检直接返回 degraded 的分支也属于每次消费的控制流。只有自然穷尽且未失败、超时或取消的完整候选序列可在同一 operation 内复用；记录候选的额外内存不足时继续本次惰性计算并安全放弃复用。当前 pair 的上限、等级过滤、编号、表名、组合信号、时间检查和 closure 校验在消费时执行。向量及逐事件预期见 [S3 A 交接](../refactoring/formal/plans/p6-s3-a-contract-handoff.md)。

### S5 neutral 候选接口

`RiskCandidateInputV1` 使用 Comparison owner 的完整单表任务身份（覆盖 neutral facts/records），加当前纯风险 facts、完整风险规则主体/model/version、RiskOptions、artifact detail、policy 语义版本和全部有效 diagnostics 生成有域分隔的规范 JCS SHA256。当前 comparison/table digest、closure ref、表显示绑定、时间、剩余名额不作持久身份；规则或 schema 中有业务含义的名称仍由原 owner 的任务身份保留。不再使用 `repr` 或含当前表绑定的 `table_fact_digest` 作为纯候选 key。

`risk-table-candidates/v1` 是有序 JCS 事件文档，包含格式、task digest、`complete: true` 与连续 ordinal。`CHECK_RECORDS_CLOSURE` 只表示当前必须验证，不保留验证结论；`EMIT` 保存 rule_id、无 table_name 的完整 typed target 与有序 evidence。恢复严格校验封闭字段、类型、顺序、格式与 key，绑定当前表名后仍走原 emit 闭包。每个 emit 保持 cap（同时触界时 pair 优先）→记录候选→rule/level 过滤→必要输出预约/编号/append→原 `_check_table`；被过滤候选不新增该处时间检查，最后一条被保留候选仍执行原检查。每 1024 事件只补 operation 控制 checkpoint，不前移 table/pair 时间检查。

候选内存、序列化 scratch、读入与恢复对象均在同 operation M 中增长前预约，最后 consumer 关闭。当前 codec 的 16MiB 为可选保留上限，超过只放弃缓存，不改变产品接受范围或继续执行已截断规则。仅自然结束且当前 pair 成功的完整序列可登记持久条目；基础设施拥有 SQLite/TTL/protection，风险 owner 不依赖 DB 或 application。组合信号仍每次由当前汇总处理，不缓存最终 outcome、编号或截断结果。
持久候选通过 Artifacts 的通用引用端口读取，Risk owner 编解码完整事件；其能力不依赖
同 operation 还有第二次使用。新 operation 命中仍沿同一 emit/closure 路径；坏事件精确
失效后惰性重算，输出预约不足先释放可选读入，再走原规则。pair 出版成功后才登记完整
候选或延长命中条目 TTL，consumer 结束关闭 lease，assembly owner 在 READY 前释放活动 cache pin。

风险侧最小只读接口按 `iter_record_batches(table, family=STANDARD, columns=(...), order=FACTS) -> Iterator[RecordBatch]` 定义，`family` 必须显式为 STANDARD/ORDERED/BLANK 中一族，`order` 对风险只能是 `FACTS`，`columns` 只能选该族已定义的必要列；未知列/族或已释放 owner 应拒绝。每个 batch 保留所请求列的 Arrow 类型与原 facts 全局顺序，跨 batch 连接后恰等于该族 facts 顺序；不能用 artifact 序、到达顺序或全表 `to_pylist()` 代替。迭代可重复以供现三种 row kind 遍历，返回 batch 借用同一 operation owner；提前关闭、异常、取消和最后消费者退出均释放借用与预算。`record_count(table,family)`、`has_records(table,family)`、`ordered_degraded(table)` 是小型事实查询，分别返回该族精确 count、存在性及 extension status/`TABLE_DEGRADED`/diagnostics 的合并布尔值，不构造记录元组。现 `_facts.py` 的 visible/scope 判断使用 STANDARD 的存在性，ordered unsupported 使用合并布尔值；closure refs 仍由现 `records_access` 控制步骤读取。

<a id="p7-s1a-目标补充risk位置待实现"></a>

## P7-S1a 生效补充：risk位置（已生效）

状态：S1a risk 位置接线已实现并经 G 核收，证据与适用边界见 [S1a 总结](../refactoring/formal/plans/p7-s1a-summary.md)；[A 入口](../refactoring/formal/plans/p7-s1a-a-entry-and-contract.md)保留当时仅固定目标的历史事实。risk content/annotation manifest/closure与持久neutral candidates/envelope显式归comparison；READY/Attempt用途只增加保护，不搬为durable。正常cold/restored风险顺序、cap、编号、level过滤与当前closure校验保持，不增统计成功前提。

artifact refs继续不直接进入risk_evaluation_digest；不含ref的内容/manifest与风险事实摘要保持原公式。含新ref的closure、report、cache envelope原bytes/SHA以及消费它们完整性的surface/bundle摘要按实际载荷传递重算。不得放宽closure校验、删除raw SHA输入或复用旧绑定来保旧golden。同盘/分盘配置本身不进入候选key或业务摘要。

## 纯结构变化与后台审计（2026-11-13）

Risk 消费 Comparison v4 的 `comparison.presentation` 统一投影；严格证明共有业务值未变的列增删不输出 schema 风险。其他行风险、诊断及 ordered 语义不删除；未知或只浏览默认零计数不能放行。Risk 文档形状/preimage 不变；comparison digest 已绑定 v4 证据与 standard-reference v3，既有 risk cache/candidate identity 核对该输入，不新增独立版本轴。


## 人工联调业务规则修订（Owner 2026-11-14）

普通新增整表的 TABLE_ADDED 默认等级为 LOW，非首次导入同样适用；其他行级增删改规则不变。
整个改前快照的表集合为空时，导入不产生任何风险标记，比较变化和原始诊断照常发布。
空基线由共享 pair pipeline 根据完整 before.summary.tables 判定，不以单表缺失或筛选后的 task 集合推断。
该事实通过 RiskOptions.empty_baseline 传入；无风险表不补 UNKNOWN，各表仍发布完整的空风险归属供导航消费。

risk-model/v4、ruleset version v4 与 rule version v4 标识本轮规则，规则校验器核对 model，ruleset/evaluation digest 与消费者绑定结果。
empty_baseline 进入已有 options 文档、evaluation digest 和 candidate cache key，防止同一新增表任务在空基线和
增量场景间误用判定。Preview assemble-state v7、History assemble-state v4 由现有 checkpoint decoder 核对，
防止恢复旧风险/导航结果；没有双读或迁移。比较事实与比较缓存不变，继续复用中性比较结果。

本修订属于 C 类可重算派生产物，不改提交、归档或审批事务。规则、空基线、缓存隔离和 Preview/History
贯通由风险与业务投影 focused 测试覆盖；全量及最终容器门禁按 Owner 授权集中后验，不在本包重复执行。

## 共享标准表规则（目标 v8）

Owner 2026-11-16：十类装置测点表的普通修改以非空 `changed_columns` 为证据，风险判定先移除 `dev_addr`；剩余为空不产生测点行风险，仅余 `name`/`description` 为 LOW，其他列沿用原规则。空或不可得的修改列、COUNTS_ONLY 不能推断，保留原风险。`device` 总表的地址变化仍按原规则报告；`device_cfg`、增删、其他表和 Comparison 原始 records、计数、快照不变。规则参数明确十个表，ruleset/rule v9 和 risk-model v6 由规则校验器核对；候选 key 包含按表适用性及 ruleset 摘要，防止重用旧风险。Preview assemble-state v13、History assemble-state v10 由各自 checkpoint 解码器核对，防止恢复旧投影。

`device_st/device_mx/device_co/device_sg/device_sp/device_cnt/device_sn/device_tap/device_other/device_disturb` 与 `device_cfg` 的普通 ROW_ADDED/ROW_DELETED 不生成风险；不影响比较记录、计数、整表增删、结构/降级或有序专项风险。所有普通表和有序表的修改列仅由 name、description 中一个或两个字段组成时发一次 LOW 风险，混合其他字段仍依原修改规则，缺修改列证据不猜 LOW。排除增删在 COUNTS_ONLY 和缺记录兜底前应用；正常空 outcome 为 complete=true。

ROW_ADDED/ROW_DELETED 的冻结 params 各含十一项 `exclude_table:<exact_name>=true`，名称/描述规则适用于所有普通表和有序表；validator 严格核对参数集合和值。单一解析函数为 evaluator 和候选 key 提供按表增删适用性；key 同时包含本表 ordered_tail_bounds。ruleset/rule v8 与 risk-model v5 由规则校验器核对，规则摘要由 RiskEvaluation 和候选核对；不新增身份轴。
