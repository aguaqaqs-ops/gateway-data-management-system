# P4-R5-S1a Handoff: Recovery Capability, Decision/Outcome and Reconcile Port

状态：**PASS — S1a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 + Application Recovery owner

上游：[P4-R5-S0 Independent Entry Acceptance](p4-r5-s0-entry-acceptance.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s1a
step_id: P4-R5-S1a
input_handoff_sha: 9beea4572b5896f2e7268b1c38aa20e54c4ea1a3
input_validated_code_sha: 9beea4572b5896f2e7268b1c38aa20e54c4ea1a3
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s0_accepted_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/__init__.py
  - vnext/backend/src/gateway_backend/application/job_definitions.py
  - vnext/backend/src/gateway_backend/application/recovery.py
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_job_definition_contracts.py
  - vnext/backend/tests/test_job_definition_registry.py
  - vnext/backend/tests/test_job_payload_decoding.py
  - vnext/backend/tests/test_operation_checkpoint_contracts.py
  - vnext/backend/tests/test_operation_recovery_policy.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s1a-handoff.md
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1a_no_durable_state_or_process_harness
serial: not_applicable_s1a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: application-owned recovery contracts only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s1a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S1b retry/manual/reconcile/cancel/startup policy matrix and budgets in operations/recovery.py
  - S2a expired lease classification, retry scheduling and CAS takeover wiring
  - S2b original identity reconcile adapter and stub recovery path
  - S3a/S3b/S3c consumer and cross-boundary fault matrix
reopen_conditions:
  - need for Operations import of application recovery implementation
  - need for R1/R2 schema, CAS, status or error-taxonomy change
  - need for second registry, persisted recovery field or R3 public protocol widening
    (exercised and re-accepted for bounded recovery-release only — see
    [P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md))
next_step: P4-R5-S1b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application` now owns the S1a recovery contract surface:

- frozen `RecoveryCapability` on the existing immutable `JobDefinition` descriptor as a
  non-persisted field (`PURE_RECOMPUTE | EXTERNAL_EFFECT | NON_RETRYABLE`);
- bounded `RecoveryDecision` and `RecoveryOutcome` records with closed disposition enums,
  namespaced diagnostic codes and read-only fields without payload, artifact bytes, SQL,
  network clients or callables;
- `RecoveryPort.recover(operation, step, control, lease_session) -> RecoveryOutcome` as an
  in-process composition port, not HTTP, persisted registry or R3 public protocol.

`synthetic_jobs` mechanical updates bind `PURE_RECOMPUTE` and `EXTERNAL_EFFECT` explicitly.
No operations runtime/store/bootstrap wiring, policy matrix, migration, second registry,
operator command port or Repository effect was introduced.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- `RecoveryDecision` is read-only bounded policy input; `RecoveryOutcome` is the sole
  application-to-R5 handler result type.
- `RecoveryPort` is composition-only; no handler recovery execution or transition mapping yet.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_job_definition_contracts.py \
  tests/test_architecture.py
  -> 72 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1522 passed, 61 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 231 source files

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

Integration, serial, Dolt, container and benchmark gates were not applicable to this
contract-only step.

## 4. Handoff boundary

S1b is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S1b, S2, S3, S4, or P5B/Repository implementation.
