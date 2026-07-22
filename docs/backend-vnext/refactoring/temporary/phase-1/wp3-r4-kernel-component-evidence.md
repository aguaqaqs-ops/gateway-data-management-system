# WP3 R4 — Kernel Component GIL / Failure / Determinism Evidence

状态：R4 implementation evidence（post-review remediation）

日期：2026-07-22

Authority：

- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md)（rev.3.1）§6、§8、§9、§10
- [WP3 R2 Rust Core Evidence](wp3-r2-rust-core-evidence.md)
- [WP3 R3 PyO3 Adapter Evidence](wp3-r3-pyo3-adapter-evidence.md)（round 6 + inherited doc fix）
- [WP3–WP5 Checkout 计划](wp3-wp5-checkout-plan.md) §2、§4、§8
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md) §5–§7
- [Rust Safety and Performance Policy](../../formal/policies/rust-safety-and-performance-policy.md)

Gate：**`PR-CORRECTNESS` + native-kernel component**；**非** `PR-NATIVE` / `gate.sh native`

## 1. Summary

完成 WP3 R4 kernel component 级验证：合规 `test-probes` feature（非 hooks crate）、GIL 并发探针、import/compute/export panic→`NATIVE_PANIC` 矩阵、facade 路径 failure mapping / determinism 补全、release wheel smoke（empty + multi-batch + duplicate），以及 `gate.sh correctness` native-kernel component 段扩展。

## 2. Identity / worktree

| 项 | 值 |
| --- | --- |
| 基线（R3 sign-off） | `6b97ce8bcc08deb39c7bcbb6560cf79663feba5d` |
| merge-base（baseline..worktree） | `6b97ce8bcc08deb39c7bcbb6560cf79663feba5d` |
| 提交前 HEAD | `6b97ce8bcc08deb39c7bcbb6560cf79663feba5d`（R4 为单 commit worktree） |
| tracked patch SHA-256 | 见 commit 时 `git diff 6b97ce8..HEAD` 输出 |
| Normative fixture SHA | `8220e7e587b87a446803ac579e81a8d8b99a0f98cd29d1152c7793442f235c77`（未变） |

## 3. R3 inherited correction

| 项 | 修正 |
| --- | --- |
| R3 remediation 表 workspace 计数 | `224` → **`226`**（[wp3-r3-pyo3-adapter-evidence.md](wp3-r3-pyo3-adapter-evidence.md) L245） |
| 归属 | **inherited R3 documentation correction**；**不计入** R4 新增测试 |
| R4 workspace 增量 | R3 226 → R4 **234**（+8：panic 3、GIL 2、adapter 2、impl panic boundary 1） |

## 4. 变更清单

### 新增

- `vnext/rust/gateway-compute-python-impl/src/test_probes.rs`
- `vnext/rust/gateway-compute-python/tests/common/mod.rs`
- `vnext/rust/gateway-compute-python/tests/adapter_panic_matrix.rs`
- `vnext/rust/gateway-compute-python/tests/gil_probe.rs`
- `vnext/rust/gateway-compute-python/tests/test_component_support.py`
- `vnext/rust/gateway-compute-python/tests/test_component_gil.py`
- `vnext/rust/gateway-compute-python/tests/test_component_failure.py`
- `vnext/rust/gateway-compute-python/tests/test_component_determinism.py`
- `vnext/scripts/native_kernel_component.sh`
- `docs/.../wp3-r4-kernel-component-evidence.md`

### 修改

- `vnext/rust/gateway-compute-python-impl/{Cargo.toml,src/adapter.rs,src/lib.rs}`
- `vnext/rust/gateway-compute-python/Cargo.toml`
- `vnext/rust/gateway-compute-python/tests/adapter_errors.rs`
- `vnext/rust/gateway-compute-python/tests/test_facade.py`（failure envelope 完整断言）
- `vnext/scripts/gate.sh`
- `docs/.../wp3-r3-pyo3-adapter-evidence.md`（inherited 224→226）

## 5. GIL 区间与探针机制

```text
[GIL attached]  facade: _as_record_batch_reader
[GIL attached]  PyRecordBatchReader::extract → into_reader()（import，含 panic boundary）
[GIL detached]  parse_request + canonical_row_hashes_v1（含 panic boundary）
[GIL attached]  PyRecordBatchReader::new → into_pyarrow()（export，含 panic boundary）
```

| 探针 | 机制 | release wheel |
| --- | --- | --- |
| Detached compute | Python `threading` progress + Rust `gil_probe.rs` 并发 `Python::attach` | 纯测试 target |
| Import/export smoke | `test_empty_table_import_export_smoke` | 纯测试 |
| Panic 三段 | `test-probes` feature + `adapter_panic_matrix.rs` | 无 feature 时不编译 |

运行时证据：

- Python：`test_component_gil.py::test_concurrent_python_thread_makes_progress_during_compute`（progress ≥ 1000）
- Rust：`gil_probe.rs::concurrent_python_thread_makes_progress_during_native_compute`

## 6. Fault-injection 隔离设计

