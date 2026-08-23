# P4/R2-S2a Handoff: Create, Readback and Guarded CAS

状态：**PASS**

日期：2026-08-23

Owner：Control DB infrastructure (`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S1b Handoff](p4-r2-s1b-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s2a
step_id: P4-R2-S2a
input_handoff_sha: 5de2c99311b28e19789d31342e966dd85adb73a1
input_validated_code_sha: 3b837dba23ba47e36910fbffd5d49f0889f20da1
validated_code_sha: 2c3c0d4e6944de3383154999e20489aac336a8bf
candidate_commit: 2c3c0d4e6944de3383154999e20489aac336a8bf
validated_code_tree_identity: vnext_backend_control_db_and_tests_match_2c3c0d4
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_no_fixed_time_or_process_boundary
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary
benchmark: not_applicable_no_performance_claim
next_step: P4-R2-S2b
next_step_authorized: no
```

## 1. Delivered behavior

`SQLiteOperationStore` now implements the transaction-scoped `OperationStore` participant. It never
commits or rolls back; `ControlDbUnitOfWork` owns the connection, transaction, read-only boundary,
injected UTC transaction clock, and `operations` participant binding.

Create paths insert a `QUEUED` Operation with its initial `PENDING` Step or a `PENDING` successor.
Complete record equality returns `IDEMPOTENT`; any identity collision with different content returns
`ConflictingDuplicate`. ID reads and all paginated read paths reconstruct records through the existing
R1 row mappers and parsers.

Steps, Operation status lists, and claim candidates use bounded canonical keyset cursors. Claim reads
only due materialized `PENDING`/`RETRY_WAIT` rows in the frozen ordering; it does not claim or mutate
them.

Operation and Step CAS execute inside the caller-owned transaction, in R1 guard/precondition order,
with version and lease identity predicates. Terminal exact duplicates return `IDEMPOTENT` without a
second UPDATE. Stale, expired, missing, conflict, and corruption outcomes remain distinct.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_store.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 82 passed

cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py
  -> 7 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1284 passed, 7 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 202 source files
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
```

Integration coverage proves file-backed create/readback after reopen, shared owner/Operation commit,
shared rollback, read-only write rejection, and one clock sample per UoW transaction. No fixed-time,
process-crash, image/deployment, or benchmark claim applies to S2a.

## 3. Atomicity and boundary record

```yaml
atomicity_matrix:
  create: operation_insert_and_initial_step_insert_share_uow_transaction
  readback: every_operation_and_step_row_revalidated_by_R1_parser
  generic_cas: load_guard_precondition_lease_check_version_lease_predicated_update
  terminal_duplicate: idempotent_without_update
  owner_composition: synthetic_owner_and_operation_commit_or_rollback_together
sqlite_profile:
  journal_mode: WAL
  foreign_keys: true
  synchronous: FULL
  write_begin: BEGIN IMMEDIATE
  busy_timeout_ms: 5000
known_capacity_limits:
  page_limit: 100
  claim_limit: 1
  max_in_flight: 1
deferred_items:
  - S2b claim/heartbeat/checkpoint/cancel/terminal action composition
  - S3a integrity and corruption hardening
  - S3b contention and crash visibility evidence
  - R3 worker/settings/volume/readiness boundary
  - R4 successor and final outcome policy
  - R5 retry/backoff/effect-aware takeover policy
reopen_conditions:
  - changed R1 parser, transition guard, persisted semantic field, or public store taxonomy
  - business/outbox/Repository ownership or deployment wiring enters the adapter
  - direct RUNNING lease replacement, automatic repair, quarantine, or durable rejection evidence is required
  - accepted SQLite lock/capacity boundary no longer holds
```

S2a does not authorize S2b, R3, R4, R5, P5, Repository effects, or production outbox integration.
