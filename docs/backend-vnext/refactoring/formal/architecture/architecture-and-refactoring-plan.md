# Backend vNext Architecture and Refactoring Plan

状态：正式设计基线（Accepted Baseline）

本文定义 backend vNext 整体重构的目标架构、模块边界和依赖规则。本文是重构总纲；详细实施阶段见 [Implementation Stages](../plans/implementation-stages.md)，精确语义由本目录的 owner-oriented contracts 和 ADR 规定。旧架构区的 `flows.md`、`operations.md`、`contracts/`、`capabilities/` 与 ADR 仅作为 legacy 证据；发生冲突时以本目录正式文档为准。

2026-08-01过渡说明：WP1-R1旧设计checkpoint已经完成。安全、恢复、
Repository Service范围和交付控制遵循
[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)。
旧Phase 2完整双存储、全量evidence和exact-commit设计只解释历史checkpoint；
不得据此启动旧计划WP1-R2+。D01 Phase 0–1简化设计已由
[ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)闭合；DX cross-phase
interface reconciliation也已由
[DX plan](../plans/dx-cross-phase-interface-reconciliation.md)闭合，S02联合代码清理已
完成。P2-R1 v8 formal 已通过，默认 provider 为
Candidate A offline CLI，Candidate B保留但默认禁用。
2026-08-22：P2-R6-S11 `phase_2_complete: yes`；P3 design 已完成，P3-R4 module gate
`p3_r4_exit: pass`，P3-R5 module gate `p3_r5_exit: pass`、`p3_r6_ready: yes`；P3-R6
comparison risk/surface/bundle design、detail plan 和 S0 freeze 已完成，但实现仍须由
R6-specific scoped authorization 明确授权；全局 `p3_implementation_authorized` 保持 `no`。
当前下一入口为 P3-R6-S1 risk contracts；设计
基线和执行计划见
[P3 Active Context Index](../plans/p3-active-context-index.md) 与
[P3-R5 Comparison Design Baseline](../plans/p3-r5-comparison-design.md)，以及
[P3-R5 Comparison Execution Plan](../plans/p3-r5-comparison-execution-plan.md)、
[P3-R5-S0 Entry and Budget Freeze](../plans/p3-r5-s0-entry-and-budget-freeze.md)、
[P3-R6 Risk, Surface and Bundle Design Baseline](../plans/p3-r6-risk-surface-bundle-design.md)、
[P3-R6 Risk, Surface and Bundle Execution Plan](../plans/p3-r6-risk-surface-bundle-execution-plan.md)、
[P3-R6-S0 Entry and Budget Freeze](../plans/p3-r6-s0-entry-and-budget-freeze.md)，以及
[P3-R4 Storage Projection and Canonicalization Handoff](../plans/p3-r4-storage-projection-handoff.md)。
不得把文档 HEAD 当作 `CANDIDATE_SHA`。

## 1. 目标与范围

本轮整体重构解决以下问题：

- 以 Workspace、Submission、Archive 等领域边界组织业务代码，避免 API、Flow 或统一 StateStore 成为事实上的业务中心。
- 保留 Snapshot、Comparison、Risk、Surface、Bundle 等可复用 capability，同时建立稳定公共契约，控制 capability 之间的依赖方向。
- 将 Flow 收敛为 application use case，将 Operation 收敛为可持久化、可重试、可接管的通用执行机制。
- 将基于 Dolt 的 repository 能力拆成独立、通用、容器化的 Repository Service，与当前项目业务彻底解耦。
- 以最小持久业务事实和 derived projection 取代重复状态，以 immutable artifact、
  数据库事务、幂等键和必要operation marker支持可重试主路径。
- 让 SourcePackageArtifact 保存原始上传权威，Dolt 只保存 versioned storage projection 形成的 canonical business state。
- 消除跨进程不可用的本地路径、Python 闭包状态和具体 Dolt CLI 对业务层的泄漏。
- 通过契约测试、架构测试和分阶段替换完成迁移，不做一次性目录搬迁式重写。

