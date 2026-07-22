# Phase 1 WP3–WP5 Checkout 计划

状态：临时实施计划（checkout 拆分与对话边界，**已定稿**）

日期：2026-07-22（修订：gate 命名与顺序）

适用：Phase 1 D3 通过后 → Phase 1 exit 前

Authority：

- [Phase 1 Implementation Design and Delivery Plan](../../formal/plans/phase-1-implementation-design-and-delivery-plan.md)
- [Implementation Stages §4 Phase 1](../../formal/plans/implementation-stages.md)
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md)
- [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md)

前置完成：WP0–WP2（D3 checkpoint）；R6/R7 evidence 人工 sign-off 后再启动 WP3 实现。

## 1. 总体评价

用户提出的 WP3–WP5 checkout 拆分**合理**，与正式计划中「D3 后 Arrow/PyO3 → Artifact → Harness/Scenario → Phase 1 exit」的依赖顺序一致。

需在实施中明确以下边界：

| 项 | 说明 |
| --- | --- |
| **正式 `PR-NATIVE` 定义** | `implementation-stages` §Gate classes 规定 **`PR-NATIVE` 必须包含 Artifact round-trip**（IPC write/reopen、raw/semantic identity 等）。WP3 **不得**使用 `PR-NATIVE` 或 `gate.sh native` 名称指代 kernel-only 验收。 |
| **WP3 子门禁** | WP3 R4–R5 使用 **`native-kernel` component checks**（或等价具体检查项列表），归属 `PR-CORRECTNESS` 扩展或独立 component sign-off；**不是**正式 `PR-NATIVE`。 |
| **首次正式 native gate** | **`gate.sh native` / 完整 `PR-NATIVE` 首次执行**在 **WP4 R4**（artifact/data-path walking-skeleton closure）达成后启用。 |
| **Walking skeleton 分层** | WP4 R4 = **artifact/data-path closure**（`facade → PyO3 → Rust → ArtifactRef → reopen`）；**完整 Phase 1 walking skeleton** 仍须等 WP5 harness、scenario 与 required profiles（`reference \| integration \| provider-matrix`）全部通过。 |
| **WP5 R5** | Phase 1 exit 聚合：`PR-CORRECTNESS` + `PR-NATIVE`（回归全矩阵）+ `PHASE-EXIT-CONTAINER`；blocking register 清空。 |

## 2. Gate 命名对照（避免混淆）

| 名称 | 何时启用 | 包含内容 | 不含 |
| --- | --- | --- | --- |
| `gate.sh correctness` / `PR-CORRECTNESS` | WP0 起持续 | schema/vectors/architecture/unit；WP3+ 可含 **native-kernel component** 用例 | Artifact round-trip、scenario matrix |
| **`native-kernel` component sign-off** | WP3 R5 | GIL、failure mapping、stream determinism、Arrow mapping、wheel smoke；**显式声明非 PR-NATIVE** | Artifact IPC/reopen、正式 `gate.sh native` |
| **`gate.sh native` / `PR-NATIVE`** | **WP4 R4 首次** | release wheel、Arrow C Stream/PyO3、GIL/failure、**artifact round-trip**、stream determinism | scenario profiles、container |
| `PHASE-EXIT-CONTAINER` | WP5 R5 | pinned image、wheel-in-image、health/smoke、immutable build identity | — |

## 3. 推荐实施顺序（含跨 WP 依赖）

```text
WP3 R1 → WP3 R2 → WP3 R3 → WP3 R4
                              ↓
         WP3 R5：kernel-native component sign-off
               （不是正式 PR-NATIVE；不启用 gate.sh native）
                              ↓
         WP4 R1 → WP4 R2 → WP4 R3
                              ↓
         WP4 R4：artifact/data-path walking-skeleton closure
               首次执行完整 gate.sh native / PR-NATIVE
                              ↓
WP5 R1 → WP5 R2 → WP5 R3 → WP5 R4 → WP5 R5
```

WP3 R5 安排在 WP4 之前：对 **kernel 组件**做 sign-off 与 evidence 归档，**不**声称已通过正式 `PR-NATIVE`。WP4 R4 才是 native gate 的权威首次通过点。

## 4. WP3 — Arrow / PyO3

目标：正式 `canonical_row_hashes_v1` kernel；`gateway-compute-core` 首次依赖 `gateway-shared-kernel`；替换 bootstrap `to_pylist()` demo。

| Checkout | 内容 | 主要交付 | Gate / Evidence |
| --- | --- | --- | --- |
| **R1** | 详细设计、API/error registry、Arrow mapping v1、依赖与安全审计 | `wp3-r1-arrow-pyo3-design.md`、error registry、mapping 矩阵、dependency inventory 草稿 | design review |
| **R2** | Rust core：row hash / sort / table digest | `gateway-compute-core` 依赖 shared-kernel；Rust 单元/contract 测试；内存 Arrow stream fixtures | `PR-CORRECTNESS` |
| **R3** | Arrow C Stream / PyO3 adapter / Python facade | `gateway-compute-python`；`RecordBatchReader` 统一；禁止 `to_pylist`/generator/combine_chunks | `PR-CORRECTNESS` + architecture |
| **R4** | GIL、failure mapping、stream determinism、kernel component tests | GIL 探针；stable failure；empty/multi-batch/duplicate row hash；component 级 wheel smoke | `PR-CORRECTNESS` + **native-kernel component**（**非 PR-NATIVE**） |
| **R5** | kernel-native component sign-off 与 evidence | `wp3-r5-kernel-native-signoff.md`；dependency inventory 定稿；**不**扩展 `gate.sh native` | **native-kernel sign-off**（**非 PR-NATIVE**） |

