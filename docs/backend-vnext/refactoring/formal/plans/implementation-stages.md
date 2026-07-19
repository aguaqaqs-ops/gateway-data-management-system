# Backend vNext Refactoring Implementation Stages

状态：正式设计基线（Accepted Baseline）

本文把 [整体架构总纲](../architecture/architecture-and-refactoring-plan.md) 转换为可执行的重构阶段。阶段编号表示主要依赖顺序，不表示必须完成整个水平层后才能继续；每一阶段只建设下一条业务纵切所需的最小能力，并保持可运行、可验证和可回退。

## 1. 实施原则

### 1.1 从头实现的含义

“从头重构”指新代码不继承旧模块边界和内部 DTO，不代表重新猜测业务语义：

- 旧代码只作为业务行为、边界 case 和人工体验的发现 oracle；不作为 vNext 内部结构或性能 oracle。
- 新代码不得依赖旧业务模块，也不在旧实现上包一层 adapter 作为正式能力。
- 稳定的业务结果、digest、artifact 和状态变化必须由 fixture、contract 和验收用例固定。
- 新旧实现可以在测试或 shadow 阶段离线对照，但不共享可变业务状态。

### 1.2 纵向交付优先

禁止按以下方式长期水平推进：

```text
先写完全部 core
  -> 再写完全部 domain
  -> 再写完全部 capabilities
  -> 最后一次性接 API
```

推荐方式：

```text
最小基础
  -> upload preview vertical slice
  -> submit vertical slice
  -> review vertical slice
  -> archive vertical slice
  -> history compare vertical slice
```

每个纵切都应包含 contract、domain/application、capability、operation、adapter、API 和测试，形成可运行闭环。

### 1.3 正确性先于性能

- 第一版 capability 默认串行、确定性执行。
- 初始 production route 可包含满足稳定 contract、language-neutral oracle 与 component evidence 的 Rust provider；后续 Rust coverage、并行、cache 和 provider 优化不能先于 accepted vNext baseline。
- 性能结果只统计 validation passed 的运行。
- 优化不能改变 canonical scalar、排序、digest、records 或 diagnostics 语义。

### 1.4 阶段门禁

每个 Phase 必须满足退出条件后，才能把下一 Phase 的产物接入正式主路径。允许提前开展验证性 spike，但 spike 代码不能绕过 contract 和门禁直接成为正式实现。

## 2. 阶段总览

```text
Phase 0  Baseline and Oracle
    |
Phase 1  Contracts and Architecture Skeleton
    |
Phase 2  Repository Service Foundation
    |
Phase 3  Capability Foundation
    |
Phase 4  Durable Operation Runtime
    |
Phase 5  Business Vertical Slices
    |
Phase 6  Rust Coverage Expansion and Compute Optimization
    |
Phase 7  Concurrency, Cache and Performance
    |
Phase 8  Shadow Traffic and Cutover
    |
Phase 9  Cleanup and Production Hardening
```

Phase 2 至 Phase 4 可以在接口稳定后有限并行，但必须共同服务于 Phase 5 的纵切，而不是独立扩张范围。

## 3. Phase 0：Baseline and Oracle

### 目标

固定新实现必须保持或有意改变的业务语义、数据契约、fixture/oracle 和 performance measurement contract；建立可重复 conformance 环境与 numeric baseline capture gate。同时识别可派生状态、重复事实、无真实调用方功能和无证据优化，形成明确的首版简化范围。

Normative outputs 由 [Business Lifecycle](../contracts/business-lifecycle-and-state.md)、[External Effect](../contracts/external-effect-and-recovery.md)、[Canonical Encoding](../contracts/shared-canonical-encoding.md)、[Fixture Conformance](../contracts/fixture-oracle-and-conformance.md)、[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)和 [Performance Measurement](../contracts/performance-measurement-and-baseline.md) contracts 分别拥有。

### 主要工作

