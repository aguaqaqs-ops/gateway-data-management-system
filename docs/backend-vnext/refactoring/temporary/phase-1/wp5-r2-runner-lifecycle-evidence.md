# WP5 R2 — Runner Lifecycle / Registry / Fake Harness / Result Precedence Evidence

状态：**PASS — independent external review accepted**

日期：2026-07-24

前置基线：WP5 R1 PASS（`4df45e417c897f3523b9ef559cfa03427d364d58`）

Gate：**`PR-CORRECTNESS`**（`vnext/scripts/gate.sh correctness`）

---

## 1. 结论与边界

| 项 | 声明 |
| --- | --- |
| 本轮范围 | In-process runner skeleton：固定 lifecycle、subject registry、fake harness、runner 独占 compare/result、最小 RunEvidenceBundle |
| **不是** | R3 正式 canonical-row-hash scenario、R4 provider 全矩阵、R5 container / Phase 1 exit、`PR-NATIVE` 专项补跑（本轮未触及 native 职责变更） |
| 审核状态 | **PASS** — **EXT-REVIEW-WP5-R2** 已完成并接受 |

### 威胁模型（Phase 1 / WP5 R2）

SubjectHarness 是受信任、遵守协议的**同进程 adapter**。R2 约束公开 DTO 与 capability API（fault 仅 `consume()`，clock 仅 `now_iso()`），**不**提供针对 `__globals__`、模块私有变量、反射或 `object.__setattr__` 的沙箱。对抗性进程隔离 **deferred / out of R2**。模块级 token 表仅为 runner **内部 dispatch**，不是安全边界。

### Deferred

- R3 `vnext/fixtures/scenarios/` 真实 data scenario
- R4 reference/integration/provider-matrix 真实 harness
- subprocess / plugin ABI / harness service
- auto-bless / golden rewrite
- 正式 evidence store（`evidence_ref` 保持 null）

---

## 2. 基线、HEAD、merge-base

| 项 | 值 |
| --- | --- |
| branch | `main` |
| HEAD | `4df45e417c897f3523b9ef559cfa03427d364d58` |
| merge-base（约定 baseline） | `4df45e417c897f3523b9ef559cfa03427d364d58` |
| worktree | 未提交交付（见 §8） |
| AGENTS.md | 仓库内不存在 |

---

## 3. Authority

| Authority | 采用 |
| --- | --- |
| [fixture-oracle-and-conformance.md](../../formal/contracts/fixture-oracle-and-conformance.md) | §7–§8 lifecycle、harness 关闭集、observation、result precedence |
| [shared-canonical-encoding.md](../../formal/contracts/shared-canonical-encoding.md) | owner digest / RUN_EVIDENCE |
| [contract-taxonomy-and-ownership.md](../../formal/contracts/contract-taxonomy-and-ownership.md) | Conformance Harness 归属 |
| [implementation-stages.md](../../formal/plans/implementation-stages.md) | `PR-CORRECTNESS` |
| [ADR 0006](../../formal/adr/0006-language-neutral-fixture-oracle.md) | language-neutral oracle |
| [wp3-wp5-checkout-plan.md](wp3-wp5-checkout-plan.md) | WP5 R2 范围 |
| [wp5-r1-scenario-schema-closure-evidence.md](wp5-r1-scenario-schema-closure-evidence.md) | R1 基座 |

---

## 4. Delivery manifest

### Runner 模块（`vnext/conformance/src/gateway_conformance/runner/`）

