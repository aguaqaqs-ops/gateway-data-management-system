# WP2 R5 Rust Dependency Inventory

状态：WP2 R5 evidence（vector consumer / conformance harness）

日期：2026-07-21

适用：Phase 1 D3 / WP2 R5 — JSONL loader、operation dispatcher、`validate_scalar_frame`、integration conformance

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（本步新增 `base64==0.22.1`、`jsonschema==0.48.2`（`default-features = false`）dev-only）

## 1. 本步实际引入的直接依赖

### `base64 = 0.22.1`（workspace，`dev-dependencies` only）

| 项 | 记录 |
| --- | --- |
| 用途 | integration-test support `tests/support/codec.rs`：fixture `base64url` strict decode / encode；**production 继续 first-party `base64url`（`src/base64url.rs`）** |
| Lock identity | `base64 0.22.1`；见 §2 |
| Safe API 边界 | test support 仅 `base64::engine::general_purpose::URL_SAFE_NO_PAD` 的 `encode` / `decode`；外加与 production 等价的 canonical round-trip 检查 |
| Proc-macro / build / native | 无 build script、无 proc-macro、无 native link |
| Third-party unsafe | **`base64 0.22.1` crate root 为 `#![forbid(unsafe_code)]`**；first-party test support 仅经 safe Engine API 调用 |
| Features | workspace pin `=0.22.1`；默认 features |
| 维护状态 | crates.io 活跃维护 |
| License | MIT OR Apache-2.0 |
| Advisory | R5 引入时无已知阻塞 advisory |
| 移除/回退 | 可改回 first-party test codec 并移除 dev 依赖；不影响 production bytes |

### `jsonschema = 0.48.2`（workspace，`default-features = false`，dev-dependencies only）

| 项 | 记录 |
| --- | --- |
| 用途 | `tests/support/schemas.rs`：Draft 2020-12 manifest / case envelope validation（与 Python `testing.schemas` + `vnext/fixtures/schemas/...` 同源） |
| Lock identity | `jsonschema 0.48.2`（checksum `39d785c0683d1027839f1ac6a43b6d07c63d58ecd363d8146dda4531d53465a1`）；见 §2 传递依赖闭包 |
| Safe API 边界 | test support **仅**使用 `Registry::add/prepare`、`jsonschema::options().with_registry(...).build`、`Validator::validate`；**不**启用 `resolve-http` / `resolve-file` / TLS features；不调用 `reqwest`、不解析远程 `$ref` |
| Proc-macro / build / native | **First-party**：无 build script。**传递闭包 build scripts**（`cargo metadata` `custom-build` target，2026-07-21）：`ahash 0.8.12`（`version_check`）、`getrandom 0.3.4`（target cfg）、`libc 0.2.186`（C ABI 探测）、`parking_lot_core 0.9.12`（TSAN 检测）、`num-traits 0.2.19`（`autocfg` feature 探测）、`libm 0.2.16`（crate 自带 `configure` / 可选 no-panic cfg）。**传递 proc-macro**：`serde_derive`、`displaydoc`、`ref-cast-impl`、`strum_macros`、`yoke-derive`、`zerofrom-derive`、`zerovec-derive`、`zerocopy-derive`（及 `proc-macro2` / `quote` / `syn` 基础设施）。**Native / system link**：`libc` 为纯 Rust FFI 绑定，**不**链接 OpenSSL / `aws-lc-sys`；`parking_lot_core` 在 Linux 经 `libc` 走 futex/syscall 路径，无额外 `links =` crate；`libm` 为 C math 函数的**纯 Rust 实现**，非 system libm 绑定。`default-features = false` 刻意移除 HTTP/TLS（`aws-lc-sys` / `reqwest`）传递闭包 |
| Third-party unsafe / SIMD | 传递闭包含 `unsafe` 与架构优化路径；workspace lint **不**检查 third-party 内部 unsafe。First-party 保持 `#![forbid(unsafe_code)]`。**重点 crate**：`ahash`（`getrandom` + `zerocopy` 哈希表）、`bytecount`（SIMD newline/tab 计数）、`uuid-simd` / `vsimd`（UUID 解析 SIMD）、`zerocopy`（`zerocopy-derive` + 可能 intrinsic）、`regex` / `regex-automata`（DFA 优化）、`hashbrown` / `foldhash`（allocator-aware map）。First-party 不直接调用上述 crate API |
| Features | `default-features = false`（禁用 `resolve-http`、`resolve-file`、`tls-aws-lc-rs`） |
| 维护状态 | crates.io / Stranger6667/jsonschema 活跃维护 |
| License | MIT（`jsonschema`）；传递闭包多为 MIT OR Apache-2.0（ICU / serde / regex 系） |
| Advisory | R5 引入时无已知阻塞 advisory |
| 替代方案 | ① 手写 validator（与 formal schema 漂移风险高）；② 仅 Python 侧 schema gate（Rust conformance 失去 parity）；③ 更轻量 JSON Schema 子集 crate（需重新映射 Draft 2020-12 keyword 面）。Phase 1 选用 `jsonschema` + fixture registry |
| 移除/回退 | 可替换为手写 validator 并移除 dev 依赖，但会与 formal schema 漂移；不推荐。若 advisory / TLS 传递链回归：保持 `default-features = false` 并升级到 reviewed pin |

### `serde_json_canonicalizer = 0.3.2`（workspace，**dev-dependencies** 引用，lock 已存在）

| 项 | 记录 |
| --- | --- |
| 用途 | `tests/support/closure.rs` 中 `vector_set_content_digest` 投影体序列化 |
| 引入方式 | 非新 lock entry；R2 已入 production path，R5 仅在 dev-dependencies 复用同一 workspace pin |

