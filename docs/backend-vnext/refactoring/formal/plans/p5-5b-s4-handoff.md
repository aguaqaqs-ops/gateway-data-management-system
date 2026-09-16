# P5-5B-S4 Backend HTTP v1 and Re-authorization Handoff

状态：**S4 independent review pass — S5 entry authorized**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
s3_handoff: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
s4_entry: authorized
s4_scope: backend HTTP adapter only; fake/S2 local UoW; no Repository effect
s4_independent_review: pass
s5_entry: authorized
s5_authorization_source: explicit_user_instruction_2026-09-16
```

最终独立复审与 S5 入口授权记录见
[p5-5b-s4-final-independent-review.md](p5-5b-s4-final-independent-review.md)。

## Scope amendment

执行计划 §S4 allowed paths 原文未列出测试 harness。实施前用户确认将下列路径纳入 S4 changed paths：

- `vnext/backend/tests/support/http_workspace_harness.py` — submit registry、internal bearer、submit-ready seed、fake ports（`FakeBaselineCanonicalDigestPort`、`RecordingBaselineCanonicalDigestPort`、`RecordingMainResolvePort`、`FailingMainResolvePort`、`LocalOperatorRecoveryPort`）、recovery promote helper。

Round-2 新增：

- `vnext/backend/src/gateway_backend/http/schemas/constraints.py` — shared DTO bounds（I-JSON、opaque id、diagnostic reason UTF-8）

Round-3 最小 application 例外（用户授权，消除 baseline 双调用）：

- `vnext/backend/src/gateway_backend/application/submission/accept_transaction.py` — 当 `preflight.baseline_canonical_digest` 已填充时跳过二次 `baseline_digest` 调用

## Traceability

```yaml
stage: P5-5B-S4-backend-http-v1-re-authorization
candidate_head: 0fdc0cb6cf4f6549331e989b7eb8994ebef46c9a
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md §5/§6.1/§12
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md §S4/§4
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-handoff.md
scope_paths:
  - vnext/backend/src/gateway_backend/http/schemas/constraints.py
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
  - vnext/backend/src/gateway_backend/application/submission/accept_transaction.py
  - vnext/backend/tests/support/http_workspace_harness.py
  - vnext/backend/tests/support/workspace_fixtures.py
  - vnext/backend/tests/test_submit_http.py
  - vnext/backend/tests/test_submit_read_http.py
  - vnext/backend/tests/test_operator_recovery_http.py
  - vnext/backend/tests/test_operation_http.py
  - vnext/backend/tests/test_http_auth_matrix.py
  - vnext/backend/tests/test_http_openapi.py
