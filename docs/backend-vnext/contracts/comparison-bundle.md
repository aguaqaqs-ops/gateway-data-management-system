# Comparison Bundle Contract

> comparison-bundle v2 / preview-bundle v3 加入逐 pair identity assessment artifact、顶层 assessment-set digest 与 replacement confirmation requirement。comparison-bundle v3 将 Preview/History 的完整表数据闭合为 Parquet 并按 layout 与 writer 版本复用导出。只支持当前合同；历史产物需重新生成。详见 `../capabilities/project-identity-and-dataset-replacement.md`。

本文定义 backend vNext 第一版 comparison bundle contract。Bundle 是一个或多个 `ComparisonSurface` 及其 artifacts 的闭合交付单元，可用于前端加载或下载。

前后端简化策略见 `../frontend-surface-simplification.md`。Bundle core 只做闭合交付；preview/upload/submit 绑定语义属于 flow envelope，不写入通用 bundle contract。

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

对于 `DATASET_REPLACEMENT` pair，bundle 必须同时闭合 surface/preview index 中每张表的 `replacement_summary` 与可用侧 snapshot parquet refs。前端按 `comparison_mode` 进入独立双侧浏览模块，不得把两侧 parquet 拼接为普通 diff dataset，也不得为全部替换行生成增删或风险展示。

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
      surface_result
      surface_artifact_closure
  shared_artifacts optional
  artifact_policy
  ref_scope: BUNDLE_RELATIVE
```

`surface_result` 是已完成的 `SurfaceAssemblyResult`。Bundle 只接受 `READY` Surface；取消是
bundle `CANCELLED`，required pair 失败是 `FAILED`，optional pair 失败可生成不含 partial
artifact 的 closure-valid `DEGRADED` bundle。

`BundleArtifactBinding` 只在输入 closure 中保存 source `ArtifactRef`、kind、pair/shared scope
和 normalized logical path。最终 manifest/closure 只保存 bundle final ref；source ref 不进入
bundle semantic digest。

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
  bundle_id
  bundle_profile
  status: READY | DEGRADED
  inputs
  pairs:
    - BundlePair
  table_aliases optional
  summary
  manifest_ref
  artifact_closure_ref
  failed_pairs
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

- bundle manifest canonical semantic payload。
- pair surface digests。
- artifact closure semantic manifest digest。
- bundle contract version。

不进入 digest：

- bundle id。
- operation id。
- flow id。
- download URL。
- host path。
- generated_at。

Manifest/closure 的 serialized `ArtifactRef.artifact_id`、source ref、host path 和 runtime metadata
不进入 semantic digest；artifact media type、size 和 raw content digest 进入 closure integrity。

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
        composite-signal-points.json
        composite-signal-formulas.json
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
- 跨 pair 复用的 snapshot table artifact 使用 `shared/snapshot-tables/...` bundle-root ref；bundle
  pair ref rewrite 不得再次把这类 ref 改写到 `pairs/<pair_id>/shared/...`。
- 相同内容的 snapshot table rows 使用一个 `shared/snapshot-tables/{digest}.parquet` 文件。
  对应 closure entry 的 `table_bindings` 保留每个 pair、`before | current | browse` side 和
  `table_name` 的绑定；共享文件不得丢弃其中任一绑定。普通 pair-scoped snapshot entry 也使用
  单元素 `table_bindings`，不再用单个 `pair_id` / `table_name` 表示 snapshot binding。
- MULTI_PAIR 闭包中若出现相同 `source_ref` 且相同 artifact kind 的非 snapshot binding，assembler
  将其提升为 `shared/{kind-segment}/{digest-suffix}/artifact`。Snapshot table binding 使用上面的
  `table_bindings` 合并规则。该结构属于 Bundle v3 Contract。
- Upload preview 的 `before_table_ref`、`current_table_ref` 和 `browse_table_ref` 若非空，必须直接指向
  可读取的 Parquet snapshot rows；不得以 JSON descriptor 或 metadata envelope 占位。
- Upload preview 默认只发布单侧 snapshot：current 侧存在时只发布 `current_table_ref`（包括
  unchanged、modified、schema changed 和 degraded）；仅 current 不可用且 before 存在时发布
  `before_table_ref`。两侧均不可用时不发布 row ref。
- Preview bundle 闭合上传侧全部表以及被删除表的基线侧数据；History 每个节点闭合全部表。bundle 清单为每个 pair/node 保留表名到 Parquet ref 的绑定。相同内容的 Parquet rows 按内容地址共享，不合并或丢弃绑定。
- `records_ref` 若非空同样必须闭合为 bundle 内 Parquet diff rows，并与其 manifest ref 一起发布。
  Bundle assembler 不得自动生成 descriptor、diff envelope 或其他 metadata 来替代这些 row artifacts。
- Bundle artifact closure 必须覆盖最终 rewritten surface 引用的 snapshot parquet、standard/ordered
  records parquet、records manifest、risk annotation content/manifest 和 business projection artifacts。
  Upload preview 与 history compare 使用同一套 writer/validator；发布层不得再手工补写 records/risk。
- Upload preview 的 `preview_index.tables[].diff_artifact_ref` 在正式 vNext 路径中等同于 direct
  Parquet records ref：标准 records 表使用 `CURRENT_INLINE`，ordered records 表使用
  `CURRENT_SLOTTED` 并必须携带 `position_column`。
- History/formal comparison bundle 在 comparison input 带有 snapshot table set 时，应发布可浏览的
  `current_table_ref` / `browse_table_ref` Parquet snapshot rows。标准 records 表使用 `CURRENT_INLINE`，
  ordered records 表使用 `CURRENT_SLOTTED`，从而复用 upload diff 浏览和 full/diff/risk 过滤逻辑。
- History compare 的 snapshot table 发布应复用 upload preview 的 snapshot ref 绑定、fast candidate
  去重、cross-pair shared ref rewrite 和 Parquet export helper。三节点 history compare 中相同内容的
  snapshot rows 可以跨 `left_to_middle` / `middle_to_right` pair 共享为 `shared/snapshot-tables/...`。
- Upload preview 和 history compare 使用同一套 snapshot Parquet cache/export capability。
  跨 operation 持久 cache 只允许使用 repository scope、`SnapshotTableDescriptor.row_layout_digest +
  parquet_writer_contract_version` 精确命中；缓存引用经 artifact protection intent 登记并按 TTL 过期。
  schema/export layout 不同不得命中；`fast_candidate_key` 只用于同次 dedupe、shared ref
  rewrite 和 dry-run/估算，不得作为持久 cache identity。
- Snapshot Parquet cache hit 恢复到 bundle 时必须复制为当前 bundle 的 bundle-relative
  Parquet artifact ref，并进入统一 artifact closure；cache-local artifact ref 不得出现在
  surface、preview index 或 bundle manifest 中。
- 如果 history/formal comparison bundle 缺少 snapshot table refs，但存在 ordered records，前端可以
  以 `FORMAL_ORDERED_RECORDS` 直接读取 `ordered_extension.ordered_records_ref` 指向的 Parquet records。
  该 fallback 只展示 ordered 差异记录本身，不要求 `current_table_ref`。
- Formal comparison surface 中没有 `records_ref` / `ordered_records_ref` 的表应作为 `SUMMARY_ONLY`
  展示摘要；这不是 artifact 读取失败。
- Alias member 默认不重复携带 records artifact；closure 只需闭合 canonical table records 和 alias mapping。
- Comparison records、business projections、risk report、risk annotations 和 diagnostics 是 pair 级 artifacts，默认不跨 pair 合并。
- Business projection supplemental artifact 是任意可附加的 pair 级 artifact。复合信号 points/formulas 使用 projection item 内的 ref/digest 寻址，并必须同时出现在 pair closure；因此无需提升 comparison bundle 总合同版本。
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
  business_projection_supplemental_artifacts
  risk_reports
  risk_annotations
  diagnostics
  shared_snapshot_artifacts optional
```

