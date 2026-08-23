# P4/R2-S1b Handoff: Control DB Schema and Migration Skeleton

状态：**PASS**

日期：2026-08-23

Owner：Control DB infrastructure (`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S1a Handoff](p4-r2-s1a-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s1b
step_id: P4-R2-S1b
input_handoff_sha: b130e3424f9733d86668ff1f8305d4b395e41c24
input_validated_code_sha: eaa25e6b4d44eee05fdf2ffdce06308a08fe54d0
validated_code_sha: 3b837dba23ba47e36910fbffd5d49f0889f20da1
validated_code_tree_identity: vnext_backend_control_db_and_tests_match_3b837dba
result: pass
candidate_commit: 3b837dba23ba47e36910fbffd5d49f0889f20da1
changed_paths:
  - vnext/backend/src/gateway_backend/infrastructure/control_db/__init__.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_control_db_migrations.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_no_fixed_time_or_process_boundary
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary
benchmark: not_applicable_no_performance_claim
next_step: P4-R2-S2a
next_step_authorized: no
```

## 1. Delivered boundary

S1b adds the stdlib SQLite control DB boundary without application wiring. `connect_control_db` only
accepts an absolute `Path` whose parent already exists; it never reads environment state or creates
directories. Each configured connection uses WAL, foreign keys, `synchronous=FULL`, a 5000 ms busy
timeout, and explicit transaction ownership. `ControlDbUnitOfWork` opens an independent connection,
uses `BEGIN IMMEDIATE` for writes and deferred `BEGIN` for read-only scopes, then commits or rolls
back and closes the connection at scope exit.

The Operations schema component is `operations` at version `1`. `bootstrap_control_schema` creates the
component ledger and Operations tables/indexes inside one immediate transaction, advances absent/v0
state to v1, treats v1 as a no-op, rejects future versions with `UnsupportedSchemaVersion`, and rolls
back the complete DDL/ledger change on failure. Migration time is sampled once from the injected
aware UTC clock and stored as signed epoch microseconds. There is no downgrade, legacy import,
checksum, shadow migration, repair, or quarantine path.

The v1 layout contains only the R1 operation/step scalar fields and canonical JSON BLOB composites,
plus step `eligible_at_us`. It has the R1 identity/foreign-key/unique constraints and the bounded
active-step, claim, and operation-status indexes. The row mapper converts scalar timestamps to signed
UTC epoch microseconds, reconstructs closed R1 documents, and delegates semantic validation to the
existing R1 parsers. Readback shape, type, canonical-encoding, enum, boolean, range, and metadata
errors become `CorruptPersistedRecord`.

`gateway_backend.infrastructure.control_db` exports the connection/UoW and migration entry points;
`sqlite_operations` exposes only the operation/step row conversion functions. The concrete UoW is a
transaction shell for this step and does not claim complete `OperationStore` conformance or provide
create/read/CAS behavior; adapter wiring belongs to S2a. Operations remains free of infrastructure
imports, and control DB imports only Operations public contracts plus Shared Kernel canonicalization.

## 2. Schema and transaction profile

```text
component: operations
schema_version: 1
ledger: control_schema_migrations(component, version, applied_at_us)
tables: operation_records, step_records
foreign_key: step_records.operation_id -> operation_records.operation_id ON DELETE RESTRICT
unique: step_records(operation_id, step_name)
partial_unique: one active step per operation for PENDING/RUNNING/RETRY_WAIT/MANUAL_RECOVERY_REQUIRED
claim_index: (status, eligible_at_us, created_at_us, step_id) for PENDING/RETRY_WAIT
status_index: (status, updated_at_us, operation_id)
sqlite: WAL, foreign_keys=ON, synchronous=FULL, busy_timeout=5000
write_begin: BEGIN IMMEDIATE
read_begin: BEGIN
```

No business, outbox, Repository, worker, settings, Compose, deployment, or additional dependency
surface was added. No SQLite file, Dolt repository, or external process is used by the unit mapping
and migration tests.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 46 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_sqlite_operation_store_integration.py
  -> 4 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1276 passed, 4 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; ruff pass, mypy 202 source files
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

The integration coverage uses real temporary SQLite files for WAL/reopen, migration repeat,
transaction visibility, missing-parent rejection, and two independent bootstrap connections. It has
no fixed timeout, sleep, process termination, or serial-only timing claim, so the serial gate is not
applicable. Container/build and benchmark gates are not applicable because this step changes neither
an image/deployment boundary nor a production performance path.

## 4. Deferred work and reopen conditions

Deferred to S2a: complete SQLite `OperationStore` adapter conformance, exact create/idempotency,
ID/read/list behavior, keyset cursor execution, SQLite-to-owner error classification, and guarded
operation/step CAS. Claim/lease/action composition remains S2b-owned; integrity hardening and
contention/crash evidence remain S3a/S3b-owned.

Reopen before S2a if the next step requires a new schema authority, a changed R1 parser/guard or
disposition, a generic repository/database error, settings/deployment wiring, business/Repository
tables, a repair/quarantine/evidence state, or a dependency beyond stdlib SQLite and existing
contracts.
