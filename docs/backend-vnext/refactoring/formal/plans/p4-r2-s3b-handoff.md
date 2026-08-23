# P4/R2-S3b Handoff: WAL, Contention and Crash Visibility Hardening

状态：**PASS**

日期：2026-08-23

Owner：Durable operation runtime (`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S3a Handoff](p4-r2-s3a-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s3b
step_id: P4-R2-S3b
input_handoff_sha: 04e9d36e8ad87f70462704145cbaca046b5b431e
input_validated_code_sha: 4de5c67928aca4d21cc3149e7a800e9b6d24db11
validated_code_sha: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
candidate_commit: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
validated_code_tree_identity: vnext_backend_s3b_wal_contention_crash_match_f77dd43
result: pass
changed_paths:
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
focused_tests: pass_105_unit
integration: pass_15
backend_unit: pass_1307_deselected_15
backend_unit_warning: one_pre_existing_starlette_deprecation_warning
five_package_static: pass
serial: pass_2_collected_2; 13_deselected
container_gate: not_applicable_no_image_or_deployment_boundary
benchmark: not_applicable_no_performance_claim
schema_or_dependency_change: none
next_step: P4-R2-S4
next_step_authorized: no
```

## 1. Delivered evidence

The file-backed integration suite now proves the accepted SQLite transaction boundary without
changing production behavior. An independent reader cannot observe an operation or its initial
step before the writer commits; after commit both records are readable, while an exception rolls
back the complete operation/step pair. Close/reopen preserves the WAL profile, schema, indexes,
records, and subsequent writeability.

The stale-CAS case uses one physical connection A to read version 0, connection B to commit
version 1, and connection A to submit an old precondition. The write returns the existing
`StaleWrite` outcome and the persisted row remains B's `RUNNING` result. Migration contention
uses two independent connections bootstrapping the same file at a barrier; both finish normally,
the ledger contains one `operations/v1` row, and reopen confirms the schema/index/WAL profile.

The writer-contention case holds `BEGIN IMMEDIATE` on one connection and locally patches
`BUSY_TIMEOUT_MS` to zero only in the test. The competing writer returns the existing
`StoreBusy` outcome; the production profile remains 5 seconds and is asserted on reopen.

The representative process case creates a committed synthetic probe table, has a child begin an
immediate transaction and insert an uncommitted probe before emitting `READY`, and verifies the
probe is invisible to the parent. After `SIGKILL`, the child terminates by signal, the probe is
absent after reopen, and the parent can commit a new probe. The failure-position barrier is
stdout/pipe only; no RunEvidence, repair state, quarantine, audit record, schema, or new timeout
API was introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_store.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 105 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_sqlite_operation_store_integration.py
  -> 15 passed

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_sqlite_operation_store_integration.py
  -> 2 passed, 13 deselected
  -> contention and process-termination cases were both collected

cd vnext/backend && uv run pytest -q -m unit
  -> 1307 passed, 15 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 203 source files
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

The validated code candidate changes only the file-backed integration test. No production source,
schema v1 DDL, `OperationStore` API, SQLite profile, error taxonomy, dependency, deployment,
container, or benchmark boundary changed. Container and benchmark gates are therefore not
applicable for S3b.

## 3. Deferred items and reopen conditions

```yaml
deferred_items:
  - P4-R2-S4 focused review and next authorized implementation step
  - R3 worker/bootstrap/settings/volume/readiness boundary
  - R4 successor and final outcome policy
  - R5 retry/backoff/effect-aware recovery and lease takeover
  - production outbox, Repository effects, HTTP, and deployment wiring
reopen_conditions:
  - need to change schema v1, OperationStore API, SQLite profile, or existing error taxonomy
  - need for formal throughput, multi-host, NFS, HA, or exhaustive SQLite interleaving claims
  - local reliable WAL-volume, single-trust-domain, or 5-second production busy-timeout assumptions no longer hold
  - need for durable crash evidence, repair, quarantine, audit state, or a public timeout API
  - production busy/rollback behavior cannot be repaired within existing database.py connection/UoW semantics
```

S3b is sealed at code candidate `f77dd43d8f0e2e10b5c40048093161c3a70f4ffe`. This handoff points
only to `P4-R2-S4`; it does not authorize automatic continuation or the broader P4-R2 module gate.
