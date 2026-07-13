# Backend vNext Architecture and Refactoring Plan

状态：正式设计基线（Accepted Baseline）

本文定义 backend vNext 整体重构的目标架构、模块边界和依赖规则。本文是重构总纲；详细实施阶段见 [Implementation Stages](../plans/implementation-stages.md)。本文不替代旧架构区的 `flows.md`、`operations.md`、`contracts/`、`capabilities/` 和 ADR 中的业务语义资料；正式重构实现以本目录正式文档为准。

## 1. 目标与范围

本轮整体重构解决以下问题：

- 以 Workspace、Submission、Archive 等领域边界组织业务代码，避免 API、Flow 或统一 StateStore 成为事实上的业务中心。
- 保留 Snapshot、Comparison、Risk、Surface、Bundle 等可复用 capability，同时建立稳定公共契约，控制 capability 之间的依赖方向。
- 将 Flow 收敛为 application use case，将 Operation 收敛为可持久化、可重试、可接管的通用执行机制。
- 将基于 Dolt 的 repository 能力拆成独立、通用、容器化的 Repository Service，与当前项目业务彻底解耦。
- 消除跨进程不可用的本地路径、Python 闭包状态和具体 Dolt CLI 对业务层的泄漏。
- 通过契约测试、架构测试和分阶段替换完成迁移，不做一次性目录搬迁式重写。

本文暂不决定：

- Repository Service 最终使用 REST、gRPC 还是组合协议。
- 生产环境最终使用何种数据库、对象存储和部署编排平台。
- 是否将所有 backend vNext 模块拆成独立进程。除 Repository Service 外，第一阶段仍以模块化单体为默认部署形态。

## 2. 总体结论

`core / capabilities / operations / flows` 是四类有价值的架构概念，但它们不是完整且互斥的四层：

| 概念 | 定位 |
| --- | --- |
| `core` / `shared_kernel` | 无业务归属的稳定基础原语。 |
| `capabilities` | Flow-neutral、可复用的计算或数据处理能力。 |
| `operations` | 执行状态、step、lease、retry、cancel、checkpoint 和 diagnostics。 |
| `flows` / `application` | 面向具体业务用例的编排入口。 |

目标架构采用：

```text
模块化单体
  + 领域纵向拆分
  + 六边形依赖方向
  + 通用 Operation Runtime
  + 独立 Repository Service
```

业务系统内部以领域模块为骨架，capability 是可复用计算，application use case 是编排入口，operation 是执行引擎，infrastructure 是适配器。Repository Service 是明确的进程和数据所有权边界。

### 2.1 Python/Rust 语言职责

Backend vNext 从第一版采用 Python/Rust 混合架构，不要求所有性能 capability 先实现完整 Python 生产版本：

```text
Python control plane
  interfaces / application / domain
  Operation Runtime / JobDefinition
  provider and ruleset selection
  frequently changing business policy
          |
          v
stable capability contracts
          |
          v
Rust data plane
  scalar / digest / projection
  standard and ordered comparison
  records / Arrow / Parquet kernels
```

原则：

- 满足稳定 contract、golden oracle、Arrow/Parquet 边界和性能证据的热点，可以在 Phase 3 直接使用 Rust production provider。
- Python 为 Rust 内核保留小规模 reference oracle，不必建设同等规模的 Python production implementation。
- 已经完整落在 Polars native expression 的逻辑不因语言统一机械翻译 Rust；优先消除 Python 行级循环和对象 materialization。
- 频繁变化的 domain/application/ruleset 保持 Python；大规模 facts extraction 与业务规则决策分离。
- 第一阶段使用 PyO3 + Arrow 粗粒度调用；独立 Rust worker/service 必须由异步规模、隔离或扩缩容需求证明。
- Operation Runtime 保持 Python 并统一管理持久 step、retry 和接管；Rust 只执行 capability 计算，不直接修改业务状态和 operation store。

详细决策、进入条件和替代方案见 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)。

## 3. 当前实现评估

### 3.1 已有良好基础

- `core` 已包含 digest、identifier、scalar encoding、row digest 和 diagnostics 等基础原语。
- Snapshot、Comparison、Risk、Surface、Bundle 已形成相对清晰的 capability 轮廓。
- `operations` 已有 operation/step 状态、lease、retry 和 SQLite store 的基础实现。
- `workspaces`、`submissions`、`archive` 已开始承载真实业务状态和状态转换。
- `repository_server` 已形成 repository ref、resolved commit、catalog、table reader/export、native diff、cache 和 registry 等读侧抽象。
- 文档已明确 RepositoryServer 不应产出 Snapshot、Comparison 或业务状态。

