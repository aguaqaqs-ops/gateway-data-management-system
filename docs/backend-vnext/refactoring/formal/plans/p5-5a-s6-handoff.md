# P5-5A S6 Handoff: Slice Acceptance

状态：**PASS — 5A slice functional acceptance 闭合；container gate 已闭合（current-HEAD 重建 + smoke + conjunction 通过）**

日期：2026-09-12

Owner：Architecture Acceptance

上游：[P5-5A Remediation Review](p5-5a-remediation-review.md)、
[P5-5A Upload/Preview Execution Plan](p5-5a-upload-preview-execution-plan.md) S6、
HEAD `71773296`（implementation `33bf0fb9` + remediation docs）。

```yaml
stage: S6
candidate_head: 717732962c59863f6472252e94c8430a02b148a7
implementation_head: 33bf0fb9bf09a93b0bcff7ae04c0ad73b218eddf
conversation_context: independent_acceptance
scope_paths:
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s6-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-remediation-review.md
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/README.md
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-s6-handoff.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-execution-plan.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5a-remediation-review.md
  - docs/backend-vnext/refactoring/formal/README.md
  - docs/backend-vnext/README.md
contract_owners:
  - Workspace Domain -> exact scope, OPEN uniqueness, generation CAS
  - Upload Application + ArtifactStore -> role closure, streaming, protection
  - Preview Application -> frozen binding, stale, supersede/cancel
  - JobDefinition owner -> materialize_inputs/assemble_preview/publish_preview
  - HTTP Interface -> DTO separation, re-authorization, status families
  - Bootstrap/deployment -> settings fail-closed, /readyz, admission shutdown
tests:
  authoritative_runner: partial_pass_5a_scope
  shared_kernel: pass_242
  repository_contracts: pass_152
  repository_client: pass_154
  backend_all: pass_1876
  backend_unit: pass_1761
  backend_integration: pass_127
  backend_serial: pass_15
  repository_service_parallel: fail_5_env_out_of_5a_scope
  repository_service_serial: fail_8_compose_e2e_env
  five_package_static: pass_ruff_mypy_all_packages
review:
  independent: yes
  findings: []
  remediation_retest: pass_via_p5-5a-remediation-review
container:
  required: yes
  rebuild_attempted: yes
  rebuild_result: pass_2026-09-12_after_rustup_toolchain_pin
  image_revision: sha256:52666754dfab4fd2a17dbb84d3179ca15d34fefebca0403a3fdc64e8ee17a6fd
  worker_image_revision: sha256:f90a6361b1028fa2540ff1f7f3fb278672a8aabcf7e18b13b306870822ea93ea
  repository_service_image_revision: sha256:26092bd5a7e86d20675286d79e863a99c974718c3e25a265a058e240d2c6c966
  last_verified_image_revision: sha256:7a8e2834e67f0131092b575e8ce11c0d02dcdcee219699ee5d22d07629d18faf
  last_verified_image_scope: historical_218d4a24_not_current_head
  image_source: backend_src_tests_at_33bf0fb9_plus_builder_rustup_toolchain_pin_in_this_closure
  status: pass
  conjunction: pass_backend_worker_repository
  smoke: pass_healthz_200_readyz_200_logs_redacted_worker_ready
deferred_touched:
  - repository_service_compose_e2e_env_failures
  - deploy_compose_build_network_wiring
  - lxc_v6_default_route_dead_path
reopen_required: false
decision: pass
hold: released
p5_5a_slice_exit: pass
p5_5b_design_s0_authorized: no
next_step: P5-5B-S0-entry-brief
next_step_authorized: no
validated_source_tree: sha256:68682f21bff051de42908d5c84b019a525054bff535436051cf4c99b0636104a
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
source_tree_file_count: 308
compose_yaml_sha256: sha256:113224e1ba968ed2ce588640d7fb07c7f8f2bb10ce136dd444f314dbe6591c81
```

## 1. Findings-first acceptance（设计 §9）

| 验收项 | 结论 | 证据 |
| --- | --- | --- |
| Upload/Preview 命令与 identity 分离 | pass | `test_upload_application.py`, `test_preview_application.py`, HTTP contract tests |
| FULL / MODIFIED_ONLY 映射 | pass | `test_preview_job_*.py` |
| immutable/CAS / generation | pass | `test_sqlite_workspace_repository.py`, `test_workspace_domain.py` |
| supersede / cancel / stale | pass | `test_preview_job_publish.py`, remediation fixes `218d4a24`–`33bf0fb9` |
| 每次 read 重新授权 | pass | `test_http_auth_matrix.py`, `test_live_session.py` |
| ArtifactStore protection | pass | `test_workspace_artifact_store.py`, protection transfer tests |
| readiness / admission shutdown | pass | `test_backend_readiness.py`, `test_http_admission_shutdown.py` |
| 无 forbidden mechanism 扩展 | pass | `test_architecture.py`；无 Repository write/outbox/dynamic DAG |

