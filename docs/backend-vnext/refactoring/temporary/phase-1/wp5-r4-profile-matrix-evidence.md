# WP5 R4 — Canonical Row Hash Required Profile Matrix Evidence

状态：**CONDITIONAL HOLD — awaiting independent external review**

日期：2026-07-25

前置基线：WP5 R3 accepted（`f50015c3439b598b2d5b43afd82b10ceadd070fd`）

Gate：**`PR-CORRECTNESS`** + **`PR-NATIVE`** 回归（`gate.sh correctness` / `gate.sh native`）

---

## 1. 结论与边界

| 项 | 声明 |
| --- | --- |
| 本轮范围 | 正式 `data.canonical-row-hashes.mixed-scalars` 的 4-cell required profile matrix；production harness；matrix planner/executor/aggregation；integration artifact full-chain；provider-matrix `python-reference` / `rust-native` |
| **不是** | R5、Phase 1 exit、`PHASE-EXIT-CONTAINER`、第二个正式 scenario、repository row-hash provider、首次建立 `PR-NATIVE` |
| 审核状态 | **CONDITIONAL HOLD**（不自报外部 PASS） |

### 明确不包括

- WP5 R5、process-crash 正式业务 scenario
- Phase 2 Repository transport / Dolt
- container/build-image、benchmark 声明
- 修改 R3 正式 fixture/golden

---

## 2. Authority

- `implementation-stages.md` §4 Phase 1 / Required scenario/profile matrix / Gate classes
- `fixture-oracle-and-conformance.md`
- `canonical-row-hash-compute-boundary.md`
- `shared-canonical-encoding.md`
- `rust-safety-and-performance-policy.md`
- `wp3-wp5-checkout-plan.md`
- WP4 R4 artifact closure、WP5 R1–R3 Evidence

---

## 3. 4-cell matrix

| # | profile | provider_id | harness 路径 | comparison | cleanup |
| --- | --- | --- | --- | --- | --- |
| 1 | `reference` | `null` | shared-kernel oracle（仅 `table-stream`） | runner exact vs golden | CLEAN |
| 2 | `integration` | `null` | `canonical_row_hashes_v1` → IPC → ArtifactStore → fresh reopen/verify | runner exact vs golden | CLEAN |
| 3 | `provider-matrix` | `python-reference` | 独立 reference oracle | runner exact vs golden | CLEAN |
| 4 | `provider-matrix` | `rust-native` | release wheel native facade | runner exact vs golden | CLEAN |

Provider 闭集（UTF-8 排序）：`python-reference`、`rust-native`。

---

## 4. Reference 独立性

- Harness 仅通过 `VerifiedAssetResolver` 读取 `table-stream`
- 不读取 golden、`owner_closure_assets` oracle anchor
- 不调用 Rust/native `canonical_row_hashes_v1`

---

## 5. Integration artifact full-chain

- Public `gateway_backend.compute.canonical_row_hashes_v1`
- `persist_canonical_row_hash_stream` + `reopen_and_verify_canonical_row_hash_artifact`
- Profile 临时 `LocalArtifactStore` 根目录不进入 plan/result/evidence

---

## 6. Provider coverage inventory

**Executed mapping inventory**（`mapping_inventory.REQUIRED_CASE_IDS`，**22 cases** / 15 kinds：每 kind 非空正例 + **null-slot** + **24-bit 合法 boundary**；overflow/非有限等 boundary **负例**仍由 Rust compute-core / component 承担）：

| case_id | primary_kind |
| --- | --- |
| `mapping-null` | `null` |
| `mapping-boolean` | `boolean` |
| `mapping-signed-integer-32` | `signed-integer` |
| `mapping-unsigned-integer-32` | `unsigned-integer` |
| `mapping-decimal` | `decimal` |
| `mapping-float32` | `float32` |
| `mapping-float64` | `float64` |
| `mapping-string` | `string` |
| `mapping-binary` | `binary` |
| `mapping-bit-8` | `bit` |
| `mapping-date` | `date` |
| `mapping-datetime` | `datetime` |
| `mapping-timestamp` | `timestamp` |
| `mapping-time-duration` | `time-duration` |
| `mapping-anomaly` | `source-literal-anomaly` |
| `mapping-boolean-null-slot` | `boolean` |
| `mapping-string-null-slot` | `string` |
| `mapping-signed-integer-null-slot` | `signed-integer` |
| `mapping-decimal-null-slot` | `decimal` |
| `mapping-float64-null-slot` | `float64` |
| `mapping-unsigned-integer-24-max` | `unsigned-integer` |
| `mapping-signed-integer-24-max` | `signed-integer` |