| 路径 | 职责 |
| --- | --- |
| `types.py` | Harness protocol v1 runtime DTO（receipt / observation） |
| `registry.py` | `SubjectKey` 静态 registry；duplicate fail-closed；强引用实例 identity |
| `observation_snapshot.py` | harness observation runner-owned 深快照 |
| `receipts.py` | harness receipt/support/cleanup 关闭集校验（含 diagnostic lower-kebab） |
| `plan.py` | `build_harness_plan` + `validate_harness_plan` |
| `runtime.py` | token 内部 dispatch；最小公开 capability API（`consume` / `now_iso`）；runner 独占 arm/disarm/tick |
| `compare.py` | Observation exact-set、runner 重算 digest、owner compare |
| `result.py` | `resolve_final_status`、四态 precedence、`build_runner_result`、`apply_recovery_checkpoint_gate`（真实 checkpoint digest） |
| `evidence.py` | `package_run_evidence` + `validate_run_evidence_bundle`（diagnostics 消毒） |
| `diagnostics.py` | `sanitize_diagnostic` |
| `lifecycle.py` | `execute_scenario_run` 固定 12 步 |
| `fake/harness.py` | `FakeSubjectHarness`（仅测试） |

### 测试

| 路径 |
| --- |
| `tests/runner_support.py` |
| `tests/test_runner_registry.py` |
| `tests/test_runner_preflight.py` |
| `tests/test_runner_lifecycle.py` |
| `tests/test_runner_golden_isolation.py` |
| `tests/test_runner_assets.py` |
| `tests/test_runner_observations.py` |
| `tests/test_runner_compare.py` |
| `tests/test_runner_result_precedence.py` |
| `tests/test_runner_determinism.py` |
| `tests/test_runner_recovery.py` |
| `tests/test_runner_evidence.py` |
| `tests/test_runner_mutation_probes.py` |
| `tests/test_runner_plan_integrity.py` |
| `tests/test_runner_diagnostics_sanitize.py` |
| `tests/test_runner_observation_snapshot.py` |
| `tests/test_runner_receipt_validation.py` |
| `tests/test_runner_fault_isolation.py` |
| `tests/test_architecture.py`（R2 守卫更新） |

### 工具

| 路径 |
| --- |
| `vnext/scripts/verify-wp5-r2-patch-sha.sh` |

---

## 5. Registry 与 lifecycle

**Registry 键：** `(track, subject.kind, subject.name)`，例如 `(data, capability, test-capability)`。

**Lifecycle（formal §7.2）：**

1. `load_validated_scenario`
2. `build_harness_plan` → `preflight(plan)` only
3. `UNSUPPORTED` → result `NOT_RUN`，无 provision/seed/invoke/cleanup_subject
4. provision → seed → arm fault（若声明）→ invoke
5. observe：`final`（data/command）或 `after-failure` → `drive_recovery` → `after-recovery`（recovery）
6. compare（expectation 以 `after-recovery` / `final` 为准；recovery 任一 checkpoint `MISMATCH` 经 `apply_recovery_checkpoint_gate` 门控终态）
7. `finally`：`cleanup_subject` + fault disarm
8. `_finalize_run_outcome`：`build_runner_result` + `package_run_evidence`（仅 `plan_authority`；失败不向外抛）

**实现说明（MIN-002）：** formal 图示为 evidence→teardown；本实现先在 `finally` 完成 cleanup，再组装 result/evidence，以便 evidence 含最终 cleanup 状态。

---

## 6. Result precedence 矩阵（runner `resolve_final_status`）

| unsupported | harness_error | comparison | cleanup | status |
| --- | --- | --- | --- | --- |
| T | F | NOT_RUN | CLEAN | UNSUPPORTED |
| F | T | * | * | HARNESS_ERROR |
| F | F | NOT_RUN | CLEAN | HARNESS_ERROR |
| F | F | MATCH | CLEAN | PASSED |
| F | F | MISMATCH | CLEAN | ASSERTION_FAILED |
| F | F | MATCH/MISMATCH | LEAKED/FAILED | HARNESS_ERROR（保留 comparison） |

聚合：`MISMATCH` > `MATCH` > `NOT_RUN`。

---

## 7. Golden 隔离

- Plan 经 `validate_harness_plan` + `FORBIDDEN_PROTOCOL_FIELDS` 语义检查。
- Harness runtime context 不含 golden envelopes / expected digest / fixture root。
- Harness 仅接收 `plan_harness`（`deepcopy`）；result/evidence 仅使用 `plan_authority`。
- 测试 `test_runner_plan_integrity` 验证嵌套 mutation 不污染 identity。

