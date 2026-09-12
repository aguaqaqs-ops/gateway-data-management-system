# P5-5A S6 Handoff: Slice Acceptance

状态：**PASS — 5A slice functional acceptance 闭合；container gate deferred（rebuild 环境阻塞）**

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
  rebuild_result: failed_rust_lang_network_unreachable_in_docker_build
  image_revision: null_for_current_head
  last_verified_image_revision: sha256:7a8e2834e67f0131092b575e8ce11c0d02dcdcee219699ee5d22d07629d18faf
  status: deferred_rebuild_blocked
  conjunction: not_run_rebuild_prerequisite
deferred_touched:
  - current_head_container_rebuild
  - backend_worker_repository_compose_conjunction
  - worker_compose_http_healthcheck
  - repository_service_compose_e2e_env_failures
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

### 3.1 重建尝试

```bash
cd vnext/deploy && docker compose build backend
```

**失败**：builder 阶段 `gateway-compute-python` maturin 构建需访问 `static.rust-lang.org`，
Docker build 网络不可达（`Network is unreachable`）。`GATEWAY_DOCKER_BUILD_NETWORK=host` 重试同样失败。

### 3.2 状态

| 项 | 值 |
| --- | --- |
| current_source_tree | `sha256:68682f21...`（implementation HEAD `33bf0fb9`；docs-only `71773296` 未改源码） |
| last_verified_image | `sha256:7a8e2834...`（`218d4a24`）；**historical** |
| container_gate | **deferred_rebuild_blocked** |
| conjunction | 未运行（rebuild 前置未满足） |

历史 P4 image 不得作为 current-HEAD 证据（见 remediation review §3）。

### 3.3 恢复条件

网络可达后执行：

```bash
cd vnext/deploy
GATEWAY_P2R2_BEARER_TOKEN_FILE=<token> \
GATEWAY_BACKEND_SESSION_FILE=./config/session.json \
docker compose build backend
# smoke: /healthz + /readyz
# optional: backend ∧ worker ∧ repository conjunction
```

## 4. S1–S5 证据摘要

| 阶段 | commit | 状态 |
| --- | --- | --- |
| S1 domain/application | `6532a6eb` | pass |
| S2 persistence/ArtifactStore | `774bacb6` | pass |
| S3–S5 HTTP/JobDefinition/runtime | `18e7155a` | pass |
| Remediation | `218d4a24`, `dd1c8c4d`, `33bf0fb9` | pass |
| S5 handoff | [p5-5a-s5-handoff.md](p5-5a-s5-handoff.md) | **superseded** |

## 5. Deferred register

- current-HEAD backend image rebuild + smoke
- backend ∧ worker ∧ repository Compose conjunction
- worker HTTP healthcheck / `worker_ready` 日志证据
- repository_service Dockerfile lock SHA256 漂移修复（P2/P4 owner）
- TTL/capacity 数值、History pagination、5B+ DTO

## 6. Authority

- `p5_5a_slice_exit`: **pass**
- `hold`: **released**
- `p4_r6_exit`: 仍 **pending**（5A slice exit 不替代 P4-R6）
- `p5_5b_design_s0_authorized`: **no**
