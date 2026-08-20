# P3-R5-S0 Entry, Applicability and Budget Freeze

状态：S0 complete；implementation authorization pending

日期：2026-08-20

Owner：Backend vNext Architecture / Comparison Capability

上级计划：[P3-R5 Comparison Execution Plan](p3-r5-comparison-execution-plan.md)

设计基线：[P3-R5 Comparison Design Baseline](p3-r5-comparison-design.md)

R4 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)

本文冻结 R5 开始实现前必须检查的入口、适用性、跨语言边界、资源预算、fixture、benchmark、
allowlist 和 reopen 条件。它不授权实现，也不把未实测的数值写成性能 gate。

## 1. Entry facts

```yaml
handoff_kind: p3_r5_s0_entry_and_budget_freeze
p3_r4_exit: pass
p3_r5_ready: yes
p3_r5_design: p3-r5-comparison-design.md
p3_r5_execution_plan: p3-r5-comparison-execution-plan.md
p3_r5_s0_exit: pass
p3_r5_s1_authorized: yes
p3_r5_s1_exit: pass
p3_implementation_authorized: no
validated_r4_code_sha: 4effb6eefa16d246e75213212f884b2546e6d6ef
r4_focused_suite: 268 passed
r4_full_unit_current_head: timeout at existing healthz test; no assertion failure
s0_worktree: dirty_docs_only
container_rebuild_for_entry: no
container_reason: R5 entry is docs/design only; no image or deployment boundary changed
benchmark: measurement_only_no_gate
```

R4 SHA/test facts are entry evidence only; they do not authorize R5 implementation. R4 handoff
documentation SHA and final R5 S0 commit SHA are sealed by the documentation commit that contains
this record. No production source, dependency, image or deployment path is changed by S0.

## 2. Applicability and public boundary

R5 consumes only immutable `SnapshotTableArtifact` and public reader/batch-reader closure. R4
`CanonicalizationManifest` is opaque identity/binding. R5 does not import R4 private modules or infer
comparison columns from storage.

```text
trusted flow/orchestrator
  -> PairExecutionInput
  -> R5 planning and table tasks
  -> Arrow batch reader closure
  -> comparison kernels
  -> facts/records publication
```

Applicability matrix:

| View/flow context | before | identity applicability | comparison mode | R5 behavior |
| --- | --- | --- | --- | --- |
| initial snapshot | none | `NOT_APPLICABLE` | none | current-side view only |
| formal upload pair | required | `REQUIRED` | assessment-selected | gate then detailed/replacement |
| `MODIFIED_ONLY` | reconstructed baseline required | `REQUIRED` | assessment-selected | no sparse delta |
| history compare | required | trusted `NOT_APPLICABLE` | `DETAILED` | no identity assessment/replacement |
| archive replay | required | trusted `NOT_APPLICABLE` | `DETAILED` | no identity assessment/replacement |

`NOT_APPLICABLE` is flow capability output, not a free caller option. `UNVERIFIABLE` is fail-closed
until `ALLOW_DETAILED_ON_UNVERIFIABLE` continuation is revalidated by the trusted orchestrator.

### 2.1 PairExecutionInput applicability contract

`PairExecutionInput` is a flow-neutral, already-bound input. The caller supplies immutable snapshot
artifacts and an assessment; it does not supply a replacement decision or bypass identity applicability.

```text
PairExecutionInput:
  pair_id: opaque, non-host-path identifier
  view_kind: PAIR_COMPARISON | INITIAL_SNAPSHOT | HISTORY | ARCHIVE_REPLAY
  before: BoundSnapshotInput | none
  current: BoundSnapshotInput
  input_completeness: FULL | MODIFIED_ONLY
  comparison_mode: DETAILED | DATASET_REPLACEMENT | none  # derived and validated
  artifact_scope: ALL_CHANGES | UPDATE_ONLY | none
  identity_applicability: REQUIRED | NOT_APPLICABLE
  identity_assessment: ProjectIdentityAssessment | none
  continuation_binding: UnverifiableContinuationBinding | none
  comparison_options: immutable semantic options
  contract_versions: immutable version tuple
  runtime_policy: resource-only policy
```

