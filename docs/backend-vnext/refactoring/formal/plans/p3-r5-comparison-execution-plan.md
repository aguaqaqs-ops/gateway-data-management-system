# P3-R5 Comparison Execution Plan

状态：Accepted for staged planning；S0/S1/S2/S3/S4/S5/S6/S7 scoped complete；implementation authorization pending

日期：2026-08-21

阶段：P3-R5 Comparison

Owner：Backend vNext Comparison Capability

设计基线：[P3-R5 Comparison Design Baseline](p3-r5-comparison-design.md)

入口：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)

S0：[P3-R5-S0 Entry and Budget Freeze](p3-r5-s0-entry-and-budget-freeze.md)

本文定义 R5 的 staged execution、conversation boundaries、allowlist、review gates 和 handoff
evidence。S1 的 public batch boundary/provider-port 实现由本次明确任务授权并已完成；本文不因
此自动授权 S2-S8 production implementation。后续阶段仍需另有明确
`p3_implementation_authorized: yes` 或等价的阶段授权记录。

## 1. Objective and exit

R5 将 immutable before/current `SnapshotTableArtifact` / public reader closure 转换为稳定的
`ComparisonFacts` 和可选 `ComparisonRecordsClosure`，供后续 capability 消费。

R5 exit 必须证明：

- pair planning、identity applicability 和 `UNVERIFIABLE` continuation boundary 不越权；
- standard、ordered、blank、schema、keyless 和 typed records 语义满足设计基线；
- Python/Rust 共享 Arrow/Parquet boundary，禁止逐 row FFI 和无界 Python object materialization；
- HASH/SQLite 或 Python reference/Rust provider 在 canonical facts、records digest、counts 上等价；
- records manifest、closure、digest、publication 和 cancellation fail-closed；
- neutral core cache restore 不绕过 identity/policy/submit binding；
- no HTTP、Workspace、Submit、Repository/Dolt、Operation Runtime 或旧实现 production dependency；
- focused review、independent review、module gate 和 handoff evidence 完整。

## 2. Conversation policy

每个阶段的上下文策略是执行合同的一部分：

| Step | 内容 | 对话策略 | 原因 |
| --- | --- | --- | --- |
| S0 | entry、applicability、contract/budget/benchmark freeze | 新开 R5 entry 对话 | 清理 R4 过程上下文，只携带设计基线、R4 handoff 和正式 contracts |
| S1 | language-neutral batch boundary、provider port、Arrow/FFI contract | 与 S0 同一对话 | S0 决策直接决定 batch reader、provider interface 和 allowlist |
| S2 | pair input binding、pair planning、identity gate | 新开 implementation 对话 | 与数据面 kernel 隔离，专注 flow-neutral input boundary |
| S3 | standard comparison core、schema/key、digest | 与 S2 同一 implementation 对话 | planner 输出直接驱动 table task 和 standard core |
| S4 | ordered/blank extensions | 新开 integrity 对话 | 特殊语义风险高，避免被 standard core 的实现细节带偏 |
| S5 | records Parquet、manifest、closure、publication | 新开 artifact/integrity 对话 | 独立审查字节、artifact 和原子发布，不依赖 kernel 口述 |
| S6 | neutral core cache restore | 新开 cache/recovery 对话 | cache 不得把授权和 operation 状态带入 core |
| S7 | focused review、independent review | 新开 review 对话 | reviewer 不依赖 implementer 解释；S7 与 S6/S8 隔离 |
| S8 | module gate、sealed SHA、R5 handoff | 新开 acceptance/documentation 对话 | 汇总证据并冻结下一阶段入口 |

Finding remediation 不单独创建 round：finding 返回所属实现对话修复，补 regression fixture 和
focused rerun，再回到原 review 对话复核。P1/P2、contract ambiguity、digest mismatch、row loss、
resource/recovery failure 或 hidden dependency 必须关闭或 reopen owner 后才能前进。

## 3. Scope and forbidden paths

### 3.1 Allowed implementation paths

```text
vnext/backend/src/gateway_backend/capabilities/comparison/
vnext/backend/src/gateway_backend/artifacts/
vnext/backend/src/gateway_backend/cache/
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/  # only approved public batch boundary changes
vnext/backend/tests/test_comparison*.py
vnext/backend/tests/test_comparison_records*.py
vnext/backend/tests/test_comparison_artifacts*.py
vnext/backend/tests/test_comparison_cache*.py
vnext/backend/tests/support/comparison_*.py
vnext/fixtures/golden/comparison/
vnext/fixtures/vectors/comparison/
docs/backend-vnext/refactoring/formal/plans/p3-r5-*.md
docs/backend-vnext/refactoring/formal/contracts/comparison*.md  # only when S0 identifies contract correction
docs/backend-vnext/contracts/comparison*.md                  # only with owner review
```

