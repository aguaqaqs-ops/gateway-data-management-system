# Risk Evaluation Capability

本文定义 `Risk Contract` 的第一版实现设计。Contract 见 `../contracts/risk.md`；本文描述 capability 边界、模块拆分、旧实现参考、artifact/cache 接入点和验收标准。

Risk evaluation 是 flow-neutral capability。它不判断自己服务 upload、submit、history compare 还是 archive；它只消费 `ComparisonFacts`、可选 comparison records access 和调用方传入的 `RiskRulesetSnapshot`。

## 设计原则

规则：

- Flow 负责选择 risk ruleset、artifact policy、cache policy 和展示/审核策略。
- Capability 负责从 `ComparisonFacts` 派生 `RiskFacts`，执行 risk rules，输出 `RiskEvaluation`。
- Capability 不读取或修改 Workspace、Submission、Preview、History request 等业务状态。
- Capability 不读取 SourcePackage、SqlDumpSource、RepositoryRef 或 repository server。
- Capability 不执行 comparison compute。
- Capability 不组装 ComparisonSurface 或 WorkbenchBundle。
- 同一输入、版本、ruleset 和 options 下，重复 evaluation 必须得到相同 `risk_evaluation_digest`。

## 落地约定

为避免过度设计，第一版明确收敛为以下语义：

- `ComparisonFacts` 是 risk capability 的主输入，不再回到 diff compute 层取数。
- `ComparisonRecordsClosure` 是 risk core 里唯一的逻辑 records handle。
- 如果上层边界拿到的是 `ComparisonRecordsClosureArtifact`，应先在调用方归一化为 `ComparisonRecordsClosure`，再构造 `RiskEvaluationInput`。
- `records_access` 保持为一个很薄的同步 protocol，第一版提供 `get_records_closure()` 和 `get_ordered_records(table_name)`，前者返回逻辑 `ComparisonRecordsClosure`，后者返回 ordered records evidence。
- ordered unsupported 只输出 `UNKNOWN + ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED`，不回退成 ordered semantic risk。

本轮收尾说明：

- `risk_evaluation` 已收敛为只产出 risk evaluation / report / annotation artifact。
- `operation artifact closure`、surface assembly 和 bundle assembly 统一留到后续步骤实现，不再在本轮扩展。

## 旧实现参考边界

旧实现可参考：

- `RiskLevel` 等级形状。
- `RiskTarget` / `RiskReason` / `RiskAnnotation` / `RiskReport` 的对象形状。
- `RiskRuleRegistry`、`rule_id`、`export_model`、`ruleset_hash` 思路。
- standard / structural / ordered basic rules 的业务语义和测试样例。
- highest-risk aggregation 规则。

不直接继承：

- 旧 `RiskEngine` 消费 `TableCompareResult`；vNext 消费 `ComparisonFacts`。
- 旧 risk contract import `compare` enum；vNext risk contract 独立于旧 compare。
- `PreviewBundleContext`、sidebar projection、surface refs、workbench bundle 不进入 risk core。
- ordered diff 算法不在 risk capability 中定义。

## Legacy Simplification Strategy

Risk evaluation 也采用 vNext 简化策略：旧实现是业务语义和测试样本来源，不是输入输出 contract 来源。

第一版保留旧语义：

- Risk level ordering and aggregation。
- Table added/deleted、schema changed、row added/deleted/modified。
- Degraded / unknown review-required path。
- Rule registry、rule id、ruleset digest。
- Risk annotations with stable target and reason code。

第一版删除旧耦合：

- 不消费旧 compare result object。
- 不输出 sidebar projection。
- 不输出 Workbench-specific risk payload。
- 不把 preview/history/workbench context 写入 risk result。
- 不把 risk refs 或 artifact paths 写入 digest。

实现建议：

- `facts_extractor` 是旧 compare result 到 vNext `ComparisonFacts` 的分界线之后的模块，不处理旧对象。
- `aggregation` 只做 risk summary，不生成前端导航。
- `artifacts` 只写 risk annotation artifacts，不写 surface/bundle 文件。
- 旧 Workbench 需要的 risk-only navigation 由 surface/frontend/adapter 从 `RiskReport` 和 annotation artifacts 派生。

Coverage tests 应验证旧用户可见能力不丢，而不是验证旧 payload shape 不变。

建议 coverage：

| Case | 期望 |
| --- | --- |
| table added | table-level annotation + configured risk level |
| table deleted | table-level annotation + configured risk level |
| schema changed | table-level schema risk |
| row added/deleted/modified | row or row-pair annotation |
| ignored column only | 默认无 row risk |
| business equivalent | 默认无 risk annotation |
| duplicate/missing key | `UNKNOWN` degraded risk |
| comparison failed | `HIGH` comparison/table risk |
| ordered unsupported | `UNKNOWN` + `ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED` |
| many annotations | annotation artifact + RiskReport summary/ref |