- 列出正式业务旅程：upload、preview、submit、review、archive、next baseline、history compare。
- 固定 Workspace、UploadRevision、PreviewResult、SubmitAttempt、Submission Review、BaselineNode/Head、ArchivePlan/Execution/Result 的 owner、状态、generation gate、权限和失败语义。
- 固定 SourcePackage raw authority、canonical Dolt storage、storage/comparison projection、SnapshotTableArtifact retention 和 Repository evidence 边界。
- 在 `vnext/fixtures/` 定义 language-neutral scenario manifest、目录/命名、provenance、golden envelope、runner profile、fault/recovery checkpoint 和 CI lane。
- 固定 JCS、typed scalar、identifier、row/collection framing、digest 与 Python/Rust/Repository normative vectors。
- 定义 measurement stages、profiles、workloads、metrics、result eligibility、environment authority、baseline record lifecycle 和 first-capture gate；当前不伪造 numeric baseline。
- 将 legacy 数据迁移/旧 Dolt compatibility 保留为独立 cutover gate，本阶段不决定策略。
- 记录当前人工验收路径和已知旧 bug，不把旧 bug 自动作为新 contract。
- 按 `KEEP / SIMPLIFY / DEFER / REMOVE` 审查现有状态、流程、provider、cache、compat 和前端操作；简化项必须说明被保留的业务事实与可恢复路径。
- 优先删除可由事实推导的持久状态、重复上传/重复校验、无调用方公共 API、预优化流程和跨模块重复结果。

### 交付物

- Versioned fixture manifest、golden envelope 与 language-neutral conformance contract。
- Shared canonical encoding contract 与 normative vector specification。
- Business lifecycle、external-effect/recovery、canonical storage 与 artifact retention contracts。
- Benchmark Measurement Contract、workload/dataset identity、result schema 与 first accepted baseline capture gate。
- Flow journey/oracle audit 与 intentional-change register。
- Legacy behavior audit 和 intentional change 清单。
- First-version simplification register，记录 `KEEP / SIMPLIFY / DEFER / REMOVE`、owner、理由、风险和恢复方式。
- 第一版明确功能范围及被推迟功能的重新进入条件。

### 退出条件

- fixture 可在隔离环境重复生成相同输入 digest。
- 关键输出可做结构化比较，不依赖人工查看日志。
- 每个旧新差异可归类为 old bug、new bug 或 intentional change。
- 旧 Dolt migration/compatibility 已被明确隔离为单独 cutover gate，未被默认兼容或迁移。
- 现有主要功能、状态和优化均已完成简化分类，不存在“因为旧系统已有”而默认进入第一版的范围。
- 已确认第一版业务旅程可以在不依赖被删除/推迟功能的情况下闭环，并保留必要的可靠性和审计能力。

### 本阶段不做

- 不修改正式流量。
- 不开始大规模目录搬迁。
- 不根据单次 benchmark 决定 Rust 或并行策略。
- 不要求尚不存在的 production path 产生 numeric baseline，也不建立 legacy-vs-vNext performance report。

## 4. Phase 1：Contracts and Architecture Skeleton

### 目标

固定第一批实现真正需要的语言无关共享语义、所有权规则和依赖方向，通过一个可复用 walking skeleton 建立新代码隔离区和最小 bootstrap；不提前完成后续阶段的全部 contract 与框架。

本阶段实现 [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md) 与 [Fixture Oracle and Conformance](../contracts/fixture-oracle-and-conformance.md) 的最小 executable skeleton。

### 主要工作

