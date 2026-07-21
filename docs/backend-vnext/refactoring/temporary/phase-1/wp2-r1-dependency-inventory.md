# WP2 R1 Rust Dependency Inventory

状态：WP2 R1 evidence

日期：2026-07-21

适用：Phase 1 D3 / WP2 R1 — `gateway-shared-kernel` scaffold

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（与本文件同次 R1 修订一致）

## 1. 本步实际引入的直接依赖

### `thiserror = 2.0.18`（workspace dependency）

| 项 | 记录 |
| --- | --- |
| 用途 | `CanonicalEncodingError` / `TypeConstructionError` 的 typed `Error` derive |
| Lock identity | workspace pin `thiserror = "=2.0.18"`（已在 WP0 前存在；R1 仅新增 crate 引用） |
| Safe API 边界 | 仅 `#[derive(Error)]` 与 public constructors；无 filesystem / network / process |
| Proc-macro / build / native | `thiserror-impl` proc-macro；无 build script、无 native/system library |
| Third-party unsafe | proc-macro/crate 内部可能含 unsafe；first-party 仅通过 safe API 使用 |
| 维护状态 | crates.io 活跃维护 |
| License | MIT OR Apache-2.0 |
| Advisory | R1 引入引用时无已知阻塞 advisory |
| 替代方案 | 手写 `Display` + `std::error::Error`；可维护性更差 |
| 移除/回退 | 可改为手写 Error impl；当前无移除计划 |

## 2. 计划依赖（尚未写入本 crate `Cargo.toml` / 未为 R1 入 lock）

按 delivery plan §2.2，下列依赖在**首次真正使用的评审节点**再精确 pin 并完成 inventory：

| Crate | 计划版本 | 预期首次使用 | 用途 |
| --- | --- | --- | --- |
| `serde` | `1.0.229` | R2 | JCS duplicate-preserving visitor / value model |
| `serde_json` | `1.0.150` | R2 | JSON parse surface for JCS input |
| `serde_json_canonicalizer` | `0.3.2` | R2 | RFC 8785 serialization after validation |
| `sha2` | `0.11.0` | R4 | semantic / raw blob SHA-256 |
| `base64` | `0.22.1` | R5（dev / integration-test only） | fixture `base64url` decode |

R1 **故意不**预装上述未使用依赖，避免空依赖与过早冻结。

## 3. Production 禁止依赖（整段 WP2）

`gateway-shared-kernel` production path 不得依赖：PyO3、Arrow、filesystem-driven API、env、network、process、ArtifactStore。`gateway-compute-core` 在 WP2 仍不依赖本 crate。

## 4. 证据命令

```bash
cd vnext/rust
cargo metadata --locked --offline --format-version 1 --no-deps > /dev/null
cargo tree -p gateway-shared-kernel
cargo tree -p gateway-shared-kernel --edges normal,dev
```

## 5. 结论

R1 仅新增对既有 workspace `thiserror` 的 production 引用；计划中的 serde/JCS/sha2/base64 留待对应评审节点首次使用时再入 lock 并补 inventory。First-party 保持 `#![forbid(unsafe_code)]` 与 workspace lint 继承。
