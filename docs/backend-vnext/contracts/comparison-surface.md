# Comparison Surface Contract

<a id="be-b-v4实施中"></a>

## 当前版本 v4

当前 selector 为 `backend-vnext/comparison-surface/v4`；只接受该版本。本文与 `surface_assembly/contracts.py` 共同定义当前载荷。验收状态与产物来源由 BE-b 交付记录说明，Contract 版本不代表阶段已退出。

- 每个成功 surface 恰一个 BUSINESS_NAVIGATION projection，完整载荷/FE-BEB-11–13 语义由 [Business Navigation Contract](business-navigation.md) 拥有；缺失/重复拒绝。surface 仍不读表或计算 diff/risk。
- 普通 columns 为两侧 canonical 列名并集，每名一个，数组按 UTF-8 名序；新增 required `present_in:BEFORE|CURRENT|BOTH`、`pinned:bool`、`display_order:int`。展示顺序从 0 连续唯一：current 业务规则/DDL 次序，再 before-only DDL 次序；没有 current 时取 before。类型/nullable 优先 current，否则 before；名称 current 非空注释→before 非空注释→标识符。固定列规则 no、name，否则 description；宽度/对齐归前端，无隐藏或缺字段回退。
- replacement_summary.before/current 的列按本侧独立连续 display_order 与本侧 present_in（BEFORE/CURRENT），各侧 summary 新增 required display_name，取本侧注释或标识符；顶层并集仅总览使用，不替代分侧标题。
- SurfaceTable 增加 nullable `row_locator_ref` 和 required `table_content_bindings={before,current,browse}`。每项 nullable，并与对应 table_ref 同 null；非 null 为 `{business_schema_digest,raw_content_digest,row_count,source_schema_digest,canonical_schema_digest,storage_rule_digest,storage_projection_version}`。语义与已有 owner 相同，不新增行摘要。source_schema_digest 保持现有 compare schema 含义，完整类型/DDL 序由 canonical_schema_digest 绑定。同 ref 的 binding 必须相容。
- v4 semantic preimage 用 table_content_bindings 取代表文件 raw SHA/size，整个 locator ref 排除；诊断/view_id 的既有排除和其他 records/risk/projection 摘要规则不变。表/locator raw 完整性仍由 refs/bundle closure 保护。后端 surface golden 验证重排/改写不变性；前端只核形状、ref/binding 同 null 及 surface ref 与 closure raw SHA/size 一致，不重算 surface_digest。
- pair/view ID：Preview FULL 为 baseline_to_initial、initial_to_modified，MODIFIED_ONLY 仅实际 pair；History 两节点 left_to_right，三节点 left_to_middle、middle_to_right。pair_id 不拼 operation ID；同 bundle view_id 唯一，无旧别名。
- surface diagnostics_summary 仅稳定码；完整 emit 替换表见 [稳定编码](presentation-diagnostic-codes.md)，不包含异常全文或 pair 失败/取消原文。比较/风险业务算法不因编码替换改变。

