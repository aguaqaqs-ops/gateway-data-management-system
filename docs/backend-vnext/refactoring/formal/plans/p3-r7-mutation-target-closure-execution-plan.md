# P3-R7 Mutation and Target Closure Execution Plan

状态：S0 complete/pass；S1 complete/pass；S2 complete/pass；S3 complete/pass；S4 complete/pass；S5 complete/pass；S6 complete/pass；S7 complete/pass；R7 gate pass；handoff: [p3-r7-mutation-target-closure-handoff.md](p3-r7-mutation-target-closure-handoff.md)

日期：2026-08-22

Owner：Backend vNext Canonical Storage / Mutation Planner / External Target Sync

设计基线：[P3-R7 Mutation and Target Closure Design Baseline](p3-r7-mutation-target-closure-design.md)

入口冻结：[P3-R7-S0 Entry, Applicability and Budget Freeze](p3-r7-s0-entry-and-budget-freeze.md)

上游 handoff：[P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)、[P3-R6 Risk, Surface and Bundle Handoff](p3-r6-risk-surface-bundle-handoff.md)

本文将 R7 拆为可独立验证的 contract、planner、renderer 和 reference executor steps。R7 不执行
真实 Repository/Dolt effect，不接入 P5B flow，也不改变全局 `p3_implementation_authorized`。

## 1. Objective and exit

R7 exit requires：

- public mutation/change-set contracts have one owner and no unresolved architecture blocker；
- planner emits deterministic immutable plans and ChangeSet closures；
- Dolt renderer produces deterministic bounded replay artifacts without execution；
- reference executor covers apply, rollback, unknown outcome, reconcile and idempotent retry；
- focused and independent reviews have no open P1/P2 finding；
- legacy fixture gap and inherited image gate are carried with explicit close points；
- handoff records tested source SHA, exact commands, deferred register and later P4/P5 entry boundaries；
- global `p3_implementation_authorized` remains `no`.

## 2. Conversation and review policy

| Step | Topic | Conversation policy | Review isolation | Scoped authorization |
| --- | --- | --- | --- | --- |
| S0 | entry, applicability, budgets and freeze | new conversation | architecture/owner decisions only | none |
| S1 | mutation/change-set contracts and identity | new conversation after S0 | contract/import review | mutation contracts only, after S0 pass |
| S2 | planner, eligibility and closure | same conversation as S1 | implementation only | planner/closure only, after S1 contract seal |
| S3 | planner focused review | new conversation | independent resource/digest review | none |
| S4 | Dolt renderer and replay golden | new conversation after S3 | renderer/security review | renderer only, after S3 pass |
| S5 | external reference executor and recovery | same conversation as S4 | implementation only | executor only, after S4 contract/golden seal |
| S6 | independent R7 review | new conversation | owner/import/digest/recovery review | none |
| S7 | module gate and R7 handoff | new conversation | acceptance/documentation only | none |

## 3. Scope and dependency boundary

```text
R4 canonical projection
  -> R7 mutation planner / ChangeSet
       -> Dolt renderer
       -> external reference executor
```

Allowed production imports are R4 public storage projection contracts, shared canonical encoding,
artifact ports and R7 public contracts. Forbidden imports are HTTP/application/Workspace/Submit/Archive,
Operation Runtime, Repository/Dolt execution adapters, R6 private modules, legacy business modules,
host-path helpers, test support and new helper/service/security principals.

## 4. Staged steps

### S0 — Entry, applicability and budget freeze

Accept R4/R6 handoffs, freeze R7 owner DAG, immutable input boundary, policy, destructive confirmation
boundary, caps, fixture groups, review isolation and deferred register. S0 is documentation-only and
does not authorize implementation.

### S1 — Mutation and ChangeSet contracts

Define immutable public types, operation/status enums, plan identity, ChangeSet manifest, canonical
serialization and exact failure codes. Add the `external_target_sync` capability owner and public apply
contract; keep its checkpoint shape test-only. Prove forbidden imports and malformed contract rejection.

