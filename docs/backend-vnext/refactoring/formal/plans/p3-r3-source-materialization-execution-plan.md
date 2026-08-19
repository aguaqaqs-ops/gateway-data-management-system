# P3-R3 Source Materialization and Snapshot Execution Plan

状态：Accepted for staged execution；S8 module gate complete，R3 gate pass；handoff: [p3-r3-source-materialization-handoff.md](p3-r3-source-materialization-handoff.md)

日期：2026-08-19

阶段：P3-R3 complete；P3-R4 entry ready；implementation authorization pending

Owner：Backend vNext Source Materialization

上级计划：[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)

设计基线：[P3 Capability Foundation Design §4.2](p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline)

R2 入口：[P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)

## 1. Objective and exit

R3 建立 flow-neutral、bounded、可独立测试的 source materialization capability：

```text
SourcePackage / SqlDumpSource / RepositoryRef
  -> SnapshotMaterializationResult
  -> Snapshot + SnapshotSummary
  -> optional SnapshotTableSet
  -> optional immutable SnapshotTableArtifact closure
```

R3 必须交付：

- SourcePackage streaming staging、entry manifest/digest 和 required/optional document
  resolution；
- SQL table_access output 到 Snapshot/summary/table-set 的 canonical materialization；
- `logics.xml` business schema、composite AST binding 和 `composite_signal_point` derived
  table provider；
- pinned RepositoryRef provider protocol、hidden FINAL summary readback contract 和
  protocol-conformant fake provider；
- `PROVISIONAL` / `CONTENT_VERIFIED` / `COMMIT_VALIDATED` cache validation boundary；
- immutable `SnapshotTableArtifact` manifest + Parquet rows round-trip；
- deterministic digest、partial/failure atomicity、cancel/timeout/I/O cleanup 和 diagnostics
  conformance evidence；
- explicit deferred register、review closure 和 R4 handoff。

R3 不实现：

- HTTP/OpenAPI、Workspace、PreviewResult、Submit/application flow 或 Operation Runtime；
- Repository commit/write/import effect；真实 Repository Service/Dolt adapter 的 production
  gate 只作为独立 integration evidence，不成为 `table_access` 或 materializer 的 hidden
  dependency；
- storage projection、canonical storage key/schema、CanonicalizationManifest、comparison
  projection、risk/surface/bundle；
- retention/eviction/quota、durable checkpoint/takeover、projection cache、export-format
  matrix、Rust provider、automatic fallback 或正式 `TAR_ZST` SourcePackage。

## 2. Entry decisions and invariants

### 2.1 Input and package boundary

| Layer | Accepted input | R3 status |
| --- | --- | --- |
| Production HTTP business package | `TAR_GZ` only | formal V1 |
| Capability/local fixture | `ZIP`, `TAR_GZ`, `DIRECTORY` | supported resolver inputs |
| SQL-only helper | `SQL_FILE`, `SQL_GZ` | test/benchmark only |
| Internal staging transport | explicit zstd compression | allowed; no `TAR_ZST` package kind |
| Repository import transport | fixed `tar+zstd` | separate Repository contract |

All package formats use the same normalized-path, traversal/root/symlink refusal, streaming
size checks and entry digest semantics. Compression metadata is not part of SQL Snapshot
identity. A future formal `TAR_ZST` requires reopening the SourcePackage owner contract/ADR;
it is not an R3 implementation detail.

### 2.2 Resource and security budgets

R3 inherits these upper bounds; it does not make a numeric throughput or SLO claim:

| Budget | Limit | Owner/evidence |
| --- | ---: | --- |
| compressed source ingress | 256 MiB | SourcePackage contract and staging tests |
| expanded SourcePackage | 1 GiB | P3 design baseline; benchmark before tightening |
| decoded SQL document | 512 MiB | R2-S0 budget table |
| SQL/XML table, row, field, node and diagnostic limits | R2 frozen values | R2 handoff/conformance fixtures |
| artifact manifest and row files | bounded by source/table budgets and artifact policy | artifact validation tests |

Extraction, decompression, parser streams and artifact writes must enforce limits incrementally.
No full-unbounded DOM, host path, SQL executor, shell, external XML resource or automatic
fallback is allowed.

### 2.3 Result, failure and lifecycle semantics

- Public entrypoints consume R2 public contracts and an explicit immutable
  `TableRulesetSnapshot + table_ruleset_version`.
- Package/source resolution, business XML structural/semantic failure, global identity/digest
  mismatch and inability to establish a complete Snapshot identity are result-level `FAILED`;
  no Snapshot/TableSet/artifact is published.
