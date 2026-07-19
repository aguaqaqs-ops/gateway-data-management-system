# Contract Taxonomy and Ownership

状态：正式设计（Accepted）

阶段：Phase 0–1

本文定义 backend vNext 重构后的 contract 分类、语义所有权、存放位置、依赖方向和变更治理。本文只固定长期规则，不记录讨论过程；讨论记录保留在对应的 `refactoring/temporary/phase-*/` 目录。

## 1. 设计目标

- 让每个稳定 contract 只有一个明确 owner。
- 区分 domain model、application command、capability contract、wire schema 和 persistence record。
- 防止统一 `contracts`、`models.py` 或 `shared DTO` 演变成无所有权的公共依赖中心。
- 为 Python、Rust、Repository Service、artifact 和持久 operation 提供明确的跨语言/跨进程边界。
- 让 contract 变更、版本、digest、cache 和滚动升级影响可以被审查和测试。

## 2. 核心定义

### 2.1 Contract

Contract 是两个独立演进单元之间稳定、可验证的约定，包括：

- 输入输出的数据结构和字段语义。
- 行为、前置条件、后置条件和错误语义。
- 序列化、排序、digest 和版本规则。
- 兼容窗口、资源限制和生命周期。

以下情况至少满足一个时，才应提升为正式 contract：

- 跨模块稳定调用。
- 跨进程或跨服务传输。
- Python/Rust 等跨语言调用。
- 持久化后需要恢复或重放。
- 被 artifact/cache 长期保存。
- 需要独立版本化或由外部调用方消费。

### 2.2 Owner

Owner 是定义 contract 业务/技术语义并承担兼容责任的模块或服务。

```text
Contract 由语义定义者拥有，
不由消费者、存储者、传输者或展示者拥有。
```

规则：

- 每个正式 contract 只有一个 owner。
- 多个消费者不产生共同所有权。
- 消费方不能为了本地便利直接扩展 owner contract。
- 存储 artifact bytes 不代表拥有 artifact 内容 schema。
- 将对象暴露到 HTTP 不会把对象所有权转移给 API 层。

### 2.3 Model、Schema、Port 与 Record

| 概念 | 含义 |
| --- | --- |
| Model | 模块内部或公共的语义对象，不必可序列化。 |
| Schema | JSON、Arrow、Parquet、Protobuf 等物理表示。 |
| Port | 调用方需要的行为接口，由调用方一侧定义。 |
| Wire contract | 跨进程请求、响应、流和错误协议。 |
| Persistence record | 某个 adapter 的数据库/文件存储结构。 |
| Artifact contract | Artifact envelope 与其内容 schema 的组合约定。 |

一个概念可以同时具有 model 和 schema，但二者不应默认使用同一个 Python class。

## 3. 非 Contract 边界

以下内容默认不是公共 contract：

- Domain entity 的完整内部字段。
- ORM model、数据库 row 和 migration 内部结构。
- Python `dataclass` 本身。
- Capability 算法中间状态和 provider 私有配置。
- Cache 内部索引、临时 payload 和路径布局。
- HTTP handler 临时参数。
- 进程内 session、callback、executor 和 closure。
- Host path、PID、Python class identity 和具体 Dolt CLI 命令。

如果这些内容需要跨边界使用，必须先提炼稳定语义并由明确 owner 定义新的 contract，不能直接复用内部对象。

## 4. Contract 分类

### 4.1 Shared Semantic Contract

Owner：`shared_kernel`

职责：

```text
DigestRef
CanonicalIdentifier
scalar/null/decimal/datetime semantics
canonical serialization
FailureDescriptor category/recovery/effect primitives
Diagnostic primitive
ContractVersion primitive
```

约束：

- 只包含没有业务归属、被多个边界共同使用的稳定原语。
- 不包含 Workspace/Submission 状态、use-case error code/phase/details、benchmark result、repository purpose 或 capability facts。
- Python、Rust 和 Repository wire schema 必须对这些语义具有一致解释。
- Canonical bytes 的唯一规范见 [Shared Canonical Encoding](shared-canonical-encoding.md)；业务 use case 分别拥有自己的 stable failure code registry。

