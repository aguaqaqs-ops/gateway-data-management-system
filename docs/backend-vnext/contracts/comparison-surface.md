# Comparison Surface Contract

本文定义 backend vNext 第一版 `ComparisonSurface` contract。Surface 是面向前端和 Workbench 的 flow-neutral 展示结构：它消费 comparison/risk 的已完成事实和 artifact refs，不计算 diff，不计算 risk，不承载 upload、submit 或 history compare 的业务绑定语义。

旧 `docs/shared-contracts/comparison-surface.md`、`comparison_surface/contracts.py` 和 preview bundle builder 中的相对路径、表级展示、risk refs、diagnostics refs 思路可作为 UX/展示语义参考；vNext contract 不继承旧模块依赖、preview identity、host path、cache ref 或 Workbench context。

前后端简化策略见 `../frontend-surface-simplification.md`。第一版 surface 应保持 thin index；业务导航通过正式 projection artifacts 表达，不通过旧 Workbench adapter 或前端表名猜测实现。

## 范围

Comparison surface 负责：

- 表达一个 directed pair/view 的展示入口。
- 提供表清单、表级状态、统计、展示策略和 artifact refs。
- 引用业务 projection artifacts，例如转发通道、二次装置、通讯规约、全局参数和未解析表。
- 引用 `ComparisonFacts`、`ComparisonRecordsClosure`、`RiskReport`、`RiskAnnotationArtifact`、diagnostics artifacts。
- 为 bundle assembly 和前端只读浏览提供稳定输入。

Comparison surface 不负责：

- 计算 comparison facts 或 records。
- 计算 risk。
- 读取 SnapshotTable、SourcePackage、RepositoryRef 或 repository server。
- 写 repository 或推进业务状态。
- 组装 bundle tar/zip。
- 定义 ordered diff algorithm。
- 携带 preview token、submit binding、workspace state、history request state、host path 或 cache-local ref。

## 对象链路

```text
ComparisonFacts
  + ComparisonRecordsClosure optional
  + RiskReport optional
  + RiskAnnotationArtifact optional
  + diagnostics artifacts optional
  -> ComparisonSurfaceAssemblyInput
  -> ComparisonSurface
  -> BundleAssembly / API response / Workbench adapter
```

规则：

- 一个 `ComparisonSurface` 只表达一个 directed pair/view。
- 多节点 history compare 由 bundle 层持有多个 surface，不在一个 surface 内合并多段 comparison。
- Surface 可以引用 artifacts，但 artifact refs 必须可被 operation/bundle closure 重写。
- Surface 输出必须 flow-neutral；flow identity 只能作为上层 bundle/operation metadata。

## ComparisonSurfaceAssemblyInput

```text
ComparisonSurfaceAssemblyInput:
  comparison_facts
  records_closure optional
  risk_report optional
  risk_annotation_closure optional
  table_artifact_index optional
  diagnostics_refs optional
  surface_contract_version
  surface_profile
  surface_options
  ref_scope:
    OPERATION_RELATIVE | BUNDLE_RELATIVE
```

`surface_profile` 第一版：

```text
STANDARD_TABLE_BROWSER
```

规则：

- 第一版只实现 `STANDARD_TABLE_BROWSER`。
- Workbench read-only 属于前端 formal bundle loader 的消费方式，不进入 surface core profile。
- `surface_options` 进入 `surface_digest`。
- operation id、workspace id、submission id、history request id、download URL、host path 不进入 digest。
- `ref_scope` 只影响 ref 写法，不改变 facts digest。

## ComparisonSurface

```text
ComparisonSurface:
  surface_contract_version
  surface_digest
  surface_id
  direction
  comparison_digest
  risk_evaluation_digest optional
  view
  tables:
    - SurfaceTable
  projections:
    - SurfaceProjectionRef
  summary
  refs
  diagnostics
  reserved_extensions optional
```

`surface_digest` 输入：

- `comparison_digest`。
- `risk_evaluation_digest`，如果存在。
- `surface_contract_version`。
- `surface_profile`。
- `surface_options`。
- 表级 surface semantic payload。
- 被引用 artifact 的 manifest/content digest。

不进入 digest：

- surface id。
- operation id。
- bundle id。
- workspace/submission/history request id。
- download URL。
- host path。
- operation-local 或 bundle-local ref 字符串。
- generated_at。

## SurfaceView

```text
SurfaceView:
  view_id
  label optional
  before_role
  current_role
  table_count
  changed_table_count
  degraded_table_count
  risk_level optional
  diagnostics_summary optional
```

规则：

- `view_id` 是 bundle/API 内的局部展示 ID，不是业务 ID。
- Label 是展示辅助，不参与 comparison/risk identity。
- History compare 的 `left_to_right`、`left_to_middle`、`middle_to_right` 属于 bundle 层 pair id，可映射为 surface `view_id`。

## SurfaceTable

```text
SurfaceTable:
  table_id
  table_name
  display_name
  table_status
  change_kind
  row_count
  row_change_stats
  schema_summary optional
  columns optional
  table_refs
  records_refs
  risk_refs
  display
  compare
  diagnostics
  ordered_extension optional
```

`SurfaceProjectionRef`：

```text
SurfaceProjectionRef:
  projection_id
  projection_kind:
    FORWARD_CHANNELS
    SECONDARY_DEVICES
    COMMUNICATION_PROTOCOLS
    GLOBAL_PARAMETERS
    UNPARSED_TABLES
  projection_ref
  projection_digest
  projection_summary
  risk_summary_ref optional
  diagnostics_ref optional
```

