# WP4 R4 — Artifact/Data-Path Walking-Skeleton Closure Evidence

状态：R4 evidence — **sign-off passed**（实现者 pre-commit capture + 审核 findings 闭合 + 全部门禁重跑 2026-07-23）

日期：2026-07-23

前置基线：[wp4-r3-ipc-negative-evidence.md](wp4-r3-ipc-negative-evidence.md)

Gate：**`PR-NATIVE`**（`vnext/scripts/gate.sh native`）；回归 **`PR-CORRECTNESS`**

---

## 1. 结论与边界

**WP4 R4 artifact/data-path walking-skeleton closure sign-off passed; ready to enter WP5.**

| 项 | 声明 |
| --- | --- |
| 闭合范围 | `facade → PyO3 → Rust → ArtifactRef → reopen` 全链路；首次正式 `gate.sh native` / `PR-NATIVE` |
| Gate | `PR-NATIVE`（release wheel + native-kernel component + artifact full-chain targeted suite） |
| **不是** | Phase 1 complete、WP5 scenario/profile/container、`PHASE-EXIT-CONTAINER` |
| 生产语义 delta | 无 Rust core / IPC writer 行为变更；新增 PR-NATIVE gate、全链路测试与 evidence |
| 审核状态 | B1/M1/M3/m1 已闭合；全部门禁 exit 0（§10.2） |

---

## 2. R3 基线

| 项 | 值 |
| --- | --- |
| baseline | `6bb0606dea4ea1eb5097ccdbff98112e97e4b936` |
| subject | `fix(vnext): close WP4 R3 IPC negative suite review` |
| `git merge-base --is-ancestor 6bb0606... HEAD` | exit 0 |

---

## 3. HEAD、branch、worktree 与 patch identity

| 项 | 值 |
| --- | --- |
| implementation HEAD | `d482385bb0da9ff95ee2e7ed129b67e1e5125100` |
| branch | `main` |
| worktree | R4 gate/tests/scripts + 本 evidence |
| deterministic non-evidence patch SHA-256 | `e58e96c81bcd6b5025fb1a926a376d674e58d8f298d5adc96a895c64c3dc51ee` |
| patch SHA 算法 | `git diff 6bb0606dea4ea1eb5097ccdbff98112e97e4b936 -- . ':!docs/backend-vnext/refactoring/temporary/phase-1/wp4-r4-artifact-path-closure.md' \| sha256sum`（排除本 evidence 文件） |
| `git diff --check` | exit 0 |
| lockfile delta vs R3 | 无（`uv.lock` / `Cargo.lock` 无变更） |
| source-tree `.so` 污染（gate 后） | 无（`gateway-compute-python/python/**` 干净） |

---

## 4. Authority 清单与冲突处理

| Authority | 审核结果 |
| --- | --- |
| `wp3-wp5-checkout-plan.md` §2/§3/§5 | R4 = 首次 `PR-NATIVE`；WP5 defer |
| `implementation-stages.md` §4 | Gate classes、Artifact/FFI/GIL/stream determinism 矩阵 |
| `canonical-row-hash-compute-boundary.md` §5–§10 | IPC round-trip、raw vs semantic 分离 |
| `contract-taxonomy-and-ownership.md` | IPC 在 capability；`LocalArtifactStore` 在 infrastructure |
| `wp4-r1/r2/r3 evidence` | 组件能力复用；R4 闭合全链路 |
| `wp3-r5-kernel-native-signoff.md` | native-kernel ≠ PR-NATIVE；R4 首次 native gate |

冲突处理：未修改 canonical encoding、normative vectors、ArtifactRef wire schema。lockfile 无变更。

---

## 5. R4 交付物清单

