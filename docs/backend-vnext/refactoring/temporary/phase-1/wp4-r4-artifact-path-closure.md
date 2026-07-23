# WP4 R4 — Artifact/Data-Path Walking-Skeleton Closure Evidence

状态：R4 evidence — **sign-off passed**（外部重审 findings 全部闭合；最终门禁独立重跑 2026-07-23）

日期：2026-07-23

前置基线：[wp4-r3-ipc-negative-evidence.md](wp4-r3-ipc-negative-evidence.md)

Gate：**`PR-NATIVE`**（`vnext/scripts/gate.sh native`）；回归 **`PR-CORRECTNESS`**

---

## 1. 结论与边界

**外部审核结论：** R4-REREVIEW-MAJ-001/002/003 已全部闭合；正式全链路、release wheel 和 evidence 均完成独立复核。

| 项 | 声明 |
| --- | --- |
| 闭合范围 | `facade → PyO3 → Rust → ArtifactRef → reopen` 全链路；首次正式 `gate.sh native` / `PR-NATIVE` |
| Gate | `PR-NATIVE`（单次 release wheel + wheel identity + Rust kernel_component + facade probes + `pr_native` suite） |
| **不是** | Phase 1 complete、WP5 scenario/profile/container、`PHASE-EXIT-CONTAINER` |
| 生产语义 delta | IPC writer 完整公共边界消毒；`combine_chunks` 删除；无 canonical encoding / ArtifactRef schema 变更 |
| 审核状态 | **PASS**；可以进入 WP5 R1，但 WP5 与 Phase 1 exit 尚未完成 |

---

## 2. R3 基线

| 项 | 值 |
| --- | --- |
| baseline | `6bb0606dea4ea1eb5097ccdbff98112e97e4b936` |
| subject | `fix(vnext): close WP4 R3 IPC negative suite review` |
| `git merge-base --is-ancestor 6bb0606... HEAD` | exit 0 |
| 已提交 R4 HEAD（一审） | `f8b1fa202dd4ef1faa679bb66b544536171af1a4` |

---

## 3. HEAD、branch、worktree 与 patch identity

| 项 | 值 |
| --- | --- |
| committed HEAD | `f8b1fa202dd4ef1faa679bb66b544536171af1a4` |
| `git merge-base 6bb0606... HEAD` | `6bb0606dea4ea1eb5097ccdbff98112e97e4b936`（baseline 本身；committed HEAD 为其后代） |
| 二审 + 重审修复 | sign-off 输入快照为 **uncommitted working tree**；审核通过后随唯一 sign-off commit 提交 |
| branch | `main` |
| delivery manifest | sign-off 输入快照：**10 modified + 2 untracked = 12 files**（含本 evidence） |
| deterministic patch SHA-256（含 untracked，排除 evidence） | `6d417e135c5ad116106da7e64ec160dc0bfbb74e64967fd09cc7ef0db410e65a` |

### Patch SHA 算法（双方一致）

```bash
BASE=6bb0606dea4ea1eb5097ccdbff98112e97e4b936
EXCLUDE='docs/backend-vnext/refactoring/temporary/phase-1/wp4-r4-artifact-path-closure.md'

{
  git diff "${BASE}" -- . ":!${EXCLUDE}"
  git ls-files -o --exclude-standard \
    | LC_ALL=C sort \
    | while IFS= read -r path; do
        case "${path}" in ${EXCLUDE}) continue ;; esac
        git diff --no-index /dev/null "${path}" || true
      done
} | sha256sum
```

| 项 | 值 |
| --- | --- |
| `git diff --check` | exit 0 |
| lockfile delta vs R3 | 无（`Cargo.lock` gate 前后无 delta） |
| source-tree `.so` 污染（gate 后） | 无 |

### 交付物 manifest（uncommitted）

| 状态 | 路径 |
| --- | --- |
| M | `vnext/scripts/native_pr_gate.sh` |
| M | `vnext/scripts/native_kernel_component.sh` |
| M | `vnext/scripts/gate.sh` |
| M | `vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py` |
| M | `vnext/backend/tests/pr_native_support.py` |
| M | `vnext/backend/tests/test_architecture.py` |
| M | `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain.py` |
| M | `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain_negative.py` |
| M | `vnext/backend/tests/test_pr_native_wheel_origin.py` |
| M | `docs/.../wp4-r4-artifact-path-closure.md` |
| ?? | `vnext/backend/tests/test_pr_native_gil_progress.py` |
| ?? | `vnext/backend/tests/test_pr_native_mapping_coverage.py` |

---

## 4. Authority 清单与冲突处理

