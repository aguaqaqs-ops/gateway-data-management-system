# P4/R3-S1a Handoff: Worker Contracts and Execution Control

状态：**PASS — S1a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s1a
step_id: P4-R3-S1a
input_handoff_sha: edb15144ac5eae54e970c28f12f58e5e45b075a9
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:e0ec179b63cd21e0417074a77507f1838d70d3ad2be9cd6a1fa72baec0545cfe
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/worker.py
  - vnext/backend/tests/test_operation_worker_contracts.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s1a-handoff.md
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1a_no_sqlite_or_durable_state
serial: not_applicable_s1a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: worker contracts only; no image, entrypoint, settings, or deployment boundary
last_verified_image_revision: none_for_s1a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S1b LeaseSession implementation and fresh-transaction publication
  - S2a startup, topology validation, and atomic claim
  - R4 JobDefinition registry, payload, and publication policy
  - R5 recovery, retry, takeover, and effect reconciliation
reopen_conditions:
  - need to expand gateway_backend.operations root exports beyond the existing exact contract
  - need for SQLite, settings, bootstrap, scheduler, thread, subprocess, or business context
  - need for a new worker error taxonomy or mutable/hot-reloaded registry
next_step: P4-R3-S1b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.operations.worker` now owns the SQLite-neutral S1a surface:

- frozen/slots lifecycle, startup disposition, executor acknowledgment, and stable event codes;
- redacted bounded `WorkerEvent` values;
- monotonic `ExecutionControl` signals for drain, cancellation, and lease loss;
- structural registry, executor, recovery, observer, LeaseSession, and read/write UoW protocols.

The existing `gateway_backend.operations` root `__all__` is unchanged. No SQLite, infrastructure,
settings, bootstrap, scheduler, real thread, subprocess, Repository, or business payload dependency
was added. No production registry or deferred stub was created.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py tests/test_architecture.py
  -> 46 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1339 passed, 24 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 205 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
```

`git diff --check` passed. Integration, serial, Dolt, container, and benchmark gates were not
applicable to this contract-only step.

## 3. Handoff boundary

S1b is the only next step and remains unauthorized. The validated code is intentionally left in the
working tree because no explicit git commit authorization was provided; the `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not authorize
S1b, R4, R5, or P5 implementation.