---

## 8. 验证结果

| 检查 | 结果 |
| --- | --- |
| `git diff --check` | pass |
| `ruff check` / `ruff format --check`（conformance） | pass |
| `mypy`（conformance strict） | pass |
| `pytest --collect-only`（conformance） | **481** collected |
| `pytest`（conformance） | **481 passed**, **0 skipped** |
| `test_runner_*.py` + `test_architecture.py` | **120 passed** |
| `bash vnext/scripts/gate.sh correctness` | **correctness gate passed**（MAJ-023 威胁模型纠偏 / MIN-013 后复跑）；conformance **0 skipped**；backend production extension **3 个既有 skip**，非 R2 runner |

---

## 9. Patch SHA

| 项 | 值 |
| --- | --- |
| BASE | `4df45e417c897f3523b9ef559cfa03427d364d58` |
| Patch SHA（初版） | `f9bdcc6d06350ed0444fb84c8d18d77de3010220bd6ff32ae7b72b5ca4b0a00c` |
| Patch SHA（re-audit 修复后） | `ebfae53fb3050a10a45675554a60a92e3f6ba568854b5446650bb01ae0d3fa4d` |
| Patch SHA（re-audit-2 修复后） | `a72da3c278bade288dd7f3efacd88ac2de3c31b6aa227ef4fbe6f0abfeb5ab3b` |
| Patch SHA（re-audit-3 合修后，format 前误记，已作废） | `a2e39c6a3b8f707e48ceda49928bd5a1d69ea8ddfcc6f3ba8c2e7e26cdf3725f` |
| Patch SHA（re-audit-4 信任边界合修后） | `0db1e51d51cb5e03b6c6f719cef86c634ab63bb7fadf71f5e45d0f733aa39c62` |
| Patch SHA（MAJ-021 / MIN-011 信任面修补后） | `2adebb968a6ac52c389b647afaaf39038052c0a712a5c87f187dadf9b8e6f01d` |
| Patch SHA（MAJ-022 / MIN-012 闭包信任面修补后） | `d8888251697bb1108ccde262f9369c772b690592f6ef7a196e786d7ce7d4fcdc` |
| Patch SHA（MAJ-023 / MAJ-024 合修后） | `3f278d473ef061d233b35ed55bea51d4ddf279caefd13a460106292ea0274e32` |
| Patch SHA（MAJ-023 威胁模型纠偏 / MIN-013 后） | `4365a3145ac9d8395ec671f1a2aacf9b557e011a6048c62f32aaab0220faec6e` |
| 验证 | `BASE=4df45e417c897f3523b9ef559cfa03427d364d58 EXPECTED_SHA=4365a3145ac9d8395ec671f1a2aacf9b557e011a6048c62f32aaab0220faec6e bash vnext/scripts/verify-wp5-r2-patch-sha.sh` |

---

## 10. Findings / blocking register

