# P5-5D-S3 Public API, Production Composition and Deployment Inputs Handoff

状态：**S3 re-review remediation complete — delivery_recommendation: pass_recommended（不签 stage exit / slice exit）**

日期：2026-09-22

Owner：Backend Archive HTTP / Deployment

## Authority gate snapshot

```yaml
p5_5d_s1_stage_exit: pass
p5_5d_s2_stage_exit: pass
p5_5d_design: accepted
p5_5d_implementation_authorized: yes
source_or_test_change_authorized: true
unresolved_contract_drift: none
repository_effect_authorized: false
production_deployment_authorized: false
p5_5d_s3_stage_exit: not_evaluated
p5_5d_slice_exit: not_evaluated
```

## Traceability

```yaml
stage: P5-5D-S3-public-api-production-composition-and-deployment-inputs
parent_plan: docs/backend-vnext/refactoring/formal/plans/p5-5d-archive-execution-plan.md
remediation_work_order: docs/backend-vnext/refactoring/formal/plans/p5-5d-s3-remediation-work-order.md
independent_review: docs/backend-vnext/refactoring/formal/plans/p5-5d-s3-independent-review.md
re_review: docs/backend-vnext/refactoring/formal/plans/p5-5d-s3-re-review.md
baseline_commit: 2233e80cc1b8e1288acf1ed9785c6b84093f67ce
implementation_candidate_head: b9924be4da075fd99bd18d67f5e9fe50314151d5
evidence_delivery: delivered_by_re_review_remediation_commit
workspace_schema_version: 5
uv_lock_in_diff: no
candidate_binding: independent_review_uses_git_head_at_review_time
next_step: P5-5D-S3-re-review
```

## Re-review remediation summary (R1–R9)

| Finding | Fix |
| --- | --- |
| R-1 中间件断连死循环 | `ArchiveRequestBodyLimitMiddleware`：`http.disconnect` 等非 `http.request` 立即 `return`；`test_archive_body_middleware_returns_on_client_disconnect` |
| R-2 provenance digest | 统一 `path\tsha256` recipe 在最终候选重算（见 §Provenance） |
| R-3 Plan §4 残留 | execution plan §4 S3 与 §1 authority 对齐 |
| R-4 泄漏扫描 | `test_archive_responses_do_not_leak_internal_fields` 扩至 **7** 响应 |
| R-4.3 非 string 边界 | `ARCHIVE_HTTP_NON_STRING_FIELD_CASES`（reason / expected_sequence） |
| R-4.4 Start 跨 actor 重放 | `test_archive_cross_actor_start_idempotency_replay_preserves_accepted_by` |
| R-2 scope limit HTTP | `test_archive_list_candidates_returns_scope_limit_exceeded_without_partial_list` |
| R-5 容器 immutable ID | `capture_running_container_provenance` 用 `docker inspect`；落盘 `tests/support/.last_compose_gate_provenance.json` |

### Middleware 断连用例修前证据

修复前（`continue` 分支）：`test_archive_body_middleware_returns_on_client_disconnect` 在 5s 内线程未退出（`thread.is_alive()`），`receive()` 调用次数远超 3。修复后同用例通过。

### Cross-scope 可失败性实验（不提交）

临时禁用 `queries.py` `get_archive_result` scope 过滤后，`test_archive_get_result_hides_cross_scope_result_same_database` 由 404 变为 200；恢复后通过。

### Known differences / deferred

- 中间件短路 413/422 响应不含 FastAPI 校验错误的 `details` 子结构（已知差异，成本未扩）。
- 请求体读取超时（slowloris）未实现；待 design 决策。

## Scope delivered

### HTTP layer

- `vnext/backend/src/gateway_backend/http/schemas/archive.py` — Design §8.1 DTOs
- `vnext/backend/src/gateway_backend/http/orchestration/archive.py` — seven operations
- `vnext/backend/src/gateway_backend/http/routes/archives.py` — seven routes
- `vnext/backend/src/gateway_backend/http/dependencies.py` — `ArchiveRequestBodyLimitMiddleware`（断连安全）

