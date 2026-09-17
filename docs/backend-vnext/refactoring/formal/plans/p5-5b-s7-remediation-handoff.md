# P5-5B-S7 Remediation Handoff (Round 3)

状态：**S7 remediation round 3 complete — candidate pending review-5 closure**

日期：2026-09-18

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s7-independent-review-4.md
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 5de2e0b7f958eb496e24af7f304aef23f245ad1f
findings_addressed:
  S7-F1: closed @ review-4 — finalize_transaction.py + submit_jobs.py + test_submit_recovery.py
  S7-F4: closed @ review-4 — test_operator_recovery_http.py
  S7-F6: closed @ review-4 — test_architecture.py (http/runtime.py only)
  S7-F2: reclassified_deferred_to_s8 — compose smoke removed
  S7-F7: remediated — abort_transaction.py defer_operation_terminal + publish_operation stable-abort builder; WorkerRuntime serial owner
  S7-F8: remediated — closure record provenance corrected in S7 docs
findings_not_remediated:
  S7-O2: repository restart journey — reopen candidate, non-blocking
```

## Changes by finding (round 3)

| Finding | Paths | Fix |
| --- | --- | --- |
| S7-F7 | `application/submission/abort_transaction.py`, `application/submit_jobs.py`, `tests/test_submit_recovery.py` | `defer_operation_terminal`；`abort_submit_in_control_transaction`；`_make_stable_abort_builder` + `publish_operation`；`test_await_import_stable_abort_completes_via_worker_runtime` |
| S7-F8 | `p5-5b-s7-acceptance.md`, `p5-5b-s7-independent-review-3.md`, `p5-5b-s7-remediation-handoff.md` | pin round-2 seal `30193dd5`；integration 26 not 27；S6 doc reference；review-3 superseded；round-3 candidate pending |

## Prior round paths (for provenance)

| Finding | Round 2 paths |
| --- | --- |
| S7-F1 | `finalize_transaction.py`, `submit_jobs.py`, `test_submit_recovery.py` |
| S7-F4 | `test_operator_recovery_http.py` |
| S7-F6 | `test_architecture.py` |
| S7-F2 | `test_submit_compose_e2e.py`, review docs |

## Focused retest

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'
# 2 passed

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_transactions.py -k abort
# 7 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py -k stable_abort
# 1 passed

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
# 26 passed, 8 deselected

../scripts/uv-consume.sh -C . run ruff check \
  src/gateway_backend/application/submit_jobs.py \
  src/gateway_backend/application/submission/abort_transaction.py \
  src/gateway_backend/application/submission/finalize_transaction.py \
  tests/test_submit_recovery.py
# pass

../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

## Deferred to S8

- Full compose Accept→upload→import→poll→T3→read（S7-F2 reclassified）
- 五包 static、权威 runner、三镜像 conjunction provenance

## next_step

```yaml
next_step: P5-5B-S7 review-5 independent closure verification
s8_entry: blocked_until_review_5_pass
```