- 固定 Contract Taxonomy/Ownership 和 `canonical_encoding_version`：JCS、identifier、scalar、NULL、temporal、ordering、row/collection framing、domain-separated digest 与 FailureDescriptor primitive。
- 建立 `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/` normative vectors、scenario manifest schema 和最小 conformance runner/harness skeleton。
- 只定义 walking skeleton 所需的最小跨边界 envelope：ArtifactRef、contract/version marker、operation/job reference、repository ID/ref/commit reference；完整内容由对应 owner 阶段补齐。
- 建立实际会被 walking skeleton 使用的最小 package/crate，不预创建完整目标目录树和空模块。
- 建立最小依赖检查：禁止旧业务模块 import、Domain 反向依赖和 capability 内部越界；不先建设通用架构分析框架。
- 建立一条可复用 walking skeleton：Python facade -> Arrow/PyO3 -> Rust batch kernel -> ArtifactRef/diagnostics round-trip。
- Rust interop 第一版只支持预定首个部署目标，验证 GIL release、panic/error mapping 和 wheel/image 构建；完整平台矩阵在 Rust production provider 阶段补齐。
- 为 Phase 3 首批 Rust kernel 固定 scalar、ordering、digest、Arrow/Parquet schema，以及 Python/Rust/Repository 共同消费的 language-neutral oracle 约束。
- 只补充会阻塞 Phase 2/3 开工的 ADR；Repository transport、Operation persistence 等可由对应阶段在实现前收口，不为一次性完成 Phase 1 而提前决策。

### 交付物

- 最小 Python package/Rust crate bootstrap，且均被 walking skeleton 实际使用。
- Shared canonical encoding contract/normative vectors、scenario manifest schema、最小 conformance skeleton 和 boundary envelopes。
- 最小 architecture/import tests。
- 可复用 Python/Rust/Arrow/Artifact walking skeleton，不建设一次性 throwaway demo。
- 首个部署目标的 Rust 构建、失败映射和 component execution evidence。
- Blocking decision register 与必要 ADR。

### 退出条件

- 新入口可以启动且不 import 旧业务模块。
- Phase 1 最小 contract 可以独立序列化、反序列化和版本检查；未实现模块只有 owner/边界说明，不伪造完整 DTO。
- Python/Rust/Repository 对 canonical bytes、stable invalid code、Arrow schema 和 digest fixture 有一致解释。
- 已证明 Python 可以通过粗粒度 PyO3/Arrow 调用 Rust，释放 GIL，并将受控 failure 映射为稳定 error/diagnostics。
- Walking skeleton 产生的 artifact 可按 digest 校验并通过引用恢复。
- 依赖违规会在 CI 中失败。

### 本阶段不做

- 不提前建立通用 workflow/DAG framework。
- 不创建 `common`、`helpers`、`utils` 作为未归属代码容器。
- 不一次性设计所有 HTTP、Repository、Operation 和 capability 完整 contract；它们由对应 owner 阶段按真实调用方收口。
- 不建立未被首个纵切使用的 schema registry、codegen pipeline、provider registry 和 adapter hierarchy。
- 不预创建完整目标目录树和空 package。
- 不为 Phase 1 验收构建完整 OS/architecture wheel matrix。
- 不实现完整业务流程。

## 5. Phase 2：Repository Service Foundation

### 目标

优先建立真正可运行、独立、通用、容器化的 Repository Service，使业务系统不再依赖 Dolt CLI 和仓库本地路径，并提供 accepted baseline 所需的可测 production environment。

Journal/recovery 与 canonical import/readback 分别遵守 [External Effect and Recovery](../contracts/external-effect-and-recovery.md) 和 [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)。

### 2A：Contract 清理

- 从 repository wire contract 移除 Workspace、Submission、Preview、Archive、Baseline 和 History 语义。
- 合并重复 RepositoryRef、operation 和 timeout 类型。
- 将“业务主线晋升”改为业务校验加通用 `CompareAndSetRef`。
- 规定外部 contract 不返回 `repository_path`、`run_dir` 或服务端 artifact `Path`。

### 2B：读侧

实现：

```text
Create/GetRepository
ResolveRef
GetCommit
GetCatalog
StreamTableRows
ExportTable
DiffRefs
```

读请求以 immutable commit 为一致性边界。客户端 `open_ref()` 只是 resolve + pinned commit 的便利封装，不依赖服务端 Python session。

### 2C：写侧

实现：