Expected package/test surface:

```text
capabilities/mutation_planning/contracts.py
capabilities/mutation_planning/__init__.py
capabilities/external_target_sync/contracts.py
capabilities/external_target_sync/__init__.py
tests/test_mutation_contracts.py
tests/test_external_target_contracts.py
tests/test_architecture.py
```

S1 status: **complete/pass**. Scoped mutation-contract implementation only; global
`p3_implementation_authorized` remains `no`.

S1 changed paths:

```text
vnext/backend/src/gateway_backend/capabilities/mutation_planning/contracts.py
vnext/backend/src/gateway_backend/capabilities/mutation_planning/__init__.py
vnext/backend/src/gateway_backend/capabilities/external_target_sync/contracts.py
vnext/backend/src/gateway_backend/capabilities/external_target_sync/__init__.py
vnext/backend/tests/test_mutation_contracts.py
vnext/backend/tests/test_external_target_contracts.py
vnext/backend/tests/support/mutation_contracts.py
vnext/backend/tests/test_architecture.py
```

The implementation freezes mutation policy/operation/status enums, plan identity and ChangeSet
manifest/closure types, canonical cell encoding, digest helpers and publication barriers. It adds
the separate `external_target_sync` owner with public apply contracts and test-only reference
executor checkpoint shape. No planner, renderer, executor or repository integration was added.

#### S1 verification record

Executed on 2026-08-22. Pure Python contract tests; no Dolt repository or container rebuild.

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q -m unit tests/test_mutation_contracts.py tests/test_external_target_contracts.py tests/test_architecture.py` | **46 passed** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python contracts/tests only |

S1 decision: **PASS / complete**. S2 may consume the committed public contracts in the same lineage.

### S2 — Planner, eligibility and closure

Implement initial/empty baseline handling, table add/remove, rebuild/patch/no-op planning, threshold
boundaries, before/after guards, destructive `requires_confirmation`, deterministic ordering and
atomic ChangeSet artifact publication. ChangeSet closure is canonical JSON; it must not contain SQL or
executor checkpoint fields.

Expected private modules/tests:

```text
mutation_planning/_planner.py
mutation_planning/_changeset.py
mutation_planning/_digest.py
mutation_planning/_artifacts.py
tests/test_mutation_planning.py
```

#### S2 verification record

Executed on 2026-08-22. Pure Python planner/closure unit tests; no Dolt repository or container rebuild.

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q -m unit tests/test_mutation_contracts.py tests/test_mutation_planning.py tests/test_external_target_contracts.py tests/test_architecture.py` | **67 passed** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; Python planner/closure only |

S2 decision: **PASS / complete**. S3 may review planner identity, eligibility and closure publication.

### S3 — Planner focused review

Independently review identity binding, resource enforcement, key/schema/projection transitions,
destructive paths, no empty commit, closure digest and no partial publication.

#### S3 verification record

Executed on 2026-08-22 as an independent focused review against source HEAD
`44e113e2eeac34814a7b12a2e32bf98b9e6438e6`; the S1/S2 implementation, S3 remediation, tests and
formal records remain uncommitted in the current worktree. The review consumed only the public
mutation contracts, planner/closure/artifact implementation, architecture checks and test output;
no implementer explanation or private mutable state was used.

Review boundary:

- plan identity binding for source/base/projection/renderer/policy/threshold/encoding digests;
- canonical table/key/operation ordering and mixed `REBUILD_TABLE` / `PATCH_DML` / `NOOP` plans;
- initial/empty baselines, table add/remove, schema/key/projection transitions and destructive confirmation;
- unsupported canonical values, including key and persisted row-image cells;
- closure manifest/ChangeSet/closure digest binding, SQL/checkpoint exclusion and canonical JSON parsing;
- JSON resource admission, no partial public closure publication and no-op/no-empty-commit behavior;
- owner/import boundary, marker classification and absence of Dolt/process/network/container dependencies.