- Independent table schema/type/key/reader issues may produce `PARTIAL`; healthy tables remain
  consumable, while a failed table has diagnostics/degraded facts only and no partial reader or
  artifact. If every table fails, result is `FAILED`.
- Reader order remains source INSERT order. Raw/business digests use canonical scalar rows in a
  deterministic order-insensitive multiset and preserve duplicate counts. No surrogate key,
  deduplication, overwrite or last-write-wins behavior is introduced.
- Successful stream completion is the commit point. Artifact publication is staging write,
  manifest/descriptor/digest validation, then atomic publish. Cancellation, deadline, I/O or
  provider failure cannot publish incomplete rows or manifests.
- Trust levels are `PROVISIONAL`, `CONTENT_VERIFIED`, `COMMIT_VALIDATED`; only repository
  commit/readback or equivalent authority may promote to `COMMIT_VALIDATED`. Durable checkpoint,
  takeover and retry ownership remain P4 concerns.

### 2.4 Business and repository invariants

- Optional `/comps/logic/logics.xml` missing means stable EMPTY source; XML/EMPTY marker,
  parser/materializer versions and ruleset version participate in business Snapshot identity.
- Composite business invariant failure is materialization-level failure and never publishes
  `composite_signal_point`; source SQL tables remain unchanged.
- RepositoryRef sessions are read-only, operation-scoped and pinned to an immutable resolved
  commit. Missing, corrupt or version/digest-mismatched hidden FINAL SnapshotSummary fails
  closed; catalog/rows must not be used to silently reconstruct it.
- R3 module evidence may use a protocol-conformant in-memory fake provider. Real Repository
  Service/Dolt open/ref/readback/NULL/scalar integration is a separate integration gate.
- `SnapshotTableArtifact` v1 is `manifest + Parquet rows`; downstream consumers use reader and
  opaque `ArtifactRef`, not Parquet internals. Cache miss must retain a source/ref rebuild path.

## 3. Ownership, allowed paths and forbidden paths

### 3.1 Owners

| Contract/fact | Owner | R3 responsibility |
| --- | --- | --- |
| SourcePackage staging and document refs | source materialization | implement bounded resolver/staging |
| SQL/XML parser facts | `table_access` | consume only public R2 surface |
| Table semantic rules | `table_rules` | receive immutable snapshot/version; no hidden mutable global |
| Snapshot/digest/materialization facts | source materialization | implement R3 canonical facts |
| Storage projection/import package | R4/R7/Repository | not implemented in R3 |
| Operation lifecycle/retention | P4/P5 | not implemented in R3 |