## 2. 传递依赖闭包（lock 固定）

`cargo tree -p gateway-shared-kernel --edges dev -i base64`（2026-07-21）：

```text
base64 v0.22.1
[dev-dependencies]
└── gateway-shared-kernel v0.1.0
```

`cargo tree -p jsonschema`（2026-07-21，`default-features = false`；约 89 个 crate）：

```text
jsonschema v0.48.2
├── ahash v0.8.12                    # build.rs + zerocopy/getrandom
├── bytecount v0.6.9                 # SIMD dispatch
├── fancy-regex / regex / regex-automata
├── fraction → num → num-traits      # num-traits build.rs (autocfg); libm build.rs (configure)
├── idna → icu_* (displaydoc, yoke/zerofrom/zerovec derive)
├── jsonschema-regex / referencing
│   ├── fluent-uri → ref-cast-impl (proc-macro)
│   ├── hashbrown / parking_lot → parking_lot_core + libc
│   └── serde_json
├── strum → strum_macros (proc-macro)
└── uuid-simd → vsimd                 # SIMD UUID parse
```

**已排除（`default-features = false` 证据）：** `aws-lc-sys`、`reqwest`、`hyper`、`tokio` TLS 链不在闭包内（`cargo tree -p jsonschema -e features` 无 `resolve-http` edge）。

### `jsonschema` 传递闭包审计表

| Crate | 版本 | 角色 | build / proc-macro | unsafe / SIMD / native |
| --- | --- | --- | --- | --- |
| `ahash` | `0.8.12` | `referencing` / `jsonschema` hash map | **build.rs** (`version_check`)；`zerocopy-derive` | `unsafe` 哈希；`getrandom` 种子 |
| `getrandom` | `0.3.4` | `ahash` RNG | **build.rs**（target cfg） | OS RNG via `libc`（Unix） |
| `libc` | `0.2.186` | `getrandom`、`parking_lot_core` | **build.rs**（C ABI） | FFI 绑定；无 OpenSSL |
| `parking_lot_core` | `0.9.12` | `referencing` 并发 map | **build.rs**（TSAN 检测） | `unsafe`；Linux 经 `libc` futex/syscall |
| `num-traits` | `0.2.19` | `fraction` / `num` | **build.rs** (`autocfg`) | 纯 Rust numeric trait |
| `libm` | `0.2.16` | `num-traits` float | **build.rs**（crate `configure` / 可选 no-panic） | C math 纯 Rust 实现；非 system libm 绑定 |
| `zerocopy` | `0.8.54` | `ahash` | `zerocopy-derive` | `unsafe` transmute / 可能 intrinsic |
| `bytecount` | `0.6.9` | `jsonschema` 计数 | 无 | **SIMD**（x86/NEON dispatch） |
| `uuid-simd` / `vsimd` | `0.8.0` | UUID format check | 无 | **SIMD** UUID 解析 |
| `serde` / `serde_derive` | `1.0.229` | 多 crate 序列化 | **proc-macro** | derive only |
| `displaydoc` | `0.2.6` | ICU 错误显示 | **proc-macro** | derive only |
| `ref-cast-impl` | `1.0.26` | `fluent-uri` | **proc-macro** | derive only |
| `strum_macros` | `0.28.0` | `strum` enum 工具 | **proc-macro** | derive only |
| `yoke-derive` / `zerofrom-derive` / `zerovec-derive` | `0.8.x` / `0.1.x` / `0.11.x` | ICU 零拷贝字符串 | **proc-macro** | derive only |
| `regex` / `regex-automata` | `1.13.1` / `0.4.16` | pattern / format | 无 | `unsafe` DFA 优化路径 |
| `hashbrown` | `0.17.1` | `referencing` map | 无 | allocator API；`foldhash` |

传递依赖 license（registry 摘要）：`jsonschema` MIT；ICU / serde / regex / parking_lot 系多为 MIT OR Apache-2.0；`libc` MIT OR Apache-2.0。

## 3. Production 路径（R5 未变更）

R5 **未**向 production `[dependencies]` 新增 crate。Test-only（`tests/support/`）新增 `schemas` 模块；`validate_scalar_frame` 仍不 export。

## 4. Production 禁止依赖（整段 WP2，重申）

`gateway-shared-kernel` production path 不得依赖：PyO3、Arrow、filesystem、env、network、process、Python runtime、`base64` / `jsonschema` crate。

## 5. 证据命令

```bash
cd vnext/rust
cargo tree -p gateway-shared-kernel --edges dev -i base64
cargo tree -p gateway-shared-kernel --edges dev -i jsonschema
cargo tree -p jsonschema                              # 完整传递闭包
cargo tree -p jsonschema -e features                  # 确认无 resolve-http/TLS
cargo metadata --format-version 1 --locked | jq '.packages[] | select(.name=="libc") | .targets'  # build target 证据
cargo tree -p gateway-shared-kernel --edges normal          # dev crate 不在 production 闭包
cargo fmt --check
cargo clippy --locked -p gateway-shared-kernel --all-targets -- -D warnings
cargo test --locked -p gateway-shared-kernel --all-targets
```

## 6. 结论

R5 将 `base64==0.22.1` 与 `jsonschema==0.48.2`（`default-features = false`）以 dev-dependencies only 写入 lock。Closure 在 strict JSON（递归 duplicate + EOF）之后执行正式 schema validation，再 JCS/dispatch。Integration test 仅在 `EnvNotSet` 时 fallback 生成 candidate，显式 env 错误 fail closed；vector root 在 canonicalize 前拒绝 symlink 祖先。
