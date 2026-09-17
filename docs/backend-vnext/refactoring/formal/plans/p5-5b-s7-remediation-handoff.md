# P5-5B-S7 Remediation Handoff (Round 3 + F8 Closeout)

状态：**F8 record sealing remediated — pending review-6 mechanical verification**

日期：2026-09-18

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s7-independent-review-5.md
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 7c511c4b8b59842b67d24083abf274ba620b2e7e
implementation_seal: 7c511c4b8b59842b67d24083abf274ba620b2e7e
records_head: b80a283f689ed6e957f932a72bc283aeacbef5be
findings_addressed:
  S7-F1: closed @ review-4 — finalize_transaction.py + submit_jobs.py + test_submit_recovery.py
  S7-F4: closed @ review-4 — test_operator_recovery_http.py
  S7-F6: closed @ review-4 — test_architecture.py (http/runtime.py only)
  S7-F2: reclassified_deferred_to_s8 — compose smoke removed
  S7-F7: closed @ review-5 — abort_transaction.py defer_operation_terminal + publish_operation stable-abort builder; WorkerRuntime serial owner
  S7-F8: remediated — pin 7c511c4b reachable; integration deselected count corrected
findings_not_remediated:
  S7-O2: repository restart journey — reopen candidate, non-blocking
```

> `b48ca592` 的 pin（`5de2e0b7…`）为 amend 孤本，不可解析；authoritative implementation seal 为 `7c511c4b`。

## Changes by finding (round 3)

| Finding | Paths | Fix |
| --- | --- | --- |
| S7-F7 | `application/submission/abort_transaction.py`, `application/submit_jobs.py`, `tests/test_submit_recovery.py` | `defer_operation_terminal`；`abort_submit_in_control_transaction`；`_make_stable_abort_builder` + `publish_operation`；`test_await_import_stable_abort_completes_via_worker_runtime` |
| S7-F8 | `p5-5b-s7-acceptance.md`, `p5-5b-s7-remediation-handoff.md` | pin `7c511c4b`；integration retest `9 deselected`；`implementation_seal` / `records_head` 字段 |

## Prior round paths (for provenance)

| Finding | Round 2 paths |
| --- | --- |
| S7-F1 | `finalize_transaction.py`, `submit_jobs.py`, `test_submit_recovery.py` |
| S7-F4 | `test_operator_recovery_http.py` |
| S7-F6 | `test_architecture.py` |
| S7-F2 | `test_submit_compose_e2e.py`, review docs |

## Focused retest (@ `7c511c4b`)

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'
# 2 passed, 9 deselected

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_transactions.py -k abort
# 7 passed, 28 deselected

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py -k stable_abort
# 1 passed, 15 deselected

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
# 26 passed, 9 deselected

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
next_step: P5-5B-S7 review-6 mechanical F8 sealing verification
s8_entry: blocked
```
