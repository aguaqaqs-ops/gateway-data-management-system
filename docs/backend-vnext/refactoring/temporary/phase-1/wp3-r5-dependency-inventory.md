# WP3 R5 — Kernel-native Dependency Inventory（定稿）

状态：WP3 R5 evidence（dependency / safety inventory 定稿）

日期：2026-07-23（最终审计窗口：2026-07-22 23:49:19 UTC – 2026-07-23 00:18:50 UTC）

适用：Phase 1 WP3 R5 — `native-kernel` component sign-off；**非** `PR-NATIVE`

Authority：

- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md) §9
- [Rust Safety and Performance Policy](../../formal/policies/rust-safety-and-performance-policy.md)
- [WP2 R5 Dependency Inventory](wp2-r5-dependency-inventory.md)（体例参考）

关联 sign-off：[wp3-r5-kernel-native-signoff.md](wp3-r5-kernel-native-signoff.md)

被审计 source baseline：`6e14f91cb65a67eb1dd54e4e392b41462755f5ac`

## 0. Lock / toolchain identity（对照 R1 §9.1）

| 组件 | 版本 | Lock identity | R1 §9.1 delta |
| --- | --- | --- | --- |
| Rust toolchain | **1.97.0** | `vnext/rust/rust-toolchain.toml` SHA-256 `0506c53cddc8435a55513d5f662c302ff6eb4035f012d5d5e5a47e96a7f40420` | 无 |
| Rust workspace manifest | — | `vnext/rust/Cargo.toml` SHA-256 `c25d2d82d8a0b690422ac06ca56db18fbc3e633fb07b722d7211eed49bce33f1` | — |
| Rust lock | lock format 4 | `vnext/rust/Cargo.lock` SHA-256 `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544` | R5 移除两个未使用 direct edge；第三方 package/version/checksum 未变 |
| `pyo3` | **0.29.0** | `Cargo.lock` checksum `cd274650b21d4bfc26a0a47587962c1edb425f69287324355cd040c3ea66071c` | 无 |
| `pyo3-arrow` | **0.19.0** | checksum `3d5ddf226a2dbf7607570d0657c2bf6fbe299208368b2914f3dd7e7ba0b57688` | 无 |
| `arrow-array` / `arrow-buffer` / `arrow-data` / `arrow-schema` | **59.1.0** | workspace pin `vnext/rust/Cargo.toml`；例 `arrow-array` checksum `9486151b2f0785bafc6fa04fc5c99fcb4495455662e58787ea32eaaed33c4192` | 无 |
| `serde` / `serde_json` | **1.0.229** / **1.0.150** | `Cargo.lock` | 无 |
| `serde_json_canonicalizer` | **0.3.2** | checksum `fe52319a927259afbfa5180c5157cd8167edfd3e8c254f9558c7fef44c5649f2` | 无 |
| `sha2` | **0.11.0** | checksum `446ba717509524cb3f22f17ecc096f10f4822d76ab5c0b9822c5f9c284e825f4` | 无 |
| `thiserror` | **2.0.18**（first-party）；**1.0.69**（`pyo3-arrow` 传递） | checksums 见 `Cargo.lock` | 无 |
| Python | **3.14.6** | `vnext/shared_kernel/.python-version`；gate/wheel-smoke 实测 | 无 |
| `pyarrow` | **25.0.0** | `vnext/backend/uv.lock` sdist `sha256:d2d697008b5ec06d75952ef260c2e9a8a0f6ccfce24266c04c9c8ade927cb3b4` | 无 |
| `maturin` | **1.14.1** | `gateway-compute-python/pyproject.toml` SHA-256 `50faa508980d9c4bcc61daf59470601de92afa5893e0beb81cd3de712b2e0b31`，`requires = ["maturin==1.14.1"]`；`uv.lock` upload 2026-06-19 | 无 |
| Python lock / manifest | — | `vnext/backend/uv.lock` SHA-256 `446184d5a1ddf7a45115c993499b4ed2fd34980e4cef07b703dda7326cdad211`；`pyproject.toml` SHA-256 `f61ed12f75d2391084d3afeb310b3c6a4c766c282d959683658b26a0878a73a7` | 无 |

**R5 结论**：相对 R1 §9.1 草稿 **无版本 delta**。R5 代码审查发现 `gateway-compute-core` 对 `arrow-data`、`thiserror` 的 direct edge 没有任何 first-party API 使用；已从 manifest/lock 的 first-party dependency list 删除。两者仍由真实传递路径解析（`arrow-data` 经 Arrow，`thiserror` 经 shared-kernel / pyo3-arrow），因此第三方 resolved package identity 不变。

