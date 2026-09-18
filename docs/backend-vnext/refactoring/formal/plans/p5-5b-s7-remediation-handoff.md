# P5-5B-S7 Remediation Handoff (Round 4 Owner Evidence + F8 Closeout)

状态：**S7 pass @ review-7 — S8 entry eligible**

日期：2026-09-17 (UTC+8)

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s7-independent-review-7.md
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 7c511c4b8b59842b67d24083abf274ba620b2e7e
remediation_round_4: e5c43c0c9f71de3cd2e602504ec9034f16add8af
remediation_round_4_fix: d3661fe0eda4a3463afed879c6a5bbec72f79404
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
records_head: e19744e0f852518acea6aa91284cd5b10cc89fc3
findings_addressed:
  S7-F1: closed @ review-4 — finalize_transaction.py + submit_jobs.py + test_submit_recovery.py
  S7-F4: closed @ review-4 — test_operator_recovery_http.py
  S7-F6: closed @ review-4 — test_architecture.py (http/runtime.py only)
  S7-F2: reclassified_deferred_to_s8 — compose smoke removed
  S7-F7: closed @ review-5 — abort_transaction.py defer_operation_terminal + publish_operation stable-abort builder; WorkerRuntime serial owner
  S7-F8: closed @ review-7 — acceptance/review-7 mechanical seal
  S7-O2-T3-crash-barrier: closed @ review-7 — test_await_import_finalize_response_loss_after_terminal_commit_before_worker_ack
  S7-O2-repository-restart: closed @ review-7 — test_await_import_result_consumes_matching_terminal_after_repository_restart
  R4-F1: closed @ d3661fe0 — restart owner claim moved post-restart (test-only lease robustness)
timezone: Asia/Shanghai
```

> `b48ca592` 的 pin（`5de2e0b7…`）为 amend 孤本，不可解析；Round 3 code seal 为 `7c511c4b`；Round 4 owner evidence 为 `e5c43c0c`；R4-F1 test-only fix 为 `d3661fe0`。

## Changes by finding (round 4)

| Finding | Paths | Fix |
| --- | --- | --- |
| T3 crash barrier owner | `tests/test_submit_recovery.py` | `after_business_finalize_commit_before_worker_ack` UoW commit 后 fault；WorkerRuntime `_run_claim`；terminal durable fact eliminates reclaim |
| Repository restart owner | `tests/test_submit_recovery.py`, `tests/support/submit_job_harness.py` | live import journey + `shutdown_repository_service_client(preserve_data=True)` + post-restart poll/finalize |
| F8 closeout | `p5-5b-s7-acceptance.md`, `p5-5b-s7-independent-review-7.md`, 本 handoff | decision pass / s8_entry eligible |
| R4-F1 lease window | `tests/test_submit_recovery.py` | post-restart claim；docstring §490；hard-kill 语义 |

## Prior round paths (for provenance)

| Finding | Round 3 paths |
| --- | --- |
| S7-F7 | `abort_transaction.py`, `submit_jobs.py`, `test_submit_recovery.py` |
| S7-F8 | `p5-5b-s7-acceptance.md`, 本 handoff |

## Focused retest (@ `d3661fe0`)

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py \
  -k 'after_terminal_commit_before_worker_ack or repository_restart or (worker_runtime and (finalize or stable_abort))'
# 4 passed, 9 deselected

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'after_terminal_commit_before_worker_ack or repository_restart'
# 2 passed

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'
# 2 passed, 9 deselected

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
# 26 passed, 11 deselected

../scripts/uv-consume.sh -C . run ruff check .
../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

## Deferred to S8

- Full compose Accept→upload→import→poll→T3→read（S7-F2 reclassified → closed @ [p5-5b-s7-independent-review-8.md](p5-5b-s7-independent-review-8.md)）
- 五包 static、权威 runner、三镜像 conjunction provenance

## next_step

```yaml
next_step: P5-5B-S8 container and authoritative runner gate
s8_entry: eligible
```