独立 findings-first review：**无新增 finding**。Remediation review 已闭合（见
[p5-5a-remediation-review.md](p5-5a-remediation-review.md)）。

## 2. 测试矩阵

### 2.1 权威 runner

```bash
./vnext/scripts/run-tests.sh
```

| 包 | 结果 | 说明 |
| --- | --- | --- |
| shared_kernel | 242 passed | pass |
| repository_contracts | 152 passed | pass |
| repository_client | 154 passed | pass |
| backend | 1876 passed | pass；5A owner scope |
| repository_service (parallel) | 1643 passed, **5 failed** | 环境/锁文件漂移；**非 5A slice owner** |
| repository_service (serial) | 193 passed, **8 failed** | Compose e2e 需 Docker 镜像 provenance；**非 5A blocker** |

repository_service 失败项：

- `test_dockerfile_uv_lock_sha256_matches_lockfile` — Dockerfile `UV_LOCK_SHA256` 与 lockfile 漂移
- `test_import_isolation_in_isolated_environments` ×3 — offline uv cache 缺包
- Compose e2e ×8 — `ensure_repository_service_image()` / worktree provenance

### 2.2 Backend focused（5A owner）

```bash
cd vnext/backend
uv run pytest -q -m unit          # 1761 passed
uv run pytest -q -m integration   # 127 passed
uv run pytest -q -m 'serial and not parallel_safe'  # 15 passed
```

五包 `ruff check` + `mypy`：**全部通过**（backend 308 files）。

## 3. Container provenance

### 3.1 初次重建尝试（失败）

```bash
cd vnext/deploy && docker compose build backend
```

**失败**：builder 阶段 `gateway-compute-python` maturin 构建需访问 `static.rust-lang.org`
（toolchain manifest / 缺失 component），BuildKit 构建容器内
`tcp connect error: Network is unreachable (os error 101)`。`GATEWAY_DOCKER_BUILD_NETWORK=host`
重试**为空操作**（见 §3.2 第 3 条），实际仍走默认网络。

### 3.2 根因（2026-09-12 排查）

1. **BuildKit 沙箱 v6 路径死亡**：三个沙箱探针（`pve-registry-http` 节点默认网络、BuildKit
   `--network=host`、`default` docker-driver）结果一致：IPv4 出站正常
   （`static.rust-lang.org` HTTP 200、`static.crates.io` 可达，均为 ~2s），IPv6 内核存在默认路由
   条目但实际不可达（立即失败）。`os error 101 (EUNRCH)` 正是 v6 路由死条目下的立即错误；
   任何 v6 优先且 v4 回退不可靠的客户端都会以该错误终止。宿主 v4 出站正常
   （`curl static.rust-lang.org` 200）。
2. **builder 冷构建硬依赖 `static.rust-lang.org`**：`vnext/rust/rust-toolchain.toml`
   （channel `1.97.0` / profile `minimal` / `rustfmt`,`clippy`）要求 rustup 对基座镜像
   `rust:1.97.0-bookworm` 预装 full-profile toolchain 执行 manifest 同步 + 补装缺失 component。
   这是全构建唯一触达该域名的步骤；其余网络步骤（PyPI / astral.sh）走 v4 正常。
3. **文档化重试路径未接线**：`GATEWAY_DOCKER_BUILD_NETWORK` 仅被 repository_service 测试
   harness（`compose_lifecycle_harness.py`）消费；deploy/compose.yaml 的 `build:` 未接任何
   network 字段，`docker compose build` 不读取该变量 —— “host” 重试从未生效。
   `BUILDX_BUILDER=default` 只是切换到另一个（更冷）缓存的 builder，不改变网络。
4. **S5 当时能建**：当时构建容器 v4 出站健康、rustup 同步经 v4 完成，且多数层级 warm cache；
   S6 失败 = 冷跑的 rustup 步骤遭遇 v6 优先故障 + 重试网络参数空操作叠加。

### 3.3 修复

