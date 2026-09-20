# P5-5C-S4 HTTP Contract, Production Wiring and Deployed Permission Handoff

状态：**S4 delivered — pending independent countersign**

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
stage: P5-5C-S4-http-contract-production-wiring-deployed-permission
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s3-handoff.md
s3_countersign_head: ea6b38e4f22fcd282622ee09e6cb102aca39d8aa
implementation_candidate_head: pending_commit
uv_lock_in_diff: no
next_step: independent_S4_countersign_then_P5-5C-S5
```

## Changed paths

- `vnext/backend/src/gateway_backend/application/submission/ports.py`
- `vnext/backend/src/gateway_backend/application/submission/review.py`
- `vnext/backend/src/gateway_backend/application/submission/review_transaction.py`
- `vnext/backend/src/gateway_backend/http/dependencies.py`
- `vnext/backend/src/gateway_backend/http/errors.py`
- `vnext/backend/src/gateway_backend/http/orchestration/review.py` (new)
- `vnext/backend/src/gateway_backend/http/routes/reviews.py` (new)
- `vnext/backend/src/gateway_backend/http/schemas/review.py` (new)
- `vnext/backend/src/gateway_backend/http/wiring.py`
- `vnext/deploy/config/session.json`
- `vnext/backend/tests/support/http_workspace_harness.py`
- `vnext/backend/tests/support/runtime_settings.py`
- `vnext/backend/tests/test_review_http.py` (new)
- `vnext/backend/tests/test_review_transactions.py` (S3 test param cleanup)
- `vnext/backend/tests/test_http_openapi.py`
- `vnext/backend/tests/test_production_wiring.py`

## OpenAPI paths

```text
POST /v1/submissions/{submission_id}/review-events
GET  /v1/submissions/{submission_id}/review
```

Registered in `PRODUCTION_OPENAPI_PATHS` and `register_workspace_http`.

## Permission / config diff

`review_submission` added to:

- `vnext/deploy/config/session.json`
- `tests/support/runtime_settings.py` `default_session_document()`

Production runtime continues to use existing `WorkspaceHttpDependencies`; `unit_of_work_factory`
static type updated to `WorkspaceControlUnitOfWorkFactory` (no new dependency field).

## Invariants delivered

- closed HTTP DTOs (`ApplyReviewRequest`, `ReviewAppliedResponse`, `ReviewFactsResponse`)
- POST 201 fresh / 200 replay via `ApplyReviewResult.replay`
- stable error mapping per design §9.3 in `http/errors.py`
- `ReviewApplyTransaction` minimal port convergence (P3)
- permission-before-object-read via application layer; HTTP tests own 403/404 taxonomy
- no start-review / mutation-delete / Archive / History routes
- no Repository/Operation/worker import

## HTTP test matrix (unique owner: `tests/test_review_http.py`)

| Barrier | Covered |
| --- | --- |
| POST 201 approve + GET facts/redaction | yes |
| POST 200 same-key replay | yes |
| cross-actor same project/key replay | yes |
| 422 Idempotency-Key / closed schema / reason | yes |
| 403 missing `review_submission` (POST/GET) | yes |
| 403 permission-before-object-read hides absent submission | yes |
| 404 absent/cross-scope submission | yes |
| 409 idempotency/version/transition/occupancy | yes |
| 429 admission gate | yes |
| 503 scope provider failure | yes |
| 503 integrity failure on GET | yes |

## S3 cleanup included

`CROSS_SUBMISSION_IDEMPOTENCY_CONFLICT_CASES` first case now uses `device-2` + `repo-1`
(different device, same repository).

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# => 86 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/http \
  src/gateway_backend/bootstrap tests/test_review_http.py \
  tests/test_http_openapi.py tests/test_production_wiring.py tests/test_architecture.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 389 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S4 touches route/production wiring/session config; fresh rebuild deferred to S5
deferred: S5
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Forbidden imports

None.

## Independent countersign

```yaml
review: pending
next_step: P5-5C-S5
```
