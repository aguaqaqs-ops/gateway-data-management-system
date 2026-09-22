# P5-5D-S3 Public API, Production Composition and Deployment Inputs Handoff

状态：**S3 remediation complete — pass_recommended（不签 stage exit / slice exit）**

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
baseline_commit: 6a27565b55342cdab9e3c137664fb7ca330f9a89
implementation_candidate_head: introduced_by_this_commit
evidence_delivery: delivered_by_remediation_commit
workspace_schema_version: 5
uv_lock_in_diff: no
candidate_binding: independent_review_uses_git_head_at_review_time
next_step: P5-5D-S4
```

## Remediation summary (P1–P3)

| Finding | Fix |
| --- | --- |
| P1-1 校验 500→422 | `ArchiveRequestValidation`；contracts/queries/schemas/routes 收口；`test_archive_http.py` 参数表 + 409/429/replay |
| P1-2 双 actor Compose | `test_archive_compose_e2e.py` 双 submission 旅程；helper 迁入 `compose_gate_harness.py` |
| P1-3 跨 scope | 同 DB + `OTHER_SCOPE_BEARER` mapping；同 scope 跨 actor 可读 200 |
| P1-4 authority | 本 handoff 与 execution plan 回退 delivery 自签 `pass` |
| P2-1/P2-2 body/dup key | `ArchiveRequestBodyLimitMiddleware`（256 KiB + duplicate JSON key） |
| P2-3 稳定码分工 | 保留 append/Start 现有 `ARCHIVE_AUDIT_VERSION_CONFLICT` / `CANDIDATE_SET_CONFLICT` 分工，测试固定断言 |
| P2-6 provenance | 见下文 §Provenance（fresh build + conjunction 重采） |
| P2-7 handoff 数字 | `test_production_wiring.py` **19 passed**；零 Repository effect 仅 compose 观察窗口证明 |
| P3 清单 | 死代码删除、disposition Literal、OpenAPI 字面量基线、job registry 精确集合、泄漏扫描、session.json/extra=forbid |

### Cross-scope 可失败性实验（不提交）

临时禁用 `queries.py` `get_archive_result` scope 过滤（`plan.repository_id != fresh_scope.repository_id` 分支）后，
`test_archive_get_result_hides_cross_scope_result_same_database` 由 404 变为 200；恢复过滤后通过。证明用例绑定生产 scope 路径。

## Scope delivered

### New HTTP layer

- `vnext/backend/src/gateway_backend/http/schemas/archive.py` — Design §8.1 DTOs, `extra=forbid`, disposition `Literal`
- `vnext/backend/src/gateway_backend/http/orchestration/archive.py` — seven operations, idempotency
- `vnext/backend/src/gateway_backend/http/routes/archives.py` — seven Archive routes + bounded audit-events query
- `vnext/backend/src/gateway_backend/http/dependencies.py` — `ArchiveRequestBodyLimitMiddleware`

### Modified HTTP / wiring

- `vnext/backend/src/gateway_backend/http/app.py` — middleware 注册于 `create_app()`
- `vnext/backend/src/gateway_backend/http/wiring.py` — `include_router(archives_router)`; `PRODUCTION_OPENAPI_PATHS` +7
- `vnext/backend/src/gateway_backend/http/errors.py` — `ArchiveApplicationError` stable_code → 409/404

### Application

- `vnext/backend/src/gateway_backend/application/archive/errors.py` — `ArchiveRequestValidation`
- `vnext/backend/src/gateway_backend/application/archive/contracts.py` — caller validators → `ArchiveRequestValidation`
- `vnext/backend/src/gateway_backend/application/archive/queries.py` — `limit`/`subject_kind` 校验；`disposition` Literal

### Tests

- `vnext/backend/tests/test_archive_http.py` — contract owner (**50 passed**)
- `vnext/backend/tests/test_archive_compose_e2e.py` — dual-actor compose journey (**1 passed**)
- `vnext/backend/tests/support/compose_gate_harness.py` — shared stack/journey helpers + provenance capture
- Updated: `test_http_openapi.py`, `test_http_auth_matrix.py`, `test_production_wiring.py`, compose e2e imports

### Routes registered (production OpenAPI)

| Method | Path |
| --- | --- |
| GET | `/v1/archive-candidates` |
| POST | `/v1/archive-plan-preview` |
| POST | `/v1/archive-confirmations` |
| POST | `/v1/archive-anomaly-resolutions` |
| GET | `/v1/archive-audit-events` |
| POST | `/v1/archives` |
| GET | `/v1/archives/{archive_result_id}` |

Worker job registry: **no** Archive job added; keys == `preview ∪ submit`（`test_production_wiring.py`）。

## Invariants delivered

- All seven Design §8 routes on production factory via `register_workspace_http`
- `archive_submission` permission independent of review/submit
- Write routes wrapped in `acquire_new_work`; Preview/candidates/audit-events/result reads do not
- Invalid Archive input → **422** `REQUEST_VALIDATION_FAILED`（非 500）
- Request body >256 KiB → **413**；duplicate JSON key → **422**
- Preview read-only：`assert_archive_durable_state_unchanged` / disposition 计数
- Archive Start **零 Repository effect**：compose 观察窗口（commit 集合不变 + 无新增 Archive operation）
- HTTP responses 不泄漏 `repository_id`、internal paths、raw SQL（七响应 forbidden 字段表）
- Dual-sibling：`APPROVED_SIBLING_EXCLUDED`、disposition、Head CAS — HTTP fixture + compose dual-actor

## Compose dual-actor journey

`test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect`：

1. Actor-1 journey → approve A；Actor-2（`REVIEWER_TOKEN`, `journey_key_prefix=compose-b`）→ approve B
2. 2 candidates；preview `APPROVED_SIBLING_EXCLUDED`；confirm + resolution；`can_start`；Start dispositions/releases/Head
3. 观察窗口：commit 集合 + operation 计数不变 → Archive → 再读相同
4. 归档后新 base preview；`restart backend/worker`；Head/Result/audit 可读

第二位 actor 使用独立 OPEN workspace（`journey_key_prefix` 隔离 idempotency），非单 submission 限制。

## Unique test owners

- `tests/test_archive_http.py` — validation 参数表、permissions、replay、admission、409/429、cross-scope、body limit、dup keys、泄漏扫描
- `tests/test_archive_compose_e2e.py` — dual-actor compose、zero repository effect 观察窗口、restart persistence
- `tests/test_http_openapi.py` — `FROZEN_ARCHIVE_OPENAPI_PATHS` 字面量基线
- `tests/test_http_auth_matrix.py` — archive mutation without permission → 403
- `tests/test_production_wiring.py` — archive routes + job registry（19 passed）

## Focused gate (E1)

```bash
cd vnext/backend
../scripts/uv-consume.sh -C . run pytest -q \
  tests/test_archive_http.py tests/test_http_auth_matrix.py tests/test_http_openapi.py \
  tests/test_production_wiring.py tests/test_backend_readiness.py tests/test_architecture.py
