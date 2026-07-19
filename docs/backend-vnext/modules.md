# Target Modules

本文定义 backend vNext 第一阶段目标代码模块。实现硬约束见 `implementation-boundary.md`；本文件描述模块职责、依赖方向和第一轮 benchmark 所需的最小拆分。

## 包根

```text
gateway-data-management-system/backend/backend_vnext/
```

模块依赖方向：

```text
benchmarks
  -> flows
    -> operations
    -> capabilities
  -> capabilities
  -> contracts

flows
  -> operations
  -> capabilities
  -> contracts

capabilities
  -> artifacts
  -> contracts
  -> core

repository_server
  -> core

artifacts / contracts / operations / cache
  -> core
```

禁止反向依赖。禁止依赖旧业务模块。`repository_server` 不依赖业务 flow/capability，也不产出 Snapshot/Comparison 业务对象。共享原语默认落在 `core`，跨层 DTO、port 和 contract 版本默认落在 `contracts`。

## 模块列表

| Module | 职责 | 第一轮 benchmark 是否需要 |
| --- | --- | --- |
| `core` | digest、通用 result、diagnostics、稳定序列化、identifier/scalar/row digest 等跨模块共享原语。 | 必需 |
| `contracts` | flow-neutral DTO、port、跨层 contract/version 默认值。正式调用方从这里取 submit/repository contract，不从 flow 或 capability 兼容出口取。 | 必需 |
| `artifacts` | artifact manifest、artifact ref、本地 artifact store、staging metadata、records artifact、artifact closure。 | 必需 |
| `repository_server` / `dolt_repository` | repository-local registry、table catalog、row stream reader（primary row path）、optional export fast path、repository server table cache。独立 API/容器边界，不包含业务模型。 | repository-backed 能力前置；纯 SQL path 可暂缓 |
| `capabilities.snapshot_materialization` | 从 SourcePackage 中的 SQL document 或 repository ref 生成 Snapshot、Summary、TableDescriptor 和 TableReader。 | 必需 |
| `capabilities.composite_signal` | 解析可选 composite logic XML，绑定特殊装置测点并生成 `composite_signal_point` 派生表及 supplemental artifacts。 | 必需 |
| `capabilities.repository_import` | 生成 import artifact，执行 Dolt provider，commit，readback validation。 | 必需 |
| `benchmarks.repository_import` | dataset 解析、benchmark matrix、runner、summary/report。 | 必需 |
| `capabilities.comparison` | directed comparison、projection table、diff facts、comparison compute orchestration。Contract 见 `contracts/comparison.md`，实现设计见 `capabilities/comparison-compute.md`。 | 后续 |
| `capabilities.comparison.providers.dolt_native` | RepositoryRef -> RepositoryRef 的 Dolt native diff provider、raw diff canonicalization 和 fallback diagnostics。实现设计见 `capabilities/dolt-native-provider.md`。 | 后续 |
| `capabilities.comparison.providers.ordered_table_compare` | 有序表 position/move/interval diff provider。Contract 见 `contracts/ordered-diff.md`，实现设计见 `capabilities/ordered-diff-compute.md`。 | 后续 |
| `capabilities.risk_evaluation` | risk facts、ruleset、risk report、annotation artifacts。Contract 见 `contracts/risk.md`，实现设计见 `capabilities/risk-evaluation.md`。 | 后续 |
| `capabilities.business_projection` | comparison records/risk 到业务视图的身份挂载与 projection artifact；secondary-device 设计见 `capabilities/business-projection.md`。 | 后续 |
| `capabilities.project_identity` | 基于 materialized snapshot 的 flow-neutral 项目身份 assessment；不暴露原始身份行。 | 后续 |
| `capabilities.dataset_replacement` | 跨项目时构造不做实体配对的 table replacement facts 和 comparison-level risk。 | 后续 |
| `capabilities.surface_assembly` | comparison surface 组装、表级展示投影、ref validation、surface digest。Contract 见 `contracts/comparison-surface.md`。 | 后续 |
| `capabilities.bundle_assembly` | comparison bundle 组装、artifact closure、ref rewrite、bundle digest。Contract 见 `contracts/comparison-bundle.md`。 | 后续 |
| `cache` | cache registry、validation status、comparison core cache、promotion、cleanup。 | 后续 |
| `operations` | async operation runtime、step diagnostics、retry/cancel。 | 后续 |
| `flows` | upload/submit/review/history/archive 的业务编排适配层，只暴露 flow input/result/runner/worker；不作为 contract DTO 的兼容 re-export 层。正式 archive 入口位于 `backend_vnext/flows/archive.py`。 | 后续 |
| `benchmarks.workflow_ladder` | 真实三节点 ladder benchmark：upload -> submit -> approve -> archive -> history compare，默认以 `business_small_cut` 三份样本跑 smoke，并复用 repo refs / cache / repo readback。 | 后续 |