```text
SubmitImport
GetOperation
CreateRef
CreateImmutableRef
CompareAndSetRef
DeleteRef
Plan/ExecuteGarbageCollection
```

写侧包含单 repository writer lease、幂等键、PREPARED/APPLIED/VERIFIED operation journal、full committed-ref SnapshotManifest readback、审计和确定 effect classification。Restart/reconciliation 必须先读 evidence，不得重做可能已产生 effect 的请求。

### 2D：客户端与部署

- `FakeRepositoryClient` 用于 domain/application tests。
- `LocalRepositoryClient` 用于早期 contract integration。
- `RemoteRepositoryClient` 用于正式容器访问。
- 大文件使用对象存储引用、预签名 URL 或流式传输，不进入普通 JSON。
- Repository Service container 自己拥有 Dolt process/binary、registry、journal、repository volume 和 staging；第一版不另拆 Dolt container。
- 建立持久 volume、Dolt/image identity 固定、readiness/liveness、graceful/non-graceful restart recovery、run-scoped fresh repository 和最小 backup/restore。
- 暴露 typed measurement spans/counters 与 environment fingerprint；benchmark runner 只能走 production public client/wire contract。

### 交付物

- Repository Service image。
- Local/Remote client SDK。
- Local/Remote contract test suite。
- Repository operation、并发 CAS 和 restart recovery tests。
- Full post-commit readback、journal evidence 与可测 container environment。
- 最小运维 runbook。

### 退出条件

- 业务侧仅使用 repository ID/ref/commit/artifact/operation ID。
- Local 与 Remote 实现对相同 fixture 返回等价 catalog、rows、diff 和 commit。
- 重复 import/CAS 请求有确定幂等结果。
- 服务重启不会产生无法判断的半完成写入。
- Normal write 只有 full readback manifest 匹配后才进入 VERIFIED；unknown outcome 保持可 reconcile。

### 本阶段不做

- Repository Service 不解释 SnapshotSummary、Comparison、Risk 或业务 hidden table。
- 不实现业务 candidate selection 和 archive gate。
- 第一版不追求多节点共享写入；先固定单 repository writer ownership。

## 6. Phase 3：Capability Foundation

### 目标

建立可独立调用、独立测试、无环依赖的 capability 主链，并产出首个业务纵切需要的事实和 artifact。

Storage/comparison projection、artifact retention、ordered identity 和 full-readback expectations 以 [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md) 为准。

### 实现顺序

```text
table_access + parser -> snapshot_materialization -> SnapshotTableArtifact
table_rules + SnapshotTableArtifact
  -> storage_projection -> RepositoryImportArtifact
  -> comparison_projection -> comparison
       -> risk_evaluation
       -> business_projection
       -> surface_assembly
       -> bundle_assembly
```

Repository import 在业务系统侧收敛为 Repository Client 调用和业务 readback validation，不重新拥有 Dolt lifecycle。

### 每个 capability 的固定步骤

1. 定义或收口 `contracts.py`，固定 scalar、ordering、digest 和 Arrow/Parquet 边界。
2. 实现只覆盖小规模语义和边界 case 的 Python reference oracle。
3. 通过 Phase 0 golden/property fixtures，记录 component candidate measurement 和 implementation route；不要求 legacy 对比或已不存在的 numeric baseline。
4. 对满足 ADR 0001 门禁的稳定热点，直接实现 Rust production provider；其他能力使用 Python/Polars 验证语义。
5. 实现 artifact 输入输出、closure、失败映射和受控 provider fallback。
6. 增加独立 kernel/end-to-end benchmark 和 diagnostics。

### 重点调整

