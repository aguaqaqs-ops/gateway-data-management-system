# WP3 R5 — Kernel-native Component Sign-off

状态：R5 sign-off evidence（pre-commit capture）

日期：2026-07-23

Authority：

- [WP3–WP5 Checkout 计划](wp3-wp5-checkout-plan.md) §2、§3、§4 R5、§8
- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md) §1.1、§9
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md) §5–§7
- [Shared Canonical Encoding](../../formal/contracts/shared-canonical-encoding.md)
- [Canonical Encoding Normative Vector Schema](../../formal/contracts/canonical-encoding-normative-vector-schema.md)
- [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md)
- [Rust Safety and Performance Policy](../../formal/policies/rust-safety-and-performance-policy.md)
- [Implementation Stages](../../formal/plans/implementation-stages.md)
- [Phase 1 Implementation Design and Delivery Plan](../../formal/plans/phase-1-implementation-design-and-delivery-plan.md)
- [ADR-0001 Python/Rust Hybrid Compute Strategy](../../formal/adr/0001-python-rust-hybrid-compute-strategy.md)
- [WP3 R2 Rust Core Evidence](wp3-r2-rust-core-evidence.md)
- [WP3 R3 PyO3 Adapter Evidence](wp3-r3-pyo3-adapter-evidence.md)
- [WP3 R4 Kernel Component Evidence](wp3-r4-kernel-component-evidence.md)
- [WP3 R5 Dependency Inventory](wp3-r5-dependency-inventory.md)（定稿）

Gate：**`PR-CORRECTNESS` + `native-kernel` component sign-off**；**非** `PR-NATIVE` / **`gate.sh native`**

---

## 1. Sign-off 结论与边界

**WP3 kernel-native component sign-off passed; ready to enter WP4.**

| 项 | 声明 |
| --- | --- |
| 闭合范围 | WP3 kernel：`gateway-compute-core` + PyO3 adapter + native-kernel component tests |
| Gate | `PR-CORRECTNESS` + `native-kernel` component（`gate.sh correctness` + `native_kernel_component.sh`） |
| **不是** | `PR-NATIVE`、Phase 1 complete、`gate.sh native` passed |
| 本步代码变更 | 无 runtime semantic `.rs` delta；移除 core 两个未使用 direct edge，并补齐 production `panic!` 负向门禁 fixture |
| 下一步 | **WP4 R1** — ArtifactRef / manifest / identity API |

---

## 2. 审计时间、环境、工具版本

| 项 | 值 |
| --- | --- |
| 审计执行 UTC | **2026-07-22 23:49:19 – 2026-07-23 00:18:50 UTC** |
| OS | Linux 6.6.114.1-microsoft-standard-WSL2 (x86_64) |
| Rust | `rustc 1.97.0` / `cargo 1.97.0`（`vnext/rust/rust-toolchain.toml`） |
| Python | **3.14.6** |
| uv | **0.11.30** |
| maturin | **1.14.1**（`pyproject.toml` + `uv.lock`；gate 经 `uv` 调用，非全局 PATH） |
| pyarrow | **25.0.0**（`vnext/backend/uv.lock`） |
| cargo-audit | **0.22.2** |

---

## 3. R4 已签核基线与 pre-commit 澄清

| 项 | 值 |
| --- | --- |
| R4 sign-off commit | `6e14f91cb65a67eb1dd54e4e392b41462755f5ac` |
| R5 审计 source baseline | **同上**（`git merge-base --is-ancestor` exit 0） |
| R4 evidence 状态说明 | [`wp3-r4-kernel-component-evidence.md`](wp3-r4-kernel-component-evidence.md) 中 “worktree 未提交” 等为 **pre-commit capture**；R4 最终签核提交为 `6e14f91` |
| R5 不修改 R4 evidence | 澄清仅在本 R5 文档记录 |

---

## 4. 当前 HEAD、工作区与 patch identity