### Modified HTTP / wiring

- `vnext/backend/src/gateway_backend/app.py` — middleware 注册于 `create_app()`
- `vnext/backend/src/gateway_backend/http/wiring.py` — archive router + OpenAPI paths
- `vnext/backend/src/gateway_backend/http/errors.py` — stable_code mapping

### Tests / fixture changes（Plan §3 披露）

| 文件 | 改动 |
| --- | --- |
| `tests/test_archive_http.py` | 断连中间件用例；R1/R2/R3；七响应泄漏扫描 |
| `tests/support/compose_gate_harness.py` | `capture_running_container_provenance` → immutable image ID；`persist_compose_gate_provenance`；`assert_running_backend_worker_images_match_build` |
| `tests/test_archive_compose_e2e.py` | 调用上述 provenance helper；落盘固定路径 |

## Invariants delivered

- Invalid Archive input → **422**；body >256 KiB → **413**；duplicate JSON key → **422**
- 客户端断连时中间件立即返回，不阻塞事件循环
- Start idempotency-key 跨 actor 重放 → **200**，`archived_by` 保持首次 actor（confirmation 同 key 仍 **409**）
- `ARCHIVE_SCOPE_LIMIT_EXCEEDED` HTTP **409**，无部分 `candidates` 列表
- HTTP 七响应 `ARCHIVE_FORBIDDEN_RESPONSE_SUBSTRINGS` 扫描
- Archive Start 零 Repository effect（compose 观察窗口）

## Focused gate (E1)

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
# => 136 passed, 1 warning
```

## Container / image gate (E2)

```yaml
container_rebuild_required: yes
container_reason: T0 middleware src change
compose_project_name: gateway-p5-5d-s3-rereview-gate
prebuilt_used: no
```

```bash
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-s3-rereview-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
# => 6 passed, 0 skipped
```

## Provenance record (§6.3, re-review conjunction)

统一 recipe（path + tab + file sha256，树级再 sha256sum）：

```bash
cd <repo-root> && git ls-files 'vnext/**' | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum

cd vnext/backend/src && find . -name '*.py' -type f | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum
```

| 证据 | 值 |
| --- | --- |
| Git HEAD | `b9924be4da075fd99bd18d67f5e9fe50314151d5` |
| `vnext/**` tree status | clean |
| Source-tree file count | 905 |
| Source-tree digest | `6006d443268f51a6474cca28357da0dd81e8c4a2ddebe73f86e1d17293def985` |
| Backend `src` py digest（`path\tsha256` recipe，local == image） | `12ecd51e624f23f56bba048044cd6424018d716a13569f227b9abce6f74324e0` |
| uv.lock SHA (backend) | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| uv.lock SHA (repository_service) | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| uv.lock SHA (repository_client) | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| uv.lock SHA (repository_contracts) | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| uv.lock SHA (shared_kernel) | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| compose.yaml SHA-256 | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| repository-service | `sha256:70c25d76bb1abd9a24e73558c91d66e99980cee49d3f55a5e2ea50b936eb7487`（container `ce20642abf90`） |
| backend | `sha256:51ef519dd6a8f2ebabaf64c1529a65b667c936b91f972e53e99718b310d07888`（container `8b994c3aa493`） |
| worker | `sha256:6e88dd57d5839e6e872858d5aa623c1bd82b340d34dfcf73b854f0ee67d354d2`（container `62987f7edc96`） |
| Running container provenance | `vnext/backend/tests/support/.last_compose_gate_provenance.json` |
| `org.opencontainers.image.revision` (backend/worker) | 空（py digest 对等补偿） |

Superseded：`a963b15a…` source-tree digest（中间态，非最终候选）。

## Forbidden imports

None.

## Independent countersign

```yaml
delivery_recommendation: pass_recommended
review: pending
p5_5d_s3_stage_exit: not_evaluated
next_step: P5-5D-S3-re-review
slice_exit: not_signed_by_delivery
```

Delivery 不代签 `p5_5d_s3_stage_exit`、`p5_5d_slice_exit` 或 `production_deployment_authorized`。