本文暂不决定：

- 除已固定使用HTTP/OpenAPI的Repository Service外，其他内部服务最终使用REST、
  gRPC还是组合协议。
- 生产环境最终使用何种数据库、对象存储和部署编排平台。
- 是否将所有 backend vNext 模块拆成独立进程。除 Repository Service 外，第一阶段仍以模块化单体为默认部署形态。
- Legacy Dolt repository 的迁移或兼容策略；它是独立 cutover gate。

### 1.1 适度保障原则

- 安全、恢复、一致性和交付控制必须对应明确威胁、业务损失、已确认consumer或
  可复现故障；没有依据时不预建通用框架。
- 本项目默认是少量协作者、单一信任域和可信内网系统。业务正确性优先于形式化
  evidence closure，允许罕见矛盾状态进入明确的人工修复。
- 业务digest只表达owner定义的内容相等性；没有独立key/trust contract时，不得称为
  签名、来源认证或防篡改证明。
- 优先使用HTTP、OpenAPI、Arrow、数据库事务、容器和普通CI等标准能力；输入大小、
  服务端路径、非root、`shell=False`和secret脱敏等低成本保护继续保留。
- 新机制必须说明owner、当前consumer、失败成本、最小验收和重新进入条件。仅为
  未来可能需要的CurrentTableStore、ACL、恢复或治理能力不得进入当前主路径。

上述原则在Phase 0–9的设计、实现和评审规则由
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)
统一执行。每个纵切必须区分权威/不可逆事实、可恢复durable状态、derived/temporary状态与
外部信任边界；不得为C/D类对象静默引入新的安全主体、IPC、持久evidence状态机或证明墙。

精确Repository信任边界、最小contract、恢复策略、Current扩展方式和过渡顺序由
[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
规定。

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

持久化遵循“事实最小、projection 可派生”：Workspace/SubmitAttempt/Submission/BaselineNode/Head/ArchiveExecution/Result 各由单一 domain/application owner 管理；执行进度、Candidate、readiness、dry-run plan 和当前/历史标签不复制为业务状态。精确生命周期见 [Business Lifecycle and State Contract](../contracts/business-lifecycle-and-state.md)。

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

- 满足稳定contract、必要golden与Arrow/Parquet边界的热点，可以在Phase 3直接使用
  Rust production provider。
- Python 为 Rust 内核保留小规模 reference oracle，不必建设同等规模的 Python production implementation。
- production不自动fallback到Python，也不维持两套同等地位的production provider。
- 已经完整落在 Polars native expression 的逻辑不因语言统一机械翻译 Rust；优先消除 Python 行级循环和对象 materialization。
- 频繁变化的 domain/application/ruleset 保持 Python；大规模 facts extraction 与业务规则决策分离。
- 第一阶段使用 PyO3 + Arrow 粗粒度调用；独立 Rust worker/service 必须由异步规模、隔离或扩缩容需求证明。
- Operation Runtime 保持 Python 并统一管理持久 step、retry 和接管；Rust 只执行 capability 计算，不直接修改业务状态和 operation store。
- 首条正确production path可以包含初始Rust provider；后续优化只要求先通过正确性，
  记录dataset/version、环境说明和raw results，且不与legacy建立性能门禁。

详细决策、进入条件和替代方案见 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)。

### 2.2 Formal contract authority

精确业务状态、外部 effect、bytes、fixture、storage 与 measurement 分别由以下唯一 owner contract 规定：

- [Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)
- [External Effect and Recovery](../contracts/external-effect-and-recovery.md)
- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)
- [Correctness Golden and Fixture](../contracts/fixture-oracle-and-conformance.md)
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
- [Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)