### 4.2 Domain Contract

Owner：对应领域模块，例如 `workspace`、`submission`、`archive`。

可以公开：

```text
typed business ID
stable status enum
read-only snapshot/projection
domain event
explicit domain policy result
```

默认保持内部：

- 完整 aggregate/entity。
- 状态转换实现。
- Persistence record。
- 为单个 adapter 添加的技术字段。

跨模块调用不得直接加载并修改其他模块的完整 entity；跨聚合协调通过 application use case 完成。

### 4.3 Application Contract

Owner：具体 application use case。

示例：

```text
AcceptSubmissionCommand/Result
FinalizeSubmissionCommand/Result
ExecuteArchiveCommand/Result
CompareHistoryQuery/Result
```

规则：

- 表达调用者意图和用例结果，不暴露内部 operation step、provider 或 repository path。
- HTTP DTO 映射为 application command，但二者不是同一个 contract。
- Command 优先携带 ID、digest、ref 和显式 value object，不携带已加载 domain entity。
- 跨服务副作用必须包含 idempotency/correlation 信息或由 use case 明确生成。

### 4.4 Capability Contract

Owner：对应 capability。

示例：

```text
SnapshotMaterializationInput/Result
ProjectionSchema/Result
ComparisonInput/Facts/Result
RiskEvaluationInput/Report
SurfaceAssemblyInput/Result
BundleAssemblyInput/Result
```

规则：

- Contract 与实现就近放置，例如 `capabilities/comparison/contracts.py`。
- 消费者只依赖公共 contract/entrypoint，不依赖 `_internal`、planner、builder、provider selection 或 cache layout。
- Contract 必须 flow-neutral，不包含 Workspace、Submission、Archive 或 History request identity。
- Capability 可以依赖上游 capability 的公共 contract，但禁止反向依赖和环。
- Python reference、Rust、Dolt native 等 provider 共享同一 capability contract；语言或 provider 实现不拥有业务语义。Provider 类型不应泄漏到 application contract，除非调用方需要显式策略控制。
- 满足稳定 contract、golden oracle、Arrow/Parquet 边界和性能证据的 capability 可以首版直接使用 Rust production provider；Python reference 可以只覆盖小规模正确性，不要求成为同等规模 production implementation。
- Python/Rust 具体分工和 provider 进入条件遵守 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)。

允许的主依赖方向：

```text
table_access/table_rules
  -> storage_projection -> RepositoryImportArtifact
  -> comparison_projection
  -> snapshot
  -> comparison
  -> risk
  -> surface
  -> bundle
```

### 4.5 Operation Contract

Owner：`operations`

Operations 拥有：

```text
OperationRecord/Status
StepRecord/Status
Lease/Claim
RetryPolicy
CheckpointRef
ReadyClosureRef
generic failure and diagnostics
```

Application 拥有：

```text
JobDefinition
job-specific payload schema
business step meaning
capability/repository invocation policy
```

Operation 只持久化 job envelope：

```text
job_kind
job_contract_version
job_payload or job_payload_ref
```

Operation Runtime 不解释 payload 中的 Workspace、Submission 或 Archive 语义。Job payload 必须版本化，不能使用未声明 schema 的任意 context dict。

### 4.6 Artifact Contract

Artifact contract 分为 envelope 与 content schema 两个 owner。

`artifacts` 拥有通用 envelope：

```text
ArtifactRef
ArtifactManifest
ArtifactClosure
logical_ref
content_digest
size
media_type
retention class
location-independent access metadata
```

生产 artifact 的 capability 拥有内容 schema：

| Artifact 内容 | Owner |
| --- | --- |
| `SourcePackageArtifact` content | Workspace Input/Application |
| `SnapshotTableArtifact` full-row facts | Snapshot Materialization capability |
| `CanonicalizationManifest`、`RepositoryImportArtifact` | Table Rules/Storage Projection capability |
| Comparison projection table | Comparison Projection capability |
| `SnapshotManifest` readback envelope | Repository Service；canonical expected fields 由 Storage Projection 定义 |
| Comparison records | Comparison capability |
| Ordered records | Ordered Comparison capability |
| Risk annotations/report | Risk capability |
| Surface document | Surface capability |
| Bundle index/layout | Bundle capability |