Validation is fail-closed before any reader opens:

| Input shape | Required result | Reader open |
| --- | --- | --- |
| `INITIAL_SNAPSHOT`, no `before` | `INITIAL_SNAPSHOT` result, `NOT_APPLICABLE` | current only |
| `PAIR_COMPARISON`, `FULL` | assessment-bound detailed or replacement result | after gate |
| `PAIR_COMPARISON`, `MODIFIED_ONLY` | pinned baseline reconstruction first; no sparse delta | after reconstruction |
| `HISTORY` / `ARCHIVE_REPLAY` | trusted `NOT_APPLICABLE` + `DETAILED` | after trusted binding |
| `DIFFERENT_PROJECT` | `DATASET_REPLACEMENT`, `records_ref=none` | side readers only |
| `UNVERIFIABLE` without a valid continuation binding | `IDENTITY_GATE_BLOCKED` | never |

`NOT_APPLICABLE` is accepted only from the trusted history/archive flow context. A normal caller
cannot set it. `ALLOW_DETAILED_ON_UNVERIFIABLE` continuation and replacement submit confirmation are
separate bits and separate actions; neither is accepted by the comparison kernel as actor/session
authorization.

### 2.2 Public type and field ownership

The following table is the S0 ownership authority. A field is not duplicated in a downstream DTO;
consumers reference the owning immutable value or digest.

| Type/field family | Owner and authority | Frozen rule/version |
| --- | --- | --- |
| `ArtifactRef`, artifact store port | artifacts support | four-field opaque ref; no host path |
| `SnapshotTableArtifact`, descriptor, reader | R3 snapshot materialization; [snapshot-table-access contract](../../../contracts/snapshot-table-access.md) | `snapshot_table_artifact_contract_version=1`; consume public contracts only |
| batch reader / Arrow schema metadata | R3 public reader owner with R5 consumer review | `RecordBatch` bulk path; scalar, projection, ordered, blank and artifact versions are metadata |
| `ProjectIdentityAssessment` and `assessment_digest` | project identity capability | `project-identity-assessment/v1`, `version-manager-overlap/v1` |
| `PairExecutionInput`, `PairExecutionResult`, `ComparisonPlan`, `TableComparisonTask` | R5 comparison | discriminated tags frozen in §2.3; no flow/HTTP state |
| `ComparisonFacts`, table facts, summary, records kinds, `FieldChange` | R5 comparison; [comparison contract](../../../contracts/comparison.md) | `backend-vnext/comparison/v2`; `ROW_MODIFIED` is the authority for derived field changes |
| standard/ordered/blank record schemas | R5 comparison + artifact support | standard records use typed Parquet; ordered/blank use independent versioned schemas |
| `RecordsArtifactManifest`, `ComparisonRecordsClosure` | artifact support for bytes/closure; R5 for semantic fields | refs operation-local; manifest/content/facts-core/closure digests have no cycle |
| neutral comparison cache key/value | cache support + R5 | pair-level canonical facts/closure only; no identity, authorization, submit or host path |
| canonical scalar/null/digest bytes | Shared Canonical Encoding owner | reuse existing scalar encoding; no second encoding or stringify fallback |

### 2.3 Result union

S2 must implement this frozen discriminated result shape; S0 does not implement it:

```text
PairExecutionResult:
  kind: INITIAL_SNAPSHOT | DETAILED_FACTS | DATASET_REPLACEMENT
        | IDENTITY_GATE_BLOCKED | CANCELLED | FAILED
  pair_id
  status: UNCHANGED | BUSINESS_EQUIVALENT | CHANGED | DEGRADED | FAILED | CANCELLED
  facts: ComparisonFacts | none
  records_closure: ComparisonRecordsClosure | none
  diagnostics
```