## 能力列表

```text
risk_evaluation
risk_facts_extraction
risk_rule_evaluation
risk_report_aggregation
risk_annotation_artifact
risk_evaluation_cache optional future
```

## 建议代码模块

建议落点：

```text
gateway-data-management-system/backend/backend_vnext/capabilities/risk_evaluation/
```

内部拆分：

```text
models.py
ruleset_contract.py
facts_extractor.py
engine.py
rule_registry.py
aggregation.py
artifacts.py
versions.py
rules/
  structural.py
  standard_basic.py
  degraded.py
  ordered_placeholder.py
  ordered.py
```

职责：

| Module | 职责 |
| --- | --- |
| `models` | RiskEvaluationInput、RiskFacts、RiskAnnotation、RiskReport 等模型。 |
| `ruleset_contract` | RiskRulesetSnapshot 和 ruleset digest。 |
| `facts_extractor` | 从 ComparisonFacts 派生 RiskFacts。 |
| `engine` | 执行 rules、聚合结果、输出 RiskEvaluation。 |
| `rule_registry` | rule 注册、选择、导出 model。 |
| `aggregation` | highest risk、reason code 合并、annotation summary。 |
| `artifacts` | annotation artifact 写入、manifest 以及落盘/恢复 helper。 |
| `rules` | structural、standard、degraded、ordered basic 和 ordered placeholder 规则集。 |

规则：

- `ordered_placeholder` 用于 ordered provider missing/degraded，输出 review-required unknown。
- `ordered_basic` 负责 ordered provider 接入后的 tail / middle / move 风险分级。

依赖方向：

```text
risk_evaluation
  -> contracts.comparison / contracts.risk
  -> artifacts
  -> core
```

禁止 risk_evaluation 依赖 flow、operation、repository_import、repository_server、comparison_surface、workbench 或旧业务模块。

## 输入输出

输入：

```text
RiskEvaluationInput:
  comparison_facts
  records_access optional
  risk_ruleset
  risk_contract_version
  risk_model_version
  requested_tables optional
  risk_options
  artifact_policy
  cache_policy optional
```

输出：

```text
RiskEvaluationResult:
  risk_evaluation
  risk_report
  annotation_artifacts optional
  cache_diagnostics optional
  diagnostics
```

规则：

- `records_access` 必须来自已经闭合的 operation-local comparison records closure，或来自经过 restore 的 cache closure。
- 如果边界拿到的是 `ComparisonRecordsClosureArtifact`，先归一化为逻辑 `ComparisonRecordsClosure` 再进入 core。
- 第一版默认不读取 full records；只有规则需要 changed columns/evidence 时才读取。
- artifact refs 不进入 digest。

## Risk Facts Extraction

第一版从 `ComparisonTableFact` 派生：

```text
table status
schema_changes
row_counts
records_ref / records_manifest_digest
degraded diagnostics
comparison diagnostics
```

映射：

| Comparison 输入 | Risk scope |
| --- | --- |
| `ADDED_TABLE` / `DELETED_TABLE` | `TABLE` |
| `SCHEMA_CHANGED` / `SCHEMA_ONLY_CHANGED` | `TABLE` |
| row added/deleted/modified counts | `STANDARD_ROWS` |
| duplicate key / missing key / key changed | `DEGRADED_TABLE` |
| ordered unsupported/degraded | `DEGRADED_TABLE` |

规则：

- `BUSINESS_EQUIVALENT` 默认不产生风险 annotation。
- ignored columns 默认不产生 row risk。
- comparison failed 产生 comparison/table level high risk。
- table-level degraded 不阻塞其他表 risk evaluation。

## Rule Evaluation

第一版规则建议：

```text
StructuralTableRiskRule
StandardRowRiskRule
DegradedTableRiskRule
OrderedUnsupportedRiskRule
```

默认等级：

```text
TABLE_ADDED -> MEDIUM_LOW
TABLE_DELETED -> MEDIUM_HIGH
SCHEMA_CHANGED -> MEDIUM_HIGH
ROW_ADDED -> MEDIUM_LOW
ROW_DELETED -> MEDIUM_LOW
ROW_MODIFIED -> MEDIUM_HIGH
KEY_DEGRADED -> UNKNOWN
ORDERED_DIFF_UNSUPPORTED -> UNKNOWN
COMPARISON_FAILED -> HIGH
```

