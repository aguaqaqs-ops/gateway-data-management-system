# P5-5B-S4 Backend HTTP v1 and Re-authorization Handoff

状态：**S4 remediation complete — pending independent re-review**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
s3_handoff: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
s4_entry: authorized
s4_scope: backend HTTP adapter only; fake/S2 local UoW; no Repository effect
s4_independent_review: changes_required (remediated)
```

## Scope amendment

执行计划 §S4 allowed paths 原文未列出测试 harness。实施前用户确认将下列路径纳入 S4 changed paths：

- `vnext/backend/tests/support/http_workspace_harness.py` — submit registry、internal bearer、submit-ready seed、fake ports（`FakeBaselineCanonicalDigestPort`、`RecordingMainResolvePort`、`FailingMainResolvePort`、`LocalOperatorRecoveryPort`）、recovery promote helper。

## Traceability

```yaml
stage: P5-5B-S4-backend-http-v1-re-authorization
candidate_head: 9fa652ae8c8f0e0e0e0e0e0e0e0e0e0e0e0e0e0
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md §5/§12
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md §S4/§4
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-handoff.md
scope_paths:
  - vnext/backend/src/gateway_backend/http/schemas/submit.py
  - vnext/backend/src/gateway_backend/http/schemas/operator_recovery.py
  - vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py
  - vnext/backend/src/gateway_backend/http/orchestration/operator_recovery.py
  - vnext/backend/src/gateway_backend/http/routes/submit_attempts.py
  - vnext/backend/src/gateway_backend/http/routes/submissions.py
  - vnext/backend/src/gateway_backend/http/routes/operator_recovery.py
  - vnext/backend/src/gateway_backend/http/errors.py
  - vnext/backend/src/gateway_backend/http/auth.py
  - vnext/backend/src/gateway_backend/http/dependencies.py
  - vnext/backend/src/gateway_backend/http/orchestration/operation_scope.py
  - vnext/backend/src/gateway_backend/http/routes/operations.py
  - vnext/backend/src/gateway_backend/http/wiring.py
  - vnext/backend/tests/support/http_workspace_harness.py
  - vnext/backend/tests/test_submit_http.py
  - vnext/backend/tests/test_submit_read_http.py
  - vnext/backend/tests/test_operator_recovery_http.py
  - vnext/backend/tests/test_operation_http.py
  - vnext/backend/tests/test_http_auth_matrix.py
  - vnext/backend/tests/test_http_openapi.py