### 3.2 主要结构性缺口

- `flows` 与 Workspace/Submission application service 职责重叠，并存在领域模块反向调用 flow 的情况。
- 部分 operation step 使用进程内闭包传递 Comparison/Risk/Surface 结果，worker 重启或跨进程接管后无法恢复。
- 正式 API 仍以进程内 operation store 和大型统一 state store 为主，持久化边界尚未按领域拆分。
- `api/formal_state_store.py` 同时包含多个领域的数据结构、业务查询、状态变化和文件持久化。
- capability 消费方经常直接 import 其他 capability 的内部 `models.py` 或实现模块，公共契约面不足。
- `snapshot_materialization` 反向依赖 `comparison.digest`，与 comparison 对 snapshot 的正向依赖形成潜在环。
- Repository 读侧已有抽象，但正式 Dolt backend、import、readback 和 server lifecycle 仍位于 `capabilities.repository_import`。
- Repository contract 中混入 Workspace、Submission、Archive、History 等业务枚举和命令。
- `repository_path`、`run_dir`、export `Path` 和 `DoltCli` 仍被业务代码、flow 或 benchmark 直接感知。

## 4. 目标逻辑架构

```text
interfaces
  HTTP routers / request-response DTO / worker entrypoints
        |
        v
application
  use cases / commands / queries / transaction boundaries / job definitions
        |                    |                         |
        v                    v                         v
domain modules          capabilities             operation port
  workspace               table rules                 |
  submission              table projection            v
  archive                 snapshot              Operation Runtime
  baseline                comparison             store / lease / retry
                          risk
                          surface
                          bundle
        |                    |
        +--------- ports ----+
                    |
                    v
infrastructure adapters
  domain persistence / artifact store / cache / Repository Client
                                                    |
                                                    v
                                     independent Repository Service
                                     Dolt / registry / repository volume
```

### 4.1 依赖总规则

- `interfaces -> application`。
- `application -> domain + capability public contracts + ports`。
- `domain -> shared_kernel`，不得依赖 API、operation runtime、Dolt 或具体持久化。
- capability 可以依赖上游 capability 的公开 contract，不得依赖其内部实现。
- `operations` 不依赖 Workspace、Submission、Archive、Snapshot、Comparison 等业务模型。
- infrastructure 实现 application/domain 定义的 port，业务内核不反向依赖 infrastructure。
- Repository Client 只暴露网络可表达的 repository contract，不暴露 Dolt CLI、服务端路径或进程对象。
- 禁止循环依赖；允许的流水线依赖必须形成有向无环图。

## 5. 业务领域模块

第一阶段至少识别以下业务边界：

| 模块 | 主要职责 |
| --- | --- |
| `workspace` | Workspace 生命周期、upload generation、preview binding、submit gate、重新开放。 |
| `submission` | Submission 身份、finalization 结果、review/approve/reject/withdraw 状态机。 |
| `archive` | Archive batch、candidate、confirmation、anomaly resolution、selection 和 execute gate。 |
| `baseline` | 当前 mainline、历史节点、batch 与 archive 结果的业务映射。 |
| `history` | 历史比较请求和结果身份；不拥有通用 comparison 算法。 |

每个领域模块内部建议采用最小六边形结构：

```text
modules/<module>/
  domain/
    models.py
    policies.py
  application/
    commands.py
    queries.py
    services.py
  ports.py
  adapters/
```

规则：

- Domain model 表达状态和不变量，不直接修改其他模块的存储。
- 跨聚合协调位于 application use case，不塞入 entity，也不放入 HTTP handler。
- 跨模块写入需要显式事务、outbox 或补偿策略，不通过捕获通用异常后静默回滚外部副作用。
- API DTO、持久化 record 和 domain model 可以不同，不以一个 dataclass 同时承担全部职责。

## 6. Application、Flow 与 Operation

### 6.1 Flow 的目标定位

现有 `flows` 逐步收敛为 `application/use_cases`。一个入口代表一个业务用例，例如：

```text
BuildUploadPreview
AcceptSubmission
FinalizeSubmission
ReviewSubmission
ExecuteArchive
CompareHistory
```

Use case 负责：

- 权限与 generation gate。
- 加载和保存领域对象。
- 选择 capability、ruleset 和业务 policy。
- 创建 operation 或提交异步 job。
- 定义事务边界、幂等键和业务结果。

Use case 不负责：

