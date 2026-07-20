# WP0 Rust Dependency Inventory

状态：WP0 evidence

日期：2026-07-20

适用：Phase 1 D1 / WP0 — `gateway-architecture-check` 引入的直接依赖

Toolchain：`rustc 1.97.0`（`vnext/rust/rust-toolchain.toml`）

Lock identity：`vnext/rust/Cargo.lock`（与本文件同次 WP0 修订一致）

## 1. 直接依赖

### `serde_json = 1.0.150`

| 项 | 记录 |
| --- | --- |
| 用途 | `gateway-architecture-check` 解析 `cargo metadata --format-version 1` JSON，发现 workspace member 与全部 target `src_path` |
| Lock identity | `serde_json 1.0.150` + workspace 传递 `serde_core 1.0.229` |
| Safe API 边界 | 仅使用 `serde_json::from_slice` / `from_str` 反序列化 Cargo 输出；不执行任意文件 I/O 或网络 |
| Proc-macro / build / native | 无 proc-macro、无 build script、无 native/system library |
| Third-party unsafe | crate 内部实现可能含 unsafe；first-party 仅通过 safe public API 使用 |
| 维护状态 | crates.io 活跃维护 |
| License | MIT OR Apache-2.0 |
| Advisory | WP0 引入时无已知阻塞 advisory（以 lock 生成时 crates.io index 为准） |
| 替代方案 | `cargo metadata` 文本解析或 `cargo_metadata` crate；JSON 解析更稳健且依赖面小 |
| 移除/回退 | 若 Cargo metadata schema 稳定且可用 shell+jq，可替换；当前无移除计划 |

### `tempfile = 3.26.0`（dev-dependency）

| 项 | 记录 |
| --- | --- |
| 用途 | architecture-check 单元测试与负向 fixture 在临时目录构造隔离 workspace |
| Lock identity | `tempfile 3.26.0` |
| Safe API 边界 | 仅 `tempfile::tempdir()`；测试代码路径 |
| Proc-macro / build / native | 无 proc-macro；Unix 上通过 `rustix` 系统调用创建临时目录 |
| Third-party unsafe | 传递依赖 `getrandom`、`rustix` 内部可能含 unsafe；first-party 不直接调用 |
| 维护状态 | crates.io 活跃维护 |
| License | MIT OR Apache-2.0 |
| Advisory | WP0 引入时无已知阻塞 advisory |
| 替代方案 | `std::env::temp_dir()` + 手动 `remove_dir_all`；可测试性更差 |
| 移除/回退 | 负向测试改为固定 repo 内 fixture 目录时可移除；当前保留 |

## 2. 传递依赖变化说明

WP0 新增 `gateway-architecture-check` 后，`Cargo.lock` 同步引入/升级了下列传递依赖，均服务于上述直接依赖或既有 workspace crate，**非 WP0 新增业务逻辑**：

| Crate | 引入路径 | 说明 |
| --- | --- | --- |
| `serde_core` | `serde_json` | JSON 反序列化核心 |
| `itoa`, `zmij`, `memchr` | `serde_json` | 格式化/解析支持 |
| `rustix`, `linux-raw-sys`, `bitflags`, `errno` | `tempfile`（dev） | Unix 临时目录与文件描述符 |
| `getrandom`, `fastrand` | `tempfile`（dev） | 随机临时路径 |

既有 workspace crate（`pyo3`、`arrow` 等）的传递依赖未因 WP0 改变直接声明，仅随 lock 整体解析保持兼容。

## 3. 证据命令

离线 correctness gate 前，先执行一次 bootstrap：

```bash
vnext/scripts/bootstrap-rust.sh
```

或：

```bash
vnext/scripts/gate.sh bootstrap
```

随后可重复执行：

```bash
vnext/scripts/gate.sh correctness
```

Lock / tree 快照（WP0 修订时）：

```bash
cd vnext/rust
rustc --version
cargo metadata --locked --offline --format-version 1 --no-deps > /dev/null
cargo tree -p gateway-architecture-check
cargo tree -p gateway-architecture-check --edges normal,dev
```

## 4. 结论

WP0 仅新增两个直接依赖：`serde_json`（production path）与 `tempfile`（dev/test path）。两者均通过 reviewed safe API 使用，first-party 代码保持 zero unsafe。无 nightly、无 cargo-deny、无额外 native FFI 依赖。
