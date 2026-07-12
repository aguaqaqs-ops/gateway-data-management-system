# Formal Bundle / Surface Contract Scheme

本文固定 Slice 2 的 contract 收口方案。目标是让正式 history compare 和后续 upload preview 都消费同一类干净的 `ComparisonBundle` / `ComparisonSurface` / business projection / risk annotation / Parquet records artifact，不恢复 legacy Workbench 或 preview sidecar 作为正式路径。

## Design Principles

1. `ComparisonSurface` 是轻索引：表达 pair、table summary、artifact refs、projection refs、risk refs 和 diagnostics refs，不内嵌大 row records。
2. Business projection 表达业务导航：转发通道、二次装置、通讯规约、全局参数、未解析表由 projection artifact 输出，前端不再按表名猜业务结构。
3. Row records 只表达 row-level diff：正式 diff artifact 固定为 Parquet；metadata、manifest、surface、projection、risk、diagnostics 使用 JSON。
4. Risk 输出分层：table-level、row-level、projection-level aggregation 各有明确 owner；projection 聚合不反写 comparison/risk core facts。
5. Bundle 只负责 artifact closure 和可下载边界：不计算 diff、不计算 risk、不推进流程、不携带 host path、repo path、cache-local ref 或 debug-only 字段。
6. 非兼容重构不保留旧 history workbench path、旧 sidecar 字段或旧 OPFS record migration。

## Formal Bundle Layout

正式 bundle tar 使用稳定 layout：

```text
bundle-root/
  manifest.json
  artifact-closure.json
  inputs/
    input-0.json
    input-1.json
    input-2.json optional
  pairs/
    <pair_id>/
      comparison-surface.json
      comparison/
        facts.json
        records/
          <table_id>.records.parquet
          <table_id>.records.manifest.json
      projections/
        forward-channels.json optional
        secondary-devices.json optional
        communication-protocols.json optional
        global-parameters.json optional
        unparsed-tables.json optional
      risk/
        risk-evaluation.json
        risk-report.json
        annotations/
          <table_id>.risk-annotations.json
          <table_id>.risk-annotations.manifest.json
        projections/
          <projection_id>.risk-summary.json optional
      diagnostics/
        projection-diagnostics.json optional
        ordered-diagnostics.json optional
        table-diagnostics.json optional
```

Rules:

- All refs are bundle-relative logical refs.
- `manifest.json` is the package entrypoint and includes contract versions, input order, pair plan and refs.
- `artifact-closure.json` lists every artifact needed to open the bundle and validates digest/size/format.
- `comparison-surface.json` is pair-local and never contains host path, repository path, cache-local ref, commit hash, debug registry entry or download URL.
- Snapshot/input artifacts may be shared across pairs; pair-level records, risk annotations, projections and diagnostics remain pair-local unless explicitly deduplicated by closure.

## Pair Model

No three-way diff is introduced.

| Flow shape | Inputs | Pair ids |
| --- | --- | --- |
| 2-node history compare | left, right | `left_to_right` |
| 3-node history compare | left, middle, right | `left_to_middle`, `middle_to_right` |
| FULL upload preview | baseline, initial, modified | `baseline_to_initial`, `initial_to_modified` |
| MODIFIED_ONLY upload preview | baseline, modified | `baseline_to_modified` |

`pair_id` is bundle-local display/lookup identity. It is not a repository ref and does not enter comparison digest.

## Surface Shape

`ComparisonSurface` stays small:

```text
ComparisonSurface:
  surface_contract_version
  surface_digest
  surface_id
  pair_id
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
```

`SurfaceTable`:

```text
SurfaceTable:
  table_id
  table_name
  display_name
  table_status
  change_kind
  row_count
  row_change_stats
  columns optional
  records_refs
  risk_refs
  diagnostics_refs
  display
  compare
  ordered_extension optional
```

`SurfaceProjectionRef`:

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

Rules:

- `table_id` is the stable key used by records refs, risk refs, diagnostics refs and frontend cache keys.
- `table_name` is the normalized business table name; `display_name` is presentation metadata and may come from metadata, SQL comment or projection policy.
- Business identity (`dev_addr`, `gid`, `board/link`) belongs to projection artifacts, not table compare key.
- Compare key (`gid`, primary key, `board/link`, ordered position) belongs to comparison/table rules and diagnostics.