## 1. Production crate 边界

| Crate | 角色 | `#![forbid(unsafe_code)]` | Production 直接依赖数 |
| --- | --- | --- | ---: |
| `gateway-compute-core` | `canonical_row_hashes_v1` 纯 Rust kernel | ✅ | 6 |
| `gateway-compute-python-impl` | PyO3 adapter / C Stream / GIL 区间 | ✅ | 5 |
| `gateway-compute-python` | maturin cdylib 导出 | ✅ | 2 |
| `gateway-shared-kernel` | compute-core 唯一 first-party 上游 | ✅ | 5 |

**不在 WP3 production 闭包**：`gateway-shared-kernel` dev-only `base64`、`jsonschema`；`gateway-compute-python` dev-deps（`arrow-*`、`gateway-compute-core`、`pyo3-arrow`）仅测试。完整 dev/test edge 表见 §7.5。

**架构边界**（`gateway-architecture-check` exit 0）：

- `gateway-compute-core` / `gateway-shared-kernel` **不得**依赖 `gateway-compute-python-impl`
- `cargo tree --locked --offline -p gateway-compute-core -i pyo3` → **无匹配**（exit 101，预期）

### 1.1 Direct production edge ledger（逐 edge）

Registry source 均为 `registry+https://github.com/rust-lang/crates.io-index`；path crate 均为本仓库 `vnext/rust/<crate>`、`0.1.0`、`LicenseRef-Proprietary`。分类均为 **direct / production**；详细 unsafe/build/维护/advisory/license/替代/rollback 字段见 §2–§5 对应条目。

| Owner | Direct package | Exact identity / checksum | 引入目的 | First-party 实际 safe API surface |
| --- | --- | --- | --- | --- |
| core | `gateway-shared-kernel` | path `../gateway-shared-kernel` | canonical row/JCS/digest owner | `encode_row`、`canonicalize_*`、`semantic_digest`、`unordered_row_hashes_content_digest` |
| core | `arrow-array` | 59.1.0 / `9486151b…c4192` | batch/array/reader/output | `RecordBatch*`、typed arrays、`Array`、`FixedSizeBinaryBuilder` |
| core | `arrow-buffer` | 59.1.0 / `c4776577…7b434` | Decimal256 extraction | `i256` |
| core | `arrow-schema` | 59.1.0 / `d9e4969d…69e5` | schema/mapping/error | `Schema`、`Field`、`DataType`、`ArrowError` |
| core | `serde` | 1.0.229 / `4148590a…e0ba` | result/failure DTO | `Serialize` derive |
| core | `serde_json` | 1.0.150 / `e8014e44…4fb9` | closed request parse / DTO serialize | `Value`、`from_slice`、`to_vec`、`json!` |
| adapter impl | `arrow-array` | 59.1.0 / `9486151b…c4192` | owned output reader | `RecordBatch`、`RecordBatchReader` |
| adapter impl | `arrow-schema` | 59.1.0 / `d9e4969d…69e5` | output reader schema/error | `Schema`、`ArrowError` |
| adapter impl | `gateway-compute-core` | path `../gateway-compute-core` | 唯一 capability 实现 | `parse_request`、`canonical_row_hashes_v1`、typed failure |
| adapter impl | `pyo3` | 0.29.0 / `cd274650…071c` | Python/GIL/exception/macro boundary | `Python::detach`、`Bound`/`Py`、safe macros |
| adapter impl | `pyo3-arrow` | 0.19.0 / `3d5ddf22…7688` | owned Arrow C Stream import/export | `PyRecordBatchReader::{extract,into_reader,new,into_pyarrow}` |
| cdylib | `gateway-compute-python-impl` | path `../gateway-compute-python-impl` | module mount implementation | `mount_pymodule` / exception re-export |
| cdylib | `pyo3` | 0.29.0 / `cd274650…071c` | `#[pymodule]` entry | safe `PyModule` / macro surface |
| shared kernel | `serde` | 1.0.229 / `4148590a…e0ba` | canonical DTO/decode | Serde traits/visitor |
| shared kernel | `serde_json` | 1.0.150 / `e8014e44…4fb9` | strict JSON model | parser/value safe API |
| shared kernel | `serde_json_canonicalizer` | 0.3.2 / `fe52319a…49f2` | RFC 8785 serialization | `to_vec` |
| shared kernel | `sha2` | 0.11.0 / `446ba717…25f4` | SHA-256 | `Digest`/`Sha256` |
| shared kernel | `thiserror` | 2.0.18 / `4288b5bc…fbc4` | canonical typed errors | `thiserror::Error` derive |

