# P5-5A S5 Handoff: bootstrap / readiness / shutdown / container

状态：**PASS — S5 实现闭合；backend image 已按本脏树重建并通过 /readyz smoke；worker Compose conjunction 仍 deferred；独立审核未做**

日期：2026-09-08

Owner：Bootstrap / deployment

上游：[P5-5A Upload Preview Execution Plan](p5-5a-upload-preview-execution-plan.md) S5、
HEAD `774bacb6`（S1/S2 已提交）+ 工作区未提交的 S3 HTTP 与 S4 Preview JobDefinition。

授权说明：仓库文档仍写 `p5_5a_implementation_authorized: no`。本阶段与 S1–S4 相同，以本对话用户指令覆盖，不回头改授权文档。本 handoff 不构成 S6 验收授权。

```yaml
stage: S5
candidate_head: 774bacb6be4d752f805e6df5b8ba9696959a70a9
candidate_worktree: uncommitted_s3_s4_s5_dirty_tree
conversation_context: new
scope_paths:
  - vnext/backend/src/gateway_backend/settings.py
  - vnext/backend/src/gateway_backend/app.py
  - vnext/backend/src/gateway_backend/http/dependencies.py
  - vnext/backend/src/gateway_backend/http/wiring.py
  - vnext/backend/src/gateway_backend/http/runtime.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/repository_read/
  - vnext/deploy/compose.yaml
  - vnext/backend/tests/
changed_paths:
  - vnext/backend/src/gateway_backend/settings.py
  - vnext/backend/src/gateway_backend/app.py
  - vnext/backend/src/gateway_backend/http/runtime.py
  - vnext/backend/src/gateway_backend/http/dependencies.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/src/gateway_backend/application/preview_registry.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/database.py
  - vnext/backend/src/gateway_backend/infrastructure/control_db/__init__.py
  - vnext/backend/src/gateway_backend/infrastructure/artifact_store/local_store.py
  - vnext/backend/src/gateway_backend/infrastructure/artifact_store/__init__.py
  - vnext/backend/src/gateway_backend/infrastructure/repository_read/__init__.py
  - vnext/deploy/compose.yaml
  - vnext/backend/README.md
  - vnext/backend/tests/support/runtime_settings.py
  - vnext/backend/tests/test_backend_settings.py
  - vnext/backend/tests/test_backend_readiness.py
  - vnext/backend/tests/test_http_admission_shutdown.py
  - vnext/backend/tests/test_app.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_operation_worker_lifecycle.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_operation_worker_process.py
  - vnext/backend/tests/test_operation_effect_reconcile.py
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_operation_job_synthetic.py
  - vnext/backend/tests/test_http_openapi.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s5-handoff.md
inherited_uncommitted_not_owned_by_s5:
  - vnext/backend/src/gateway_backend/application/preview_jobs.py
  - vnext/backend/src/gateway_backend/http/ (S3 routes/schemas/orchestration except runtime.py)
  - vnext/backend/pyproject.toml
  - vnext/backend/uv.lock
  - vnext/backend/tests/test_http_*.py
  - vnext/backend/tests/test_preview_job_*.py
  - vnext/backend/tests/test_workspace_http.py
  - vnext/backend/tests/test_upload_http.py
  - vnext/backend/tests/test_operation_http.py
  - vnext/backend/tests/support/http_workspace_harness.py
  - vnext/backend/tests/support/preview_job_harness.py
contract_owners:
  - Bootstrap/deployment -> settings fail-closed, /readyz, admission-first shutdown, worker preview composition, compose wiring, log redaction
tests:
  unit: pass
  integration: pass_focused_worker_wal
  serial: pass_focused_worker_process
  static: pass_backend_ruff_mypy
container:
  required: yes
  image_revision: sha256:83a81cf1ccadcce244a4f96cd8be962b0fc21cb77a1a455a19feb807eaf1d912
  image_tag: deploy-backend
  status: rebuilt
  rebuild_attempt: passed_default_builder_after_gcr_mirror
  backend_readyz_smoke: pass
review:
  independent: no
  findings: []
  remediation_retest: not-needed
deferred_touched:
  - live Repository table-access HTTP/Arrow adapter
  - worker Compose HTTP healthcheck
  - TTL/budget numeric retuning (frozen to existing constants)
  - S3/S4 git commit
  - worker_ready Compose evidence (no worker HTTP port)
  - backend ∧ worker ∧ repository deployment conjunction
reopen_required: false
decision: pass
validated_source_tree: sha256:796006e61d07210e4f6a75ce29bcde588b227c0125d20bceedfbc851ca980e03
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
source_tree_file_count: 299
compose_yaml_sha256: sha256:11441cd631cb1ea5279f7fe684a14cd41160257444012067665d7bcfd7b6bf0d
validated_source_tree_plus_compose: sha256:0179354ac1ef27be8311a5ee971347ce1f4836844176e7d0375ed22744d37142
container_rebuild_required: yes
container_gate: passed_backend_image_smoke
last_verified_image_revision: sha256:83a81cf1ccadcce244a4f96cd8be962b0fc21cb77a1a455a19feb807eaf1d912
p5_5a_implementation_authorized_in_docs: no
next_step: P5-5A-S6
next_step_authorized: no
```

