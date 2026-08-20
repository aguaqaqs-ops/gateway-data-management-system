# P3-R5 Comparison Execution Plan

状态：Accepted for staged planning；S0/S1 complete；implementation authorization pending

日期：2026-08-20

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

S1 is pure Python/public-boundary and test work plus reuse of the already-built native boundary. No
Dockerfile, dependency lock, image, entrypoint, Compose or container-only runtime boundary changed;
container rebuild is therefore deferred to a later Rust/dependency/image change or the final candidate.

## 7. Deferred and reopen conditions

Deferred: static risk rules/aggregation, surface/bundle production integration, table-level cache,
projection cache promotion/eviction, independent compute worker/service, and provider-specific raw cache.

Reopen R5 if batch boundary requires R4 private imports, Python row objects become required bulk input,
Rust changes semantic facts without version/digest update, replacement enters row alignment, blank
payload affects comparison, cache bypasses policy, partial closure publishes, or a forbidden business/
repository dependency is introduced.
