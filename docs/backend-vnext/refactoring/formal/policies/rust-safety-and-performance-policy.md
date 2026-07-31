# Rust Safety and Performance Policy

状态：正式设计（Accepted Simplified Baseline）

日期：2026-07-31

Policy ID：`gateway-vnext.rust-safety-and-performance-policy`

Owner：Backend vNext Architecture

Policy version：`2`

适用阶段：Phase 1–9

决策依据：
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)

## 1. Goal

Rust用于稳定、批量的数据面能力，不追求语言覆盖率或峰值性能。优先级为：

```text
business and canonical correctness
  -> memory/type safety
  -> maintainability and diagnosability
  -> sufficient end-to-end performance
```

没有业务容量压力或validation-passed measurement时，简单、串行、确定的Safe Rust
优先。

## 2. First-party Safe Rust

Repository内所有first-party Rust source继续禁止unsafe，包括production、test、
example、benchmark和build script。

Workspace必须统一：

```toml
[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"
```

每个member继承workspace lint，并在crate root保留
`#![forbid(unsafe_code)]`。禁止nightly和`#![feature(...)]`。

PyO3/Arrow只使用第三方公开safe API；first-party代码不得手写Python C API、raw
Arrow C pointer conversion、custom allocator bridge或通过wrapper规避unsafe禁令。

## 3. Panic and failure

Production path禁止以`unwrap`、`expect`、`panic!`、`todo!`或`unimplemented!`
处理外部输入、schema、conversion、resource或可恢复failure。

Capability failure使用owner定义的最小结构：

```text
code
message
details optional
```

FFI入口不得让panic跨语言边界传播。Safe supported boundary可将意外panic映射为
稳定failure；abort、segfault或allocator termination不能伪装为普通结果。

Test可以为可读性使用`unwrap/expect`，但所有first-party test仍受unsafe hard
error约束。

## 4. Core and adapter boundary

Rust core：

- 不依赖PyO3、Python object lifecycle、filesystem、network、environment或
  ArtifactStore；
- 接收Arrow数据和小型versioned metadata；
- 返回Arrow结果和小型result/failure；
- 不拥有业务workflow、artifact locator或resource policy。

PyO3 adapter：

- 每table/stream使用粗粒度调用；
- 使用owned Arrow C Stream transfer；
- compute、sort和digest主区间释放GIL；
- 不把Python row/list/dict object graph作为正式bulk path；
- 不自动引入`combine_chunks()`或逐scalar FFI。

## 5. Dependency and toolchain

使用stable pinned Rust toolchain和committed lockfile。新增或升级native/FFI、
allocator、compression、crypto、proc-macro或build dependency必须在普通code
review中说明：

- 当前用途；
- safe API边界；
- build/system依赖影响；
- 维护和移除风险。

不要求独立dependency evidence artifact、exact-commit inventory或签署流程。已知
advisory、license和供应链检查使用项目现有平台/CI能力。

## 6. Performance

优化顺序：

1. 算法和数据结构；
2. 消除Python row/object materialization和重复serialization；
3. 调整Arrow batch/allocation；
4. 根据真实measurement减少copy和peak memory；
5. 证明端到端需求后再引入受控parallelism或safe library provider。

下列能力需要单独Accepted ADR或policy breaking version：

```text
first-party unsafe
nightly
hand-written SIMD/intrinsics
custom/global allocator
unchecked/raw-memory traversal
manual native FFI
unbounded thread/Rayon fan-out
独立compute network service仅由microbenchmark驱动
```

性能测量遵循
[Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)。
不要求Phase 1 memory breakdown evidence或形式化baseline capture。

## 7. Ordinary CI

每个Rust相关变更至少执行适用项：

```text
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --workspace --release --locked
architecture check: every member inherits workspace lints
```

涉及PyO3/Arrow时另运行：

- installed release wheel import；
- native compute golden；
- GIL progress；
- Arrow/artifact round-trip；
- container health/native smoke。

不生成dependency inventory、phase ledger、exact source identity或immutable evidence
bundle。普通command失败直接阻塞对应变更。

## 8. Governance and acceptance

以下变化需要Architecture owner审批并同步ADR 0001：

- 降低unsafe/panic lint；
- 引入nightly、manual FFI、allocator、SIMD或新thread runtime；
- 把Rust扩展到高变化business/domain/application代码；
- 改变Python reference与Rust production provider定位。

验收：

- 所有first-party target的unsafe编译失败；
- Production failure通过typed result传播；
- Core与adapter依赖方向保持；
- Python/Rust对保留golden产生相同canonical结果；
- Native path使用粗粒度Arrow并在compute期间释放GIL；
- 性能优化有真实业务或measurement依据。

## 9. Related authority

- [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [Canonical Row Hash Compute Boundary](../contracts/canonical-row-hash-compute-boundary.md)
- [Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)