Rust data-plane changes, if S1 or benchmark evidence requires them, are limited to the existing
`vnext/rust/gateway-compute-core/` and `gateway-compute-python` boundary plus their tests and required
lock/build metadata. A Rust change triggers the Rust policy gates and relevant image/build verification.

### 3.2 Forbidden in R5

```text
HTTP/API route activation
Workspace/Submission/Archive/Preview business state
Submit or confirmation persistence implementation
Repository Service/Dolt read/write or SQL execution
Operation Runtime production integration
Risk provider rules or static-risk implementation
Surface/Bundle production integration
legacy/ production imports
host paths in public identity
new service/helper/security principal
automatic Python fallback for a failed Rust provider
JSONL as a public records artifact
```

R5 may define ports and test doubles for downstream seams, but must not activate them in production.

## 4. Owner graph and data flow

```text
trusted flow/orchestrator
  -> PairExecutionInput
  -> comparison planning / identity applicability already resolved
  -> batch reader closure
  -> standard / ordered / blank kernel
  -> TableComparisonResult
  -> PairFactsDraft
  -> records writer + manifest
  -> publication gate
  -> immutable ComparisonFacts + ComparisonRecordsClosure
  -> future risk / surface / bundle consumers
```

Ownership:

| Object/capability | Owner | R5 rule |
| --- | --- | --- |
| SnapshotTableArtifact / reader | R3 snapshot materialization | consume public closure only |
| batch reader / Arrow boundary | R3 public reader owner with R5 consumer review | no private Parquet inference |
| ProjectIdentityAssessment | identity capability | consume immutable assessment only |
| pair-set aggregation | application/flow owner | R5 only handles one pair |
| comparison facts/records | R5 comparison | sole semantic owner |
| records artifact/closure | artifact support + R5 | no operation/business state |
| neutral core cache | cache support + R5 | no authorization state |
| risk/surface/bundle | downstream capabilities | no production integration |

## 5. Staged steps

### S0 — Entry, applicability, contract, budget and benchmark freeze

Conversation: new R5 entry conversation.

Deliverables:

- `p3-r5-s0-entry-and-budget-freeze.md` accepted;
- public type/field owner and version table;
- `PairExecutionInput` applicability matrix;
- Python/Rust batch boundary and provider-port decision;
- exact inherited input budgets plus pair/table/runtime/records/spill budgets;
- fixture roots, marker policy, benchmark workload and output metrics;
- architecture allowlist/forbidden imports and reopen conditions.

Exit: **pass**；no architecture-level ambiguity remains. `p3_implementation_authorized` remains
`no` until a separate explicit authorization record is accepted.

S0 authority and sealed decisions are recorded in
[p3-r5-s0-entry-and-budget-freeze.md](p3-r5-s0-entry-and-budget-freeze.md). That record is the
owner for the exact applicability matrix, public field ownership, `PairExecutionResult` tags, Arrow /
Parquet boundary, inherited R2/R3 limits, R5 execution caps, failure matrix, fixture roots and
benchmark output shape. S1 may implement those decisions but may not reinterpret them; any change goes
through the S0 reopen conditions and an owner-reviewed contract correction.

### S1 — Language-neutral batch boundary and provider port

Conversation: same as S0.

Objective: eliminate a future requirement for Python row-object materialization without prematurely
creating a compute service.

Deliverables:

- public batch access protocol, preferably Arrow `RecordBatchReader` or equivalent;
- schema metadata for scalar encoding, projection, ordered/blank and artifact versions;
- provider-neutral kernel port for Python reference and Rust production provider;
- coarse-grained PyO3/Arrow adapter contract, GIL release and stable native error mapping;
- tiny Python/Rust round-trip goldens; `iter_rows()` retained only for reference/small fixtures unless
  S0 explicitly reopens R3 reader ownership.

Exit: one table/batch can cross the boundary without `to_pylist()`, per-row FFI or JSON bulk encoding;
semantic digest remains language-neutral.

S1 status: **complete**. The public boundary is implemented additively in the R3 snapshot
materialization surface and consumed through R5 `.contracts` only:

- `SnapshotTableBatchMetadata` freezes scalar, projection, ordered, blank and artifact versions in
  Arrow schema metadata;
- `SnapshotTableBatchReader` exposes `schema()`, `metadata()`, `iter_record_batches()`, `reopen()`
  and `close()`; `ParquetSnapshotTableBatchReader` uses `ParquetFile.iter_batches()` and never calls
  `to_pylist()`;