本总纲只描述这些 contract 的组合和依赖关系，不重新定义其字段或状态表。

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
| `workspace` | Workspace OPEN/CLOSED 生命周期、UploadRevision、immutable PreviewResult、当前引用与占用。 |
| `submission` | SubmitAttempt、business-owned acceptance facts后的Submission、PENDING/APPROVED/REJECTED/RETURNED/WITHDRAWN review projection。 |
| `archive` | Confirmation/AnomalyResolution、derived CandidateProjection、pure PreviewArchivePlan、frozen ArchivePlan、Execution/Result。 |
| `baseline` | Immutable BaselineNode 与当前 BaselineHead pointer；不拥有 batch。 |
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
UploadWorkspaceSource
BuildUploadPreview
AcceptSubmit
FinalizeSubmit
Approve/Reject/Withdraw/ReturnSubmission
PreviewArchivePlan
StartArchive/FinalizeArchive
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

跨Repository Service写effect必须采用T1业务验收、T2 durable external effect、T3核对
matching SUCCEEDED result与requested/completed verification后业务finalize。Worker接管
`RUNNING` step时先以既有operation identity查询Repository；请求可能已接受后不得
blind replay。业务状态、Operation/outbox、effect result的权威边界见
[External Effect and Recovery Contract](../contracts/external-effect-and-recovery.md)。

## 7. Capability 架构

### 7.1 允许的主依赖链

```text
table_access + parser
    -> snapshot_materialization -> SnapshotTableArtifact
                                      |
table_rules --------------------------+-> storage_projection
                                      |      -> RepositoryImportArtifact
                                      |      -> Repository Client
                                      |
                                      +-> comparison_projection
                                             -> comparison
                                             -> risk_evaluation
                                             -> surface_assembly
                                             -> bundle_assembly
                                             -> upload_preview_bundle
```

该流水线中的正向依赖属于业务数据流，不要求所有 capability 相互零依赖。要求的是只依赖公开 contract、禁止反向依赖和禁止环。

### 7.2 第一轮公共能力调整

新增或明确以下边界：

1. `storage_projection`
   - Dolt canonical column policy、physical key、ordered identity。
   - CanonicalizationManifest 与 RepositoryImportArtifact content schema。
   - 保证 retained rows 完整，失败时 fail closed。
2. `comparison_projection`
   - 跨版本 schema alignment、selected value columns、effective compare key。
   - comparison projection schema/logical/row identity digest。
   - 与 storage projection 复用 table-rules 语义源，但不共享未区分职责的 DTO/cache。
3. `contracts.table_access`
   - column/descriptor 的最小稳定结构。
   - TableReader、TableSet、row stream protocol。
   - 不把完整 Snapshot 业务语义泛化成通用 table model。
4. `artifacts`
   - Backend store-owned opaque ID、raw integrity、put/read和独立retention policy。
   - 不拥有capability semantic metadata，不建设generic closure/ref rewrite或把
     ComparisonSurface/RiskReport映射到具体bundle payload。

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

- [canonical encoding](../contracts/shared-canonical-encoding.md)、identifier、digest 和 row/collection framing。
- 与业务无关的 validation primitive。

Use-case error code/message/details、Workspace status、Repository operation purpose等
有明确归属的模型不得放入shared kernel。

### 8.2 Contract 分类

不再把所有 DTO、port 和 wire schema 堆入统一 `contracts` 包。至少区分：

```text
interface contracts
  HTTP request/response schema

application contracts
  command/query/result

capability contracts
  flow-neutral input/facts/result/port

artifact content contracts
  source/snapshot/canonical import/comparison records

correctness and measurement contracts
  direct golden / benchmark record

repository wire contracts
  repository service API and client SDK
```

BackendArtifactRef与RepositoryArtifactRef分别只包含各自scope的opaque artifact
id、`media_type`、`size_bytes`和`raw_sha256`；二者不共享nominal type，upload时
Repository分配新ID。内容语义属于capability result或business manifest；
retention/access属于store或业务policy。LocalArtifactStore、文件布局和本地`Path`
仍属于infrastructure。精确映射见
[DX Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)。