- 提取独立 storage/comparison projection，消除 snapshot 对 comparison digest 的反向依赖。
- 分离 storage projection 与 comparison projection；前者产出 CanonicalizationManifest/RepositoryImportArtifact，后者负责 schema alignment 与 compare records。
- Storage projection 直接执行 column policy、canonical key、ordered `no/gid` 与 row-integrity validation；Repository Service 不解释业务规则。
- 提取最小 `table_access` protocol，不把完整 Snapshot 泛化成通用表模型。
- 消费方只依赖 capability public contract，不 import 内部 `models.py`、planner 或 builder。
- 风险规则先保留 Python reference；大规模 row facts extraction 与规则决策分离。
- 第一批 Rust production 候选为 scalar/digest、storage/comparison projection、standard hash diff、records 和计算结果的 Arrow/Parquet materialization。
- `SnapshotTableArtifact` 只在 current Preview/active SubmitAttempt 期间 pin；Attempt 终态后可重算，不建设长期重复 full-row archive。
- Python reference 不是与 Rust 同等规模的 production provider；正式语义由 contract 和 golden fixtures 拥有。

### 交付物

- Capability contract、Python reference oracle 和按门禁选择的 production implementations。
- 首批 Rust core/PyO3 providers 及跨语言 differential tests。
- Capability-level unit、contract 和 benchmark tests。
- Artifact schemas 和 closure validation。
- 无环 capability dependency report。

### 退出条件

- 每个 capability 可脱离 API、application 和 Operation Runtime 单独调用。
- 相同输入、版本和 policy 产生稳定结果与 digest。
- Rust production provider 与 Python reference 在 golden/property fixtures 上语义一致。
- Python、Rust 和 Repository 对 canonical encoding normative vectors 逐字节一致。
- Capability 不包含 Workspace、Submission、Archive、History request 等 flow identity。
- 依赖图无环且无内部实现越界。

### 本阶段不做

- 不为每个 capability 同时维护 Python、Rust、Dolt native 多个同等权威的正式 provider。
- 不要求尚未满足 Rust 进入条件的 capability 为语言统一而使用 Rust。
- 不引入无 benchmark 依据的表级并行和 cache。

## 7. Phase 4：Durable Operation Runtime

### 目标

建立可持久化、可重试、可接管的最小执行运行时，为 submit、archive 和 history 等耗时流程提供可靠执行机制。

Operation 与业务 execution/effect evidence 的分界以 [External Effect and Recovery](../contracts/external-effect-and-recovery.md) 为准。

### 主要工作

- 持久化 operation/step store 和 optimistic version。
- 原子 claim、lease、heartbeat、timeout takeover。
- 稳定 `operation_kind + step_name -> JobDefinition handler` 注册。
- Step output 只保存稳定 DTO、business ID、artifact ref、repository operation ID 和 checkpoint。
- 大型 Comparison/Risk/Surface 结果必须通过 artifact/checkpoint 重载，不能依赖 Python 闭包。
- 实现 retry、cancel、supersede、final failure 和 READY closure。
- 建立 Repository remote operation 的 submit/poll/evidence checkpoint 模式，不占用线程阻塞等待。
- Takeover `RUNNING` step 时先读取 durable checkpoint 与 Repository journal；`APPLIED/VERIFIED` 向前完成，`UNKNOWN` 只 reconcile，只有 explicit `NOT_APPLIED` evidence 才能用原 idempotency key replay。
- 第一版保持顺序 step；只预留固定 fan-out/fan-in contract。

### 交付物

- Durable Operation Runtime。
- JobDefinition registry。
- Worker entrypoint。
- Crash、lease、retry、duplicate delivery 和 cancellation tests。

### 退出条件

- 任意 step 后终止 worker，另一 worker 能从 checkpoint/evidence 继续、reconcile 或给出精确 attention；只有证据允许时才进入业务终态。
- 已提交的 repository 写操作不会因业务 step 重试而重复提交。
- 不存在“保守重做整个 step”的 blind replay 路径。
- READY 前 artifact closure 完整，READY 后后台优化不改变正式结果。
- Operation Runtime 不依赖具体业务模型或 capability 实现。

### 本阶段不做

- 不实现任意 DAG、动态脚本工作流或跨服务分布式事务框架。
- 不把 capability 内部按表并行提升成 operation step，除非它需要独立恢复和业务可见进度。