- SQL parse、diff、risk 或 bundle 算法。
- Dolt CLI 和 repository 本地目录。
- 通用 lease、step claim 和 retry 状态机。

### 6.2 Operation 的目标定位

Operation Runtime 只负责执行机制：

```text
operation/step persistence
atomic claim
lease and takeover
retry/cancel/supersede
checkpoint and diagnostics
READY artifact closure
```

JobDefinition 由 application 层注册，runtime 通过稳定的 `operation_kind + step_name` 找到 handler。不得依赖请求进程中动态创建的闭包才能继续执行。

Step 间只传递可持久化数据：

- 稳定 DTO。
- business ID、repository ID/ref/commit。
- artifact ref、digest 和 closure ref。
- 可验证 checkpoint。

大型中间结果写入 artifact store，step output 只保存引用。任意 worker 应能仅凭 operation record、prior outputs 和外部持久化结果继续执行。

### 6.3 目标异步调用链

```text
API request
  -> application use case
  -> validate domain state
  -> persist business change + operation/outbox
  -> return operation_id

worker
  -> claim operation
  -> load JobDefinition
  -> execute next step through capabilities/ports
  -> persist checkpoint/artifact refs
  -> publish READY or final failure
```

## 7. Capability 架构

### 7.1 允许的主依赖链

```text
table_rules
    |
table_projection
    |
snapshot_materialization ------> repository import client/use case
    |
comparison
    |
risk_evaluation
    |
surface_assembly
    |
bundle_assembly
    |
upload_preview_bundle
```

该流水线中的正向依赖属于业务数据流，不要求所有 capability 相互零依赖。要求的是只依赖公开 contract、禁止反向依赖和禁止环。

### 7.2 第一轮公共能力调整

新增或明确以下边界：

1. `table_projection`
   - ProjectionSchema。
   - selected/ignored columns。
   - effective compare key。
   - projection schema/logical/row identity digest。
   - snapshot 与 comparison 共同使用的 projector。
2. `contracts.table_access`
   - column/descriptor 的最小稳定结构。
   - TableReader、TableSet、row stream protocol。
   - 不把完整 Snapshot 业务语义泛化成通用 table model。
3. `artifacts`
   - logical ref、closure、records、ref rewrite 和 artifact relocation。
   - 不包含 ComparisonSurface/RiskReport 到具体 bundle payload 的业务映射。

不创建 `capabilities/common` 或 `capabilities/utils`。一个概念只有满足以下条件时才独立：

- 至少存在两个独立消费者。
- Flow-neutral，且具有稳定名称和语义。
- 可以独立版本化、测试和诊断。
- 提取后消除反向依赖、循环依赖或实质重复。

### 7.3 Capability 公共契约

每个 capability 必须有明确公共面，例如：

```text
capabilities/comparison/
  contracts.py
  service.py
  _internal/
    planner.py
    providers.py
    records_builder.py
```

公共面只暴露：

- Input/Result/Facts。
- Port/Protocol。
- 稳定枚举和 contract version。
- 明确声明的 entrypoint。

调用方不得 import `_internal`，也不应直接依赖 provider selection、cache layout、builder 或算法中间状态。

## 8. Shared Kernel、Contracts 与 Infrastructure

### 8.1 Shared Kernel

只保留：

- digest/canonical serialization。
- identifier/scalar encoding/row digest。
- diagnostics 和最小 result/error primitive。
- 与业务无关的 validation primitive。

Benchmark result、Workspace status、Repository operation purpose 等有明确归属的模型不得放入 shared kernel。

### 8.2 Contract 分类

不再把所有 DTO、port 和 wire schema 堆入统一 `contracts` 包。至少区分：

```text
interface contracts
  HTTP request/response schema

application contracts
  command/query/result

capability contracts
  flow-neutral input/facts/result/port

repository wire contracts
  repository service API and client SDK
```

`ArtifactRef` 如果作为跨进程引用，必须具有稳定 wire schema；LocalArtifactStore、文件布局和本地 `Path` 仍属于 infrastructure。

### 8.3 Persistence

- 按领域拆分 repository interface 和持久化实现。
- 第一阶段可以共用同一个数据库实例，但不共用一个无边界 StateStore 类。
- 领域 repository 保存领域 record；operation store 保存执行状态；artifact/cache registry 保存技术状态。
- 跨领域一致性优先通过同库事务；跨 Repository Service 的一致性通过幂等、CAS、outbox 和显式补偿实现。

## 9. Independent Repository Service

### 9.1 服务定位

Repository Service 是通用表数据版本库，不理解本项目的 Workspace、Submission、Preview、Archive、Baseline、History、Snapshot、Risk 或 Bundle。