### 8.3 Persistence

- 按领域拆分 repository interface 和持久化实现。
- 第一阶段可以共用同一个数据库实例，但不共用一个无边界 StateStore 类。
- 领域 repository 保存领域 record；operation store 保存执行状态；artifact/cache registry 保存技术状态。
- 跨领域一致性优先通过同库事务；跨 Repository Service 的一致性通过幂等、CAS、outbox 和显式补偿实现。
- SourcePackageArtifact 长期保存原始 bytes；SnapshotTableArtifact 只在 current Preview/active SubmitAttempt 期间 pin，终态后释放为可重算材料。首版不再额外长期保存一份重复 full-row archive。

## 9. Independent Repository Service

### 9.1 服务定位

Repository Service是独立内网Versioned table repository，不理解本项目的
Workspace、Submission、Preview、Archive、Baseline、History、Snapshot、Risk或
Bundle。V1只交付当前consumer需要的Dolt-backed immutable history，不预建
CurrentTableStore或generic dual-store framework。

服务拥有：

- Repository 生命周期和持久化目录。
- 同步create、repository-bound临时artifact和异步Versioned import。
- Versioned commit/ref、commit-pinned catalog和raw Arrow IPC row stream。
- import operation、幂等、operation commit marker和有限启动恢复。
- single durable-root ownership、per-repository writer和简单容量admission。
- Dolt runtime、版本识别和部署级volume snapshot恢复边界。

业务系统拥有：

- 哪个 Workspace/Submission 可以写入。
- 哪个derived CandidateProjection/ArchivePlan可以生成import。
- ruleset、storage/comparison projection、CanonicalizationManifest、SnapshotSummary、Comparison 和 Risk 语义。
- 原始package向外部系统的备份。
- 业务content digest、no-change判断与选择Repository verification policy。
- 业务 retention、审批、权限和状态机。

独立CompareAndSetRef、rollback、promotion和审批发布等到出现真实consumer后再增加。

### 9.2 公共API

V1公共能力只包含create、upload、Versioned import/operation/ref/catalog/stream和
health/readiness。精确operation、identity、DTO、stream、failure和security规则由
[Repository Service Contract](../contracts/repository-service.md)唯一规定。

Read只接受explicit CommitId；需要当前main时，caller先ResolveVersionedRef。
`CreateRepository`和`UploadArtifact`同步执行，`SubmitVersionedImport`是唯一异步
业务operation。T2只建立DTO skeleton；真实route从`/v1/`激活并由FastAPI OpenAPI
拥有wire。

### 9.3 Import 与 artifact

Repository import 采用异步 operation：

```text
SubmitVersionedImport(
  repository_id,
  artifact_ref,
  target_ref="main",
  expected_commit_id,
  verification_policy="STRUCTURAL",
  unknown_type_policy="REJECT",
  idempotency_key
) -> repository_operation_id
```

`expected_commit_id`同时是新commit parent和target ref CAS预期。成功结果返回
commit和ref，不返回服务端`repository_path`或`run_dir`。Service始终检查upload
size/raw SHA、package safety、commit marker和mandatory commit CAS；caller选择
NONE/STRUCTURAL/FULL_SCAN，默认STRUCTURAL。FULL_SCAN只做bounded read/type
conversion/row-count检查，不提供业务digest或防篡改readback。未知type默认REJECT，
caller可显式选择lossy STRINGIFY。

Package固定为`manifest.json + replay.sql`的`tar+zstd`。`replay.sql`由受信Backend
生成；Service只做固定文件、路径、大小和基本manifest检查。大型bytes不进入普通
JSON payload：

- Upload使用authenticated repository-bound one-shot streaming；
- 不接受URL、host path、presigned URL、multipart或range resume；
- row read直接使用标准Arrow IPC stream；
- success result持久化后删除本地package；
- orphan/普通失败按TTL清理，RUNNING/manual-recovery package保留。

