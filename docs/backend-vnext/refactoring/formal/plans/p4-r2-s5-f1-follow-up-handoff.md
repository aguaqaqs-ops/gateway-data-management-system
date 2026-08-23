# P4-R2-S5 F1 follow-up handoff

```yaml
step_id: P4-R2-S5-F1-follow-up
input_review_sha: ddc54ad7dc6417d07b690c5b1ef87a9c9e2d7489
validated_source_sha: 15fc3e80031cb503292c880afc9b77b245b3a23c
finding_scope: F1
result: PASS
next_step: P4-R2-S6
next_step_authorized: no
container_gate: not_applicable
benchmark_gate: not_applicable
```

## Disposition

The remaining F1 finding was that a caught mutation failure poisoned the unit of work for durability but still allowed a later valid mutation to return `APPLY` or `IDEMPOTENT` before the unit of work silently rolled back it. The SQLite adapter now checks its existing rollback-only state before entering every mutating store operation. Once a mutation raises, all later store mutations fail with the existing concrete `RuntimeError` before any candidate is evaluated or applied. The original typed failure, including `StaleWrite`, is preserved, and `ControlDbUnitOfWork` still rolls back the complete transaction on clean exit when the participant is poisoned.

No new public transaction outcome, mutation API, savepoint API, schema field, error taxonomy entry, or persistence state was added.

## Changed paths

- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_operations.py`
  - added the pre-mutation rollback-only guard to the existing mutation wrapper;
  - the existing `BaseException` poisoning path remains the single failure barrier.
- `vnext/backend/tests/test_sqlite_operation_store.py`
  - added stale operation and live-step follow-up mutation regressions;
  - isolated tests that intentionally catch a mutation error from later valid-mutation tests, matching the poisoned-transaction contract.
- `vnext/backend/tests/test_sqlite_operation_store_integration.py`
  - added file-backed caught-failure cases for a later valid create and valid CAS;
  - verified the original records remain rolled back and later records are absent after reopen.

## Validation

- Focused unit: `329 passed`.
- Backend unit: `1315 passed, 20 deselected`.
- Backend integration: `20 passed`.
- Backend serial: `2 passed, 18 deselected`; the two serial cases were collected and executed.
- `vnext/backend`: `ruff check .` and `mypy` passed.
- `vnext/shared_kernel`: `ruff check .` and `mypy` passed.
- `vnext/repository_contracts`: `ruff check .` and `mypy` passed.
- `vnext/repository_client`: `ruff check .` and `mypy` passed.
- `vnext/repository_service`: `ruff check .` and `mypy` passed.
- `git diff --check` passed before the source candidate was committed.

The backend unit run emitted only the pre-existing Starlette/httpx deprecation warning. Container and benchmark gates were not applicable because this follow-up changes only SQLite adapter behavior and tests; it does not change image, deployment, dependency, volume, or runtime boundaries.

## F1 closure and reopen conditions

F1 is closed for S5 candidate review when a caught mutation failure followed by a valid create or CAS cannot return `APPLY` or `IDEMPOTENT`, the original typed failure is observable, the whole unit of work is absent after reopen, and the database remains usable. Reopen if any public R2 mutation bypasses the precondition guard, if a later mutation applies or reports idempotence after poisoning, if the typed failure is replaced, or if rollback-only state leaks across units of work.

The follow-up does not claim a new public transaction-aborted result. Introducing one, or extending the contract to arbitrary direct connection writes after poisoning, requires an explicit public-boundary review. S6 remains the next independently authorized review step; S7 is not started.