| Authority | 审核结果 |
| --- | --- |
| `wp3-wp5-checkout-plan.md` §2/§3/§5 | R4 = 首次 `PR-NATIVE`；WP5 defer |
| `implementation-stages.md` §4 | Gate classes、Artifact/FFI/GIL/stream determinism 矩阵 |
| `canonical-row-hash-compute-boundary.md` §5–§10 | IPC round-trip、raw vs semantic 分离 |
| `shared-canonical-encoding.md` | semantic digest / JCS 路径未变；未改 digest registry |
| `architecture-and-refactoring-plan.md` | wire 稳定；ArtifactStore 仍在 infrastructure |
| `rust-safety-and-performance-policy.md` | structural performance 证据要求；unsafe/lint policy 回归通过 |
| `contract-taxonomy-and-ownership.md` | IPC 在 capability；`LocalArtifactStore` 在 infrastructure |
| `wp4-r1/r2/r3 evidence` | 组件能力复用；R4 闭合全链路 |
| `wp3-r5-kernel-native-signoff.md` | native-kernel ≠ PR-NATIVE；R4 首次 native gate |

冲突处理：未修改 canonical encoding、normative vectors、ArtifactRef wire schema。lockfile 无变更。

---

## 5. R4 交付物清单

| 路径 | 动作 |
| --- | --- |
| `vnext/scripts/gate.sh` | `native` 分支；`ruff format --check` |
| `vnext/scripts/native_pr_gate.sh` | 单次 wheel install + identity；`maturin --locked --offline`；Rust `kernel_component` |
| `vnext/scripts/native_kernel_component.sh` | `wheel-smoke-installed`（无 nested `uv sync`） |
| `vnext/backend/src/gateway_backend/canonical_row_hash_ipc.py` | IPC writer/reader `ArrowException` 公共边界消毒 |
| `vnext/backend/tests/pr_native_support.py` | 全链路 helper、oracle、`assert_public_boundary_sanitized` |
| `vnext/backend/tests/test_architecture.py` | 禁止 `combine_chunks` 等 materialization |
| `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain.py` | 成功矩阵；chunking raw/semantic |
| `vnext/backend/tests/test_canonical_row_hash_artifact_full_chain_negative.py` | 失败矩阵；PyArrow sibling 参数化消毒 |
| `vnext/backend/tests/test_pr_native_wheel_origin.py` | wheel module origin 探针 |
| `vnext/backend/tests/test_pr_native_gil_progress.py` | **新增** GIL 窗口探针 + 负向 fake-compute |
| `vnext/backend/tests/test_pr_native_mapping_coverage.py` | **新增** wheel mapping coverage（5 kinds） |
| 本 evidence | 外部重审闭合与最终 sign-off capture |

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
| 6. IPC writer | `write_row_hash_ipc_stream`（含 `reader.schema` 在公共边界内） | roundtrip + full-chain + `test_ipc_writer_failure_sanitizes_pyarrow_exceptions` |
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
| chunking raw bytes ≠ semantic digest | `test_chunking_differs_raw_bytes_same_semantic_digest_full_chain` |
| nullable smoke | `test_nullable_string_smoke_full_chain` |
| InMemory + LocalArtifactStore | roundtrip + full-chain |
| fresh LocalArtifactStore reopen | `test_fresh_local_store_instance_reopen_full_chain` |
| 不同 store root 相同 ref JSON | `test_artifact_ref_json_is_location_independent` |
| 独立 oracle cross-check | `assert_independent_table_schema_digest_oracle` / `test_table_schema_digest_matches_compute_result` |
| ref 无 host path | `assert_ref_json_has_no_host_paths` |
| GIL 窗口探针 + 负向控制 | `test_wheel_path_python_thread_progresses_during_compute` / `test_gil_probe_rejects_instant_fake_compute` |
| mapping coverage（wheel） | `test_pr_native_mapping_coverage.py`（5 kinds） |

---

## 8. 失败矩阵与 effect

| 场景 | 异常 / effect | 测试 |
| --- | --- | --- |
| request/schema/version | `ComputeRequestError` + stable envelope | `test_backend_facade_request_schema_invalid_*` |
| unsupported physical type | `ComputeRequestError` `ARROW_TYPE_UNSUPPORTED` | `test_backend_facade_unsupported_physical_type_*` |
| schema mismatch | `ComputeRequestError` `ARROW_SCHEMA_MISMATCH` | `test_backend_facade_schema_mismatch_*` |
| non-null null slot | `ComputeRequestError` `ARROW_STREAM_IMPORT_FAILED` | `test_backend_facade_non_nullable_null_slot_*` |
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
| IPC writer PyArrow sibling 异常消毒 | `CanonicalRowHashIpcError` 无 path；覆盖 `ArrowInvalid`/`ArrowMemoryError`/`ArrowTypeError`/`ArrowCapacityError` | `test_ipc_writer_failure_sanitizes_pyarrow_exceptions`（6 cases：sink/stream/finalize） |
| IPC reader PyArrow sibling 异常消毒 | `CanonicalRowHashIpcError` 无 path；覆盖 `BufferReader`/`from_batches` | `test_ipc_reader_failure_sanitizes_pyarrow_exceptions` |
| public boundary 无 path/traceback | 消息消毒 | `test_publish_failure_message_has_no_host_paths` + `assert_public_boundary_sanitized` |