`DATASET_REPLACEMENT` never enters the detailed planner and has no records closure. `CANCELLED` and
`IDENTITY_GATE_BLOCKED` publish diagnostics only; `FAILED` is terminal and publishes no facts/READY.

## 3. Language-neutral batch boundary

R5 S1 must provide or consume an approved public batch boundary:

```text
SnapshotTableBatchReader:
  descriptor()
  iter_record_batches()
  reopen()
  close()
```

Arrow `RecordBatch`/`RecordBatchReader` is the in-process Python/Rust bulk boundary; Parquet is the
immutable artifact boundary; Arrow IPC stream is the temporary cross-process stream. `iter_rows()` is
retained for Python reference and tiny fixtures, not as the large-table Rust production path.

Constraints:

- no `to_pylist()`, per-row FFI, per-scalar JSON or Python object graph as bulk input;
- PyO3/Arrow uses safe public APIs and releases GIL during native compute;
- schema metadata carries scalar/projection/ordered/blank/artifact versions;
- Python reference and Rust provider must produce equal canonical facts, records digests and counts;
- if adding batch reader changes R3 public ownership, stop and reopen R3 owner rather than importing
  private R4/R3 modules.

## 4. Budget freeze

The input limits below are inherited from R2/R3 and remain owned there. R5 adds execution caps to
bound comparison work and temporary state. These are fail-closed safety/resource limits, not throughput
targets, latency SLOs or automatic implementation gates.

### 4.1 Inherited input limits

| Budget | Frozen limit | Owner |
| --- | ---: | --- |
| compressed source ingress | 256 MiB | R3 SourcePackage / R3-S0 |
| expanded source package | 1 GiB | R3 SourcePackage / R3-S0 |
| tables per side | 2,048 | R2 `table_access.RESOURCE_BUDGETS` |
| rows per table | 2,000,000 | R2 `table_access.RESOURCE_BUDGETS` |
| rows per side | 10,000,000 | R2 `table_access.RESOURCE_BUDGETS` |
| reader batch | 1,024 rows or 8 MiB | R2 `table_access.RESOURCE_BUDGETS` |
| field / diagnostic limits | R2-S0 §8 | R2 owner |

R5 never copies parser implementation budgets into a second parser table. A pair may reference two
independently validated sides; the pair caps below govern their combined comparison work.

### 4.2 R5 execution caps

| Layer / budget name | Frozen limit | Exceedance |
| --- | ---: | --- |
| `max_tables_per_pair` | 4,096 | pair `FAILED` before reader open |
| `max_rows_per_pair` | 20,000,000 | pair `FAILED` before reader open |
| `max_pair_input_artifact_bytes` | 2 GiB | pair `FAILED` before reader open |
| `max_pair_working_memory_bytes` | 512 MiB | `AUTO` spills; forced HASH becomes table `DEGRADED` |
| `max_pair_wall_time_seconds` | 900 s | pair `CANCELLED` / no publication |
| `max_rows_per_table` | 2,000,000 per side | table `DEGRADED`; other tables continue |
| `max_table_working_memory_bytes` | 256 MiB | `AUTO` switches to SQLite; forced HASH degrades |
| `max_table_wall_time_seconds` | 120 s | table `DEGRADED` and partial artifact discarded |
| `max_records_per_table` | 2,000,000 | table `DEGRADED` and partial artifact discarded |
| `max_records_artifact_bytes` | 512 MiB per table | table `DEGRADED` and partial artifact discarded |
| `max_manifest_json_bytes` | 16 MiB | pair `FAILED`; no closure publication |
| `max_closure_json_bytes` | 16 MiB | pair `FAILED`; no closure publication |
| `max_sqlite_temp_bytes` | 2 GiB per pair | current table `DEGRADED`; delete spool |
| `max_spool_bytes` | 2 GiB per pair | current table `DEGRADED`; delete spool |
| `cancellation_observation_seconds` | 5 s | diagnostic; no facts/closure publication |

