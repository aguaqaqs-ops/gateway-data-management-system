# WP3 R3 — PyO3 Adapter / Python Facade Evidence

状态：R3 implementation evidence（post external audit remediation, round 6）

日期：2026-07-22

Authority：

- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md)（rev.3.1）
- [WP3 R2 Rust Core Evidence](wp3-r2-rust-core-evidence.md)
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md) §5–§7
- [WP3–WP5 Checkout 计划](wp3-wp5-checkout-plan.md) §4、§8

Gate：**`PR-CORRECTNESS`**（`vnext/scripts/gate.sh correctness`）；**非** `PR-NATIVE` / `gate.sh native`

## 摘要

完成 WP3 R3 Arrow C Stream adapter、Python facade 与异常投影；移除 bootstrap `double_first_column` / `to_pylist()` / `double_nullable_i64` 正式路径。

外部审核 remediation（round 6，2026-07-22）：

- architecture gate 封闭反向依赖：`gateway-compute-core` / `gateway-shared-kernel` 均禁止依赖 `gateway-compute-python-impl`
- evidence 计数与路径修正：workspace **226** passed；impl **4** `#[cfg(test)]`（adapter 1、errors 2、smoke 1）

外部审核 remediation（round 5，2026-07-22）：

- **删除** `gateway-compute-python-hooks` workspace member 与 Python fault-injection lane；GIL/panic 端到端探针 **defer 至 WP3 R4**
- production `adapter` 移除 `hook_checkpoint` seam；panic 仅出现在 impl `#[cfg(test)]`（adapter 1 + errors 2）
- `gateway-architecture-check` 纳入 `gateway-compute-python-impl` dependency/source policy；依赖检查改用 `resolve` graph
- 新增 forbidden release workspace member 回归（`gateway-compute-python-hooks` 不得列入 members）
- `cargo build --workspace --release` 不再编译任何 hook/panic artifact

外部审核 remediation（round 4，2026-07-22）：

- 共享逻辑拆至 `gateway-compute-python-impl`（rlib）；production cdylib **不含** fault-injection / `#[allow(clippy::panic)]`
- fault injection 仅在独立 artifact `gateway-compute-python-hooks`（test-only cdylib，`#![allow(clippy::panic)]` 限于此 crate）
- hook lane：`maturin build --out <tmpdir>` + `uv pip install` 临时 wheel；**不** `maturin develop`、**不**写入 source tree
- `gate.sh` hook tests 后 `uv sync --reinstall-package gateway-compute-python`；最终断言 installed hooks `[]`、source tree 无 `.so`、production smoke 通过

外部审核 remediation（round 3，2026-07-22）：

- **production maturin** 仅启用 `extension-module`；`test-hooks` 不再编入普通 `uv sync --reinstall-package`
- fault injection 经 `maturin develop --features extension-module,test-hooks` 独立构建后运行 `test_facade_hooks.py`
- `test_production_extension.py` 断言普通安装无 `_test_*` / `_TEST_*` 符号
- 删除 source tree 残留 `.so`；保留 `.gitignore` 规则
- evidence 计数与完整验证命令对齐（workspace **223** passed）

外部审核 remediation（round 2，2026-07-22）：

- `parse_request` 移入 `py.detach` + `run_with_panic_boundary`（与 core compute 同区间）
- import / compute / export 三段均经 `run_with_panic_boundary`；fault injection 经独立 hook-extension artifact
- facade `request_jcs: bytes` 运行时拒绝 `bytearray`/`memoryview`/`str`
- 静态 `ROW_HASH_COMPUTE_FAILED` canonical fallback envelope（禁止空 `envelope_jcs`）
- `gate.sh correctness` 含 backend pytest；`gate.sh native` 诊断改为 WP4 R4
- `.gitignore` 排除 `python/**/*.so` 构建产物

## Identity / worktree

| 项 | 值 |
| --- | --- |
| 审核基线（R2） | `b9c4725693b7afafb24dffe1c1ebfbf313e4baa3` |
| 当前 HEAD（未提交 R3） | `b9c4725693b7afafb24dffe1c1ebfbf313e4baa3`（R3 全部在工作区） |
| Normative fixture SHA | `8220e7e587b87a446803ac579e81a8d8b99a0f98cd29d1152c7793442f235c77`（未变） |

## API 对照表

| 层 | 符号 | 说明 |
| --- | --- | --- |
| Native | `_canonical_row_hashes_v1_native(request_jcs, input_stream)` | Rust `#[pyfunction]`；C Stream in/out |
| Facade | `canonical_row_hashes_v1(request_jcs: bytes, data)` | `RecordBatch \| Table \| RecordBatchReader` |
| Facade | `_as_record_batch_reader(data)` | 单 batch / table chunks reader；禁止 `combine_chunks()` |
| 异常 | `ComputeRequestError` / `CanonicalValueError` / `ComputeError` / `ResourceLimitError` | 均携带 `envelope_jcs` |