| 项 | 值 |
| --- | --- |
| 当前 HEAD | `6e14f91cb65a67eb1dd54e4e392b41462755f5ac` |
| Branch | `main` |
| tracked diff vs R4 baseline | `Cargo.toml` / `Cargo.lock` dependency-edge cleanup；architecture negative fixture +14 lines |
| **runtime semantic source delta from R4 baseline** | **none**（无 production `.rs` 行为变更） |
| deterministic non-evidence patch SHA-256 | `2f55ae170cf5bd7fbd4e682424c55f7076e63dfe6b40a4bebe17c647de9b740f` |
| untracked（R5 evidence） | `wp3-r5-kernel-native-signoff.md`、`wp3-r5-dependency-inventory.md` |
| `git diff --check` | clean |

```bash
git rev-parse HEAD
# 6e14f91cb65a67eb1dd54e4e392b41462755f5ac

git status -sb
# ## main
#  M vnext/rust/Cargo.lock
#  M vnext/rust/gateway-architecture-check/tests/negative_fixtures.rs
#  M vnext/rust/gateway-compute-core/Cargo.toml
# ?? docs/.../wp3-r5-kernel-native-signoff.md
# ?? docs/.../wp3-r5-dependency-inventory.md

git diff 6e14f91cb65a67eb1dd54e4e392b41462755f5ac -- . \
  ':(exclude)docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-kernel-native-signoff.md' \
  ':(exclude)docs/backend-vnext/refactoring/temporary/phase-1/wp3-r5-dependency-inventory.md' \
  | sha256sum
# 2f55ae170cf5bd7fbd4e682424c55f7076e63dfe6b40a4bebe17c647de9b740f  -
```

---

## 5. Authority 文档清单

已按 formal contract 优先顺序阅读并对照实现：

1. `canonical-row-hash-compute-boundary.md` §5–§7
2. `shared-canonical-encoding.md`
3. `canonical-encoding-normative-vector-schema.md`
4. `fixture-oracle-and-conformance.md`
5. `rust-safety-and-performance-policy.md`
6. `implementation-stages.md`
7. `phase-1-implementation-design-and-delivery-plan.md`
8. `adr/0001-python-rust-hybrid-compute-strategy.md`
9. `wp3-wp5-checkout-plan.md` §2–§4 R5
10. `wp3-r1-arrow-pyo3-design.md` §1.1、§9
11. R2/R3/R4 evidence

**Formal vs 实现冲突**：未发现。

---

## 6. WP3 R1–R4 累积交付物清单

| Checkout | 交付物 | 状态 |
| --- | --- | --- |
| R1 | `wp3-r1-arrow-pyo3-design.md`、error registry、mapping v1、dependency 草稿 | ✅ |
| R2 | `gateway-compute-core`、`unordered_row_hashes_content_digest`、Arrow fixtures、Rust contract tests | ✅ |
| R3 | `gateway-compute-python-impl`、C Stream adapter、facade、architecture 负向检查 | ✅ |
| R4 | GIL/panic/failure/determinism component tests、`native_kernel_component.sh`、wheel EXIT trap | ✅ |
| R5 | 本 sign-off + dependency inventory 定稿；direct-edge cleanup；`panic!` 负向门禁 | ✅ |

---

## 7. Canonical semantics 审查结果

**审查方法**：对照 formal contract 阅读 `gateway-shared-kernel` framing/scalar/digest、`gateway-compute-core` pipeline/extract/row_encode/request；交叉验证 normative vectors 与 component tests。

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| Row framing / column order / null / scalar | ✅ 与 shared-kernel `encode_row` 一致；nullable null slot 经 `row_encode.rs:12-28` 适配为 `DeclaredType::Null` 仅用于编码 | `framing.rs:14-50`、`row_encode.rs` |
| Row hash → sort → table digest 分层 | ✅ `pipeline.rs:45-62` 先收集 per-row `raw_hash()`，再 `sort()`，再 `unordered_row_hashes_content_digest` | `pipeline.rs`、`framing.rs:197-203` |
| empty / multi-batch / duplicate | ✅ empty digest oracle；multi-batch 字节一致；duplicate 保留 | `test_component_determinism.py:18-29,32-46,147-158` |
| batch / row permutation 不变性 | ✅ 覆盖 row hash bytes、排序顺序、`raw_content_digest` | `test_component_determinism.py:82-109,112-133,135-144` |
| stream 边界不影响 digest | ✅ `RecordBatchReader` 逐 batch 消费；schema 一致性检查 | `pipeline.rs:27-36` |
| 禁止 `to_pylist` / `combine_chunks` / generator materialization | ✅ production path 无匹配；facade 仅 `RecordBatch`/`Table`/`RecordBatchReader` | `__init__.py:29-40`；architecture-check |
| normative vector / encoding version 未迁就实现 | ✅ vector / contract / encoding version 路径相对 R4 无 diff | scoped `git diff 6e14f91 -- docs/.../formal vnext/fixtures` |

