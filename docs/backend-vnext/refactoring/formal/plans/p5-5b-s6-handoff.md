# P5-5B-S6 Readiness, Shutdown, Settings and Deployment Wiring Handoff

状态：**S6 initial handoff — superseded by remediation round 1（见 p5-5b-s6-remediation-handoff.md）**

日期：2026-09-17

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
s5_handoff: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
s6_entry: authorized
s6_scope: production HTTP composition, readiness/shutdown, settings, compose wiring, process smoke
s6_complete: yes
s7_entry: deferred
```

## Traceability

```yaml
stage: P5-5B-S6-readiness-shutdown-settings-deployment-wiring
parent_head: pending-s5-commit
candidate_head: pending-s6-commit
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md §13
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md §S6
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s5-handoff.md
scope_paths:
  - vnext/backend/src/gateway_backend/app.py
  - vnext/backend/src/gateway_backend/settings.py
  - vnext/backend/src/gateway_backend/http/auth.py
  - vnext/backend/src/gateway_backend/http/runtime.py
  - vnext/backend/src/gateway_backend/http/dependencies.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/tests/test_backend_settings.py
  - vnext/backend/tests/test_backend_readiness.py
  - vnext/backend/tests/test_backend_dockerfile_contract.py
  - vnext/backend/tests/test_http_admission_shutdown.py
  - vnext/backend/tests/test_production_wiring.py
  - vnext/backend/tests/test_submit_worker_process.py
  - vnext/backend/tests/test_submit_compose_e2e.py
  - vnext/backend/tests/support/runtime_settings.py
  - vnext/deploy/compose.yaml
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s6-handoff.md
uv_lock_in_diff: no
container_rebuild_required: yes
container_reason: S6 touched compose/settings/readiness/deployment boundary
```

## Deliverables summary

| 组件 | 行为 |
|------|------|
| `settings.py` | 新增 `internal_bearer_token_file`（`GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE`）；absolute path validator；`repr=False` |
| `http/auth.py` | `load_internal_bearer_token()` — 与 repository/session token 同模式 |
| `http/runtime.py` | `build_workspace_job_registry()`（preview+submit）；`assert_repository_service_ready()`（`GET /readyz` + Bearer）；`prepare_backend_runtime()` 注入完整 `WorkspaceHttpDependencies`（`ReadOnlySubmissionStore`、`LocalArtifactRefLookup`、`StaticInternalBearerPort`、`HttpRepositoryMainResolvePort`、`HttpBaselineCanonicalDigestPort`、`build_submit_operator_recovery_port` + `HttpRepositoryAbortEvidencePort`） |
| `app.py` | lifespan `finally`：`app.state.ready = False` → `admission_gate.close()`；GET 路由仍可达 |
| `operation_worker.py` | 启动时 `assert_workspace_registry_ready(build_workspace_job_registry())` — 与 HTTP 同源 registry |
| `compose.yaml` | backend `GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE` + `backend-internal-bearer` secret；worker `stop_grace_period: 180s`；`depends_on: backend: service_healthy` |
| `test_submit_worker_process.py` | spawn `python -m gateway_backend.bootstrap.operation_worker`；SIGTERM drain；submit checkpoint barrier（before/after） |
| `test_submit_compose_e2e.py` | 三容器 compose smoke：`/readyz`、worker `worker_ready`、backend restart、workspace POST；repository build 失败时 fallback 本地 `gateway-repository-service:local` |

## Invariants delivered

- Backend `/readyz` 开放前校验 combined preview+submit registry **与** Repository `/readyz`（fail-closed；错误消息不含 token/URL path）。
- HTTP 与 worker 共用 `preview_job_definitions()` + `submit_job_definitions()` 源；remediation 后 `assert_submit_registry_decoders` 校验 submit decoder identity。
- Shutdown 顺序：readiness=false → admission close；new-work POST 返回 429；GET submit-attempts/submissions 仍可达。
- `HttpBaselineCanonicalDigestPort` 在 `runtime.py` 内组合 materialize + comparison + bundle assembly；失败映射 503 `DEPENDENCY_UNAVAILABLE`。
- Compose internal bearer secret 与 backend session/repository bearer 并列挂载。

## Unique test owners（S6）

| 文件 | 覆盖 |
|------|------|
| `tests/test_backend_settings.py` | `internal_bearer_token_file` 必填/absolute；worker 固定 budget 不可 env 覆盖；repr 无 token 泄露 |
| `tests/test_backend_readiness.py` | Repository `/readyz` fail-closed；combined registry 缺 submit step 失败；production port 类型断言；`/readyz` 无 token/path |
| `tests/test_http_admission_shutdown.py` | production shutdown `/readyz` 503 + `/healthz` 200；submit POST admission close 429 |
| `tests/test_production_wiring.py` | submit ports wired；combined registry step identity；`HttpRepositoryMainResolvePort` exact wire |
| `tests/test_backend_dockerfile_contract.py` | compose internal bearer env/secret；worker `stop_grace_period` |
| `tests/test_submit_worker_process.py` | 模块入口 drain/checkpoint barrier；日志无 token/db path/lease |
| `tests/test_submit_compose_e2e.py` | 三进程 compose smoke + backend restart |

## Focused gate

```bash
cd vnext/backend

# Unit
../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_backend_settings.py \
  tests/test_backend_readiness.py \
  tests/test_http_admission_shutdown.py \
  tests/test_production_wiring.py
# 28 passed

# Serial — submit worker process
../scripts/uv-consume.sh -C . run pytest -q -m serial \
  tests/test_submit_worker_process.py
# 3 passed

# Integration + serial — compose e2e（需 docker）
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_compose_e2e.py
# 1 passed

# Static
../scripts/uv-consume.sh -C . run ruff check .
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 371 source files
```

Compose build（S6 记录；S8 正式 gate 复验 current HEAD）：

```bash
cd vnext/deploy
docker compose build backend worker repository-service
# 本环境：backend+worker build pass；repository-service 可能因 Dolt 下载 checksum 失败，
# compose e2e 测试 fallback 至 gateway-repository-service:local（2026-09-15 b44a67a7fe62）
```

## Container provenance

```yaml
last_verified_image_revision:
  backend: gateway-submit-s6-test_compose_three_process_sub0-backend:latest (c2a3d674467d)
  worker: gateway-submit-s6-test_compose_three_process_sub0-worker:latest (fed90499aa9a)
  repository-service: gateway-repository-service:local (b44a67a7fe62)
container_gate_for_current_head: deferred
```

S6 在具备 docker 的环境验证了 compose smoke；**未**对最终 candidate HEAD 执行完整三镜像 conjunction gate（defer 至 S8）。

## Deferred

- **S8 authoritative runner**：五包 static conjunction、完整 container gate、current-HEAD image digest 记录。
- **Compose e2e 完整 journey**：accept submit → poll operation → read submission（S6 smoke 仅覆盖 startup/restart/workspace POST；完整 functional matrix 属 S7）。
- **Repository restart worker reconcile**：compose e2e 未复制 `test_submit_recovery.py` 全矩阵。
- **five_package_static**：S6 focused gate 仅 backend 包 ruff/mypy；其余四包 defer S8。
- **Dockerfile / UV_LOCK_SHA256**：S6 未修改 Dockerfile 或 lockfile。

## next_step

```yaml
next_step: P5-5B-S7 independent functional acceptance
s7_entry: deferred
s7_authorized: no
implementation_authority_unchanged: true
```