### 9.4 容器与运行约束

- 一个Repository同时只有一个import writer，不同Repository有限并行。
- 多实例不得无协调共享可写 `.dolt` 目录。
- publication只允许expected commit CAS，不提供LWW或force。
- v1使用单ASGI process、单durable-root lock和per-repository operation state。
- 多副本需要 repository ownership/sharding 和共享控制面 registry。
- 使用简单的upload/import并发上限、single upload limit和free-disk admission，不建
  通用quota/accounting系统。
- 固定Dolt版本；真实数据测量import耗时和重复数据增量占用。
- Versioned history永久保留；package不常驻。
- 部署方对quiescent durable root做volume snapshot并由operator恢复；最近snapshot
  后允许人工重放package和修正变化的CommitId。

### 9.5 安全边界

- Repository及后续业务/capability安全机制遵守全局比例化保障policy；本节列出当前accepted
  边界，不隐含同机零信任、tenant隔离或独立安全主体。
- 服务使用一个global bearer token；有效token可访问全部Repository。
- TLS由deployment ingress/sidecar拥有。
- 禁止客户端提交任意宿主机路径。
- import受bounded streaming、文件大小、expanded size和磁盘admission控制。
- 不建设CallerIdentity、per-repository ACL、policy generation或typed audit subsystem。
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
    storage_projection/
    comparison_projection/
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
Phase 0  canonical cases + necessary business golden
  -> Phase 1  contracts and architecture skeleton
  -> Phase 2 WP1-R1 old-design checkpoint
  -> Phase 2 simplification design
  -> Phase 0–1 simplification design (D01 complete)
  -> cross-phase interface reconciliation (DX complete)
  -> Phase 0–2 combined code simplification
  -> revised Phase 2 Repository Service foundation
  -> Phase 3  capability foundation
  -> Phase 4  durable Operation Runtime
  -> Phase 5  business vertical slices
  -> Phase 6  Rust coverage expansion and compute optimization
  -> Phase 7  concurrency/cache/performance
  -> Phase 8  shadow traffic and cutover
  -> Phase 9  cleanup and production hardening