- `vnext/backend/Dockerfile` builder 阶段（`uv python install` 之后、`uv sync` 之前）新增：

  ```dockerfile
  ARG RUSTUP_TOOLCHAIN=1.97.0
  ENV RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN}
  ```

  环境变量优先于 `rust-toolchain.toml`，toolchain 固定为基座镜像预装版本，构建期不再触发
  rustup 网络同步。探针验证：pin 下 `cargo metadata` 0.13s 完成、零 syncing/downloading；
  本次重建 maturin `--release` 步骤 9.4s、全构建 112s 通过。
- 其余 RUN egress（PyPI / astral.sh）v4 验证可达，**无需** host 网络或 mirror 变更；
  `compose.yaml` 未改动（sha256 保持 `113224e1...`）。
- **Residual（记入 deferred，不阻塞）**：LXC 存在死亡 v6 默认路由，v6 优先客户端仍有同类失败
  风险（环境层修复）；deploy compose 构建网络未接 `GATEWAY_DOCKER_BUILD_NETWORK`
  （deploy hygiene，后续轮次接线）。

### 3.4 current-HEAD 重建通过验证（2026-09-12）

worktree clean @ `b82e449b`，`git diff 33bf0fb9..b82e449b -- vnext/backend` 为空
（src/tests 与 implementation HEAD 逐字节一致，308 py files）；重建命令：

```bash
cd vnext/deploy
docker compose build backend worker
```

| 项 | 值 |
| --- | --- |
| current_source_tree | `sha256:68682f21...`（308 py files；identity 见 §3.4 命令段） |
| backend image（current-HEAD） | `sha256:52666754dfab4fd2a17dbb84d3179ca15d34fefebca0403a3fdc64e8ee17a6fd`（tag `deploy-backend`） |
| worker image（current-HEAD） | `sha256:f90a6361b1028fa2540ff1f7f3fb278672a8aabcf7e18b13b306870822ea93ea`（tag `deploy-worker`） |
| repository-service image | `sha256:26092bd5...`（既有本地 image，非本轮 5A 重建范围） |
| historical image | `sha256:7a8e2834...`（`218d4a24`）；**不得**作为 current-HEAD 证据 |
| compose.yaml sha256 | `113224e1...`（未改动，与记录一致） |
| image src 对照 | 镜像 `/app/backend/src` == worktree `vnext/backend/src`（178 py files，零差异） |
| container_gate | **pass** |

smoke（`docker compose up -d`：backend ∧ worker ∧ repository-service；token/session 用本地
dev fixture，`config/session.json`）：

- `/healthz` 200 `{"status":"ok"}`；`/readyz` 200 `{"status":"ok"}`
- backend / worker 日志无 host path、无 bearer token（grep 计数 0）
- worker 日志 `operation_worker_event code=worker_ready worker_id=worker-ad58ee86-3e70-4d9e-b2af-aec0388e3172`
- 三服务 up；backend 与 repository-service `healthy`；worker 以 `worker_ready` 日志判定
  （无 HTTP 端口）→ conjunction 闭合，smoke 后 `docker compose down`

## 4. S1–S5 证据摘要

| 阶段 | commit | 状态 |
| --- | --- | --- |
| S1 domain/application | `6532a6eb` | pass |
| S2 persistence/ArtifactStore | `774bacb6` | pass |
| S3–S5 HTTP/JobDefinition/runtime | `18e7155a` | pass |
| Remediation | `218d4a24`, `dd1c8c4d`, `33bf0fb9` | pass |
| S5 handoff | [p5-5a-s5-handoff.md](p5-5a-s5-handoff.md) | **superseded** |

## 5. Deferred register

- ~~current-HEAD backend image rebuild + smoke~~（闭合，见 §3.4）
- ~~backend ∧ worker ∧ repository Compose conjunction~~（闭合，见 §3.4）
- ~~worker `worker_ready` 日志证据~~（闭合，见 §3.4；worker 无 HTTP healthcheck，维持日志判定）
- repository_service Dockerfile lock SHA256 漂移修复（P2/P4 owner）
- deploy compose 构建网络接线（`GATEWAY_DOCKER_BUILD_NETWORK` 未接 deploy/compose.yaml；非阻塞）
- LXC v6 默认路由死亡路径（环境层；非阻塞）
- TTL/capacity 数值、History pagination、5B+ DTO

## 6. Authority

- `p5_5a_slice_exit`: **pass**
- `hold`: **released**
- `p4_r6_exit`: 仍 **pending**（5A slice exit 不替代 P4-R6）
- `p5_5b_design_s0_authorized`: **no**