| Finding | Area / disposition | Evidence |
| --- | --- | --- |
| `S3-F001` | Unsupported canonical key values / **P2 closed** | Initial review found the renderer-capability preflight scanned persisted row images but not canonical storage keys. Planner preflight now checks both key and image cells and returns `TARGET_CAPABILITY_UNSUPPORTED` before closure construction; a key-anomaly regression test proves no closure is produced. |
| `S3-F002` | Mixed-plan closure summary / **P2 closed** | Initial review found the manifest summary list could omit unchanged tables in a mixed plan. Closure construction now retains every per-table summary, including `NOOP`; a mixed-plan regression asserts deterministic `inventory`, `orders` summaries. |
| `S3-F003` | Closure parser malformed column entries / **P2 closed** | Initial review found non-object key/image column entries were silently filtered by deserialization. The parser now rejects every non-object entry explicitly; malformed closure regression coverage proves fail-closed parsing. |
| `S3-001` | Artifact-store orphan reclamation / **accepted defer** | `ArtifactStorePort` has no delete/transaction primitive. A later store failure may leave opaque unreachable bytes, but no public closure ref is returned; reclamation remains ADR 0012 lifecycle work and is outside R7 planner authority. |

Exact verification evidence:

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q -m unit tests/test_mutation_contracts.py tests/test_mutation_planning.py tests/test_external_target_contracts.py tests/test_architecture.py` | **70 passed** |
| `cd vnext/backend && uv run pytest -q -m unit` | **818 passed**, 1 existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 181 source files |
| `git diff --check` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; planner/closure Python and tests only; no Dockerfile, lockfile, deployment or runtime boundary changed. The inherited image gate remains a final-current-HEAD prerequisite. |

No fixed-timeout, Dolt, process, network or integration fixture was introduced; no `integration` or
`serial -n 0` rerun is required. The full unit result is evidence for the current worktree, while the
recorded source SHA identifies its committed base; uncommitted remediation is intentionally visible
in `git status` and must be sealed before downstream S4 consumption.

S3 decision: **PASS / complete**. All P1/P2 findings are closed; `S3-001` is explicitly accepted
deferred lifecycle work with no contract ambiguity. S4 is **APPROVED AFTER SEAL** to implement the
deterministic Dolt renderer and replay golden fixtures in a new conversation, consuming only the
sealed public ChangeSet boundary. `p3_r7_implementation_authorized` and global
`p3_implementation_authorized` remain `no`.

### S4 — Deterministic Dolt renderer

Implement controlled identifier/value encoding and deterministic `replay.sql` generation, replay-size
admission, renderer capability declaration and SQL golden fixtures. Renderer code remains under
`mutation_planning` but consumes only public ChangeSet contracts. No real Dolt execution is allowed.

Expected private module/tests:

```text
mutation_planning/_dolt_renderer.py
tests/test_dolt_renderer.py
vnext/fixtures/golden/mutation/
```

#### S4 verification record

Executed on 2026-08-22 against source HEAD
`b0261cb669fedc07173a31cd55ce83ef19b0c6ad`. Renderer implementation and golden fixtures were
sealed in `e09ff32cc3562b744ff5718357a529c7b8ce3e6f`; S7 reran gates at the current tip.

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q -m unit tests/test_dolt_renderer.py tests/test_mutation_contracts.py tests/test_mutation_planning.py tests/test_architecture.py` | **PASS** |
| golden fixtures under `vnext/fixtures/golden/mutation/renderer/` | **PASS**; valid SQL and capability-failure closures present |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; renderer Python and fixtures only |

S4 decision: **PASS / complete**. S5 may consume the sealed public ChangeSet and renderer boundary.

### S5 — External reference executor

Implement the in-memory `PREPARE/APPLYING/VERIFYING/SUCCEEDED|FAILED|UNKNOWN_OUTCOME` state machine,
transaction rollback, exact affected-row checks, ledger/readback reconciliation and idempotent retry.
Checkpoint export/import is test-only JSON fixture data and not durable production state. Executor code
must live under `external_target_sync`; it may import public ChangeSet contracts but not planner-private
modules.