| ID | 状态 | 说明 |
| --- | --- | --- |
| WP5-R2-REV-BLK-001 | **FIXED** | `plan_authority`/`plan_harness` deepcopy；`_finalize_run_outcome` 吞掉 result/evidence 校验异常 |
| WP5-R2-REV-MAJ-001 | **FIXED** | evidence 重算 digest；`harness_error` 时 observations 不入 bundle |
| WP5-R2-REV-MAJ-002 | **FIXED** | `apply_recovery_checkpoint_gate`（re-audit-2：使用 checkpoint 真实 `content_digest`，禁止伪造 actual） |
| WP5-R2-REV-MAJ-003 | **FIXED** | registry 拒绝 factory 单例复用 |
| WP5-R2-REV-MAJ-004 | **FIXED** | `sanitize_message` on result + evidence/cleanup/observation diagnostics |
| WP5-R2-REV-MAJ-005 | **FIXED** | 移除 `_mismatch_actual_digest`；gate actual 对齐 checkpoint / evidence |
| WP5-R2-REV-MAJ-006 | **FIXED** | `_seen_resolve_ids` 拒绝任意实例 id 复用（含 A→B→A） |
| WP5-R2-REV-MIN-007 | **FIXED** | Evidence §8 runner 侧用例计数更正 |
| WP5-R2-REV-MAJ-007 | **FIXED** | receipt/support/cleanup 关闭集校验 |
| WP5-R2-REV-MAJ-008 | **FIXED** | binding `wire_schema_version` + descriptor `media_type` |
| WP5-R2-REV-MAJ-009 | **FIXED** | registry duplicate fail-closed + weakref 存活检测 |
| WP5-R2-REV-MAJ-010 | **FIXED** | fault 由 harness consume；runner 终态验证 |
| WP5-R2-REV-MAJ-011 | **FIXED** | `ProfileHandle.teardown` exactly-once |
| WP5-R2-REV-MAJ-012 | **FIXED** | finalize 四态封闭 + evidence fallback |
| WP5-R2-REV-MAJ-013 | **FIXED** | harness_error 保留可信 checkpoint MISMATCH |
| WP5-R2-REV-MIN-008 | **FIXED** | unsupported reason + receipt diagnostics |
| WP5-R2-REV-MIN-009 | **FIXED** | runner vs cleanup diagnostics 分轨 |
| WP5-R2-REV-MAJ-014 | **FIXED** | Evidence §9 Patch SHA 与脚本对齐 |
| WP5-R2-REV-BLK-002 | **FIXED** | observation 深快照；compare/evidence 与 result 身份一致 |
| WP5-R2-REV-MAJ-015 | **FIXED** | per-id checkpoint gate；gate 异常入四态 |
| WP5-R2-REV-MAJ-016 | **FIXED** | diagnostic lower-kebab；fallback 安全 diagnostics |
| WP5-R2-REV-MAJ-017 | **FIXED** | ProfileView + provision exactly-once |
| WP5-R2-REV-MAJ-018 | **FIXED** | env 前置校验；fallback 不伪造 fault |
| WP5-R2-REV-MAJ-019 | **FIXED** | registry 强引用 identity（无 weakref 硬依赖） |
| WP5-R2-REV-MAJ-020 | **FIXED** | `harness_error` 优先于 `unsupported` |
| WP5-R2-REV-MIN-010 | **FIXED** | `environment_versions` component 唯一 + lower-kebab |
| WP5-R2-REV-MAJ-021 | **FIXED** | 公开面去掉 `_channel`；无 fault 声明时不创建 channel、`fault_receipt` 为 null（非反射沙箱；现以 §1 威胁模型为准） |
| WP5-R2-REV-MIN-011 | **FIXED** | 自 context 移除 `_logical_clock` / `deadline_tick`；公开 clock 面仅 `now_iso()` |
| WP5-R2-REV-MAJ-022 | **FIXED** | 公开 capability 改为 token dispatch / 冻结 ISO，去掉 bound-method `__self__` 误用面（非对抗隔离；现以 §1 为准） |
| WP5-R2-REV-MIN-012 | **FIXED** | `ClockView` 仅暴露冻结 ISO `now_iso()`，无公开 `_clock` / `tick` / `advance_iso` |
| WP5-R2-REV-MAJ-023 | **CLOSED** | 范围误判：trusted in-process adapter；不以 Python 私有机制作安全边界；公开 API 最小化 |
| WP5-R2-REV-MAJ-024 | **FIXED** | checkpoint gate 仅当前 MISMATCH 记 digest，保留首次 mismatch；gate 拒绝 actual==expected |
| WP5-R2-REV-MIN-013 | **FIXED** | per-run token 注册/注销；测试前后 registry 为空、无泄漏 |
| WP5-R2-REV-MIN-001..006 | **ADDRESSED** | 见实现与新增测试 |

---

## 11. 外部签核

**EXT-REVIEW-WP5-R2：PASS** — 已独立审核 Patch SHA（见 §9）、完整 `PR-CORRECTNESS` 证据与公开 capability 面；无未关闭 Blocker / Major，公开协议面无 `arm` / `disarm` / `tick` / `advance_iso`。