Runner：`mapping_matrix.run_mapping_provider_matrix()` — 每 case 比较 `table_schema_digest`、`row_count`、`raw_content_digest`、sorted row-hash bytes（python-reference vs rust-native）。

Guard：`assert_mapping_matrix_executed(executed_case_ids)`（`coverage_inventory.py`）+ `test_coverage_inventory_guard` / `test_wp5_r4_mapping_provider_matrix.py`；`GATE_PR_NATIVE=1` 下 `test_pr_native_mapping_provider_matrix_on_wheel`。

---

## 7. Release wheel identity

`gate.sh native` / `native_pr_gate.sh` 在 matrix 前后执行 `assert_wheel_identity_unchanged`；conformance `test_wp5_r4_pr_native.py` 在 `GATE_PR_NATIVE=1` 下验证 rust-native cell。

---

## 8. Gate 命令（离线 locked）

```bash
git diff --check
cd vnext/conformance && uv run --offline --no-sync pytest tests/test_wp5_r4_profile_matrix.py -q
cd vnext/conformance && uv run --offline --no-sync pytest -q
bash vnext/scripts/gate.sh correctness
bash vnext/scripts/gate.sh native
```

（完整原始计数：`gate.sh correctness` → conformance **600 passed, 3 skipped**；backend **246 passed, 3 skipped**；`gate.sh native` → backend pr_native **57 passed** + conformance pr_native **3 passed**。审核者复审日志：`/tmp/review-r4-nullslot-correctness.log`、`/tmp/review-r4-nullslot-native.log`。）

---

## 9. skip / xfail / UNSUPPORTED 审计

- R4 matrix suite：zero skip、zero xfail、zero UNSUPPORTED（`test_formal_matrix_four_cells_all_passed`）
- `pr_native` conformance 测试：仅在 `GATE_PR_NATIVE=1` 时执行（非 xfail）

---

## 10. Patch SHA

```bash
BASE=f50015c3439b598b2d5b43afd82b10ceadd070fd \
  EXPECTED_SHA=92eecf4d8d2d1254115ecfd51afdcb0e59255fe766530ad7de258a80d6af0fc9 \
  bash vnext/scripts/verify-wp5-r4-patch-sha.sh
```

---

## 11. 变更文件清单（摘要）

- `vnext/conformance/src/gateway_conformance/matrix/*`
- `vnext/conformance/src/gateway_conformance/harness/canonical_row_hashes/*`
- `vnext/conformance/tests/test_wp5_r4_*.py`
- `vnext/scripts/verify-wp5-r4-patch-sha.sh`
- `vnext/scripts/gate.sh`、`vnext/scripts/native_pr_gate.sh`
- `vnext/fixtures/schemas/definitions-v1.schema.json`（`providerId`）
- `vnext/conformance/pyproject.toml`、`vnext/conformance/uv.lock`

---

## 12. Deferred

- WP5 R5 Phase 1 exit 聚合
- `PHASE-EXIT-CONTAINER`
- process-crash 正式 scenario

---

## 13. Finding / fix register

| ID | 状态 |
| --- | --- |
| WP5-R4-REV-MAJ-001 | EXIT trap 双环境 restore（backend + conformance matrix extra） |
| WP5-R4-REV-MAJ-002 | conformance cwd 下 capture/assert wheel identity |
| WP5-R4-REV-MIN-001～005 | 见实现与定向测试 |
| WP5-R4-REV-MAJ-003 | reviewer-assisted fix：stale sidecar 测试 `Path \| None` mypy（不改 Evidence PASS 状态） |
| all-kind Blocker | executed mapping inventory 22 cases / 15 kinds；python vs rust 四维对照 |
| null-slot / 24-bit | 5 null-slot + 2×24-bit 合法上界已进 inventory |
| Evidence gate 计数 | reviewer-assisted fix：599→600（审核者 null-slot 复审 correctness） |
| R3 patch SHA | f50015c frozen-path；R3 Evidence cumulative SHA 不变 |

---

EXPECTED_SHA=92eecf4d8d2d1254115ecfd51afdcb0e59255fe766530ad7de258a80d6af0fc9
