# P5-5C-S2 Control DB Schema, Migration, Repository and Finalize Seed Handoff

状态：**S2 remediation + R1–R6 closure delivered — pending independent closure**

日期：2026-09-20

Owner：P5-5C Delivery

## Authority gate snapshot

```yaml
p5_5b_slice_exit: pass
p5_5c_design: accepted
p5_5c_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
repository_effect_authorized: false
production_deployment_authorized: false
```

## Traceability

```yaml
stage: P5-5C-S2-control-db-migration-repository-finalize-seed
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s1-handoff.md
implementation_candidate_head: 0f446c8b9070eea8cba5b5cf1d2e7cddcb0d1fca
remediation_implementation_head: fa45496d5b8cfdc4949ffe78b9e86896a04dd46e
workspace_schema_version: 4
uv_lock_in_diff: no
remediation_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s2-remediation-handoff.md
next_step: P5-5C-S3
```

## Input authority

- `docs/backend-vnext/refactoring/formal/plans/p5-5c-review-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-review-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-s0-entry-brief.md`

## Scope paths

- `vnext/backend/src/gateway_backend/infrastructure/control_db/**`
- `vnext/backend/src/gateway_backend/domain/submission/**`
- `vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py`
- `vnext/backend/src/gateway_backend/application/submit_jobs.py`
- `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py`
- `vnext/backend/tests/test_review_domain.py`
- `vnext/backend/tests/test_review_persistence.py`
- `vnext/backend/tests/test_submit_transactions.py`
- `vnext/backend/tests/test_submit_control_db_migrations.py`
- `vnext/backend/tests/test_workspace_control_db_migrations.py`

## Changed paths

See `implementation_candidate_head` commit stat.

## Invariants delivered

- `WORKSPACE_SCHEMA_VERSION` upgraded to **4** with review tables and v3→v4 backfill
- `SQLiteReviewRepository` with typed fail-closed read/write semantics
- `ControlDbUnitOfWork.review` participant
- T3 finalize inserts review seed in same transaction; replay validates closure
- No Review HTTP route; no `uv.lock` change

## Unique test owners

- `tests/test_review_domain.py` — `validate_review_closure` matrix
- `tests/test_review_persistence.py` — schema/migration/adapter probes
- `tests/test_submit_transactions.py` — T3 seed/replay closure only

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_submit_transactions.py tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py
# => 157 passed (post P2 closure)

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/infrastructure/control_db \
  src/gateway_backend/application/submission src/gateway_backend/application/submit_jobs.py \
  tests/test_review_domain.py tests/test_review_persistence.py tests/test_submit_transactions.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 382 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S2 is control DB migration/application/tests only; no route, Compose, entrypoint, or runtime ENV change
deferred: S5
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Forbidden imports

None.

## Independent countersign

```yaml
review: pending
next_step: P5-5C-S3
```
