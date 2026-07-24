# WP5 R3 — Canonical Row Hash Formal Scenario Evidence

状态：**CONDITIONAL HOLD — awaiting independent external re-review**

日期：2026-07-24

前置基线：WP5 R2 PASS（`97720ea1ce857e320090623372e746b1f12f38fc`）

Gate：**`PR-CORRECTNESS`**（`vnext/scripts/gate.sh correctness`）

---

## 1. 结论与边界

| 项 | 声明 |
| --- | --- |
| 本轮范围 | 正式 `data.canonical-row-hashes.mixed-scalars`（`manifest_schema_version: 2`）；`owner_closure_assets` 隔离 oracle；fixture 投影 strip owner transport；ordering/collision；IPC trailing；writer + install digest 门；formal 治理九字段；`owner-closure-v2` normative digest 向量 |
| **不是** | R4 profile matrix PASSED；`PR-NATIVE` |
| 审核状态 | **CONDITIONAL HOLD**（wire + doc/vector/gate 批次已交付；**不自报 PASS**） |

---

## 2. 复审 / Fix Pack / Doc-Vector 摘要

### Wire / 实现（CLOSED）

| ID | 实现 |
| --- | --- |
| BLK-003 (wire) | closed v1 manifest；v2 含 `owner_closure_assets`；`validate_scenario_manifest` 按版本分发 |
| BLK-004 (transport) | `_manifest_projection_for_fixture` 对 owner 条目不纳入 `size_bytes`/`raw_sha256` |
| MAJ-007 | `vnext/conformance` + `--extra writer`；自动可逆路径；`--install` published digest 门 — **待审方按 §3 Writer 复现签字** |
| MAJ-009 | owner 排序/唯一；`logical_name` 跨集合冲突 fail-closed |
| MIN-010 | IPC 任意 trailing 拒绝 |
| BLK-001/002、MAJ-003/006/008、MIN-001/008/009、ADD-005 | 见历史 Evidence 行（不重开） |

### Doc / vector / gate（本轮 residual → 实现侧 CLOSED，待重审）

| ID | 实现 |
| --- | --- |
| BLK-003 (governance) | formal 页首 `1 \| 2`；§3 v2 schema；§4 v1 示例与 §4.0 v2；§10 taxonomy 九字段 + `semantic_change` |
| BLK-004 (vector) | `scenario-digest/v1` case `owner-closure-v2`；Python+Rust 复算固定 `collection_frame` |
| MAJ-010 | `gate.sh` 预装 `--extra writer`；writer pytest 无 skip、无内联 `uv sync` |
| MIN-011 | writer 子进程 `uv run --offline --no-sync --extra writer`（禁止隐式 sync） |

---

## 3. Closure 权威

- Harness 可见 input：仅 `table-stream`
- Oracle anchor：`owner_closure_assets` / `input/row-hash-oracle-anchor.json`（validator-only）
- Row identity：`arrow_row_hash_oracle`（shared-kernel + PyArrow）

### 固定 digest（正式 scenario）

| 字段 | 值 |
| --- | --- |
| `manifest_schema_version` | `2` |
| `input_digest` | `sha256:3f3bc9791793bb3cb435eb75e0c566064026012a82e3866803acd8702892d995` |
| `fixture_content_digest` | `sha256:1f7361b145cc9c353b3ada8577123de4d632936ebf7ebfde0e496220869aaf09` |
| golden `content_digest` | `sha256:9ca39767f4f7e685da2d91699681b988e69fcc6ee9ce4d90e1634b487f81f420` |
| anchor `raw_sha256` | `sha256:e1eea51ea97b70ae0f12d9ec0df8c1cd946f3cafe83baf702342c886efd4280d`（461 B pretty JSON） |

### Writer 复现（offline，非 pytest）

```bash
cd vnext/conformance
uv sync --locked --offline --extra writer --reinstall-package gateway-compute-python
uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py

# 扁平 base（自动追加 data/canonical-row-hashes/mixed-scalars）
uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py --output-dir /tmp/wp5-r3-formal

# 可选：比对 published digest 后安装
uv run --offline --no-sync --extra writer python ../scripts/write-wp5-r3-formal-scenario.py --output-dir /tmp/wp5-r3-formal --install
```

---

## 4. 验证

```bash
cd vnext/conformance && uv run pytest tests/test_scenario_digest_vectors.py tests/test_wp5_r3_formal_canonical_row_hash_scenario.py -q
cd vnext/conformance && uv run pytest -q
cd vnext/rust && cargo test scenario_digest_preimage_vectors_match_rust_oracle --locked --offline
bash vnext/scripts/gate.sh correctness
```

---

## 5. Patch SHA

```bash
BASE=97720ea1ce857e320090623372e746b1f12f38fc \
  EXPECTED_SHA=551bfd6694d330f977ff975a56b943ad4bbcf7cc5cb59a16870dd086e60d2cdd \
  bash vnext/scripts/verify-wp5-r3-patch-sha.sh
```

---

## 6. Finding register

| ID | 状态 |
| --- | --- |
| WP5-R3 wire (BLK-003/004 transport, MAJ-007/009, MIN-010) | 实现侧 **CLOSED（wire）**；**待独立重审** |
| WP5-R3 doc-vector (governance BLK-003, vector BLK-004, MAJ-010) | 实现侧 **CLOSED**；**待独立重审** |
| MIN-011 (`uv run --no-sync`) | 实现侧 **CLOSED** |
| MAJ-007 writer 复现签字 | **待审方按 §3 执行** |
| R4 matrix | deferred |

**注记（ADD-EV-001）：** 外部 HOLD 的 doc/vector/gate 项与 wire 项分列；勿将「wire 已修」等同于全部 BLK 对外闭合。
