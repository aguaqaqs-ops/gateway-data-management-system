# P4/R2-S5 Handoff: Finding-Scoped Remediation

状态：**PASS**

日期：2026-08-24

Owner：Durable operation runtime (`gateway_backend.operations` 与
`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S4 Focused Owner Review](p4-r2-s4-focused-review.md)、
[P4/R2-S5 Remediation Appendix](p4-r2-s5-remediation-appendix.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
handoff_kind: p4_r2_s5
step_id: P4-R2-S5
input_review_sha: 4cc76f9aff8489f6b593dac7012ceddf5ae0fd37
input_reviewed_candidate_sha: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
validated_code_sha: 8e5fcce890d5bcb920c7c469a6546fbd15903df8
candidate_commit: 8e5fcce890d5bcb920c7c469a6546fbd15903df8
validated_code_tree_identity: vnext_backend_s5_finding_remediation_match_8e5fcce
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/store.py
  - vnext/backend/src/gateway_backend/operations/persistence.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-s2b-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-s5-remediation-appendix.md
focused_tests: pass_326_unit
integration: pass_18
serial: pass_2_collected_2; 16_deselected
migration_bootstrap_repetition: pass_20_of_20
backend_unit: pass_1312_deselected_18
backend_unit_warning: one_pre_existing_starlette_deprecation_warning
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary_change
benchmark: not_applicable_no_performance_claim
schema_or_dependency_change: none
public_boundary_reopen: read_only_OperationStore_transaction_now_property_only
next_step: P4-R2-S6
next_step_authorized: no
```

## 1. Finding disposition

| Finding | Disposition | Evidence and closure |
| --- | --- | --- |
| F1 | **closed** | Failed mutating SQLite store calls mark the participant rollback-only; the UoW rolls back even when the caller catches the typed error. File-backed cancel and successor second-leg regressions prove no prefix survives reopen. |
| F2 | **closed** | Successor insertion rejects final-terminal owners, and final Operation publication rejects active Steps after transition/precondition classification. Direct insertion, both terminal branch orders, duplicate retry and active scan cases pass. |
| F3 | **closed with explicit boundary reopen** | `OperationStore.transaction_now` exposes the adapter's single sampled clock; action construction and claim scans reject mismatches. Due/lease boundary and mismatched-clock cases pass. No second clock or persisted time was added. |
| F4 | **closed** | WAL profile setup retries only busy/locked `PRAGMA journal_mode=WAL` within the existing `BUSY_TIMEOUT_MS`; fresh-file bootstrap passes the barrier test and 20/20 bounded repetitions. |
| F5 | **closed** | S2b now points to P4-R2-S3a in YAML and prose. The existing `test_operation_contracts.py` export assertion is explicitly recorded as the single shared public-export test owner. |

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_store.py \
  tests/test_operation_contracts.py \
  tests/test_control_db_migrations.py \
  tests/test_sqlite_operation_store.py \
  tests/test_architecture.py
  -> 326 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_sqlite_operation_store_integration.py
  -> 18 passed

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_sqlite_operation_store_integration.py
  -> 2 passed, 16 deselected
  -> both contention and process-termination cases were collected

concurrent fresh-file bootstrap nodeid, bounded repetition
  -> 20 passed of 20

cd vnext/backend && uv run pytest -q -m unit
  -> 1312 passed, 18 deselected, 1 pre-existing Starlette deprecation warning

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

No schema, dependency, deployment, container or benchmark boundary changed. The only public
surface adjustment is the read-only transaction-clock property explicitly authorized in the S5
remediation appendix. S6 is required to independently review this seam and the durable cross-table
invariants.

## 3. Deferred items and reopen conditions

```yaml
deferred_items:
  - P4-R2-S6 independent review
  - P4-R2-S7 module gate and final R2 handoff
  - R3 worker/bootstrap/settings/volume/readiness boundary
  - R4 successor selection and final outcome policy
  - R5 retry/backoff/effect-aware recovery and lease takeover
  - production outbox, Repository effects, HTTP, and deployment wiring
reopen_conditions:
  - need for a mutation API, savepoint API, persisted rollback/evidence state, or schema change
  - a neutral store/UoW implementation cannot enforce rollback-only composition without another public boundary change
  - need for JobDefinition interpretation, multiple active Steps, direct lease replacement, or new status semantics
  - need for public timeout policy, unbounded startup retry, multi-host/NFS/HA or formal throughput claims
  - need to change R1 parser/guards, existing error taxonomy, dependency or deployment boundaries
```

S5 is sealed at code candidate `8e5fcce890d5bcb920c7c469a6546fbd15903df8`. The only next step is
`P4-R2-S6`, and this handoff does not authorize automatic continuation.