**R1 不做**：实现代码、Artifact IPC、scenario runner。

**WP3 全程不做**：`gate.sh native` 实现、正式 `PR-NATIVE` 宣称、scenario YAML、container image、numeric performance claim。

## 5. WP4 — Artifact

目标：location-independent `ArtifactRef`；Arrow IPC write/reopen；raw IPC hash 与 semantic content digest 分离（[Canonical Row Hash Boundary §Artifact](../../formal/contracts/canonical-row-hash-compute-boundary.md)）。

| Checkout | 内容 | 主要交付 | Gate / Evidence |
| --- | --- | --- | --- |
| **R1** | ArtifactRef / manifest / identity API | artifact 类型与 manifest schema；无 host path | `PR-CORRECTNESS` |
| **R2** | Arrow IPC write/reopen 与 raw/semantic identity | IPC writer/reader；size/raw_sha256 + semantic digest 复验 | `PR-CORRECTNESS`（组件单测） |
| **R3** | corrupt / truncated / mismatch 负向验证 | 负向测试套件 | `PR-CORRECTNESS` |
| **R4** | artifact/data-path walking-skeleton closure | `facade → PyO3 → Rust → ArtifactRef → reopen` 全链路；`wp4-r4-artifact-path-closure.md` | **首次 `gate.sh native` / 完整 `PR-NATIVE`** |

WP4 R2–R3 的 IPC 测试在 `PR-CORRECTNESS` 下验收组件行为；**含 artifact round-trip 的正式 `PR-NATIVE` 仅在 R4 与 `gate.sh native` 一并启用**。

## 6. WP5 — Harness / Scenario

目标：scenario oracle root、runner authority、真实 `canonical-row-hash` data scenario、Phase 1 exit。

| Checkout | 内容 | 主要交付 | Gate / Evidence |
| --- | --- | --- | --- |
| **R1** | scenario / golden / protocol / result schema 与 strict closure | scenario 相关 schema；strict YAML/JSON 校验器 | `PR-CORRECTNESS` |
| **R2** | runner lifecycle、registry、fake harness、result precedence | 四态 result；harness 不见 golden；runner 唯一 compare | `PR-CORRECTNESS` |
| **R3** | 真实 canonical-row-hash data scenario | scenario oracle root 内 `data` scenario；`required_profiles[]` | `PR-CORRECTNESS` + 场景预备 |
| **R4** | `reference \| integration \| provider-matrix` 全矩阵 | 三方 profile 全绿；zero skip/UNSUPPORTED | `PR-CORRECTNESS` + **`PR-NATIVE` 回归**（`gate.sh native` 已存在） |
| **R5** | Phase 1 exit 候选、container evidence、最终 sign-off | `PHASE-EXIT-CONTAINER`；phase ledger；blocking register 清空 | **Phase 1 exit** |

## 7. 对话 / 实施粒度建议

| 策略 | 建议 |
| --- | --- |
| **一个 WP 一个对话** | **不推荐**。 |
| **一个 checkout（R）一个对话** | **推荐**。每轮产出 evidence + 可复现命令。 |
| **R1 设计轮** | 可用 Plan 模式；R2 起再实现。 |
| **可并行** | WP3 R2 与 WP4 R1 设计可在 WP3 R1 后部分并行；合并须满足 §3 顺序。 |
| **新对话必备上下文** | 本文件、当前 checkout、前置 evidence、authority §、gate 命令、本步「不做」 |

## 8. Evidence 命名约定

```text
docs/backend-vnext/refactoring/temporary/phase-1/
  wp3-r1-arrow-pyo3-design.md
  wp3-r2-rust-core-evidence.md
  wp3-r3-pyo3-adapter-evidence.md
  wp3-r4-kernel-component-evidence.md
  wp3-r5-kernel-native-signoff.md
  wp4-r1-artifact-api-evidence.md
  wp4-r2-ipc-identity-evidence.md
  wp4-r3-ipc-negative-evidence.md
  wp4-r4-artifact-path-closure.md      # 含首次 gate.sh native / PR-NATIVE
  wp5-r1-... / wp5-r5-phase1-exit-evidence.md
```

每份 evidence 至少包含：摘要、authority、变更清单、验证命令与输出、使用的 **gate 名称**（明确是否为正式 PR-NATIVE）、人工 review checklist、deferred 项。

## 9. Phase 1 exit 对照（WP5 R5 验收）

来自 `implementation-stages` §4 退出条件（摘要）：

1. Exit commit 的 `PR-CORRECTNESS` 与 `PR-NATIVE` 全部通过（`PR-NATIVE` 自 WP4 R4 起持续回归）
2. `PHASE-EXIT-CONTAINER` 在同一 commit/toolchain/lock identity 通过
3. Required scenario matrix 全部 `PASSED`
4. Python/Rust vectors + Repository consumer 仍全量通过
5. Walking-skeleton artifact 可按 ref 恢复并复验 identity
6. Bootstrap `to_pylist()` demo 不再是 formal path
7. Blocking register 为空
8. Rust workspace / wheel / container evidence 满足 cross-stage policy

## 10. 不在 WP3–WP5 范围

- Phase 2 Repository transport / Dolt integration
- Phase 3+ capability 主链（table_access、projection 等）
- Numeric throughput/latency baseline 或收益声明
- Rayon/parallel、独立 Rust worker/service、Parquet 生产路径
- Vector bless / normative root 自动覆盖
