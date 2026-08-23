# P4/R2-S2b Handoff: Claim, Lease and Action Composition

状态：**PASS**

日期：2026-08-23

Owner：Durable operation runtime (`gateway_backend.operations` 与
`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S2a Handoff](p4-r2-s2a-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s2b
step_id: P4-R2-S2b
input_handoff_sha: 602c07e063be48edeb91a41a13e177238e5d06e6
input_validated_code_sha: 2c3c0d4e6944de3383154999e20489aac336a8bf
validated_code_sha: cc0e6a418dabfce73f1c05383d1ca0c4be4a9e1a
candidate_commit: cc0e6a418dabfce73f1c05383d1ca0c4be4a9e1a
validated_code_tree_identity: vnext_backend_s2b_claim_lease_action_composition_match_cc0e6a4
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/persistence.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
focused_tests: pass_90_unit
integration: pass_10
backend_unit: pass_1292_passed_10_deselected
backend_unit_warning: one_pre_existing_starlette_deprecation_warning
five_package_static: pass
serial: not_applicable_no_fixed_time_or_process_boundary
container_gate: not_applicable_no_image_or_deployment_boundary
benchmark: not_applicable_no_performance_claim
schema_or_dependency_change: none
next_step: P4-R2-S3a
next_step_authorized: no
```

## 1. Delivered behavior

`OperationLifecycleActions` is a SQLite-neutral composition layer over the frozen
`OperationStore` port. It performs bounded deterministic claim, first Operation `RUNNING`
composition, fixed 30-second lease assignment, live-lease heartbeat/checkpoint/terminal CAS,
cancel intent, terminal-plus-successor composition, and terminal/recovery Operation composition.
It never opens, commits, or rolls back a transaction; `ControlDbUnitOfWork` remains the sole
transaction owner and exposes its single sampled UTC transaction clock.

Claim candidates now join the owning Operation and exclude `MANUAL_RECOVERY_REQUIRED` and terminal
Operations while preserving the canonical keyset ordering and limit. R1 transition guards,
optimistic versions, lease identity, live lease checks, exact terminal idempotency, and distinct
stale/expired/conflict outcomes remain authoritative.

The root `gateway_backend.operations` public export surface and `OperationStore` signatures remain
unchanged. No schema, dependency, worker, retry, effect, outbox, settings, Compose, HTTP, or
takeover behavior was added.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_store.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 90 passed

cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py
  -> 10 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1292 passed, 10 deselected, 1 pre-existing Starlette deprecation warning

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
```

Integration coverage proves file-backed claim/readback after reopen, same-UoW owner and lifecycle
commit, rollback of claim/action composition, and rollback of a step completion when successor
materialization conflicts. No fixed-time, process-crash, image/deployment, or benchmark claim
applies to S2b.

## 3. Deferred items and boundary record

```yaml
deferred_items:
  - P4-R2-S3a integrity and corruption hardening
  - P4-R2-S3b contention and crash visibility evidence
  - R3 worker/bootstrap/settings/volume/readiness boundary
  - R4 successor and final outcome policy
  - R5 retry/backoff/effect-aware recovery and lease takeover
  - production outbox, Repository effects, HTTP, and deployment wiring
reopen_conditions:
  - changed R1 parser, transition guard, persisted semantic field, or public store taxonomy
  - business/effect/outbox/Repository ownership enters the action composer or adapter
  - direct RUNNING lease replacement, automatic repair, or durable takeover is required
  - accepted SQLite lock/capacity boundary no longer holds
```

S2b passes its module gate and hands off only to `P4-R2-S3a`; this record does not authorize that
step or the broader P4-R2 implementation gate.
