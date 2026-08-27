# P4/R3-S1b Handoff: LeaseSession and Atomic Publication

状态：**PASS — S1b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s1b
step_id: P4-R3-S1b
input_handoff_sha: edb15144ac5eae54e970c28f12f58e5e45b075a9
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:6c64a7cadd2c2cad1b41b1f746c54c35badfc5387225e85e76404587e7da1f2f
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/lease_session.py
  - vnext/backend/src/gateway_backend/operations/worker.py
  - vnext/backend/tests/test_operation_lease_session.py
  - vnext/backend/tests/test_operation_worker_contracts.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s1b-handoff.md
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1b_fake_uow_no_sqlite_or_durable_file
serial: not_applicable_s1b_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: operations-only worker capability; no image, entrypoint, settings, deployment, or runtime boundary changed
last_verified_image_revision: none_for_s1b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2a startup integrity/topology gates and atomic claim
  - S2b scheduler, executor thread, heartbeat retry, and cancellation orchestration
  - R4 JobDefinition registry, payload, checkpoint closure, successor and final policy
  - R5 retry, takeover, expired lease disposition, and effect reconciliation
  - P5 settings, bootstrap, process signal wiring, and container evidence
reopen_conditions:
  - need for SQLite, settings, bootstrap, scheduler, process, or business-context imports
  - need for direct store CAS/insert outside OperationLifecycleActions
  - need for a new worker error taxonomy, durable worker evidence, or mutable registry
  - need for multiple active executors, multi-worker coordination, or non-local storage
next_step: P4-R3-S2a
next_step_authorized: no
```

## 1. Delivered boundary

S1b adds a concrete `LeaseSession` under `gateway_backend.operations.lease_session` while keeping
the `gateway_backend.operations` root export surface unchanged. The session fixes worker/token and
operation/step identity, serializes mutations with one per-session lock, and opens a fresh write UoW
for every refresh, heartbeat, checkpoint, successor publication, or operation publication.

Every live mutation reloads Operation/Step, validates the RUNNING state and live lease, propagates
cancel intent monotonically, and calls only the existing R2 `OperationLifecycleActions`. Stale or
expired ownership marks `ExecutionControl.lease_lost` and fences subsequent publication. Checkpoint
safe handoff is bound to the latest generation returned only after the UoW commit boundary.

The implementation does not add schema, store methods, settings, bootstrap, scheduler, executor
threads, recovery policy, business payload handling, or container wiring.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_architecture.py
  -> 60 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1353 passed, 24 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 207 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
```

`git diff --check` passed. Integration, serial, Dolt, container, and benchmark gates are not
applicable to this fake-UoW, operations-only step.

## 3. Handoff boundary

S2a is the only next step and remains unauthorized. The validated implementation is intentionally
left in the working tree because no explicit git commit authorization was provided. This handoff does
not authorize S2a, S2b, R4, R5, or P5 implementation.

## 4. Post-S1b lineage addendum (2026-08-27)

`LeaseSession.publish_recovery_release()` was added later under
[P4-R5-R3 Recovery-Release Reopen](p4-r5-r3-recovery-release-reopen.md). It extends the S1b
fresh-transaction publication model with a bounded recovery-release mutation on a live lease. This
addendum records lineage only; it does not retroactively widen the sealed S1b validation scope or
change the S1b verification record above.
