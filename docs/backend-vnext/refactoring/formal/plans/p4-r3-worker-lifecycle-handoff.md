# P4/R3 Worker Lifecycle Handoff

状态：**PASS — S7 module gate complete; P4-R4-S0 discussion only**

日期：2026-08-24

Owner：Operation Worker Runtime + Backend Bootstrap

上游：[P4/R3-S6 Independent Review](p4-r3-s6-independent-review.md)、
[P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)、
[P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)

本文是 R3 的最终 module handoff。它封存 S7 当前 HEAD 的 source/test gate、远程 backend
image provenance 和 worker container smoke；它不授权 R4/R5/P5 implementation 或真实
Repository effect。

```yaml
handoff_kind: p4_r3_worker_lifecycle
step_id: P4-R3-S7
input_handoff_sha: 4c9a29454043fb0fb8d2c0754560a0a2d341883a10fb99949192ccc976e1d038
input_review_sha: e1ea57c68e15e7108614613d57ecff1b41a2ff8a2fdefd1e075481a719e0eaae
validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
validated_source_tree: sha256:26994ad239969afb95556c03d9f03590837a98ac3148f3a9d70d835241370146
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
candidate_worktree_at_gate: clean_committed
result: pass
p4_r3_exit: pass
applicable_steps:
  - P4-R3-S0
  - P4-R3-S1a
  - P4-R3-S1b
  - P4-R3-S2a
  - P4-R3-S2b
  - P4-R3-S3a
  - P4-R3-S3b
  - P4-R3-S4
  - P4-R3-S5
  - P4-R3-S6
  - P4-R3-S7
skipped_steps_with_reason: []
focused_review: pass_after_s5
independent_review: pass
focused_tests: pass_565
backend_unit: pass_1393_deselected_34
integration: pass_24_non_serial_deselected_10
serial: pass_10_deselected_24
five_package_static: pass
container_rebuild_required: yes
container_reason: R3 owns a real module entrypoint and process-local signal/startup/shutdown boundary
last_verified_image_revision: sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf
last_verified_source_tree_image_identity: source_sha=acb3efca06a02aadaa5ce6d1e2a815e85d36e6af; tree_sha256=26994ad239969afb95556c03d9f03590837a98ac3148f3a9d70d835241370146
container_gate: passed
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - R4 JobDefinition registry, payload interpretation, successor policy and production handlers
  - R5 retry, takeover, expired-lease disposition and external-effect reconciliation
  - P5 HTTP/global readiness, deployment signal wiring, Compose and global quiescence
  - multiple workers, global permits, HA, external DB and multi-host SQLite
reopen_conditions:
  - Any source/test/build-input change invalidates the recorded candidate or image provenance.
  - Any executor cannot cooperate with cancellation, lease loss or drain before an irreversible effect.
  - Any fix requires R1 state, R2 schema/store/CAS/error changes, force-kill/detach or IPC.
  - Any need arises for production job execution, retry/takeover policy or deployment/global readiness.
next_step: P4-R4-S0
next_entry: P4-R4-S0 discussion
next_step_authorized: yes_for_discussion_only
r4_implementation_authorized: no
r5_implementation_authorized: no
p5_implementation_authorized: no
handoff_documentation_sha: pending_handoff_documentation_commit
```

## 1. Sealed candidate and public boundary

The final code candidate is commit `acb3efca06a02aadaa5ce6d1e2a815e85d36e6af`. The candidate
contains the R3 worker runtime, lease session, startup/topology gate, scheduler/heartbeat,
process-local lifecycle, settings, module bootstrap, process evidence and their S1a–S6 records.
The source/test identity was recomputed from every Python file under
`vnext/backend/src` and `vnext/backend/tests`; it is independent of ignored caches and of this
docs-only handoff descendant.

The stable R3 public surface is:

```text
gateway_backend.operations.worker:
  ClaimedExecutor, ClaimedWork, CheckpointGeneration, ExecutionControl,
  ExecutorAcknowledgment, LeaseSession, ReadUnitOfWorkFactory, RecoveryHook,
  StartupDisposition, WorkerEvent, WorkerEventCode, WorkerLifecycle,
  WorkerObserver, WorkerRegistry, WriteUnitOfWorkFactory
gateway_backend.operations.lease_session:
  LeaseSession
gateway_backend.operations.worker_startup:
  WorkerStartup
gateway_backend.operations.worker_runtime:
  WorkerRuntime
gateway_backend.operations.worker_lifecycle:
  WorkerLifecycleController
gateway_backend.settings:
  BackendSettings, OperationWorkerSettings
```

The authoritative process entrypoint is:

```text
python -m gateway_backend.bootstrap.operation_worker
```

`OperationWorkerSettings` has the independent prefix
`GATEWAY_BACKEND_OPERATION_WORKER_`. `CONTROL_DB_PATH` is required and absolute. R3 freezes a
30-second lease, 10-second heartbeat, 1-second idle poll, 1–10-second transient backoff, 60-second
startup budget, 180-second graceful-drain budget, one in-flight executor and claim limit one.