- `SnapshotTable.batch_reader` is optional so existing `iter_rows()` reference/small-fixture paths
  remain compatible;
- `ComparisonBatchProvider` is a coarse-grained provider port. `PythonReferenceBatchProvider` is
  reference-only and `RustArrowBatchProvider` accepts an injected native callable, keeping the
  comparison capability independent from `gateway_backend.compute`;
- the existing `pyo3-arrow` adapter remains the native boundary: it imports/exports one Arrow stream,
  releases the GIL around parse/compute, catches native panics and maps stable error codes.

S1 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/batch.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_parquet.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/artifact.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py
vnext/backend/src/gateway_backend/capabilities/comparison/provider.py
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py
vnext/backend/tests/test_comparison_batch_boundary.py
vnext/backend/tests/test_architecture.py
```

S1 evidence is recorded below in §6.1. No comparison facts, pair planning, records semantics or
production flow integration is part of this step.

### S2 — Pair input binding, planning and identity applicability

Conversation: new implementation conversation.

Objective: create executable pair tasks without importing flow state.

Deliverables:

- validated `PairExecutionInput` and `PairExecutionResult` discriminated union;
- `INITIAL_SNAPSHOT`, `FULL` pair roles, baseline reconstruction result and `NOT_APPLICABLE` history/
  archive context;
- `SAME_PROJECT`, `DIFFERENT_PROJECT`, `UNVERIFIABLE` assessment binding;
- continuation gate input validation, without actor/session authorization logic inside core;
- table plan and `TableComparisonTask` generation.

Exit: invalid combinations fail before reader open; replacement never enters detailed planner;
unverifiable confirmation is required before any comparison execution.

S2 status: **complete**. This is an S2-only implementation authorization; the global
`p3_implementation_authorized` value remains `no`, and S3-S8 remain unauthorized.

S2 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py
vnext/backend/src/gateway_backend/capabilities/comparison/pair_planning.py
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py
vnext/backend/tests/test_comparison_planning.py
```

The implementation consumes immutable snapshot metadata, baseline reconstruction output and the
read-only identity assessment port. It does not implement identity production, actor/session policy,
reader lifecycle, row materialization or detailed comparison kernels.

### S3 — Standard comparison core and semantic digest

Conversation: same as S2 implementation conversation.

Objective: implement neutral keyed/keyless standard comparison.

Deliverables:

- schema alignment and selected comparison columns;
- effective key and explicit keyless multiset policy;
- canonical scalar/null/type handling and opaque row identity;
- `ROW_ADDED`, `ROW_DELETED`, `ROW_MODIFIED`, `SCHEMA_CHANGE` and derived `FieldChange`;
- `UPDATE_ONLY` suppressed counts;
- table facts, summary, `facts_core_digest` and final `comparison_digest` envelope;
- Python reference fixtures and Rust differential fixtures where Rust is enabled.

Exit: standard canonical facts and counts are deterministic; key changes never become fake updates;
HASH/SQLite/reference/provider paths agree on semantic outputs.

S3 status: **complete**. This is an S3-only implementation authorization; the global
`p3_implementation_authorized` value remains `no`, and S4-S8 remain unauthorized.

S3 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py
vnext/backend/src/gateway_backend/capabilities/comparison/pair_planning.py
vnext/backend/src/gateway_backend/capabilities/comparison/standard.py
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py
vnext/backend/tests/test_comparison_standard.py
```

The implementation consumes immutable `ComparisonTablePolicy` bindings and public snapshot readers;
it does not import table-rules or snapshot-materialization private modules. S5 remains responsible for
records Parquet, manifests and closure publication; S6 remains responsible for neutral cache behavior.
The current source SHA is `d61199f3b4a3425272b7b152da3dd16142542770`. Focused verification passed with
51 tests; full unit verification reported 584 passed and 58 pre-existing legacy-oracle failures in
`tests/test_table_rules_resolver.py` because the repository lacks the referenced `legacy/backend_vnext`
paths/symbols. `ruff check .` and `mypy` passed. No Rust, dependency, Dockerfile, Compose, entrypoint or
runtime-boundary path changed, so Docker rebuild is deferred.
The current Rust/provider seam is still the S1 coarse Arrow pass-through and no semantic native
provider is enabled in this checkout; S3 therefore validates the Python reference semantic contract
and leaves native differential execution for the stage where that provider is enabled.

### S4 — Ordered and blank extensions

Conversation: new integrity conversation.

Objective: add special semantics without changing standard row identity.

Deliverables:

- stable-key content/move separation and replay guarantee;
- `ORDERED_POSITION_CHANGED`, ordered move/content records;
- reserved pseudo gid source validation and trusted canonical provenance;
- blank payload ignore rule, interval occupancy/count comparison;
- `BLANK_DELETE_INTERVAL` and `BLANK_INSERT_INTERVAL`, no move pairing;
- independent typed ordered and blank record schemas.

Exit: ordered/blank fixtures prove no positional fallback, no blank payload diff, no pseudo gid business
identity and deterministic digest behavior.

S4 status: **complete**. This is an S4-only implementation authorization; the global
`p3_implementation_authorized` value remains `no`, and S5-S8 remain unauthorized.

S4 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py
vnext/backend/src/gateway_backend/capabilities/comparison/ordered.py
vnext/backend/src/gateway_backend/capabilities/comparison/standard.py
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/batch.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_parquet.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/artifact.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/materialize.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/repository_ref.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/tests/test_comparison_ordered.py
vnext/backend/tests/test_comparison_blank.py
vnext/backend/tests/test_snapshot_artifact_roundtrip.py
```

