# P5-5D-S2 Bounded Read, Audit and Single-Transaction Archive Handoff

状态：**S2 remediation delivered — pending independent closure**

日期：2026-09-21

Owner：Backend Archive Application

## Authority gate snapshot

```yaml
p5_5d_s1_stage_exit: pass
p5_5d_design: accepted
p5_5d_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
repository_effect_authorized: false
production_deployment_authorized: false
p5_5d_s2_stage_exit: not_evaluated
```

## Traceability

```yaml
stage: P5-5D-S2-bounded-read-audit-single-transaction-archive
parent_plan: docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md
implementation_candidate_head: 6c99810779
remediation_implementation_head: 1796e5b0bf
workspace_schema_version: 5
uv_lock_in_diff: no
next_step: P5-5D-S2-remediation-review
```

## Input authority

- `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5d-s0-entry-brief.md`

## Scope paths

### Initial implementation (`6c99810779`)

- `vnext/backend/src/gateway_backend/domain/archive/**`
- `vnext/backend/src/gateway_backend/application/archive/**`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_archive.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/database.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_baseline.py`
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py`
- `vnext/backend/src/gateway_backend/domain/baseline/errors.py`
- `vnext/backend/src/gateway_backend/domain/submission/ports.py`
- `vnext/backend/src/gateway_backend/application/submission/review.py`
- `vnext/backend/src/gateway_backend/application/submission/review_transaction.py`
- `vnext/backend/src/gateway_backend/application/submission/errors.py`
- `vnext/backend/src/gateway_backend/http/orchestration/review.py`
- `vnext/backend/src/gateway_backend/http/routes/reviews.py`
- `vnext/backend/src/gateway_backend/http/errors.py` — `ARCHIVE_CLOSED` mapping
- `vnext/backend/tests/test_archive_*.py`
- `vnext/backend/tests/support/archive_fixtures.py`

### Remediation (review F1–F10)

- `vnext/backend/src/gateway_backend/application/archive/snapshot.py` — occupancy gate, bounded read mapping
- `vnext/backend/src/gateway_backend/application/archive/queries.py` — submit blockers; remove dead code
- `vnext/backend/src/gateway_backend/application/archive/start.py` — occupancy gate wiring
- `vnext/backend/src/gateway_backend/application/archive/audit.py` — empty-stream REVOKE rejection
- `vnext/backend/src/gateway_backend/domain/submission/errors.py` — `ArchiveCandidateReadBoundExceeded`
- `vnext/backend/src/gateway_backend/http/errors.py` — `ArchiveIntegrityFailure` → 503
- `vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py` — disposition partial unique
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py` — `LIMIT 201`
- `vnext/backend/tests/support/archive_fixtures.py` — dual-sibling seed helpers
- `vnext/backend/tests/support/baseline_fixtures.py` — scoped baseline node id
- Extended: `test_archive_queries.py`, `test_archive_audit.py`, `test_archive_transactions.py`,
  `test_archive_concurrency.py`, `test_archive_control_db_migrations.py`, `test_review_transactions.py`,
  `test_review_http.py`, `test_submit_transactions.py`

## Review findings closed

| Finding | Remediation |
| --- | --- |
| F1 sibling/anomaly zero coverage | Dual-sibling fixtures; queries/audit/transaction tests for disposition, anomaly, resolution |
| F2 occupancy gate missing | `collect_repository_submit_blockers` / `assert_repository_submit_gate`; `ArchiveIntegrityFailure` HTTP 503 |
| F3 concurrency owner gaps | Two-connection races for Start/revoke and competing keys |
| F4 audit owner gaps | REVOKE on empty stream; actor/sequence/subject-expiry matrix |
| F5 unbounded candidate read | SQL `LIMIT 201` + domain `ArchiveCandidateReadBoundExceeded` |
| F6 cross-repo negative case removed | `scoped_baseline_node_id` fix; restore `different_repository_same_project` |
| F7 allowlist drift | Execution plan §3 budget updated |
| F8 missing handoff | This document |
| F9 `ARCHIVE_CLOSED` HTTP untested | `test_review_http.py` 409 assertions |
| F10 disposition partial unique | Migration index + migration test assertion |

## Invariants delivered

- Bounded candidate read at SQL layer (`LIMIT 201`) with typed scope-limit errors
- Repository occupancy integrity gate before Archive Start (Design §5.1.4)
- Single-transaction Archive: Plan/Result/Node/Head CAS/disposition/release atomic in one UoW
- Audit append with fingerprint idempotency; REVOKE requires existing stream
- Review closure: `ARCHIVE_CLOSED` on new return after archive; successful replay returns original event
- Dual-sibling candidate-set semantics with disposition classification
- No Archive HTTP routes; no production wiring; v5 schema not published; zero Repository I/O

## Unique test owners

- `tests/test_archive_queries.py` — candidate eligibility, sibling set, anomaly preview, scope limit
- `tests/test_archive_audit.py` — confirmation/resolution idempotency, REVOKE, actor, subject expiry
- `tests/test_archive_transactions.py` — single-tx Start, dual-sibling disposition, occupancy integrity
- `tests/test_archive_concurrency.py` — two-connection commit-order races
- `tests/test_archive_control_db_migrations.py` — v5 Archive DDL including partial unique index
- `tests/test_review_transactions.py` — `ARCHIVE_CLOSED`, replay after archive
- `tests/test_review_http.py` — HTTP 409 `ARCHIVE_CLOSED`

## Focused gate

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_queries.py tests/test_archive_audit.py \
  tests/test_archive_transactions.py tests/test_archive_concurrency.py \
  tests/test_archive_control_db_migrations.py tests/test_review_transactions.py \
  tests/test_review_http.py tests/test_submit_transactions.py tests/test_submit_idempotency.py \
  tests/test_architecture.py
# => 218 passed, 1 warning, ~9.1s

../scripts/uv-consume.sh -C . run ruff check .
# => All checks passed

../scripts/uv-consume.sh -C . run mypy
# => Success: no issues found in 415 source files
```

五包 static（backend / repository_service / repository_client / repository_contracts / shared_kernel）
ruff + mypy 全通过；无 `uv.lock` 变更。

## Container / image gate

```yaml
container_rebuild_required: deferred
container_reason: S2 is control DB / application / tests only; no Archive routes, Compose, entrypoint, or runtime ENV change
deferred: S3/S4
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
```

## Forbidden imports

None. Archive application/domain layers import only shared_kernel and backend domain layers.

## Independent countersign

```yaml
review: pending
next_step: P5-5D-S2-remediation-review
```
