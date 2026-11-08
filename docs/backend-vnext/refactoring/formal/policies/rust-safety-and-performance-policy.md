# Rust Safety and Performance Policy

状态：正式设计（Accepted Simplified Baseline）

日期：2026-07-31

Policy ID：`gateway-vnext.rust-safety-and-performance-policy`

Owner：Backend vNext Architecture

Policy version：`8`（2026-11-08：Owner 授权补充 §4.1 独立调用边界及按实际消费者落实的要求，不改变 native consumer 允许列表或当前阶段门禁；`7` 按已批准的 Phase 6 S3 设计登记 Comparison records 的精确 native consumer；`6` 由实际 CLI 消费者复用薄 bootstrap 初始化入口，替换 D 的直接初始化 owner；`5` 补 Table Access/parser 与 worker 初始化边，`4` 纳入 S2b B/C consumer，`3` 修订 reference 生命周期；Safe Rust 与失败边界不变）

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

S2b B–E 与 Phase 6 S3 C 已批准的 Python 调用侧由下列精确 capability 模块拥有；backend import guard 应表达这些已确认 consumer，不能将其登记为 layer violation 豁免：

| Python owner（`gateway_backend.capabilities.` 下） | 可直接从 `gateway_compute._native` 导入的粗入口 |
| --- | --- |
| `table_access.native` | `_parse_sql_native` |
| `snapshot_materialization.native` | `_sql_materialize_native`、`_catalog_filter_native` |
| `storage_projection.native` | `_canonical_project_native` |
| `snapshot_materialization.canonical_store` | `_encode_canonical_ipc_native`、`_inspect_canonical_ipc_native` |
| `comparison.native` | `_begin_comparison_operation_native`、`_compare_records_native`、`_summarize_unchanged_ordered_native`、`_facts_core_digest_native`、`_validate_records_batches_native` |

Comparison 的批量数据只以 owned Arrow C Stream 进入或导出；小型 policy/metadata JSON 不承载整表 rows。`comparison.native` 的 operation 入口复用现有进程池与同一 operation M，显式持有输入 backing charge、native portion、取消与截止；table/core JCS 完成后 `seal()` 收缩 native portion，已导出的 Arrow buffer 与其最后 consumer 保留输出和输入 charge。Python `comparison.artifacts` 的 Parquet 读取经该 facade 调用 `_validate_records_batches_native`，只保 raw ref/Parquet I/O 和小 manifest/closure 责任，不直接导入 `_native`。本增补不授予风险、bundle、workflow 或其他模块直接 FFI 边。

这些入口保持各 capability 的现有 DAG、公开 facade、局部预算与 control 边界。规则按 source module、精确 target 和显式导入的 entrypoint 名称匹配，不给全部 capability 开放 `ext:compute`，不允许 wildcard 或任意 native 模块导入绕过该表；其他 capability module/entrypoint 继续拒绝。

E 已确认 `real_dump_journey`/仍有实际消费者的 census CLI 也需要显式初始化进程池，因此由 `gateway_backend.bootstrap.compute_kernel` 单独拥有从 `gateway_compute._native` 导入 `_init_kernel_native` 的精确边，替换 D 的 `bootstrap.operation_worker` 直接导入边。公开薄函数 `initialize_compute_kernel(threads)` 仅集中原 native 初始化和 PyArrow CPU/IO N 设置，worker 与实际 CLI 启动入口复用；不在 import、首次 parse 或每表调用时自动初始化。固定 N、冲突和未初始化拒绝语义保持，不同时放开旧 owner 或工具私有 FFI 导入。M、control 和 operation scope 继续由现调用方显式提供；此 helper 不加载整个 worker settings、不提供 M fallback、不新建通用配置/上下文框架，也不授予 capability 访问 runtime initializer。

Table Access 的 parser bridge 保持原诊断/descriptor 语义并以 Arrow 传递 bulk，不重建整表 Python rows。`artifacts` 仍只拥有 port/value，不直接调用 compute。后续新增实际调用 owner 必须按 owning 设计明确，不由普通 Finding 自动扩展。规则验证包含允许边与其他 owner/entrypoint 的拒绝例；`IMPORT_RULE_BASELINE` 和 cycle baseline 不为本次增加条目。

### 4.1 独立调用边界

解析与比较核心遵守 [架构总纲 §7.4](../architecture/architecture-and-refactoring-plan.md#74-计算能力独立复用)。
Rust core、Python 公共适配与 backend 业务适配分工保持单向：公共适配负责类型转换及计算资源生命周期，
backend 适配负责 SnapshotTable、产物存储与业务流程绑定；core 不反向依赖这些具体对象。

面向独立消费者的入口必须声明版本化的输入/策略、结果与错误语义，以及输入借用、结果关闭、预算、取消和截止行为。
这些是调用契约，不要求把 Arrow buffer 或 native handle 序列化为 JSON。调用方通过公开会话或参数显式建立执行环境；
内部 ContextVar、共享线程池与 owner/charge 实现可以复用，但调用方不得依赖 backend 私有初始化顺序或私有 native 名称。
独立入口同样必须提供有效的资源边界，不能直接暴露宽松的 core 默认预算来绕过生产准入。

Arrow C Stream 和 owner 的进程内借用语义不自动构成跨进程传输契约；独立打包、跨进程执行与并发调度分别按实际需求设计。
固定进程池 N 与 operation M 的职责保持分开，新增调用方不得隐式重设全局池或新增无界 fan-out。

按首个实际消费者完成独立调用验收，范围和唯一测试 owner 依架构总纲 §7.4；当前无需为潜在调用方复制接口或建立新框架。
本补充不改变 §4 的精确 FFI 导入边，也不授权当前 P6 阶段新增 SDK、AI 服务或并发模式。

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
- 改变计算实现或临时参照的定位；DC78 已批准无 Python 回退、Rust 接入验证后删除被替代算法，具体执行按对应阶段 kickoff，不重复请求原则确认。

验收：

- 所有first-party target的unsafe编译失败；
- Production failure通过typed result传播；
- Core与adapter依赖方向保持；
- 实际消费者对保留 golden 产生相同 canonical 结果；替换期差分，替换后删除旧算法、保留独立向量与性质测试，不要求永久双实现；
- Native path使用粗粒度Arrow并在compute期间释放GIL；
- 性能优化有真实业务或measurement依据。

## 9. Related authority

- [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)
