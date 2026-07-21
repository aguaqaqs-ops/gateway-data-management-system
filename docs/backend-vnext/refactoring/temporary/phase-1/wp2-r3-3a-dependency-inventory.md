# WP2 R3-3A Rust Dependency Inventory

状态：WP2 R3-3A evidence

日期：2026-07-21

适用：Phase 1 D3 / WP2 R3-3A — `DeclaredType` / literal grammar / typed normalization

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（本步未新增 dependency）

## 1. 本步实际引入的直接依赖

无。R3-3A 仅使用既有 crate 内模块（`errors` / `types` / `unicode`）与标准库；不新增 production / dev crate。

## 2. 计划依赖（仍未为本步入 lock）

| Crate | 计划版本 | 预期首次使用 | 用途 |
| --- | --- | --- | --- |
| `sha2` | `0.11.0` | R4 | semantic / raw blob SHA-256 |
| `base64` | `0.22.1` | R5（dev / integration-test only） | fixture `base64url` decode |

R3-3B 预计继续不新增 dependency（payload / frame 用既有 ULEB128 + 标准库；anomaly JCS 复用 R2 `canonicalize_json_value`）。

## 3. Production 禁止依赖（整段 WP2）

`gateway-shared-kernel` production path 不得依赖：PyO3、Arrow、filesystem-driven API、env、network、process、ArtifactStore、Python runtime。`gateway-compute-core` 在 WP2 仍不依赖本 crate。

## 4. 证据命令

```bash
cd vnext/rust
cargo tree -p gateway-shared-kernel --edges normal
cargo clippy --locked --offline -p gateway-shared-kernel --all-targets --all-features -- -D warnings
cargo test --locked --offline -p gateway-shared-kernel --all-targets
```

## 5. 结论

R3-3A 无 lock / dependency 变化。First-party 保持 `#![forbid(unsafe_code)]` 与 workspace lint 继承。