## 评审模板（testing-conventions）

```text
Current HEAD: 774bacb6be4d752f805e6df5b8ba9696959a70a9 (dirty tree: uncommitted S3 HTTP + S4 Preview JobDefinition + S5 bootstrap)
Container rebuild required: yes
Reason: Compose env/volume/healthcheck/worker command 已改；backend healthcheck 从 /healthz 改为 /readyz；worker 从 print stub 改为 python -m gateway_backend.bootstrap.operation_worker。命中 testing-conventions 强制重建项。Dockerfile / production 依赖闭包 / CMD 未改；未把 gateway-repository-client 加入 backend 生产闭包。
Last verified image revision: sha256:83a81cf1ccadcce244a4f96cd8be962b0fc21cb77a1a455a19feb807eaf1d912 (tag deploy-backend)
Last verified source-tree/image id: validated_source_tree sha256:796006e61d07210e4f6a75ce29bcde588b227c0125d20bceedfbc851ca980e03 paired with image sha256:83a81cf1ccadcce244a4f96cd8be962b0fc21cb77a1a455a19feb807eaf1d912
Container gate for current HEAD: passed_backend_image_smoke
Deferred gates/nodeids:
  - worker_ready log evidence from Compose worker service (no worker HTTP port)
  - backend ∧ worker ∧ repository conjunction
Prior failed attempt (historical, not current evidence): 2026-09-08T16:38:36Z–17:11:59Z, exit 17, pve-registry-http BuildKit blob commit after rust pull; superseded by 2026-09-08T17:53:35Z–17:56:35Z BUILDX_BUILDER=default rebuild
Required execution point: S6 for worker Compose conjunction; backend image smoke already executed on this dirty tree
```

历史 P4 image 一律标 `historical`，不得关闭本 HEAD 的 container finding：

- `sha256:f461fc3ec5347e3779edbdc0c041ba15af9b2cc79c007e525f7844d3815abaaf` — historical (P4-R3 worker lifecycle)
- `sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95` — historical (P4-R5)
- `sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b` — historical (P4-R4)

`docker compose config` 对本 dirty tree 的 `vnext/deploy/compose.yaml` 解析成功；这不是 image gate。

拉取网络（本机，非仓库文件）：`pve-registry-http` 原先不继承 `/etc/docker/daemon.json` 的 LAN mirror，直连 Docker Hub 导致 `rust:1.97.0-bookworm` 超时/BuildKit ingest 失败。已把 `https://mirror.gcr.io` 置于 daemon `registry-mirrors` 首位并写入 `~/.docker/buildkitd.toml`（保留 `http://192.168.233.184:5000` 为 fallback），`docker pull rust:1.97.0-bookworm` 经 GCR 完成（digest `sha256:8fa55b2f3ddf97471ab6a767bfa3f37e6bad0986ba823e75fea57e2a2a5c3073`）。随后 `BUILDX_BUILDER=default docker compose ... build backend` 使用本机 rust/python 层，在 180s 内写出 `deploy-backend`。单容器 smoke：`/healthz` 200 `{"status":"ok"}`，`/readyz` 200 `{"status":"ok"}`，正文不含 host path。未跑 worker Compose 或 repository conjunction。

## 1. S5 交付

### 1.1 Settings 六组，缺省即失败

`BackendSettings`（`GATEWAY_BACKEND_`）与 `OperationWorkerSettings`（`GATEWAY_BACKEND_OPERATION_WORKER_`）均为 frozen。必填绝对 `control_db_path` / `artifact_root` / `repository_base_url` / `repository_bearer_token_file`。禁止猜测 sibling `artifacts/`。URL 不得嵌入 credentials。`__repr__` 为 `BackendSettings(redacted)` / `OperationWorkerSettings(redacted)`；token 文件 `repr=False`。

数值类字段暴露语义名，默认钉死现有常量，环境改值 fail-closed：

