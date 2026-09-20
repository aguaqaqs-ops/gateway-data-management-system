# P5-5C-S3 Finding-Scoped Remediation Handoff

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
stage: P5-5C-S3-remediation
parent_handoff: docs/backend-vnext/refactoring/formal/plans/p5-5c-s3-handoff.md
implementation_candidate_head: dadf5d1f6f01e028e2020b005737040ae4bee11e
remediation_implementation_head: 02acbee188b05e4f78f9725c9ad959f2fbdc2189
sealed_doc_tree_head: pending_bind_after_commit
finding_remediation: F1-F8, P2-1-P2-3
next_step: independent_S3_countersign_then_P5-5C-S4
```

`implementation_candidate_head` 保留首次 S3 代码交付提交 `dadf5d1f6f`；
`remediation_implementation_head` 绑定 P2 countersign remediation 代码提交 `02acbee188`；
`sealed_doc_tree_head` 绑定 P2 remediation docs 提交（首轮 F1–F8 见 `9e08f2f63e` / `af157cf880`）。

## Findings closed

| ID | Severity | Summary | Closure |
| --- | --- | --- | --- |
| F1 | HIGH | `find_idempotency` `ReviewClosureViolation` leaked as 500 | `try/except` → `ReviewIntegrityFailure` in `review_transaction.py`; seed-bound idempotency regression test |
| F2 | HIGH | `ApplyReviewResult` missing `replay` for 201/200 | Added `replay: bool`; replay paths `True`, fresh `False`; design §6.1 updated |
| F3 | MEDIUM | `_release_workspace_for_review` object/isinstance dead defense | Top-level `Workspace` import; typed parameter |
| F4 | MEDIUM | CLOSED workspace empty 409 message | `WorkspaceNotOpen` → bounded `"workspace is not open"`; dedicated test |
| F5 | MEDIUM | Test/handoff overclaims | Release occupancy-delete rollback test; precise `ReviewVersionConflict` sequential test; replay workspace write-free assertions |
| F6 | MEDIUM | Handoff candidate head / gate incomplete | This handoff + parent handoff update; gate includes `test_sqlite_submit_repository.py`, `test_architecture.py` |
| F7 | LOW | Path budget omission | `sqlite_submission.py` + `test_sqlite_submit_repository.py` added to execution plan §3.1/§3.2 |
| F8 | LOW | Seam hygiene | `review_action_for_event_kind` in domain; removed `ReviewScopeFacts.resolved_scope`; simplified fingerprint path |
| P2-1 | P2 | Idempotency integrity after request compare | Reordered `verify_idempotency_replay`; cross-submission loads record events; corrupted fingerprint regression |
| P2-2 | P2 | Persisted reason not in closure | `validate_review_reason` in `validate_review_closure`; domain param cases + GET/replay integrity tests |
| P2-3 | P2 | Concurrent barrier evidence gap | `Barrier` dual-connection test; one commit + stable `ReviewVersionConflict` |
| P3 | LOW | Review uses full Submit transaction port | Deferred: no stray calls found; converge to minimal `ReviewApplyTransaction` before/within S4 |

## S4 entry note (not S3 defects)

Current `map_domain_exception` routes `ReviewIntegrityFailure` and `ReviewWorkspaceOccupancyConflict`
through generic `SubmitApplicationError` → 422; `ReviewVersionConflict` / `InvalidReviewReason` map to
`None` → 500. S4 must add explicit branches per design §9.3 before route registration.

## Focused gate (post-remediation)

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_review_domain.py tests/test_review_persistence.py \
  tests/test_review_transactions.py tests/test_submit_transactions.py \
  tests/test_sqlite_submit_repository.py tests/test_architecture.py
# => 230 passed

../scripts/uv-consume.sh -C . run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/domain/submission src/gateway_backend/infrastructure/control_db \
  tests/test_review_transactions.py tests/test_review_domain.py
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 385 source files
```

## Independent countersign

```yaml
review: pending
next_step: P5-5C-S4
```
