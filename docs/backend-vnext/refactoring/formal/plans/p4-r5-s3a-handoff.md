# P4-R5-S3a Handoff: Pure-compute Recovery Consumer

状态：**PASS — S3a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：Application Recovery + Operation Runtime consumer

上游：[P4-R5-S2c Handoff](p4-r5-s2c-handoff.md)、[P4-R5-S2b Handoff](p4-r5-s2b-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s3a
step_id: P4-R5-S3a
input_handoff_sha: ccc7939b91bac40532d52d3c4197e74c3584d4d6630e75a331c0e2a96cb9442b
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s2c_validated_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_operation_recovery_process.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s3a-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: application-owned pure-compute RecoveryPort and test harness only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s3a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3b external-effect stub consumer and cancel-after-request proofs
  - S3c cross-boundary fault matrix consolidation
  - bootstrap/worker composition wiring for RecoveryPort and operator-lease execution
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - need for Operations import of application recovery at worker runtime
  - need to change pure-compute handler default to SAFE_HANDOFF (R4 synthetic test owner)
  - need for R1/R2 schema, CAS, status or error-taxonomy change
next_step: P4-R5-S3b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.synthetic_jobs` now owns the S3a pure-compute recovery consumer:

- `build_pure_compute_recovery_port()` implementing frozen `RecoveryPort.recover()` for
  `RecoveryCapability.PURE_RECOMPUTE`;
- **cancel-before-effect** when `checkpoint_ref is None` and `control.cancel_requested`;
- **checkpoint recompute** from durable `job_state` (`output_artifact_id`, `seed`) through
  `prepare_ready_closure` terminal publication → `RecoveryOutcome.PUBLISHED`;
- **idempotent duplicate** when operation/step are already terminal with `ready_closure_ref`;
- **manual** on missing/unreadable checkpoint or identity mismatch without fabricating READY;
- no successor publication, no external-effect stub paths, no operations import.

`build_pure_compute_handler()` R4 one-shot terminal semantics are unchanged.

Tests in allowed paths prove S3a invariants with `synthetic.pure-compute`:

| Invariant | Test owner |
|---|---|
| checkpoint recompute via RecoveryPort | `test_pure_compute_recovery_port_completes_from_checkpoint` |
| cancel-before-effect | `test_pure_compute_recovery_port_cancel_before_effect` |
| duplicate / idempotent recovery | `test_pure_compute_recovery_port_duplicate_publish_is_idempotent` |
| three-session exhaustion (pure-compute job) | `test_pure_compute_three_session_exhaustion_marks_manual_recovery` |
| lease takeover + reclaim + checkpoint preserve | `test_pure_compute_lease_takeover_reclaim_preserves_started_at_and_checkpoint` |
| successor non-duplication / single closure | `test_pure_compute_retry_does_not_duplicate_successor_or_closure` |
| process-level takeover (serial) | `test_process_startup_takeover_moves_expired_running_to_retry_wait` |

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- No bootstrap default synthetic registration or worker runtime RecoveryPort wiring.
- External-effect stub recovery port and S3b cancel-after-request proofs remain deferred.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_job_recovery.py
  -> 28 passed

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_recovery_process.py
  -> 1 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1608 passed, 88 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py
  -> 33 passed, 8 deselected

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py
  -> 2 passed, 15 deselected

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 235 source files

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

Dolt, container and benchmark gates were not applicable to this application consumer step.

## 4. Handoff boundary

S3b is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S3b, S3c, S4, or P5B/Repository implementation.
