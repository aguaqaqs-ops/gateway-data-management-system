# P5-5C-S2 Finding-Scoped Remediation Handoff

状态：**S2 remediation delivered — pending independent closure**

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
stage: P5-5C-S2-remediation
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s2-handoff.md
implementation_candidate_head: 0f446c8b9070eea8cba5b5cf1d2e7cddcb0d1fca
sealed_doc_tree_head: b7846d9ed9c9a81e8a58e603d655c87b10390d5b
workspace_schema_version: 4
uv_lock_in_diff: no
finding_remediation: F1-F12
next_step: P5-5C-S3
```

## Input authority

- `docs/backend-vnext/refactoring/formal/plans/p5-5c-review-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-review-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-s2-handoff.md`
- Independent S2 review findings F1–F12

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

## Finding remediation summary

| Finding | Resolution |
| --- | --- |
| F1 | Implementation commit rebinding; handoff SHA corrected |
| F2 | `cas_projection` missing row → `ReviewClosureViolation` |
| F3 | Read mapping errors wrapped as `ReviewClosureViolation` |
| F4 | `find_idempotency` JOIN + reject seed-bound records |
| F5 | `append_event` enforces contiguous sequence |
| F6 | Seed inlined in `finalize_transaction.py`; `ReviewIntegrityFailure` at boundary |
| F7 | Replay closure uses single `get_projection` path |
| F8 | Domain closure matrix, byte-bound, backfill/idempotency/occupancy/drift tests |
| F9 | Generic workspace migration integrity messages |
| F10 | Deleted `review_seed.py`; `submit_jobs` factory typed as `WorkspaceControlTransaction` |
| F11 | This structured handoff |
| F12 | Backfill uses `INSERT … SELECT` |

## Unique test owners

- `tests/test_review_domain.py` — `validate_review_closure` violation matrix
- `tests/test_review_persistence.py` — schema/migration/adapter fail-closed probes
- `tests/test_submit_transactions.py` — T3 seed/replay closure only

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_submit_transactions.py tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py
# => 148 passed

../scripts/uv-consume.sh -C . run ruff check \
  src/gateway_backend/infrastructure/control_db \
  src/gateway_backend/application/submission \
  src/gateway_backend/application/submit_jobs.py \
  tests/test_review_domain.py tests/test_review_persistence.py tests/test_submit_transactions.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 382 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: remediation is control DB adapter/application/tests only; no route, Compose, entrypoint, or runtime ENV change
deferred: S5
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Forbidden imports

None introduced.

## Independent countersign

```yaml
review: pending
next_step: independent_s2_remediation_closure
```
