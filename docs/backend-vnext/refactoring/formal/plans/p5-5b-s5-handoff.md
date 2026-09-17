# P5-5B-S5 Submit JobDefinition, Repository Effect and Recovery Handoff

状态：**S5 complete — candidate `3eaaf3a5`**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
s4_handoff: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
s5_entry: authorized
s5_scope: submit JobDefinition handlers, repository write adapter, recovery/abort, integration harness
s5_complete: yes
s6_entry: deferred
```

## Scope amendment

执行计划 §S5 allowed paths 基础上，用户确认追加：

- `vnext/backend/tests/test_architecture.py` — `repository_read` + `repository_write` 双边界；bootstrap 允许 `infrastructure.repository_write`
- `vnext/backend/tests/support/submit_job_harness.py` — Repository Service 子进程 fixture、submit worker 组合、端到端 seed
- S4 F6 路径：`submit_acceptance.py`、`operator_recovery.py` 及对应 HTTP 测试

**未触碰**：`operations/**`、`application/recovery.py`、Repository packages、lockfile/依赖、P4 core 协议。

## Traceability

```yaml
stage: P5-5B-S5-submit-jobdefinition-repository-effect-recovery
parent_head: 0fdc0cb6cf4f6549331e989b7eb8994ebef46c9a
candidate_head: 3eaaf3a524cc4f16030329973b89b66e17f1cc98
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md §8–§9
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md §S5
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s4-handoff.md
scope_paths:
  - vnext/backend/src/gateway_backend/application/submit_registry.py
  - vnext/backend/src/gateway_backend/application/submit_jobs.py
  - vnext/backend/src/gateway_backend/application/submission/effect_pending_transaction.py
  - vnext/backend/src/gateway_backend/application/submission/errors.py
  - vnext/backend/src/gateway_backend/application/submission/operator_recovery_mapping.py
  - vnext/backend/src/gateway_backend/application/submission/accept_transaction.py
  - vnext/backend/src/gateway_backend/application/submission/ports.py
  - vnext/backend/src/gateway_backend/infrastructure/repository_write/**
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py
  - vnext/backend/src/gateway_backend/http/orchestration/operator_recovery.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/support/submit_job_harness.py
  - vnext/backend/tests/support/repository_service_starter.py
  - vnext/backend/tests/support/http_workspace_harness.py
  - vnext/backend/tests/test_submit_job_payload.py
  - vnext/backend/tests/test_submit_job_prepare.py
  - vnext/backend/tests/test_submit_job_effect.py
  - vnext/backend/tests/test_submit_finalize.py
  - vnext/backend/tests/test_submit_recovery.py
  - vnext/backend/tests/test_submit_worker.py
  - vnext/backend/tests/test_submit_transactions.py
  - vnext/backend/tests/test_submit_http.py
  - vnext/backend/tests/test_operator_recovery_http.py
uv_lock_in_diff: no
container_rebuild_required: no
```

## Deliverables summary

| 组件 | 行为 |
|------|------|
| `submit_registry.py` | 三步 `JobDefinition` 唯一权威源（prepare / submit / await） |
| `submit_jobs.py` | payload + 三 checkpoint decoder；prepare/submit/await handlers；recovery ports；operator abort adapter；`submit_composition_bundle`；`build_production_submit_dependencies` |
| `effect_pending_transaction.py` | T2 crossing：`PREPARED → EFFECT_PENDING` 单 SQLite UoW；occupancy 保持 |
| `infrastructure/repository_write/` | `HttpRepositoryWriteClient`（upload / versioned import / get/wait operation）；`HttpRepositoryAbortEvidencePort` |
| `operation_worker.py` | preview+submit definitions/handlers/decoders 合并；submit EXTERNAL_EFFECT 走 `build_submit_recovery_port` |
| F6 typed errors | `SubmitJobNotRegistered`、`OperatorRecovery*Conflict`；HTTP 层去除 message sniffing |

## Step topology and operator capability mapping

| Step | Recovery capability | Operator command | 关键副作用 |
|------|--------------------|------------------|-----------|
| `prepare_import` | `PURE_RECOMPUTE` | `RETRY_FROM_CHECKPOINT` | 本地 build package + checkpoint；复用同一 `BackendArtifactRef` |
| `submit_import` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` | upload + import wire；`PREPARED→EFFECT_PENDING` |
| `await_import_result` | `EXTERNAL_EFFECT` | `RESUME_RECONCILE` | poll matching operation → T3 finalize 或 stable abort |

`build_submit_recovery_port`：`submit_import` / `await_import_result` 仅 `RESUME_RECONCILE`（handler replay）；`prepare_import` 由 P4 `RETRY_FROM_CHECKPOINT` 走 handler 重算。

## Repository operation / ref evidence

集成测试通过 **subprocess Repository Service**（`submit_job_harness.repository_service_session`）验证真实 wire：

| 证据项 | 测试 owner | 结论 |
|--------|-----------|------|
| Upload path/header/body（`Idempotency-Key`、`x-artifact-sha256`、closed body keys） | `test_submit_job_effect.py::test_submit_upload_and_import_wire_mapping_uses_recording_transport` | pass |
| Import path/header/closed `SubmitVersionedImportRequest` body | 同上 + live repository 变体 | pass |
| Live repository `operation_id` 为合法 UUID | `test_submit_upload_and_import_wire_mapping_against_live_repository` | pass |
| `repository_artifact_ref` 自 upload response 经 `nominal_refs` 映射 | recording + live 两条路径 | pass |

Recording transport 固定 `operation_id = 018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11` 用于 deterministic wire 断言；live 路径仅校验 UUID 形态与 request fingerprint 闭合。

## Fault barrier and manual recovery matrix

| 场景 | 处置 | 测试证据 |
|------|------|---------|
| `submit_import` / `await_import_result` 无 checkpoint 恢复 | `MANUAL_RECOVERY_REQUIRED`；occupancy **保留** | `test_submit_recovery_without_checkpoint_retains_occupancy` |
| `PREPARED` 状态 operator abort | occupancy **保留**（不得盲放） | `test_prepared_attempt_operator_abort_retains_occupancy` |
| Repository `IMPORT_REJECTED` + operator `ABORT_CONFIRMED_FAILURE` | P4 CAS → `abort_submit_transaction` + evidence port；occupancy **释放** | `test_operator_abort_import_rejected_releases_occupancy` |
| Abort evidence 与 attempt `repository_operation_id` 不匹配 | `AbortProofNotSatisfied`；不释放 | `test_operator_abort_evidence_rejects_unknown_repository_operation` |
| Repository terminal success vs business T3 | `await_import_result` 解码 bounded evidence → `MatchingFinalizeFacts` → `finalize_submit_transaction`；与 Repository SUCCEEDED 显式分层 | `test_submit_finalize.py` 单元族 + effect happy path |
| 非 `EFFECT_PENDING` / binding fault / missing operation id | finalize 守卫拒绝 | `test_validate_matching_result_for_finalize_*` |
| T3 response-loss replay | `validate_finalize_replay` + 不插入第二条 submission | `test_finalize_submit_replay_returns_existing_submission`、`test_finalize_submit_transaction_replay_does_not_insert_second_submission` |
| Poll reconcile timeout | `MANUAL_RECOVERY_REQUIRED` diagnostic；occupancy 保留 | handler `wait_operation` `TimeoutError` 路径（`submit_jobs.build_await_import_result_handler`） |
| 非允许 abort code（非三码） | `MANUAL_RECOVERY_REQUIRED`；不盲 abort | `ALLOWED_ABORT_CODES` 守卫 + `HttpRepositoryAbortEvidencePort` |

允许 stable abort 三码：`IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH`、`VERIFICATION_FAILED_NOT_PUBLISHED`。

## F6 typed error closure（S5 首项）

| 路径 | 变更 |
|------|------|
| `submit_acceptance.py` | `SubmitJobNotRegistered` → `503 SERVICE_NOT_READY`（去除 `"not registered" in str(exc)`） |
| `operator_recovery.py` | `OperatorRecoveryIdentityConflict` / `StateConflict` / `CapabilityConflict` typed 映射（去除 `_RECOVERY_*_MESSAGES` 与 `"does not belong" in message`） |
| `operator_recovery_mapping.py` | P4 frozen 文案 → typed exception 单一映射表 |
| HTTP 回归 | `test_submit_http.py`、`test_operator_recovery_http.py`（registry/recovery 子集 17 passed） |

## §S5 unique test owners

| 文件 | 覆盖 |
|------|------|
| `tests/test_submit_job_payload.py` | 封闭 payload、version、registry identity、policy 负例 |
| `tests/test_submit_job_prepare.py` | checkpoint/ref reuse、successor 发布、replay |
| `tests/test_submit_finalize.py` | matching closure、finalize replay、binding mismatch |
| `tests/test_submit_job_effect.py` | upload/import exact wire；live repository journey |
| `tests/test_submit_recovery.py` | no-blind-replay、unknown-outcome occupancy、operator abort effect |
| `tests/test_submit_worker.py` | composition 注册、claim、duplicate exclusive、live repository ready |
| `tests/test_architecture.py` | repository_write 双边界、submit_jobs 例外、bootstrap 接线 |

**未修改** P4 owner：`test_operation_effect_reconcile.py`、`test_operation_job_recovery.py`。

## Focused gate

```bash
cd vnext/backend

# Unit
uv run pytest -q -m unit \
  tests/test_submit_job_payload.py \
  tests/test_submit_job_prepare.py \
  tests/test_submit_finalize.py
# 21 passed

uv run pytest -q -m unit tests/test_architecture.py
# 43 passed

# Integration（非 serial）
uv run pytest -q -m 'integration and not serial' \
  tests/test_submit_job_effect.py \
  tests/test_submit_recovery.py \
  tests/test_submit_worker.py
# 7 passed, 3 deselected

# Serial
uv run pytest -q -m serial \
  tests/test_submit_recovery.py \
  tests/test_submit_worker.py
# 3 passed, 5 deselected

# Static
uv run ruff check src/gateway_backend/application/submit_jobs.py \
  src/gateway_backend/application/submit_registry.py \
  src/gateway_backend/infrastructure/repository_write \
  tests/test_submit_job_payload.py tests/test_submit_job_effect.py \
  tests/test_submit_finalize.py tests/test_submit_recovery.py
# All checks passed

../scripts/uv-consume.sh -C . run mypy
# Success: no issues found in 367 source files
```

## Deferred / observations

- **S6**：production settings / `http/runtime.py` internal bearer 与完整 readiness 接线；`build_production_submit_dependencies` 已在 worker bootstrap 可运行，完整 deployment 属 S6。
- **dolt 不可用节点**：integration 用例通过 `skipif(not dolt_available())` 跳过 live repository 路径；recording transport 用例无 dolt 依赖始终运行。
- **container_rebuild_required: no** — 未触碰 Dockerfile、Compose、entrypoint、UID/volume/signal 边界。

## next_step

```yaml
next_step: P5-5B-S6 production deployment wiring and container gates
s6_entry: deferred
s6_authorized: no
```
