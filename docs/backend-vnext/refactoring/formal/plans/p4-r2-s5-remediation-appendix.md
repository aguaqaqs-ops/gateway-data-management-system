# P4/R2-S5 Remediation Appendix

状态：**IN PROGRESS**

日期：2026-08-24

Owner：Durable operation runtime (`gateway_backend.operations` 与
`gateway_backend.infrastructure.control_db`)

上游：[P4/R2-S4 Focused Owner Review](p4-r2-s4-focused-review.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)

```yaml
step_id: P4-R2-S5
input_review_sha: 4cc76f9aff8489f6b593dac7012ceddf5ae0fd37
input_reviewed_candidate_sha: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
validated_code_sha: pending
result: in_progress
scope_decision: finding_scoped_remediation_with_explicit_clock_port_reopen
allowed_paths:
  - vnext/backend/src/gateway_backend/operations/store.py
  - vnext/backend/src/gateway_backend/operations/persistence.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py
  - vnext/backend/tests/test_operation_store.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_control_db_migrations.py
  - vnext/backend/tests/test_sqlite_operation_store.py
  - vnext/backend/tests/test_sqlite_operation_store_integration.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-*.md
forbidden_paths:
  - schema DDL, schema version, persisted fields, repair/audit/evidence state
  - Repository Service, business modules, worker, settings, HTTP, Compose, Dockerfile, entrypoint
  - dependency locks and deployment configuration
focused_test_owner_exception:
  path: vnext/backend/tests/test_operation_contracts.py
  reason: single existing owner for the shared Operations public-export surface
  rule: retain the one-line assertion; do not duplicate it in an R2 test module
next_step: P4-R2-S6
next_step_authorized: no
```

## Finding remediation matrix

| Finding | Owner | Allowed implementation | Regression proof | Closure condition | Reopen trigger |
| --- | --- | --- | --- | --- | --- |
| P4-R2-S4-F1: caught second-leg failures commit prefixes | `SQLiteOperationStore` and `ControlDbUnitOfWork` | Mark the concrete transaction rollback-only after any failed mutating store call; UoW commits only a clean, non-marked participant. No savepoint or new public mutation API. | File-backed UoW catches a cancel second-leg failure and a terminal/successor second-leg failure; reopen proves neither prefix persists. | Every representative caught mutation failure rolls back the complete current UoW. | A future neutral store/UoW composition cannot enforce the same rollback-only rule without a public boundary change. |
| P4-R2-S4-F2: terminal Operation plus active Step branch drift | `SQLiteOperationStore` cross-table mutation guards | Reject successor insertion under a final Operation and reject final Operation publication while any active Step exists, using `ConflictingDuplicate` and the existing transaction. | Both branch orders, direct successor insertion, terminal duplicate retry, persisted non-mutation and active-integrity scan. | No public R2 mutation can create a terminal Operation with an active Step. | Requirement for schema changes, new persisted state, JobDefinition policy or a new query/mutation surface. |
| P4-R2-S4-F3: action time is detached from UoW clock | `OperationStore` clock seam and `OperationLifecycleActions` | Add the minimal read-only `transaction_now` property; require the action argument and claim scan `now` to equal the captured adapter clock. No second clock or persisted time. | Mismatched-clock rejection plus due/lease boundary cases. | Claim eligibility, lease expiry and action timestamps use one exact transaction sample. | Need for monotonic time, multiple transaction clocks or a new persisted clock axis. |
| P4-R2-S4-F4: fresh-file bootstrap WAL race | `database.py` connection configuration | Bounded retry only around busy/locked `PRAGMA journal_mode=WAL`, using existing `BUSY_TIMEOUT_MS`; zero timeout remains immediate `StoreBusy`. | Barrier bootstrap plus bounded 20-run repetition; one v1 ledger and stable WAL/profile after reopen. | Concurrent fresh-file startup completes without transient `StoreBusy`. | Need for public timeout policy, unbounded retry, migration evidence or a changed SQLite profile. |
| P4-R2-S4-F5: path and next-step provenance inconsistency | P4/R2 formal plan records | Correct S2b next-step typo and explicitly record the shared export-test ownership exception. | Diff/path lineage and docs consistency checks. | Handoffs identify P4-R2 lineage and all changed paths have an explicit owner. | Any change outside formal plan/docs or a need to duplicate the shared export owner. |

## Shared closure and handoff rules

S5 may close only after all focused/integration/serial gates applicable to the changed behavior,
the backend unit gate, five-package static gates and `git diff --check` pass. The validated code SHA
must be an ancestor of the docs-only S5 handoff, and the handoff must list the exact candidate tree,
finding dispositions and reopen conditions.

The read-only `OperationStore.transaction_now` property is the only intentional public boundary
reopen. It carries the already-sampled transaction clock; it does not add a mutation operation,
change a persisted key, or transfer transaction ownership from the concrete UoW.

S6 remains required as an independent review of cross-table atomicity, CAS, clock binding and
migration startup. S5 does not authorize S6 execution, S7, container gates or benchmark claims.
