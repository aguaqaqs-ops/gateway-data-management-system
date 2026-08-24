# P4/R3-S3a Handoff: Drain and Process-Local Lifecycle

状态：**PASS — S3a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s3a
step_id: P4-R3-S3a
input_handoff_sha: 2e9b4d4cf11d06b59294e238863efc3f95ac5f77b448b2e4d5fcb5c7aea6a2d8
input_validated_code_sha: 31235dc8204725ca2c99138fdf150090cfe122a
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:88ba7a67f46deb6010a9b9e68fc28176bf561dc0791960aaaa307038174c519a
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/worker_lifecycle.py
  - vnext/backend/src/gateway_backend/operations/worker_runtime.py
  - vnext/backend/tests/test_operation_worker_lifecycle.py
  - vnext/backend/tests/test_operation_worker_scheduler.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s3a-handoff.md
focused_tests: pass_42
backend_unit: pass_1383_deselected_24
integration: not_applicable_s3a_deterministic_unit_runner
serial: not_applicable_s3a_no_real_signal_or_process_timing
five_package_static: pass
container_rebuild_required: no
container_reason: process-local lifecycle only; no image, entrypoint, settings, deployment, or container boundary changed
last_verified_image_revision: none_for_s3a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3b settings, concrete UoW/bootstrap, module CLI, OS signal wiring, and process evidence
  - R4 JobDefinition registry, payload, checkpoint closure, successor and final policy
  - R5 retry, takeover, expired lease disposition, and effect reconciliation
  - P5 HTTP/global readiness, deployment signal wiring, and global quiescence
reopen_conditions:
  - need for OS signal handling, subprocess/process evidence, settings, or concrete SQLite composition
  - need for timeout kill/detach, force escalation, or a second executor
  - need for persisted worker lifecycle/membership, IPC, broker, sidecar, or global readiness semantics
  - representative handler cannot cooperate with heartbeat, drain, or lease-loss fencing
next_step: P4-R3-S3b
next_step_authorized: no
```

## 1. Delivered boundary

`WorkerLifecycleController` now owns the worker-local, non-durable lifecycle:

```text
STARTING -> READY_TO_CLAIM -> DRAINING -> QUIESCED -> STOPPING -> EXITED
                              |
                              +----------> DRAINING_TIMEOUT
```

Drain intent is monotonic and idempotent. A drain observed during startup is latched and
prevents the first claim after startup. Once draining begins, no new claim is attempted.

`WorkerRuntime` continues the active executor and heartbeat path during drain. Clean quiescence
requires the existing `LeaseSession` acknowledgment validation; a terminal publication or
session-proven safe handoff is required before an active executor can release the worker into
`QUIESCED`. Idle drain uses the same local barrier without changing durable operation state.

The 180-second deadline is driven by an injected monotonic clock. Timeout emits one bounded
`drain_timed_out` event and enters `DRAINING_TIMEOUT`; it does not cancel the operation, kill or
detach the non-daemon executor, stop heartbeat supervision, publish a terminal state, or emit
`worker_exited`. No lifecycle state is persisted and no global quiescence claim is made.

## 2. Public and architectural boundary

The existing `gateway_backend.operations` root exports remain unchanged. The new controller is
available from `gateway_backend.operations.worker_lifecycle` and depends only on existing worker
types. No signal, SQLite, settings, infrastructure, Repository, business payload, or process
boundary dependency was added.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py \
  tests/test_architecture.py
  -> 42 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1383 passed, 24 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 213 source files

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

Integration, serial, Dolt, container, and benchmark gates are not applicable to S3a. The
implementation remains in the working tree because no explicit commit authorization was provided.
This handoff authorizes no S3b, R4, R5, or P5 implementation.
