# P5-5B-S6 Remediation Round 4 Handoff

状态：**S6 remediation round 4 complete — candidate 待 round 5 复审**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: p5-5b-s6-independent-review-4.md (FAIL on S6-RR12)
parent_candidate: 5a2bd56dafe5ccb71f5ffe334a12e41c639ff215
remediation_round: 4
findings_addressed:
  S6-RR12: closed — AdmissionFirstUvicornServer pre-drain runs before Uvicorn connection drain;
    readiness=false and admission close happen on SIGTERM/shutdown entry, not lifespan finally only
container_rebuild_required: yes
container_reason: Dockerfile CMD now uses gateway_backend.bootstrap.http_server entrypoint
container_gate_for_current_head: deferred
```

## Key changes

| Finding | Fix |
|---------|-----|
| RR12 | `gateway_backend/http/shutdown.py` — `begin_http_pre_drain()` |
| RR12 | `gateway_backend/bootstrap/http_server.py` — `AdmissionFirstUvicornServer` overrides `handle_exit` + `shutdown` |
| RR12 | `Dockerfile` CMD → `python -m gateway_backend.bootstrap.http_server` |
| RR12 | `app.py` lifespan finally delegates to `begin_http_pre_drain`; test-only `GATEWAY_BACKEND_SKIP_REPOSITORY_READY_PROBE=1` |
| RR12 | `test_uvicorn_sigterm_rejects_new_submit_before_exit` — real subprocess SIGTERM evidence |

## Focused gate

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py \
  tests/test_bundle_assembly.py \
  tests/test_architecture.py::test_http_bootstrap_owns_uvicorn_entry

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_http_admission_shutdown.py::test_uvicorn_sigterm_rejects_new_submit_before_exit \
  tests/test_submit_worker_process.py

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 374 source files
```

Gate results (2026-09-17): unit 55 passed; serial 4 passed; ruff/mypy pass.

## New owner test nodeids

- `test_production_pre_drain_marks_not_ready_and_closes_admission`
- `test_uvicorn_sigterm_rejects_new_submit_before_exit`
- `test_http_bootstrap_owns_uvicorn_entry`

## Deferred

- S8 authoritative runner、五包 static conjunction、current-HEAD image digest
- Compose e2e full conjunction pass

## next_step

```yaml
next_step: S6 independent review round 5
s7_entry: blocked pending S6 pass
```