# => 131 passed, 1 warning
```

## Container / image gate (E2)

```yaml
container_rebuild_required: yes
container_reason: remediation touches HTTP middleware, archive validation, compose harness
compose_project_name: gateway-p5-5d-s3-remediation-gate
prebuilt_used: no
```

```bash
GATEWAY_COMPOSE_GATE_PROJECT_NAME=gateway-p5-5d-s3-remediation-gate \
GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local \
../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' -v \
  tests/test_archive_compose_e2e.py tests/test_review_compose_e2e.py \
  tests/test_submit_compose_e2e.py tests/test_backend_http_container_gate.py
# => 6 passed, 0 skipped
```

## Provenance record (§6.3, remediation conjunction)

| 证据 | 值 |
| --- | --- |
| Git HEAD | introduced_by_this_commit |
| `vnext/**` tree status | clean |
| Source-tree digest recipe | `git ls-files 'vnext/**' \| LC_ALL=C sort \| while read p; do printf '%s\t%s\n' "$p" "$(sha256sum "$p" \| cut -d' ' -f1)"; done \| sha256sum` |
| Source-tree file count | 905 |
| Source-tree digest | `a963b15a80059ed1dabbf982c8f65774beaf1e7d0f69ef5129dd386f067edd48` |
| Backend `src` py digest (recipe §6.3, local == image) | `1702492dd7a947f62d8a0e8515ba8fdeb98614c40fd39ca7fb9307cc66950a3b` |
| uv.lock SHA (backend) | `21c8da4f438d9ab58c4fa61de13d1dbc24d19d5795c62d405d89568a3520acea` |
| uv.lock SHA (repository_service) | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| uv.lock SHA (repository_client) | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| uv.lock SHA (repository_contracts) | `b4b9740959fca2517b4c2b8a1237e8110aa854a69139d6742247748faae91ff3` |
| uv.lock SHA (shared_kernel) | `7be9e482910c3ede1c0a7f33d1eb08e9ff8fc183468fca8570cf04bf023fb898` |
| compose.yaml SHA-256 | `f1b8ca6fec0ec9c0108ea7f722c97a744956aff26b625c048fa038e572e3b8b0` |
| repository-service | `gateway-repository-service:local` → `sha256:70c25d76bb1abd9a24e73558c91d66e99980cee49d3f55a5e2ea50b936eb7487`；label revision `d19b3efcab` |
| backend | `gateway-p5-5d-s3-remediation-gate-backend` → `sha256:f10b26edd54b65134ba8d2da92499b9d3eaa3143198641120cc85a22524ad278` |
| worker | `gateway-p5-5d-s3-remediation-gate-worker` → `sha256:c25434af4efdfcb336006a43d23a1883f2c92127a60a09a50d23ddca8a4b44c9` |
| `org.opencontainers.image.revision` (backend/worker) | 空（Dockerfile 未接线；py digest 对等已验证） |

运行中 container provenance 由 `capture_running_container_provenance` 在 archive compose journey 采集并落盘
（`compose-container-provenance.json` in pytest tmp_path）。

## Forbidden imports

None. HTTP layer imports Application archive modules and existing HTTP dependencies only.

## Independent countersign

```yaml
review: pass_recommended
p5_5d_s3_stage_exit: not_evaluated
next_step: P5-5D-S4
slice_exit: not_signed_by_delivery
```

Delivery 建议独立 re-review 后签署 `p5_5d_s3_stage_exit`；不代签 `p5_5d_slice_exit` 或 `production_deployment_authorized`。
