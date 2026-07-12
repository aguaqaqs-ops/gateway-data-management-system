# Comparison Bundle Contract

本文定义 backend vNext 第一版 comparison bundle contract。Bundle 是一个或多个 `ComparisonSurface` 及其 artifacts 的闭合交付单元，可用于前端加载或下载。

旧 `history-comparison-bundle/v1`、`preview-bundle/v2` 和 `workbench-bundle/v1` 中的多 pair 组织、相对路径、snapshot artifact 复用思路可以参考；vNext 第一版不把 preview/upload/submit 绑定语义写入通用 bundle contract。

前后端简化策略见 `../frontend-surface-simplification.md`。Bundle core 只做闭合交付；正式路径不再输出 history workbench legacy sidecar。

## 范围

Comparison bundle 负责：

- 组装一个或多个 `ComparisonSurface`。
- 闭合 surface 引用的 comparison records、risk report、risk annotations、diagnostics 和可选 snapshot table artifacts。
- 提供 bundle manifest、artifact closure manifest 和 bundle digest。
- 支持 flow-specific envelope 在上层引用。

Comparison bundle 不负责：

- 计算 diff、risk 或 surface。
- 读取 SourcePackage、RepositoryRef 或 repository server。
- 写 repository 或推进业务状态。
- 定义 upload/submit/history compare 状态机。
- 定义 ordered diff algorithm。

## 分层

```text
Flow / Operation
  -> BundleAssemblyInput
  -> ComparisonBundle
  -> optional FlowEnvelope
```

规则：

- `ComparisonBundle` 是 flow-neutral derived artifact。
- `FlowEnvelope` 可以保存 upload/history/archive 等业务 metadata，但不改变 surface 内容。
- History compare 2/3 节点由 bundle 持有多个 pair surface；每个 pair surface 仍是完整 directed comparison。

## BundleAssemblyInput

```text
BundleAssemblyInput:
  bundle_contract_version
  bundle_profile:
    SINGLE_PAIR
    MULTI_PAIR
  inputs
  pairs:
    - pair_id
      before_input_index
      current_input_index
      comparison_surface
      surface_artifact_closure
  shared_artifacts optional
  artifact_policy
  ref_scope: BUNDLE_RELATIVE
```

`inputs` 是展示输入，不是 source truth：

```text
BundleInput:
  input_index
  role
  display_name
  display_metadata optional
  snapshot_digest optional
```

规则：

- 第一版 `bundle_profile` 只区分 `SINGLE_PAIR` / `MULTI_PAIR`。
- `inputs` 可以表达节点顺序和展示标题，但不暴露 repository commit hash、host path 或 cache refs。
- Flow 可以在自己的业务 record 中保存真实 source/ref identity。
- Bundle assembly 不根据 input kind 计算 comparison。

## ComparisonBundle

```text
ComparisonBundle:
  bundle_contract_version
  bundle_digest
  bundle_profile
  inputs
  pairs:
    - BundlePair
  table_aliases optional
  summary
  artifact_closure_ref
  diagnostics
```

`BundlePair`：

```text
BundlePair:
  pair_id
  before_input_index
  current_input_index
  surface_ref
  surface_digest
  comparison_digest
  risk_evaluation_digest optional
  summary
```

`bundle_digest` 输入：

- bundle manifest canonical payload。
- pair surface digests。
- artifact closure manifest digest。
- bundle contract version。

不进入 digest：

- bundle id。
- operation id。
- flow id。
- download URL。
- host path。
- generated_at。

## Table Alias Mapping

Bundle 可以携带 summary-driven table alias mapping，用于让前端展示 logical table，同时复用 canonical table records。

```text
TableAliasMapping:
  logical_table_name
  canonical_table_name
  alias_scope: PROVISIONAL_FAST | CANONICAL
  pair_id optional
  diagnostics optional
```

规则：

