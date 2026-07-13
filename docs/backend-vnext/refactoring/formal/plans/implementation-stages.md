# Backend vNext Refactoring Implementation Stages

状态：正式设计基线（Accepted Baseline）

本文把 [整体架构总纲](../architecture/architecture-and-refactoring-plan.md) 转换为可执行的重构阶段。阶段编号表示主要依赖顺序，不表示必须完成整个水平层后才能继续；每一阶段只建设下一条业务纵切所需的最小能力，并保持可运行、可验证和可回退。

## 1. 实施原则

### 1.1 从头实现的含义

“从头重构”指新代码不继承旧模块边界和内部 DTO，不代表重新猜测业务语义：

- 旧代码只作为业务行为、边界 case、性能和人工体验的 oracle。
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
- Rust、并行、cache 和 provider 优化不能先于 contract、oracle 和 benchmark。
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

固定新实现必须保持或有意改变的业务语义、数据契约和性能基线，建立可重复对照环境。

### 主要工作

- 列出正式业务旅程：upload、preview、submit、review、archive、next baseline、history compare。
- 固定 Workspace、Submission、Archive/Batch 的状态转换、generation gate、权限和失败语义。
- 建立 source package、SQL dump、普通表、有序表、空表、无 key 表、schema change 和异常输入 fixture。
- 固定 Snapshot、Comparison、Ordered Records、Risk、Surface、Bundle 的 golden payload、Parquet schema 和 digest。
- 记录 parse、materialize、projection、comparison、risk、surface、Parquet、Dolt import/readback 的分阶段性能和峰值内存。
- 决定是否迁移旧数据；如果不迁移，记录正式不兼容边界。
- 记录当前人工验收路径和已知旧 bug，不把旧 bug 自动作为新 contract。

### 交付物

- Versioned fixture manifest。
- Golden contract/digest 数据集。
- Flow journey baseline report。
- Performance baseline report。
- Legacy behavior audit 和 intentional change 清单。

### 退出条件

- fixture 可在隔离环境重复生成相同输入 digest。
- 关键输出可做结构化比较，不依赖人工查看日志。
- 每个旧新差异可归类为 old bug、new bug 或 intentional change。
- 已明确数据迁移策略。

### 本阶段不做

- 不修改正式流量。
- 不开始大规模目录搬迁。
- 不根据单次 benchmark 决定 Rust 或并行策略。

## 4. Phase 1：Contracts and Architecture Skeleton

### 目标

固定语言无关的语义边界，建立新代码隔离区、依赖方向和最小 bootstrap。

### 主要工作

- 建立 shared kernel：identifier、scalar、canonical serialization、digest、diagnostics。
- 分类 interface、application、capability 和 repository wire contracts。
- 固定 ArtifactRef、artifact closure、records Parquet 和 table access contract。
- 固定 Operation、Step、checkpoint 和 error taxonomy。
- 固定 Repository ID/ref/commit、CAS、artifact 和 remote operation contract。
- 建立目标目录、依赖检查和禁止旧模块 import 的架构测试。
- 建立 Python package、Rust workspace、格式化、静态检查、测试和构建骨架；完成 PyO3、Arrow round-trip、panic/error mapping 和目标平台 wheel/image 的最小验证。
- 为 Phase 3 首批 Rust production kernel 固定 scalar、ordering、digest、Arrow/Parquet schema 和 Python reference oracle 约束。
- 补充 transport、artifact transfer、persistence、Python/Rust boundary 等 ADR。

### 交付物

- 新架构 package skeleton。
- Versioned contract modules/schema。
- Architecture test suite。
- Python/Rust minimal interop spike，不包含正式业务算法。
- Rust provider contract、构建和失败映射基线。
- 第一批 ADR。

### 退出条件