explicit_non_paths:
  - vnext/backend/src/gateway_backend/application/submission/** (except accept_transaction.py baseline dedup)
  - vnext/backend/src/gateway_backend/http/mappers.py
  - vnext/backend/src/gateway_backend/http/runtime.py
uv_lock_in_diff: no
docker_rebuild_required: no
```

## Remediation summary

### Round 1 (independent review)

| Finding | Fix |
|---------|-----|
| F1 missing Preview/UploadRevision → 409 | `submit_acceptance` 预读 `None` 直接 `404 RESOURCE_NOT_FOUND` |
| F2 recovery state/capability mislabel | `operator_recovery` 按 P4/StaleWrite 冻结文案精确映射 |
| F3 uv.lock mirror drift | 工作区还原为 HEAD canonical PyPI；`uv lock --check` pass |
| F5 §4 owner gaps | 补齐 submit/recovery/operation/openapi 冻结错误矩阵 |
| F6 message sniffing | 登记 deferred → S5 入口 gate（typed error / stable_code） |
| occupancy 500 | 新增 `SubmissionDomainError` exception handler |

### Round 2 (independent review)

| Finding | Fix |
|---------|-----|
| F1 读路径无 mapping 重授权 | `operation_scope` 调用 `scope_resolution.resolve()` 并校验 frozen/current repository |
| F2 Accept 权限前预读 | `assert_permission` 先于一切业务读；无权限不泄露存在性 |
| F3 Submit DTO 无 bounds/strict | `constraints.py` + `AcceptSubmitRequest` strict I-JSON / opaque id |
| F4 Recovery DTO 无 I-JSON/UTF-8 budget | `OperatorRecoveryRequestBody` 版本/reason 封闭校验 |
| F5 recovery registry → 500 | `_capability_lookup` 捕获 `JobDefinitionLookupError` → `503 SERVICE_NOT_READY` |
| F6 预检顺序/双 main resolve | 删除 HTTP `validate_accept_submit`；guards → artifact → transaction 单次 main resolve |

### Round 3 (independent review)

| Finding | Fix |
|---------|-----|
| F1 preflight 在 write txn 内调 baseline | 预检 `read_only=True` UoW；baseline I/O 在 UoW 外；`accept_transaction` 复用已填充 digest |
| F2 replay 依赖当前 artifact metadata | `build_replay_preflight_from_attempt`；跳过 `load_accept_submit_preflight` 与 artifact verify |
| F3 读路径 permission 在对象加载之后 | `assert_workspace_read_permission` 先于 GET；消除 403/404 oracle |
| F4 mapping missing → 503 | `provisioned mapping is missing/disabled` → `404 RESOURCE_NOT_FOUND` |

### Round 3 re-review (independent review)

| Finding | Fix |
|---------|-----|
| R3-RR-F1 NO_CANONICAL_CHANGE 被 occupancy 提前遮蔽 | `post_noop_guards` 移到 baseline I/O 与 `assert_no_canonical_change_after_baseline` 之后 |

## Deliverables

| 路由 | 行为 | 权限 |
|------|------|------|
| `POST /v1/workspaces/{workspace_id}/submit-attempts` | AcceptSubmit；首次与 same/same replay 均 `202` | `upload_submit_workspace` + exact scope |
| `GET .../submit-attempts/{submit_attempt_id}` | GetSubmitAttempt `200` | `workspace_read` + permission-first + mapping re-auth |
| `GET .../submissions/{submission_id}` | GetSubmission `200` | 同上 |
| `GET /v1/operations/{operation_id}` | 复用；submit operation 走 `submit_attempt` business ref | `workspace_read` + permission-first + mapping |
| `POST /internal/v1/operations/{operation_id}/steps/{step_id}/recovery` | Operator recovery（fake application port） | deployment internal bearer |

附加：closed DTO（`extra=forbid`）、header-only `Idempotency-Key`、Submit/recovery stable error 映射、response redaction、OpenAPI path closure。

## HTTP status / error evidence

| 场景 | Status | Stable code |
|------|--------|-------------|
| AcceptSubmit 成功 / replay | 202 | — |
| same/same replay（closure metadata 已移除） | 202 | — |
| 缺 Idempotency-Key | 422 | `REQUEST_VALIDATION_FAILED` |
| DTO strict/bounds 失败 | 422 | `REQUEST_VALIDATION_FAILED` |
| 缺 Preview / UploadRevision（已授权） | 404 | `RESOURCE_NOT_FOUND` |
| 无 submit/read 权限（无论资源是否存在） | 403 | `SCOPE_FORBIDDEN` |
| mapping missing/disabled | 404 | `RESOURCE_NOT_FOUND` |
| mapping 暂时性解析失败 | 503 | `DEPENDENCY_UNAVAILABLE` |
| submit / recovery registry 未注册 | 503 | `SERVICE_NOT_READY` |
| idempotency conflict | 409 | `IDEMPOTENCY_CONFLICT` |
| workspace version / stale / occupancy / no change | 409 | 各 stable code |
| artifact 不可读（优先于 main resolve） | 503 | `ARTIFACT_UNAVAILABLE` |
| main resolve 不可用 | 503 | `DEPENDENCY_UNAVAILABLE` |
| GET cross-scope / 不存在（已授权） | 404 | `RESOURCE_NOT_FOUND` |
| recovery / internal auth 族 | 见 round-1/2 evidence | — |

## OpenAPI closure

`PRODUCTION_OPENAPI_PATHS` 与 OpenAPI `paths` **等号**闭合（`test_http_openapi.py`）。

## §4 unique HTTP test owners

| 文件 | 覆盖 |
|------|------|
| `tests/test_submit_http.py` | POST 202、baseline 单次、replay 冻结 facts、NO_CANONICAL_CHANGE 优先于 occupancy、permission-before-read、422、503/409 族 |
| `tests/test_submit_read_http.py` | GET 200、permission-first 403 oracle、mapping missing 404、mapping 漂移 404 |
| `tests/test_operator_recovery_http.py` | round-2 recovery 矩阵 |
| `tests/test_operation_http.py` | Operation GET、permission-first 403 oracle、mapping 漂移 404 |
| `tests/test_http_openapi.py` | paths 等号 |
| `tests/test_http_auth_matrix.py` | permission matrix |

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
# 62 passed

uv run pytest -q -m unit tests/test_submit_transactions.py -k "baseline or canonical"
# 3 passed

uv run ruff check src/gateway_backend/http \
  tests/test_submit_http.py tests/test_submit_read_http.py \
  tests/test_operation_http.py tests/support/http_workspace_harness.py
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 352 source files
```

## Deferred / observations

**F6 → S5 first work item**：message sniffing / P4 文案耦合已在 S5 entry audit 中确认不触发
contract reopen；必须先以 typed error / stable classification 关闭，之后才开始真实 Repository effect。
Finding-scoped 路径扩展仅包括：

- `vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py`
- `vnext/backend/src/gateway_backend/http/orchestration/operator_recovery.py`
- `vnext/backend/tests/test_submit_http.py`
- `vnext/backend/tests/test_operator_recovery_http.py`

**F9 observation**: AcceptSubmit replay 仍经过 `acquire_new_work`；design 未冻结，留 S7。

## Explicit non-deliverables (deferred)

- 真实 Repository effect、Submit JobDefinition worker handler → **S5**
- production settings / `http/runtime.py` internal bearer 与 port 接线 → **S6**
- Docker/Compose 镜像重建 — 本阶段未触碰 image/deployment boundary

## next_step

```yaml
next_step: P5-5B-S5 F6 typed-error closure, then planned S5 implementation
s5_entry_gate: pass
s5_authorized: yes
s5_first_required_work: close_F6_typed_error_and_stable_classification
real_repository_effect_before_F6_closure: forbidden
s6_authorized: no
```