## GIL 区间（对照 R1 §8.1 / R3-A5）

```text
[GIL]  facade: _as_record_batch_reader
[GIL]  PyRecordBatchReader::extract → into_reader()（import 段，含 panic boundary）
[GIL detached]  parse_request + canonical_row_hashes_v1（含 panic boundary）
[GIL]  PyRecordBatchReader::new → into_pyarrow()（export 段，含 panic boundary）
```

实现：[`gateway-compute-python-impl/src/adapter.rs`](../../../../vnext/rust/gateway-compute-python-impl/src/adapter.rs) — `request_jcs.to_vec()` 后在 `py.detach(|| detached_parse_and_compute(...))` 内解析与计算。

## pyo3-arrow 转换（0.19.0）

| 方向 | API | 所有权 |
| --- | --- | --- |
| Input | `PyRecordBatchReader::extract` → `into_reader()` | `Box<dyn RecordBatchReader + Send>` 归 Rust |
| Output | `OutputBatchReader` → `PyRecordBatchReader::new` → `into_pyarrow` | batch/schema 由 Rust reader 持有至 export |

## 依赖 / lock identity（R3 新增）

| 依赖 | 版本 | Lock identity | 用途 |
| --- | --- | --- | --- |
| `pyo3` | `=0.29.0` | `vnext/rust/Cargo.lock` | FFI / GIL |
| `pyo3-arrow` | `=0.19.0` | 同上 | safe C Stream import/export |
| `arrow-array` | `=59.1.0` | 同上（R3 新增，经 `gateway-compute-python-impl`） | `OutputBatchReader` |
| `arrow-schema` | `=59.1.0` | 同上（R3 新增，经 `gateway-compute-python-impl`） | output reader schema |
| `gateway-compute-core` | path | workspace | 唯一 compute 能力来源 |
| Python | `3.14.6` | `vnext/backend/.python-version` | backend / pytest |
| `pyarrow` | `25.0.0` | `vnext/backend/uv.lock` | facade 测试 |
| `maturin` | `1.14.1` | `gateway-compute-python/pyproject.toml` | extension build |

`gateway-compute-python` / `gateway-compute-python-impl` **不**直接依赖 `gateway-shared-kernel`（经 `gateway-compute-core`）。

依赖方向（architecture gate 固化）：

```text
gateway-compute-python → gateway-compute-python-impl → gateway-compute-core → gateway-shared-kernel
```

## 变更清单（完整）

### 新增

- `vnext/rust/gateway-compute-python-impl/`（`adapter.rs` / `errors.rs` / `mount_pymodule`）
- `vnext/rust/gateway-compute-python/tests/test_production_extension.py`
- `vnext/rust/gateway-compute-python/python/gateway_compute/__init__.py`
- `vnext/rust/gateway-compute-python/python/gateway_compute/exceptions.py`
- `vnext/rust/gateway-compute-python/tests/adapter_errors.rs`
- `vnext/rust/gateway-compute-python/tests/test_facade.py`
- `vnext/backend/tests/test_canonical_row_hash.py`
- `docs/.../wp3-r3-pyo3-adapter-evidence.md`

### 修改

- `vnext/rust/gateway-compute-python/{Cargo.toml,pyproject.toml,src/lib.rs}`
- `vnext/rust/gateway-compute-core/src/lib.rs`（移除 bootstrap `double_nullable_i64`）
- `vnext/backend/src/gateway_backend/compute.py`
- `vnext/rust/gateway-architecture-check/src/lib.rs` + `tests/negative_fixtures.rs`
- `vnext/rust/Cargo.lock`（`gateway-compute-python-impl` 增加 `arrow-array`/`arrow-schema`）
- `vnext/scripts/gate.sh`（production pytest + source `.so` / hooks 最终断言）
- `.gitignore`（`python/**/*.so`）

### 删除

- `vnext/backend/tests/test_compute.py`（bootstrap）
- `vnext/rust/gateway-compute-python/tests/python_extension.rs`（bootstrap）
- `vnext/rust/gateway-compute-python-hooks/`（round 5 移除；defer R4）
- `vnext/rust/gateway-compute-python/tests/test_facade_hooks.py`（defer R4）

## 验证命令与结果（2026-07-22 round 6）

| 命令 | Exit | 结果 |
| --- | ---: | --- |
| `cargo fmt --check` | 0 | 通过 |
| `cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings` | 0 | 通过 |
| `cargo test --locked --offline --workspace --all-targets` | 0 | **226 passed** |
| `cargo build --locked --offline --workspace --release` | 0 | 通过 |
| `cargo metadata --locked --offline` | 0 | 通过 |
| `uv sync --reinstall-package gateway-compute-python`（production） | 0 | 扩展无 `_test_*` / `_TEST_*` |
| backend `ruff` | 0 | 通过 |
| backend `mypy` | 0 | 8 source files 通过 |
| backend production pytest | 0 | **22 passed** |
| `gate.sh correctness` | 0 | shared-kernel 131、repository 5、Rust 226、R3 Python 22 |
| architecture check（impl policy + forbidden hook member） | 0 | 通过 |
| `gate.sh native` | 2 | 正确提示 WP4 R4 |
| `git diff --check b9c4725693b7afafb24dffe1c1ebfbf313e4baa3` | 0 | 通过 |