**Findings**：none。

---

## 8. Arrow / PyO3 safe-boundary 审查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| first-party `#![forbid(unsafe_code)]` | ✅ 全部 workspace member | 各 crate `lib.rs`；architecture-check |
| 无 first-party raw Arrow C ABI / PyCapsule / raw pointer | ✅ adapter 经 `PyRecordBatchReader` safe API | `adapter.rs:132-167` |
| `gateway-compute-core` 不依赖 pyo3 | ✅ `cargo tree --locked --offline -p gateway-compute-core -i pyo3` 无匹配 | inventory §1 |
| GIL：import/export attached；parse+compute detached | ✅ `adapter.rs:239-254` | `py.detach(|| detached_parse_and_compute(...))` |
| production 无 test hook / fault injection 导出 | ✅ `test_hooks` 为 `#[cfg(test)]`；gate 断言 hooks `[]` | `adapter.rs:15-117` |
| production release 单一 cdylib | ✅ `gateway-compute-python` only | `pyproject.toml`、`architecture-check` |
| 无额外 production cdylib / hook crate | ✅ architecture-check exit 0 | 验证矩阵 §18 |

**Findings**：none。

---

## 9. GIL / panic / failure mapping 审查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| panic 不跨 FFI | ✅ `catch_unwind` → `NativePanic` | `adapter.rs:122-129` |
| panic matrix（import/compute/export） | ✅ `panic_matrix.rs` | Rust `kernel_component_tests` |
| failure precedence / stable envelope | ✅ `errors.rs:44-60`；`failure_goldens.rs` | component-pytest failure suite |
| `effect=NONE` | ✅ static fallback envelope 含 `"effect":"NONE"` | `errors.rs:8` |
| GIL 探针为真实 native entry | ✅ `gil_probe.rs`、`gil_00_python_thread.rs`、`gil_controller.rs` | 非 Python mock |
| 超时 / RAII cleanup | ✅ `HOLD_RELEASE_TIMEOUT` + hold clear 断言 | `adapter.rs:33,106-114`；R4 evidence |

**Findings**：none。

---

## 10. Stream determinism 审查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 重复执行字节一致 | ✅ `test_multi_batch_serial_execution_is_byte_identical` 等 | `test_component_determinism.py:63-69,72-79` |
| permutation 覆盖 hash bytes + digest | ✅ §7 表 | `test_component_determinism.py:82-109` |
| 输出 row hashes 排序 | ✅ unsigned lexicographic | `test_component_determinism.py:135-144` |
| batch 划分不影响结果 | ✅ single vs split batch | `test_component_determinism.py:32-46` |

**Findings**：none。

---

## 11. Production release inventory

| 项 | 值 |
| --- | --- |
| Production cdylib | `gateway-compute-python`（maturin `extension-module`） |
| 导出 module | `gateway_compute.gateway_compute` |
| Test hooks | **`[]`**（gate + R5 重验） |
| Source tree `.so` | **0**（`find .../python -name '*.so'`） |
| 额外 hook crate / production cdylib | **无**（architecture-check） |
| wheel 构建 | maturin **1.14.1** release wheel；`manylinux_2_34_x86_64` |

---

## 12. 完整 dependency inventory

定稿见 **[wp3-r5-dependency-inventory.md](wp3-r5-dependency-inventory.md)**：

- R1 §9.3 全字段逐项闭合（direct production deps）
- 第三方 resolved package/version/checksum 与 R1 §9.1 **无 delta**；core direct-edge list 与 lock SHA 有 R5 审计修正
- 传递闭包附录（重复版本、proc-macro、build、native）
- Python pins：`pyarrow 25.0.0`、`maturin 1.14.1`

---

## 13. Proc-macro / build / native / system 清单

见 inventory §7.2。要点：