R3 IPC 负向套件（37 `def test_` cases）在 `PR-CORRECTNESS` 下持续回归。

---

## 9. `gate.sh native` / PR-NATIVE 执行记录

```bash
bash vnext/scripts/gate.sh native
# exit 0 — native gate passed
```

Gate 步骤（重审后）：

1. `native_pr_exit_trap_regression`
2. `maturin build --release --locked --offline`（`CARGO_NET_OFFLINE=true`）
3. 单次 wheel install + wheel identity capture
4. `wheel-smoke-installed`（无 nested `uv sync`）
5. `cargo test --package gateway-compute-python-impl kernel_component`（8 passed）
6. `component-pytest`（18 passed）
7. `pytest -m pr_native`（**57 collected，57 passed，0 skipped** in gate）

---

## 10. 验证命令与结果

### 10.1 实现者自报（重审 Major 修复 capture，未 commit）

| 命令 | 结果 |
| --- | --- |
| `git diff --check` | exit 0 |
| `bash vnext/scripts/gate.sh correctness` | exit 0；**246 passed, 3 skipped** |
| `bash vnext/scripts/gate.sh native` | exit 0；gate 内 **57 passed, 0 skipped** |
| `cd vnext/backend && uv run pytest -q` | **226 passed, 3 skipped** |
| `ruff check .` | All checks passed |
| `ruff format --check src tests` | **36 files already formatted**（exit 0） |
| `mypy` | Success: 36 source files |
| `pytest -m pr_native --collect-only` | **57/229 collected** |
| `pytest -m pr_native`（gate 外） | **54 passed, 3 skipped** |
| `cd vnext/shared_kernel && pytest -q` | 139 passed |
| `cargo fmt/clippy/test/build` | exit 0 |

### 10.2 外部审核者独立签署验证

| 验证 | 独立结果 |
| --- | --- |
| §3 deterministic patch SHA | `6d417e135c5ad116106da7e64ec160dc0bfbb74e64967fd09cc7ef0db410e65a`，一致 |
| `bash vnext/scripts/gate.sh correctness` | exit 0；**246 passed, 3 skipped** |
| `bash vnext/scripts/gate.sh native` | exit 0；**57 passed, 0 skipped** |
| wheel identity | Rust kernel probes、component pytest、PR-NATIVE suite 后均不变 |
| backend pytest / ruff / format / mypy | **226 passed, 3 skipped**；其余全部通过 |
| shared-kernel pytest | **139 passed** |
| IPC writer/reader boundary targeted | **8 passed**；独立 `BufferReader` 反证返回 `CanonicalRowHashIpcError` 且无 path 泄漏 |
| GIL 负向控制 | fake compute `delta_ticks < MIN_PROGRESS_TICKS`；正式 wheel compute 通过 |
| structural probe | `16384 / 131072 / 131352 / 133512`，与 §11 一致 |
| gate 后恢复 / lock / 污染 | production install 已恢复；lock SHA-256 无变化；无 source-tree wheel/IPC/sidecar/`.so` 污染 |

---

## 11. Structural performance evidence（轻量）

### 11.1 版本与 workload

| 项 | 值 |
| --- | --- |
| PyArrow | `25.0.0`（`uv.lock`） |
| Rust toolchain | `rustc 1.97.0 (2d8144b78 2026-07-07)` |
| `gateway-compute-core` | `0.1.0` |
| GIL 探针 workload | `row_count=4096`；`batch_layout=16×256`；列 `int32` non-null `v`（`test_pr_native_gil_progress._large_multi_batch_reader`） |
| Python materialization count | **0**（`test_architecture.py` 禁止 `to_pylist`/`as_py`/`combine_chunks`） |
| GIL release | Rust `kernel_component`（8 tests）；wheel 窗口探针 `test_pr_native_gil_progress.py` |
| numeric 收益 | **未声明** |

### 11.2 Memory breakdown（4096-row GIL 探针规模）

| 分量 | 可复算上界 / 公式 | 实测（探针脚本） |
| --- | --- | --- |
| Input Arrow buffers（4096-row GIL input） | `4096 × 4 B = 16,384 B`（int32 values；non-null 无 validity bitmap） | `sum(batch.nbytes) = 16,384 B` |
| Row-hash vector / sort storage | `4096 × 32 B = 131,072 B`（Rust sorted hash 向量上界） | `131,072 B`（`row_count × ROW_HASH_BYTE_WIDTH`） |
| **Output IPC — production native compute**（单 batch） | schema + 4096 hashes + EOS | **`131,352 B`** |
| Output IPC — synthetic 16-batch row_hash reader（非 production 路径；仅说明 batch 布局不影响 semantic） | 对照 | `133,512 B`（勿与 production 混淆） |

