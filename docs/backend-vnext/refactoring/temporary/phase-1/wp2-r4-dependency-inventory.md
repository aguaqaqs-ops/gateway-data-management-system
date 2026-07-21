# WP2 R4 Rust Dependency Inventory

状态：WP2 R4 evidence（policy §6 crypto review 补齐）

日期：2026-07-21

适用：Phase 1 D3 / WP2 R4 — row/collection framing / semantic & raw blob digest

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（本步新增 `sha2==0.11.0`（`default-features = false`）及其传递依赖）

## 1. 本步实际引入的直接依赖

### `sha2 = 0.11.0`（workspace，`default-features = false`）

| 项 | 记录 |
| --- | --- |
| 用途 | `semantic_digest` / `raw_blob_digest` 的 SHA-256；domain-separated semantic prefix + payload，以及 raw blob 直接 hash |
| Lock identity | `sha2 0.11.0`（checksum `446ba717…`）；见 §2 传递依赖闭包 |
| Safe API 边界 | first-party **仅**使用 `sha2::{Digest, Sha256}` 与 `Sha256::digest(&[u8]) -> Output<Sha256>`（见 `gateway-shared-kernel/src/digest.rs`）。`Output<Sha256>` 为固定 32-byte 栈类型；不调用 `Sha256::new` streaming API、不启用 `zeroize` feature、不直接使用 `digest` / `block-buffer` / `crypto-common` crate API |
| Proc-macro / build / native | **`sha2` 本身**：`build = false`、无 build script、无 `links`、不链接 OpenSSL / 系统 crypto 库。**传递闭包**：`cpufeatures` 在部分目标经 `libc` 查询 CPU feature；`libc` **带有 `build.rs`**（生成/探测 C ABI 绑定），属 target-dependent 传递依赖，非 first-party build script。`cpufeatures` 在运行时按目标架构选择纯 Rust 或架构优化实现路径 |
| Third-party unsafe | 传递闭包中 `sha2`、`cpufeatures`、`block-buffer`、`hybrid-array` 为实现性能含 `unsafe`（含 x86/aarch64 等 intrinsic 路径）；`digest 0.11.3` 自身源码未包含 `unsafe`。workspace lint **不**检查 third-party 内部 unsafe。First-party 保持 `#![forbid(unsafe_code)]` 与 zero unsafe call site |
| Features | `default-features = false`；**未**启用 `alloc`、`oid`、`zeroize`。当前调用仅需 core `Digest::digest` 与固定尺寸 `Output`；`alloc` 主要服务 boxed/`DynDigest` 等 API，`oid` 服务 OID 常量——均非 R4 所需。刻意最小化以缩小 lock 闭包（移除 `const-oid`） |
| 维护状态 | crates.io / RustCrypto `hashes` 仓库活跃维护；`sha2 0.11.0` 为 Phase 1 计划 pin 版本 |
| License | MIT OR Apache-2.0（`sha2`）；传递闭包见 §2 |
| Advisory | R4 引入时无已知阻塞 advisory（以 lock 生成时 crates.io index 为准；后续升级须重新查 advisory） |
| 替代方案 | ① first-party 纯 Safe Rust SHA-256（与现有 first-party `base64url` 同类，可消除 crypto 传递依赖但增加自维护面）；② `ring` / OpenSSL 绑定（native/FFI 面更大，不符合 WP2 边界）；③ Phase 1 计划明确选用 `sha2` |
| 移除/回退 | 若 advisory / 维护状态恶化：在 reviewed patch 中 (a) 升级到 inventory 记录的下一 pin，或 (b) 替换为 first-party SHA-256 并移除 `sha2` workspace 依赖；语义 bytes 不变则无需升级 `canonical_encoding_version` |

**Workspace pin：**

```toml
sha2 = { version = "=0.11.0", default-features = false }
```

**First-party 调用点（safe surface only）：**

```rust
use sha2::{Digest, Sha256};
let raw_digest: [u8; 32] = Sha256::digest(payload).into();
```

## 2. 传递依赖闭包（lock 固定）

`cargo tree -p gateway-shared-kernel --edges normal`（2026-07-21，`default-features = false`）：

```text
sha2 v0.11.0
├── cfg-if v1.0.4
├── cpufeatures v0.3.0
│   └── libc v0.2.186          # target-dependent：部分 Unix 目标；libc 含 build.rs
└── digest v0.11.3
    ├── block-buffer v0.12.1
    │   └── hybrid-array v0.4.13
    │       └── typenum v1.20.1
    └── crypto-common v0.2.2
        └── hybrid-array v0.4.13 (*)
```

| Crate | 版本 | 角色 |
| --- | --- | --- |
| `cfg-if` | `1.0.4` | `sha2` / `cpufeatures` 条件编译 |
| `cpufeatures` | `0.3.0` | 目标架构 CPU feature 探测与实现分派；**非**手写 first-party `target_feature` |
| `libc` | `0.2.186` | `cpufeatures` 在部分目标上的 OS feature 查询（如 `getauxval`）；**含 `build.rs`**；无 direct first-party 依赖 |
| `digest` | `0.11.3` | `Digest` trait 与 `Sha256` 类型别名 |
| `block-buffer` / `crypto-common` / `hybrid-array` / `typenum` | 见 tree | RustCrypto 通用 hash 基础设施 |

`const-oid` 不在闭包内（`oid` feature 未启用）。

传递依赖 license（registry 摘要）：RustCrypto 系 crate 多为 MIT OR Apache-2.0；`typenum` 为 MIT OR Apache-2.0；`libc` 为 MIT OR Apache-2.0。

## 3. 计划依赖（仍未为本步入 lock）

无。R5 已引入 `base64==0.22.1`（dev-only）；见 `wp2-r5-dependency-inventory.md`。

## 4. Production 禁止依赖（整段 WP2）

`gateway-shared-kernel` production path 不得依赖：PyO3、Arrow、filesystem-driven API、env、network、process、ArtifactStore、Python runtime。`gateway-compute-core` 在 WP2 仍不依赖本 crate。

## 5. 证据命令

```bash
cd vnext/rust
cargo tree -p gateway-shared-kernel --edges normal
cargo tree -p gateway-shared-kernel -i sha2 --edges all    # 应无 default/alloc/oid feature 链
cargo tree -p cpufeatures --target aarch64-unknown-linux-gnu -e normal  # libc edge（target-dependent）
cargo clippy --locked -p gateway-shared-kernel --all-targets --all-features -- -D warnings
cargo test --locked -p gateway-shared-kernel --all-targets
```

## 6. 结论

R4 首次引入 `sha2==0.11.0`（workspace pin，`default-features = false`）。First-party 仅经 safe `Digest` / `Sha256::digest` 调用；crate 内部架构优化 unsafe 不穿透 first-party。正式 production 导出 `encode_row`、`encode_collection`、`semantic_digest`、`raw_blob_digest`；framing/digest 内部 helper 保持模块私有或 `pub(crate)`。