`AUTO` follows [ADR 0002](../../../adr/0002-comparison-hash-sqlite-mode-selection.md): explicit mode
override wins; a projected payload at or below 75% of the table memory cap uses HASH, at or above the
cap uses SQLite, and the grey zone uses HASH with a diagnostic. A cap is checked incrementally at
reader-batch, record-write and digest boundaries.

```text
input budgets (R2/R3 owner)
  -> pair budget
  -> table budget
  -> runtime/deadline budget
  -> records budget
  -> spill/SQLite temporary budget
```

Required behavior:

- HASH `AUTO` may switch to SQLite before memory exhaustion;
- table spill/records/per-table limit produces table `DEGRADED` and discards partial artifact;
- pair writer/manifest/digest/closure failure produces pair `FAILED`;
- cancellation/deadline produces `CANCELLED` with no published facts/closure;
- all readers, writers, SQLite handles and temporary spools close before terminal publication;
- benchmark records duration, CPU/RSS, spill, artifact bytes, records count and cancellation latency;
  no result changes the caps or grants implementation authorization.

### 4.3 Failure matrix

| Fault / boundary | Scope and result | Publication rule |
| --- | --- | --- |
| invalid pair shape, missing baseline, cap known before open | pair `FAILED` | no reader, facts or closure |
| missing/invalid key or schema on one table | table `DEGRADED` | other tables continue; discard that table artifact |
| HASH memory, SQLite temp, records or table cap | table `DEGRADED` | close handles and discard partial artifact |
| reader I/O, provider error or digest mismatch | table `DEGRADED` if isolated; otherwise pair `FAILED` | never treat as empty input |
| manifest/content/closure validation or atomic publish failure | pair `FAILED` | no READY and no published facts |
| user cancellation or deadline | pair `CANCELLED` | no facts/closure; cleanup before terminal state |
| `UNVERIFIABLE` without revalidated continuation | `IDENTITY_GATE_BLOCKED` | diagnostics only; no comparison execution |
| `DIFFERENT_PROJECT` | `DATASET_REPLACEMENT` | side facts only; `records_ref=none` |

Every terminal path closes readers, writers, SQLite handles and temporary spools before publishing its
status. A failed provider is not silently replaced by Python when Rust is selected.

## 5. Fixture, marker and benchmark freeze

Fixture families:

- initial snapshot, missing baseline and FULL pair aggregation;
- identity SAME/DIFFERENT/UNVERIFIABLE/NOT_APPLICABLE and continuation revalidation;
- standard keyed/keyless/schema/type/nullability/typed-null cases;
- ordered content/move/position/replay cases;
- blank provenance, reserved gid range, ignored payload and interval occupancy;
- UPDATE_ONLY suppressed counts and FieldChange derivation;
- records Parquet schema, manifest/closure, corruption and atomic publication;
- HASH/SQLite and Python/Rust canonical equivalence;
- budget, cancellation, writer failure and cache restore/revalidation.

Frozen roots and owners:

```text
vnext/fixtures/golden/comparison/       # cross-provider semantic goldens; R5 owns
vnext/fixtures/vectors/comparison/      # language-neutral Arrow/Parquet vectors; R5 owns
vnext/backend/tests/test_comparison*.py
vnext/backend/tests/test_comparison_records*.py
vnext/backend/tests/test_comparison_artifacts*.py
vnext/backend/tests/test_comparison_cache*.py
vnext/backend/tests/support/comparison_*.py
```

The first fixture manifest is a module-level parameter table, not one test per malformed shape:
`PAIR_APPLICABILITY_CASES`, `IDENTITY_GATE_CASES`, `SCHEMA_ALIGNMENT_CASES`,
`KEYLESS_MATCH_CASES`, `ORDERED_RECORD_CASES`, `BLANK_INTERVAL_CASES`, `RECORDS_CLOSURE_FAULTS`,
`RESOURCE_BOUNDARY_CASES` and `CACHE_REBIND_CASES`. Test names describe contract behavior.

