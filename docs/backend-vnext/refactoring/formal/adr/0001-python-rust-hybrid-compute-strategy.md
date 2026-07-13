# ADR 0001: Python/Rust Hybrid Compute Strategy

状态：Accepted

日期：2026-07-13

决策 owner：Backend vNext Architecture

关联阶段：Phase 1、Phase 3、Phase 6

## Context

Backend vNext 同时包含两类变化特征不同的代码：

- Workspace、Submission、Archive、Application Use Case、Operation JobDefinition 和业务 ruleset 变化频繁，主要复杂度来自业务语义和外部协调。
- Snapshot、Projection、Digest、Standard/Ordered Comparison、Records 和 Parquet 等模块处理大量表数据，主要复杂度来自 CPU、内存布局、数据复制和吞吐。

当前 Python 实现虽然使用 Polars，但 Polars 主要覆盖部分 Parquet/cache 路径，仍存在 Python tuple/dict/list materialization、逐 scalar normalization、自定义 diff 和 records 构造。Polars 核心本身已经使用 Rust，因此将既有 Polars expression 从 Python 机械翻译为 Rust 不一定产生显著收益；需要优化的是 Python 行级处理和跨层重复物化。

本次为完整重构，可以从第一版固定 Arrow/Parquet、scalar、ordering 和 digest 边界。如果所有性能模块都先建设完整 Python 生产实现，后续再翻译 Rust，会产生重复投资和双实现分叉；如果所有 capability 都直接使用 Rust，又会降低业务规则迭代效率并放大 FFI、构建和调试风险。

## Decision

采用 Python 控制面、Rust 数据面的混合架构：

```text
Python control plane
  interfaces
  application use cases
  domain models and policies
  Operation Runtime and JobDefinition
  provider/ruleset selection
  frequently changing business rules
          |
          v
stable capability contracts
          |
          v
Rust data plane
  scalar normalization
  digest
  table projection
  standard/ordered comparison
  records
  Arrow/Parquet materialization
```

Arrow/Parquet 是批量数据的主要语言边界；小型 options、facts metadata、errors 和 diagnostics 使用版本化 DTO/schema。

### 1. 首版实现策略

不要求所有性能 capability 先有完整 Python 生产实现。满足进入条件的稳定热点，在 Phase 3 可以直接使用 Rust 作为 production provider，同时提供只面向小数据的 Python reference oracle。

第一批直接 Rust 候选：

```text
scalar normalization and canonical row encoding
row/table/projection digest
table projection
standard hash diff
records construction
Arrow/Parquet materialization around compute results
```

第二批、需要更多语义和 benchmark 依据的候选：

```text
ordered preparation/classification/interval/move
large-scale risk facts extraction
SQL streaming parser
```

### 2. Python Reference 的定位

Python reference implementation 用于：

- 小规模 golden fixtures。
- Property-based/differential tests。
- 边界 case 和语义解释。
- Rust provider 诊断和受控 fallback。

Python reference 不需要满足生产数据规模、吞吐和内存目标，也不与 Rust 长期作为两个同等权威的 production provider 演进。正式语义由 capability contract 和 golden fixtures 拥有，不由任一语言实现拥有。

### 3. 保留 Python 的范围

以下模块第一版保持 Python：

```text
HTTP/API and authentication
application use cases and cross-domain workflows
Workspace/Submission/Archive domain
Operation Runtime and durable job orchestration
Repository Client orchestration
provider and ruleset selection
frequently changing risk/business policies
small metadata/surface/response assembly
```

Risk 拆分为大规模 facts extraction 与业务规则决策：前者在证明为热点后可使用 Rust，后者优先保留 Python。

### 4. 调用和部署边界

第一阶段优先使用 PyO3 + Arrow 的进程内粗粒度调用：

```text
Python capability facade
  -> Arrow RecordBatch/array
  -> one Rust call per table/batch
  -> Arrow/Parquet + compact metadata
```

约束：

- Rust 计算释放 GIL。
- 不逐 row/scalar 跨 FFI 调用。
- 不以百万级 Python dict/dataclass/object graph 作为正式输入。
- Panic、timeout、cancel、out-of-memory 和 native failure 映射为稳定 capability error/diagnostics。
- Operation 只持久化 artifact/checkpoint，不持久化 Rust 内存对象。