| 组 | env 字段（prefix + 名） | 冻结值 |
| --- | --- | --- |
| control DB | `CONTROL_DB_PATH` | 必填绝对 path |
| artifact root | `ARTIFACT_ROOT` | 必填绝对 path；启动时必须已存在且为可写目录 |
| upload budgets | `UPLOAD_MAX_COMPRESSED_BYTES` 等 | 对齐 `RESOURCE_BUDGETS`：256 MiB / 1024 MiB / 8192 / 1024 / 60s |
| operation admission | `HTTP_NEW_WORK_LIMIT` | 32 |
| cleanup | `CLEANUP_UNPINNED_TTL_SECONDS` / `CLEANUP_SWEEP_BATCH_SIZE` / `CLEANUP_RETRY_BACKOFF_SECONDS` | 86400 / 32 / 1.0 |
| Repository read | `REPOSITORY_BASE_URL` / `REPOSITORY_BEARER_TOKEN_FILE` / `REPOSITORY_TIMEOUT_SECONDS` | URL + 可读非空 secret-file；timeout 30.0 |

Worker 另保留 P4 冻结 lease 预算（`LEASE_DURATION_SECONDS=30` 等，`max_in_flight=1`）。两进程由 Compose 填相同 path/URL/secret，不共享进程内对象。

`/healthz` 现为纯 liveness `{"status":"ok"}`，不回显 host path。

### 1.2 Backend lifespan + `/readyz`

生产 `create_app()`（未注入 `workspace_http`）在 lifespan 中：

1. 解析 settings（失败则进程不起来）
2. 读 secret-file；`validate_artifact_root`；`initialize_and_verify_control_db`（含 `PRAGMA integrity_check` + `foreign_key_check`，错误不泄漏 row）
3. 组装 preview `JobDefinitionRegistry`：必须恰好 resolve `backend-vnext.preview` 的 `materialize_inputs` / `assemble_preview` / `publish_preview` 及 decoder identity
4. `ClosableAdmissionGate` + SQLite workspace facade；注册 5A 路由
5. `/readyz`：完成前 503 `not_ready`；完成后 200 `ok`，不暴露 path/token

注入 `workspace_http` 的 HTTP contract 测试跳过生产 lifespan。Backend **不等** worker。Repository **live ping 不做**。生产 session/scope/baseline 为 fail-closed（无 identity 供给则 401 / `ScopeResolutionError`）。

### 1.3 Worker preview composition

`run()` 使用配置的 `artifact_root`，接入 `preview_composition_bundle` 与 `build_preview_recovery_port`。生产 `repository_provider_factory` 从 secret-file 把 token 留在内存，永不写入 `WorkerEvent`。测试继续注入 fake。空库仍可 READY；未注册/decoder 不匹配的 runnable Operation 仍 FATAL_BLOCK。

架构 allowlist 仅扩到 `gateway_backend.infrastructure.repository_read`。bootstrap 仍禁止 `fastapi` / `uvicorn` / `gateway_repository*` 字符串。未把 `gateway-repository-client` 加入生产闭包。

### 1.4 Admission-first shutdown

SIGTERM/lifespan shutdown **先** `admission_gate.close()`，使创建类 POST 返回已有 `429 ADMISSION_LIMIT_REACHED`。Drain 期间 GET operation / preview-result / bundle、`/healthz`、`/readyz` 仍 200（creation 关闭、read 仍 ready）。不在 HTTP 进程 join worker。Shutdown **不** sweep/unpin protected artifact。

### 1.5 Compose

`vnext/deploy/compose.yaml` 仅 5A 边界：

- backend：`CONTROL_DB_PATH`、`ARTIFACT_ROOT`、Repository URL/timeout、secret 挂载、`backend-control` volume、healthcheck `http://127.0.0.1:8000/readyz`
- worker：同一镜像，`command: python -m gateway_backend.bootstrap.operation_worker`；相同 volume 与 `GATEWAY_BACKEND_OPERATION_WORKER_*`；**无** worker HTTP 端口
- 未改 repository-service 生产 profile；复用已有 `repository-bearer-token` secret

Dockerfile 未改。完整 5A deployment conjunction（backend ∧ worker ∧ repository）未宣称通过。

## 2. 验证

未跑 `./vnext/scripts/run-tests.sh`。阶段 gate 为 backend focused + ruff/mypy。

```text
cd vnext/backend && uv run ruff check . && uv run mypy
  -> All checks passed; mypy 0 errors

cd vnext/backend && uv run pytest -q -m unit
  -> 1725 passed

cd vnext/backend && uv run pytest -q -m 'serial and not parallel_safe' -n 0 \
  tests/test_operation_worker_process.py tests/test_operation_worker_integration.py
  -> 9 passed (9 deselected)

cd vnext/backend && uv run pytest -q \
  tests/test_app.py tests/test_http_admission_shutdown.py \
  tests/test_backend_settings.py tests/test_backend_readiness.py \
  tests/test_architecture.py
  -> 59 passed  (explicit unit markers added to test_app / test_http_admission_shutdown)

docker compose -f vnext/deploy/compose.yaml config
  -> OK
```

测试 owner：