| 路径 | 动作 |
| --- | --- |
| `vnext/scripts/gate.sh` | 实现 `native` 分支，委托 `native_pr_gate.sh` |
| `vnext/scripts/native_pr_gate.sh` | **新增** PR-NATIVE gate：release wheel、module origin、component probes、`pr_native` suite、EXIT trap/restore + trap regression |
| `vnext/backend/pyproject.toml` | 新增 `pr_native` pytest marker；mypy override `gateway_compute.exceptions` |
| `vnext/backend/tests/pr_native_support.py` | **新增** 全链路 helper、`run_full_chain`、独立 oracle、`assert_public_boundary_sanitized` |
| `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain.py` | **新增** 成功矩阵（permutation、fresh reopen、multi-batch input probe 等） |
| `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain_negative.py` | **新增/扩展** 失败矩阵（facade failure、publish effect、store/reopen 拒绝、public boundary） |
| `vnext/backend/tests/test_pr_native_wheel_origin.py` | **新增** gate 下 wheel module origin 探针 |
| `vnext/backend/tests/test_canonical_row_hash_artifact_roundtrip.py` | 标记 `pr_native` |
| 本 evidence | 定稿 sign-off |

Rust workspace：无 production semantic 变更。

---

## 6. 全链路调用链证明

| 层 | 生产入口 | 测试 / gate 入口 |
| --- | --- | --- |
| 1. Python facade | `gateway_backend.compute.canonical_row_hashes_v1` | `pr_native_support.run_full_chain` |
| 2. Reader normalization | `gateway_compute._as_record_batch_reader` | `test_facade.py`（correctness gate） |
| 3. Arrow C Stream → Rust | `gateway_compute._canonical_row_hashes_v1_native` | `test_component_*.py`（native gate） |
| 4. Rust compute/sort/digest | `gateway-compute-core` | Rust unit tests（correctness gate） |
| 5. Result stream | PyO3 export → `RecordBatchReader` | full-chain tests |
| 6. IPC writer | `write_row_hash_ipc_stream` | roundtrip + full-chain |
| 7. Publish 前验证 | `_verify_ipc_bytes_match_content_manifest` | publish reject + `put_calls == 0` |
| 8. ArtifactStore.put | `put_with_built_manifest` | InMemory + LocalArtifactStore |
| 9. ArtifactRef | `artifacts/types.py` | location-independence tests |
| 10. Fresh reopen | `reopen_and_verify_canonical_row_hash_artifact` | `test_fresh_local_store_instance_reopen_full_chain` |
| 11. 全量复验 | size/raw_sha256/schema/sorted hashes/digests | `reopen_and_verify` internals |

---

## 7. 成功矩阵覆盖

| 场景 | 测试 |
| --- | --- |
| empty / one / multi-row | `test_in_memory_round_trip` parametrized |
| true multi-batch input | `test_multi_batch_input_full_chain_preserves_semantic_identity` + `assert_multi_batch_input` |
| duplicate row hashes | `test_duplicate_row_hashes_round_trip` |
| row / field permutation | `test_row_permutation_*` / `test_field_permutation_*` |
| batch partition / chunking | `test_batch_partition_change_*` / `test_semantic_identity_stable_across_chunking` |
| nullable smoke | `test_nullable_string_smoke_full_chain` |
| InMemory + LocalArtifactStore | roundtrip + full-chain |
| fresh LocalArtifactStore reopen | `test_fresh_local_store_instance_reopen_full_chain` |
| 不同 store root 相同 ref JSON | `test_artifact_ref_json_is_location_independent` |
| 独立 oracle cross-check | `assert_independent_table_schema_digest_oracle` / `test_table_schema_digest_matches_compute_result` |
| ref 无 host path | `assert_ref_json_has_no_host_paths` |

---

## 8. 失败矩阵与 effect

