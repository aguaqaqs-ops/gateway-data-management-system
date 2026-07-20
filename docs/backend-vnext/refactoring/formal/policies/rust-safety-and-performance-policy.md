# Rust Safety and Performance Policy

状态：正式设计（Accepted）

日期：2026-07-19

Policy ID：`gateway-vnext.rust-safety-and-performance-policy`

Owner：Backend vNext Architecture

Policy version：`1`

适用阶段：Phase 1–9

## 1. 目标与优先级

Backend vNext 是业务系统重构，不是系统底层、数据库内核或极限低延迟工程。Rust 的目标是为稳定批量数据能力提供确定语义、受控内存布局、粗粒度 Arrow 边界和可预测运行特征，不以语言覆盖率、微基准或峰值吞吐为目标。

工程优先级固定为：

```text
business and byte correctness
  -> memory/type safety
  -> maintainability and diagnosability
  -> sufficient end-to-end performance
  -> peak performance
```

性能不足必须由validation-passed的vNext measurement、容量目标或明确materialization evidence证明。不能仅因“Rust可以更快”增加语言边界、并行或低层优化。

## 2. 适用范围与定义

本policy覆盖repository内所有first-party Rust source：workspace member、library/binary、PyO3 adapter、worker/CLI、test、example、benchmark、build script和未来first-party proc macro。

- `first-party unsafe`：本repository Rust source中的`unsafe` block/function/trait/impl/extern/static、raw pointer dereference、unsafe attribute或其他由`unsafe_code` lint覆盖的construct。
- `third-party unsafe`：Cargo dependency内部实现使用的unsafe。Workspace lint不把它变成first-party code，也不能据此宣称完整进程零unsafe。
- `production path`：非`#[cfg(test)]`、非test-only fixture/helper且可能进入release artifact的代码。
- `performance exception`：为性能理由偏离本policy；不存在临时、口头或单PR exception。

## 3. First-party Safe Rust 硬门禁

Policy v1禁止全部first-party unsafe，不按core/adapter、生产/test或性能用途提供例外：

```text
unsafe {}
unsafe fn / trait / impl
unsafe extern / static
raw pointer dereference
transmute and unchecked APIs
manual PyCapsule/C ABI/raw Arrow FFI
no_mangle/export_name/link_section and other unsafe attributes
inline/global assembly
```

所有workspace member必须继承统一lint，所有crate root必须保留defense-in-depth `#![forbid(unsafe_code)]`：

```toml
# workspace Cargo.toml
[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"

# every member Cargo.toml
[lints]
workspace = true
```

`forbid`不得由inner `#[allow]`、feature flag、`cfg`或generated wrapper降级。正式CI禁止使用`--cap-lints`压低first-party lint等级，并必须验证编译确实以error阻断unsafe。Architecture test必须发现未继承workspace lints的新member。Stable pinned toolchain是唯一正式toolchain；禁止nightly和`#![feature(...)]`。

## 4. Panic、stub 与错误传播

Rust memory safety不等于业务可靠性。Production path必须把外部输入、schema/version、conversion、resource和可恢复compute failure显式映射到owner-defined `Result`/failure envelope，不得使用panic捷径。

Workspace Clippy baseline：

```toml
[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
```

Test-only `unwrap/expect/panic`例外必须由repository-level Clippy configuration显式限定在test target；不得在production item上使用局部`#[allow]`。

规则：

- Production path禁止`unwrap()`、`expect()`、显式`panic!`、`todo!`和`unimplemented!`。
- Test可以为可读性允许`unwrap/expect`，但不得用它们掩盖被测failure classification；test helper仍不得使用unsafe。
- `assert!/debug_assert!`只表达无法由外部数据触发的内部invariant；public/capability input validation返回typed failure。
- FFI入口不得让panic跨边界传播。意外panic由safe supported boundary捕获并映射stable failure；abort、segfault和allocator termination不能伪装为普通envelope。
- 不启用整个`clippy::restriction` group；只逐项启用本policy列出的稳定lint，避免相互冲突或无替代方案的噪声。

## 5. 数值、索引与内存语义

- Contract value使用`TryFrom`、checked arithmetic和显式range validation；禁止可能静默截断、sign change或precision loss的numeric cast。
- Wrapping、saturating或modular arithmetic只有在owning semantic contract明确要求时合法，且必须由normative vectors覆盖；不能作为overflow临时处理。
- 来自Arrow、fixture、wire或其他外部长度的index/slice必须checked；固定array或循环已证明边界的普通safe indexing不被机械禁止。
- 禁止通过`mem::forget`、intentional leak、unbounded buffer retention或伪造lifetime规避ownership/cleanup。
- Rust core不得拥有filesystem、network、environment、process、ArtifactStore locator或Python object lifecycle；side effect与resource policy留在adapter/control plane。

## 6. FFI 与依赖边界

PyO3/Arrow交互必须使用`pyo3`、`pyo3-arrow`和Arrow crate公开的safe API。First-party adapter不得手写Python C API、Arrow C Data/Stream pointer conversion或custom allocator bridge。

Workspace lint不检查普通third-party dependency内部unsafe。因此新增或升级以下dependency必须单独review并保留evidence：

