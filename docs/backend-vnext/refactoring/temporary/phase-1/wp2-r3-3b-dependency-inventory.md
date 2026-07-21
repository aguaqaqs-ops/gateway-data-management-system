# WP2 R3-3B Rust Dependency Inventory

状态：WP2 R3-3B evidence

日期：2026-07-21

适用：Phase 1 D3 / WP2 R3-3B — typed payload / scalar frame / formal encode API

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（本步未新增 dependency）

## 1. 本步实际引入的直接依赖

无。`encode_typed_scalar` / anomaly envelope 复用既有 `serde_json` + `canonicalize_json_value`；base64url 为 first-party 实现（不引入计划中的 `base64` crate，该 crate 仍留给 R5 fixture 路径）。

## 2. 计划依赖（仍未为本步入 lock）

| Crate | 计划版本 | 预期首次使用 | 用途 |
| --- | --- | --- | --- |
| `sha2` | `0.11.0` | R4 | semantic / raw blob SHA-256 |
| `base64` | `0.22.1` | R5（dev / integration-test only） | fixture `base64url` decode |

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

R3-3B 无 lock / dependency 变化。正式 production 导出 `normalize_logical_literal` 与 `encode_typed_scalar`；`normalize_to_typed_scalar` 保持 `pub(crate)`。