| 场景 | 异常 / effect | 测试 |
| --- | --- | --- |
| request/schema/version | `ComputeRequestError` + stable envelope | `test_backend_facade_request_schema_invalid_*` |
| unsupported physical type | `ComputeRequestError` `ARROW_TYPE_UNSUPPORTED` | `test_backend_facade_unsupported_physical_type_*` |
| schema mismatch | `ComputeRequestError` `ARROW_SCHEMA_MISMATCH` | `test_backend_facade_schema_mismatch_*` |
| non-null null slot | `CanonicalValueError` or `ARROW_STREAM_IMPORT_FAILED` | `test_backend_facade_non_nullable_null_slot_*` |
| Arrow C Stream import failure | `ComputeRequestError` `ARROW_STREAM_IMPORT_FAILED` + `effect=NONE` | `test_backend_facade_arrow_stream_import_failure_*` |
| invalid Python input | `TypeError` before persist | `test_backend_facade_rejects_invalid_python_input_*` |
| publish row_count mismatch | `CanonicalRowHashIpcError` + `put_calls == 0` | `test_publish_row_count_mismatch_*` |
| publish schema digest mismatch | `CanonicalRowHashIpcError` + `put_calls == 0` | `test_publish_schema_digest_mismatch_*` |
| publish raw_content_digest mismatch | `CanonicalRowHashIpcError` + `put_calls == 0` | `test_publish_raw_content_digest_mismatch_*` |
| publish envelope content_digest mismatch | `ManifestVerificationError` | `test_full_chain_reopen_rejects_envelope_content_digest_mismatch` |
| ArtifactStore.put failure（消毒） | `ManifestVerificationError` 无 path 泄漏 | `test_full_chain_put_failure_sanitizes_os_error` |
| trailing garbage / concatenated IPC | `ManifestVerificationError` / `CanonicalRowHashIpcError` | `test_full_chain_reopen_rejects_trailing_garbage_*` / `test_full_chain_reopen_rejects_concatenated_ipc_stream` |
| compute failure before persist | `ComputeRequestError` + `put_calls == 0` | `test_compute_failure_before_persist_has_no_put_effect` |
| disk tamper / truncate | `ManifestVerificationError` at store layer | corrupt/truncated reopen tests |
| fresh store + disk tamper | `ManifestVerificationError` | `test_fresh_local_store_disk_tamper_rejects_reopen` |
| sidecar / exact identity mismatch | `ManifestVerificationError` | `test_fresh_local_store_sidecar_identity_mismatch` |
| forged ref | `ManifestVerificationError` | forged size/raw_sha256 tests |
| semantic mismatch after locate | `CanonicalRowHashIpcError` | `test_full_chain_reopen_rejects_semantic_mismatch_after_locate` |
| public boundary 无 path/traceback | 消息消毒 | `test_publish_failure_message_has_no_host_paths` + `assert_public_boundary_sanitized` |

R3 IPC 负向套件（37 `def test_` cases）在 `PR-CORRECTNESS` 下持续回归。

---

## 9. `gate.sh native` / PR-NATIVE 执行记录

```bash
bash vnext/scripts/gate.sh native
# exit 0
# native gate passed
```

Gate 内容：

1. `native_pr_exit_trap_regression`（`NATIVE_PR_FORCE_RESTORE_FAIL` EXIT trap）
2. release wheel（maturin `--release`，locked/offline）
3. `uv pip install --force-reinstall` wheel
4. module origin 验证（site-packages，非 source tree）
5. `native_kernel_component.sh wheel-smoke`
6. `native_kernel_component.sh component-pytest`（18 passed）
7. `pytest -m pr_native`（41 collected，41 passed，0 skipped in gate）

Gate 后 `uv sync --reinstall-package gateway-compute-python` 恢复 production install；source tree 无 `.so` 污染。

---

## 10. 验证命令与结果

### 10.1 实现者自报（sign-off capture）

| 命令 | 结果 |
| --- | --- |
| `git diff --check` | exit 0 |
| `bash vnext/scripts/gate.sh correctness` | exit 0；232 passed, 1 skipped |
| `bash vnext/scripts/gate.sh native` | exit 0；41 passed, 0 skipped（gate 内） |
| `cd vnext/backend && uv run pytest -q` | 212 passed, 1 skipped |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 34 files already formatted |
| `mypy` | Success: no issues found in 34 source files |
| `pytest -m pr_native --collect-only` | 41/213 collected |

### 10.2 签署前全量验证（2026-07-23 UTC+8）

