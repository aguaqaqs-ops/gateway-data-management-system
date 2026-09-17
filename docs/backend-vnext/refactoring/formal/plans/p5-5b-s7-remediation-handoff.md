# P5-5B-S7 Remediation Handoff

状态：**S7 remediation complete — candidate 待 closure review**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s7-independent-review.md
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
remediation_worktree: uncommitted
findings_addressed:
  S7-F6: closed — architecture owners allow http.runtime bootstrap import + http/ repository client
  S7-F1: closed — await handler idempotent return before lease refresh; recovery integration test
  S7-F4: closed — HTTP negative external step + RETRY_FROM_CHECKPOINT
  S7-F2: closed (scoped) — compose submit route wiring test; full Accept→T3→read defer S8
findings_not_remediated:
  S7-O2: repository restart journey — reopen candidate, non-blocking
```

## Changes by finding

| Finding | Paths | Fix |
| --- | --- | --- |
| S7-F6 | `tests/test_architecture.py` | Allow `gateway_backend.http.runtime` in bootstrap imports; allow `http/` for repository client |
| S7-F1 | `application/submit_jobs.py`, `tests/test_submit_recovery.py` | Read fresh FINALIZED+SUCCEEDED before `refresh_control`; `test_await_import_replay_after_finalize_commit_before_worker_ack` |
| S7-F4 | `tests/test_operator_recovery_http.py` | `test_operator_recovery_rejects_retry_on_external_step` |
| S7-F2 | `tests/test_submit_compose_e2e.py` | `test_compose_submit_accept_route_is_wired_for_unprepared_workspace` (local repo image; proves not SERVICE_NOT_READY) |

## Focused retest

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_architecture.py::test_worker_bootstrap_owns_concrete_process_composition \
  tests/test_architecture.py::test_repository_client_is_confined_to_repository_read_and_write \
  tests/test_operator_recovery_http.py::test_operator_recovery_rejects_retry_on_external_step
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
# 27 passed, 7 deselected

../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_submit_recovery.py::test_await_import_replay_after_finalize_commit_before_worker_ack \
  tests/test_submit_job_effect.py::test_await_import_result_succeeded_finalizes_submission
# 2 passed

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_compose_e2e.py::test_compose_submit_accept_route_is_wired_for_unprepared_workspace
# 1 passed

../scripts/uv-consume.sh -C . run ruff check \
  src/gateway_backend/application/submit_jobs.py \
  tests/test_submit_recovery.py tests/test_operator_recovery_http.py \
  tests/test_architecture.py tests/test_submit_compose_e2e.py
# pass

../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

## Deferred to S8

- Full compose Accept→upload→import→poll→T3→read（repository-service **build** 仍因 dolt checksum 失败）
- 五包 static、权威 runner、三镜像 conjunction provenance

## next_step

```yaml
next_step: P5-5B-S7 closure review (p5-5b-s7-acceptance.md)
s8_entry: eligible_after_closure_pass
```
