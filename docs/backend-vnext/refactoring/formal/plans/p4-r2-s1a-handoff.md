# P4/R2-S1a Handoff: Store Port and Error Boundary

状态：**PASS**

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R2-S0 Independent Entry Acceptance](p4-r2-s0-entry-acceptance.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s1a
step_id: P4-R2-S1a
input_handoff_sha: e671fce0888aff7049229e39c68ae752aa23a550
input_validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
validated_code_sha: eaa25e6b4d44eee05fdf2ffdce06308a08fe54d0
validated_code_tree_identity: vnext_backend_operations_and_tests_match_eaa25e6
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/store.py
  - vnext/backend/src/gateway_backend/operations/__init__.py
  - vnext/backend/tests/test_operation_store.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_architecture.py
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1a_no_durable_state
serial: not_applicable_s1a_no_fixed_time_or_process_boundary
five_package_static: pass
container_gate: not_applicable_s1a_no_runtime_boundary_change
benchmark: not_applicable_s1a_port_only
next_step: P4-R2-S1b
next_step_authorized: no
```

## 1. Delivered boundary

S1a publishes the SQLite-neutral `OperationStore` and `OperationUnitOfWork` ports, the bounded
`ClaimCandidate`, pagination limits, and the seven individually typed store outcomes:

- `RecordNotFound`
- `StaleWrite`
- `LeaseExpired`
- `ConflictingDuplicate`
- `StoreBusy`
- `CorruptPersistedRecord`
- `UnsupportedSchemaVersion`

The store participant exposes no commit/rollback operation. `OperationUnitOfWork` owns the context
boundary and may expose future repositories without introducing a generic repository framework.
Successful mutations reuse R1 `TransitionDisposition`; SQLite details and durable mapping remain
S1b-owned.

`ClaimCandidate` contains only operation/step identity, `JobStepKey`, claimable status, and UTC
ordering timestamps. It does not carry payload, handler, business references, SQL, connection,
cursor, row, or filesystem path data.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit tests/test_operation_store.py tests/test_operation_contracts.py tests/test_architecture.py
  -> 269 passed
cd vnext/backend && uv run pytest -q -m unit
  -> 1255 passed, 1 pre-existing Starlette deprecation warning
cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
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

No integration, serial, container, or benchmark gate applies: S1a contains no SQLite file,
external process, fixed-time budget, deployment wiring, dependency change, or performance claim.

## 3. Deferred work and reopen conditions

Deferred to S1b/S2a: concrete SQLite connection and UoW, migration/schema, row mapping, readback,
CAS execution, error translation from SQLite, and durable transaction evidence.

Reopen before S1b if the public port requires SQLite/connection/path types, a second transaction
owner, a generic repository framework, a new error taxonomy, a changed R1 disposition/guard, or
business/Repository/worker/deployment ownership.