ArtifactStore 保存、校验和定位 bytes，不解释业务内容。内容 schema 变化由内容 owner 版本化，并说明 digest/cache compatibility。

### 4.7 Business Port

Owner：需要该行为的 application/domain 一侧。

示例：

```text
RepositoryVersionStore
RepositoryTableAccess
RepositoryImportGateway
ArtifactStore
OperationScheduler
WorkspaceRepository
SubmissionRepository
```

规则：

- Port 表达调用方需要的最小能力，不复制外部服务完整 API。
- Infrastructure adapter 实现 port，并负责 domain/application model 与 wire DTO 的映射。
- Port 不暴露具体 HTTP/gRPC client、Dolt session、ORM 或 host path。

### 4.8 Repository Service Wire Contract

Owner：独立 Repository Service。

包含：

```text
RepositoryId/Ref/Commit
ResolveRef
Create/GetRepository
SubmitImport/GetOperation
RepositoryOperationJournal/Evidence
SnapshotManifest
Create/Delete/CompareAndSetRef
GetCatalog/StreamRows/ExportTable
DiffRefs
GC
wire error and timeout semantics
```

禁止包含：

```text
Workspace
Submission
Preview
business candidate entity/state
baseline business batching/state
HistoryComparison
business promotion policy
```

业务系统的 Repository Port 与 Repository Service wire contract 是两个独立 contract：

```text
Application Repository Port
  -> Infrastructure RemoteRepositoryAdapter
  -> Repository Service wire API
```

Transport 从 HTTP 切换为 gRPC 不应改变 application contract。

### 4.9 Interface Contract

Owner：具体 interface，例如 `interfaces/http`。

包含：

```text
HTTP request/response schema
pagination
authentication/session context
HTTP status and error mapping
download/upload protocol
```

Interface DTO 只存在于 interface 层。Domain、Capability 和 Application 不得 import HTTP schema。

### 4.10 Integration Event Contract

Owner：事件生产方。

示例：

```text
SubmissionFinalized
SubmissionApproved
ArchiveCompleted
MainlineAdvanced
```

规则：

- Event 描述已经发生的事实，不伪装成内部命令。
- Event 必须包含 event ID、occurred_at、producer contract version 和必要 correlation ID。
- 消费方不得直接修改生产方 event schema；新需求通过 owner 评估或建立消费者自己的 projection。

### 4.11 Persistence Contract

Owner：对应 infrastructure adapter。

数据库表、ORM record、JSON column 和 migration 属于持久化实现。Domain 和 Application 只依赖 repository port，不依赖数据库 schema。

持久化 schema 可以独立版本化，但如果保存正式 contract payload，必须同时记录 payload contract/version，并遵守对应 owner 的兼容规则。

## 5. Ownership Matrix

第一版 ownership 基线如下：