## Projection Artifacts

First-class projection artifacts:

| Projection kind | Artifact schema | Main business identity | Owner |
| --- | --- | --- | --- |
| `FORWARD_CHANNELS` | `forward-channel-projection/v1` | `board`, `link_no`, `protocol`, stable key `b{board}_n{link}` | business projection capability |
| `SECONDARY_DEVICES` | `secondary-device-projection/v1` | `dev_addr`, optional `gid` | business projection capability |
| `COMMUNICATION_PROTOCOLS` | `communication-protocol-projection/v1` | channel stable key + protocol segment | business projection capability |
| `GLOBAL_PARAMETERS` | `global-parameter-projection/v1` | table name or app config target | business projection capability |
| `UNPARSED_TABLES` | `unparsed-table-projection/v1` | table id/name | surface assembly fallback |

Projection artifacts may include item summaries, tab refs, row filters, business labels, risk aggregation refs and diagnostics. They must not include large row records; they point back to `SurfaceTable` / records refs when row detail is needed.

## Records Format

Formal row records are Parquet:

```text
records_refs:
  records_ref: pairs/<pair_id>/comparison/records/<table_id>.records.parquet
  records_manifest_ref: pairs/<pair_id>/comparison/records/<table_id>.records.manifest.json
  records_format: PARQUET
```

Required record concepts:

- diff kind: added, deleted, modified, unchanged/context when explicitly emitted.
- row role: before/current/pair.
- row identity: compare key, ordered stable key, optional row position.
- display cells: before/current value sets for changed columns.
- risk links: annotation ids or risk target ids when available.

`INLINE_SUMMARY` is allowed only for tables that intentionally have no row records, such as browse-only, schema-only, unsupported or degraded summary-only tables. JSONL is not a formal row artifact format.

## Risk Contract Boundary

Risk is layered:

- Table-level risk: references a table and table diagnostics/facts.
- Row-level risk: references row identity, row pair, position or ordered interval.
- Projection-level aggregation: summarizes table/row annotations for a business projection item, such as a secondary device.

Projection-level aggregation may produce `risk_summary` and diagnostics, but it does not mutate the underlying `RiskFacts`, `RiskReport` or row records.

## Diagnostics Codes

Initial formal diagnostics codes:

| Code | Owner | Meaning |
| --- | --- | --- |
| `MISSING_PROTOCOL_EXE` | communication protocol projection | `net_cfg.exe` is missing or cannot be normalized. |
| `CANDIDATE_TABLE_NOT_FOUND` | communication protocol projection | Expected protocol cfg/dev_cfg table does not exist. |
| `CANDIDATE_TABLE_FILTERED` | communication protocol projection | Candidate table exists but is excluded from the formal surface. |
| `DUPLICATE_DEVICE_ADDRESS` | secondary device projection | Multiple device rows share the same `dev_addr`. |
| `DUPLICATE_DEVICE_GID` | secondary device projection | `gid` identity is ambiguous for gid-based tabs. |
| `ORDERED_DIFF_DEGRADED` | ordered diff provider | Ordered provider degraded and emitted summary-only result. |
| `ORDERED_DIFF_UNSUPPORTED` | ordered diff provider | Ordered semantic replay is unsupported for the table. |
| `PROJECTION_PARTIAL` | business projection capability | Projection completed but skipped ambiguous or unresolved items. |

Codes are stable contract values. Human-facing Chinese/English labels belong to frontend display dictionaries or optional display metadata, not core semantics.

## Explicit Non-Goals

- No `workbench_manifest.json`.
- No `preview_index.json` as formal history/open-workbench input.
- No `diff_summary.json` as formal bundle entrypoint.
- No synthetic preview identity for history compare.
- No `workbench_bundle_download`.
- No `source_kind="history_comparison"` legacy branch.
- No host path, repository path, cache-local path, debug registry path or Dolt internal ref in any formal response/bundle surface.

## Implementation Order

1. Update contract docs and schema fixtures to match this scheme.
2. Implement formal business projection capability with small fixtures from the Oracle audit.
3. Wire surface assembly to emit projection refs and Parquet records refs.
4. Harden ordered diff / large row records and risk annotations.
5. Move upload preview frontend loader from sidecar to formal bundle/surface, then delete the preview sidecar boundary.
6. Finish frontend Workbench display on top of formal projections and Parquet records.
