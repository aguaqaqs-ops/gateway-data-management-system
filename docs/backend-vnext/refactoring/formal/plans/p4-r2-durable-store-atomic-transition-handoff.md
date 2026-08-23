# P4/R2 Durable Store and Atomic Transition Handoff

状态：**PASS**（S7 module gate；R3-S0 entry discussion boundary）

日期：2026-08-24

Owner：Durable operation runtime（`gateway_backend.operations` 与
`gateway_backend.infrastructure.control_db`）

上游：[P4/R2-S6 Risk-based Independent Review](p4-r2-s6-independent-review.md)、
[P4/R2-S5 Handoff](p4-r2-s5-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2
step_id: P4-R2-S7
input_handoff_sha: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
input_independent_review_record: p4-r2-s6-independent-review.md
validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
validated_code_tree_identity: vnext_backend_source_and_tests_match_31235dc
candidate_head_at_gate: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
candidate_worktree_at_gate: source_and_test_tree_clean; expected_untracked_s6_review_record_only
p4_r2_exit: pass
result: pass
changed_paths:
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/refactoring/formal/plans/p4-active-context-index.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-durable-store-atomic-transition-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-durable-store-atomic-transition-handoff.md
commands_and_results:
  - focused unit -> pass_491
  - backend unit -> pass_1319_deselected_24
  - file-backed integration -> pass_24
  - applicable serial -> pass_2_collected_2_deselected_22
  - five-package ruff/mypy -> pass
  - source/test tree identity and git diff checks -> pass
focused_tests: pass_491
findings: []
applicable_steps:
  - P4-R2-S0
  - P4-R2-S1a
  - P4-R2-S1b
  - P4-R2-S2a
  - P4-R2-S2b
  - P4-R2-S3a
  - P4-R2-S3b
  - P4-R2-S4
  - P4-R2-S5
  - P4-R2-S6
  - P4-R2-S7
skipped_steps_with_reason: []
schema_component_version: operations/v1
sqlite_profile:
  library: stdlib_sqlite3
  journal_mode: WAL
  foreign_keys: true
  synchronous: FULL
  busy_timeout_ms: 5000
  write_begin: IMMEDIATE
  transaction_clock: one_injected_aware_utc_sample_per_uow
  lease_duration_seconds: 30
  claim_limit: 1
  max_page_limit: 100
public_store_symbols:
  - OperationStore
  - OperationUnitOfWork
  - ClaimCandidate
  - IntegrityScanPage
  - DEFAULT_CLAIM_LIMIT
  - DEFAULT_PAGE_LIMIT
  - MAX_CLAIM_LIMIT
  - MAX_PAGE_LIMIT
  - RecordNotFound
  - StaleWrite
  - LeaseExpired
  - ConflictingDuplicate
  - StoreBusy
  - CorruptPersistedRecord
  - UnsupportedSchemaVersion
atomicity_matrix:
  create: pass; Operation and initial PENDING Step commit or roll back together
  first_claim: pass; complete post-state construction precedes mutation and both CAS legs share the UoW
  heartbeat_checkpoint_terminal: pass; explicit guarded candidate with version, lease and live-lease checks
  step_success_successor: pass; terminal current Step and caller-selected PENDING successor are one UoW action
  final_step_operation: pass; accepted terminal/recovery Step and Operation publication share one UoW action
  cancel_request: pass; Operation and current non-final Step intent are guarded in one UoW
  terminal_duplicate: pass; exact duplicate is IDEMPOTENT and conflicting/structurally invalid retries do not write
focused_review: pass_after_s5_f1_follow_up
independent_review: pass_after_finding_scoped_remediation
unit:
  focused: pass_491
  backend: pass_1319_with_24_deselected
integration: pass_24
serial: pass_2_collected_2_with_22_deselected
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary_change
benchmark: not_applicable_no_performance_claim
known_capacity_limits:
  - max_in_flight_is_one
  - production_claim_limit_is_one
  - bounded_read_page_maximum_is_100
  - busy_timeout_is_5_seconds
  - no_formal_throughput_or_capacity_claim
deferred_items:
  - R3 worker/bootstrap/settings/volume/readiness route
  - R4 successor selection and final outcome policy
  - R5 retry/backoff/effect-aware recovery and lease takeover
  - production outbox, business repositories, Repository effects, HTTP and deployment wiring
  - terminal retention, backup and a real capacity baseline
reopen_conditions:
  - claim-local validation can again persist a cross-table prefix or a caught mutation can bypass rollback-only composition
  - unknown, null or wrong-type active status can complete the integrity scan successfully
  - need to change the R1 record/transition contract, status matrix, persisted field, schema version or error taxonomy
  - need for direct RUNNING lease replacement, multiple active Steps, JobDefinition/effect policy or automatic repair
  - need for a new public mutation/savepoint/evidence boundary, dependency, external database or deployment boundary
next_step: P4-R3-S0 entry discussion
next_entry: P4-R3-S0
next_step_authorized: yes
p4_r3_implementation_authorized: no
p4_r2_authorized: no
handoff_documentation_sha: pending_handoff_documentation_commit
```

## 1. Module gate identity

The S7 gates ran against source/test candidate `31235dc820472a5ca2c99138fdf150090cfe122d`.
`HEAD` was `29aa42d4b5c3d405ee9be24207e3fd1cddae9f72`, a documentation-only descendant. The
Operations source and test trees are identical between those revisions; the only pre-existing
worktree delta at gate entry was the untracked S6 independent-review record. No source, test,
schema, dependency or deployment change was introduced by this S7 handoff.

The S4 focused review is closed after the finding-scoped S5 follow-up. S6 independently reran the
two P2 barriers: claim-local construction failures occur before either row is mutated, and unknown,
null or wrong-type active statuses fail closed as `CorruptPersistedRecord` without repair. There
are no open S4/S5/S6 findings.

## 2. Delivered module boundary

`gateway_backend.operations` owns the SQLite-neutral `OperationStore` and transaction composition;
`gateway_backend.infrastructure.control_db` owns `sqlite3`, connection profile, migrations and
the concrete Unit of Work. The adapter reconstructs and validates every persisted row through the
R1 record owner. The module does not add business tables, outbox state, Repository effects,
JobDefinition interpretation, worker policy, settings, HTTP or deployment wiring.

The v1 schema is `operations/v1`: a forward-only migration ledger, `operation_records`, and
`step_records`, with the accepted foreign key, one-active-step, claim-order and operation-status
indexes. `eligible_at_us` remains storage metadata and is not part of the R1 document or digest /
version axis.

## 3. Gate results

| Check | Result |
| --- | --- |
| focused backend unit gate | **PASS**; 491 passed in 2.35s |
| backend unit gate | **PASS**; 1319 passed, 24 deselected, 1 pre-existing Starlette/httpx deprecation warning in 45.24s |
| file-backed integration gate | **PASS**; 24 passed in 0.96s |
| applicable serial gate | **PASS**; 2 passed, 22 deselected in 0.79s |
| backend ruff/mypy | **PASS**; 203 source files |
| shared_kernel ruff/mypy | **PASS**; 34 source files |
| repository_contracts ruff/mypy | **PASS**; 15 source files |
| repository_client ruff/mypy | **PASS**; 26 source files |
| repository_service ruff/mypy | **PASS**; 195 source files |
| `git diff --check` | **PASS** |
| source/test tree identity against `31235dc` | **PASS** |

Commands:

```text
cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_operation_store.py tests/test_control_db_migrations.py tests/test_sqlite_operation_store.py tests/test_architecture.py
  -> 491 passed
cd vnext/backend && uv run pytest -q -m unit
  -> 1319 passed, 24 deselected, 1 pre-existing Starlette/httpx deprecation warning
cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py
  -> 24 passed
cd vnext/backend && uv run pytest -q -m serial tests/test_sqlite_operation_store_integration.py
  -> 2 passed, 22 deselected
cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 203 source files
cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
git diff --check
  -> pass
git diff --name-only 31235dc820472a5ca2c99138fdf150090cfe122d..29aa42d4b5c3d405ee9be24207e3fd1cddae9f72 -- vnext/backend/src vnext/backend/tests
  -> empty; source/test tree matches validated candidate
```

R2 does not use Dolt. The integration gate covers on-disk WAL, independent connections,
migration/reopen, rollback and process-termination visibility; the two fixed-time/process cases
are the applicable serial owners. No test depends on settings, Compose, entrypoint, mount, UID/GID,
socket, pidfile or other container-only behavior.

## 4. Container and benchmark disposition

```text
Current source candidate: 31235dc820472a5ca2c99138fdf150090cfe122d
Current documentation HEAD: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
Container rebuild required for S7: no
Reason: the R2 candidate does not touch Dockerfile, dependency lock, base image, entrypoint, Compose, environment wiring, health/readiness wiring, UID/GID, mount, socket, pidfile, broker/helper or container-only runtime behavior
Last verified image revision for this Phase 4 candidate: none
Container gate: not-applicable
Deferred required execution point: final Phase 4 production candidate must rebuild current HEAD and run its production container/Compose gates
Benchmark: not-applicable; R2 makes no latency, throughput or capacity claim
```

## 5. Deferred boundary and authorization

This handoff seals R2's durable store, migration, readback, integrity, claim, lease, CAS and
cross-table transaction seam. It allows only a P4-R3-S0 entry discussion. It does not authorize
R3 worker/bootstrap/settings/Compose implementation, R4/R5 policy, P5 business/outbox work, or
real Repository effects.

R2 exits `pass`; any later change to the source/test tree, validated ancestor, accepted schema or
runtime boundary requires a new focused gate and, where applicable, a new independent review.