```

阶段不是纯水平层交付。WP1-R1只形成历史checkpoint；Phase 2简化设计、Phase 0–1
同原则设计与DX现已闭合。当前把共享conformance、artifact和contract清理作为同一
执行阶段，按DX plan分批提交。Phase 1 canonical
bytes、Python/Rust核心和业务golden在清理中保持不变。联合清理完成后按修订计划
交付最小Versioned Repository纵切；CurrentTableStore等能力等待真实consumer。Phase 3
完整设计在P2-R1至P2-R6全部完成后开始；P2-R5只允许contract-owned fixture consumer，
不提前设计Phase 3业务capability。
进入Phase 5后仍按upload preview、submit、review、archive、history compare形成
业务闭环。

## 12. 验证策略

每个 phase 至少覆盖：

- Domain unit tests：状态机、不变量、policy。
- Capability contract tests：当前consumer使用的输入、输出、业务digest和版本。
- Architecture tests：禁止反向依赖、内部模块越界和旧模块 import。
- Operation tests：事务、幂等、重试和明确的人工修复分支。
- Repository client/server tests：HTTP contract、真实Dolt integration和已知consumer
  end-to-end。
- Canonical core：Python/Rust直接消费既有128个canonical cases并逐字节验证；
  Repository不消费该corpus。
- Failure tests：按风险等级覆盖语义屏障。权威/不可逆事实覆盖effect前中断、effect后响应
  丢失、幂等/CAS和恢复；derived/temporary对象覆盖失败不污染权威事实与可重试/诊断；
  不建设全故障点或内部interleaving evidence matrix。
- End-to-end journey：upload -> preview -> submit -> review -> archive -> history compare。
- Measurement：correctness优先，只记录correctness-passed production path的
  dataset/version、环境说明和raw results；不运行legacy性能门禁或formal capture gate。

## 13. 架构完成标准

整体重构完成至少满足：

- Domain 不依赖 API、operation runtime、Dolt 或具体 persistence。
- API 不拥有业务状态机和跨领域统一 StateStore。
- Capability 依赖图无环，调用方只使用稳定公共契约。
- Operation 不依赖进程内闭包，支持持久化接管。
- Workspace/Review/Baseline/Archive 不持久化可派生的阶段、Candidate、Batch 或 dry-run 状态。
- 业务容器没有 Dolt 二进制，不挂载 repository volume。
- 业务 contract 不出现 `repository_path`、`run_dir` 或服务端本地 artifact path。
- Repository Service contract 不出现 Workspace、Submission、Archive、Baseline、History 等业务语义。
- Repository首版只暴露Versioned-specific API；写操作具备CAS、幂等和operation
  marker，矛盾结果显式进入人工修复。
- Repository使用单一内网bearer token；不包含per-repository ACL或通用治理surface；
  verification由caller显式选择且默认STRUCTURAL。
- Raw SourcePackageArtifact 与 canonical Dolt state 权威分离，storage/comparison projection 分离。
- Python/Rust canonical核心golden保持一致；普通fixture和CI不自建closure/evidence
  digest。
- 正式业务旅程、必要artifact hash、业务digest和前端contract通过验收。

## 14. 已完成 ADR

以下 ADR 已完成：[最小持久状态（0002）](../adr/0002-minimal-persisted-business-state.md)、[external-effect reconciliation（0003）](../adr/0003-external-effect-reconciliation.md)、[raw artifact/canonical Dolt（0004）](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)、[shared canonical encoding（0005）](../adr/0005-shared-canonical-encoding.md)、[language-neutral fixture oracle（0006，已被0010替代）](../adr/0006-language-neutral-fixture-oracle.md)、[vNext performance baseline authority（0007，已被0010替代）](../adr/0007-vnext-performance-baseline-authority.md)、[generic dual-store/caller-selected rigor（0008，WP1-R1后被替代）](../adr/0008-generic-dual-store-and-caller-selected-rigor.md)、[适度保障与可信内网Repository（0009）](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)、[最小golden与普通CI（0010）](../adr/0010-minimal-golden-and-ordinary-ci.md)和[协作式artifact cleanup（0012，替代0011）](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)。

Phase 2修订方向已固定为HTTP/OpenAPI、raw Arrow IPC、repository-bound upload、
single-root writer、最小operation marker和Versioned-only surface。CurrentTableStore、
multi-node/shared writer、legacy cutover、额外platform/provider、resumable upload
和复杂maintenance/security governance均需按ADR 0009重新进入。
Phase 3及之后新增的安全、恢复、evidence和测试机制还必须通过全局比例化保障policy的
风险分类与架构升级门。

## 15. 与现有文档的关系

- `modules.md` 和 `implementation-boundary.md`：当前模块边界与第一阶段实现约束；后续按本文目标逐步更新。
- `flows.md`：legacy 业务旅程证据；正式状态与转换由 owner contract 规定。
- `operations.md`：Operation Runtime 的历史设计来源；外部 effect 以正式 reconciliation contract 为准。
- 旧 `contracts/`：现有数据契约证据；正式 contract 按 interface/application/capability/repository wire owner 分类。
- `capabilities/`：各 capability 的算法、输入输出和验收细节来源。
- `capabilities/repository-import.md`、`capabilities/repository-ref-materialization.md`：Repository Service 拆分前的行为证据，不是 vNext 性能 oracle。
- ADR：关键不可逆决策的最终权威记录。

本文先固定总体方向；目录迁移、服务拆分和 contract 删除均应按 phase 小步实施，并在每阶段保留可运行、可验证的正式主路径。
