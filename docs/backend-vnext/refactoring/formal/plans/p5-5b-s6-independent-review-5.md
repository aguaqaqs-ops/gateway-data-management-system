# P5-5B-S6 Independent Review Round 6 (remediation round 5, 37fa7c21)

状态：**PASS — S6 closed; S7 entry eligible**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target and decision

```yaml
stage: P5-5B-S6-remediation-round-5
implementation_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
parent_candidate: 5a2bd56dafe5ccb71f5ffe334a12e41c639ff215
previous_reviews:
  - p5-5b-s6-independent-review.md
  - p5-5b-s6-independent-review-2.md
  - p5-5b-s6-independent-review-3.md
  - p5-5b-s6-independent-review-4.md
decision: pass
findings_open: []
findings_closed_this_round: [S6-RR12, S6-RR13, S6-RR14, S6-RR15]
container_gate_for_current_head: backend_build_pass; repository_conjunction_skipped_dolt_checksum
five_package_static: deferred
authoritative_runner: deferred
s7_entry: eligible
```

## 2. Round 5 closure verification

| Finding | Fix verified | Evidence |
| --- | --- | --- |
| S6-RR12 | Admission-first pre-drain before Uvicorn shutdown | `http/shutdown.py::begin_http_pre_drain`; `bootstrap/http_server.py::AdmissionFirstUvicornServer`; `test_admission_first_server_pre_drains_before_super_shutdown`; `test_uvicorn_sigterm_rejects_new_submit_before_exit` |
| S6-RR13 | Production `create_app()` no longer reads skip probe env | `app.py` uses `prepare_backend_runtime` without skip flag; `repository_ready_stub.py` test-only; `test_http_server_subprocess_fails_closed_when_repository_unreachable` |
| S6-RR14 | Serial process tests split from unit | `test_http_admission_shutdown_process.py` (`serial`); unit barrier in `test_http_admission_shutdown.py` |
| S6-RR15 | Backend image CMD gate + provenance | `test_backend_image_builds_with_http_server_entrypoint`; Dockerfile CMD `python -m gateway_backend.bootstrap.http_server` |

**Architecture boundary expansion（S6 scope，非 regression）**：
- `operation_worker.py` 导入 `http.runtime` 共享 production composition
- `http/runtime.py` 使用 `gateway_repository_client`（readiness/resolve ports）
- `test_architecture.py` 已更新允许 `http.runtime` / `http.shutdown` imports

## 3. Focused gate results（@ `37fa7c21`, `uv-consume.sh`）

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
# 6 passed, 1 skipped
# skipped: test_backend_container_ready_and_stops_cleanly_with_repository_service
#   (repository-service build unavailable — dolt checksum; backend-only gate still passes)

../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: 377 source files
```

## 4. Deferred（不阻塞 S6 pass）

| Item | Owner stage |
| --- | --- |
| 五包 static gate | S8 |
| 权威 `./vnext/scripts/run-tests.sh` | S8 |
| 三镜像 conjunction + provenance digest | S8 |
| Compose Accept→T3→read 完整 journey | **S7**（S6 handoff explicit defer） |
| `test_backend_container_ready_and_stops_cleanly_with_repository_service` skip | 环境 dolt checksum；S8 重试 |

## 5. Conclusion

S6-R1–R8、RR1–RR15 全部关闭。Production wiring、readiness/shutdown、settings、compose secret/grace、
process smoke 与 backend image entrypoint 证据完整。

```yaml
s5_independent_review: pass
s6_independent_review: pass
next_step: P5-5B-S7 independent functional acceptance
```