- `logical_table_name` 是用户看到和选择的业务表名。
- `canonical_table_name` 是 bundle 中实际携带 records / artifacts 的表名。
- 前端打开 alias table 时读取 canonical records，但 UI 仍显示 logical table。
- 发布到 `preview_index.table_aliases` 的 mapping 两端都必须存在于同一 `pair_id` 的
  `preview_index.tables`。比较引擎可以在内部复用空且未变表的 alias；若 surface 隐藏了该表，
  bundle 不得发布该 alias。
- `PROVISIONAL_FAST` 只来自 upload preview / preview cache，不能作为 submit/archive/history 的权威事实。
- `CANONICAL` 只能来自 FINAL summary / repository readback，可被 history compare、archive 和正式 cache 消费。
- Alias mapping 是正式 bundle/display contract，不得包含 host path、cache-local ref、debug registry 或 repository internal ref。

## 建议 Layout

```text
bundle-root/
  manifest.json
  artifact-closure.json
  inputs/
    input-0/
      tables/...
    input-1/
      tables/...
  pairs/
    <pair_id>/
      comparison-surface.json
      tables/
        current/
          <table_id>.parquet
        before/
          <table_id>.parquet
      comparison/
        facts.json
        records/
          <table_id>.records.parquet
          <table_id>.records.manifest.json
      projections/
        forward-channels.json
        secondary-devices.json
        communication-protocols.json
        global-parameters.json
        unparsed-tables.json
      risk/
        risk-evaluation.json
        risk-report.json
        annotations/
          <table_id>.risk-annotations.json
          <table_id>.risk-annotations.manifest.json
        projections/
          <projection_id>.risk-summary.json
      diagnostics/
        ...
```

规则：

- Bundle 内所有 refs 都必须是 bundle-relative。
- Snapshot/input table artifacts 可以跨 pair 复用。
- Upload preview 的 `before_table_ref`、`current_table_ref` 和 `browse_table_ref` 若非空，必须直接指向
  可读取的 Parquet snapshot rows；不得以 JSON descriptor 或 metadata envelope 占位。
- Upload preview 默认只发布单侧 snapshot：current 侧存在时只发布 `current_table_ref`（包括
  unchanged、modified、schema changed 和 degraded）；仅 current 不可用且 before 存在时发布
  `before_table_ref`。两侧均不可用时不发布 row ref。
- `records_ref` 若非空同样必须闭合为 bundle 内 Parquet diff rows，并与其 manifest ref 一起发布。
  Bundle assembler 不得自动生成 descriptor、diff envelope 或其他 metadata 来替代这些 row artifacts。
- Upload preview 的 `preview_index.tables[].diff_artifact_ref` 在正式 vNext 路径中等同于 direct
  Parquet records ref：标准 records 表使用 `CURRENT_INLINE`，ordered records 表使用
  `CURRENT_SLOTTED` 并必须携带 `position_column`。
- Alias member 默认不重复携带 records artifact；closure 只需闭合 canonical table records 和 alias mapping。
- Comparison records、business projections、risk report、risk annotations 和 diagnostics 是 pair 级 artifacts，默认不跨 pair 合并。
- 正式 row records artifact 固定为 Parquet；JSON 只用于 manifest、surface、projection、risk 和 diagnostics 等小型结构化 metadata。
- Layout 是建议，不是 digest 身份；manifest/closure 才是可校验事实。

## Flow Envelope

Flow envelope 是上层业务对象，不属于通用 bundle core。

允许的 envelope：

```text
PreviewComparisonEnvelope
HistoryComparisonEnvelope
ArchiveComparisonEnvelope optional future
```

规则：

- Envelope 可以引用 `bundle_digest`、`bundle_artifact_ref`、operation id、TTL 和权限信息。
- Envelope 可以保存 flow-specific display metadata。
- Envelope 不应改变 `ComparisonSurface` 或 `ComparisonBundle` core payload。
- History compare 不伪装成 preview bundle；preview 的 submit/source binding 不进入 history bundle。

## Artifact Closure

Bundle READY 前必须闭合所有可读取 artifacts：

```text
ComparisonBundleArtifactClosure:
  bundle_manifest_digest
  surfaces
  comparison_records
  business_projections
  risk_reports
  risk_annotations
  diagnostics
  shared_snapshot_artifacts optional
```

