# P5-5B-S7 Remediation Handoff (Round 2)

状态：**S7 remediation complete — closure @ review-3**

日期：2026-09-18

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s7-independent-review.md
baseline_commit: 4cda6b9c
remediation_commit: pending
supersedes_round: 1 (draft baseline in 4cda6b9c)
findings_addressed:
  S7-F1: closed — defer_operation_terminal + publish_operation finalize builder; WorkerRuntime serial integration proof
  S7-F4: closed — test_operator_recovery_rejects_retry_on_external_step (retained from baseline)
  S7-F6: closed — repository client allow-list精确到 http/runtime.py
  S7-F2: reclassified_deferred_to_s8 — compose smoke removed; full journey defer S8 §6.4
findings_not_remediated:
  S7-O2: repository restart journey — reopen candidate, non-blocking
```

## Changes by finding

| Finding | Paths | Fix |
| --- | --- | --- |
| S7-F1 | `application/submission/finalize_transaction.py`, `application/submit_jobs.py`, `tests/test_submit_recovery.py` | `defer_operation_terminal`；`_make_finalize_success_builder` + `publish_operation`；删除 handler 裸 `return PUBLISHED` / 早返回；`test_await_import_finalize_commits_lease_acknowledgment_via_worker_runtime` |
| S7-F4 | `tests/test_operator_recovery_http.py` | unchanged from baseline |
| S7-F6 | `tests/test_architecture.py` | `allowed_files = (http/runtime.py,)` for `gateway_repository_client` |
| S7-F2 | `tests/test_submit_compose_e2e.py`, review docs | 删除 `test_compose_submit_accept_route_is_wired_for_unprepared_workspace`；S7-F2 → S8 |

## Focused retest

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'await_import and worker_runtime'
# 1 passed

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_finalize.py tests/test_submit_transactions.py -k finalize
# 3 passed

ACCUMULATED=(tests/test_submit_domain.py tests/test_submit_idempotency.py \
  tests/test_submit_application.py tests/test_submit_transactions.py \
  tests/test_submit_control_db_migrations.py tests/test_sqlite_submit_repository.py \
  tests/test_submit_import_builder.py tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py tests/test_artifact_boundary.py \
  tests/test_submit_http.py tests/test_submit_read_http.py tests/test_operation_http.py \
  tests/test_operator_recovery_http.py tests/test_http_openapi.py \
  tests/test_submit_job_payload.py tests/test_submit_job_prepare.py \
  tests/test_submit_finalize.py tests/test_production_wiring.py \
  tests/test_backend_readiness.py tests/test_http_admission_shutdown.py \
  tests/test_architecture.py)
../scripts/uv-consume.sh -C . run pytest -q -m unit "${ACCUMULATED[@]}"
# 319 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py
# 27 passed (excluding new serial owner)

../scripts/uv-consume.sh -C . run ruff check \
  src/gateway_backend/application/submit_jobs.py \
  src/gateway_backend/application/submission/finalize_transaction.py \
  tests/test_submit_recovery.py tests/test_operator_recovery_http.py \
  tests/test_architecture.py tests/test_submit_compose_e2e.py
# pass

../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

## Deferred to S8

- Full compose Accept→upload→import→poll→T3→read（S7-F2 reclassified）
- 五包 static、权威 runner、三镜像 conjunction provenance

## next_step

```yaml
next_step: P5-5B-S8 final current-HEAD gate (p5-5b-s7-acceptance.md)
s8_entry: eligible
```