| 命令 | 结果 |
| --- | --- |
| `git merge-base --is-ancestor 6bb0606... HEAD` | exit 0 |
| `git diff --check` | exit 0 |
| `bash vnext/scripts/gate.sh correctness` | **exit 0**；232 passed, 1 skipped |
| `bash vnext/scripts/gate.sh native` | **exit 0**；gate 内 `pytest -m pr_native` **41 passed, 0 skipped**（`GATE_PR_NATIVE=1`） |
| `cd vnext/backend && uv run --offline --no-sync pytest -q` | **212 passed, 1 skipped** |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 34 files already formatted |
| `mypy .` | Success: no issues found in 34 source files |
| `cd vnext/shared_kernel && uv run --offline --no-sync pytest -q` | **139 passed** |
| `cargo fmt --all --check` | exit 0 |
| `cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings` | exit 0 |
| `cargo test --locked --offline --workspace --all-targets` | exit 0 |
| `cargo build --locked --offline --workspace --release` | exit 0 |
| `pytest -m pr_native --collect-only` | **41/213 collected** |
| `pytest -m pr_native`（gate 外） | **40 passed, 1 skipped**（wheel-origin skip） |

```bash
cd vnext/backend
uv run --offline --no-sync pytest -q --collect-only -m pr_native
# 41/213 collected

uv run --offline --no-sync pytest -q -m pr_native
# gate 外: 40 passed, 1 skipped
# gate 内 (GATE_PR_NATIVE=1): 41 passed, 0 skipped
```

### 10.3 独立探针（审核者）

| 探针 | 结果 |
| --- | --- |
| 成功全链路 `run_full_chain(LocalArtifactStore)` | `ref.size_bytes=344`, `row_count=2`, `result_jcs len=429` |
| publish schema digest mismatch | `CanonicalRowHashIpcError`, `put_calls=0`, 消息无 path 泄漏 |
| module origin（gate 后 restore） | `site-packages/.../gateway_compute.cpython-314-...so`，非 source tree |
| gate 后 production install 恢复 | `uv sync --reinstall-package gateway-compute-python` → editable source path |
| native-pr EXIT trap regression | body ok/fail + restore fail → exit 99 / 42；tmp 清理 |

---

## 11. Structural performance evidence（轻量）

| 项 | 记录 |
| --- | --- |
| GIL 证据 | WP3 R4/R5 component GIL probes（native gate 内 `component-pytest`） |
| Python materialization | `test_architecture.py` 禁止 IPC 模块 `to_pylist`/`as_py` |
| batch 规模 | full-chain 覆盖 empty / 1 / 2 / 3 row cases |
| numeric 收益 | **未声明** |

---

## 12. findings register

| ID | 严重度 | 状态 | 描述 | 要求 |
| --- | --- | --- | --- | --- |
| B1 | **Blocker** | **CLOSED** | R4 交付物已提交；HEAD > R3 基线 | §3 commit SHA |
| B2 | Blocker | **CLOSED** | 审核者独立验证 | §10.2 全部门禁 exit 0 |
| M1 | **Major** | **CLOSED** | `pr_native` 全链路失败矩阵 8 项缺口已补齐 | §8、§15.2 |
| M2 | **Major** | **CLOSED** | register 已更正 | 本 register |
| M3 | **Major** | **CLOSED** | `native_pr_gate.sh` `NATIVE_PR_FORCE_RESTORE_FAIL` trap regression | §9 step 1 |
| m1 | Minor | **CLOSED** | 弱测试替换为 `test_compute_failure_before_persist_has_no_put_effect` | §8 |
| m2 | Minor | OPEN | roundtrip 与 full_chain 重复覆盖 location-independence | 可接受，建议合并 |
| m3 | Minor | OPEN | multi-batch 输出 IPC 仅断言 `>=1` batch | evidence 已注明输入 multi-batch 探针独立 |
| — | Info | CLOSED | patch SHA 算法统一 | §3 单一命令 |
| — | Info | CLOSED | 架构、scope、生产路径、gate 结构 | 审核通过 |

---

## 13. deferred：WP5、container