## 2. Runtime behavior matrix

| Boundary | S7 disposition |
| --- | --- |
| Startup | Empty local SQLite/WAL DB passes integrity and topology/registry gates, then emits `worker_ready`; unknown handler, corrupt data, higher schema or post-recovery topology drift fails closed before claim. |
| Claim | Registry preflight and atomic claim share one write UoW; an unknown first candidate leaves the durable candidate unchanged and does not create a lease. |
| Session | `LeaseSession` reloads transaction-fresh Operation/Step versions for heartbeat, checkpoint, successor and terminal publication; claim snapshots are never reused for publication. |
| Heartbeat | Same-status versioned mutation is supervised by the single runtime owner; busy retry is bounded by the remaining durable lease budget and definitive lease loss fences later publication. |
| Cancellation | Independent durable cancel intent is observed before the effect boundary and is monotonic; local control latches cannot be cleared by a stale builder. |
| Executor | Exactly one cooperative non-daemon executor is allowed; handler policy, payload interpretation, retry and external effects remain outside R3. |
| Drain | SIGTERM/SIGINT only set process-local drain intent. Idle drain exits cleanly; active drain waits for cooperative completion while heartbeat supervision continues. |
| Timeout | Drain timeout is worker-fatal and non-zero; R3 does not detach or kill the executor and does not emit a false clean-exit event. |
| Publication barrier | Checkpoint/terminal publication must be committed before safe handoff or clean quiescence. Process termination before/after the commit leaves an authoritative durable state without partial mutation. |
| Logging | Events contain bounded IDs/categories only. Failure paths redact lease token, filesystem path, payload and SQL text and return non-zero. |

## 3. Gate record

All commands ran against current HEAD `acb3efc` before this handoff documentation commit:

```text
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_contracts.py tests/test_operation_state.py tests/test_operation_store.py \
  tests/test_control_db_migrations.py tests/test_sqlite_operation_store.py \
  tests/test_operation_worker_contracts.py tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py tests/test_architecture.py
  -> 565 passed in 4.61s

uv run pytest -q -m unit
  -> 1393 passed, 34 deselected, 1 pre-existing Starlette deprecation warning in 75.03s

uv run pytest -q -m 'integration and not serial' \
  tests/test_sqlite_operation_store_integration.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 24 passed, 10 deselected in 0.53s

uv run pytest -q -m serial \
  tests/test_sqlite_operation_store_integration.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 10 passed, 24 deselected in 3.84s

cd vnext/backend && uv run ruff check . && uv run mypy
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
git merge-base --is-ancestor 31235dc820472a5ca2c99138fdf150090cfe122d HEAD
  -> pass
```

R3 does not run Dolt or Repository Service integration. Benchmark is not applicable because this
module gate makes no throughput or latency claim.

## 4. Current-HEAD image provenance and container smoke

The local Docker daemon initially lacked a running socket and its direct Docker Hub access timed
out. The final gate used the verified remote Docker daemon `tmpuser@10.10.60.4`; the build context
was the clean current HEAD above. The remote build command was:

```text
DOCKER_HOST=ssh://tmpuser@10.10.60.4 \
  docker build --network host \
  -f vnext/backend/Dockerfile -t p4-r3-acb3efc vnext
  -> successfully built f461fc3ec534
```

```yaml
build_host: 10.10.60.4
build_user: tmpuser
image_tag: p4-r3-acb3efc
image_id: sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf
image_digest: p4-r3-acb3efc@sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf
image_source_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
image_source_tree_sha256: 26994ad239969afb95556c03d9f03590837a98ac3148f3a9d70d835241370146
```

The worker smoke used a fresh exact remote host directory mounted at
`/var/lib/gateway/control`, ran the explicit module command, observed `worker_ready`, sent
SIGTERM, and observed `drain_started`, one `worker_exited` and exit code 0. Reopening the retained
database through the image returned:

```text
journal_mode=wal
schema_valid=1
tables=control_schema_migrations,operation_records,step_records
```

The smoke log redaction check found no configured DB path, container path, lease token, payload or
SQL text. The exact container and temporary directory were removed after verification; remote
container inventory and path checks were empty. The image remains on the remote build host under
the candidate tag for provenance, but no later source/test/build-input commit may be treated as
covered by it.

## 5. Limits and next boundary

R3 is a single-host, single-worker, local SQLite/WAL mechanism with an immutable empty registry.
It proves the worker lifecycle and fencing barriers; it does not execute production jobs, interpret
payloads, choose retry/manual/takeover outcomes, reconcile external effects, expose HTTP/global
readiness, provide Compose deployment coordination, or support HA/multi-host/external DB operation.

The S4 findings are closed by S5, S6 independently passed with no open finding, and S7 passed all
backend/five-package/image/container gates. The only next action is the P4-R4-S0 entry discussion.
That discussion may define the JobDefinition registry and handler contract; it does not authorize
R4 implementation, R5 recovery work, P5 deployment work or real Repository effects from this
handoff alone.