- **Proc-macro**：`serde_derive`、`thiserror-impl`、`pyo3-macros`、`zerocopy-derive`
- **build.rs**：`pyo3` / `pyo3-ffi`、`ahash`、`num-traits`、`libm`、`numpy` 等；`pyo3-build-config` 是其 build-dependency library
- **FFI / native**：`pyo3-ffi`、`libc`（Python C API / OS 边界）
- **`links` crate**：无 first-party；`pyo3` (`pyo3-python`)、`pyo3-ffi` (`python`)；all-target 另含 `wasm-bindgen-shared` (`wasm_bindgen`)

---

## 14. Third-party unsafe 事实与 first-party zero-unsafe

| 层 | 结论 |
| --- | --- |
| First-party | **zero unsafe**（`forbid(unsafe_code)` + workspace lint + clippy `-D warnings`） |
| Arrow | buffer/FFI 内部 `unsafe`（third-party，first-party 不经 raw ABI） |
| PyO3 / pyo3-ffi | Python C API `unsafe`（third-party） |
| numpy（传递） | ndarray + FFI 边界（third-party） |

---

## 15. Advisory scan 证据（本轮）

| 项 | 值 |
| --- | --- |
| 命令 | `cd vnext/rust && cargo audit --json` |
| 工具 | cargo-audit **0.22.2** |
| 退出码 | **0** |
| Cargo.lock | `vnext/rust/Cargo.lock`（**195** deps） |
| Advisory DB rev | `b54e9b51596ad6a02ca5355c1f2743cc5b5d502f` |
| DB 时间戳 | `2026-07-22 19:32:51 +0200` |
| 本轮 UTC | `2026-07-23 00:11:01 UTC` |
| 结果 | **clean**（1167 advisories loaded，无匹配） |

---

## 16. License / SPDX 与维护状态

Direct production deps SPDX（`cargo metadata` + crates.io/PyPI，查询 **2026-07-23**）：

| 包 | SPDX | 来源 |
| --- | --- | --- |
| arrow-* 59.1.0 | Apache-2.0（array 另含 MIT） | crates.io |
| pyo3 / pyo3-arrow 0.29/0.19 | MIT OR Apache-2.0 | crates.io |
| serde / serde_json | MIT OR Apache-2.0 | crates.io |
| serde_json_canonicalizer 0.3.2 | MIT | crates.io |
| sha2 0.11.0 | MIT OR Apache-2.0 | crates.io |
| thiserror 2.0.18 | MIT OR Apache-2.0 | crates.io |
| pyarrow 25.0.0 | Apache-2.0 | PyPI |
| maturin 1.14.1 | MIT OR Apache-2.0 | PyPI |

**工程兼容性判断**（非法律意见）：production closure 均有 permissive 授权路径，且无 copyleft-only package；与 proprietary workspace **兼容**。

---

## 17. Alternatives 与 rollback

见 inventory §10。摘要：

- 纯 Python reference / `to_pylist` **不**替代 production kernel
- 禁用 adapter 后：`cargo test -p gateway-compute-core` + normative vectors 仍可验证语义
- 不回退 normative vectors 或 encoding version

---

## 18. 验证矩阵（R5 重跑）

| 命令 | Exit | 结果摘要 |
| --- | ---: | --- |
| `cargo fmt --check` | 0 | pass |
| `cargo clippy --locked --offline --workspace --all-targets --all-features -- -D warnings` | 0 | pass |
| `cargo test --locked --offline --workspace --all-targets` | 0 | **240** passed |
| `cargo build --locked --offline --workspace --release` | 0 | pass |
| `gateway-architecture-check` CLI | 0 | pass |
| architecture tests（workspace test 内） | 0 | **35** passed（lib 21 + negative fixtures 14；含真实 `panic!` 拒绝） |
| `native_kernel_component.sh wheel-trap-regression` | 0 | body=0/restore=99→99；body=42/restore=99→42 |
| `native_kernel_component.sh wheel-smoke` | 0 | empty/multi-batch/duplicate ok；tmp 已清理 |
| `native_kernel_component.sh component-pytest` | 0 | **18** passed |
| `gate.sh correctness` | 0 | shared-kernel **131**（coverage 82.58%）；repository **5**；Rust **240**；component **18**；backend selected **22** |
| backend selected pytest（gate 内） | 0 | **22** passed |
| **gate Python 精选合计** | 0 | **40**（18+22） |
| `gateway-compute-python/tests` 全量 | 0 | **38** passed |
| `vnext/backend/tests` 全量 | 0 | **4** passed；另有 1 条 third-party Starlette deprecation warning |
| **完整 Python 合计** | 0 | **42**（38+4） |
| `gate.sh native` | **2** | `native gate is not implemented until WP4 R4`（预期） |