- 新入口可以启动且不 import 旧业务模块。
- Contract 可以独立序列化、反序列化和版本检查。
- Python/Rust 对 scalar、Arrow schema 和 digest fixture 有一致解释。
- 已证明 Python 可以通过粗粒度 PyO3/Arrow 调用 Rust，并将受控 failure 映射为 capability error。
- 依赖违规会在 CI 中失败。

### 本阶段不做

- 不提前建立通用 workflow/DAG framework。
- 不创建 `common`、`helpers`、`utils` 作为未归属代码容器。
- 不实现完整业务流程。

## 5. Phase 2：Repository Service Foundation

### 目标

建立独立、通用、容器化 Repository Service 的最小读写边界，使业务系统不再依赖 Dolt CLI 和仓库本地路径。

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

写侧包含单 repository writer lease、幂等键、operation journal、readback、审计和确定错误分类。

### 2D：客户端与部署

- `FakeRepositoryClient` 用于 domain/application tests。
- `LocalRepositoryClient` 用于早期 contract integration。
- `RemoteRepositoryClient` 用于正式容器访问。
- 大文件使用对象存储引用、预签名 URL 或流式传输，不进入普通 JSON。
- 建立持久 volume、Dolt 版本固定、健康检查和最小 backup/restore。

### 交付物

- Repository Service image。
- Local/Remote client SDK。
- Local/Remote contract test suite。
- Repository operation、并发 CAS 和 restart recovery tests。
- 最小运维 runbook。

### 退出条件

- 业务侧仅使用 repository ID/ref/commit/artifact/operation ID。
- Local 与 Remote 实现对相同 fixture 返回等价 catalog、rows、diff 和 commit。
- 重复 import/CAS 请求有确定幂等结果。
- 服务重启不会产生无法判断的半完成写入。

### 本阶段不做

- Repository Service 不解释 SnapshotSummary、Comparison、Risk 或业务 hidden table。
- 不实现业务 candidate selection 和 archive gate。
- 第一版不追求多节点共享写入；先固定单 repository writer ownership。

## 6. Phase 3：Capability Foundation

### 目标

建立可独立调用、独立测试、无环依赖的 capability 主链，并产出首个业务纵切需要的事实和 artifact。

### 实现顺序

```text
table_rules
  -> table_projection
  -> snapshot_materialization
  -> comparison
  -> risk_evaluation
  -> business_projection
  -> surface_assembly
  -> bundle_assembly
```

Repository import 在业务系统侧收敛为 Repository Client 调用和业务 readback validation，不重新拥有 Dolt lifecycle。

### 每个 capability 的固定步骤

1. 定义或收口 `contracts.py`，固定 scalar、ordering、digest 和 Arrow/Parquet 边界。
2. 实现只覆盖小规模语义和边界 case 的 Python reference oracle。
3. 通过 Phase 0 golden/property fixtures，记录基线 profile 和 implementation route。
4. 对满足 ADR 0001 门禁的稳定热点，直接实现 Rust production provider；其他能力使用 Python/Polars 验证语义。
5. 实现 artifact 输入输出、closure、失败映射和受控 provider fallback。
6. 增加独立 kernel/end-to-end benchmark 和 diagnostics。

### 重点调整

- 提取 `table_projection`，消除 snapshot 对 comparison digest 的反向依赖。
- 提取最小 `table_access` protocol，不把完整 Snapshot 泛化成通用表模型。
- 消费方只依赖 capability public contract，不 import 内部 `models.py`、planner 或 builder。
- 风险规则先保留 Python reference；大规模 row facts extraction 与规则决策分离。
- 第一批 Rust production 候选为 scalar/digest、table projection、standard hash diff、records 和计算结果的 Arrow/Parquet materialization。
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
- Capability 不包含 Workspace、Submission、Archive、History request 等 flow identity。
- 依赖图无环且无内部实现越界。

### 本阶段不做

- 不为每个 capability 同时维护 Python、Rust、Dolt native 多个同等权威的正式 provider。
- 不要求尚未满足 Rust 进入条件的 capability 为语言统一而使用 Rust。
- 不引入无 benchmark 依据的表级并行和 cache。

