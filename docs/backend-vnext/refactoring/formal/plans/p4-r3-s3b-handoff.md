# P4/R3-S3b Handoff: Settings, Bootstrap, Module CLI and Process Evidence

状态：**PASS — S3b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Backend Bootstrap + Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s3b
step_id: P4-R3-S3b
input_handoff_sha: 5036dd4f1fb71b19a3531c340b2d93aab096296c1977af958e30413c7a4e9823
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:cf411aa52974d103cf5bb1d38eee87f550e2d0ed9da9fda14df3ebfd5e91a849
validated_head: edb15144ac5eae54e970c28f12f58e5e45b075a9
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/bootstrap/__init__.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/src/gateway_backend/settings.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_operation_worker_process.py
  - vnext/backend/tests/test_operation_worker_lifecycle.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/README.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s3b-handoff.md
focused_tests: pass
backend_unit: pass_1387_deselected_29
integration: pass_1_non_serial_and_pass_6_serial
serial: pass_6
five_package_static: pass
container_rebuild_required: yes
container_reason: module entrypoint, settings, signal wiring, startup and shutdown process boundary changed
last_verified_image_revision: none_for_s3b
container_gate: deferred
required_execution_point: P4-R3-S7 final candidate
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - current-HEAD container rebuild and worker smoke gate at S7
  - R4 immutable job registry, payload interpretation, checkpoint/READY closure and executor policy
  - R5 retry, takeover, expired-lease disposition and external-effect reconciliation
  - P5 HTTP/global readiness, deployment signal wiring, Compose and global quiescence
reopen_conditions:
  - need for a configurable worker budget, multiple in-flight executors or a second worker process
  - need for production job handlers before R4 registry/policy ownership exists
  - need for durable worker lifecycle evidence, IPC, socket, pidfile, broker or sidecar
  - need for container/Compose wiring before the scheduled S7 gate
  - need to change R1 records, R2 schema/store/error taxonomy or lease fencing semantics
next_step: P4-R3-S4
next_step_authorized: no
```

## 1. Delivered boundary

S3b adds the concrete process boundary without changing `BackendSettings`, `app.py`, the
Operations public contract, the R2 schema, packaging, Dockerfile or Compose files.

`OperationWorkerSettings` is an independent frozen settings model with the
`GATEWAY_BACKEND_OPERATION_WORKER_` prefix. `control_db_path` is required and absolute; its
parent is created by bootstrap before the existing `initialize_control_db` boundary is called.
The lifecycle budgets are fixed at the R3 values: 30-second lease, 10-second heartbeat,
one-second idle poll, one-to-ten-second transient backoff, 60-second startup retry budget,
180-second drain timeout, one in-flight executor and claim limit one.

The module entrypoint is:

```text
python -m gateway_backend.bootstrap.operation_worker
```

Bootstrap composes fresh read/write `ControlDbUnitOfWork` factories, an immutable empty registry,
and a fail-closed recovery hook. Empty DB startup completes the existing integrity/topology double
gate and idles. A runnable record with no R4 handler emits a bounded startup failure before claim,
leaving the durable record unchanged.

SIGTERM and SIGINT are installed only in the main thread. Their handler only sets a process-local
event; repeated signals do not force-kill, perform DB I/O, join threads or write cancellation.
Worker events log only bounded IDs/categories. Bootstrap and fatal paths never log exception text,
the configured DB path or lease tokens. No HTTP endpoint, socket, pidfile, ready file, durable worker
state, IPC or global readiness claim was added.

## 2. Verification

```text
cd vnext/backend
uv run pytest -q -m unit
  -> 1387 passed, 29 deselected, 1 pre-existing Starlette deprecation warning

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 1 passed, 4 deselected

uv run pytest -q -m serial \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 4 passed, 1 deselected

uv run ruff check . && uv run mypy
  -> pass; mypy 217 source files

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

The focused file/process evidence uses a temporary local SQLite/WAL path and the real module entrypoint:
empty DB reaches `worker_ready`, SIGTERM produces drain and clean `worker_exited`, schema/WAL
survive reopen, and corrupt/higher-schema startup exits non-zero without path/token leakage.
The file-backed composition tests prove the empty scheduler's double startup gate, fail-closed
missing-handler behavior, heartbeat renewal and concurrent cancellation readback. No Dolt or
Repository Service dependency is used. A killed helper process retains the RUNNING/checkpoint
version and leaves the lease naturally expired; no takeover is asserted.

## 3. Handoff boundary

The implementation and S1a–S3a candidate changes remain in the working tree because no explicit
commit authorization was provided. The source/test tree identity above includes the current Python
source and tests; ignored bytecode caches are excluded. `validated_code_sha` must be replaced with
the candidate code commit SHA only after explicit authorization.

S7 must rebuild the current candidate HEAD and run the container gate with a precisely created and
mounted local control-DB directory. The gate must record image ID/digest, source-tree identity,
`worker_ready`, SIGTERM drain/exit 0, schema/WAL reopen and redacted logs. This handoff authorizes
no S4 review work, R4/R5 implementation, P5 implementation or production Repository effect.