Architecture negative fixtures 实际执行并拒绝：未继承 workspace lint、first-party unsafe、production `unwrap` / `panic!`、原名与重命名 hook/fault feature、adapter 对重命名 hook crate 的依赖，以及额外 production cdylib target。

### 计数差异说明

| 集合 | 计数 | 说明 |
| --- | ---: | --- |
| gate Python 精选 | 40 | component 18 + backend 精选 22（含 facade/production_extension/canonical_row_hash） |
| 完整 Python | 42 | `gateway-compute-python/tests` 38 + `backend/tests` 4 |
| Delta | +2 | 全量多 **2** 项 backend 非 native-kernel 段：`tests/test_app.py`（healthz）、`tests/test_architecture.py`（legacy import 边界）；gate 故意精选 native-kernel 最小闭包 |

---

## 19. Cleanup 与 hermeticity

| 检查 | 结果 |
| --- | --- |
| R5 wheel tmp（本轮） | gate/smoke 使用 `/tmp/tmp.*`；trap regression 验证删除 |
| `/tmp/tmp.*` 下本项目 whl（R5 后查询） | **0** |
| 预存 `/tmp/gw-wheel-test/*.whl` | **1**（非 R5 产生；不删除非本项目所有权 `/tmp` 内容） |
| production hooks | **`[]`** |
| source tree `.so` | **0** |
| `uv sync --reinstall-package gateway-compute-python` | gate 后 production 已恢复 path install |
| `git diff --check` / tracked 污染 | clean |
| `gate.sh correctness` 离线 locked | ✅ `UV_OFFLINE` / `CARGO_NET_OFFLINE` |
| advisory 未塞进 gate | ✅ 仅 R5 evidence 执行 `cargo audit --json` |

---

## 20. Deferred register

| 项 | 归属 |
| --- | --- |
| `ArtifactRef` / Arrow IPC write→reopen / corrupt IPC | **WP4** |
| raw IPC hash vs semantic `raw_content_digest` | **WP4** |
| 正式 **`gate.sh native` / `PR-NATIVE`** | **WP4 R4** |
| Scenario YAML / harness / golden envelope | **WP5** |
| `PHASE-EXIT-CONTAINER` / Phase 1 exit | **WP5 R5** |
| Normative vector 变更 | — |
| Rayon / SIMD / external sort / performance claims | Phase 3+ |

---

## 21. Unresolved findings

**none**

（无 Blocker / Major / Minor 未闭合项。）

本轮审计曾发现并已闭合两项 **Minor**：

1. `vnext/rust/gateway-compute-core/Cargo.toml:10-16` 的 `arrow-data`、`thiserror` 没有 first-party symbol 使用；已删除虚假 direct edge，`Cargo.lock` 仅同步删除 first-party dependency-list 项，第三方 resolved identity 未变。
2. `vnext/rust/gateway-architecture-check/tests/negative_fixtures.rs:171-183`：原有检查已覆盖 `unwrap` shortcut，但缺少独立的 production `panic!` 负向 fixture；已补齐并由完整 workspace test 验证。

---

## 22. 最终结论

**WP3 kernel-native component sign-off passed; ready to enter WP4.**

- Gate：**`PR-CORRECTNESS` + native-kernel component** ✅
- **不是** `PR-NATIVE`；**不是** Phase 1 complete
- 正式 **`gate.sh native`** 仍在 **WP4 R4**
- runtime semantic source delta from R4 baseline：**none**；非 evidence patch SHA-256 见 §4
- 本文为 pre-commit capture；同一提交 SHA 不在 evidence 内自引用，最终 SHA 在提交后回复中报告

**Reviewer sign-off**：R5 automated audit complete — 2026-07-23