| 行为 | 文件 | marker | 结果 |
| --- | --- | --- | --- |
| settings 六组 fail-closed、冻结值、token 不进 repr | `tests/test_backend_settings.py` | unit | pass |
| `/readyz` 在 settings/integrity/root/registry 完成前为 false | `tests/test_backend_readiness.py` | unit | pass |
| registry mismatch fail-closed | 同上 + worker startup | unit | pass |
| admission 先关、read 仍可用 | `tests/test_http_admission_shutdown.py` | unit | pass |
| worker 注入 preview 后空库 READY；recovery port | worker lifecycle/startup | unit | pass |
| DB reopen + WAL | `test_empty_file_backed_worker_reaches_ready_drains_and_reopens_wal` | integration/serial | pass |
| 进程日志脱敏 | `tests/test_operation_worker_process.py` | serial | pass |
| 架构方向 | `tests/test_architecture.py` | unit | pass |

## 3. Env 名清单

Backend prefix `GATEWAY_BACKEND_`：

- `CONTROL_DB_PATH`（必填）
- `ARTIFACT_ROOT`（必填）
- `REPOSITORY_BASE_URL`（必填）
- `REPOSITORY_BEARER_TOKEN_FILE`（必填）
- `REPOSITORY_TIMEOUT_SECONDS`（冻结 30.0）
- `UPLOAD_MAX_COMPRESSED_BYTES` / `UPLOAD_MAX_EXPANDED_BYTES` / `UPLOAD_MAX_ENTRIES` / `UPLOAD_MAX_PATH_BYTES` / `UPLOAD_STREAM_TIMEOUT_SECONDS`（冻结）
- `HTTP_NEW_WORK_LIMIT`（冻结 32）
- `CLEANUP_UNPINNED_TTL_SECONDS` / `CLEANUP_SWEEP_BATCH_SIZE` / `CLEANUP_RETRY_BACKOFF_SECONDS`（冻结）

Worker prefix `GATEWAY_BACKEND_OPERATION_WORKER_`：

- `CONTROL_DB_PATH` / `ARTIFACT_ROOT` / `REPOSITORY_BASE_URL` / `REPOSITORY_BEARER_TOKEN_FILE` / `REPOSITORY_TIMEOUT_SECONDS`
- P4 冻结 lease 预算：`LEASE_DURATION_SECONDS`、`HEARTBEAT_INTERVAL_SECONDS`、`IDLE_CLAIM_POLL_SECONDS`、`TRANSIENT_BACKOFF_INITIAL_SECONDS`、`TRANSIENT_BACKOFF_MAX_SECONDS`、`STARTUP_RETRY_BUDGET_SECONDS`、`GRACEFUL_DRAIN_TIMEOUT_SECONDS`、`MAX_IN_FLIGHT`、`CLAIM_LIMIT`

Compose 默认 secret 文件仍为 `${GATEWAY_P2R2_BEARER_TOKEN_FILE:-/dev/null}`。空文件会使 settings fail-closed；实际启动必须提供非空 token 文件。这不是降级路径。

## 4. 残余与边界

- 完整 `RepositoryTableAccessProvider` HTTP/Arrow 适配未接线；生产 factory 为 `UnwiredRepositoryTableAccessProvider`（`open_ref` 抛 `RuntimeError`）。S5 只证明 settings + secret-file + 日志不泄漏 token。供 S6 或独立 adapter 工作消化。
- Worker 无 Compose healthcheck；健康证据仍是 `worker_ready` 日志。
- 生产 HTTP identity/scope/baseline 供给为 fail-closed；5A 路由在注入测试 deps 时已覆盖，生产进程需后续 identity 接线才能完成真实 journey。
- S3 HTTP 与 S4 Preview JobDefinition 源码仍未提交；无独立 S3/S4 handoff 文件。S5 以源码为准，未把 S3/S4 行为修进本阶段。
- TTL/capacity 数值仍属设计 deferred；settings 改冻结值 fail-closed。
- 未宣称 backend ∧ worker ∧ repository 同树容器 conjunction。
- 未 git commit。
- 未改 P4 lease/CAS/drain 超时合同。
- `/readyz` 不是跨进程 worker 探测。
- backend image 已按本脏树重建（`deploy-backend` / `sha256:83a81cf1...`）并通过 `/healthz`+`/readyz` smoke。worker Compose `worker_ready` 与 backend∧worker∧repository conjunction 仍未跑，不得写成完整 deployment PASSED。

## 5. Handoff boundary

S6 independent acceptance 是命名下一步，本文件不授权。S6 必须携带本 dirty-tree `validated_source_tree`、重建后的 image digest，以及 S3/S4 未提交这一事实。任何把 live Repository adapter、新 principal、第二 registry 或 worker HTTP side channel 扩进生产路径的改动，必须先 reopen owning contract。