| 对象/语义 | Owner | 主要消费者 |
| --- | --- | --- |
| `DigestRef`、CanonicalIdentifier、canonical encoding | Shared Kernel | 所有模块和跨语言实现 |
| `FailureDescriptor.category/recovery/effect` | Shared Kernel | Application、Operations、Interfaces |
| Submit/Review/Archive failure code、phase、details | 对应 Application use case | Operations、Interfaces、Fixtures |
| `ArtifactRef`、manifest、closure | Artifacts | Capabilities、Operations、Interfaces |
| `SourcePackageArtifact` content/provenance/retention intent | Workspace Input/Application | Workspace、Submission、ArtifactStore |
| `SnapshotTableArtifact` full-row facts/schema | Snapshot Materialization capability | Preview、Storage/Comparison Projection |
| `Snapshot`、`SnapshotSummary` | Snapshot capability | Comparison、Application |
| `TableReader`、`TableSet` | Table Access contract | Snapshot、Comparison、Repository adapter |
| Storage column policy/key/ordered identity、`CanonicalizationManifest` | Table Rules/Storage Projection capability | Submit、Repository adapter、Fixtures |
| Comparison `ProjectionSchema`、projection digest | Comparison Projection capability | Snapshot、Comparison、Cache |
| `RepositoryImportArtifact` content schema | Storage Projection capability | Submit Attempt、Repository Service |
| `SnapshotManifest` readback/journal schema | Repository Service | Repository adapter、Submit/Archive reconciliation |
| `ComparisonFacts`、standard records | Comparison capability | Risk、Surface、Bundle |
| Ordered facts/records | Ordered Comparison capability | Risk、Surface、Bundle |
| `RiskFacts`、`RiskReport` | Risk capability | Surface、Bundle、Application |
| `ComparisonSurface` | Surface capability | Bundle、Interface |
| `ComparisonBundle` | Bundle capability | Application、Interface |
| `Workspace`、`UploadRevision` | Workspace Domain | Workspace Application、Interface |
| `PreviewResult` | Workspace Application | Submission Application、Interface |
| `SubmitAttempt` | Submission Application | Operations、Workspace、Interface |
| `Submission`、Review projection/event | Submission Domain | Archive Application、Interface |
| `BaselineNode`、`BaselineHead` | Baseline Domain | Workspace、Submission、Archive、History |
| `ArchivePlan`、`ArchiveExecution` | Archive Application | Baseline、Operations、Interface |
| `ArchiveResult` | Archive Domain | Baseline、Submission、Interface |
| `CandidateProjection`、`PreviewArchivePlan` | Archive Application read model | Interface、StartArchive |
| `OperationRecord`、Step、Lease | Operations | Application jobs、Workers、Interface polling |
| `SubmitFinalizeJobPayload` | Submission Application | Operations handler |
| Repository ID/ref/commit/CAS wire semantics | Repository Service | Remote Repository adapter |
| Business Repository Port | Consuming Application | Repository adapter/fake |
| Archive mainline promotion decision | Archive Application | Repository Port |
| Hidden SnapshotSummary table schema/content | Snapshot capability | Snapshot read/write adapter |
| Hidden table 的普通版本化存储 | Repository Service | Repository adapter |
| HTTP preview/submit/archive DTO | HTTP Interface | External clients、Application mapping |
| Cache registry/envelope | Cache module | Capability provider、Operations |
| Cache payload schema | Payload-producing capability | Cache module、consumer capability |
| Scenario manifest/runner result/evidence bundle | Conformance Harness | Python、Rust、Repository、CI |
| Scenario expected semantic content | 对应 Domain/Application/Capability contract owner | Conformance Harness |
| `BenchmarkBaselineRecord`/measurement semantics | Performance Measurement | Phase owners、CI、Architecture review |
| `environment_profile_id` | Deployment/Repository Environment owner | Performance Measurement |

新增对象时必须先加入 ownership matrix 或在对应正式 contract 中声明 owner，不能通过放入 `shared` 目录回避归属决策。

## 6. Public、Persisted 与 Wire Classification

每个正式 contract 必须声明三个独立维度：

```text
module_public: yes/no
persisted: no/optional/required
wire: none/json/http/grpc/arrow/parquet
```

示例：

| Contract | Module Public | Persisted | Wire |
| --- | --- | --- | --- |
| `ComparisonInput` | yes | no | none/Arrow refs |
| `ComparisonFacts` | yes | optional | metadata JSON |
| Comparison records | yes | required when published | Parquet |
| `OperationRecord` | yes | required | persistence + HTTP metadata |
| Workspace entity | no | required through adapter | none |
| Workspace HTTP DTO | yes at interface | no | HTTP JSON |
| Repository import request | yes at service boundary | operation journal | HTTP/gRPC + artifact ref |
| `SourcePackageArtifact` | yes by ref | required | artifact bytes + manifest |
| `SnapshotTableArtifact` | yes by ref | current Preview/active Attempt only | Arrow/Parquet + manifest |
| `RepositoryImportArtifact` | yes by ref | active Attempt/checkpoint | artifact stream + manifest |
| `CanonicalizationManifest` | yes | required for accepted commit | JCS JSON |
| `SnapshotManifest` | yes | required as VERIFIED evidence | Repository wire/JCS JSON |
| `BenchmarkBaselineRecord` | yes | required when accepted | JCS JSON |