The ordered reference kernel keeps stable-key row identity separate from content, relative move and
absolute position changes; it rejects positional fallback, duplicate/missing order facts and
reserved SQL pseudo gids. The blank kernel uses real-row backbone intervals, ignores blank payload,
does not create ordinary identity/move records, and preserves suppressed interval counts under
`UPDATE_ONLY`. Ordered/blank canonical payload is included in table and facts-core digests while
diagnostics and physical references are excluded. SQL, canonical repository and derived snapshot
tables now carry explicit blank provenance through `SnapshotTable`, Arrow metadata and artifact
manifests; `PSEUDO_BLANK` interpretation is accepted only for canonical provenance.

The tested source/base SHA is `d61199f3b4a3425272b7b152da3dd16142542770`; S4 remains uncommitted in
the shared worktree, so this is not a post-change sealed commit SHA. No Rust semantic provider,
Parquet records publication, cache, Docker or repository execution was added.

### S5 — Records artifacts, closure and publication

Conversation: new artifact/integrity conversation.

Objective: turn complete table streams into immutable public artifacts.

Deliverables:

- typed per-table Parquet standard/ordered/blank artifacts;
- `RecordsArtifactManifest` and `ComparisonRecordsClosure`;
- canonical sort, record/content/manifest/closure digest;
- operation-local ref rewriting without semantic digest changes;
- bounded writer/spool, cancellation, cleanup and atomic publication gate;
- replacement `records_ref=none` and initial snapshot no-record behavior.

Exit: incomplete or corrupt closure cannot publish facts/READY; complete closure reopens identically
from Python and Rust readers.

S5 status: **scoped complete**. This is an S5-only implementation authorization; the global
`p3_implementation_authorized` value remains `no`, and S6-S8 remain unauthorized.

S5 changed-path inventory:

```text
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py       # records public contracts
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py        # public exports
vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py       # Parquet/manifest/closure gate
vnext/backend/tests/test_comparison_records.py                                # logical records/typed values
vnext/backend/tests/test_comparison_artifacts.py                              # round-trip/tamper/budget tests
vnext/fixtures/vectors/comparison/records/standard-v1.parquet.b64              # Python/Rust golden vector
vnext/rust/Cargo.toml
vnext/rust/Cargo.lock
vnext/rust/gateway-compute-core/Cargo.toml
vnext/rust/gateway-compute-core/src/lib.rs
vnext/rust/gateway-compute-core/src/records.rs                                # language-neutral reader
```

The publication gate validates the facts and each table/family record stream, canonical-sorts rows,
writes bounded Parquet, computes logical content digests, reopens every stored Parquet and manifest,
then writes and reopens the canonical closure JSON before attaching its operation-local ref to
`ComparisonFacts.records_ref`. `INITIAL_SNAPSHOT`, `DATASET_REPLACEMENT`, `CANCELLED` and `FAILED`
remain without a records ref/closure. Manifest bytes deliberately do not contain `comparison_digest`;
closure metadata layers comparison/facts-core digests without a cycle. Ref rewriting only changes
operation-local refs and the derived closure digest.

S5 implementation evidence is recorded in §6.4. The S5 worktree is dirty and the current base HEAD
`d61199f3b4a3425272b7b152da3dd16142542770` is not a sealed S5 SHA. Rust/Cargo changes require the
backend image gate; Docker daemon availability is recorded as deferred rather than claimed passed.

### S6 — Neutral comparison core cache

Conversation: new cache/recovery conversation.

Objective: add reuse only after cold correctness and closure are stable.

Deliverables:

- pair-level neutral cache key/value and validation status;
- cache lookup, manifest/content validation and restore through operation-local closure;
- mode/identity/assessment/continuation re-binding after restore;
- cache diagnostics and disabled/cold path equivalence;
- no replacement reuse and no authorization/submit state in cache.