### 3.2 Initial allowlist

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/
vnext/backend/src/gateway_backend/capabilities/source_package_staging/
vnext/backend/src/gateway_backend/capabilities/composite_signal/
vnext/backend/src/gateway_backend/capabilities/table_rules/
vnext/backend/src/gateway_backend/artifacts/
vnext/backend/src/gateway_backend/infrastructure/artifact_store/
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/test_source_package_*.py
vnext/backend/tests/test_composite_signal_*.py
vnext/backend/tests/test_repository_ref_materialization_*.py
vnext/backend/tests/test_snapshot_artifact_*.py
vnext/backend/tests/support/*materialization*
vnext/backend/tests/support/*snapshot*
vnext/fixtures/golden/snapshot-materialization/
vnext/fixtures/golden/composite-signal/
vnext/fixtures/vectors/snapshot-materialization/
vnext/fixtures/vectors/composite-signal/
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s6-focused-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s7-independent-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-handoff.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

New paths require S0 registration. Forbidden paths include `vnext/repository_service/`, HTTP,
Workspace, Submit, Operation Runtime, storage/comparison/risk/application modules, host path
fields, SQL execution, external XML resources, new service/helper/security principal and formal
`TAR_ZST` package admission.

## 4. Conversation and step policy

S-step count is **not a fixed seven-step convention**. The P3 execution plan supplies a default
template only; R3 uses the following nine step boundaries because source staging, SQL materializer,
business XML, repository provider and artifact/cache validation have distinct owners and risk
evidence. S0 may merge or split them if actual implementation context proves a different boundary.

| Step | Objective/output | Conversation |
| --- | --- | --- |
| S0 | entry/applicability, R2 handoff check, owner graph, budgets, package/zstd scope, reopen record | **New entry conversation** |
| S1 | public R3 contracts, source staging/resolution skeleton, fixtures and import checks | **Same conversation as S0** |
| S2 | SQL Snapshot materializer, ruleset view, summary/digest and table-level partial semantics | **New implementation conversation** |
| S3 | business XML/composite provider and SQL+XML composition/failure oracle | **Same conversation as S2** |
| S4 | RepositoryRef provider protocol, hidden-summary validation and fake-provider conformance | **New implementation/integration-boundary conversation** |
| S5 | SnapshotTableArtifact Parquet round-trip, cache validation/status promotion and atomic publish | **New artifact/integrity conversation** |
| S6 | focused contract/resource/security review and findings register | **New focused-review conversation** |
| S7 | independent owner/import/digest/recovery review and exact reruns | **New independent-review conversation** |
| S8 | module gate, handoff, deferred register and next-module prerequisites | **New acceptance/documentation conversation** |

Remediation is an embedded loop, not a standalone step or conversation:

```text
S6/S7 finding
  -> issue register
  -> return to owning S2/S3/S4/S5 conversation
  -> fix + regression fixture + focused rerun
  -> return to the original review conversation
```

P1/P2, contract ambiguity, digest mismatch, unbounded path, hidden dependency or recovery
finding must be closed or formally reopen its owner before the next step. S8 cannot authorize
unlisted capability or production integration.

## 5. Step execution details

### S0 — Entry, applicability and budget freeze

**Objective**：证明 R2 handoff 可作为 R3 输入，冻结 source formats、zstd internal-only
transport、R3 owners, budgets, result status, trust levels, allowed paths and reopen conditions.

**Inputs**：R2 handoff, P3 design §4.2, SourcePackage/Snapshot/SnapshotTableAccess contracts,
table rules contract, artifact contract, testing conventions and current git status.

**Outputs**：S0 brief, decision register, owner/import graph, resource table, package-security
matrix, fixture roots, review/reopen register and S1 contract checklist.

**Checks**：read-only contract cross-reference, `git status --short`, `git diff --check`,
forbidden import/path scan. No business code, Dolt or external process.

**Exit**：no unresolved R3 ownership, package-format, digest, failure-atomicity or cache-trust
ambiguity; S1 is authorized only within the allowlist.

S0 记录：[P3-R3-S0 Entry, Applicability and Budget Freeze](p3-r3-s0-entry-and-budget-freeze.md)。

### S1 — Public contract and SourcePackage staging skeleton

**Objective**：建立 importable R3 public ports and minimum source staging/entry-resolution
walking path without SQL/XML business interpretation.

**Required behavior**：bounded TAR_GZ resolver; capability-only ZIP/DIRECTORY/SQL_FILE/SQL_GZ
helpers; normalized path and symlink/traversal refusal; required SQL uniqueness; optional XML
EMPTY source; entry/package/document digests; opaque artifact refs; explicit compression metadata.

**Tests/checks**：pure unit path/archive/size/digest tests, malformed package parameter tables,
architecture/import tests, fixture shape checks, ruff/mypy and `git diff --check`. No Dolt.

**Exit**：SourcePackage staging produces only public refs/artifact metadata; it cannot import
table_access internals, snapshot materialization, repository service or application flow.

### S2 — SQL Snapshot materialization

**Objective**：consume only R2 public SQL results and produce deterministic Snapshot,
SnapshotSummary and optional table readers under an explicit ruleset snapshot.

**Required behavior**：descriptor/ruleset view, effective key precedence, keyless facts, typed
scalar/NULL preservation, row-count and digest computation, table-level PARTIAL, all-table
FAILED, requested-table filtering without rediscovery, `DESCRIPTOR_ONLY`/`READERS_REQUIRED`/
`ARTIFACTS_REQUIRED` policy and `PROVISIONAL`/`CONTENT_VERIFIED` result metadata.

**Tests**：golden SQL-to-Snapshot cases; row-order and package-metadata invariance; duplicate
row/key behavior; keyless/degraded tables; malformed/type/NULL/resource/cancel/timeout paths;
reader reopen and stream commit point; summary without row opening; cache miss rebuild.

**Exit**：SQL-only materialization is flow-neutral, deterministic and independent of Repository,
HTTP, Workspace and storage projection.

### S3 — Composite XML and business-source composition

**Objective**：consume R2 bounded XML events plus SQL Snapshot facts and produce the business
composition required by `composite_signal_point` without changing source SQL tables.

**Required behavior**：strict XML business AST, EMPTY source handling, exact point matching,
special-device invariants, canonical derived rows/formula digests, SQL+XML identity composition,
whole-result failure for business invariant violations and stable diagnostics.

**Tests**：valid/missing/EMPTY XML, malformed/unknown operator/duplicate/orphan/security cases,
derived-table golden fixtures, source table preservation, SQL-only vs XML identity, row/digest
determinism, partial SQL plus XML failure atomicity and artifact closure planning.

**Exit**：business wrapper is independent of HTTP/flow state and publishes no derived table on
business failure.

### S4 — RepositoryRef materialization provider boundary

**Objective**：define and validate the repository table-access provider protocol without hiding
Repository Service/Dolt implementation inside R3.

**Required behavior**：read-only pinned immutable ref session, memoized catalog, requested-table
filtering without relist, tuple row/null normalization, hidden FINAL summary readback and strict
version/digest mismatch failure, operation-scoped close and timeout diagnostics.

**Tests**：protocol-conformant fake unit/contract matrix; catalog-to-descriptor, scalar encoding,
row-order-insensitive digest, close/timeout/failure, hidden-summary missing/corrupt/mismatch and
cache-validation cases. Real Repository Service/Dolt tests are a separately marked integration
gate and are not required for pure unit classification.

**Exit**：R3 can consume a provider protocol; no import cycle, SQL execution, repository write or
summary reconstruction path exists.

### S5 — SnapshotTableArtifact and cache integrity

**Objective**：materialize immutable raw table artifacts and validate cache/trust transitions.

**Required behavior**：manifest + Parquet rows, descriptor/row_count/raw digest/artifact digest
round-trip, staging-to-atomic-publish, `PROVISIONAL` revalidation, `CONTENT_VERIFIED` closure,
explicit promotion input for `COMMIT_VALIDATED`, cleanup-safe transient failures and source/ref
fallback rebuild.

**Tests**：Parquet round-trip, corrupt manifest/schema/row file, digest mismatch, truncation,
cancel/timeout/I/O cleanup, cache hit descriptor/digest validation, provisional rejection without
revalidation, cache deletion rebuild and no host path in refs/manifests. Artifact tests use tmp
roots and do not require Dolt.

**Exit**：incomplete artifact cannot be published or used as a ready/cache-authoritative result;
retention/eviction remains outside R3.

### S6 — Focused contract/resource/security review

**Conversation input**：S0/S1 decisions, S2-S5 diff, fixture corpus, resource evidence, fake
provider output, artifact manifests and exact test results.

**Review focus**：SourcePackage path/archive/symlink/root boundaries; package budgets and zstd
scope; table rules/keyless/duplicate semantics; digest order/multiplicity; XML business failure;
hidden summary authority; reader/artifact atomicity; trust-level promotion; no HTTP/Repository
write/application dependency; test marker correctness.

**Exit**：findings register complete; no unclassified P1/P2 or contract ambiguity. Remediation
returns to the original implementation conversation and then back to this review conversation.

S6 记录：[P3-R3 S6 Focused Contract, Resource and Security Review](p3-r3-s6-focused-review.md)。

### S7 — Independent review

**Conversation input**：independent copy of the plan, contracts, cumulative diff, fixtures,
resource table, S6 findings closure and test commands; reviewer does not rely on implementer
oral explanation.

**Minimum checks**：unit/architecture/ruff/mypy/diff rerun; exact package security and digest
vectors; SQL/XML oracle; fake RepositoryRef provider; hidden-summary fail-closed cases; Parquet
round-trip/corrupt artifact; cancellation/timeout/atomic publish; forbidden path/import scan;
real Repository Service/Dolt integration nodeids if this round claims them.

**Exit**：independent pass; no unclosed P1/P2, contract ambiguity, unbounded path, import cycle,
hidden Repository/application dependency or incorrect marker.

S7 记录：[P3-R3 S7 Independent Owner, Import, Digest and Recovery Review](p3-r3-s7-independent-review.md)。

### S8 — R3 module gate and R4 handoff

**Required record**：tested source tip, changed paths, exact commands/results, fixture roots,
budget revision, S6/S7 closure, container rebuild decision, known limitations, deferred register,
contract/ADR refs, R4 prerequisites and implementation authorization status.

**R3 gate commands**（按实际 package/test surface调整，不机械扩大范围）：

```text
cd vnext/backend && uv run pytest -m unit
cd vnext/backend && uv run ruff check . && uv run mypy
git diff --check
```

若加入真实 Repository/Dolt、固定进程/stream timeout 或 durable-on-disk staging 测试，
必须按测试 conventions 加 `integration`/`serial` 并运行精确 nodeid。纯 source parser、
materialization、digest、artifact validation 测试不得创建 Dolt。若本轮未触碰 Dockerfile、
lock、Compose、entrypoint、UID/GID、mount、socket、healthcheck 或 container-only runtime
boundary，container rebuild 可延期；若触碰或要宣称当前 HEAD 通过容器门禁，则必须重建并
记录 source-tree/image provenance。

**R3 exit**：immutable Snapshot artifact closure、failure/cancel/resource/security semantics
通过；无未处理 P1/P2、contract ambiguity、unbounded path 或隐式跨 R 依赖；handoff 明确
R4 storage projection 只接收 R3 public Snapshot/Artifact contract。

## 6. Deferred register and reopen conditions

| ID | Deferred item | Earliest owner | Guard before use |
| --- | --- | --- | --- |
| R3-D01 | formal `TAR_ZST` SourcePackage admission | future SourcePackage/HTTP owner | real consumer or measured deployment need; reopen contract/ADR |
| R3-D02 | Repository Service/Dolt production adapter/readback gate | P2 integration/Repository owner | provider protocol, hidden summary and exact integration nodeids |
| R3-D03 | retention, pinning, eviction, quota and durable artifact lifecycle | P4/P5 | lifecycle contract and cleanup evidence |
| R3-D04 | storage projection, canonical storage key/schema and import package semantics | P3-R4/R7 | R4 owner contract; no R3 duplicate digest logic |
| R3-D05 | projection cache and export-format matrix | P3-R4/R5 or later | validated consumer and benchmark evidence |
| R3-D06 | Rust materializer/provider, automatic fallback and optimization profile | P6+ | accepted Python differential oracle and profile |
| R3-D07 | durable cancellation/checkpoint/takeover/retry ownership | P4 | Operation Runtime contract |

Reopen R3 before the next gate if source/package ownership changes, a zstd format is promoted to
formal input without contract review, table rules cannot be injected immutably, SQL/XML composition
publishes partial business facts, hidden summary is reconstructed after mismatch, digest changes
with row order/package metadata, artifact publication is non-atomic, a reader exposes partial rows
as ready, or R3 imports Repository/application/HTTP implementation details.

## 7. Status

```yaml
module: P3-R3
status: s8_complete
implementation_authorized: no
current_step: S8_complete
s0_record: p3-r3-s0-entry-and-budget-freeze.md
s1_authorized: yes
p3_r3_s1: completed
p3_r3_s2: completed
p3_r3_s3: completed
p3_r3_s4: completed
p3_r3_s5: completed
p3_r3_s6: completed
p3_r3_s7: completed
p3_r3_s8: completed
upstream: p3-r2-table-access-parser-handoff.md
design_baseline: p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline
next_module: P3-R4
zstd_scope: internal_fixture_and_staging_only
formal_source_package: TAR_GZ
review_model: focused_S6_independent_S7_embedded_remediation
s6_record: p3-r3-s6-focused-review.md
s7_record: p3-r3-s7-independent-review.md
s8_handoff: p3-r3-source-materialization-handoff.md
p3_r3_exit: pass
p3_r4_ready: yes
```

## 8. Normative references

- [P3 Capability Foundation Design](p3-capability-foundation-design.md)
- [P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md)
- [P3 Active Context Index](p3-active-context-index.md)
- [P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)
- [P3-R3-S0 Entry, Applicability and Budget Freeze](p3-r3-s0-entry-and-budget-freeze.md)
- [SourcePackage Contract](../../../contracts/source-package.md)
- [Snapshot Contract](../../../contracts/snapshot.md)
- [Snapshot Table Access Contract](../../../contracts/snapshot-table-access.md)
- [Snapshot Materialization Capability](../../../capabilities/snapshot-materialization.md)
- [Repository Ref Materialization Capability](../../../capabilities/repository-ref-materialization.md)
- [Composite Signal Device Capability](../../../capabilities/composite-signal-device.md)
- [Artifact and Persistence](../../../artifacts.md)
- [Testing Conventions](../../../testing-conventions.md)
- [Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)
- [P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)
- [P3-R3 S7 Independent Owner, Import, Digest and Recovery Review](p3-r3-s7-independent-review.md)

## 9. S8 module gate record

状态：**PASS**；handoff: [P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)。

S8 confirmatory rerun against `validated_code_sha`
`7989e47d08c48fda46e7d8b6b3550ef9ee266d92`（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run --offline pytest -m unit` | **372 passed**（1.40s）；1 pre-existing Starlette deprecation warning |
| `cd vnext/backend && uv run --offline ruff check . && uv run --offline mypy` | **passed**；mypy 121 source files |
| `git diff --check` | **passed** |

No serial nodeid, Dolt, or container rebuild. S6-001–003 remain closed. `S6-004`
and `R3-D01`–`R3-D07` are carried forward. `S7-V01` did not reproduce; full unit
is the S8 evidence. `p3_r3_exit: pass`；`p3_r4_ready: yes`；
`p3_implementation_authorized: no`。R4 必须先写详细计划再实现。