## core

职责：

```text
stable_sha256
canonical_json_bytes
content digest / manifest digest helper
contract version constants
Result / Error / Diagnostics primitives
canonical_identifier / scalar encoding / row digest primitives
```

不负责：

- SQL parsing。
- Dolt 调用。
- artifact 文件布局。
- 业务 flow。

测试重点：

- digest 稳定性。
- canonical serialization 稳定性。
- diagnostics 不包含敏感 payload 或 host-only identity。

## artifacts

职责：

```text
ArtifactManifest
ArtifactRef
LocalArtifactStore
RepositoryImportArtifact metadata
SnapshotTableArtifact metadata
RecordsArtifactManifest
ArtifactClosureManifest
```

规则：

- Artifact identity 由内容和 manifest 决定，不由 host path 决定。
- Local path 只能作为 runtime location。
- Manifest 必须能被 digest 校验。
- Records artifact 和 artifact closure 是 flow-neutral 支撑能力，可被 comparison compute、cache restore、bundle assembly 和测试复用。

第一轮 benchmark 中只需要本地 artifact store；远端存储、TTL 和 cleanup registry 后续再设计。

## capabilities.snapshot_materialization

职责：

```text
Source SQL parser
SourcePackage entry resolver
SqlDumpSource resolver
RepositoryRef materialization
Snapshot model
SnapshotSummary model
SnapshotTableDescriptor
SnapshotTableReader
scalar_encoding
raw CREATE TABLE retention
row/content digest
```

建议内部拆分：

```text
source_package
sql_source
sql_parser
materializer
repository_ref
summary
table_set
scalar_encoding
```

第一轮最小输入：

```text
SourcePackage with /sql/dbcfg.sql
or bare SQL benchmark input
DROP TABLE optional
CREATE TABLE
INSERT INTO ... VALUES ...
```

第一轮输出：

```text
Snapshot
SnapshotSummary
SnapshotTableReader
SnapshotTableDescriptor
raw_ddl_digest
```

规则：

- `SourcePackage` 是容器；SQL parser 只消费 `SqlDumpSource`。
- 当前业务输入只支持唯一 `/sql/dbcfg.sql`，不支持多个 SQL 文件合并。
- benchmark 裸 SQL 或 `.sql.gz` 输入必须通过 compat/test helper 显式进入，不作为正式业务 package contract。
- `SourcePackage` required entry resolution 和通用 SQL dump parser 必须是独立 entrypoint。
- `/sql/dbcfg.sql` 是当前项目的 SourcePackage 约定；SQL parser / materializer 不应依赖该路径。
- 测试、benchmark 或其他项目可以直接调用 `resolve_sql_dump_source`、`parse_sql_dump_source` 或 `materialize_sql_dump_source`。

后续扩展：

- Repository ref materialization via repository table access provider。
- Snapshot table artifact cache。
- Projection table cache 的上游输入。
- `scalar_encoding` 第一版位于 snapshot materialization 内，供 SQL、RepositoryRef、readback validation 和 comparison projection 复用；后续可下沉到 `core.scalar_encoding`。

repository ref materialization 规则：