## 8. Phase 5：Business Vertical Slices

### 目标

按业务价值和依赖顺序建立新的正式主路径。每个 Slice 通过后再进入下一 Slice，不等待所有功能一次完成。

所有 Slice 的对象、状态、占用、derived projection 与 freeze point 遵守 [Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)。

### Slice 5A：Upload Preview

```text
HTTP
  -> Workspace application use case
  -> source/snapshot
  -> comparison/risk
  -> surface/bundle
  -> artifact closure
  -> preview response
```

重点验证 capability 组合、bundle contract 和同步/异步边界。该 Slice 不依赖 Repository 写路径，是首个端到端架构验证点。

Upload/Preview 产生 immutable UploadRevision、PreviewResult 与 full-row table facts；SnapshotTableArtifact 仅在未接受的 current Preview 或 active SubmitAttempt 期间持久 pin，T1 转移 pin responsibility，Attempt 终态释放。

退出条件：正式 preview bundle 可由新前端 loader 打开，golden comparison/risk/digest 一致，API 不内联 capability 算法。

### Slice 5B：Submit Acceptance and Finalize

```text
Workspace submit gate
  -> reject NO_CANONICAL_CHANGE before Attempt
  -> persist SubmitAttempt + Operation/outbox (T1)
  -> build/reuse one RepositoryImportArtifact
  -> Repository SubmitImport
  -> poll/checkpoint
  -> full readback VERIFIED evidence (T2)
  -> create Submission/finalize Workspace (T3)
```

重点验证跨服务幂等、事务边界、补偿和 worker takeover。

退出条件：重复请求、worker crash 和 Repository Service restart 不产生重复 submission/ref/commit；Repository 成功前不存在 Submission；unknown effect 不解锁或 blind replay。该 slice 通过 capture gate 后立即捕获首份 accepted vNext performance baseline。

### Slice 5C：Review

实现直接 approve、reject、withdraw、return 和 mutable ref release；不建设单独 start-review 动作或中间审核状态。领域状态变化归 Submission/Workspace，Repository Service 只执行通用 ref 操作。

退出条件：状态机、权限、幂等和 ref release conflict 全部由自动测试覆盖。

### Slice 5D：Archive

实现从 approved Submission facts 派生 CandidateProjection、confirmation/anomaly resolution、纯读 PreviewArchivePlan 与 StartArchive execute gate。Preview 不持久化、不冻结；Start 才重新校验并冻结 ArchivePlan。使用 immutable BaselineNode + BaselineHead，不建设 batch。业务侧决定 target commit，Repository Service 仅执行 main ref CAS。

退出条件：并发 archive、base main conflict、重复执行和部分失败有确定结果，业务与 repository operation 可关联审计。

### Slice 5E：History Compare

实现 immutable commit resolve、repository read/native diff、comparison/risk/surface/bundle 和只读 operation。

退出条件：history compare 不修改 Workspace/Submission/Archive 状态，远程 repository read 与本地 oracle 等价。

### Phase 5 整体退出条件

- 完整 `upload -> submit -> review -> archive -> next baseline -> history compare` journey 通过。
- API、application、domain、capability、operation 和 repository 边界符合架构测试。
- 新主路径不依赖旧业务模块和统一 StateStore。

## 9. Phase 6：Rust Coverage Expansion and Compute Optimization

### 目标

在 Phase 3 首批 Rust production kernel 的基础上，根据完整业务 journey profile 扩大 Rust 覆盖并深度优化数据路径。Phase 6 不是首次引入 Rust，也不机械替换所有 Python/Polars 实现。

Provider route 遵守 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)，收益声明遵守 [Performance Measurement and Baseline](../contracts/performance-measurement-and-baseline.md)。

### 推荐顺序