| 项 | 归属 |
| --- | --- |
| scenario manifest / runner / golden / harness | WP5 |
| `reference \| integration \| provider-matrix` | WP5 R4 |
| `PHASE-EXIT-CONTAINER` | WP5 R5 |
| Phase 1 complete | WP5 R5 |

---

## 14. 最终结论

WP4 R4 在 R3 基线 `6bb0606...` 上完成 artifact/data-path walking-skeleton closure；`gate.sh correctness` 与 `gate.sh native` 均为 exit 0；B1/M1/M3/m1 已闭合。

**WP4 R4 sign-off passed — ready to enter WP5.**

实现就绪后可进入 WP5 准备；**不是** Phase 1 complete / PR-NATIVE 全 scenario matrix。

---

## 15. 外部审核报告（2026-07-23）

### 15.1 正面项（已通过）

- R3 祖先关系确认；无 lockfile / canonical encoding / ArtifactRef schema 变更
- 生产全链路真实：`run_full_chain` 经 facade → PyO3 C Stream → Rust → IPC → store → reopen；无 Python compute fallback
- 架构边界：facade 无 ArtifactRef；`artifacts/` 不依赖 compute；Rust core 无 fs
- `gate.sh native` 首次正式启用：release wheel、module origin、component-pytest（18）、`pr_native`（41）
- 成功矩阵在 `pr_native` 覆盖：empty/one/multi-row、duplicate、permutation、fresh reopen、nullable smoke、location-independent ref
- 独立 oracle：`table_schema_digest_from_declared_fields` cross-check
- native-pr EXIT trap regression 与 correctness gate `wheel-trap-regression` 对称

### 15.2 严格 `pr_native` 失败矩阵逐项核对

| 要求项 | `pr_native` 全链路 | 仅 cross-gate | 测试 / 位置 |
| --- | --- | --- | --- |
| facade request/schema/version | ✅ | | `test_backend_facade_request_schema_invalid_*` |
| unsupported physical type | ✅ | | `test_backend_facade_unsupported_physical_type_*` |
| schema mismatch | ✅ | | `test_backend_facade_schema_mismatch_*` |
| non-null null slot | ✅ | | `test_backend_facade_non_nullable_null_slot_*` |
| invalid Python input | ✅ | | `test_backend_facade_rejects_invalid_python_input_*` |
| publish row_count mismatch + no put | ✅ | | `test_publish_row_count_mismatch_*` |
| publish table_schema_digest mismatch + no put | ✅ | | `test_publish_schema_digest_mismatch_*` |
| publish raw_content_digest mismatch + no put | ✅ | | `test_publish_raw_content_digest_mismatch_*` |
| publish envelope content_digest mismatch | ✅ | | `test_full_chain_reopen_rejects_envelope_content_digest_mismatch` |
| Arrow C Stream import failure（专用） | ✅ | | `test_backend_facade_arrow_stream_import_failure_*` |
| ArtifactStore.put failure（消毒） | ✅ | | `test_full_chain_put_failure_sanitizes_os_error` |
| corrupt / truncated IPC reopen | ✅ | | full-chain negative |
| trailing garbage / concatenated stream | ✅ | | `test_full_chain_reopen_rejects_trailing_garbage_*` / `concatenated_ipc_stream` |
| forged size_bytes / raw_sha256 | ✅ | | full-chain negative |
| semantic mismatch after locate | ✅ | | `test_full_chain_reopen_rejects_semantic_mismatch_*` |
| fresh store + disk tamper | ✅ | | `test_fresh_local_store_disk_tamper_rejects_reopen` |
| sidecar / exact identity mismatch | ✅ | | `test_fresh_local_store_sidecar_identity_mismatch` |
| compute failure no artifact | ✅ | | `test_compute_failure_before_persist_has_no_put_effect` |
| public boundary 无 path/traceback | ✅ | | `test_publish_failure_message_has_no_host_paths` |

### 15.3 签署决策

```text
B1 CLOSED
M1 CLOSED（严格 pr_native 标准）
M3 CLOSED
m1 CLOSED
→ WP4 R4 sign-off passed
```
