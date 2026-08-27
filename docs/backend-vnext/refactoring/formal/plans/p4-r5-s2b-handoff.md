# P4-R5-S2b Handoff: Effect Identity Reconcile Adapter and Stub Recovery Path

状态：**PASS — S2b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 + Application Recovery

上游：[P4-R5-S2a Handoff](p4-r5-s2a-handoff.md)、[P4-R5-S1a Handoff](p4-r5-s1a-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s2b
step_id: P4-R5-S2b
input_handoff_sha: c2648f13ed0b1f64ae8121763ea78e020ba9a55b08b9ea56451d8019e892bae7
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s2a_validated_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/recovery.py
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/tests/test_operation_effect_reconcile.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s2b-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s2b_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: application-owned reconcile adapter only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s2b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2c internal authorized recovery command port
  - bootstrap/worker composition wiring for RecoveryPort
  - S3a/S3b/S3c consumer and cross-boundary fault matrix
reopen_conditions:
  - need for Operations import of application recovery implementation at runtime
  - need for R1/R2 schema, CAS, status or error-taxonomy change
  - need for real Repository client wire or P5 effect paths
next_step: P4-R5-S2c
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.recovery` now owns checkpoint-aware external-effect identity
primitives:

- `ExternalEffectRequestIdentity` binding `idempotency_key`, `request_fingerprint` and
  `repository_operation_id`;
- `validate_external_effect_identity`, `classify_external_effect_phase` and mirrored
  `RECONCILE_SESSION_BUDGET_SECONDS` without importing `gateway_backend.operations.recovery`;
- bounded diagnostics `r5.effect_identity_mismatch` and `r5.reconcile_timeout`.

`gateway_backend.application.synthetic_jobs` now owns the S2b reconcile adapter surface:

- shared checkpoint `job_state` keys including `request_fingerprint` and `reconcile_started_at`;
- `PollingExternalEffectStub` poll-by-original-identity wrapper (no `external_effect_stub.py` change);
- `build_external_effect_stub_recovery_port` implementing frozen `RecoveryPort.recover`;
- handler submit path writes fingerprint and reconcile start timestamp; post-request paths poll only
  the original `operation_identity` and never generate a new idempotency key.

No operations runtime/store/bootstrap wiring, operator command port, migration, or Repository/Dolt
effect was introduced.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- Legacy checkpoints without `request_fingerprint` remain readable; explicit fingerprint mismatch
  maps to `MANUAL_RECOVERY` on the recovery port and `CHECKPOINT_JOB_STATE_MISMATCH` on handler reload.
- `RecoveryPort` is composition-only; R5 transition mapping and operator CAS commands remain S2c/S3.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_recovery_policy.py \
  tests/test_job_definition_contracts.py \
  tests/test_architecture.py
  -> 137 passed, 5 deselected

cd vnext/backend && uv run pytest -q -m unit
  -> 1589 passed, 74 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py
  -> 27 passed, 8 deselected

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

Serial, Dolt, container and benchmark gates were not applicable to this application adapter step.

## 4. Handoff boundary

S2c is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S2c, S3, S4, or P5B/Repository implementation.