1. 复核 Phase 3 scalar/digest、projection、standard diff 和 records 的端到端收益与内存表现。
2. 优化 Arrow zero-copy、batch size、materialization 次数和 Rust/Polars 线程预算。
3. 根据 fixtures 和 profile 引入 ordered preparation、classification、interval 和 move。
4. 根据 risk records 规模评估 Rust facts extraction，规则定义和业务决策继续保留 Python。
5. 最后单独评估 SQL streaming parser，不按当前 Python parser 机械翻译。

### 实现形态

```text
gateway-compute-core       Rust algorithms
gateway-compute-python     PyO3/Arrow adapter
gateway-compute-worker     artifact-based worker/CLI
```

- 同步低延迟路径使用 PyO3 + Arrow 粗粒度调用。
- 大型异步任务可以由 Rust worker 消费 Parquet/Arrow artifact。
- Python 保留 domain、application、Operation Runtime、ruleset selection 和频繁变化的业务 policy。
- Risk 的大规模 facts extraction 可进入 Rust，规则定义和小规模决策优先保留 Python。

### 进入条件

- 目标阶段有独立 profile，且占正式请求 CPU 或内存的显著比例。
- Python reference oracle 和跨语言 golden fixture 已稳定。
- Arrow/Parquet 和 scalar/digest contract 已版本化。
- Phase 3 首批 Rust provider 已通过真实纵切验证，不存在尚未收口的基础 FFI/打包问题。
- Slice 5B 已按 measurement contract 产生 accepted vNext baseline；没有 baseline 不得声明 coverage/provider 优化收益。

### 退出条件

- Rust 与 Python reference 的 facts、records、排序和 digest 一致。
- Kernel 和端到端 benchmark 均达到预设收益门槛。
- Panic、超时、取消、内存不足和 native crash 有明确失败边界。
- Rust provider 可通过 feature flag 回退到 reference provider。

### 本阶段不做

- 不按 Python 文件、class 和 dataclass 一一翻译 Rust。
- 不通过逐行 PyO3 调用传递百万个 Python object。
- 不长期维护两个同等权威的正式算法实现；Python 逐步转为小数据 oracle/fallback。

## 10. Phase 7：Concurrency, Cache and Performance

### 目标

在完整正确路径稳定且首份 vNext baseline 已 accepted 后，根据同一可比 series 的 measurement 引入受控并行、cache 和 provider 优化。

### 主要工作

- Capability 内部按表/partition 并行和确定性汇总。
- Operation 固定 fan-out/fan-in，仅用于需要独立恢复的 pair/task。
- Repository Service 单 repository writer 和节点级资源队列。
- Snapshot table、projection、comparison core、risk 和 artifact cache。
- Cache authority、promotion、validation、eviction 和 cleanup。
- Polars LazyFrame/streaming、Arrow zero-copy、Rust Rayon 和 I/O pipeline 优化。
- 建立统一并发预算，控制 Operation worker、Python pool、Polars/Rayon 和 Repository worker。

### 退出条件

- 并行模式与串行模式产生相同正式结果和 digest。
- Cache miss/corruption 只影响性能，不改变业务事实。
- p50/p95、吞吐、峰值内存和磁盘放大满足目标。
- 过载时系统有背压，不通过无限线程/任务扩张维持吞吐。

## 11. Phase 8：Shadow Traffic and Cutover

### 目标

在不破坏正式业务状态的前提下验证新路径，并按风险从低到高切换流量。

### 切换顺序

1. 离线 language-neutral fixture/canonical correctness 对照，以及独立 vNext measurement。
2. 只读 shadow：catalog、history resolve、comparison。
3. Upload preview shadow，结果不对用户生效。
4. Upload preview 正式切换。
5. Submit 双重验证但单写，禁止两个系统同时提交 repository 写入。
6. Submit/Review 正式切换。
7. Archive plan preview shadow。
8. Archive mainline CAS 正式切换。

### 规则

