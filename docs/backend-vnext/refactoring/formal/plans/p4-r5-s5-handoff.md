# P4-R5-S5 Handoff: Finding-Scoped Remediation

状态：**PASS — S5 findings (F1/F2/F3/F4) closed; S6 re-review not authorized by this document**

日期：2026-08-27

Owner：Bootstrap + Operation Runtime + Application Recovery

上游：[P4-R5-S6 Independent Review](p4-r5-s6-independent-review.md)、
[P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md)

```yaml
step_id: P4-R5-S5
context: new_conversation
input_handoff_sha: p4-r5-s6-independent-review.md
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_worktree: documented_dirty_candidate
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/recovery.py
  - vnext/backend/src/gateway_backend/operations/lease_session.py
  - vnext/backend/src/gateway_backend/operations/worker.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/tests/test_operation_recovery_policy.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_operation_worker_contracts.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-r3-recovery-release-reopen.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s1a-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s1b-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s5-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_run_s5_scope
five_package_static: pass
five_package_static_basis: backend mypy 0 errors + five-package ruff/mypy all green
public_boundary_reopen: LeaseSession_publish_recovery_release_bounded_recovery_release_only
public_boundary_reopen_record: p4-r5-r3-recovery-release-reopen.md
container_rebuild_required: yes
container_reason: worker/runtime RecoveryPort composition touched; S7 owns current-HEAD image gate
last_verified_image_revision: none_for_current_candidate
container_gate: deferred_to_S7
benchmark: not_applicable_no_performance_claim
findings:
  - F1 external-effect RecoveryPort composed into worker claim path — closed
  - F2 RECONCILE_PENDING respects three-session budget — closed
  - F3 LeaseSession.publish_recovery_release protocol mypy contravariance — closed
  - F4 R3 LeaseSession public protocol widened without owning-contract reopen — closed with explicit R3/architecture boundary reopen
deferred_items:
  - explicit commit authorization and clean candidate before S7
  - current-HEAD image/container gate owned by S7
  - S6 independent re-review authorization
reopen_conditions:
  - any fix requiring R1/R2 schema, status, CAS or error-taxonomy change
  - any real Repository effect, new principal/IPC, second registry or generic evidence state machine
  - any R3 protocol extension beyond bounded recovery-release (see p4-r5-r3-recovery-release-reopen.md)
handoff_document: p4-r5-s5-handoff.md
next_step: P4-R5-S6
next_step_authorized: no
```

## 1. Findings closed

### F1 — P1: external-effect RecoveryPort composed into worker claim path

**Regression:** `test_worker_runtime_external_effect_accepted_takeover_polls_original_identity`

**Closure:** [`build_worker_runtime()`](vnext/backend/src/gateway_backend/bootstrap/operation_worker.py) wraps executors via `_RecoveryAwareWorkerRegistry` and `build_recovery_routed_executor()`. `EXTERNAL_EFFECT` steps with a durable checkpoint route to `build_external_effect_stub_recovery_port()` at claim time; outcomes apply through `LeaseSession.publish_recovery_release()` and `finalize_handler_recovery()`.

### F2 — P2: `RECONCILE_PENDING` respects three-session budget

**Regression:** `test_transition_for_outcome_matrix` row `reconcile_pending_session_exhausted`

**Closure:** [`transition_for_outcome()`](vnext/backend/src/gateway_backend/operations/recovery.py) checks `recovery_sessions_exhausted(attempt_count)` before scheduling another `RETRY_WAIT` for `RECONCILE_PENDING`.

### F3 — P1: `LeaseSession.publish_recovery_release` protocol mypy contravariance

**Regression:** `test_protocol_signatures_use_existing_records_and_ports` (`publish_recovery_release` `get_type_hints` probe); backend `mypy` 0 errors

**Closure:** [`worker.LeaseSession`](vnext/backend/src/gateway_backend/operations/worker.py) aligns `publish_recovery_release(intent)` with concrete [`lease_session.LeaseSession`](vnext/backend/src/gateway_backend/operations/lease_session.py) via `TYPE_CHECKING` import of `RecoveryTransitionIntent` (no runtime `recovery` ↔ `worker` cycle). [`finalize_handler_recovery()`](vnext/backend/src/gateway_backend/operations/recovery.py) calls `publish_recovery_release` directly (no `getattr`). Contract probe prevents regression to `intent: object`.

### F4 — P1: R3 LeaseSession public protocol widened without owning-contract reopen

**Regression:** architecture import-boundary probes; sealed static and behavioral evidence from F1–F3

**Closure:** [P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md) explicitly re-accepts bounded `LeaseSession.publish_recovery_release` on the R3 protocol and concrete session. `RecoveryPort` remains a composition port only. R3 depends on R5 `RecoveryTransitionIntent` within `gateway_backend.operations` and does not import `gateway_backend.application`. Cross-references recorded in [p4-r5-s1a-handoff.md](p4-r5-s1a-handoff.md) and [p4-r3-s1b-handoff.md](p4-r3-s1b-handoff.md).

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_worker_integration.py \
  tests/test_operation_effect_reconcile.py \
  tests/test_architecture.py
  -> 146 passed, 22 deselected (F1/F2 round)

cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_architecture.py
  -> 62 passed (F3 contract + architecture probes)

cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py::test_transition_for_outcome_matrix \
  tests/test_operation_worker_integration.py::test_worker_runtime_external_effect_accepted_takeover_polls_original_identity
  -> 10 passed, 1 deselected (F1/F2 focused regression)

cd vnext/backend && uv run ruff check . && uv run mypy
  -> 0 errors

five-package ruff/mypy (backend, shared_kernel, repository_contracts, repository_client, repository_service)
  -> all green
```

Serial/process/container gates deferred to S7 per execution plan.

## 3. Handoff boundary

S6 re-review is the named next step and is not authorized here. S7 remains blocked until S6 passes, explicit commit authorization is recorded, and the mandatory current-HEAD image/container gate completes.
