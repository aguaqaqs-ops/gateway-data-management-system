# Implementation Boundary

本文定义 backend vNext 的代码落点、模块依赖和实现阶段边界。它是长期实现约束，不描述某一次临时 benchmark 的具体执行步骤。

## 代码落点

backend vNext 的正式代码放在现有后端目录内的新隔离包：

```text
gateway-data-management-system/backend/backend_vnext/
```

不创建与 `gateway-data-management-system/backend/` 平级的新 backend 目录。项目后端工具、测试、虚拟环境和运行约定仍以现有 backend 目录为准。

建议初始包结构：

```text
backend_vnext/
  __init__.py
  core/
    identifiers.py
    scalar_encoding.py
    row_digests.py
  contracts/
    submit.py
    repository.py
    versions.py
  artifacts/
    records.py
    closure.py
  cache/
    comparison_core.py
    validation_status.py
  capabilities/
    snapshot_materialization/
      source_package.py
      sql_source.py
      sql_parser.py
      materializer.py
      repository_ref.py
    repository_import/
    comparison/
      engine.py
      native_provider.py
      records_builder.py
      facts_builder.py
      ordered/
        policy.py
        preparation.py
        classifier.py
        replay.py
        records.py
        digest.py
    risk_evaluation/
    surface_assembly/
    bundle_assembly/
  repository_server/
    registry.py
    registry_sqlite.py
    ref_session.py
    catalog.py
    table_reader.py
    table_export.py
    table_cache.py
    dolt_backend.py
  benchmarks/
    repository_import/
    workflow_ladder/
  testing/
```

## 正式公共边界

`core` 承载跨模块共享原语，例如 identifier 归一化、scalar encoding、row digest 和稳定 digest helper。业务 capability 可以 re-use 这些原语，但不应通过 snapshot/comparison 模型模块间接 re-export。

`contracts` 承载 flow-neutral DTO、port 和跨层默认版本常量。submit DTO、repository port 等正式调用方应从 `backend_vnext.contracts` 或具体 `contracts.*` 模块导入。

`flows` 只承载业务编排入口、flow input/result、worker/runner；不得作为 contract DTO 或共享原语的 re-export 层。

upload preview bundle 组装是正式能力，落在 `backend_vnext/capabilities/upload_preview_bundle/`。它从 vNext flow / operation / artifact 输出生成正式 preview index、surface、risk、projection、snapshot/diff Parquet bundle，并负责 bundle artifact closure；`api` 与 `flows` 只能编排调用它，不应内联 row artifact 写入、closure 校验或 sidecar payload 拼装细节。

表格展示默认值落在独立的 `backend_vnext/capabilities/table_presentation/`。该能力只从 raw descriptor、effective diff key 和自身 versioned registry 生成展示投影；不得放入 comparison/table rules/risk，也不得依赖旧 `infrastructure.sql_ingestion`。Upload delivery 只消费完整投影，不自行猜测列宽、隐藏或冻结规则。

## 旧模块依赖规则

新架构代码完全不依赖旧业务模块。

禁止从以下旧业务模块 import：

```text
compare
comparison_core
comparison_surface
history_comparison
preview
repository_service
risk
workbench
api
application
domain
infrastructure
observability
```

旧实现只作为：

- 行为参考。
- 性能问题样本。
- 业务语义样本。
- 测试 fixture 或人工对照来源。

旧实现不是新架构的模块边界、状态机、ID/hash、artifact 结构或 cache contract 的依据。

如果确实需要复用旧 adapter、旧工具函数或旧数据结构，必须先讨论并在设计文档中记录：

```text
reuse_target
reuse_reason
why_not_reimplement
dependency_surface
exit_plan
```

未经讨论，不在旧实现上包一层 adapter 作为 vNext 正式能力。

## 允许依赖

新包可以依赖：

```text
Python standard library
backend/.venv 中已有第三方库
Dolt CLI / dolt sql-server
MySQL client
pytest / test tooling
```

如果新增第三方依赖，应先讨论其必要性、替代方案和部署影响。

## 模块分层

第一版按 capability 边界实现最小纵切。

