# P5-5D-S2 Bounded Read, Audit and Single-Transaction Archive Handoff

状态：**S2 evidence remediation delivered — pending independent closure**

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
remediation_implementation_head: 12441a5402
evidence_remediation_head: b34d64751a
workspace_schema_version: 5
uv_lock_in_diff: no
candidate_binding: bind to the reachable commit that introduces or updates this handoff; never record amend intermediate objects
next_step: P5-5D-S2-remediation-review
```

## Input authority

- `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5d-s0-entry-brief.md`

## Scope paths

### Allowed budget (unchanged in remediation)

- `vnext/backend/src/gateway_backend/http/orchestration/review.py`
- `vnext/backend/src/gateway_backend/http/routes/reviews.py`
- `vnext/backend/tests/conftest.py` — `db_path` fixture (`6c99810779`)

### Changed in `6c99810779`

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
- `vnext/backend/src/gateway_backend/http/errors.py` — `ARCHIVE_CLOSED` mapping
- `vnext/backend/tests/conftest.py`
- `vnext/backend/tests/test_archive_*.py`
- `vnext/backend/tests/support/archive_fixtures.py`

### Changed in remediation `12441a5402`

- `vnext/backend/src/gateway_backend/application/archive/snapshot.py` — occupancy gate, bounded read mapping
- `vnext/backend/src/gateway_backend/application/archive/queries.py` — submit blockers; remove dead code
- `vnext/backend/src/gateway_backend/application/archive/start.py` — occupancy gate wiring
- `vnext/backend/src/gateway_backend/application/archive/audit.py` — empty-stream REVOKE rejection
- `vnext/backend/src/gateway_backend/domain/submission/errors.py` — `ArchiveCandidateReadBoundExceeded`
- `vnext/backend/src/gateway_backend/http/errors.py` — `ArchiveIntegrityFailure` → 503
- `vnext/backend/src/gateway_backend/infrastructure/control_db/migrations.py` — disposition partial unique
- `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_submission.py` — `LIMIT 201`
- `vnext/backend/tests/support/archive_fixtures.py`, `baseline_fixtures.py`
- Extended archive/review/submit tests listed in F1–F10 remediation

### Changed in evidence remediation (this commit)

- `vnext/backend/tests/support/archive_fixtures.py` — bulk approved candidate SQL seed
- `vnext/backend/tests/test_archive_queries.py` — real `LIMIT 201` boundary tests
- `vnext/backend/tests/test_archive_audit.py` — resolution empty-stream REVOKE
- `vnext/backend/tests/test_archive_transactions.py` — `ArchiveAnomalyUnresolved` Start; occupancy mismatch
- `vnext/backend/tests/test_archive_concurrency.py` — strengthened races; AcceptSubmit/Start barrier
- `vnext/backend/tests/test_submit_transactions.py` — scoped `seed_submit_ready_workspace` actor ids
- This handoff and execution plan §3 note

## Review findings closed

| Finding | Remediation |
| --- | --- |
| F1 sibling/anomaly zero coverage | Dual-sibling fixtures; queries/audit/transaction tests for disposition, anomaly, resolution |
| F2 occupancy gate missing | `collect_repository_submit_blockers` / `assert_repository_submit_gate`; `ArchiveIntegrityFailure` HTTP 503 |
| F3 concurrency owner gaps | Two-connection races; strengthened post-state; AcceptSubmit/Start barrier |
| F4 audit owner gaps | REVOKE on empty stream (confirmation + resolution); actor/sequence/subject-expiry matrix |
| F5 unbounded candidate read | SQL `LIMIT 201` + real 200/201 boundary tests + `ArchiveCandidateReadBoundExceeded` mapping |
| F6 cross-repo negative case removed | `scoped_baseline_node_id` fix; restore `different_repository_same_project` |
| F7 allowlist drift | Execution plan §3 budget updated incl. `T/conftest.py` |
| F8 missing handoff | This document |
| F9 `ARCHIVE_CLOSED` HTTP untested | `test_review_http.py` 409 assertions |
| F10 disposition partial unique | Migration index + migration test assertion |

## Open observations (no production change)

- `start_archive` validates `candidate_set_digest` before `assert_repository_submit_gate`; when both digest mismatch and active attempts exist, callers observe `CandidateSetConflict` rather than `ActiveSubmitAttempt` (Design §5.1 step order vs current implementation).

## Invariants delivered

- Bounded candidate read at SQL layer (`LIMIT 201`) with typed scope-limit errors and regression tests on real rows
- Repository occupancy integrity gate before Archive Start (Design §5.1.4)
- Single-transaction Archive: Plan/Result/Node/Head CAS/disposition/release atomic in one UoW
- Audit append with fingerprint idempotency; REVOKE requires existing stream
- Review closure: `ARCHIVE_CLOSED` on new return after archive; successful replay returns original event
- Dual-sibling candidate-set semantics with disposition classification
- No Archive HTTP routes; no production wiring; v5 schema not published; zero Repository I/O

## Unique test owners

- `tests/test_archive_queries.py` — candidate eligibility, sibling set, anomaly preview, SQL fetch limit
- `tests/test_archive_audit.py` — confirmation/resolution idempotency, REVOKE, actor, subject expiry
- `tests/test_archive_transactions.py` — single-tx Start, dual-sibling disposition, occupancy integrity, anomaly Start block
- `tests/test_archive_concurrency.py` — two-connection commit-order races incl. AcceptSubmit/Start
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
# => 223 passed, 1 warning, ~9.6s

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
last_verified_image_revision: 04317788c2
container_gate_for_current_head: not_applicable
```

`last_verified_image_revision` 引用 execution plan §6.3 既有锚点（5C accepted candidate）；本轮未重建镜像。

## Forbidden imports

None. Archive application/domain layers import only shared_kernel and backend domain layers.

## Independent countersign

```yaml
review: pending
next_step: P5-5D-S2-remediation-review
```