- repository server 提供 `RepositoryRefSession`、catalog、table reader（primary row path）和 optional export fast path。
- `capabilities.snapshot_materialization` 负责把 repository table access 归一化为 Snapshot/Summary/TableSet。
- `SnapshotSummary` 生成时同一 ref 最多加载一次 catalog。
- comparison 不直接 list repository tables，只消费 SnapshotSummary/TableSet。
- `SnapshotTableReader` 是 repository-backed row access 的第一选择；调用方优先消费 row stream，再按需派生 snapshot、diff 或 artifact。
- 具体实现设计见 `capabilities/repository-ref-materialization.md`。

## capabilities.repository_import

职责：

```text
RepositoryImportPlan / Result
RepositoryImportArtifactBuilder
Dolt CLI wrapper
ProviderRunner
DoltReadbackValidator
Dolt server lifecycle
```

Provider：

```text
SQL_DUMP_REPLAY
SINGLE_TABLE_CLI_IMPORT
MULTI_TABLE_CLI_IMPORT
LOAD_DATA
PARQUET_IMPORT
DOLT_SERVER_BULK_LOAD
SERVER_SESSION_BULK_LOAD
```

规则：

- Provider 成功不等于 import 成功；必须 readback validation。
- `LOAD_DATA` 第一版固定经 `dolt sql-server` 路由。
- schema-backed import 是默认 contract。
- Provider 不知道 Workspace、Preview、Submission 等业务模型。

## benchmarks.repository_import

职责：

```text
DatasetResolver
DatasetManifestBuilder
BenchmarkMatrix
BenchmarkRunner
SummaryJsonWriter
MarkdownReportWriter
```

规则：

- 真实业务 SQL 不进入 git。
- `summary.json` 是权威结果。
- `report.md` 必须由 `summary.json` 生成。
- 性能排序只使用 validation passed 的结果。
- benchmark 不应长期维护独立 SQL parse、digest 或 table artifact 生成逻辑；正式 capability 落地后，benchmark 应反向调用正式能力。

benchmark 与正式能力关系：

```text
prototype code proven by benchmark
  -> capabilities.snapshot_materialization / repository_import
  -> benchmarks.repository_import
```

即先吸收 benchmark 中已验证的底层能力，再让 benchmark 作为薄调用层复用正式模块。

## 后续模块

### cache

后续负责：

```text
source_package_index_cache optional
source_snapshot_cache
snapshot_table_artifact_cache
projection_table_cache
comparison_core_cache
PROVISIONAL / CONTENT_VERIFIED / COMMIT_VALIDATED
promotion / eviction / cleanup
```

规则：

- cache 模块不选择业务 ruleset，不推进 flow 状态。
- `comparison_core_cache` 保存 neutral facts core 和 records closure。
- cache hit 必须通过 `artifacts.closure` 恢复为 operation-local refs。
- `PROVISIONAL` / `CONTENT_VERIFIED` / `COMMIT_VALIDATED` 等可信等级由 cache 模块表达。

第一轮 benchmark 不实现正式 cache registry。

### repository_server / dolt_repository

第一版以本地 Python 模块先行，未来再容器化为独立网络 API 或 Unix socket 服务。

后续负责：

```text
RepositoryRegistry
RepositoryTableAccessProvider
RepositoryRefSession
RepositoryTableCatalog
RepositoryTableReader
RepositoryTableExportArtifact
repository_server_table_cache
```

规则：

- 不产出 Snapshot、Comparison 或业务状态。
- 不依赖 Workspace、Submission、History request 等业务模型。
- repository_server table cache 是 repository-local 技术 cache，不等同于 backend vNext capability cache。
- repository-local registry 是 repository metadata/cache/scan 的持久化底座，v1 只承载技术元数据，不直接编码业务状态机。
- repository_server 内部可按 `registry`、`ref_session`、`catalog`、`table_reader`、`table_export`、`table_cache`、`dolt_backend` 等 technical capabilities 拆分。
- 本地模块 API 应按未来服务化边界设计，不暴露业务模型，不依赖 flow/operation。
- `open_ref()` read-only、pinned-to-commit，支持 timeout，语义幂等但不保证返回同一 session 对象。
- table reader 第一版输出 tuple + catalog column order，并负责补齐 Dolt/driver 省略的 NULL 字段。
- benchmark 中已验证的 Dolt CLI/server primitives 可作为实现参考，但正式 benchmark 应反向调用 repository_server/capability 能力。