服务拥有：

- Repository 生命周期和持久化目录。
- commit、branch、tag、ref resolve 和原子 CAS 更新。
- import、catalog、row stream、table export 和通用 native diff。
- 单 repository writer lease 和并发控制。
- repository operation、幂等、审计、cache 和 GC。
- Dolt CLI/sql-server 生命周期、版本升级和存储恢复。

业务系统拥有：

- 哪个 Workspace/Submission 可以写入。
- 哪个 Archive candidate 可以晋升主线。
- ruleset、projection、SnapshotSummary、Comparison 和 Risk 语义。
- 业务 retention、审批、权限和状态机。

“Promote mainline”在业务侧完成候选校验，Repository Service 只执行通用原子操作：

```text
CompareAndSetRef(
  repository_id,
  ref="main",
  expected_commit,
  target_commit,
  idempotency_key
)
```

### 9.2 最小通用 API

控制面：

```text
CreateRepository
GetRepository
SubmitImport
GetOperation
ResolveRef
CreateRef
CreateImmutableRef
CompareAndSetRef
DeleteRef
GetCommit
PlanGarbageCollection
ExecuteGarbageCollection
```

数据面：

```text
GetCatalog(repository_id, commit_hash)
StreamTableRows(repository_id, commit_hash, table, projection, cursor)
ExportTable(repository_id, commit_hash, table, format)
DiffRefs(repository_id, before_commit, current_commit, options)
```

外部 API 优先使用 immutable commit。客户端 `open_ref()` 可以保留为便利 API，但其语义是先 resolve，再让后续请求显式绑定 resolved commit；不依赖服务端进程内 Python session。

### 9.3 Import 与 artifact

Repository import 采用异步 operation：

```text
SubmitImport(
  repository_id,
  base_commit,
  target_ref,
  expected_target_commit,
  source_artifact,
  source_digest,
  import_format,
  idempotency_key
) -> repository_operation_id
```

成功结果返回 commit、ref 和 digest，不返回服务端 `repository_path` 或 `run_dir`。

大型 SQL、Parquet 和 export 不进入普通 JSON payload：

- 控制请求使用 HTTP/gRPC。
- 大文件使用对象存储 URI、预签名 URL 或流式上传。
- 大规模 row read 使用流式协议或 Parquet artifact。
- Artifact handle 至少包含 artifact ID、digest、size、media type 和可控生命周期。

### 9.4 容器与运行约束

- 一个 repository 同时只有一个 writer owner。
- 多实例不得无协调共享可写 `.dolt` 目录。
- ref 更新使用 expected commit/CAS，不能依赖客户端“先读后写”。
- 单节点可使用 persistent volume 和 repository-local SQLite registry。
- 多副本需要 repository ownership/sharding 和共享控制面 registry。
- 固定 Dolt 版本；升级必须有兼容性检查、备份、迁移和回滚方案。
- backup 覆盖 Dolt 数据、registry 和 operation journal，并定期执行恢复演练。
- 必须提供 readiness/liveness、磁盘水位、operation、writer lease、GC、延迟和失败率指标。

### 9.5 安全边界

- 服务间认证和 repository/tenant 级授权。
- 禁止客户端提交任意宿主机路径。
- 校验 repository/ref/table 名称，隔离命令和 SQL 注入风险。
- import 受 timeout、CPU、内存、磁盘、文件大小和解压配额控制。
- 审计记录 caller、idempotency key、request/input digest、before/after commit。
- 诊断不得泄漏服务端路径、命令参数中的凭据或原始敏感数据。

## 10. 建议目标目录

业务系统：

```text
backend_vnext/
  shared_kernel/
  modules/
    workspace/
    submission/
    archive/
    baseline/
    history/
  application/
    use_cases/
    jobs/
  capabilities/
    table_rules/
    table_projection/
    snapshot_materialization/
    comparison/
    risk_evaluation/
    business_projection/
    surface_assembly/
    bundle_assembly/
  operations/
  artifacts/
  cache/
  ports/
    repository.py
  infrastructure/
    persistence/
    repository_client/
    artifact_store/
  interfaces/
    http/
    workers/
  bootstrap/
```

Rust compute workspace：

```text
rust/
  gateway-compute-core/
  gateway-compute-python/
  gateway-compute-worker/ optional
```

`gateway-compute-core` 实现语言中立的计算内核，`gateway-compute-python` 只负责 PyO3/Arrow 适配；可选 worker 只负责 artifact-based 执行，不复制 core 算法。Rust crate 结构不按 Python 文件和 class 一一映射。