- Native/FFI、allocator、compression、crypto或Arrow memory dependency。
- Proc macro、build script或会执行外部tool的dependency。
- 引入大量unsafe surface、未维护fork、unlocked git revision或新的system library的dependency。

Review至少记录用途、版本/lock identity、safe API边界、维护状态、已知advisory、license、build/native行为、替代方案和移除/回退路径。Dependency内部unsafe不是自动拒绝理由，但不得借dependency wrapper规避first-party unsafe禁令。

## 7. 性能策略

默认实现采用简单、串行、确定性的Safe Rust。优化顺序固定为：

1. 改善算法复杂度和数据结构。
2. 消除Python row/object materialization与重复serialization。
3. 调整Arrow batch/chunk和allocation reuse，但不自动`combine_chunks()`。
4. 根据accepted measurement减少copy、allocation和peak memory。
5. 证明端到端需求后再引入受控parallelism或safe SIMD/library provider。

下列手段在没有单独Accepted decision前禁止进入正式实现：

```text
hand-written SIMD/intrinsics or target-feature dispatch
custom/global allocator
unchecked indexing or raw-memory traversal
manual prefetch/assembly
unbounded Rayon/thread fan-out
performance-only cache changing correctness authority
custom FFI/network compute service justified only by microbenchmark
```

Phase 1只要求结构性性能证据：粗粒度stream call、零Python row materialization、GIL release、确定性和memory breakdown。Numeric benefit claim遵守Performance Measurement contract；没有业务容量压力时，简单Safe Rust优先于更快但更复杂的实现。

## 8. Future unsafe exception process

Policy v1没有first-party unsafe exception。未来确实无法通过safe API满足已接受业务容量目标时，必须先发布policy breaking version和单独ADR；不得在现有crate内添加局部`allow`。

新的policy/ADR至少证明：

1. Validation-passed accepted baseline显示实际端到端缺口，不是孤立microbenchmark。
2. 算法、batch/materialization、safe library和部署扩容方案均不足或成本更高。
3. Unsafe被隔离在最小private leaf crate，对外只有safe API，不拥有业务或canonical语义。
4. 每个unsafe operation具有可审查safety invariant、`SAFETY` rationale和failure/rollback策略。
5. Exception crate启用`unsafe_op_in_unsafe_fn=forbid`与`undocumented_unsafe_blocks=forbid`，并具有适用的Miri、sanitizer、fuzz/property和platform evidence。
6. Architecture owner、security reviewer和affected capability owner批准，并有删除exception的重新评估条件。

交付期限、临时兼容、第三方示例代码或小幅性能提升不是exception理由。

## 9. CI 与阶段门禁

每个Rust相关PR至少执行：

```text
cargo fmt --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-targets
cargo build --workspace --release
architecture check: every member inherits workspace lints
dependency/native/build-script inventory check
```

Phase 1还必须证明：

- `gateway-compute-core`和PyO3 adapter均由workspace `unsafe_code=forbid`覆盖。
- 正式Arrow C Stream路径完全通过third-party safe wrappers实现。
- Production path不存在panic/stub/error-shortcut；ComputeFailureEnvelope覆盖所有预期失败。
- Source/lint gate没有local waiver，release wheel/image来自同一lock/toolchain identity。

Phase 3新增Rust provider、Phase 6扩大Rust覆盖、Phase 7引入并行/cache/性能优化时，都必须重新满足本policy；阶段编号不会自动授权低层优化。

## 10. Governance 与验收

本policy是Architecture-owned cross-stage engineering gate，不进入业务digest或wire schema。以下变化必须由Architecture owner审批并同步ADR 0001、Implementation Stages和CI：

- 降低lint等级、排除crate/target或允许first-party unsafe。
- 引入nightly、custom native/FFI、allocator、SIMD/intrinsic或新thread runtime。
- 改变panic/overflow/indexing policy。
- 以性能为由扩大Rust进入高变化business/domain/application代码。

验收标准：

- 所有first-party Rust target编译时unsafe为hard error，不能被member降级。
- Production failure通过typed result/envelope传播，不依赖panic或stub。
- 新dependency和性能优化具有required evidence与owner。
- Safe serial/reference与任何优化provider产生相同formal bytes、facts和digest。
- CI和phase gate能自动发现policy violation；code review或source grep只能补充，不能替代compiler/lint gate。

## 11. 关联文档与官方依据

- [ADR 0001: Python/Rust Hybrid Compute Strategy](../adr/0001-python-rust-hybrid-compute-strategy.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Canonical Row Hash Compute Boundary](../contracts/canonical-row-hash-compute-boundary.md)
- [Performance Measurement and Baseline](../contracts/performance-measurement-and-baseline.md)
- [Cargo workspace lints](https://doc.rust-lang.org/cargo/reference/workspaces.html#the-lints-table)
- [Cargo manifest lint scope](https://doc.rust-lang.org/cargo/reference/manifest.html#the-lints-section)
- [Rust lint levels and `forbid`](https://doc.rust-lang.org/stable/rustc/lints/levels.html)
- [Rust `unsafe_code` lint](https://doc.rust-lang.org/stable/rustc/lints/listing/allowed-by-default.html#unsafe-code)
- [Clippy lint policy guidance](https://doc.rust-lang.org/clippy/index.html)