大型异步任务后续可以由 `gateway-compute-worker`/CLI 消费 Arrow/Parquet artifact，但不在第一阶段额外引入 Compute 网络微服务。PyO3 和 worker 必须复用同一个 Rust core crate。

建议 Rust workspace：

```text
gateway-compute-core       algorithms and semantic kernels
gateway-compute-python     PyO3/Arrow adapter
gateway-compute-worker     optional artifact-based worker/CLI
```

### 5. Rust Production Provider 进入条件

模块满足以下条件后，才可首版直接使用 Rust：

- Capability contract、排序和 digest 语义已固定。
- 有足够的 golden/property fixtures。
- 输入输出能以 Arrow/Parquet 和小型 metadata 表达。
- 算法相对稳定，不是仍在高频试错的业务规则。
- Profile 或现有实现证据表明它是显著 CPU、内存或数据复制热点。
- CI 能构建和测试目标平台 wheel/image。
- 具有 Python reference、明确失败映射和受控 fallback。

不满足条件时，先用 Python/Polars 验证语义和瓶颈，不为语言统一强行使用 Rust。

### 6. 性能验收

Rust provider 必须同时通过 kernel 和端到端 benchmark。微基准更快不足以成为采用依据。

每个候选在实现前记录：

```text
baseline CPU and wall time
peak memory and materialization count
input scale/distribution
expected kernel gain
expected end-to-end gain
fallback cost
```

具体收益门槛由对应 capability benchmark memo 固定；如果端到端收益不足以覆盖维护、构建和部署成本，保留 Python/Polars provider。

### 7. 并发控制

Operation worker、Python executor、Polars/Rayon 和 Repository worker 共享明确的资源预算。Rust provider 不按 CPU 数无条件开满线程；并发度通过 execution policy 或进程配置受控，串行与并行模式必须产生相同正式结果和 digest。

## Alternatives Considered

### A. 所有模块先实现完整 Python 生产版

拒绝作为统一策略。优点是早期调试简单，但对已经明确的数据热点造成重复实现成本，且容易长期保留两套 production 算法。

### B. 所有 Capability 首版直接使用 Rust

拒绝。业务 ruleset、application orchestration 和小型 metadata 逻辑变化频繁，Rust 不提供足以抵消迭代、FFI 和部署成本的普遍收益。

### C. 将 Python 目录、class 和 dataclass 一一翻译为 Rust

拒绝。语言实现应共享 contract，而不是共享对象图和文件结构。一一映射会保留 Python 对象粒度，同时引入 Rust ownership、FFI 和双版本维护成本。

### D. 首版建立独立 Rust Compute Service

暂不采用。网络服务会提前引入序列化、部署、认证、调度和故障恢复边界。第一阶段使用 PyO3；只有独立扩缩容、故障隔离或超大异步任务证明需要时，再评估 worker/service。

## Consequences

正面影响：

- 已知稳定热点不需要经历完整 Python 生产版再重写。
- Python 继续承载高变化业务代码。
- Capability contract 对语言实现保持中立。
- Arrow/Parquet 降低逐对象 FFI 和重复 materialization。
- Python reference 为跨语言正确性提供可解释 oracle。

成本和风险：

- 需要维护 Rust toolchain、PyO3 wheel、目标平台构建和 native profiling。
- Native crash 可能终止 Python worker，需要 Operation Runtime 接管和重试。
- Scalar、NULL、Decimal、datetime、ordering 和 digest 语义必须跨语言逐字节一致。
- Polars、Rayon、Python executor 和 Operation worker 可能造成线程超卖。
- Fallback 和滚动升级期间需要管理 provider/schema 兼容。

## Required Verification

- Python/Rust shared scalar and digest golden tests。
- Arrow schema/FFI round-trip tests。
- Rust/Python differential and property-based tests。
- Serial/parallel determinism tests。
- Panic、timeout、cancel、native crash 和 worker takeover tests。
- Wheel/image platform matrix tests。
- Capability-level 与 end-to-end benchmark。

## Related Documents

- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)
