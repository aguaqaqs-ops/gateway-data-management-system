# P5-5B-S6 Remediation Round 5 Handoff

状态：**S6 remediation round 5 complete — candidate 待 round 6 复审**

日期：2026-09-17

Owner：P5-5B Delivery

## Review closure

```yaml
review: independent Round 4 RR12 FAIL (RR13/RR14/RR15 findings; not p5-5b-s6-independent-review-4.md)
parent_candidate: 5a2bd56dafe5ccb71f5ffe334a12e41c639ff215
implementation_candidate: acf63ec3550a09c364886b50b1fb0cad893184c6
remediation_round: 5
findings_addressed:
  S6-RR12: closed (carried from round 4) — AdmissionFirstUvicornServer pre-drain before Uvicorn drain
  S6-RR13: closed — production create_app() no longer reads SKIP_REPOSITORY_READY_PROBE
  S6-RR14: closed — serial process tests split; deterministic shutdown barrier unit probe; SIGTERM test stable
  S6-RR15: closed — immutable candidate commit; backend image build gate; container provenance recorded
container_rebuild_required: yes
container_reason: Dockerfile CMD uses gateway_backend.bootstrap.http_server since round 4
container_gate_for_current_head: backend build + CMD inspect pass; repository readiness runtime gate skipped (dolt checksum)
```

## Key changes

| Finding | Fix |
|---------|-----|
| RR13 | Removed `GATEWAY_BACKEND_SKIP_REPOSITORY_READY_PROBE` from [`app.py`](vnext/backend/src/gateway_backend/app.py) |
| RR13 | [`repository_ready_stub.py`](vnext/backend/tests/support/repository_ready_stub.py) for process tests |
| RR13 | `test_http_server_subprocess_fails_closed_when_repository_unreachable` |
| RR14 | [`test_http_admission_shutdown_process.py`](vnext/backend/tests/test_http_admission_shutdown_process.py) (`serial` only) |
| RR14 | `test_admission_first_server_pre_drains_before_super_shutdown` (unit barrier) |
| RR15 | [`test_backend_http_container_gate.py`](vnext/backend/tests/test_backend_http_container_gate.py) |

## Focused gate

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py
# 40 passed

../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_http_admission_shutdown_process.py \
  tests/test_submit_worker_process.py \
  tests/test_backend_http_container_gate.py
# 4 passed, 1 skipped (repository-service build unavailable)

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 377 source files
```

## Container provenance

```bash
cd vnext/deploy
docker compose build backend
docker inspect "${COMPOSE_PROJECT_NAME}-backend" --format '{{json .Config.Cmd}}'
# ["python","-m","gateway_backend.bootstrap.http_server"]

# Example gate run image (project gateway-backend-gate-test):
# sha256:9873640e0880ab84d5c4116610694fba98c4639bd947917876a9c763a95293d6
```

`test_backend_container_ready_and_stops_cleanly_with_repository_service` skipped when
`repository-service` build fails (dolt checksum); backend-only build and CMD inspect still required.

## New owner test nodeids

- `test_http_server_subprocess_fails_closed_when_repository_unreachable`
- `test_admission_first_server_pre_drains_before_super_shutdown`
- `test_backend_image_builds_with_http_server_entrypoint`

## Deferred

- S8 three-service conjunction、五包 static gate
- Compose e2e full journey

## next_step

```yaml
next_step: S6 independent review round 6
s7_entry: blocked pending S6 pass
```