Bundle v3 的 closure entry 至少包含 `logical_path`、final `artifact_ref`、kind、size/raw digest
和 pair/shared scope。`SNAPSHOT_TABLE` entry 使用按 `(pair_id, side, table_name)` 排序的非空
`table_bindings`；同一内容文件可绑定到多个 pair/table。其他 kind 使用 `pair_id` / `table_name`
表达单一 scope。Bundle assembler 会对 JSON closure 中嵌套的 ArtifactRef 做确定性 rewrite，
拒绝未声明 ref、重复 entry、环依赖、非法 path 或 integrity mismatch。写入 manifest、closure
和所有 referenced artifacts 并完成回读校验前，不返回 READY/DEGRADED public result。

规则：

- Bundle 不得引用 cache-local path。
- Cache hit 恢复到 bundle 时必须重写为 bundle-relative refs。
- Closure 缺失时 bundle 不能对外 READY。
- Bundle digest 可以包含 closure manifest digest；closure refs 本身可重写。
- Core closure 不闭合 upload-specific 的 `preview_index.json`、`diff_summary.json`；它们由 preview bundle delivery 层根据当前 v3 contract 生成。
- 所有 `ComparisonSurface.tables[].risk_refs.annotation_ref` 与
  `annotation_manifest_ref` 必须在 bundle 内闭合为真实
  `backend-vnext/risk-annotations/v1` content / manifest JSON。任何非当前合同或空 placeholder 都不能占用 annotation ref。
- `RiskReport.tables` 缺席某个表表示该表没有 annotation；正式/preview consumer 应将该表风险
  展示为 `risk_level: null`、`annotation_count: 0`，不得因存在 surface 或缺失 source artifact
  合成 `UNKNOWN`。

## Cache 边界

第一版不要求实现 bundle cache。Snapshot Parquet persistent cache 已作为 snapshot artifact IO cache
实现，但它只缓存可重建的 snapshot rows parquet，不缓存 surface、risk、records 或 bundle assembly。

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
- Upload preview snapshot、records、risk 和 projection artifact 默认 pair-scoped；不同 `source_ref`
  不得共享同一 pair-scoped logical path（`tables/...`、`comparison/records/...`、`risk/...` 等）。
  相同 `source_ref` 的跨 pair 重复允许提升为 `shared/...`（见上条）。
- Ordered unsupported bundle 仍可 READY，并提供 review-required risk/diagnostics。