Exit: cache hit and cold run produce identical canonical facts, records manifests and counts; cache hit
cannot bypass confirmation or policy recheck.

S6 status: **scoped complete**. This is an S6-only implementation authorization; the global
`p3_implementation_authorized` value remains `no`, and S7-S8 remain unauthorized.

S6 implementation adds the in-process `gateway_backend.cache.comparison_core` pair cache. Its key is
JCS-digested over directed snapshot, contract, ruleset, projection, scalar, ordered/blank, requested
table, option, scope and algorithm inputs. Its value contains only detailed canonical facts and a
validated cache-local records closure with `CacheTrustLevel`; no pair, operation, workspace,
authorization, submit or host-path identity is retained. Cache restore reopens and validates every
manifest/Parquet artifact, copies them into an operation-local artifact scope, rewrites only refs,
and rebinds the fresh detailed identity/continuation context. Replacement mode is rejected.

### S7 — Focused and independent review

Conversation: new focused review, then new independent review.

Review focus:

- public-only R4 input and forbidden imports;
- Python/Rust Arrow/Parquet equivalence and no row-object FFI;
- standard/schema/keyless/ordered/blank semantics;
- typed nulls, digest layering and no digest cycle;
- bounded budgets, cancellation, partial artifact cleanup;
- cache restore authorization boundary;
- fixture marker/performance policy compliance.

Exit: no unclosed P1/P2, contract ambiguity, digest mismatch, hidden dependency or unbounded path.

S7 status: **scoped complete; focused and independent review PASS**. Two P2 artifact-read budget
findings were remediated in the owning artifact boundary and re-run below. The review does not grant
the global `p3_implementation_authorized` flag, production flow integration or the deferred native
semantic provider.

### S8 — R5 module gate and handoff

Conversation: new acceptance/documentation conversation.

Required evidence:

- sealed tested source SHA and changed-path inventory;
- exact commands/results for backend unit, focused tests, ruff/mypy and Rust gates if applicable;
- Python/Rust golden/differential and Arrow/Parquet round-trip evidence;
- benchmark metrics without fixed performance gate;
- S7 findings closure, deferred/reopen register and container decision;
- R5 input contract, downstream seam status and implementation authorization.

Exit: `p3_r5_exit: pass` and next-stage readiness may be recorded only after closure validation;
`p3_implementation_authorized` is not changed by this plan.

## 6. Verification policy

- Pure comparison, digest, records, cache validation and Arrow schema tests are unit tests.
- Real Dolt/Repository reader tests are integration tests; fixed timeout tests are serial.
- Python/Rust changes run applicable ruff/mypy and Rust policy commands.
- Docker rebuild is deferred for pure Python/docs/test changes, but required for Rust/native dependency,
  lockfile, Dockerfile, image, entrypoint or container-only runtime changes, and at final candidate gate.
- Benchmark records workload, cold/cache, provider mode, duration, CPU/RSS, spill, artifact bytes,
  records count and cancellation latency; it does not automatically create a performance gate.

### 6.1 S1 verification record

The following commands were run against the current worktree. They validate the public batch surface,
architecture edge, artifact round-trip and existing native Arrow/PyO3 boundary; no Dolt or HTTP flow is
required.

| Command | Result |
| --- | --- |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline pytest -q -m unit tests/test_comparison_batch_boundary.py tests/test_architecture.py tests/test_snapshot_artifact_roundtrip.py tests/test_snapshot_materialization_contracts.py` | **29 passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline ruff check .` | **passed** |
| `cd vnext/backend && UV_CACHE_DIR=/tmp/gateway-data-uv-cache uv run --offline mypy` | **passed** |
| `cd vnext/rust && cargo fmt --all -- --check` | **passed** |
| `cd vnext/rust && cargo test -p gateway-compute-core` | **78 passed** |
| `cd vnext/rust && cargo test -p gateway-compute-python` | **3 passed** |
| `cd vnext/rust/gateway-compute-python && /root/gateway-data-management-system/vnext/backend/.venv/bin/python -m pytest -q` | **4 passed** |
| sealed S1 code SHA (2026-08-20 confirmatory rerun) | **2963963c9cb707c9584aac8778eb07e8d6d40782** |

S1 is pure Python/public-boundary and test work plus reuse of the already-built native boundary. No
Dockerfile, dependency lock, image, entrypoint, Compose or container-only runtime boundary changed;
container rebuild is therefore deferred to a later Rust/dependency/image change or the final candidate.

### 6.2 S2 verification record

The following commands were run against the S2 worktree. They cover the pure pair-binding/planning
contracts, the S1 batch boundary and architecture import DAG; no Dolt, HTTP or flow runtime is used.

