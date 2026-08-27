# P4-R5-S2c Handoff: Authorized Operator Recovery Port

状态：**PASS — S2c implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 Operation Runtime

上游：[P4-R5-S2b Handoff](p4-r5-s2b-handoff.md)、[P4-R5-S2a Handoff](p4-r5-s2a-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s2c
step_id: P4-R5-S2c
input_handoff_sha: c2648f13ed0b1f64ae8121763ea78e020ba9a55b08b9ea56451d8019e892bae7
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s2b_validated_tip
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/recovery.py
  - vnext/backend/tests/test_operation_recovery_policy.py
  - vnext/backend/tests/test_operation_takeover.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s2c-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s2c_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: internal operator recovery port and SQLite CAS integration only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s2c
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3a pure-compute synthetic job consumer and operator-lease execution wiring
  - bootstrap/worker composition for AuthorizedOperatorRecovery
  - S3b/S3c external-effect stub consumer and cross-boundary fault matrix
reopen_conditions:
  - need for MANUAL to RETRY_WAIT transition to integrate scheduler claim_one
  - need for Operations import of application recovery implementation
  - need for R1/R2 schema, CAS, status or error-taxonomy change
next_step: P4-R5-S3a
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.operations.recovery` now owns the S2c internal operator recovery surface:

- frozen `OperatorRecoveryCommand`: `RESUME_RECONCILE`, `RETRY_FROM_CHECKPOINT`,
  `ABORT_CONFIRMED_FAILURE`;
- `OperatorRecoveryRequest` with operation/step identity, expected optimistic versions and
  bounded operator reason;
- `authorize_operator_command`, `transition_for_operator_command`,
  `build_operator_recovery_candidates` and `apply_operator_recovery_transition`;
- `AuthorizedOperatorRecovery` / `build_authorized_operator_recovery` applying
  `recovery_authorized=True` CAS through existing R2 `compare_and_set_*` ports.

Command semantics (R1 matrix aligned):

| Command | Capability guard | Transition |
|---|---|---|
| `RESUME_RECONCILE` | `EXTERNAL_EFFECT` | `MANUAL_RECOVERY_REQUIRED` → `RUNNING` (step + operation) with operator-recovery lease |
| `RETRY_FROM_CHECKPOINT` | `PURE_RECOMPUTE` | same authorized `MANUAL` → `RUNNING` resume |
| `ABORT_CONFIRMED_FAILURE` | any (from `MANUAL`; terminal replay from `FAILED`) | paired `MANUAL` → `FAILED` with operator reason in diagnostic |

`RUNNING` resume clears persisted diagnostics per R1 contract bounds; operator reason is
persisted on `ABORT_CONFIRMED_FAILURE`. `attempt_count` and `started_at` are preserved on
resume/retry. No HTTP, auth principal, migration, force-terminal escape hatch or application
import was introduced.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- No `MANUAL` → `RETRY_WAIT` edge added; resume uses authorized `MANUAL` → `RUNNING` with
  bounded `OPERATOR_RECOVERY_WORKER_ID` lease for S3 execution wiring.
- Manual records remain non-claimable via `list_claim_candidates`; occupancy is not released
  through `CANCELLED`/`SUCCEEDED` shortcuts.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_takeover.py
  -> 92 passed, 15 deselected

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_takeover.py
  -> 15 passed, 1 deselected

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

Serial, Dolt, container and benchmark gates were not applicable to this operator port step.

## 4. Handoff boundary

S3a is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided; `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S3a, S3b, S3c, S4, or P5B/Repository implementation.