```text
core
  identity, digest, result, diagnostics, version constants

artifacts
  manifest, artifact refs, local artifact store, staging metadata, records artifact, artifact closure

cache
  cache registry, validation status, comparison core cache, promotion/cleanup

capabilities.snapshot_materialization
  SourcePackage entry resolution, SqlDumpSource parsing, RepositoryRef materialization, Snapshot, SnapshotSummary, SnapshotTableReader, scalar_encoding

capabilities.repository_import
  import artifact builder, provider runner, Dolt readback validation

capabilities.comparison
  ComparisonPlan, ProjectionTable, SnapshotTableCompare, DoltNativeProvider, OrderedTableCompare, ComparisonFacts

capabilities.risk_evaluation
  RiskFacts, RiskRuleRegistry, RiskEvaluation, RiskReport, RiskAnnotationArtifact

capabilities.surface_assembly
  ComparisonSurface, SurfaceTable projection, ref validation, surface digest

capabilities.table_presentation
  raw descriptor column presentation, versioned display registry, preview column contract

capabilities.bundle_assembly
  ComparisonBundle, artifact closure, ref rewrite, Workbench adapter

repository_server
  ref session, catalog, table reader/export, repository-local technical cache

benchmarks.repository_import
  dataset resolver, benchmark matrix runner, summary/report writer

benchmarks.comparison_provider
  后续 Dolt native / snapshot compare / cache path benchmark runner
```

依赖方向：

```text
benchmarks -> capabilities -> repository_server -> core
benchmarks -> capabilities -> artifacts -> core
```

反向依赖不允许。Capability 不依赖 benchmark。Core 不依赖 artifact、repository_server 或 capability。repository_server 不依赖 flow/operation/business modules。

## Implementation Sequence

第一版实现建议按“基础模型 -> 独立 capability -> flow 串联”的顺序推进。详细模块级计划、每阶段完成标准和参考文档见 `implementation-plan.md`；本节只保留长期边界摘要。

阶段：

1. `core`：Result、Error、Diagnostics、canonical serialization、digest、version constants。
2. `artifacts`：本地 artifact store、manifest、artifact ref、records artifact、closure。
3. `capabilities.snapshot_materialization`：先细化 stable entrypoint API，再实现 SQL dump path；该阶段不依赖 repository_server。
4. `repository_server`：本地 Python 模块先行，提供 `RepositoryTableAccessProvider`、catalog、reader/export、local technical cache；未来再容器化为网络 API 或 Unix socket。
5. `capabilities.snapshot_materialization.repository_ref`：通过 repository_server 把 repository ref 归一化为 Snapshot/Summary/TableSet。
6. `capabilities.repository_import`：整理 benchmark 中已验证的 provider primitives，正式 readback/catalog/export 尽量复用 repository_server。
7. `capabilities.comparison`：普通表 compare、projection、records artifact、cache handoff 接口。
8. `capabilities.risk_evaluation`：hardcoded registry 第一版，structural/standard/degraded/ordered placeholder。
9. `capabilities.surface_assembly` / `bundle_assembly`：thin core，闭合 artifacts。
10. `flows` / `operations`：在 capabilities 可独立测试后再串联业务流程；进入 flow 前明确 operation persistence。
11. 后续扩展：Dolt native provider、ordered diff、formal cache registry、provider benchmark。

规则：

- 每个 capability 开始编码前，先细化该 capability 的 stable entrypoint API 形状。
- 涉及 artifact 的 capability，先明确本地 artifact layout、manifest、digest 和 cleanup 规则。
- ordered diff 实现前先落最小 fixture。
- flow/API 集成前先明确 operation persistence、step diagnostics 和 READY artifact closure。
- Benchmark 不维护独立业务逻辑；正式 capability 落地后 benchmark 应反向调用正式能力。
- repository_server 不阻塞纯 SQL parser/materializer，但应早于所有 repository-backed capability。

## Capability Entrypoint Boundary

Capability 可以有多个稳定 entrypoint。Flow-facing entrypoint 可以组合更小的子能力，但可复用、可测试、输入输出稳定的子能力不应被无必要地藏成私有黑盒。

规则：