| Command | Result |
| --- | --- |
| `cd vnext/backend && .venv/bin/pytest -q -m unit tests/test_comparison_planning.py tests/test_comparison_batch_boundary.py tests/test_architecture.py` | **35 passed** |
| `cd vnext/backend && .venv/bin/pytest -q -m unit tests/test_comparison_planning.py` | **13 passed** |
| `cd vnext/backend && .venv/bin/pytest -q -m unit` | **568 passed, 58 failed**; all failures are the pre-existing legacy oracle loading `legacy/backend_vnext/...` paths absent from this checkout |
| `cd vnext/backend && .venv/bin/ruff check src/gateway_backend/capabilities/comparison tests/test_comparison_planning.py` | **passed** |
| `cd vnext/backend && .venv/bin/mypy src tests/test_comparison_planning.py` | **passed** |
| current base HEAD | `d61199f3b4a3425272b7b152da3dd16142542770` (S2 changes remain uncommitted in the worktree) |
| S2 container rebuild | **deferred**; pure Python/contracts/tests/docs only, no image or deployment boundary changed |

S2 result status correction: `INITIAL_SNAPSHOT` uses `NOT_APPLICABLE`; `DIFFERENT_PROJECT` returns
`DATASET_REPLACEMENT` without detailed tasks or records closure; `UNVERIFIABLE` without a valid
continuation returns `IDENTITY_GATE_BLOCKED` before reader access. The source SHA above identifies the
current base revision; a sealed S2 SHA requires the later documentation/implementation commit.

### 6.3 S4 verification record

The following checks cover ordered/blank semantics, SQL and canonical blank provenance, digest
stability, Arrow/artifact round-trip, existing standard comparison behavior and architecture imports.
They are pure Python unit checks; no Dolt, Rust semantic provider or container boundary is involved.

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit -q tests/test_comparison_ordered.py tests/test_comparison_blank.py tests/test_comparison_standard.py tests/test_comparison_batch_boundary.py tests/test_snapshot_artifact_roundtrip.py tests/test_architecture.py` | **63 passed** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| tested source/base SHA | `d61199f3b4a3425272b7b152da3dd16142542770` (S4 changes remain uncommitted in the worktree) |
| S4 container rebuild | **deferred**; Python contracts/kernel/tests/docs and public snapshot metadata only, with no image or deployment boundary change |

The focused suite covers ordered content-only, move-only, content-plus-move and absolute renumber;
no positional fallback, stable-key/order ambiguity degradation, ignored columns, SQL reserved-gid
rejection, canonical pseudo-blank provenance, blank payload/occupancy semantics, `UPDATE_ONLY`
suppression, deterministic digests and artifact/batch metadata preservation. S5-S8 deliverables
remain out of scope.

### 6.4 S5 verification record

The S5 focused gate covers standard/ordered/blank family schemas, canonical ordering, `UPDATE_ONLY`,
empty detailed closure, typed null/binary/float-bits/decimal/temporal values, detail policies,
manifest/closure digest layering, duplicate/tampered/truncated artifacts, store and budget failures,
cancellation fail-closed behavior, replacement/initial-snapshot ref absence and operation-local ref
rewriting. The Rust fixture reads the Python-produced Parquet with Arrow/Parquet 59.1.0 and recomputes
the same logical content digest.

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit -q tests/test_comparison_records.py tests/test_comparison_artifacts.py tests/test_comparison_standard.py tests/test_comparison_ordered.py tests/test_comparison_blank.py tests/test_comparison_planning.py tests/test_comparison_batch_boundary.py tests/test_snapshot_artifact_roundtrip.py tests/test_architecture.py` | **97 passed** |
| `cd vnext/backend && uv run pytest -m unit` | **625 passed, 58 pre-existing legacy-oracle failures, 1 warning**; failures are absent `legacy/backend_vnext` paths/symbols in `tests/test_table_rules_resolver.py` |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| `cd vnext/rust && cargo fmt --all -- --check` | **passed** |
| `cd vnext/rust && cargo clippy -p gateway-compute-core --all-targets -- -D warnings` | **passed** |
| `cd vnext/rust && cargo test -p gateway-compute-core` | **82 passed** across unit/integration suites; **0 failed** |
| `cd vnext/rust && cargo test -p gateway-compute-python` | **3 passed** |
| Python/Rust golden vectors | **STANDARD 1 row `sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4`; ORDERED 1 row `sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b`; BLANK 2 rows `sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a` — all equal** |
| tested base HEAD | `d61199f3b4a3425272b7b152da3dd16142542770`; worktree **dirty**, therefore not a sealed S5 SHA |
| S5 backend image rebuild | **required but deferred**: `vnext/backend/Dockerfile` copies/builds `vnext/rust` and Cargo/Parquet changed; `docker info` cannot connect to `/var/run/docker.sock`; image revision **none**, source tree is the dirty candidate above |