| 检查项 | 状态 |
| --- | --- |
| production cdylib 无 `_test_*` / `_TEST_*` | ✅ |
| `cargo build --workspace --release` 无 test-probes | ✅ |
| `nm -D target/release/libgateway_compute.so` 无 test/probe 符号 | ✅ |
| panic 仅在 `test_probes.rs` + `#[cfg(test)]` adapter 单测 | ✅ |
| 无 hooks crate / 无 production global callback seam | ✅ |
| gate 结束 installed hooks `[]` | ✅ |

机制：`gateway-compute-python-impl` feature `test-probes` + thread-local `PanicStage`；`adapter_panic_matrix` 使用 `required-features = ["test-probes"]`。

## 7. Failure mapping matrix

| Code | Facade/component | Adapter projection | Envelope exact bytes |
| --- | --- | --- | --- |
| `COMPUTE_REQUEST_SCHEMA_INVALID` | `test_facade.py` | `adapter_errors.rs` | ✅ |
| `COMPUTE_CONTRACT_VERSION_UNSUPPORTED` | `test_component_failure.py` | `adapter_errors.rs` native | ✅ |
| `COMPUTE_CANONICAL_VERSION_UNSUPPORTED` | `test_component_failure.py` | — | ✅ |
| `COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED` | `test_component_failure.py` | — | ✅ |
| `ARROW_STREAM_IMPORT_FAILED` | — | `adapter_errors.rs` native | ✅ |
| `ARROW_TYPE_UNSUPPORTED` | `test_facade.py` + precedence | — | ✅ |
| `ARROW_SCHEMA_MISMATCH` | `test_facade.py` + precedence | — | ✅ |
| `CANONICAL_VALUE_INVALID` | `test_facade.py` + `test_component_failure.py` | `adapter_errors.rs` | ✅ |
| `ROW_HASH_COMPUTE_FAILED` | — | `adapter_errors.rs` | ✅ |
| `RESOURCE_LIMIT_EXCEEDED` | — | `adapter_errors.rs` | ✅（投影；无端到端触发，capability 未实现） |
| `ARROW_STREAM_EXPORT_FAILED` | — | `adapter_errors.rs` | ✅（投影；真实 export 错误 defer） |
| `NATIVE_PANIC` | — | `adapter_panic_matrix.rs` + `adapter_errors.rs` | ✅ |

Precedence：`large_utf8` → `ARROW_TYPE_UNSUPPORTED`；`utf8` + declared `binary` → `ARROW_SCHEMA_MISMATCH`（`test_component_failure.py`）。

## 8. Stream determinism matrix（facade → extension → core）

| Case | 测试 |
| --- | --- |
| empty table | `test_facade.py` + wheel smoke |
| zero-field table | `test_facade.py` |
| one-row | `test_facade.py` |
| multi-batch / partition | `test_facade.py` + `test_component_determinism.py` |
| duplicate row hashes | `test_component_determinism.py` + wheel smoke |
| input row permutation | `test_component_determinism.py` |
| Arrow field-order permutation | `test_component_determinism.py` |
| output lexicographic sort | `test_component_determinism.py` |
| zero batches, declared schema | `test_component_determinism.py` |
| serial ≥2 byte-identical | `test_facade.py` + `test_component_determinism.py` |
| digest fields stable | `test_component_determinism.py` |

## 9. Production wheel identity

| 项 | 值 |
| --- | --- |
| 构建命令 | `uv run maturin build --release --manifest-path gateway-compute-python/Cargo.toml --out <tmpdir>/dist` |
| Wheel 文件名 | `gateway_compute_python-0.1.0-cp314-cp314-manylinux_2_34_x86_64.whl` |
| Python ABI | CPython 3.14.6 |
| Platform tag | `manylinux_2_34_x86_64` |
| 安装位置 | `mktemp` 外构建；`uv pip install --force-reinstall <wheel>` |
| Smoke cases | empty + multi-batch(3 rows) + duplicate(2 rows) |
| 恢复 | `uv sync --reinstall-package gateway-compute-python` |
| Wheel 无 test hooks | ✅ |

## 10. Lock identity

| 组件 | 版本 | Lock |
| --- | --- | --- |
| Rust toolchain | 1.97.0 | `vnext/rust/rust-toolchain.toml` |
| pyo3 | 0.29.0 | `vnext/rust/Cargo.lock` |
| pyo3-arrow | 0.19.0 | 同上 |
| arrow-* | 59.1.0 | 同上 |
| Python | 3.14.6 | `vnext/shared_kernel/.python-version` |
| pyarrow | 25.0.0 | `vnext/backend/uv.lock` |
| maturin | 1.14.1 | `gateway-compute-python/pyproject.toml` / `uv.lock` |

## 11. Dependency / native / build-script delta

| 变更 | 说明 |
| --- | --- |
| `gateway-compute-python-impl` feature `test-probes` | 测试专用 panic 注入；不进入 release default features |
| `gateway-compute-python` feature `test-probes` | 透传 impl；`adapter_panic_matrix` `required-features` |
| 无新 workspace member | ✅ |
| 无新 proc-macro / build-script | ✅ |
| `Cargo.lock` | 仅 test-probes feature 解析增量（无新第三方 crate） |

