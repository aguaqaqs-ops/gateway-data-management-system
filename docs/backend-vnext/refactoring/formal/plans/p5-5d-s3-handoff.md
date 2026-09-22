# P5-5D-S3 Public API, Production Composition and Deployment Inputs Handoff

状态：**S3 round-4 remediation complete — delivery_recommendation: pass_recommended（不签 stage exit / slice exit）**

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
closure_verification: docs/backend-vnext/refactoring/formal/plans/p5-5d-s3-closure-verification.md
baseline_commit: 2233e80cc1b8e1288acf1ed9785c6b84093f67ce
implementation_candidate_head: d61d37be97821f303e9083abe739618cebd96b46
evidence_delivery: delivered_by_round4_review_remediation_commit
candidate_binding_note: bind to round-4 review F1 harness commit (in-history); do not record amend-replaced SHAs
workspace_schema_version: 5
uv_lock_in_diff: no
candidate_binding: independent_review_uses_git_head_at_review_time
next_step: P5-5D-S3-re-review
```

## Round-4 remediation summary (P2-1, P2-2)

| Finding | Fix |
| --- | --- |
| P2-1 深层 JSON `RecursionError` → 500 | `ArchiveRequestBodyLimitMiddleware` 捕获 `RecursionError` → **422**；`test_archive_post_rejects_deeply_nested_json_with_422` |
| P2-2 Compose main ref 屏障 | 前置 `main_after_both != main_after_a`；观察窗口 `main_after_archive == main_before_archive`（全程经 HTTP `refs/main`） |

### RecursionError 修前证据

修复前：payload `b'[' * 50000 + b'0' + b']' * 50000`（100001 bytes < 256 KiB）POST `/v1/archive-plan-preview` → **500**。修复后 → **422** `REQUEST_VALIDATION_FAILED`。

## Round-4 review remediation (F1)

| Finding | Fix |
| --- | --- |
| F1 compose gate root dolt 污染 | `list_repository_commit_ids` 改 `docker compose exec -u gateway`；删除 `resolve_main_commit_id` dolt 回退；main ref 观测全程 HTTP |

先前「归档后 refs/main 持续 503」归因不成立：503 由 harness 以 root 在容器内执行 `dolt`、污染 `.dolt/**` 属主所致，与 Archive 无关。

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

### Known differences / deferred

- 中间件短路 413/422 响应不含 FastAPI 校验错误的 `details` 子结构（已知差异，成本未扩）。
- 请求体读取超时（slowloris）未实现；待 design 决策。
- compose gate 在 repository-service 容器内执行 `dolt` 时必须以服务用户 `gateway` 运行（`exec -u gateway`），避免 root 写入污染 `.dolt/**` 导致后续 `refs/main` **503**。

## Scope delivered

### HTTP layer

- `vnext/backend/src/gateway_backend/http/schemas/archive.py` — Design §8.1 DTOs
- `vnext/backend/src/gateway_backend/http/orchestration/archive.py` — seven operations
- `vnext/backend/src/gateway_backend/http/routes/archives.py` — seven routes
- `vnext/backend/src/gateway_backend/http/dependencies.py` — `ArchiveRequestBodyLimitMiddleware`（断连安全；`RecursionError`→422）

### Repository hygiene

- `.gitignore` — ignore `vnext/backend/tests/support/.last_compose_gate_provenance.json`（compose gate 运行产物，非交付源码）

### Modified HTTP / wiring

- `vnext/backend/src/gateway_backend/app.py` — middleware 注册于 `create_app()`
- `vnext/backend/src/gateway_backend/http/wiring.py` — archive router + OpenAPI paths
- `vnext/backend/src/gateway_backend/http/errors.py` — stable_code mapping

### Tests / fixture changes（Plan §3 披露）

| 文件 | 改动 |
| --- | --- |
| `tests/test_archive_http.py` | 断连中间件用例；R1/R2/R3；七响应泄漏扫描；深层 JSON RecursionError→422 |
| `tests/support/compose_gate_harness.py` | provenance helper；`list_repository_commit_ids` 以 `gateway` 用户 exec；`resolve_main_commit_id` 仅 HTTP |
| `tests/test_archive_compose_e2e.py` | 双 actor main ref 屏障；零 Repository effect main 直接断言 |

## Invariants delivered

- Invalid Archive input → **422**；body >256 KiB → **413**；duplicate JSON key → **422**
- 极深嵌套 JSON 触发 `RecursionError` → **422**（非 500）
- 客户端断连时中间件立即返回，不阻塞事件循环
- Start idempotency-key 跨 actor 重放 → **200**，`archived_by` 保持首次 actor（confirmation 同 key 仍 **409**）
- `ARCHIVE_SCOPE_LIMIT_EXCEEDED` HTTP **409**，无部分 `candidates` 列表
- HTTP 七响应 `ARCHIVE_FORBIDDEN_RESPONSE_SUBSTRINGS` 扫描
- Archive Start 零 Repository effect（compose 观察窗口：commit 集合不变 + **main ref 不变**）
- 双 actor 旅程：B 审批后 `main_after_both != main_after_a`（B 为当前技术 main）

## Focused gate (E1)

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
# => 137 passed, 1 warning
```

## Container / image gate (E2)

```yaml
container_rebuild_required: yes
container_reason: round-4 middleware src change
compose_project_name: gateway-p5-5d-s3-round4-gate
prebuilt_used: no
```

```bash
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-s3-round4-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
# => 6 passed, 0 skipped
```

## Provenance record (§6.3, round-4 conjunction)

统一 recipe（path + tab + file sha256，树级再 sha256sum）：

```bash
cd <repo-root> && git ls-files 'vnext/**' | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum

cd vnext/backend/src && find . -name '*.py' -type f | LC_ALL=C sort | \
  while read -r p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" | cut -d' ' -f1)"; done | sha256sum
```

| 证据 | 值 |
| --- | --- |
| Implementation binding commit | `d61d37be97821f303e9083abe739618cebd96b46`（round-4 review F1 harness；在历史中可 `git cat-file`） |
| `vnext/**` tree status | clean at implementation binding |
| Source-tree file count | 905 |
| Source-tree digest | `c21785c370568befd0c24517c190c003bde7b0ef1efcfc4fb6f97b68c0e24c15` |
| Backend `src` py digest（`path\tsha256` recipe，local == image） | `b37e8b3ec48fad1144505a6756e79ae33f71cfeb8c3356f4f2a4c85e235f6285` |
| uv.lock SHA (backend) | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| uv.lock SHA (repository_service) | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| uv.lock SHA (repository_client) | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| uv.lock SHA (repository_contracts) | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| uv.lock SHA (shared_kernel) | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| compose.yaml SHA-256 | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| repository-service | `sha256:6709828c4188c5eb8b41384463eef7baa8d1727d4fc75b9042c4aaa91d644b41`（container `2ec32cd101cc`） |
| backend | `sha256:81e1d5919f4e565ebae8b5f5e4e21807d7aadc0afd3fb3d1cd8ea00af48ff116`（container `316f7ca74562`） |
| worker | `sha256:337cde10a3296a8c3f16e12c1917b967f06edc90087b6fd1b65dde7d725daf36`（container `44aa70680cb8`） |
| Running container provenance | `vnext/backend/tests/support/.last_compose_gate_provenance.json` |
| `org.opencontainers.image.revision` (backend/worker) | 空（py digest 对等补偿） |

Superseded：`4f2b69fd…` source-tree digest（round-4 初版含 dolt 回退，非 review F1 最终候选）；`6006d443…`（round-3）。

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