- Shadow 比较使用规范化结果，不要求保留旧 host path、cache key 或 bundle layout。
- Shadow 只对照 canonical correctness 和明确 intentional change；不运行 legacy-vs-vNext 性能门禁。
- 任何写路径只能有一个 system of record 和一个 writer owner。
- 每次切换有明确 feature flag、回滚点和数据兼容说明。
- 回滚不得依赖删除新系统已经提交的 immutable commit。

### 退出条件

- 新路径承载全部正式旅程，旧路径不再写业务事实。
- Shadow 差异全部有结论。
- 回滚演练和数据一致性检查通过。

## 12. Phase 9：Cleanup and Production Hardening

### 目标

删除临时兼容边界，完成生产运维、容量和恢复能力，使目标架构成为唯一正式实现。

### 主要工作

- 删除旧 Flow、统一 StateStore、Dolt local adapter、重复 DTO 和路径字段。
- 从业务容器移除 Dolt 二进制和 repository volume。
- 删除不再使用的 feature flag、shadow writer 和 compatibility artifact。
- 完成 Repository Service backup/restore、GC、Dolt upgrade/rollback 和容量 runbook。
- 完成 operation backlog、lease、cache、artifact、repository disk 和业务 journey observability。
- 执行故障注入、灾难恢复、滚动升级和安全审计。
- 更新所有架构、contract、部署和运维文档。

### 退出条件

- 目标架构是唯一正式主路径。
- 业务容器不执行 Dolt 命令、不访问 repository 本地目录。
- API 不拥有业务状态机，Domain 不依赖 infrastructure。
- Operation 可跨进程恢复，Repository 写操作可审计和恢复。
- 完整 journey、故障注入、恢复演练、性能和安全验收通过。

## 13. 跨阶段工作流

### 13.1 Contract 变更

任何跨模块或跨语言 contract 变更必须：

1. 更新 schema/version。
2. 更新 golden fixture。
3. 更新 Python/Rust/Repository contract tests。
4. 说明 cache/digest compatibility。
5. 说明滚动升级期间的兼容窗口。

### 13.2 数据迁移

- Legacy Dolt migration/compatibility 是独立 cutover gate；本计划不预设迁移或不迁移结论。
- Gate 若选择不迁移，必须提供明确环境初始化和切换边界。
- Gate 若选择迁移，迁移器是独立一次性应用，不把 legacy schema 兼容写入新 domain。
- 迁移结果通过业务 ID、commit、artifact digest 和抽样 journey 验证；不得把 raw legacy commit 与 canonical vNext commit 当作同版本 state 直接比较。

### 13.3 可观测性

从 Phase 1 开始统一 correlation ID：

```text
request_id
business operation_id
repository_operation_id
repository_id/ref/commit
artifact digest
capability/provider/version
```

日志不携带敏感 row payload 和服务端私有路径。

### 13.4 安全

- Interface 执行用户认证和业务授权。
- Repository Service 执行 service/tenant/repository 授权和资源隔离。
- Import、SQL、archive 和 artifact 解压从第一版就设置配额，不作为生产化阶段才补的功能。

## 14. 全局 Definition of Done

一个阶段或纵切只有同时满足以下条件才算完成：

- 行为和 contract 测试通过。
- 架构依赖测试通过。
- 关键失败路径和幂等测试通过。
- 产物有 digest、diagnostics 和 owner。
- 没有新增 host path、隐式全局状态或跨层 DTO re-export。
- 初始 correctness route 有 component evidence；任何优化/回归性能结论都有 accepted vNext baseline 或容量数据支持。
- 文档、ADR、runbook 与实现一致。
- 新代码已接入正式入口或明确标记为未启用，不能长期处于无人使用的“已完成”状态。

## 15. 执行台账模板

每个 Phase/Slice 建议建立独立执行台账，至少记录：

```text
owner
scope
entry criteria
contract/ADR links
implementation PRs
test commands and results
benchmark dataset and results
manual verification
known differences
rollback point
exit criteria decision
```

台账只记录执行事实，不复制本文件的长期边界。阶段中出现的新架构决策必须回写总纲、专项 contract 或 ADR。