Expected private module/tests:

```text
capabilities/external_target_sync/_reference_executor.py
tests/test_external_target_executor.py
```

#### S5 verification record

Executed on 2026-08-22 against source HEAD
`b0261cb669fedc07173a31cd55ce83ef19b0c6ad`. Executor implementation was sealed in
`e09ff32cc3562b744ff5718357a529c7b8ce3e6f`; S7 reran gates at the current tip.

| Check | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -q -m unit tests/test_external_target_executor.py tests/test_external_target_contracts.py tests/test_architecture.py` | **PASS** |
| rollback, drift, unknown outcome, reconcile and idempotent retry coverage | **PASS** |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; in-memory executor Python only |

S5 decision: **PASS / complete**. S6 may review the full owner/import/digest/recovery surface.

### S6 — Independent R7 review

Review complete owner/import graph, digest identity, renderer safety, transaction atomicity, unknown
outcome recovery, resource caps and forbidden P4/P5 integration.

#### S6 verification record

Executed on 2026-08-22. Authoritative record:
[P3-R7-S6 Independent Owner, Import, Digest and Recovery Review](p3-r7-s6-independent-review.md).

| Finding | Area / disposition | Evidence |
| --- | --- | --- |
| `S3-F001`–`S3-F003` | Planner/closure findings / **P2 closed in S3** | Remain closed at S6 re-review |
| `S3-001` | Artifact-store orphan reclamation / **accepted defer** | ADR 0012 lifecycle work; no public closure ref on store failure |
| `S6-001` | Owner/import boundary / **pass** | Architecture DAG and forbidden-import scans pass |
| `S6-002` | Plan identity and closure digest binding / **pass** | Mixed-plan, threshold, destructive and idempotency tests pass |
| `S6-003` | Renderer safety and replay admission / **pass** | Golden SQL and capability-failure fixtures pass |
| `S6-004` | Executor rollback/unknown/reconcile / **pass** | Rollback, reconcile-then-retry and idempotent reuse tests pass |
| `S6-005` | Forbidden P4/P5 integration / **pass** | No flow/Repository/Dolt/durable-state wiring in R7 capabilities |

| Check | Result |
| --- | --- |
| focused R7 mutation/renderer/executor/architecture unit gate | **98 passed** |
| `cd vnext/backend && uv run pytest -q -m unit` | **848 passed**, 1 existing Starlette deprecation warning |
| `cd vnext/backend && uv run ruff check .` | **passed** |
| `cd vnext/backend && uv run mypy` | **passed**; 188 source files |
| other four Python packages `uv run ruff check .` / `uv run mypy` | **passed** |
| `git diff --check` | **passed** |
| Docker/container rebuild | **DEFERRED / NOT APPLICABLE**; review Python/tests/docs only |

S6 decision: **PASS / complete**. No open P1/P2 finding. S7 may seal the tested source candidate and
publish the R7 handoff.

### S7 — R7 module gate and handoff

Rerun focused/full applicable unit gates, ruff, mypy, benchmark discovery, legacy-oracle disposition and
current-HEAD container decision. Record tested tip, deferred items, exact commands and later P4/P5 entry.

#### S7 verification and handoff record

Executed on 2026-08-22. The tested source candidate is the clean committed source tip
`b0261cb669fedc07173a31cd55ce83ef19b0c6ad`, immediately before adding this acceptance record and
the handoff document. The detailed handoff is
[P3-R7 Mutation and Target Closure Handoff](p3-r7-mutation-target-closure-handoff.md).
This is a source/module gate only: it does not authorize P3 production integration, flow wiring,
Repository/Dolt effect or the global implementation flag.

| Check | Result |
| --- | --- |
| focused R7 mutation/renderer/executor/architecture unit gate | **PASS**; 98 passed |
| `cd vnext/backend && uv run pytest -q -m unit` | **HISTORICAL ENVIRONMENT-BOUND PASS**; 848 passed, 1 warning was recorded at S7, but the required legacy source was not sealed in this repository and the result is not portable final-candidate evidence |
| `cd vnext/backend && uv run ruff check .` | **PASS** |
| `cd vnext/backend && uv run mypy` | **PASS**; 188 source files |
| other four Python packages `uv run ruff check .` / `uv run mypy` | **PASS**; mypy 26 / 15 / 195 / 34 source files |
| `git diff --check` | **PASS** |
| benchmark runner discovery | **NOT APPLICABLE**; exact command and empty result are recorded in the handoff; no numeric result is used as a gate |
| `docker info` | **CLIENT ONLY / DAEMON UNAVAILABLE**; no `/var/run/docker.sock`, so no current-HEAD image rebuild is claimed for this candidate |
| legacy oracle disposition | **CARRIED**; the historical environment loaded it, but `legacy/backend_vnext` is absent/incompatible in the sealed repository; P3 final closure owns the exact-nodeid exclusion and reopen rule |

The inherited R5 Rust/Cargo backend image gate remains mandatory and deferred. No R7 Dockerfile,
dependency, deployment or runtime-boundary change was introduced.

S7 decision: **PASS / complete**. `p3_r7_exit = pass`. `p3_implementation_authorized = no` remains
unchanged.

## 5. Verification policy

Pure planner, contract, digest, renderer and in-memory executor tests are `unit`; no test creates a
Dolt repository. Fixed-timeout or crash/recovery timing tests are `serial` and run with `-n 0`. R7 must
use structured parameter binding or canonical encoding and never shell interpolation.

S1/S2 remain in one implementation lineage only for public contract continuity; S3 is a clean review
boundary. S4/S5 share the stable ChangeSet contract but not mutable planner state. S6 receives committed
artifacts and exact commands only.

The inherited R5 legacy-oracle gap may remain excluded only by exact path/nodeid and must be resolved or
formally accepted before R7 module exit. The inherited Rust/Cargo image gate is required at final current
HEAD and is not closed by source-only unit results.

## 6. Deferred register and reopen conditions

Deferred: real Repository/Dolt execution, P5B confirmation/finalize, P4/P5 durable operation state,
production external adapters, multi-target persistence, cache/retention/GC, orphan reclamation, Rust
renderer/provider optimization, benchmark numeric gates, and inherited image gate until the P3 final
candidate gate.

Reopen R7 if forbidden imports appear, presentation artifacts become mutation authority, plan identity
can drift, partial effects publish, unknown outcomes blind-replay, unsupported values stringify, or a
new service/helper/security principal is introduced.

## 7. Current status

```yaml
current_module: P3-R7
p3_r7_design: accepted
p3_r7_detail_plan: accepted_for_staged_planning
p3_r7_s0: completed
p3_r7_s0_exit: pass
p3_r7_s1: completed
p3_r7_s1_exit: pass
p3_r7_s2: completed
p3_r7_s2_exit: pass
p3_r7_s3: completed
p3_r7_s3_exit: pass
p3_r7_s4: completed
p3_r7_s4_exit: pass
p3_r7_s5: completed
p3_r7_s5_exit: pass
p3_r7_s6: completed
p3_r7_s6_exit: pass
p3_r7_s6_review: p3-r7-s6-independent-review.md
p3_r7_s7: completed
p3_r7_s7_exit: pass
p3_r7_s7_handoff: p3-r7-mutation-target-closure-handoff.md
p3_r7_validated_code_sha: b0261cb669fedc07173a31cd55ce83ef19b0c6ad
p3_r7_exit: pass
p3_r7_implementation_authorized: no
p3_implementation_authorized: no
inherited_r5_legacy_oracle_gap: carried_to_p3_final_closure_exact_nodeid_disposition
inherited_image_gate: required_deferred_to_final_candidate
```