`module_public=yes` 不等于必须跨语言序列化；`persisted=yes` 也不等于可以直接作为 HTTP response。

## 7. 建议代码落点

Contract 按 owner 就近放置：

```text
backend_vnext/
  shared_kernel/
    contracts.py

  modules/
    workspace/
      domain/
      application/
        contracts.py
      ports.py

  capabilities/
    comparison/
      contracts.py
      service.py
      _internal/

  operations/
    contracts.py
    runtime.py

  artifacts/
    contracts.py
    store.py

  interfaces/
    http/
      schemas/

  infrastructure/
    repository_client/
    persistence/
```

跨语言/跨服务物理 schema 可以集中在独立 schema root，但 schema owner 仍由语义模块决定：

```text
schemas/
  shared-semantics/v1/
  compute/v1/
  repository/v1/
  artifacts/v1/
```

集中存放生成输入不等于集中拥有语义。Schema 文件必须声明 semantic owner 和 contract ID。

## 8. 依赖规则

```text
interfaces -> application
application -> domain + capability contracts + ports + operation contracts
domain -> shared_kernel

capability implementation
  -> own contract + upstream capability contracts + shared_kernel

operations implementation
  -> operation contracts + shared_kernel

infrastructure
  -> business ports + external wire contracts
```

禁止：

- Domain import API、Operations、Dolt 或具体 persistence。
- Capability import Application、Workspace、Submission、Archive。
- 上游 capability import 下游 capability。
- 跨 capability import `_internal`、planner、builder 或 provider 私有模块。
- Application/Domain import HTTP schema。
- Business code import Dolt CLI、repository local session 或 host path。
- 通过 package `__init__.py` 大量 re-export 内部模型形成隐式公共 API。

这些规则必须由静态 import graph/architecture tests 在 CI 中执行。

## 9. 版本模型

每个正式 contract 至少记录：

```text
contract_id
semantic_contract_version
wire_schema_version optional
owner
stability
serialization
digest_participation
compatibility_window
```

区分基础版本与独立 contract version axes：

| 版本 | 含义 | 是否进入业务 digest/cache identity |
| --- | --- | --- |
| Semantic contract version | 字段含义、排序、计算或正式结果语义 | 语义相关时进入 |
| Wire schema version | JSON/Protobuf/Arrow 等传输结构 | 只有影响正式语义时进入 |
| Provider implementation version | Python/Rust/Dolt 的算法实现版本 | 纯性能变化不进入 |

下列版本轴不得折叠为单个“系统版本”，也不得因 provider 升级而静默改变：

| Version axis | Owner | 主要影响 |
| --- | --- | --- |
| `canonical_encoding_version` | Shared Kernel | JCS/scalar/frame/digest bytes |
| `fixture_manifest_schema_version` | Conformance Harness | Scenario closure/validation |
| Scenario-bound semantic contract version | 对应 semantic owner | Golden expected meaning |
| `storage_projection_version` + ruleset digest | Storage Projection/Table Rules | Canonical Dolt schema/content |
| Repository wire/readback schema version | Repository Service | Import/journal/SnapshotManifest wire |
| `measurement_contract_version` | Performance Measurement | Stage/metric/eligibility/aggregation |
| Baseline series identity | Performance Measurement + environment/data owners | 可比 dataset/environment/component 集合 |

规则：

- 删除字段、改字段含义、改变默认值或排序属于 breaking change。
- 新字段必须说明是否可选、默认语义、是否进入 digest。
- Wire enum 必须规定未知值处理；内部 domain enum 可以保持严格。
- 跨进程 contract 至少定义生产部署所需的滚动升级窗口。
- Artifact/cache schema 变化必须说明旧数据读取、失效、重建或迁移策略。
- 不对只在一个函数内部使用的中间 DTO 进行无意义版本化。