`change_kind` 第一版建议：

```text
UNCHANGED
BUSINESS_EQUIVALENT
ADDED
DELETED
UPDATED
SCHEMA_CHANGED
DEGRADED
FAILED
```

规则：

- `change_kind` 从 `ComparisonTableFact` 派生，不由 surface 自行推断。
- `table_id` 是 records/risk/diagnostics refs 和前端 cache key 的稳定表身份；`table_name` 是展示和业务识别用的 normalized table name。
- Business identity 如 `dev_addr`、`gid`、`board/link` 属于 projection artifact；compare key 属于 comparison/table rules 和 diagnostics。
- `BUSINESS_EQUIVALENT` 可展示为业务无变化，但 diagnostics 必须保留 raw/projection basis。
- `FAILED` 或 `DEGRADED` 表必须保留 review/diagnostics 入口。
- 第一版不为 ordered table 生成 move/interval 展示，只表达 degraded/unsupported 或普通表结果。

## Refs

```text
table_refs:
  before_table_ref optional
  current_table_ref optional
  browse_table_ref optional

records_refs:
  records_ref optional
  records_manifest_ref optional
  records_format:
    PARQUET | INLINE_SUMMARY

risk_refs:
  report_ref optional
  annotation_ref optional
  annotation_manifest_ref optional

diagnostics:
  diagnostics_ref optional
  diagnostics_summary optional
```

规则：

- 所有 `*_ref` 必须是 operation-relative 或 bundle-relative logical ref。
- 不允许 host path、cache-local path、repository ref、commit hash 或 Dolt internal path。
- `records_ref` 不进入 `comparison_digest`；surface/bundle restore 可以重写。
- 如果 surface 暴露 records/risk refs，operation READY 前必须有完整 artifact closure。
- `PARQUET` 是正式 row diff artifact 格式；`INLINE_SUMMARY` 只用于无 row records 的 summary-only/degraded/schema-only 表。
- JSONL 不作为正式 row artifact 格式。

## Display 与 Compare Metadata

```text
display:
  strategy:
    SUMMARY_ONLY
    TABLE_BROWSE
    RECORDS_ONLY
    CURRENT_WITH_RECORDS
    DEGRADED_NOTICE
  table_processing_mode:
    STANDARD
    SCHEMA_ONLY
    DEGRADED
  replay_guarantee:
    EXACT
    SUMMARY_ONLY
    UNSUPPORTED

compare:
  artifact_scope
  compare_key_columns
  ignored_columns
  effective_columns
  projection_schema_digest optional
  projection_logical_digest optional
  provider optional
```

规则：

- `display` 只描述前端如何浏览已存在 artifacts，不触发后端计算。
- `compare` 是 diagnostics/解释层信息，不是 ruleset 选择入口。
- ignored columns 不生成 row risk；如需展示，作为 diagnostics/notice。

## Ordered Table 第一版策略

Surface contract 不定义 ordered diff algorithm。第一版只消费 ordered provider 已产出的事实；如果 ordered provider 未接入或 ordered 结果发生真实降级，surface 直接展示 `DEGRADED` / `DEGRADED_NOTICE`，不再保留旧的 ordered 占位值。

预留字段：

```text
ordered_extension:
  ordered_contract_version
  ordered_summary optional
  ordered_records_ref optional
  ordered_records_manifest_ref optional
  ordered_display_mode optional
  table_processing_mode optional
  ordered_preprocess_applied optional
```

第一版策略：

- ordered provider 未实现时，surface 使用 `DEGRADED` / `DEGRADED_NOTICE`。
- risk 使用 `ORDERED_DIFF_UNSUPPORTED_REVIEW_REQUIRED`。
- 不把普通 key-based diff 伪装成 ordered semantic diff。

后续 `ORDERED_TABLE_COMPARE` 完成后，需要补充：

- ordered records contract。
- move/position/interval summary。
- `ROW_INTERVAL` risk target 映射。
- ordered table 前端导航和风险定位规则。
- `ORDERED_TAIL_SEGMENT`、`ORDERED_LOCAL_PATCH`、`ORDERED_SHIFT_REPAIRED`、`ORDERED_REORDER_COMPLEX`、`DEGRADED` 的展示策略。
- pseudo blank interval 的展示与定位。

## 第一版取舍

第一版固定选择：

- Surface 输入为 `ComparisonFacts + optional RecordsClosure + optional RiskReport`。
- 普通表按 table/row/schema summary 输出。
- Row records 不内联到 surface。
- Surface 不包含 flow state。
- Surface 不实现 cache，只保留 digest 和 future cache key 边界。
- Ordered table 只预留 extension，不展开语义。

后续可能变化：

- Dolt native provider 已有第一版设计；实现和 benchmark 完成后，确认 native records 如何映射到 `ComparisonRecords`，surface contract 不直接消费 Dolt native raw output。
- Ordered diff contract/capability 已有第一版设计；实现完成后，补充 ordered extension。
- 增加 surface cache。
- 增加更细的分页索引、列视图和前端筛选 manifest。

## 验收标准

- Surface assembly 不 import 旧业务模块。
- Surface 不包含 preview token、submit binding、workspace/history state、host path 或 cache ref。
- 同一 comparison/risk/artifact manifest 输入得到稳定 `surface_digest`。
- 所有 refs 都可被 operation/bundle closure 重写。
- Degraded/unsupported 表有可展示诊断入口。
- Ordered unsupported 不被展示成普通 semantic diff。
