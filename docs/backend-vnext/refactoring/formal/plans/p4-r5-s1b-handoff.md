# P4-R5-S1b Handoff: Policy Matrix, Budgets and Transition Mapping

状态：**PASS — S1b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 + Operation Runtime

上游：[P4-R5-S1a Handoff](p4-r5-s1a-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s1b
step_id: P4-R5-S1b
input_handoff_sha: 2e9b7fe3d178d9dd8530a08602937e2acab489990542a8edfd23c3495b970212
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s1a_validated_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/recovery.py
  - vnext/backend/tests/test_operation_recovery_policy.py
  - vnext/backend/tests/test_operation_state.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s1b-handoff.md
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1b_no_durable_state_or_process_harness
serial: not_applicable_s1b_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: pure policy/decision module only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s1b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2a expired lease classification, retry scheduling and CAS takeover wiring
  - S2b original identity reconcile adapter and stub recovery path
  - S2c internal authorized recovery command port
  - S3a/S3b/S3c consumer and cross-boundary fault matrix
reopen_conditions:
  - need for Operations import of application recovery implementation
  - need for R1/R2 schema, CAS, status or error-taxonomy change
  - need for worker startup/runtime composition before S2a handoff authorizes it
next_step: P4-R5-S2a
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.operations.recovery` now owns the S1b pure policy surface:

- frozen budgets: three recovery sessions per Step, backoff `1s -> 2s -> 4s` capped at `10s`,
  `60s` active reconcile session, injectable bounded jitter;
- closed namespaced diagnostics including `r5.recovery_authorized` (operator port wiring deferred to S2c);
- `RecoveryPolicyDecision` / `RecoveryPolicyOutcomeDisposition` mirrors of S1a application contracts
  without importing `gateway_backend.application`;
- classifiers for expired lease, startup, cancel, and handler failure matrix rows;
- `RecoveryTransitionIntent` plus `transition_for_decision` / `transition_for_outcome` normative
  mapping to existing R1 step/operation statuses.

No worker startup/runtime wiring, CAS writes, migrations, operator command port, application handler
changes or Repository effect was introduced.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- Policy transition intents are a subset of the existing `state.py` allowed transition matrix.
- `RecoveryPolicyDecision` is structurally convertible to application `RecoveryDecision` in tests only;
  composition wiring remains S2a-owned.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_contracts.py \
  tests/test_operation_state.py
  -> 447 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1580 passed, 61 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 232 source files

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
policy-only step.

## 4. Handoff boundary

S2a is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S2a, S2b, S2c, S3, S4, or P5B/Repository implementation.
