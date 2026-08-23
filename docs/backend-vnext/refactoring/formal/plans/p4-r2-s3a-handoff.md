# P4/R2-S3a Handoff: Mapping, Migration and Integrity Hardening

状态：**PASS**

日期：2026-08-23

Owner：Durable operation runtime (`gateway_backend.operations` 与
`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S2b Handoff](p4-r2-s2b-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s3a
step_id: P4-R2-S3a
input_handoff_sha: 9497216eea38fa6f9e194df7b6316d4167d0c42f
input_validated_code_sha: cc0e6a418dabfce73f1c05383d1ca0c4be4a9e1a
validated_code_sha: 4de5c67928aca4d21cc3149e7a800e9b6d24db11
candidate_commit: 4de5c67928aca4d21cc3149e7a800e9b6d24db11
validated_code_tree_identity: vnext_backend_s3a_mapping_integrity_match_4de5c679
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/store.py
  - vnext/backend/src/gateway_backend/operations/__init__.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_operation_store.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
focused_tests: pass_321_unit
integration: pass_11
backend_unit: pass_1307_deselected_11
backend_unit_warning: one_pre_existing_starlette_deprecation_warning
five_package_static: pass
serial: not_applicable_no_fixed_time_or_process_boundary
container_gate: not_applicable_no_image_or_deployment_boundary
benchmark: not_applicable_no_performance_claim
schema_or_dependency_change: none
next_step: P4-R2-S3b
next_step_authorized: no
```

## 1. Delivered behavior

`OperationStore` now exposes the additive, SQLite-neutral
`scan_active_integrity(cursor=None, limit=DEFAULT_PAGE_LIMIT)` read port and the immutable
`IntegrityScanPage` result. The concrete adapter scans active Operations before active Steps using
bounded canonical keyset cursors. It validates `QUEUED`, `RUNNING`,
`MANUAL_RECOVERY_REQUIRED` Operations and `PENDING`, `RUNNING`, `RETRY_WAIT`,
`MANUAL_RECOVERY_REQUIRED` Steps; active Steps must retain a non-terminal owning Operation.

Readback now also converts invalid UTF-8 and missing-row-field mapping failures into the existing
`CorruptPersistedRecord` owner error. All rows continue to reconstruct closed R1 documents and pass
through the R1 parser. Integrity failures are reported without repair, deletion, quarantine,
audit state, or readiness ownership. Terminal history is excluded from the active scan while direct
readback remains strict.

Schema v1, migration version, DDL, SQLite profile, R1 parser/guards, error taxonomy, dependencies,
and deployment boundaries are unchanged. Existing migration tests plus file-backed reopen and
orphan tests prove commit/rollback/reopen and FK corruption behavior.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_store.py \
  tests/test_operation_contracts.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 321 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_sqlite_operation_store_integration.py
  -> 11 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1307 passed, 11 deselected, 1 pre-existing Starlette deprecation warning

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
serial collection for tests/test_sqlite_operation_store_integration.py
  -> no tests collected; 11 deselected; not applicable
```

No Docker/container or benchmark gate applies: this candidate changes only Python persistence
ports, SQLite mapping, and tests. No Dolt or Repository Service integration is required.

## 3. Boundary and deferred items

```yaml
deferred_items:
  - P4-R2-S3b WAL, contention and crash visibility evidence
  - R3 worker/bootstrap/settings/volume/readiness boundary
  - R4 successor and final outcome policy
  - R5 retry/backoff/effect-aware recovery and lease takeover
  - production outbox, Repository effects, HTTP, and deployment wiring
reopen_conditions:
  - changed R1 parser, transition guard, persisted semantic field, or public store taxonomy
  - need for historical/full-database scan semantics beyond bounded active scan
  - need for automatic repair, quarantine, durable evidence, or readiness route ownership
  - active-step/operation cross-table semantics no longer match the accepted R2 boundary
  - accepted SQLite lock, capacity, or local-volume boundary no longer holds
```

S3a is sealed at candidate commit `4de5c67928aca4d21cc3149e7a800e9b6d24db11`. This handoff points only to `P4-R2-S3b` and does not
authorize automatic continuation or the broader P4-R2 module gate.