```bash
cd vnext/rust
cargo fmt --check                                    # exit 0
cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings  # exit 0
cargo test --locked --offline --workspace --all-targets  # exit 0, 226 passed (workspace)
cargo build --locked --offline --workspace --release   # exit 0
cargo metadata --locked --offline                      # exit 0

cd vnext/backend
uv sync --locked --offline --all-groups --reinstall-package gateway-compute-python  # exit 0, no test hooks
uv run pytest -q ../rust/gateway-compute-python/tests/test_facade.py \
  ../rust/gateway-compute-python/tests/test_production_extension.py \
  tests/test_canonical_row_hash.py                     # exit 0, 22 passed
# gate 结束：installed hooks []；source tree .so 数量 0

cd /root/gateway-data-management-system
git diff --check b9c4725693b7afafb24dffe1c1ebfbf313e4baa3  # exit 0
vnext/scripts/gate.sh correctness                      # exit 0
```

Gate 内 Python：

- `test_facade.py`：**19 passed**
- `test_production_extension.py`：**1 passed**
- `test_canonical_row_hash.py`：**2 passed**
- **合计 22 passed**

gate 结束后：installed hooks **[]**；source tree `.so` **0**

Rust `gateway-compute-python-impl`：`adapter.rs` **1** + `errors.rs` **2** + `lib.rs` smoke **1** = **4**；`gateway-compute-python`：`adapter_errors.rs` **5**

## 测试矩阵（R3）

| 层 | 文件 | 计数 |
| --- | --- | ---: |
| Rust adapter errors | `adapter_errors.rs` | 5 |
| Rust impl unit | `gateway-compute-python-impl` `#[cfg(test)]` | 4 |
| Python facade | `test_facade.py` | 19 |
| Python production guard | `test_production_extension.py` | 1 |
| Backend formal | `test_canonical_row_hash.py` | 2 |
| Architecture check | impl policy + negative fixtures | 5+ |
| **R3 小计** | | **36+** |

覆盖：三输入、multi-chunk Table、output schema、core golden bytes、bytes-only request、generator 拒绝、production 无 test hooks 断言、native 单次调用；impl `#[cfg(test)]` panic boundary（adapter `panic!` 1 + errors `panic!` 2）。Python GIL/panic fault matrix **defer R4**。

## 人工 review checklist

| # | 项 | 状态 |
| --- | --- | --- |
| A1 | C Stream；无 `to_pylist` | ✅ |
| A2 | 三 data 入口 + `request_jcs: bytes` | ✅ |
| A3 | 仅经 `gateway-compute-core` | ✅ |
| A4 | parse+compute 在 detach；export 在 GIL | ✅ |
| A5 | 全段 panic boundary；非空 envelope fallback | ✅ |
| A6 | Python→extension 端到端 + golden parity | ✅ |
| A7 | production 无 hook seam / panic waiver；release workspace 无 hook artifact | ✅ |
| A8 | evidence 计数/命令与 gate 一致 | ✅ |
| A9 | `gate.sh correctness` 含 R3 production pytest + 最终状态断言 | ✅ |
| A10 | 非 PR-NATIVE | ✅ |

**本轮归属**：`PR-CORRECTNESS` + architecture；**不是** kernel-native sign-off。

## Deferred

| 项 | 归属 |
| --- | --- |
| GIL detach 探针、Python panic fault matrix、hook-extension artifact | WP3 R4 |
| wheel smoke / component sign-off | WP3 R4–R5 |
| `gate.sh native` / `PR-NATIVE` | WP4 R4 |
| Artifact IPC / scenario / container | WP4–WP5 |

## Remediation 映射

| Finding | 修复 |
| --- | --- |
| M1 GIL 持有 parse_request | `parse_request` 移入 `py.detach` |
| M2 panic scope 不完整 | import/compute/export 均 `run_with_panic_boundary` |
| M3 `Buffer` 注解 | `request_jcs: bytes` + runtime `isinstance` |
| M4 空 envelope fallback | 静态 `ROW_HASH_COMPUTE_FAILED_ENVELOPE_JCS` const |
| M5 evidence 不完整 | 本文 identity/lock/清单 |
| Minor gate 诊断 | `gate.sh native` → WP4 R4 |
| Minor `.so` 残留 | 删除 source tree `.so`；`.gitignore` 保留 |
| M1 hooks release artifact / panic waiver | 删除 hooks crate；defer Python fault injection 至 R4 |
| M2 impl 绕过 architecture gate | impl 纳入 policy；core/shared-kernel 禁止 → impl 反向依赖 |
| M3 evidence 漂移 | workspace **224**；impl **4** tests；路径/lock 描述对齐 |