- Capability entrypoint 必须是 flow-neutral：不读取或修改 Workspace、Submission、Preview、History request 等业务状态。
- Flow 可以选择调用组合入口，也可以直接调用稳定子入口；两者在同一输入、版本和 policy 下应得到等价结果。
- 子入口必须显式声明输入、输出、contract version、digest 语义和 diagnostics。
- Source resolver、document resolver、parser、projector、validator、canonicalizer、artifact writer 这类通用能力优先暴露为可单独测试的子入口。
- Provider 内部启发式、临时优化、私有缓存布局和算法中间状态可以保持私有，不强行公开。
- Benchmark、测试和未来迁移到其他项目时，应优先调用正式 entrypoint，而不是复制 capability 内部实现。
- 如果某个子能力开始被两个以上 flow、benchmark、provider 或测试场景直接需要，应评估提升为 stable entrypoint。

示例：

```text
SourcePackage entry resolution
  -> SourceDocumentRef

SqlDumpSource resolution
  -> SqlDumpSource

SqlDump parsing / materialization
  -> Snapshot + SnapshotSummary + SnapshotTableSet
```

其中 `/sql/dbcfg.sql` 是当前项目 SourcePackage 的业务约定；SQL dump parser 是通用能力，应能直接消费 `SqlDumpSource`，也能被 `SQL_FILE`、`SQL_GZ`、测试 fixture 或其他项目复用。

## 本轮 Benchmark 的实现边界

Repository import benchmark 可以先实现最小能力集：

```text
SourcePackage / SqlDumpSource
  -> SnapshotSummary / SnapshotTableReader
  -> RepositoryImportArtifact
  -> Dolt provider import
  -> commit
  -> readback validation
  -> summary.json / report.md
```

本轮不实现：

```text
正式 cache registry
operation state machine
upload / submit / history compare 业务 flow
projection table cache
comparison contract 完整实现
前端 API
```

这些能力后续应在当前包结构内扩展，不要求推倒 benchmark 的最小纵切。

## 后续 Comparison Provider 边界

`DOLT_NATIVE` 和 `ORDERED_TABLE_COMPARE` 都是 `capabilities.comparison` 的 provider 子模块。

规则：

- `providers.dolt_native` 只能在 repository-backed comparison context 存在时作为优化路线。
- `providers.dolt_native` 不直接产出业务 cache value；必须通过 `native_diff_canonicalizer` 输出 canonical `ComparisonFacts + ComparisonRecordsClosure`。
- `providers.ordered_table_compare` 只消费 projection-ready rows 和 ordered policy，不调用 repository_server 或 Dolt native。
- `capabilities.comparison.ordered` 内部按 policy、preparation、classifier、replay、records、digest 拆分，便于未来独立修改规则或替换算法。
- IEC104 ordered family 的 `gid/no/pseudo blank/table_processing_mode` 规则应集中在 `ordered.policy` 和 `ordered.preparation`，不要散落在 provider 主流程。
- Provider benchmark 应落在后续 `benchmarks.comparison_provider` 或等价目录，且调用正式 capability，不维护独立 diff/canonicalization 实现。
- Provider 子模块不得 import flow、operation、risk、surface、bundle 或旧业务模块。

## 测试边界

每个模块需要有独立测试入口。

建议测试层级：

```text
unit:
  digest, manifest, SQL parser, table descriptor, artifact writer

contract:
  Snapshot digest stability
  RepositoryImportArtifact manifest stability
  provider input/output contract

integration:
  Dolt provider import + readback validation
  benchmark runner small dataset
 ```

业务 SQL 数据不进入 git。真实业务数据由外部 dataset root 提供，benchmark 只记录 manifest 和 digest。

测试时请遵循以下约定：

- vNext 测试只跑 `gateway-data-management-system/backend/tests/backend_vnext/`，不要把 `gateway-data-management-system/backend/tests/` 作为新架构验证入口。
- 可提交的小 SQL fixture 只放在 `tests/backend_vnext/fixtures/minimal/` 和 `tests/backend_vnext/fixtures/regression/`。
- 原始业务输入只放在 `tests/backend_vnext/fixtures/external/` 或仓库外 dataset root，不进入正式测试资产。

## 收口标准

进入正式业务 flow 集成前，至少满足：

- 新包不 import 旧业务模块。
- Snapshot materialization 最小闭环可独立测试。
- Repository import provider runner 可独立测试。
- Benchmark runner 以 `summary.json` 为权威输出。
- 所有 Dolt import provider 都通过 readback digest validation。
- 失败能区分 parse、staging、import、commit、validation、cleanup phase。