## 12. 验证命令与结果

| 命令 | Exit | 结果 |
| --- | ---: | --- |
| `cargo fmt --check` | 0 | 通过 |
| `cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings` | 0 | 通过 |
| `cargo test --locked --offline --workspace --all-targets --features test-probes` | 0 | **234 passed** |
| `cargo build --locked --offline --workspace --release` | 0 | 通过 |
| `gateway-architecture-check` | 0 | 通过 |
| `native_kernel_component.sh wheel-smoke` | 0 | empty + multi-batch + duplicate |
| `native_kernel_component.sh component-pytest` | 0 | **17 passed** |
| backend production pytest | 0 | **22 passed** |
| `gate.sh correctness` | 0 | 全段绿 |
| `gate.sh native` | 2 | `native gate is not implemented until WP4 R4` |

```bash
cd vnext/rust
cargo fmt --check
cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings
cargo test --locked --offline --workspace --all-targets --features test-probes
cargo build --locked --offline --workspace --release
cargo run --locked --offline -q --bin gateway-architecture-check -- \
  --rust-workspace-root . --vnext-root ..

cd /root/gateway-data-management-system
vnext/scripts/native_kernel_component.sh wheel-smoke
vnext/scripts/native_kernel_component.sh component-pytest

cd vnext/backend
uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python
uv run pytest -q \
  ../rust/gateway-compute-python/tests/test_facade.py \
  ../rust/gateway-compute-python/tests/test_production_extension.py \
  tests/test_canonical_row_hash.py

vnext/scripts/gate.sh correctness
vnext/scripts/gate.sh native   # exit 2 expected
```

## 13. 测试计数

| 层 | 文件 | 计数 |
| --- | --- | ---: |
| Rust adapter errors | `adapter_errors.rs` | 8 |
| Rust panic matrix | `adapter_panic_matrix.rs` | 3 |
| Rust GIL probe | `gil_probe.rs` | 2 |
| Python component GIL | `test_component_gil.py` | 2 |
| Python component failure | `test_component_failure.py` | 6 |
| Python component determinism | `test_component_determinism.py` | 9 |
| **R4 component 小计** | | **17** |
| Python facade（R3） | `test_facade.py` | 19 |
| Python production guard | `test_production_extension.py` | 1 |
| Backend formal | `test_canonical_row_hash.py` | 2 |
| **Rust workspace** | | **234** |

R4 新增 Rust workspace 测试：**8**（相对 R3 226）；其中 inherited doc 不计入。

## 14. Gate 前后状态

| 状态 | gate 前 | gate 后 |
| --- | --- | --- |
| source tree `.so` | 0 | 0 |
| installed hooks | `[]` | `[]` |
| installed extension | production editable | production editable（`uv sync --reinstall-package` 恢复） |

## 15. R4-A1～R4-A8 checklist

| # | 项 | 状态 |
| --- | --- | --- |
| R4-A1 | GIL attached/detached 运行时探针 | ✅ |
| R4-A2 | panic boundary + 合规 fault injection | ✅ |
| R4-A3 | stable failure mapping（facade + adapter） | ✅ |
| R4-A4 | stream determinism component matrix | ✅ |
| R4-A5 | 粗粒度 C Stream 边界 | ✅ |
| R4-A6 | production wheel smoke（empty/multi-batch/duplicate） | ✅ |
| R4-A7 | Rust safety / release inventory | ✅ |
| R4-A8 | Gate 命名边界（非 PR-NATIVE） | ✅ |

## 16. Deferred

| 项 | 归属 |
| --- | --- |
| `RESOURCE_LIMIT_EXCEEDED` 端到端触发 | WP3 R5（capability 未实现） |
| `ARROW_STREAM_EXPORT_FAILED` 真实 export 路径触发 | WP4+（无安全 corrupt IPC） |
| `gate.sh native` / 完整 `PR-NATIVE` | WP4 R4 |
| Artifact IPC / reopen / corrupt IPC | WP4 |
| Scenario YAML / harness / container | WP5 |
| kernel-native component sign-off 归档 | WP3 R5 |

## 17. Remediation mapping（外部审核 → 本轮修复）

| Finding | 修复 |
| --- | --- |
| M1 failure mapping 不完整 | `test_component_failure.py` + `adapter_errors.rs` ROW_HASH + facade envelope 完整断言 |
| M2 determinism matrix 缺口 | `test_component_determinism.py` 补 permutation / field-order / lex sort / declared-schema zero-batch / digest |
| M3 wheel smoke 仅 empty | `native_kernel_component.sh` 增 multi-batch + duplicate |
| M4 evidence 不完整 | 本文 §1–§17 补全 |
| m1 GIL import/export 探针名实不符 | 重命名为 `test_empty_table_import_export_smoke` |
| R3 inherited 224→226 | R3 evidence L245 + 本文 §3 |

**归属**：`PR-CORRECTNESS` + native-kernel component；**不是** `PR-NATIVE` / WP3 R5 sign-off。
