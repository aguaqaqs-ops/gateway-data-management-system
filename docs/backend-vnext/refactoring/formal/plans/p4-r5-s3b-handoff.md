# P4-R5-S3b Handoff: External-effect Stub Recovery Consumer

状态：**PASS — S3b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：Application Recovery + Operation Runtime consumer

上游：[P4-R5-S3a Handoff](p4-r5-s3a-handoff.md)、[P4-R5-S2b Handoff](p4-r5-s2b-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s3b
step_id: P4-R5-S3b
input_handoff_sha: cc09136e8e5d3911299614f7045134a820647fd999017ec128eb6ca83cc0cda5
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s3a_validated_tip
result: pass
changed_paths:
  - vnext/backend/tests/test_operation_job_recovery.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s3b-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: S3b consumer integration tests only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s3b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3c cross-boundary fault matrix consolidation
  - bootstrap/worker composition wiring for RecoveryPort and operator-lease execution
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - need for Operations import of application recovery at worker runtime
  - need for R1/R2 schema, CAS, status or error-taxonomy change
  - need for real Repository client wire or P5 effect paths
next_step: P4-R5-S3c
next_step_authorized: no
```

## 1. Delivered boundary

S2b 已交付的 `build_external_effect_stub_recovery_port()` 在本步通过 **RecoveryPort 消费者级**
integration 测试锁定 external-effect stub 行为；**无 production 源码变更**。

`test_operation_job_recovery.py` 新增 S3b owner 与共享 invariant helper
`_assert_external_effect_recovery_invariants`：

| Invariant | Test owner |
|---|---|
| cancel-before-request | `test_external_effect_recovery_port_cancel_before_request` |
| request checkpoint（pre-request recovery path） | `test_external_effect_recovery_port_creates_request_checkpoint` |
| accepted → poll original identity | `test_external_effect_recovery_port_accepted_polls_original_identity` |
| confirmed from checkpoint | `test_external_effect_recovery_port_confirmed_from_checkpoint` |
| unknown → manual, no false READY | `test_external_effect_recovery_port_unknown_manual_no_false_ready` |
| 60s reconcile budget exhaustion | `test_external_effect_recovery_port_reconcile_budget_exhausted` |
| cancel-after-request continues reconcile | `test_external_effect_recovery_port_cancel_after_request_continues_reconcile` |
| post-request no artifact recreation | `test_external_effect_recovery_port_post_request_no_artifact_recreation` |

消费者 invariant 矩阵：

- **no new key**：`RecordingExternalEffectStub.submit_count` 与 checkpoint `idempotency_key` /
  `operation_identity` 不变
- **no false READY**：manual/pending 时 `ready_closure_ref is None`
- **no occupancy release**：outcome-only 路径 step 保持 `RUNNING` 且 lease 保留
- **no artifact recreation**：post-request poll 不新增 request artifact id

S2b adapter 单元/integration 仍由 `test_operation_effect_reconcile.py` 拥有；handler 级
cancel/reload 仍由 `test_operation_job_synthetic.py` 拥有。

## 2. Diff review

- `gateway_backend.operations` 不 import `gateway_backend.application`。
- 无 R1/R2 schema、migration、新 status、CAS contract 或 shared error taxonomy 变更。
- 无 bootstrap RecoveryPort 接线、无 Repository/Dolt effect。
- S3c cross-boundary matrix 与 process crash 证明仍 deferred。

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py
  -> 41 passed, 8 deselected

cd vnext/backend && uv run pytest -q -m unit
  -> 1608 passed, 96 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py
  -> 2 passed, 15 deselected

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 235 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files

git diff --check
  -> pass
```

Dolt、container 和 benchmark gates 对本 application consumer 步骤不适用。

## 4. Handoff boundary

S3c 是唯一 next step 且 remains unauthorized。validated code  intentionally 留在 working tree，
因未提供 explicit git commit authorization；`validated_code_sha` 在 commit 授权后填入。
本 handoff 不 authorize S3c、S4 或 P5B/Repository implementation。