行定位、双侧浏览及 ref 生命周期由 [Bundle Contract](comparison-bundle.md#be-b-v4实施中) 约束；无记录行不能仅凭 EXACT、null locator 或 replay_guarantee 造 before，完整前提见 [Business Navigation](business-navigation.md#无记录行与完整性fe-beb-12)。

Surface 是面向前端和 Workbench 的 flow-neutral 展示结构：只消费 comparison/risk 已完成事实和 artifact refs，不计算 diff/risk，不承载 upload、submit 或 history compare 的业务绑定语义。

前后端简化策略见 `../frontend-surface-simplification.md`。Surface 保持 thin index；业务导航通过正式 projection artifacts 表达，不通过前端表名猜测实现。

## 范围

Comparison surface 负责：

- 表达一个 directed pair/view 的展示入口。
- 提供表清单、表级状态、统计、展示策略和 artifact refs。
- 引用恰一份 BUSINESS_NAVIGATION projection 及可选的导航诊断。
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
  -> BundleAssembly / API response / formal bundle loader
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
  ref_scope:
    OPERATION_RELATIVE | BUNDLE_RELATIVE
```

规则：

- Workbench read-only 属于前端 formal bundle loader 的消费方式，不进入 surface core。
- Surface 没有通用 options 容器；新增稳定语义必须进入显式类型字段和 contract version。
- `surface_contract_version` 由 capability 当前版本常量固定，调用方不能覆盖。
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
  comparison_mode
  project_identity_status optional
  project_identity_assessment_ref/digest optional
  requires_submit_confirmation
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
- `comparison_mode`、project identity status、assessment digest 和 submit confirmation requirement。
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
- 同一个 bundle/API payload 内的 `view_id` 必须唯一。History compare 不得发布多个
  `before_to_current` generic view；2 节点使用 `left_to_right`，3 节点使用
  `left_to_middle` / `middle_to_right`。
- Label 是展示辅助，不参与 comparison/risk identity。
- History compare 的 `left_to_right`、`left_to_middle`、`middle_to_right` 属于 bundle 层 pair id，
  应映射为 surface `view_id`，并通过 `display_before_role` / `display_current_role` 暴露
  `left` / `middle` / `right` 展示角色。

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
  columns: SurfaceColumn[]
  table_refs
  table_content_bindings: {before,current,browse}
  row_locator_ref nullable
  records_refs
  risk_refs
  display
  compare
  diagnostics
  ordered_extension optional
```

`schema_summary`：

```text
SchemaSummary:
  before_only_columns
  current_only_columns
  selected_columns
  effective_compare_key_before
  effective_compare_key_current
  effective_compare_key_changed
  incompatible_columns
  schema_evolution: NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE
```

`SurfaceProjectionRef`：

```text
SurfaceProjectionRef:
  projection_id
  projection_kind:
    BUSINESS_NAVIGATION
  projection_ref
  projection_digest
  projection_summary
  risk_summary_ref optional
  diagnostics_ref optional
```

`change_kind`：

```text
UNCHANGED
BUSINESS_EQUIVALENT
ADDED
DELETED
UPDATED
SCHEMA_CHANGED
DEGRADED
FAILED
REPLACED
```

规则：

- `change_kind` 从 `ComparisonTableFact` 派生，不由 surface 自行推断。
- `table_id` 是 records/risk/diagnostics refs 和前端 cache key 的稳定表身份；`table_name` 是展示和业务识别用的 normalized table name。
- Business identity 如 `dev_addr`、`gid`、`board/link` 属于 projection artifact；compare key 属于 comparison/table rules 和 diagnostics。
- `BUSINESS_EQUIVALENT` 可展示为业务无变化，但 diagnostics 必须保留 raw/projection basis。
- `FAILED` 或 `DEGRADED` 表必须保留 review/diagnostics 入口。
- `ADDED_TABLE` 使用 `TABLE_BROWSE` 并通过 `current_table_ref` 浏览新增表；`DELETED_TABLE` 使用 `TABLE_BROWSE` 并通过 `before_table_ref` 浏览删除表。两者不依赖逐行 records。
- `schema_evolution=COLUMNS_ADDED` 保留分类，但 `current_only_columns` 为空，surface 不向 Preview、Submission 或 History 展示新增列清单。
- Ordered records、blank 与区间展示沿 [Ordered Table Compare](../capabilities/ordered-diff-compute.md)，不交给 standard row locator。

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
- backend `ArtifactRef` 统一严格校验 `a1:<location>:<64 lowercase hex>`；不再用旧字符串前缀推断 cache/flow 身份。合法 opaque ref 的 location 只定位逻辑 root，不代表授权或可交付性；cache 恢复后的正式 ref 仍由原 operation/bundle scope、完整 closure 和 READY owner 负责，不把 cache key/path 放入四字段 ref。
- `records_ref` 不进入 `comparison_digest`；surface/bundle restore 可以重写。
- 跨 operation snapshot Parquet export cache 的键为 repository scope、`row_layout_digest` 与
  Parquet writer contract version；
  `fast_candidate_key` 不得出现在 surface refs 中，也不得作为持久 cache identity。它只服务于
  同次 snapshot ref dedupe、cross-pair shared refs 和性能估算。
- 如果 surface 暴露 records/risk refs，operation READY 前必须有完整 artifact closure。
- `risk_refs.annotation_ref` 是表级 risk annotation sidecar 的 canonical ref；前端可用它把
  ROW / ROW_PAIR / ROW_INTERVAL annotation 覆盖到具体行。只有 summary/table 级 annotation
  且缺少 row identity/position 时，前端应展示表级风险，不得伪造具体行级样式。
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
    REPLACEMENT_SIDE_BY_SIDE
  table_processing_mode:
    STANDARD
    SCHEMA_ONLY
    DEGRADED
    DATASET_REPLACEMENT
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

Dataset Replacement table 额外发布：

```text
replacement_summary:
  before:                         # 该侧无表时为 null
    row_count
    display_name
    columns[]:
      name
      display_name
      scalar_type optional
      nullable optional
      pinned
      display_order
      present_in: BEFORE
  current:                        # 结构同 before；该侧无表时为 null
```

`replacement_summary` 只允许出现在 `table_processing_mode=DATASET_REPLACEMENT` 的表；它是前端在不解码全量 Parquet 的情况下展示双侧存在性、行数和 schema 差异的权威来源。存在空表必须发布非 null side 且 `row_count=0`，不得与缺表混淆。replacement 表格不得消费 records/risk annotations 构造行级 diff。

## Ordered 与缓存边界

Surface 不定义 ordered 算法。它消费已发布的 `ordered_extension`、ordered records 与风险；真实降级展示 DEGRADED_NOTICE，不把普通 key-based diff 当 ordered diff。`ordered_extension.ordered_records_ref` 必须由 ordered decoder 消费，current snapshot 存在时按 CURRENT_SLOTTED 浏览。没有 records 时只展示 SUMMARY_ONLY，不表示 artifact 读取失败。标准五列 locator 不替代 ordered position/blank 语义。

Surface 不包含 flow state，不新增 surface cache。Snapshot Parquet cache 和计算缓存命中后仍进入当前 operation 的 ref/closure/READY/protection；cache key、路径及宿主标识不进入载荷。

## 语义摘要与 raw 完整性

`surface_digest_payload` 是 v4 的唯一 preimage owner。它保留 `table_content_bindings`、columns/presentation、comparison/risk identity、records/risk/projection integrity；排除 surface_id、view_id/label、diagnostics 与 diagnostics_count、全部 table refs 和整个 row_locator_ref。其他 ref 以 `{raw_sha256,size_bytes}` 参与，不按 artifact_id 或存储位置散列。

因此重排行文件或重编码、重写 locator 不改变 v4 surface 摘要；更换 records/risk/projection 的实际字节仍可能改变摘要。所有实际物理表和 locator 必须由 raw ref 与 bundle closure 严格校验，不能把 semantic digest 当 raw 校验。后端 golden 固定 preimage、digest 与物理改写不变量；前端校验当前形状、双侧 metadata、ref/binding 同 null 和 closure raw 一致性，不重算 surface_digest。

`rewrite_surface_refs` 只重写已验证的 opaque ArtifactRef。仅 ref ID/location 变化保持摘要；若嵌套 records/risk JSON 的 raw bytes 改变，assembler 按 owner 重新计算，不能为了保旧 golden 删除 integrity 输入。

## 验收标准

- Surface assembly 不 import 旧业务模块。
- Surface 不包含 preview token、submit binding、workspace/history state、host path 或 cache ref。
- 同一 comparison/risk/artifact manifest 输入得到稳定 `surface_digest`。
- 所有 refs 都可被 operation/bundle closure 重写。
- Degraded/unsupported 表有可展示诊断入口。
- Ordered unsupported 不被展示成普通 semantic diff。

## 实现与验证

公共类型在 `gateway_backend.capabilities.surface_assembly.contracts`。`SurfaceAssemblyResult` 仅 READY 携带 surface。`test_surface_contracts.py`、`test_surface_assembly.py` 和后端 presentation golden 分别拥有 shape/ref、语义与互通。导航完整性与缺快照上下文以 Business Navigation/Row Location owning Contract 为准，不复制一套算法。
