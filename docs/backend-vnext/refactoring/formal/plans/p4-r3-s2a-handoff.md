# P4/R3-S2a Handoff: Startup, Topology and Atomic Claim

状态：**PASS — S2a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-24

Owner：Operation Worker Runtime

```yaml
handoff_kind: p4_r3_s2a
step_id: P4-R3-S2a
input_handoff_sha: 2db23e601cb091684bd5ee60b672ee543fc61b11f452d6b3c93e3ac2f24d0699
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:7ec7b3212f575225b62392657f3464fa27a03126a713b4cce873d214b9b31c63
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/worker.py
  - vnext/backend/src/gateway_backend/operations/worker_startup.py
  - vnext/backend/tests/test_operation_worker_contracts.py
  - vnext/backend/tests/test_operation_worker_startup.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s2a-handoff.md
focused_tests: pass_65
backend_unit: pass_1370_deselected_24
integration: not_applicable_s2a_fake_uow_no_sqlite_or_durable_file
serial: not_applicable_s2a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: operations-only startup and claim ports; no image, entrypoint, settings, deployment, or runtime boundary changed
last_verified_image_revision: none_for_s2a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2b scheduler, executor thread, heartbeat retry, and cancellation orchestration
  - S3a drain and process-local lifecycle
  - S3b settings, bootstrap, module CLI, and file/process evidence
  - R4 JobDefinition registry, payload, checkpoint closure, successor and final policy
  - R5 retry, takeover, expired lease disposition, and effect reconciliation
reopen_conditions:
  - need for SQLite, settings, bootstrap, scheduler, signal, process, or business-context imports
  - need to change the R1 record/state contract or R2 schema/store/error taxonomy
  - inability to keep registry preflight and claim_one in one write UoW
  - need for multiple active executors, mutable registry, durable worker evidence, or multi-worker coordination
next_step: P4-R3-S2b
next_step_authorized: no
```

## 1. Delivered boundary

S2a adds the frozen/slotted `ClaimedWork` value to
`gateway_backend.operations.worker` and a `WorkerStartup` implementation under
`gateway_backend.operations.worker_startup`.

Startup performs complete R2 active-integrity cursor scans, enumerates all non-final Operation
statuses through bounded keyset pages, validates exactly one active Step and matching ownership,
checks immutable registry coverage for runnable statuses, skips automatic registry/recovery handling
for `MANUAL_RECOVERY_REQUIRED` while emitting a bounded warning, and invokes the recovery hook only
outside read UoW scopes. A READY recovery result is followed by a second complete integrity and
topology/registry gate before claims are enabled.

Atomic claim opens one injected write UoW, performs candidate lookup with `limit=1`, resolves the
candidate key in memory, creates a fresh typed lease token, invokes the existing R2
`OperationLifecycleActions.claim_one`, asserts exact candidate/operation/step/key/worker/token
identity, and allows the UoW to commit only after all assertions pass. Missing registry entries and
identity mismatches therefore roll back without leaving a RUNNING prefix.

Worker IDs are stable for one `WorkerStartup` instance. Default identities use `worker-<UUID4>` and
`lease-<UUID4>` prefixes; factories remain injectable for deterministic tests. The Operations root
export surface is unchanged, and no SQLite, settings, bootstrap, thread, signal, or container code
was added.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_worker_startup.py \
  tests/test_architecture.py
  -> 65 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1370 passed, 24 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 209 source files

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

Integration, serial, Dolt, container, and benchmark gates were not applicable to this fake-UoW,
operations-only step. The source/test tree identity was computed from all Python files under
`vnext/backend/src` and `vnext/backend/tests` using sorted per-file SHA-256 records.

## 3. Handoff boundary

The implementation and S1a/S1b candidate changes remain uncommitted because no explicit commit
authorization was provided. `validated_code_sha` must be replaced with the candidate code commit
SHA only after that authorization. This handoff authorizes no S2b, S3, R4, R5, or P5 implementation.