explicit_non_paths:
  - vnext/backend/src/gateway_backend/application/submission/**
  - vnext/backend/src/gateway_backend/http/mappers.py
  - vnext/backend/src/gateway_backend/http/runtime.py
uv_lock_in_diff: no
docker_rebuild_required: no
```

## Remediation summary (independent review)

| Finding | Fix |
|---------|-----|
| F1 missing Preview/UploadRevision → 409 | `submit_acceptance` 预读 `None` 直接 `404 RESOURCE_NOT_FOUND` |
| F2 recovery state/capability mislabel | `operator_recovery` 按 P4/StaleWrite 冻结文案精确映射 |
| F3 uv.lock mirror drift | 工作区还原为 HEAD canonical PyPI；`uv lock --check` pass |
| F5 §4 owner gaps | 补齐 submit/recovery/operation/openapi 冻结错误矩阵（45 tests） |
| F6 message sniffing | 登记 deferred → S5 入口 gate（typed error / stable_code） |
| occupancy 500 | 新增 `SubmissionDomainError` exception handler（`SubmitOccupancyConflict`） |

## Deliverables

| 路由 | 行为 | 权限 |
|------|------|------|
| `POST /v1/workspaces/{workspace_id}/submit-attempts` | AcceptSubmit；首次与 same/same replay 均 `202` | `upload_submit_workspace` + exact scope |
| `GET .../submit-attempts/{submit_attempt_id}` | GetSubmitAttempt `200` | `workspace_read` + every-read re-auth |
| `GET .../submissions/{submission_id}` | GetSubmission `200` | 同上 |
| `GET /v1/operations/{operation_id}` | 复用；submit operation 走 `submit_attempt` business ref | `workspace_read` + scope |
| `POST /internal/v1/operations/{operation_id}/steps/{step_id}/recovery` | Operator recovery（fake application port） | deployment internal bearer |

附加：closed DTO（`extra=forbid`）、header-only `Idempotency-Key`、Submit/recovery stable error 映射、response redaction、OpenAPI path closure。

## HTTP status / error evidence

| 场景 | Status | Stable code |
|------|--------|-------------|
| AcceptSubmit 成功 / replay | 202 | — |
| 缺 Idempotency-Key | 422 | `REQUEST_VALIDATION_FAILED` |
| 缺 Preview / UploadRevision | 404 | `RESOURCE_NOT_FOUND` |
| submit registry 未注册 | 503 | `SERVICE_NOT_READY` |
| idempotency same key / different fingerprint | 409 | `IDEMPOTENCY_CONFLICT` |
| workspace version 过期 | 409 | `WORKSPACE_VERSION_CONFLICT` |
| preview derived stale | 409 | `PREVIEW_DERIVED_STALE` |
| workspace/repository occupancy | 409 | `SUBMIT_OCCUPANCY_CONFLICT` |
| 无 canonical change | 409 | `NO_CANONICAL_CHANGE` |
| 无 submit 权限 | 403 | `SCOPE_FORBIDDEN` |
| admission 满 | 429 | `ADMISSION_LIMIT_REACHED` |
| artifact 不可读 | 503 | `ARTIFACT_UNAVAILABLE` |
| main resolve 不可用 | 503 | `DEPENDENCY_UNAVAILABLE` |
| GET cross-scope / 不存在 | 404 | `RESOURCE_NOT_FOUND` |
| internal bearer 缺失 | 401 | `AUTHENTICATION_REQUIRED` |
| recovery path/body 不一致 | 409 | `RECOVERY_IDENTITY_CONFLICT` |
| recovery 非 MANUAL 源状态 | 409 | `RECOVERY_STATE_CONFLICT` |
| capability 错配 | 409 | `RECOVERY_CAPABILITY_CONFLICT` |
| operation/step version CAS | 409 | `OPERATION_VERSION_CONFLICT` / `STEP_VERSION_CONFLICT` |
| recovery target 不存在 | 404 | `RECOVERY_TARGET_NOT_FOUND` |
| ABORT 无 proof（S4 fake） | 409 | `ABORT_PROOF_NOT_SATISFIED` |
| ABORT terminal replay | 200 | `IDEMPOTENT` |

## OpenAPI closure

`PRODUCTION_OPENAPI_PATHS` 与 OpenAPI `paths` **等号**闭合（`test_http_openapi.py`）。

## §4 unique HTTP test owners

| 文件 | 覆盖 |
|------|------|
| `tests/test_submit_http.py` | POST 202、404 missing、422、replay、idempotency/workspace/stale/occupancy/503/409 族 |
| `tests/test_submit_read_http.py` | GET Attempt/Submission 200、cross-scope 404、permission 403、redaction |
| `tests/test_operator_recovery_http.py` | bearer、identity、state/capability/version、target 404、terminal ABORT IDEMPOTENT |
| `tests/test_operation_http.py` | submit Operation GET + missing ref/attempt 404 |
| `tests/test_http_openapi.py` | paths 等号 + closed DTO |
| `tests/test_http_auth_matrix.py` | `upload_submit_workspace` / `workspace_read` matrix |

## Focused gate

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_http.py \
  tests/test_submit_read_http.py \
  tests/test_operator_recovery_http.py \
  tests/test_operation_http.py \
  tests/test_http_auth_matrix.py \
  tests/test_http_openapi.py
# 45 passed

uv run ruff check src/gateway_backend/http \
  tests/test_submit_http.py tests/test_submit_read_http.py \
  tests/test_operator_recovery_http.py tests/support/http_workspace_harness.py
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 351 source files
```

## Deferred / observations

**F6 → S5 entry gate**

- `submit_acceptance` 嗅探 `PreviewBindingConflict("not registered")` 映射 `503 SERVICE_NOT_READY`
- `operator_recovery` 依赖 P4 `ValueError` 冻结文案（已精确匹配，但仍为跨模块文本耦合）

**F8 observation**: 读路径 re-auth 与 5A 一致，以冻结 `WorkspaceScope` exact match 为读权威（非 live mapping resolve）。

**F9 observation**: AcceptSubmit replay 仍经过 `acquire_new_work`；design 未冻结，留 S7。

## Explicit non-deliverables (deferred)

- 真实 Repository effect、Submit JobDefinition worker handler → **S5**
- production settings / `http/runtime.py` internal bearer 与 port 接线 → **S6**
- Docker/Compose 镜像重建 — 本阶段未触碰 image/deployment boundary

## next_step

```yaml
next_step: S4 independent re-review
s5_entry_gate: S4 review pass + explicit S5 authorization
```
