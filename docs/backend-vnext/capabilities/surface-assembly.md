# Surface Assembly Capability

本文定义 `ComparisonSurface` 的第一版实现设计。Contract 见 `../contracts/comparison-surface.md`。

Surface assembly 是 flow-neutral capability。它只消费 comparison/risk 输出和 artifact closure 信息，把它们组装成前端可浏览的 surface；它不计算 diff、不计算 risk、不读取 source/ref，也不推进业务流程。

前后端简化策略见 `../frontend-surface-simplification.md`。本 capability 应优先输出 thin surface，避免把可由前端派生或上层兼容层生成的旧结构写入 core surface。

## 设计原则

规则：

- Flow 负责选择 surface profile、权限、TTL 和是否需要 bundle。
- Operation 负责确保输入 artifacts 已存在并可闭合。
- Capability 负责组装 deterministic surface payload、校验 refs、输出 `surface_digest`。
- Capability 不依赖 upload、submit、history compare 或 archive flow。
- Capability 不依赖旧 `comparison_surface`、`preview`、`workbench` 模块。

## 旧实现参考边界

可参考：

- 旧 `comparison-surface/v1` 的表级结构。
- `ComparisonSurfaceBuilder` 的 relative ref validation。
- 禁止 preview binding key 进入 surface 的思路。
- `preview/bundle_builder.py` 中从 surface 派生 preview table/index 的展示需求。
- 旧 risk report/annotation refs 的导航和只看风险需求。

不直接继承：

- 旧 dataclass、domain value object、preview refs。
- `PreviewBundleContext`、workspace/submission binding。
- host path、cache ref、Dolt ref。
- sidebar/workbench bundle 组装逻辑。
- secondary-device projection；它应作为后续独立 projection。

## 能力列表

```text
surface_assembly
surface_table_projection
surface_ref_rewrite
surface_digest
surface_validation
surface_cache optional future
```

## 建议代码模块

建议落点：

```text
gateway-data-management-system/backend/backend_vnext/capabilities/surface_assembly/
```

内部拆分：

```text
models.py
builder.py
table_projection.py
ref_validation.py
digest.py
versions.py
```

依赖方向：

```text
surface_assembly
  -> contracts.comparison
  -> contracts.risk
  -> contracts.comparison_surface
  -> artifacts.closure
  -> core
```

禁止依赖 flow、operation runtime、repository_server、snapshot_materialization、comparison compute provider、risk engine provider 或旧业务模块。

## 输入输出

输入：

```text
SurfaceAssemblyInput:
  comparison_facts
  records_closure optional
  risk_report optional
  risk_annotation_closure optional
  diagnostics_refs optional
  surface_profile: STANDARD_TABLE_BROWSER
  surface_options
  ref_scope
```

输出：

```text
SurfaceAssemblyResult:
  comparison_surface
  surface_digest
  referenced_artifacts
  diagnostics
```

规则：

- `records_closure` 和 `risk_annotation_closure` 可以为空；surface 仍能输出 summary-only 表示。
- 如果 `ComparisonTableFact` 声明 records required，但 closure 缺失，surface assembly 应输出 failure diagnostic，而不是伪造 refs。
- `referenced_artifacts` 交给 bundle assembly 或 operation artifact closure 使用。

## 表级投影

`surface_table_projection` 从 `ComparisonTableFact` 生成 `SurfaceTable`。

第一版映射：

| Comparison fact | Surface change_kind | Display strategy |
| --- | --- | --- |
| unchanged | `UNCHANGED` | `SUMMARY_ONLY` |
| business equivalent | `BUSINESS_EQUIVALENT` | `SUMMARY_ONLY` |
| table added | `ADDED` | `TABLE_BROWSE` |
| table deleted | `DELETED` | `RECORDS_ONLY` 或 `SUMMARY_ONLY` |
| row changes | `UPDATED` | `CURRENT_WITH_RECORDS` |
| schema changed | `SCHEMA_CHANGED` | `DEGRADED_NOTICE` 或 `RECORDS_ONLY` |
| degraded/failed | `DEGRADED` / `FAILED` | `DEGRADED_NOTICE` |
| ordered unsupported | `DEGRADED` | `DEGRADED_NOTICE` |

规则：

- Surface 不重新判断表是否变化。
- Surface 不读取 full rows。
- Surface 不把 ignored columns 生成为 row diff。
- Surface 可以输出 `diagnostics_summary`，但详细诊断走 artifact ref。

## Ref Validation

第一版必须校验：