派生表例外：`composite_signal_point` 不套用标准逐行风险。只要存在可见 ADD/DELETE/UPDATE，就输出一个表级 `UNKNOWN + COMPOSITE_SIGNAL_CHANGE_REVIEW_REQUIRED`，evidence 汇总各类计数；公式更新不升级风险等级。该 UNKNOWN 仅参与既有聚合，不增加确认或阻断工作流。原始 `device_*` 风险规则保持不变。

规则：

- 默认等级可以被 `RiskRulesetSnapshot` 参数覆盖。
- 每条 annotation 至少有一个 stable `reason_code`。
- 未被任何规则覆盖但存在 change target 时，输出 `UNKNOWN`，不静默丢弃。

## Annotation Artifacts

第一版：

- 小结果可以内联 annotation summary。
- 大量 row-level annotations 写入 artifact。
- `RiskReport` 保留 annotation refs 和 table summary。

建议 layout：

```text
risk/
  risk-evaluation.json
  risk-report.json
  annotations/
    <table>.risk-annotations.json
    <table>.risk-annotations.manifest.json
```

规则：

- annotation artifact manifest digest 可以进入 `risk_evaluation_digest`。
- annotation ref 不进入 digest。
- operation READY 前，如果 RiskReport 引用 annotation artifacts，必须进入 operation artifact closure。

## Cache 接入点

第一版可以先不实现正式 `risk_evaluation_cache`，但保留接口和 diagnostics。

未来 cache key：

```text
comparison_digest
risk_contract_version
risk_model_version
risk_ruleset_digest
risk_options
annotation_artifact_contract_version
```

规则：

- risk cache 不缓存 ComparisonSurface 或 WorkbenchBundle。
- comparison core cache hit 不等于 risk cache hit。
- risk cache hit 仍需校验 annotation artifact manifest/content digest。

## Ordered Table 第一版策略

Risk capability 不实现 ordered diff algorithm；ordered semantic facts 来自 `ORDERED_TABLE_COMPARE`。旧 ordered risk 映射见 `../contracts/ordered-diff.md`。

当 `ComparisonFacts` 标记 ordered table unsupported/degraded：

```text
risk_level: UNKNOWN
reason_code: ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED
target_type: TABLE
```

规则：

- 不把普通 key-based fallback 伪装成 ordered semantic risk。
- provider degraded 时不生成 move、position、interval annotation。
- `ORDERED_TABLE_COMPARE` provider 接入后，第一版按旧 tail/middle/move 风险分级恢复 ordered basic risk。

ordered provider 接入后的默认 reason codes：

| Reason code | 默认风险 |
| --- | --- |
| `ORDERED_REPLACEMENT` | `MEDIUM_LOW` |
| `ORDERED_MOVE` | `MEDIUM_HIGH` |
| `ORDERED_MIDDLE_INSERT_DELETE` | `MEDIUM_HIGH` |
| `ORDERED_MIDDLE_BLANK_INTERVAL` | `MEDIUM_HIGH` |
| `ORDERED_TAIL_INSERT_DELETE` | `LOW` |
| `ORDERED_TAIL_BLANK_INTERVAL` | `LOW` |
| `ORDERED_NAME_UPDATE` | `LOW` |
| `ORDERED_CONTENT_UPDATE` | `MEDIUM_LOW` |
| `ORDERED_RISK_UNKNOWN` | `UNKNOWN` |

## 第一版取舍与后续演进

第一版固定选择：

- Risk capability 输入为 `ComparisonFacts`。
- 默认基于 table facts、row counts、schema changes、ordered records 和 degraded diagnostics。
- records artifacts 只在 ordered 或 evidence 需要时读取。
- RiskReport 不包含 front-end layout。
- ordered provider 未接入或 degraded 时只输出 ordered unsupported review-required 风险；provider 接入后恢复旧 ordered basic risk。
- 不实现 risk cache，只保留 future key 边界。

后续可能变化：

- ordered table diff provider 完成后补充 ordered semantic facts/rules，关闭 legacy mapping 中的 P1 parity 项。
- 增加 `ROW_INTERVAL`、move、position change risk，并恢复旧 tail/middle/move 分级。
- 增加 risk evaluation cache。
- 增加更细的业务表/字段级 ruleset。
- 增加 surface/bundle 对 risk artifacts 的展示映射。

## 测试与验收

Unit：

- risk level aggregation。
- ruleset digest 稳定。
- comparison table status 到 risk facts 的映射。
- degraded table 输出 review-required risk。
- ordered unsupported 不输出 LOW。

Contract：

- 同一输入得到同一 `risk_evaluation_digest`。
- risk capability 不 import 旧业务模块。
- RiskReport 不包含 full records。
- annotation artifact manifest digest 可复验。

Integration：

- ComparisonFacts -> RiskEvaluation -> RiskReport。
- 大量 annotations 落 artifact。
- ordered unsupported path 输出 `ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED`。