## 10. Contract Lifecycle

正式 contract 采用以下状态：

```text
EXPERIMENTAL
  -> STABLE
  -> DEPRECATED
  -> REMOVED
```

- `EXPERIMENTAL` 可以快速变化，但不得作为长期 artifact/cache 或外部正式 API，除非显式记录风险。
- `STABLE` 变更遵守兼容和版本规则。
- `DEPRECATED` 必须记录替代 contract、迁移 owner 和最晚删除阶段。
- `REMOVED` 前必须确认正式调用、artifact reader、cache 和滚动部署窗口均已结束。

## 11. Change Governance

任何正式 contract 变更必须由 owner 提交，并至少回答：

```text
change_reason
semantic_change
wire_change
digest/cache impact
artifact/persistence impact
Python/Rust/Repository impact
compatibility window
migration/fallback
tests and golden fixtures
```

变更规则：

- 消费方提出需求，owner 决定扩展原 contract、提供 projection，还是新建 consumer-owned contract。
- 不为单个消费者方便向核心 facts 添加展示或存储字段。
- Contract 变更必须更新所有语言的 contract/golden tests。
- 无法滚动兼容的跨服务变更必须通过 ADR 或迁移计划收口。

## 12. 明确禁止的模式

```text
contracts/common.py
contracts/models.py
shared/dtos.py
dict[str, object] context bag 作为稳定 contract
一个 DTO 同时用于 HTTP、Domain、DB 和 Artifact
Capability 从其他 capability 的 __init__.py 获得大量隐式 re-export
Python object graph 直接作为 Rust FFI contract
Repository API 返回 Path 或 server session
Operation payload 保存未版本化任意 dict
Artifact envelope 解释 capability 内容语义
Persistence record 反向成为 domain model
```

## 13. Phase 1A 正式决策

本阶段确认：

1. Contract 按语义 owner 就近存放，不建立统一公共 DTO 包。
2. Domain entity 默认内部，跨模块暴露 ID、snapshot/projection、event 或 application result。
3. Capability contract 与实现分离，消费者只能依赖公共 contract 和 entrypoint。
4. Operation 通用 contract 与具体 JobDefinition/job payload 分离。
5. Artifact envelope 与 artifact content schema 分离。
6. Business Repository Port 与 Repository Service wire contract 分离。
7. Python/Rust provider 共享 capability contract，语言实现不取得 contract ownership；稳定热点允许采用 Rust production provider + Python 小规模 oracle。
8. Shared Kernel 只拥有 FailureDescriptor 的公共维度，stable use-case code/phase/details 由对应 Application owner 管理。
9. Raw Source、full-row Snapshot、canonical import/readback 和 comparison projection 是不同 artifact/contract owner，不建立泛化 `Projection` authority。
10. Fixture manifest、canonical encoding、storage projection、Repository wire 和 measurement 使用独立版本轴。

后续 Phase 1B Shared Semantic Contracts、Phase 1C Dependency Rules 和 Phase 1D Cross-process Contracts 必须遵守上述决策。

## 14. 验收标准

- 所有第一轮稳定 contract 都能在 ownership matrix 中找到唯一 owner。
- Public、Persisted、Wire 三个维度已明确。
- Domain、Application、Capability、Operation、Artifact、Repository wire 和 Interface contract 不再混用同一 DTO。
- Repository wire contract 不包含当前项目业务语义。
- Operation Runtime 不解释 job-specific payload。
- ArtifactStore 不解释 capability content schema。
- Python/Rust 边界不使用逐行 Python object graph 作为正式 contract。
- Architecture tests 可以根据本规则检测禁止依赖。
- Contract 变更具有 owner、版本、compatibility 和 golden test 要求。
- SourcePackage、SnapshotTable、RepositoryImportArtifact、CanonicalizationManifest、SnapshotManifest 和 BenchmarkBaselineRecord 均能定位到唯一内容 owner。
