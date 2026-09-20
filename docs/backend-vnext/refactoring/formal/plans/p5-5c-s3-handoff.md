# P5-5C-S3 Review Command Transaction and Workspace Release Handoff

状态：**S3 delivered — pending independent closure**

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
stage: P5-5C-S3-review-command-transaction-workspace-release
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s2-handoff.md
implementation_candidate_head: 410d274ff4287428f186ca6edf400574a3996360
uv_lock_in_diff: no
next_step: P5-5C-S4
```

## Changed paths

- `vnext/backend/src/gateway_backend/application/submission/review.py` (new)
- `vnext/backend/src/gateway_backend/application/submission/review_transaction.py` (new)
- `vnext/backend/src/gateway_backend/application/submission/errors.py`
- `vnext/backend/src/gateway_backend/application/submission/ports.py`
- `vnext/backend/src/gateway_backend/application/submission/__init__.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py`
- `vnext/backend/tests/test_review_transactions.py` (new)
- `vnext/backend/tests/test_sqlite_submit_repository.py`

## Invariants delivered

- `PERMISSION_REVIEW_SUBMISSION` + permission-before-object-read for apply/query
- project/device/repository scope closure without owner-actor equality (reviewer may differ from submitter)
- `apply_review_transaction`: idempotency replay/conflict, optimistic CAS, transition policy, occupancy bindings
- approve retains exact occupancy; reject/return/withdraw atomically clear pointers + delete submission occupancy + bump workspace version
- `get_review_facts` read query with closure validation
- `ReviewWorkspaceOccupancyConflict` (`WORKSPACE_OCCUPANCY_CONFLICT`) for binding failures
- `delete_workspace_submission_occupancy` owner-qualified CAS on workspace occupancy
- no HTTP route, no Repository/Operation/artifact cleanup import

## Transaction matrix (unique owner: `tests/test_review_transactions.py`)

| Barrier | Covered |
| --- | --- |
| PENDING four actions + approved-return | yes |
| terminal transition denied | yes |
| stale `expected_review_version` writes nothing | yes |
| occupancy generation/upload/preview/occupancy mismatch | yes |
| same-key/same-fingerprint replay (cross-actor) | yes |
| same-key/different fingerprint conflict | yes |
| cross-submission same project/key conflict | yes |
| replay returns bound event after later mutation | yes |
| approved-return archive race (occupancy cleared) | yes |
| projection/event divergence → `ReviewIntegrityFailure` | yes |
| CAS fault injection full rollback | yes |
| concurrent second command stable conflict | yes |
| `get_review_facts` permission + ordered events | yes |
| approve/release workspace + submission immutability | yes |

## Fault cases

- injected `cas_projection` failure rolls back event/idempotency/workspace
- manual occupancy delete before approved-return blocks release without review writes
- corrupted projection/event closure fails closed on apply

## Unique test owners

- `tests/test_review_transactions.py` — application transaction matrix (S3 owner)
- `tests/test_review_domain.py` — domain transition/fingerprint (unchanged)
- `tests/test_review_persistence.py` — SQLite adapter (unchanged)
- `tests/test_submit_transactions.py` — T3 seed/replay only (unchanged)

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_review_transactions.py tests/test_submit_transactions.py
# => 165 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/domain/submission src/gateway_backend/infrastructure/control_db \
  tests/test_review_transactions.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 385 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S3 is application transaction/tests only; no route, Compose, entrypoint, or runtime ENV change
deferred: S5
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Forbidden imports

None.

## Independent countersign

```yaml
review: pending
next_step: P5-5C-S4
```
