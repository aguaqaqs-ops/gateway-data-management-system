# WP2 R2 Rust Dependency Inventory

状态：WP2 R2 evidence

日期：2026-07-21

适用：Phase 1 D3 / WP2 R2 — `gateway-shared-kernel` JCS / Identifier / ULEB128

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（与本文件同次 R2 修订一致）

## 1. 本步新引入的直接依赖

### `serde = 1.0.229`（workspace）

| 项 | 记录 |
| --- | --- |
| 用途 | `DeserializeSeed` / `Visitor` / `Serialize` trait；recursive Serde visitor 构建 `Value` 并在完整 key/value pair 之后检测 duplicate；亦供 `serde_json_canonicalizer` 使用 |
| Lock identity | `serde 1.0.229` + `serde_core 1.0.229` |
| Safe API 边界 | 仅 trait 与 visitor hooks；first-party 不调用 unsafe |
| Proc-macro / build / native | 无（本 crate 未启用 `derive` feature）；无 build script、无 native/system library |
| Third-party unsafe | `serde` / `serde_core` 内部实现可能含 unsafe；first-party 仅通过 safe public API 使用 |
| 维护状态 | crates.io 活跃维护（serde-rs） |
| License | MIT OR Apache-2.0 |
| Advisory | R2 引入时无已知阻塞 advisory（以 lock 生成时 crates.io index 为准） |
| 替代方案 | 手写 JSON visitor 与 JCS serializer；成本高且易偏 RFC 8785 |
| 移除/回退 | 随 `serde_json` / `serde_json_canonicalizer` 一并替换为 reviewed 自研栈 |

### `serde_json = 1.0.150`（workspace，`float_roundtrip`）

| 项 | 记录 |
| --- | --- |
| 用途 | `Deserializer::from_str` 驱动 recursive visitor；`Value` / `Number` / `Map` 作为校验后的内存 JSON 模型 |
| Lock identity | `serde_json 1.0.150`（feature `float_roundtrip`） |
| Safe API 边界 | `Deserializer` + `Value` 构造/读取；**不**用 stock `from_str::<Value>` 的 error message 决定 stable code |
| Proc-macro / build / native | 无 proc-macro、无 build script、无 native/system library |
| Third-party unsafe | crate 内部实现可能含 unsafe（含解析缓冲）；first-party 仅 safe API |
| 维护状态 | crates.io 活跃维护（serde-rs） |
| License | MIT OR Apache-2.0 |
| Advisory | R2 引入时无已知阻塞 advisory |
| 替代方案 | 完全自研 JSON deserializer；或 `simd-json`（native/unsafe 面更大，不采用） |
| 移除/回退 | 若 visitor/`Value` 模型被自研 AST 替换，可移除直接依赖；当前保留 |
| 说明 | stock 解析会把 `NaN`/`Infinity`/overflow/`\uD800` 打成未区分 Syntax。R2 流程：① first-party grammar-aware parse **完整扫描**文档，仅语法失败立即返回 `JCS_SYNTAX_INVALID`；语义问题记为 typed events（object 闭合且未受 mid-object NaN/OOR 打断时才 commit duplicate；UTF-16 key identity；Unicode 遍历首错；NaN/OOR literal 顺序；float overflow）。② 语法成功后 **recursive Serde visitor** 构建 `Value` 并检测 duplicate（含纯 duplicate 文档，不再被 first-party 提前返回旁路）。③ 按固定阶段选 stable code。Serde 拒收 surrogate/NaN/overflow 时回退 first-party `Value`+events |

### `serde_json_canonicalizer = 0.3.2`

| 项 | 记录 |
| --- | --- |
| 用途 | RFC 8785 JCS 序列化（UTF-16 key order、number formatting） |
| Lock identity | `serde_json_canonicalizer 0.3.2`；传递 `ryu-js 1.0.3` |
| Safe API 边界 | 仅 `to_vec`；调用前已完成 I-JSON/Unicode/duplicate 校验 |
| Proc-macro / build / native | 无 build script / native |
| Third-party unsafe | 依赖内部可能含 unsafe；first-party 仅 safe API |
| 维护状态 | crates.io 维护中（evik42/serde-json-canonicalizer） |
| License | MIT |
| Advisory | R2 引入时无已知阻塞 advisory |
| 替代方案 | 自研 JCS serializer；计划明确选用该 crate |
| 移除/回退 | 若偏离 RFC 8785 向量，替换为 reviewed 自研实现 |

## 2. 既有直接依赖（无版本变化）

- `thiserror = 2.0.18`（R1）

## 3. 尚未引入（后续节点）

| Crate | 计划版本 | 节点 |
| --- | --- | --- |
| `sha2` | `0.11.0` | R4 |
| `base64` | `0.22.1` | R5（dev/integration-test only） |

## 4. 证据命令

```bash
cd vnext/rust
cargo tree -p gateway-shared-kernel --locked --offline
cargo test --locked --offline -p gateway-shared-kernel --all-targets
```

## 5. 结论

R2 按首次使用引入 serde / serde_json / serde_json_canonicalizer 并精确入 lock。JCS 使用整文档 first-party syntax/event scan + recursive Serde visitor（duplicate 检测在语法成功路径上实际执行）+ canonicalizer 序列化。First-party 保持 zero unsafe。