R5 removed two false direct edges from core: `arrow-data` (no direct symbol use) and `thiserror` (core uses a hand-written `ComputeFailure`; derive exists only in shared-kernel). This is a manifest/lock classification cleanup, not a semantic or resolved-version change.

---

## 2. `gateway-compute-core` 直接 production 依赖（R1 §9.3 全字段）

### `gateway-shared-kernel`（path，first-party）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | `v0.1.0` path `vnext/rust/gateway-shared-kernel` |
| 分类 | direct / production / first-party |
| 用途 | row hash / JCS / digest primitives；`unordered_row_hashes_content_digest` |
| Safe API | `encode_row`、`semantic_digest`、`unordered_row_hashes_content_digest` 等 reviewed public API |
| Third-party unsafe | first-party `forbid(unsafe_code)` |
| Proc-macro / build / native | 无 |
| 维护状态 | workspace 内部（2026-07-23） |
| Advisory | N/A（path crate） |
| SPDX | workspace proprietary |
| 兼容性 | first-party；无 copyleft |
| 替代 | 不得复制 kernel 公式到 compute-core |
| 回退 | `cargo test -p gateway-compute-core` + Arrow fixtures，不依赖 adapter |

### `arrow-schema` / `arrow-array` / `arrow-buffer`（`59.1.0`，direct）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | registry `59.1.0`；checksums：`arrow-array` `9486151b2f0785bafc6fa04fc5c99fcb4495455662e58787ea32eaaed33c4192`；`arrow-schema` `d9e4969dc350d571766247143ab36a5187d095d3d3690970408bc630d47c69e5`；`arrow-buffer` `c4776577a87794bfdf0b4e90e2ea12454fa7738ea2823c4be5b9d1851da7b434` |
| 分类 | direct / production / third-party |
| 用途 | Arrow physical type 校验、`RecordBatch` 读取、column extract；**无** IPC write/reopen |
| Safe API | `arrow-array::{RecordBatch, RecordBatchReader, Array, typed arrays, FixedSizeBinaryBuilder}`；`arrow-schema::{Schema, Field, DataType, ArrowError}`；`arrow-buffer::i256`；first-party 不经 raw C ABI |
| Third-party unsafe | **Arrow 内部 buffer/FFI `unsafe`** |
| Proc-macro / build | 传递 `ahash` build.rs、`num-traits`/`libm` build.rs |
| 维护状态 | Apache Arrow Rust 活跃；59.x 与 `pyo3-arrow 0.19` 对齐；[arrow-rs releases](https://github.com/apache/arrow-rs/releases)（查询 2026-07-23） |
| Advisory | 本轮 clean（见 §8） |
| SPDX | `arrow-array`: `Apache-2.0 AND MIT`；`arrow-buffer`/`arrow-schema`: `Apache-2.0`（`cargo metadata`） |
| 兼容性 | permissive；与 proprietary workspace **兼容** |
| 替代 | 纯 Python `to_pylist()` **不**替代 production kernel |
| 回退 | core 单测 + in-memory fixtures |

### `serde`（`1.0.229`，`derive`）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | checksum `4148590afebada386688f18773da617792bf2ef03ffc1e4cbd2b1d45b023e0ba` |
| 分类 | direct / production |
| 用途 | request/result DTO derive |
| Safe API | `Serialize`/`Deserialize` + `serde_json` 边界 |
| Third-party unsafe | `serde_derive` proc-macro；crate 本体 safe |
| Proc-macro / build | **`serde_derive` proc-macro** |
| 维护状态 | [crates.io/serde](https://crates.io/crates/serde) 活跃（查询 2026-07-23） |
| Advisory | clean |
| SPDX | `MIT OR Apache-2.0` |
| 兼容性 | 兼容 |
| 替代 | 手写 parser（漂移风险） |
| 回退 | 同 core 单测 |

### `serde_json`（`1.0.150`）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | checksum `e8014e44b4736ed0538adeecded0fce2a272f22dc9578a7eb6b2d9993c74cfb9` |
| 分类 | direct / production |
| 用途 | JSON 解析/序列化（request bytes → DTO；JCS authority 经 shared-kernel） |
| Safe API | `from_slice` / `to_vec` |
| Third-party unsafe | 纯 safe Rust |
| Proc-macro / build | 无 |
| 维护状态 | [crates.io/serde_json](https://crates.io/crates/serde_json) 活跃 |
| Advisory | clean |
| SPDX | `MIT OR Apache-2.0` |
| 兼容性 | 兼容 |
| 替代 | `simd-json` 等（无收益） |
| 回退 | 同 core |

---

## 3. `gateway-compute-python-impl` 直接 production 依赖

（`gateway-compute-core`、`arrow-array`、`arrow-schema` 见 §2）

### `pyo3`（`0.29.0`，`auto-initialize`）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | checksum `cd274650b21d4bfc26a0a47587962c1edb425f69287324355cd040c3ea66071c` |
| 分类 | direct / production |
| 用途 | Python extension；`py.detach` GIL release；`#[pyfunction]`；C API FFI |
| Safe API | `Py`、`Python`、`Bound`、官方 macro；first-party 无 raw `PyObject*` |
| Third-party unsafe | **PyO3 / `pyo3-ffi` 内部 `unsafe` + Python C API** |
| Proc-macro / build | `pyo3` 自身 custom build 使用 **`pyo3-build-config` build-dependency library**；**`pyo3-macros` proc-macro** |
| 维护状态 | [github.com/PyO3/pyo3](https://github.com/PyO3/pyo3) 活跃；0.29 支持 Python 3.14（查询 2026-07-23） |
| Advisory | clean |
| SPDX | `MIT OR Apache-2.0` |
| 兼容性 | 兼容 |
| 替代 | 纯 Python reference 不替代 production |
| 回退 | 禁用 adapter；core + Rust component tests |

### `pyo3-arrow`（`0.19.0`）

| 字段 | 记录 |
| --- | --- |
| 版本 / identity | checksum `3d5ddf226a2dbf7607570d0657c2bf6fbe299208368b2914f3dd7e7ba0b57688` |
| 分类 | direct / production |
| 用途 | Arrow C Stream import/export；`PyRecordBatchReader` |
| Safe API | `PyRecordBatchReader::extract` / `into_pyarrow`；architecture-check 禁止 `to_pylist` |
| Third-party unsafe | arrow + pyo3 + numpy FFI 链 |
| Proc-macro / build | 传递 `pyo3-build-config` |
| 维护状态 | [crates.io/pyo3-arrow](https://crates.io/crates/pyo3-arrow) 活跃 |
| Advisory | clean |
| SPDX | `MIT OR Apache-2.0` |
| 兼容性 | 兼容 |
| 替代 | 手写 C Data Interface（高成本） |
| 回退 | 同 `pyo3` |

---

## 4. `gateway-compute-python` 直接 production 依赖

| 依赖 | 分类 | 说明 |
| --- | --- | --- |
| `gateway-compute-python-impl` | direct / production / path | 全部 adapter 逻辑 |
| `pyo3`（`auto-initialize`, `extension-module`） | direct / production | `#[pymodule]` / cdylib init |

**Release inventory**：唯一 production cdylib target `gateway-compute-python`；无额外 hook crate、无 source-tree `.so`（gate 断言）。

---

## 5. `gateway-shared-kernel` production edge

| 依赖 | 版本 | SPDX | 用途 |
| --- | --- | --- | --- |
| `serde` | 1.0.229 | MIT OR Apache-2.0 | DTO |
| `serde_json` | 1.0.150 | MIT OR Apache-2.0 | JSON |
| `serde_json_canonicalizer` | 0.3.2 | MIT | **JCS authority** |
| `sha2` | 0.11.0 | MIT OR Apache-2.0 | digest |
| `thiserror` | 2.0.18 | MIT OR Apache-2.0 | errors |

**WP3 policy**：shared-kernel production path **不得**依赖 PyO3、Arrow、network、filesystem。

---

## 6. Python / tooling pins

| 组件 | 版本 | Lock identity | 上游（查询 2026-07-23） |
| --- | --- | --- | --- |
| CPython | 3.14.6 | `.python-version` | python.org |
| `pyarrow` | 25.0.0 | `uv.lock` sdist sha256 `d2d697008b5ec06d75952ef260c2e9a8a0f6ccfce24266c04c9c8ade927cb3b4`；upload 2026-07-10 | [pypi.org/project/pyarrow/25.0.0](https://pypi.org/project/pyarrow/25.0.0) |
| `maturin` | 1.14.1 | `pyproject.toml` + `uv.lock`；upload 2026-06-19 | [pypi.org/project/maturin/1.14.1](https://pypi.org/project/maturin/1.14.1) |

### 6.1 Current maintenance / release verification（官方元数据）

查询时间：**2026-07-23 UTC**。以下日期来自 crates.io version API 或 PyPI release JSON；repository 列来自同一官方 package metadata。它们证明当前锁定版本近期发布/上游仍活跃，不代表未来维护保证。

| Package | Locked release UTC | Exact license expression | Official metadata / upstream |
| --- | --- | --- | --- |
| `arrow-array` 59.1.0 | 2026-07-07 | `Apache-2.0 AND MIT` | [crates.io](https://crates.io/crates/arrow-array/59.1.0) / [apache/arrow-rs](https://github.com/apache/arrow-rs) |
| `arrow-buffer` / `arrow-data` / `arrow-schema` 59.1.0 | 2026-07-07 | `Apache-2.0` | [crates.io arrow-buffer](https://crates.io/crates/arrow-buffer/59.1.0) / [apache/arrow-rs](https://github.com/apache/arrow-rs) |
| `pyo3` 0.29.0 | 2026-06-11 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/pyo3/0.29.0) / [PyO3/pyo3](https://github.com/PyO3/pyo3) |
| `pyo3-arrow` 0.19.0 | 2026-06-15 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/pyo3-arrow/0.19.0) / [kylebarron/arro3](https://github.com/kylebarron/arro3) |
| `serde` 1.0.229 | 2026-07-18 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/serde/1.0.229) / [serde-rs/serde](https://github.com/serde-rs/serde) |
| `serde_json` 1.0.150 | 2026-05-21 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/serde_json/1.0.150) / [serde-rs/json](https://github.com/serde-rs/json) |
| `serde_json_canonicalizer` 0.3.2 | 2026-02-03 | `MIT` | [crates.io](https://crates.io/crates/serde_json_canonicalizer/0.3.2) / [upstream](https://github.com/evik42/serde-json-canonicalizer) |
| `sha2` 0.11.0 | 2026-03-25 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/sha2/0.11.0) / [RustCrypto/hashes](https://github.com/RustCrypto/hashes) |
| `thiserror` 2.0.18 | 2026-01-18 | `MIT OR Apache-2.0` | [crates.io](https://crates.io/crates/thiserror/2.0.18) / [dtolnay/thiserror](https://github.com/dtolnay/thiserror) |
| `pyarrow` 25.0.0 | 2026-07-10 | `Apache-2.0` | [PyPI](https://pypi.org/project/pyarrow/25.0.0/) |
| `maturin` 1.14.1 | 2026-06-19 | `MIT OR Apache-2.0` | [PyPI](https://pypi.org/project/maturin/1.14.1/) |

---

## 7. 完整 resolved production closure

```bash
cd vnext/rust
cargo tree --locked --offline -p gateway-compute-python -e normal
cargo tree --locked --offline -p gateway-compute-python-impl -e normal
cargo tree --locked --offline -p gateway-compute-core -e normal
cargo tree --locked --offline -p gateway-compute-python -e normal,build --target all
cargo tree --locked --offline -p gateway-compute-python -d -e normal,build --target all
cargo tree --locked --offline -p gateway-compute-python -e features --features extension-module
```

闭包根是 production cdylib package `gateway-compute-python`；只跟随 `normal,build`，明确排除 `dev`。当前 Linux x86_64 target 激活 **87** 个唯一 package identity；`--target all` 的跨平台 resolved union 为 **123** 个。第三方 source 均为 crates.io registry；四个 first-party package 为上文 path identity。每个 registry package 的精确 checksum 由本轮 `Cargo.lock`（SHA-256 见 §0）固定。

下面是 **123/123** identity 的完整生成附录；方括号标记 package 自身 custom-build/proc-macro/`links` target。平台条件意味着 Windows/WASM identity 在 all-target union 中，但不进入本轮 Linux wheel link。

```text
ahash@0.8.12 [build.rs]; android_system_properties@0.1.5; arrow-array@59.1.0
arrow-buffer@59.1.0; arrow-cast@59.1.0; arrow-data@59.1.0
arrow-ord@59.1.0; arrow-schema@59.1.0; arrow-select@59.1.0
atoi@2.0.0; autocfg@1.5.1; base64@0.22.1
bitflags@2.13.1; block-buffer@0.12.1; bumpalo@3.20.3
bytes@1.12.1; cc@1.3.0; cfg-if@1.0.4
chrono@0.4.45; chrono-tz@0.10.4 [build.rs]; comfy-table@7.2.2
const-random@0.1.18; const-random-macro@0.1.16 [proc-macro]; core-foundation-sys@0.8.7
cpufeatures@0.3.0; crunchy@0.2.4 [build.rs]; crypto-common@0.2.2
digest@0.11.3; equivalent@1.0.2; find-msvc-tools@0.1.9
futures-core@0.3.33; futures-task@0.3.33; futures-util@0.3.33
gateway-compute-core@0.1.0; gateway-compute-python@0.1.0; gateway-compute-python-impl@0.1.0
gateway-shared-kernel@0.1.0; getrandom@0.2.17; getrandom@0.3.4 [build.rs]
half@2.7.1; hashbrown@0.17.1; heck@0.5.0
hybrid-array@0.4.13; iana-time-zone@0.1.65; iana-time-zone-haiku@0.1.2 [build.rs]
indexmap@2.14.0; itoa@1.0.18; js-sys@0.3.103
lexical-core@1.0.6; lexical-parse-float@1.0.6; lexical-parse-integer@1.0.6
lexical-util@1.0.7; lexical-write-float@1.0.6; lexical-write-integer@1.0.6
libc@0.2.189 [build.rs]; libm@0.2.16 [build.rs]; log@0.4.33
matrixmultiply@0.3.11 [build.rs]; memchr@2.8.3; ndarray@0.17.2
num-bigint@0.4.8; num-complex@0.4.6; num-integer@0.1.46
num-traits@0.2.19 [build.rs]; numpy@0.29.0 [build.rs]; once_cell@1.21.4
phf@0.12.1; phf_shared@0.12.1; pin-project-lite@0.2.17
portable-atomic@1.14.0 [build.rs]; portable-atomic-util@0.2.7 [build.rs]; proc-macro2@1.0.107 [build.rs]
pyo3@0.29.0 [build.rs, links=pyo3-python]; pyo3-arrow@0.19.0; pyo3-build-config@0.29.0
pyo3-ffi@0.29.0 [build.rs, links=python]; pyo3-macros@0.29.0 [proc-macro]; pyo3-macros-backend@0.29.0
quote@1.0.47 [build.rs]; r-efi@5.3.0; rawpointer@0.2.1
rustc-hash@2.1.3; rustversion@1.0.23 [build.rs, proc-macro]; ryu@1.0.23
ryu-js@1.0.3; serde@1.0.229 [build.rs]; serde_core@1.0.229 [build.rs]
serde_derive@1.0.229 [proc-macro]; serde_json@1.0.150 [build.rs]; serde_json_canonicalizer@0.3.2
sha2@0.11.0; shlex@2.0.1; siphasher@1.0.3
slab@0.4.12; syn@2.0.119; syn@3.0.3
target-lexicon@0.13.5 [build.rs]; thiserror@1.0.69 [build.rs]; thiserror@2.0.18 [build.rs]
thiserror-impl@1.0.69 [proc-macro]; thiserror-impl@2.0.18 [proc-macro]; tiny-keccak@2.0.2 [build.rs]
typenum@1.20.1; unicode-ident@1.0.24; unicode-segmentation@1.13.3
unicode-width@0.2.2; version_check@0.9.5; wasi@0.11.1+wasi-snapshot-preview1
wasip2@1.0.4+wasi-0.2.12; wasm-bindgen@0.2.126 [build.rs]; wasm-bindgen-macro@0.2.126 [proc-macro]
wasm-bindgen-macro-support@0.2.126; wasm-bindgen-shared@0.2.126 [build.rs, links=wasm_bindgen]; windows-core@0.62.2
windows-implement@0.60.2 [proc-macro]; windows-interface@0.59.3 [proc-macro]; windows-link@0.2.1
windows-result@0.4.1; windows-strings@0.5.1; wit-bindgen@0.57.1 [build.rs]
zerocopy@0.8.55 [build.rs]; zerocopy-derive@0.8.55 [proc-macro]; zmij@1.0.23 [build.rs]
```

### 7.1 重复版本（`cargo tree -d` 摘录，须记录）

| Crate | 版本 | 引入路径 | 备注 |
| --- | --- | --- | --- |
| `thiserror` | 1.0.69 / 2.0.18 | `pyo3-arrow` vs shared-kernel | 不发生跨 major feature unification；各自独立 |
| `syn` | 2.0.119 / 3.0.3 | `serde_derive` vs 其他 | proc-macro 构建期隔离 |
| `getrandom` | 0.2.17 / 0.3.4 | `const-random` vs `ahash` | production all-target closure；均经传递依赖 |

全 workspace `cargo tree -d` 另显示 `getrandom 0.4.3`，它只由 architecture-check 的 dev-only `tempfile` 引入，不进入 production root。

### 7.2 Feature unification

Release wheel 以 `--features extension-module` 构建。关键统一结果：`pyo3 = default + macros + auto-initialize + extension-module + chrono + chrono-tz + indexmap`；`pyo3-arrow = default + buffer_protocol`；Arrow 由 pyo3-arrow 启用 `ffi`，first-party 仍只调用 `PyRecordBatchReader` safe wrapper；`serde = default + derive`；`serde_json = default + float_roundtrip`。不存在 Rayon/parallel/nightly/test-hook feature。

### 7.3 Proc-macro / custom build / `links` / native（production 闭包）

| Crate | 类型 | 行为 |
| --- | --- | --- |
| Proc macro | `const-random-macro`; `pyo3-macros`; `rustversion`; `serde_derive`; `thiserror-impl` 1.x/2.x; `wasm-bindgen-macro`; `windows-implement`; `windows-interface`; `zerocopy-derive` | compile-time token expansion；无 first-party proc macro |
| Python build/links | `pyo3` custom build + `links=pyo3-python`; `pyo3-ffi` custom build + `links=python`; build-dependency library `pyo3-build-config` | Python 版本/ABI/link mode 探测；本轮 Linux extension wheel 不引入额外 bundled system library |
| Other custom build | `ahash`, `chrono-tz`, `crunchy`, `getrandom 0.3`, `libc`, `libm`, `matrixmultiply`, `num-traits`, `numpy`, `portable-atomic*`, `proc-macro2`, `quote`, `serde*`, `target-lexicon`, `thiserror*`, `tiny-keccak`, `wasm-bindgen*`, `wit-bindgen`, `zerocopy`, `zmij` | cfg/target/codegen capability；精确集合由 §7 完整附录标记 |
| Target-only links | `wasm-bindgen-shared links=wasm_bindgen` | all-target closure；不进入 Linux wheel |
| Native/FFI | `pyo3-ffi`, `libc`, `numpy`; Arrow `ffi` feature | Python C API / OS / Arrow third-party FFI；first-party 无 raw pointer/C ABI/PyCapsule |

### 7.4 安全敏感传递依赖

| Crate | 角色 | unsafe / native |
| --- | --- | --- |
| `arrow-buffer` | memory | unsafe buffer ops |
| `pyo3-ffi` | Python C API | **unsafe** |
| `libc` | OS FFI | FFI |
| `sha2` / `digest` | crypto hash | safe API；底层可能 SIMD（third-party） |

### 7.5 Dev/test edges（与 production 分离）

| Owner | Dev/test direct dependencies |
| --- | --- |
| `gateway-architecture-check` | `tempfile 3.26.0` |
| `gateway-shared-kernel` | `base64 0.22.1`, `jsonschema 0.48.2`, `serde_json_canonicalizer 0.3.2` |
| `gateway-compute-core` | `serde_json 1.0.150`（同时为 production；dev declaration 冗余 feature 不扩张） |
| `gateway-compute-python-impl` | `arrow-array 59.1.0`, `arrow-schema 59.1.0`, `pyo3-arrow 0.19.0`（均同时为 production；供 test target 显式使用） |
| `gateway-compute-python` | `arrow-array 59.1.0`, `arrow-schema 59.1.0`, `gateway-compute-core` path, `pyo3 0.29.0`, `pyo3-arrow 0.19.0`（adapter integration tests） |

### 7.6 License closure / compatibility

以 `cargo tree --locked --offline -p gateway-compute-python -e normal,build --target all` 确定 123-package production closure，再逐 identity 关联 `cargo metadata` license 字段检查。精确 SPDX family 包含：`Apache-2.0`、`Apache-2.0 AND MIT`、`MIT OR Apache-2.0`、`MIT`、`BSD-2-Clause`、`BSD-2-Clause OR Apache-2.0 OR MIT`、`CC0-1.0`、`Unlicense OR MIT`、`Apache-2.0 OR BSL-1.0`、`Apache-2.0 WITH LLVM-exception`、`(MIT OR Apache-2.0) AND Unicode-3.0`，以及 target-only `r-efi` 的 `MIT OR Apache-2.0 OR LGPL-2.1-or-later`（可选 permissive 分支）。

11 个旧 crate metadata 使用 legacy `MIT/Apache-2.0` 字符串；本轮检查 registry source 的 dual-license 文件/声明，并按 SPDX **`MIT OR Apache-2.0`** 解释：`android_system_properties`, lexical 1.0 family, `matrixmultiply`, `rawpointer`, `siphasher`, `version_check`。没有 copyleft-only package。工程结论：可与 proprietary workspace 组合；这是工程审计判断，**不是法律意见**。

### 7.7 Production / full-lock 计数

Production root：Linux 87 / all-target 123 package identities。`cargo audit` 扫描 **195** crate dependencies（完整 workspace `Cargo.lock`，包含 dev/test closure），因此 advisory scan 覆盖 production closure的超集。

---

## 8. Advisory 可复现证据（R5 本轮执行）

```bash
cargo-audit --version
# cargo-audit 0.22.2

cd /root/gateway-data-management-system/vnext/rust
cargo audit --json
```

| 项 | 值 |
| --- | --- |
| 命令 | `cargo audit --json` |
| 工具版本 | **cargo-audit 0.22.2** |
| 退出码 | **0** |
| 扫描路径 | `/root/gateway-data-management-system/vnext/rust/Cargo.lock` |
| 扫描依赖数 | **195** crate dependencies |
| Advisory DB 路径 | `/root/.cargo/advisory-db` |
| Advisory DB git rev | `b54e9b51596ad6a02ca5355c1f2743cc5b5d502f` |
| Advisory DB 时间戳 | `2026-07-22 19:32:51 +0200` |
| 本轮 UTC 查询时间 | **2026-07-23 00:11:01 UTC** |
| 已加载 advisories | **1167** |
| 结果 | **无漏洞匹配**（scan clean） |
| Informational warnings | 无（JSON `warnings: {}`） |
| Ignored / withdrawn | 无 |

**Blocking advisory**：无。

---

## 9. Safety 边界与回退路径

| 层 | 策略 |
| --- | --- |
| First-party | 全部 workspace member `#![forbid(unsafe_code)]`；`unsafe_code = "forbid"` workspace lint |
| Third-party | Arrow / PyO3 **内部 unsafe 事实不回避**；first-party 不直接写 `unsafe` |
| GIL / panic | adapter `py.detach` + `run_with_panic_boundary`（R4 evidence） |
| 回退 | 禁用 Python adapter 后：`cargo test -p gateway-compute-core` + Arrow fixtures 仍可验证 kernel 语义 |

**禁止依赖（WP3 production）**：hooks crate、`to_pylist` formal path、Artifact IPC（WP4）、scenario runner（WP5）。

---

## 10. Alternatives 与 rollback（工程判断）

| 场景 | 已考虑替代 | 结论 |
| --- | --- | --- |
| Kernel compute | 纯 Python reference / `to_pylist` bootstrap | **不**作为 production 等价路径 |
| Arrow 互操作 | 手写 C Data Interface | 成本高、易错；保留 pyo3-arrow |
| JSON 解析 | `simd-json` | audit 面扩大，无收益 |
| shared-kernel 错误类型 | 手写 `Error` trait | 保留 `thiserror`；core 的 `ComputeFailure` 为手写实现且不再直连 `thiserror` |
| 禁用 adapter | — | `cargo test -p gateway-compute-core` + normative vectors 仍可闭合语义 |

---

## 11. 证据命令

```bash
cd vnext/rust
cargo metadata --locked --offline --format-version 1 >/dev/null
cargo tree --locked --offline -p gateway-compute-core -e normal
cargo tree --locked --offline -p gateway-compute-python-impl -e normal
cargo tree --locked --offline -p gateway-compute-python -e normal
cargo tree --locked --offline -p gateway-compute-python -e normal,build --target all
cargo tree --locked --offline -p gateway-compute-python -d -e normal,build --target all
cargo tree --locked --offline -p gateway-compute-python -e features --features extension-module
cargo audit --json
```

---

## 12. 结论

WP3 R5 将 R1 §9 草稿升级为定稿 inventory：覆盖 `gateway-compute-core`、`gateway-compute-python-impl`、`gateway-compute-python` 及 `gateway-shared-kernel` production edge。锁定的第三方 package/version/checksum 与 R1 §9.1 一致；R5 删除 core 的两个虚假 direct edge，因此 first-party dependency list 与 lock 文件 SHA 有可解释 delta。本轮 `cargo audit --json` clean；first-party 零 unsafe。
