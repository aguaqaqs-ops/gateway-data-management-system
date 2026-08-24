# P4/R3-S2b Handoff: Scheduler, Executor and Heartbeat

状态：**PASS — S2b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s2b
step_id: P4-R3-S2b
input_handoff_sha: 2e9b4d4cf11d06b59294e238863efc3f95ac5f77b448b2e4d5fcb5c7aea6a2d8
input_validated_code_sha: 31235dc8204725ca2c99138fdf150090cfe122a
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:344a8c5ac375d3160db0a90c5ac2569c0f9c7ccd09e9dec96a12f53952a6f2d9
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/worker.py
  - vnext/backend/src/gateway_backend/operations/lease_session.py
  - vnext/backend/src/gateway_backend/operations/worker_runtime.py
  - vnext/backend/tests/test_operation_worker_contracts.py
  - vnext/backend/tests/test_operation_lease_session.py
  - vnext/backend/tests/test_operation_worker_scheduler.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s2b-handoff.md
focused_tests: pass_85
backend_unit: pass_1378_deselected_24
integration: not_applicable_s2b_deterministic_fake_runner
serial: not_applicable_s2b_no_authoritative_real_thread_or_process_timing
five_package_static: pass
container_rebuild_required: no
container_reason: operations-only scheduler and lease capability; no image, entrypoint, settings, deployment, or process boundary changed
last_verified_image_revision: none_for_s2b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3a signal-independent drain and process-local lifecycle
  - S3b settings, concrete UoW/bootstrap, module CLI, and file/process evidence
  - R4 JobDefinition registry, payload, checkpoint closure, successor and final policy
  - R5 retry, takeover, expired lease disposition, and effect reconciliation
  - P5 HTTP/global readiness and deployment coordination
reopen_conditions:
  - need for SQLite, settings, bootstrap, signal, process, or business-context imports
  - need for direct store CAS/insert outside OperationLifecycleActions
  - inability to keep one active executor and one LeaseSession mutation owner
  - need for multiple executors, mutable registry, durable worker evidence, or multi-worker coordination
  - representative handler cannot cooperate with heartbeat or lease-loss fencing
next_step: P4-R3-S3a
next_step_authorized: no
```

## 1. Delivered boundary

S2b adds `WorkerRuntime` under `gateway_backend.operations.worker_runtime`. The main thread owns
startup retry, claim polling, bounded claim backoff, monotonic heartbeat scheduling, and the
single active executor slot. Each claim creates exactly one non-daemon executor thread and one
`ExecutionControl`/`LeaseSession` pair; a new claim cannot begin until the prior executor has
joined and its acknowledgment has been validated.

Idle polling uses a one-second interruptible wait. Claim `StoreBusy` uses bounded exponential
backoff from one through ten seconds with injected jitter. Heartbeat `StoreBusy` retries only
until the monotonic lease budget expires; exhaustion marks the control lease-lost, emits a bounded
event, joins the executor, and fails closed. Stale or expired ownership remains fenced by the
existing `LeaseSession` behavior.

`LeaseSession` now records a process-local completion acknowledgment only after a committed
terminal/successor publication or a committed checkpoint safe handoff. Runtime validation rejects
direct or mismatched `ExecutorAcknowledgment` values. No FAILED/RETRY state, worker durable state,
SQLite concrete dependency, signal handler, settings, Repository effect, or lifecycle/drain policy
was added.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py \
  tests/test_operation_worker_scheduler.py \
  tests/test_architecture.py
  -> 85 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1378 passed, 24 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 211 source files

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

The S2b tests use injected clocks, waits, jitter, thread factories, fake transaction scopes, and
barriers. Integration, serial, Dolt, container, and benchmark gates are not applicable to this
step. The current source/test tree identity is recorded above; the implementation remains in the
working tree because no explicit commit authorization was provided.

## 3. Handoff boundary

S3a is the only next step and remains unauthorized. S2b does not install OS signal handling, add
worker lifecycle states, enforce drain timeout, create concrete SQLite/bootstrap composition, or
claim process/container evidence. This handoff authorizes no S3a, S3b, R4, R5, or P5 implementation.