Markers are frozen as follows: pure contracts/kernels/digests/artifact validation are `unit`; real
Dolt/Repository readers are `integration`; fixed `Event.wait`, `join`, stream timeout or cancellation
latency tests are `serial` and run with `-n 0`. No hand-written dolt `skipif` gate is permitted, and
pure parsing/validation tests must not create a real Dolt repository.

Benchmark profiles are measurement fixtures only and use deterministic IDs/seeds:

| Profile | Shape | Required runs |
| --- | --- | --- |
| `comparison_tiny` | 4 tables, 32 rows, keyed/keyless/schema/blank boundary mix | HASH, SQLite, Python reference |
| `comparison_small` | 16 tables, 10,000 rows, 10% changed rows | HASH, SQLite, Python reference |
| `comparison_medium` | 64 tables, 250,000 rows, 10% changed rows | forced HASH, forced SQLite, AUTO |
| `comparison_large` | 128 tables, 2,000,000 rows, 10% changed rows | forced HASH, forced SQLite, AUTO; bounded run only |

Each record identifies profile ID/revision, seed, before/current snapshot digests, provider, internal
mode, cold/cache state, contract versions, runtime caps, wall duration, CPU time, peak RSS, spill
bytes, artifact bytes, record count, diagnostics count and cancellation latency. Correctness is
checked before metrics are reported. Results are not a performance gate, are not a legacy comparison,
and do not authorize implementation.

Benchmark workload records dataset identity/scale, cold/cache, provider/runtime mode, duration,
CPU/RSS, spill, artifact bytes, record count and cancellation latency. It creates measurements only;
no fixed pass threshold or automatic implementation gate is defined here.

## 6. Allowlist, forbidden imports and reopen

Initial R5 allowlist is the paths in the execution plan §3. Rust/native changes are allowed only in
the existing compute core/PyO3 boundary and trigger Rust policy/build gates. No HTTP, business flow,
Repository/Dolt, risk/static-risk, surface/bundle or Operation Runtime production integration.

The R5 capability may depend only on `gateway_backend.artifacts`, Shared Canonical Encoding public
primitives, `snapshot_materialization.contracts`, and the immutable project-identity contract. It must
not import `snapshot_materialization._digest`, `_parquet`, `_reader`, `_catalog`, `_ruleset`, `_archive`,
`_paths`, `_ast` or `_bind`; `tests/support`, `legacy`, `gateway_repository_service`, `dolt`, HTTP,
Workspace, Submit, Operation Runtime and host-path helpers are forbidden production imports.

Reopen S0 if public batch access requires private R3/R4 imports, public DTOs expose runtime objects or
host paths, Rust/Python outputs cannot share canonical schema/digest, numeric budgets are copied from
parser owners, cache can bypass policy, or any forbidden production dependency appears.

## 7. S0 exit evidence and checklist

The S0 deliverables are complete in this record and the execution plan §5. No implementation code was
authorized or changed.

- [x] accepted design baseline and execution phase list;
- [x] public/private type ownership and discriminated result union;
- [x] identity/applicability matrix and continuation/submit bit separation;
- [x] Arrow/Parquet/IPC language-neutral boundary;
- [x] exact bounded budget values and inherited-owner references;
- [x] fixture roots, markers, benchmark workload and evidence format;
- [x] allowlist, forbidden imports and reopen conditions;
- [x] implementation authorization remains separately `no`.

S0 must be reopened before S1 if any public batch method requires a private R3/R4 import, a public DTO
exposes a runtime object or host path, Python/Rust cannot share canonical schema/digest, a cap is changed
without owner evidence, an identity status can be caller-forged, a cache restore bypasses policy, or a
forbidden production dependency appears. Reopen is also required for any new service/helper/security
principal, JSONL public artifact, automatic provider fallback, or container/deployment boundary.