Failure/deferred register:

- The full unit failures are the known legacy-oracle fixture gap and are not an S5 regression.
- The backend image rebuild and container gate remain pending until a Docker daemon is available; the
  candidate must rebuild `vnext/backend/Dockerfile` from the dirty-worktree candidate and rerun the
  relevant container gates before any sealed handoff.
- S6 cache, S7 review and S8 final handoff remain intentionally unimplemented and unauthorized.
- Store objects written before a later publication failure are unreferenced orphans by contract; no
  orphan is returned to a consumer, and lifecycle reclamation is outside S5.

### 6.5 S6 verification record

The S6 focused gate covers cache key canonicalization and semantic invalidation, cache trust bounds,
disabled/miss behavior, standard/ordered/blank/empty closure restore, manifest/content/closure
tamper rejection, operation-local ref rewriting, `SAME_PROJECT` and `NOT_APPLICABLE` rebinding,
fail-closed `UNVERIFIABLE` continuation policy revalidation, and `DATASET_REPLACEMENT` rejection.
The facts context fields (`comparison_mode`, `project_identity_status`, `assessment_digest`) are
rebound without changing semantic facts or records digests.

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit -q tests/test_comparison_cache.py tests/test_comparison_artifacts.py tests/test_comparison_records.py tests/test_comparison_standard.py tests/test_comparison_ordered.py tests/test_comparison_blank.py tests/test_comparison_planning.py tests/test_comparison_batch_boundary.py tests/test_snapshot_artifact_roundtrip.py tests/test_architecture.py` | **109 passed** |
| `cd vnext/backend && uv run pytest -m unit` | **637 passed, 58 pre-existing legacy-oracle failures, 1 warning**; failures remain confined to missing/incompatible `legacy/backend_vnext` fixtures in `tests/test_table_rules_resolver.py` |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| tested source/base SHA | `d61199f3b4a3425272b7b152da3dd16142542770`; worktree **dirty**, therefore not a sealed S6 SHA |
| S6 container rebuild | **deferred**; S6 changed Python cache/contracts/tests/docs only and did not add a new image/native boundary; the inherited S5 Rust/Cargo image gate remains pending |

S6 changed-path inventory:

```text
vnext/backend/src/gateway_backend/cache/__init__.py
vnext/backend/src/gateway_backend/cache/comparison_core.py
vnext/backend/src/gateway_backend/capabilities/comparison/__init__.py
vnext/backend/src/gateway_backend/capabilities/comparison/artifacts.py
vnext/backend/src/gateway_backend/capabilities/comparison/contracts.py
vnext/backend/src/gateway_backend/capabilities/comparison/standard.py
vnext/backend/tests/test_comparison_cache.py
```

The S6 candidate is not a sealed handoff: the worktree includes prior S1-S5 changes, and the inherited
backend image rebuild is still unavailable because Docker is not connected. S7 review is recorded in
§6.6; the S8 module gate remains pending.

### 6.6 S7 focused and independent review record

本轮 review 独立重读 R5 design baseline、S0 contract/budget freeze、S1-S6 implementation surface、
comparison/artifact/cache contracts、累计 diff、Arrow/Parquet fixtures 和 capability import
graph。不依赖实现者口头解释；finding 修复返回 artifact owner 后只做 focused rerun，再重新审查
当前 source tree。

#### Review boundary

- public-only R4 snapshot input、comparison capability import DAG 和 forbidden HTTP/Workspace/
  Submit/Repository/Dolt/Operation Runtime/legacy dependencies；
- Arrow batch metadata/provider port、Parquet records schemas、Python/Rust golden vectors 和
  no per-row FFI or JSON bulk boundary；
- standard/schema/keyed/keyless/ordered/blank semantics, typed nulls, `UPDATE_ONLY`, canonical
  ordering and digest/facts-core/closure layering without a cycle；
- artifact manifest/closure readback, record-count/byte/spool budgets, cancellation/failure mapping,
  operation-local ref rewriting and partial publication behavior；
- neutral cache key/value validation, closure restore, identity/continuation/policy rebinding,
  replacement rejection, host-path/flow/authorization exclusion；
- test markers, fixed-timeout policy, architecture scan, full unit/static checks and the inherited
  Rust/container gate boundary.

#### Evidence

| Check | Result |
| --- | --- |
| focused comparison/artifact/cache/architecture suite | **112 passed** |
| `cd vnext/backend && uv run pytest -m unit -q` | **698 passed, 1 existing Starlette deprecation warning** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 155 source files |
| `git diff --check` | **passed** |
| reviewed comparison test marker/timeout scan | **passed**; no `integration`/`serial` marker or fixed process/stream timeout |
| `cd vnext/rust && cargo fmt --all -- --check` | **passed** |
| `cd vnext/rust && cargo clippy -p gateway-compute-core --all-targets -- -D warnings` | **passed** |
| `cd vnext/rust && cargo test -p gateway-compute-core` | **82 passed, 0 failed** |
| `cd vnext/rust && cargo test -p gateway-compute-python` | **3 passed, 0 failed** |
| reviewed source tip | `b39ebe3126e935cf027d4f7256dc4fafb74d1035` plus the dirty S7 remediation below; not a sealed SHA |

The Python/Rust evidence covers Arrow/Parquet records vectors and the existing coarse Arrow provider
port. No semantic Rust comparison provider is enabled in this checkout; the Python kernels remain the
small/reference path and production-scale native differential execution stays deferred under S0/S3.
This is recorded as a scope boundary, not as evidence of an enabled production provider.

#### Findings register

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| `S7-001` | **P2** | `open_records_closure()` and `read_records_artifact()` validated artifact bytes and then materialized all Parquet rows without enforcing the frozen `max_records_per_table` budget. A valid artifact over the per-table cap was accepted, and cache restore could repeat the unbounded row-object materialization. | Closed in the artifact owner: Parquet footer row count is checked against the policy before `read()`/`to_pylist()`, closure/manifest entry counts are checked at the same boundary, and `test_reopen_rejects_records_over_per_table_limit_before_materialization` passes. |
| `S7-002` | **P2** | The frozen `max_records_per_table` budget was applied independently to standard/ordered/blank closure entries. A table containing multiple record families could exceed the table cap while every individual artifact remained below it. | Closed in the artifact owner: publication and closure reopen aggregate `record_count` by table before writing or reading any Parquet; `test_publish_rejects_combined_record_families_over_table_limit` and `test_reopen_rejects_combined_record_families_over_table_limit` pass. |

No other P1/P2, contract ambiguity, digest mismatch, hidden dependency, forbidden import, partial
publication or marker violation was found. The existing S5 Docker/image gate remains deferred because
Docker is unavailable and the current candidate includes inherited Rust/Cargo changes; no container
pass is claimed here. The known missing `legacy/backend_vnext` oracle is not present in the current
unit result (the focused/full unit commands above are green), but remains outside R5 ownership if it
reappears in a different checkout.

#### Boundary disposition and decision

| Area | Result | Independent evidence |
| --- | --- | --- |
| public input/import boundary | **Pass** | architecture tests and source scan; comparison imports only public contracts and no forbidden runtime/repository modules |
| comparison semantics/digests | **Pass for staged Python reference surface** | standard/ordered/blank/key/schema/typed-null/update-only fixtures and deterministic facts/closure digest checks |
| Arrow/Parquet language-neutral boundary | **Pass for enabled boundary** | batch metadata/round-trip tests, Python/Rust records golden vectors and Rust reader tests; semantic Rust provider remains deferred |
| artifact publication/recovery | **Pass** | tamper, duplicate, truncation, store failure, cancellation, closure reopen and per-table/byte/spool budget tests |
| cache trust/identity boundary | **Pass** | semantic key invalidation, content/manifest validation, operation-local ref rewrite, replacement rejection and continuation-policy rebind tests |
| markers/static/container | **Pass with deferred image gate** | full unit, ruff, mypy, Rust gates and marker scan pass; inherited Docker rebuild remains required before S8 sealed candidate |

**S7 decision: PASS for the reviewed staged R5 implementation surface.** `S7-001` and `S7-002` are
closed with regression evidence; no unclosed P1/P2 or contract ambiguity remains. S8 is the next
conversation and must carry this record, the dirty-path/source-tip context, the deferred native-provider
and Docker gates, and the unchanged global `p3_implementation_authorized: no` decision.

## 7. Deferred and reopen conditions

Deferred: static risk rules/aggregation, surface/bundle production integration, table-level cache,
projection cache promotion/eviction, independent compute worker/service, semantic Rust comparison
provider/differential production execution, provider-specific raw cache, and the inherited backend
image/container gate.

Reopen R5 if batch boundary requires R4 private imports, Python row objects become required bulk input,
Rust changes semantic facts without version/digest update, replacement enters row alignment, blank
payload affects comparison, cache bypasses policy, partial closure publishes, the deferred provider or
container gate is claimed without its evidence, or a forbidden business/repository dependency is
introduced.