### capabilities.comparison

后续负责：

```text
ComparisonInput
ComparisonPlan
ProjectionTable
ComparisonFacts
comparison_core_cache handoff
```

第一版 contract 已在 `contracts/comparison.md` 定义；实现设计见 `capabilities/comparison-compute.md`。

内部建议拆分：

```text
models
ruleset_contract
planner
projection
providers.snapshot_table_compare
providers.dolt_native
providers.ordered_table_compare
providers.hash_stream_compare
providers.sqlite_spool_compare
native_diff_canonicalizer
ordered.policy
ordered.preparation
ordered.classifier
ordered.replay
ordered.records
ordered.digest
digest
```

规则：

- Flow 负责选择 ruleset；comparison capability 只应用调用方传入的 `TableRulesetSnapshot`。
- 第一版 `TableRulesetSnapshot` 来源使用 hardcoded registry；registry 输出必须可序列化、可计算 digest，并保留未来切换配置文件的加载边界。
- Capability 只消费 SnapshotSummary / SnapshotTableSet / SnapshotTableReader，不直接消费 SourcePackage、SqlDumpSource、RepositoryRef 或 RepositoryImportArtifact。
- `artifacts.records` 负责 JSONL records artifact 和 manifest，comparison capability 只调用它。
- `artifacts.closure` 负责 records closure 和 cache-local 到 operation-local ref 恢复，flow 不手写 restore 逻辑。
- `cache.comparison_core` 负责 pair-level comparison core cache，comparison capability 通过接口调用；它不是 pair-total surface / bundle cache。
- 第一版优先实现 `SUMMARY_EARLY_EXIT`、`HASH_STREAM_COMPARE`、JSONL records artifact 和 cold correctness。
- SQLite spool、comparison core cache、projection cache、Dolt native、ordered diff、risk/surface assembly 分阶段接入。
- `DOLT_NATIVE` 只作为 provider 子模块，必须先归一化为 `ComparisonFacts + ComparisonRecordsClosure`，不能把 Dolt raw diff 暴露给 risk/surface/bundle。
- `ORDERED_TABLE_COMPARE` 只消费 projection-ready rows 和 ordered policy，不依赖 Dolt native，也不让 surface/bundle 定义 ordered 算法。
- ordered diff 实现应按 `contracts/ordered-diff.md` 保留 IEC104 family、gid/no、pseudo blank、table processing mode 和旧 ordered risk reason code；模块边界可优化，业务语义不降级。
- ordered diff 的规则集中在 `ordered.policy` / `ordered.preparation`，分类算法集中在 `ordered.classifier`；未来恢复 bounded LIS/backbone planner 时优先替换 classifier，不扩散到 records/risk/surface。

### capabilities.risk_evaluation

后续负责：

```text
RiskEvaluationInput
RiskRulesetSnapshot
RiskFacts extraction
RiskRuleRegistry
RiskEvaluation / RiskReport
RiskAnnotationArtifact
```

第一版 contract 已在 `contracts/risk.md` 定义；实现设计见 `capabilities/risk-evaluation.md`。

规则：

- Flow 负责选择 risk ruleset、artifact policy、cache policy 和展示/审核策略。
- 第一版 `RiskRulesetSnapshot` 来源使用 hardcoded registry；registry 输出必须可序列化、可计算 digest，并保留未来切换配置文件的加载边界。
- Capability 只消费 `ComparisonFacts`、可选 records access 和调用方传入的 `RiskRulesetSnapshot`。
- Capability 不计算 diff，不读取 SourcePackage/RepositoryRef/repository server，不负责 surface/bundle 组装。
- 第一版覆盖 structural、standard row、degraded 和 ordered unsupported review-required 风险。
- ordered table 完整语义风险在 `ORDERED_TABLE_COMPARE` provider 完成后补充。

### capabilities.surface_assembly

后续负责：

```text
ComparisonSurfaceAssemblyInput
SurfaceTable projection
surface ref validation / rewrite
surface_digest
surface diagnostics
comparison_surface_cache optional future
```