独立 Repository Service：

```text
repository_service/
  contracts/
  application/
  domain/
  dolt/
  registry/
  operations/
  transport/
  storage/
  observability/
  tests/
```

Repository wire contract 可以生成轻量 client SDK，但不得通过共享业务源码包重新耦合两个系统。

## 11. 分阶段重构计划

详细阶段、交付物、依赖关系和验收门禁见 [Implementation Stages](../plans/implementation-stages.md)。总体顺序为：

```text
Phase 0  baseline and oracle
  -> Phase 1  contracts and architecture skeleton
  -> Phase 2  Repository Service foundation
  -> Phase 3  capability foundation
  -> Phase 4  durable Operation Runtime
  -> Phase 5  business vertical slices
  -> Phase 6  Rust coverage expansion and compute optimization
  -> Phase 7  concurrency/cache/performance
  -> Phase 8  shadow traffic and cutover
  -> Phase 9  cleanup and production hardening
```

阶段不是纯水平层交付。Phase 1 至 Phase 4 只建设支撑首个纵切所需的最小基础；进入 Phase 5 后按 upload preview、submit、review、archive、history compare 的顺序形成可运行闭环。Phase 1 建立 Rust/Arrow 工程和语义基线，Phase 3 允许符合门禁的热点直接交付 Rust production provider；Phase 6 负责扩大覆盖和深度优化，而不是首次引入 Rust。所有 Rust 实现仍以稳定 contract、Python reference oracle 和 benchmark 为前置条件。

## 12. 验证策略

每个 phase 至少覆盖：

- Domain unit tests：状态机、不变量、policy。
- Capability contract tests：输入、输出、digest、diagnostics 和版本。
- Architecture tests：禁止反向依赖、内部模块越界和旧模块 import。
- Operation recovery tests：claim、lease、retry、cancel、crash takeover。
- Repository client/server contract tests：local adapter 与 remote adapter 等价。
- Failure injection：网络中断、超时、重复请求、worker crash、Dolt process crash、磁盘不足。
- End-to-end journey：upload -> preview -> submit -> review -> archive -> history compare。
- Benchmark：correctness 优先于 performance，性能结果只统计 validation passed 的运行。

## 13. 架构完成标准

整体重构完成至少满足：

- Domain 不依赖 API、operation runtime、Dolt 或具体 persistence。
- API 不拥有业务状态机和跨领域统一 StateStore。
- Capability 依赖图无环，调用方只使用稳定公共契约。
- Operation 不依赖进程内闭包，支持持久化接管。
- 业务容器没有 Dolt 二进制，不挂载 repository volume。
- 业务 contract 不出现 `repository_path`、`run_dir` 或服务端本地 artifact path。
- Repository Service contract 不出现 Workspace、Submission、Archive、Baseline、History 等业务语义。
- Repository 写操作具备幂等、CAS、审计、资源限制、备份和恢复能力。
- 正式业务旅程、artifact closure、digest 和前端 contract 通过验收。

## 14. 待补 ADR

以下决策在进入对应 phase 前必须单独收口：

1. Repository Service transport：REST、gRPC、Arrow Flight 或组合方案。
2. 大型 import/export artifact 的存储、上传和授权方式。
3. Repository ownership/sharding 与多副本 writer 模型。
4. Repository operation/idempotency journal 的持久化方案。
5. Domain persistence 的数据库和事务/outbox 策略。
6. Repository wire scalar/type/null/order contract。
7. Dolt 版本升级、repository format migration 和 rollback 策略。
8. `SnapshotSummary` hidden table 的写入与解释边界：作为业务生成的普通版本化数据，Repository Service 不解释其业务内容。

## 15. 与现有文档的关系

- `modules.md` 和 `implementation-boundary.md`：当前模块边界与第一阶段实现约束；后续按本文目标逐步更新。
- `flows.md`：业务旅程和状态转换来源；后续映射到 domain/application。
- `operations.md`：Operation Runtime 的专项设计来源。
- `contracts/`：现有数据契约来源；后续按 interface/application/capability/repository wire 分类。
- `capabilities/`：各 capability 的算法、输入输出和验收细节来源。
- `capabilities/repository-import.md`、`capabilities/repository-ref-materialization.md`：Repository Service 拆分前的行为和性能依据。
- ADR：关键不可逆决策的最终权威记录。

本文先固定总体方向；目录迁移、服务拆分和 contract 删除均应按 phase 小步实施，并在每阶段保留可运行、可验证的正式主路径。