## 7. Phase 4：Durable Operation Runtime

### 目标

建立可持久化、可重试、可接管的最小执行运行时，为 submit、archive 和 history 等耗时流程提供可靠执行机制。

### 主要工作

- 持久化 operation/step store 和 optimistic version。
- 原子 claim、lease、heartbeat、timeout takeover。
- 稳定 `operation_kind + step_name -> JobDefinition handler` 注册。
- Step output 只保存稳定 DTO、business ID、artifact ref、repository operation ID 和 checkpoint。
- 大型 Comparison/Risk/Surface 结果必须通过 artifact/checkpoint 重载，不能依赖 Python 闭包。
- 实现 retry、cancel、supersede、final failure 和 READY closure。
- 建立 Repository remote operation 的 submit/poll/checkpoint 模式，不占用线程阻塞等待。
- 第一版保持顺序 step；只预留固定 fan-out/fan-in contract。

### 交付物

- Durable Operation Runtime。
- JobDefinition registry。
- Worker entrypoint。
- Crash、lease、retry、duplicate delivery 和 cancellation tests。

### 退出条件

- 任意 step 后终止 worker，另一 worker 能继续或给出确定最终失败。
- 已提交的 repository 写操作不会因业务 step 重试而重复提交。
- READY 前 artifact closure 完整，READY 后后台优化不改变正式结果。
- Operation Runtime 不依赖具体业务模型或 capability 实现。

### 本阶段不做

- 不实现任意 DAG、动态脚本工作流或跨服务分布式事务框架。
- 不把 capability 内部按表并行提升成 operation step，除非它需要独立恢复和业务可见进度。

## 8. Phase 5：Business Vertical Slices

### 目标

按业务价值和依赖顺序建立新的正式主路径。每个 Slice 通过后再进入下一 Slice，不等待所有功能一次完成。

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

退出条件：正式 preview bundle 可由新前端 loader 打开，golden comparison/risk/digest 一致，API 不内联 capability 算法。

### Slice 5B：Submit Acceptance and Finalize

```text
Workspace submit gate
  -> persist Submission + operation/outbox
  -> Repository SubmitImport
  -> poll/checkpoint
  -> readback validation
  -> finalize Submission/Workspace
```

重点验证跨服务幂等、事务边界、补偿和 worker takeover。

退出条件：重复请求、worker crash 和 Repository Service restart 不产生重复 submission/ref/commit。

### Slice 5C：Review

实现 start review、approve、reject、withdraw 和 mutable ref release。领域状态变化归 Submission/Workspace，Repository Service 只执行通用 ref 操作。

退出条件：状态机、权限、幂等和 ref release conflict 全部由自动测试覆盖。

### Slice 5D：Archive

实现 candidate、confirmation、anomaly resolution、selection、dry run 和 execute gate。业务侧决定 target commit，Repository Service 仅执行 main ref CAS。

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

在完整正确路径稳定后，根据 benchmark 引入受控并行、cache 和 provider 优化。

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

1. 离线 fixture 和 benchmark 对照。
2. 只读 shadow：catalog、history resolve、comparison。
3. Upload preview shadow，结果不对用户生效。
4. Upload preview 正式切换。
5. Submit 双重验证但单写，禁止两个系统同时提交 repository 写入。
6. Submit/Review 正式切换。
7. Archive dry run shadow。
8. Archive mainline CAS 正式切换。

### 规则

- Shadow 比较使用规范化结果，不要求保留旧 host path、cache key 或 bundle layout。
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

- 如果决定不迁移旧数据，必须提供明确的环境初始化和切换边界。
- 如果需要迁移，迁移器是独立一次性应用，不把 legacy schema 兼容写入新 domain。
- 迁移结果通过业务 ID、commit、artifact digest 和抽样 journey 验证。

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
- 有基准或容量数据支持性能结论。
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