探针脚本（实现者 capture，非 CI 测试；审核者可复制执行）：

```bash
cd vnext/backend
PYTHONPATH=tests uv run --offline --no-sync python - <<'PY'
import pyarrow as pa
from test_pr_native_gil_progress import _large_multi_batch_reader, _request_jcs
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.canonical_row_hash_ipc import ROW_HASH_BYTE_WIDTH, write_row_hash_ipc_stream

fields = [{
    "name": "v",
    "nullable": False,
    "semantic_type": {"kind": "signed-integer", "bits": 32},
}]
reader = _large_multi_batch_reader(4096)
input_nbytes = sum(b.nbytes for b in reader.read_all())
reader = _large_multi_batch_reader(4096)
output, _ = canonical_row_hashes_v1(_request_jcs(fields), reader)
production_ipc_bytes = len(write_row_hash_ipc_stream(output))

out_schema = pa.schema([pa.field("row_hash", pa.binary(32), nullable=False)])
hash_batches = []
remaining = 4096
while remaining > 0:
    chunk = min(256, remaining)
    hash_batches.append(
        pa.record_batch(
            [pa.array([b"\x00" * 32] * chunk, type=pa.binary(32))],
            schema=out_schema,
        )
    )
    remaining -= chunk
synthetic_ipc_bytes = len(
    write_row_hash_ipc_stream(pa.RecordBatchReader.from_batches(out_schema, hash_batches))
)

print("input_nbytes_sum", input_nbytes)
print("hash_sort_upper_bound", 4096 * ROW_HASH_BYTE_WIDTH)
print("production_ipc_bytes", production_ipc_bytes)
print("synthetic_ipc_bytes", synthetic_ipc_bytes)
PY
# 期望输出：
# input_nbytes_sum 16384
# hash_sort_upper_bound 131072
# production_ipc_bytes 131352
# synthetic_ipc_bytes 133512
```

### 11.3 小样本 full-chain IPC 探针（对照）

| 探针 | 结果 |
| --- | --- |
| 2-row boolean full-chain style IPC | `write_row_hash_ipc_stream` → **344 B**（与一审 `ref.size_bytes=344` 探针一致） |

---

## 12. findings register

### 12.1 外部重审 Major（2026-07-23）

| ID | 严重度 | 状态 | 描述 |
| --- | --- | --- | --- |
| R4-REREVIEW-MAJ-001 | Major | **CLOSED** | GIL 探针 barrier 窗口 + 负向 fake-compute 控制（外部重审确认） |
| R4-REREVIEW-MAJ-002 | Major | **CLOSED** | IPC reader/writer `ArrowException` 完整公共边界（含 `BufferReader`/`from_batches`）+ sibling 参数化回归；外部反证通过 |
| R4-REREVIEW-MAJ-003 | Major | **CLOSED** | merge-base、完整 authority、可执行探针、production vs synthetic IPC 区分；外部复算一致 |

### 12.2 二审 findings（历史）

| ID | 状态 |
| --- | --- |
| B-R4-001 | **CLOSED**（重审确认） |
| B-R4-002 Rust | **CLOSED**（重审确认） |
| M-R4-001 | **CLOSED**（重审确认） |
| M-R4-003 | **CLOSED**（重审确认） |
| M-R4-002 | **SUPERSEDED** by R4-REREVIEW-MAJ-002 |
| M-R4-004 | **SUPERSEDED** by R4-REREVIEW-MAJ-003 |
| MIN-R4-001/002 | **CLOSED**（重审确认） |
| m2 / m3 | **WONTFIX** |

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

WP4 R4 一审已 commit（`f8b1fa2`）；二审与重审 findings 已全部闭合；`gate.sh correctness` 与 `gate.sh native` 均由外部审核者独立重跑并通过。

**WP4 R4 artifact/data-path walking-skeleton closure sign-off passed; ready to enter WP5 R1.**

可以进入 WP5 R1；WP5 scenario、runner、golden、required profile matrix 和 container 仍未完成。当前 `PR-NATIVE` 可以通过，但仍不是 Phase 1 complete。

---

## 15. 签署决策

```text
R4-REREVIEW-MAJ-001/002/003: CLOSED（外部重审确认）
→ PASS
→ 修复与本 evidence 随唯一 sign-off commit 提交
→ 可以进入 WP5 R1；不得宣称 Phase 1 complete
```