- 所有 `*_ref` 是 logical relative ref。
- 不存在绝对路径、`..` 跳出、URL、cache-local ref、host path。
- 不存在 preview/submit binding key。
- records/risk refs 对应的 manifest digest 可被 closure 校验。

建议禁止字段：

```text
preview_token
preview_revision_id
preview_bundle_id
workspace_id
submission_id
history_request_id
submit_binding
target_set_binding
repository_commit_hash
host_path
cache_ref
```

Flow 如需这些字段，应保存在 flow envelope 或 API response metadata，不进入 surface core。

## Digest

`surface_digest` 由 canonical payload 计算，但应先移除 runtime refs。

输入：

```text
comparison_digest
risk_evaluation_digest optional
surface_contract_version
surface_profile
surface_options
surface table semantic payload
referenced artifact manifest digests
```

不输入：

```text
surface_id
operation_id
bundle_id
host path
relative ref string
generated_at
diagnostics timing
```

## Cache 接入点

第一版不实现 `comparison_surface_cache`。

第一版 `surface_profile` 只实现 `STANDARD_TABLE_BROWSER`。如果后续需要旧前端兼容输出，由 flows / operations 在上层 materialize，surface assembly 不为其增加专用 profile。

未来 key：

```text
comparison_digest
risk_evaluation_digest optional
surface_contract_version
surface_profile
surface_options
records_closure_manifest_digest optional
risk_annotation_closure_manifest_digest optional
```

规则：

- Surface cache hit 必须 restore refs 到当前 operation/bundle scope。
- Surface cache 不缓存上层兼容输出。
- Surface cache 不替代 comparison core cache 或 risk cache。

## Ordered Table 第一版策略

第一版开始消费 `ComparisonTableFact.ordered_extension`，但不在 surface 里重新实现 ordered 算法。

当 comparison/risk 表明 ordered unsupported，或者 ordered provider 仍然缺失时：

- `change_kind = DEGRADED`。
- `display.table_processing_mode = DEGRADED`。
- `display.strategy = DEGRADED_NOTICE`。
- ordered 的真实降级通过 `DEGRADED` + ordered diagnostics 表达。
- 保留 risk annotation ref。
- 不生成 move/position/interval 入口。

已接入的 ordered 扩展字段：

- `ordered_extension`。
- ordered records refs。
- `table_processing_mode`。
- `ordered_preprocess_applied`。
- ordered diagnostics。

后续仍待补充：

- move/position/interval summary。
- ordered risk target 到 surface navigation 的映射。
- pseudo blank interval 展示与定位。

## 测试与验收

Unit：

- table fact 到 surface table 的映射。
- relative ref validation。
- forbidden key rejection。
- surface digest 稳定。

Contract：

- summary-only surface 可以无 records closure。
- records required 但 closure 缺失时失败。
- risk refs 可重写且 digest 不变。
- ordered unsupported 输出 degraded notice。

Integration：

- `ComparisonFacts -> RiskReport -> ComparisonSurface`。
- `ComparisonCoreCache restore -> SurfaceAssembly`。
- `SurfaceAssembly -> BundleAssembly`。

## S4 Python reference implementation

S4 的 Python reference implementation 位于：

```text
vnext/backend/src/gateway_backend/capabilities/surface_assembly/
  contracts.py
  _assembly.py
  _digest.py
  _refs.py
```

公共入口为 `assemble_surface`、`validate_surface` 和 `rewrite_surface_refs`。Surface v2
使用不可变 dataclass contracts；表按 canonical table name 排序，table id 等于 normalized
table name，display name 按 current descriptor、before descriptor、table name 的顺序确定。
组装过程只消费 descriptor、counts、schema changes、ordered metadata 和 closure entries，
不会读取 `ComparisonRecord` 的 row values 或任何 Snapshot reader。

S4 当前只支持 `STANDARD_TABLE_BROWSER`。普通表按 `ComparisonTableStatus` 投影为 summary、
browse、records-only 或 degraded notice；ordered unsupported 保持 `DEGRADED`，不伪装成普通
semantic diff。`DATASET_REPLACEMENT` 在 Surface 层表达为独立 before/current side refs、
`REPLACED`/side-only table change kind 和 `REPLACEMENT_SIDE_BY_SIDE`，不发布 records 或
row-risk refs。

Surface digest 使用 canonical semantic payload，排除 runtime id、raw ref、diagnostic ref 和
flow metadata，但包含 comparison/risk/identity semantic digests、table payload 及 artifact
integrity identities。ref rewrite 只重写 opaque `ArtifactRef`，不会改变 surface digest。
S4 的 JSON cap 固定为 16 MiB；校验失败、取消或超限均不发布部分 Surface。
