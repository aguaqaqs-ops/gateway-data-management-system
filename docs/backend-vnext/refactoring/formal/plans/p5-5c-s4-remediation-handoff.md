# P5-5C-S4 Finding-Scoped Remediation Handoff

状态：**S4 remediation delivered — pending independent countersign**

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
stage: P5-5C-S4-remediation
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s4-handoff.md
implementation_candidate_head: 83dc907cb5
remediation_implementation_head: pending_commit
finding_remediation: P2-1, P2-2
next_step: independent_S4_countersign_then_P5-5C-S5
```

`implementation_candidate_head` 保留首次 S4 代码交付提交 `83dc907cb5`。

## Findings closed

| ID | Severity | Summary | Closure |
| --- | --- | --- | --- |
| P2-1 | P2 | `parse_review_idempotency_key` trimmed header before domain validation | Removed `.strip()`; validate raw header via `validate_review_idempotency_key`; HTTP param cases + padded-key replay regression |
| P2-2 | P2 | Cross-scope / permission / mapping HTTP matrix incomplete | Same-database cross-scope POST/GET; replay permission re-check 403; GET permission-before-object-read on existing submission; mapping missing/disabled/drift POST/GET; `ScopeResolutionError` mapping missing/disabled → 404 in `http/errors.py` |

## Changed paths

- `vnext/backend/src/gateway_backend/http/orchestration/review.py`
- `vnext/backend/src/gateway_backend/http/errors.py`
- `vnext/backend/tests/test_review_http.py`
- `docs/backend-vnext/refactoring/formal/plans/p5-5c-s4-remediation-handoff.md`

## HTTP test matrix additions (`tests/test_review_http.py`)

| Barrier | Covered |
| --- | --- |
| Idempotency-Key whitespace/length/control (no trim) | yes |
| padded-key 422 then unpadded-key fresh 201 (not replay) | yes |
| same-database cross-scope POST/GET 404 | yes |
| replay without `review_submission` → 403 | yes |
| GET existing submission without permission → 403 | yes |
| mapping missing/disabled → 404 (POST/GET) | yes |
| mapping drift (`repo-other`) → 404 (POST/GET) | yes |

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# => 102 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/http \
  tests/test_review_http.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_architecture.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 389 source files
```

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S4 remediation is HTTP orchestration/errors/tests only
deferred: S5
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Independent countersign

```yaml
review: pending
next_step: P5-5C-S5
```