Contract 见 `contracts/comparison-surface.md`；实现设计见 `capabilities/surface-assembly.md`。

规则：

- Capability 只消费 `ComparisonFacts`、records closure、`RiskReport` 和 risk annotation closure。
- Capability 不计算 diff，不计算 risk，不读取 SourcePackage/RepositoryRef/repository server。
- Surface 不包含 preview token、submit binding、workspace/history state、host path 或 cache ref。
- 第一版只展开普通表、schema/degraded 和 risk refs；ordered table 只保留 extension。
- Dolt native provider 输出必须先归一化为 comparison/risk contract，再进入 surface。

### capabilities.table_presentation

负责 raw descriptor 到 `TablePresentation` 的确定性投影，包括列标题、类型、展示顺序、宽度、对齐、隐藏、冻结和 primary/diff key 标记。模块拥有独立 ruleset，不复用 comparison table rules，也不进入 `ComparisonSurface` 或业务 digest。正式契约见 `contracts/table-presentation.md`，实现设计见 `capabilities/table-presentation.md`。

### capabilities.bundle_assembly

后续负责：

```text
ComparisonBundle
bundle manifest
bundle artifact closure
bundle-relative ref rewrite
bundle digest
flow envelope helper optional
```

Contract 见 `contracts/comparison-bundle.md`；实现设计见 `capabilities/bundle-assembly.md`。

规则：

- Bundle core 是 flow-neutral artifact。
- Flow envelope 可引用 bundle，但不改变 surface/bundle core。
- 多 pair 只在 bundle 层组织；每个 pair surface 独立。
- 第一版不实现 bundle cache；后续可增加 flow assembly cache，作为交付层复用，不承接 pair-total 比较事实。

### operations

后续负责：

```text
operation state
step diagnostics
retry / cancel
writer lease orchestration
artifact closure before READY
current flow delivery materialization
```

第一轮 benchmark 只记录 runner diagnostics，不实现 operation runtime。

### flows

后续负责：

```text
upload preview
precommit warmup
submit acceptance
commit finalize
history compare
archive / promote
formal bundle/read-model delivery
```

第一轮 benchmark 不接入业务 flow。

在正式 upload/submit/history flow 完整实现之前，可以先保留一个很薄的 `flows.comparison_risk` 编排入口，负责串联 `comparison` 和 `risk_evaluation`，但它不承载业务状态机，也不替代后续业务 flow。

## 第一轮拆分结论

第一轮不需要为了未来完整系统继续拆得更细。当前最小拆分足以支持：

- 独立测试基础 model/digest/artifact。
- 独立测试 SQL snapshot materialization。
- 独立测试 repository import provider。
- 独立运行 benchmark。

cache、operation、业务 flow 可以在 benchmark 纵切稳定后继续扩展，而不是提前实现。

## 第一版最小实现切片

第一版业务可用闭环建议只实现：

```text
Snapshot materialization
  -> Comparison compute
  -> Risk evaluation without cache
  -> Thin surface assembly
  -> Bundle assembly core
```

第一版暂不实现：

```text
risk_evaluation_cache
comparison_surface_cache
flow_assembly_cache
ordered semantic diff
projection_table_cache / formal projection artifact cache
repository server export artifact cache
```

`repository_server_table_cache` 是例外：为避免 repository ref materialization / history compare 中 Dolt catalog、describe、count、table root metadata 反复 IO，第一版可以实现简化跨 session read-through/write-through 技术 cache。它不缓存业务 facts，不替代 Snapshot digest 校验，且第一版不实现 TTL、pin、eviction 或 export 大对象 cleanup。

需要补充设计后才能扩大范围：

- 前端正式 loader 需要与当前 surface/bundle contract 锁步升级。
- ordered table 需要 move、position、interval 语义展示。
- Dolt native provider 被证明能显著提升 RepositoryRef -> RepositoryRef 性能，需要进入默认 provider planning。
- projection artifact cache 被性能数据证明必要。
- repository_server_table_cache 开始缓存 export artifacts、大表文件或跨进程共享。
- repository_server_table_cache 在长时间运行环境中超过磁盘预算，需要 TTL/pin/cleanup。
