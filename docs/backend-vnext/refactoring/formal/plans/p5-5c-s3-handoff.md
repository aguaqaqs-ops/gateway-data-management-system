# P5-5C-S3 Review Command Transaction and Workspace Release Handoff

状态：**S3 remediation delivered — pending independent countersign**

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
implementation_candidate_head: dadf5d1f6f01e028e2020b005737040ae4bee11e
remediation_implementation_head: 9e08f2f63e1da8cb8e5344de4810d5cbef5eb072
sealed_doc_tree_head: pending_bind_after_commit
remediation_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s3-remediation-handoff.md
uv_lock_in_diff: no
next_step: independent_S3_countersign_then_P5-5C-S4
```

`implementation_candidate_head` 保留首次 S3 代码交付提交 `dadf5d1f6f`；
`remediation_implementation_head` 绑定 F1–F8 remediation 代码提交 `9e08f2f63e`；
`sealed_doc_tree_head` 绑定本 follow-up docs 提交（修正无效 SHA 与 triple-SHA 键语义）。
Finding 闭环见 `p5-5c-s3-remediation-handoff.md`。

## Changed paths

- `vnext/backend/src/gateway_backend/application/submission/review.py`
- `vnext/backend/src/gateway_backend/application/submission/review_transaction.py`
- `vnext/backend/src/gateway_backend/application/submission/review_contracts.py`
- `vnext/backend/src/gateway_backend/application/submission/errors.py`
- `vnext/backend/src/gateway_backend/application/submission/ports.py`
- `vnext/backend/src/gateway_backend/application/submission/__init__.py`
- `vnext/backend/src/gateway_backend/domain/submission/review.py`
- `vnext/backend/src/gateway_backend/domain/submission/__init__.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py`
- `vnext/backend/tests/test_review_transactions.py`
- `vnext/backend/tests/test_review_domain.py`
- `vnext/backend/tests/test_sqlite_submit_repository.py`

## Invariants delivered

- `PERMISSION_REVIEW_SUBMISSION` + permission-before-object-read for apply/query
- project/device/repository scope closure without owner-actor equality
- `apply_review_transaction`: idempotency replay/conflict, optimistic CAS, transition policy, occupancy bindings
- `ApplyReviewResult.replay` distinguishes fresh commit vs same-key replay (S4 201/200 seam)
- damaged idempotency records fail closed as `ReviewIntegrityFailure` (not 500/conflict)
- approve retains exact occupancy; release clears pointers + deletes submission occupancy + bumps workspace version
- `get_review_facts` read query with closure validation
- `ReviewWorkspaceOccupancyConflict` with bounded messages including CLOSED workspace
- `delete_workspace_submission_occupancy` owner-qualified CAS (Submission adapter responsibility)
- no HTTP route, no Repository/Operation/artifact cleanup import

## Transaction matrix (unique owner: `tests/test_review_transactions.py`)

| Barrier | Covered |
| --- | --- |
| PENDING four actions + approved-return | yes |
| terminal transition denied | yes |
| stale `expected_review_version` writes nothing | yes |
| occupancy generation/upload/preview/occupancy/CLOSED mismatch | yes |
| same-key/same-fingerprint replay (cross-actor, workspace unchanged) | yes |
| same-key/different fingerprint conflict | yes |
| cross-submission same project/key conflict | yes |
| replay returns bound event after later mutation | yes |
| seed-bound/damaged idempotency → `ReviewIntegrityFailure` | yes |
| approved-return archive race (occupancy cleared) | yes |
| projection/event divergence → `ReviewIntegrityFailure` | yes |
| `cas_projection` fault injection rollback (pre-release) | yes |
| release occupancy-delete fault injection rollback | yes |
| second command after approve → `ReviewVersionConflict` (sequential) | yes |
| `get_review_facts` permission + ordered events | yes |
| approve/release workspace + submission immutability | yes |

## S4 entry note

`http/errors.map_domain_exception` 尚未为 Review 专用 stable code 提供显式分支；S4 须按设计 §9.3
映射后再注册 route（非 S3 缺陷，见 remediation handoff）。

## Unique test owners

- `tests/test_review_transactions.py` — application transaction matrix (S3 owner)
- `tests/test_review_domain.py` — domain transition/fingerprint/contracts
- `tests/test_review_persistence.py` — SQLite adapter
- `tests/test_submit_transactions.py` — T3 seed/replay only
- `tests/test_sqlite_submit_repository.py` — submission occupancy delete CAS

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_review_transactions.py tests/test_submit_transactions.py \
  tests/test_sqlite_submit_repository.py tests/test_architecture.py
# => 225 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/domain/submission src/gateway_backend/infrastructure/control_db \
  tests/test_review_transactions.py tests/test_review_domain.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 385 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S3 remediation is application transaction/tests/docs only
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
