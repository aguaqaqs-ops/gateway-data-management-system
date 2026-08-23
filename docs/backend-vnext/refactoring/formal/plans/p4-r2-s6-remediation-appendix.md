# P4-R2-S6 finding disposition and remediation appendix

This appendix is scoped to the two P2 findings in
`p4-r2-s6-independent-review.md`. It does not reopen the R2 public port, schema v1, R1
record/transition contract, error taxonomy, deployment boundary, or the deferred S7/R3 work.

## F1 — claim-local validation can commit a cross-table prefix

- Owner: `gateway_backend.operations.persistence.OperationLifecycleActions.claim_one` and its
  existing transaction-scoped store composition.
- Allowed paths:
  - `vnext/backend/src/gateway_backend/operations/persistence.py`
  - `vnext/backend/tests/test_sqlite_operation_store.py`
  - `vnext/backend/tests/test_sqlite_operation_store_integration.py`
- Disposition: validate `worker_id` and `lease_token` with the existing R1 opaque-ID rule, then
  construct the complete RUNNING Step candidate before the first Operation CAS. A local identity
  or I-JSON version failure therefore occurs before either row is mutated. Existing store
  mutation poisoning and UoW rollback remain the barrier for failures after a store mutation.
- Regression coverage: shared parameterized action cases cover an R1 control-character identity
  and a maximum I-JSON Step version; file-backed cases catch both failures and verify the original
  QUEUED/PENDING rows and versions after reopen.
- Closure criteria: no caught `claim_one()` local validation failure can persist
  `RUNNING Operation + PENDING Step`; valid claims still persist both rows together; the existing
  typed store failures and rollback-only semantics remain unchanged.
- Reopen trigger: any need for a new transaction-aborted public outcome, savepoint/mutation API,
  durable rollback state, schema field, or a change to the R1 identity/version contract.

## F2 — unknown Step status is filtered from active integrity scan

- Owner: `SQLiteOperationStore` bounded active integrity scan.
- Allowed paths:
  - `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py`
  - `vnext/backend/tests/test_sqlite_operation_store.py`
  - `vnext/backend/tests/test_sqlite_operation_store_integration.py`
- Disposition: both scan phases now exclude only recognized terminal history. Unknown, null, and
  wrong-type status scalars remain in the bounded keyset result and are passed to the existing
  strict R1 row reconstruction, which raises `CorruptPersistedRecord`. Recognized terminal
  Operation/Step history remains excluded exactly as before.
- Regression coverage: a shared Operation/Step parameter table covers in-memory scan behavior;
  file-backed corruption cases cover reopen, direct readback failure, and scan failure without
  repair or row modification. Existing bounded keyset and terminal-history tests remain owners
  for pagination and exclusion semantics.
- Closure criteria: an unclassifiable status cannot make an active scan complete successfully;
  known terminal history remains outside the active scan; scan limits, opaque cursors, owner
  validation, and direct strict readback remain unchanged.
- Reopen trigger: any requirement for repair, quarantine, audit/evidence persistence, a full
  historical scan, schema/version change, or a changed accepted terminal-history contract.

## Verification boundary

No new public API, schema, persisted field, error type, repair state, deployment setting, or
container/benchmark claim was introduced. The independent review document supplied by S6 remains
unmodified and is intentionally not part of the remediation source/test commit.