规则：

- Bundle 不得引用 cache-local path。
- Cache hit 恢复到 bundle 时必须重写为 bundle-relative refs。
- Closure 缺失时 bundle 不能对外 READY。
- Bundle digest 可以包含 closure manifest digest；closure refs 本身可重写。
- Closure 不闭合 `workbench_manifest.json`、`preview_index.json`、`diff_summary.json` 或其他 legacy sidecar。
- 所有 `ComparisonSurface.tables[].risk_refs.annotation_ref` 与
  `annotation_manifest_ref` 必须在 bundle 内闭合为真实
  `backend-vnext/risk-annotations/v1` content / manifest JSON。`legacy-risk-annotation-sidecar/v1`
  或任何空 placeholder 不能占用 annotation ref。
- `RiskReport.tables` 缺席某个表表示该表没有 annotation；正式/preview 兼容层应将该表风险
  展示为 `risk_level: null`、`annotation_count: 0`，不得因存在 surface 或缺失 source artifact
  合成 `UNKNOWN`。

## Cache 边界

第一版不要求实现 bundle cache。

未来 cache 层：

```text
comparison_surface_cache optional
flow_assembly_cache optional
```

规则：

- `comparison_core_cache` 不缓存 surface/bundle。
- `risk_evaluation_cache` 不缓存 surface/bundle。
- `comparison_surface_cache` 命中后仍需进入当前 operation/bundle artifact closure。
- `flow_assembly_cache` 是 flow-level assembly cache，不是 comparison fact。
- `comparison_surface_cache` 和 `flow_assembly_cache` 是 downstream optional caches，不合并为单一 pair-total cache。

## Ordered Table 预留

第一版 bundle 不理解 ordered diff 语义，只闭合 surface 引用的 artifacts。

`ORDERED_TABLE_COMPARE` contract/capability 第一版已拆出。实现完成后，bundle 需要补充：

- ordered records artifacts。
- ordered diagnostics artifacts。
- ordered risk annotations artifacts。
- pseudo blank interval 和 table processing mode 相关 artifacts/diagnostics。

## 第一版取舍

第一版固定选择：

- Bundle core 是 flow-neutral。
- 多 pair 只在 bundle 层组织，不合并 comparison facts。
- 所有 refs bundle-relative。
- 正式 row records 使用 Parquet；JSONL 不作为正式 row artifact 格式。
- Business projection 作为 pair-local artifact/ref 进入 bundle closure，不塞进 row records。
- 不实现正式 bundle cache。
- Ordered table 只保留 artifact closure 预留。

后续计划：

- Dolt native provider 已有第一版设计；实现和 benchmark 完成后，确认 native records 到 `ComparisonRecords` 的归一化结果。
- Dolt native 只作为 comparison provider；最终仍输出 `ComparisonFacts + ComparisonRecordsClosure`，再进入 surface/bundle。
- Ordered diff contract/capability 已有第一版设计；实现完成后回补 surface ordered extension 和 bundle ordered artifacts。

## 验收标准

- Bundle 不包含 host path、cache-local ref 或 repository internal ref。
- Bundle manifest 可由 artifact closure 完整校验。
- History 2/3 节点可以表达为 1/2 个 pair surface。
- Upload FULL preview 发布 `baseline_to_initial` 与 `initial_to_modified` 两个 pair surface，不做三方 diff。
- Upload preview 的默认 view 是 `initial_to_modified`；`manifest.comparison_surface_ref` 指向该默认 surface 的顶层副本，`preview_index.views[].derived_artifacts.comparison_surface_ref` 指向各自的 `pairs/{pair_id}/comparison-surface.json`。
- Upload preview snapshot、records、risk 和 projection artifact 均为 pair-scoped ref；同名表在不同 pair 中不得共享 `tables/...`、`comparison/records/...` 或 `risk/...` 路径。
- Ordered unsupported bundle 仍可 READY，并提供 review-required risk/diagnostics。
