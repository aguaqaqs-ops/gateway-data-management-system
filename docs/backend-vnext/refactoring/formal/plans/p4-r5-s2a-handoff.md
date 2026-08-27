# P4-R5-S2a Handoff: Expired Lease Classification, Retry Scheduling and CAS Takeover

状态：**PASS — S2a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 + R3 Operation Runtime

上游：[P4-R5-S1a Handoff](p4-r5-s1a-handoff.md)、[P4-R5-S1b Handoff](p4-r5-s1b-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s2a
step_id: P4-R5-S2a
input_handoff_sha: 2e9b7fe3d178d9dd8530a08602937e2acab489990542a8edfd23c3495b970212
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s1b_validated_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/recovery.py
  - vnext/backend/src/gateway_backend/operations/worker_startup.py
  - vnext/backend/tests/test_operation_takeover.py
  - vnext/backend/tests/test_operation_recovery_process.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s2a-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: operations startup/recovery wiring only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s2a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - bootstrap replacement of _fail_closed_recovery with build_startup_recovery composition
  - S2b original identity reconcile adapter and stub recovery path
  - S2c internal authorized recovery command port
  - S3a/S3b/S3c consumer and cross-boundary fault matrix
reopen_conditions:
  - need for R2 store port widening to express guarded RUNNING to RETRY_WAIT CAS
  - need for Operations import of application recovery implementation
  - need for RUNNING to RUNNING direct lease replacement
next_step: P4-R5-S2b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.operations.recovery` now owns the S2a runtime composition surface on top of
frozen S1b policy:

- `StartupRecovery` / `build_startup_recovery` apply `classify_startup` decisions through guarded
  `compare_and_set_*` CAS in a fresh write UoW;
- `RUNNING -> RETRY_WAIT` clears lease identity, preserves `started_at` and `attempt_count`, and
  schedules `retry_not_before` per policy;
- `MANUAL_RECOVERY_REQUIRED` applies paired step/operation CAS when session budget is exhausted;
- `StaleWrite` / `StoreBusy` during recovery map to `StartupDisposition.RETRYABLE_BLOCK`.

`gateway_backend.operations.worker_startup` accepts optional `startup_recovery: StartupRecovery` and
delegates expired-lease pairs to it while preserving the existing `RecoveryHook` port for unit
harnesses. `StaleWrite` at the startup gate is transient like `StoreBusy`.

`worker_runtime.py` required no changes: existing startup backoff and `list_claim_candidates` due
semantics already schedule `RETRY_WAIT` reclaim.

R2 store port was verified sufficient (`compare_and_set_step` with expired-lease precondition,
`require_live_lease=False`; `OperationLifecycleActions.claim_one` for due reclaim). No migration,
schema, port signature or bootstrap composition change was introduced.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- No `RUNNING -> RUNNING` lease replacement; takeover is `RUNNING -> RETRY_WAIT -> RUNNING` only.
- Policy diagnostic codes are uppercased when persisted as `OperationDiagnostic` to satisfy R1 bounds.
- Recovery read/write UoW separation in `WorkerStartup` is preserved.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_takeover.py
  -> 73 passed, 7 deselected

cd vnext/backend && uv run pytest -q -m unit
  -> 1581 passed, 69 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_takeover.py
  -> 7 passed, 1 deselected

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py
  -> 2 passed, 7 deselected

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 234 source files

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

## 4. Handoff boundary

S2b is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S2b, S2c, S3, S4, or P5B/Repository implementation.
