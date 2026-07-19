# Artifact 与持久化等级

本文定义 backend vNext 中 artifact 分类、持久化等级和 operation artifact closure 规则。

## 持久化等级

| 等级 | 名称 | 是否可丢失 | 说明 |
| --- | --- | --- | --- |
| L0 | Ephemeral / 临时态 | 是 | 内存对象或 operation 临时目录内容。 |
| L1 | Staged Durable / 已暂存持久态 | 否，除非明确过期 | 已可靠保存的输入或执行记录，可用于恢复、校验或重算。 |
| L2 | Business Truth / 业务事实 | 否 | 受业务状态机和审计保护的事实。 |
| L3 | Recomputable Cache / 可重算 Cache | 是 | 可删除、可重算的优化产物。 |

Cache 不是业务事实。Cache 缺失不得改变业务语义。

## Artifact 分类

| Artifact | 默认等级 | 是否业务事实 | 说明 |
| --- | --- | --- | --- |
| `SourcePackage` artifact | L1 | 否 | 用户上传或系统接收的原始多目录多文件输入包。 |
| `SourceDocumentRef` | L1 metadata | 否 | 指向 package 内某个可解析文档，例如 `/sql/dbcfg.sql`。 |
| `SubmitSourcePackage` artifact | L1 | 否 | submit acceptance 成功的必要输入。 |
| `PreviewInputBinding` | L1 | 否 | 证明 submit full package 可复现 preview-relevant input。 |
| immutable repository commit/ref | L2 | 是 | submit finalize、archive/promote 成功后的事实来源，内部包含 FINAL hidden summary table。 |
| hidden summary table | L2 | 是 | repository commit/ref 内的隐藏系统表，存放 FINAL SnapshotSummary 的 compare-ready facts；history compare / archive 只读读取。 |
| `SnapshotSummary` artifact/index | L0 / operation artifact / L3 | 否 | upload/preview 的 provisional 摘要或 operation-local index；FINAL 事实写入 hidden summary table，L1/L2 record 可保存 summary digest/ref metadata。 |
| `SnapshotTableArtifact` | L3 或 operation artifact | 否 | `SnapshotTable` 的物理承载，通常是 manifest + rows。 |
| `SnapshotRowsArchive` | L1 submit artifact | 否 | submit finalize 产出的自包含 snapshot rows archive，用于后续 FULL baseline 快速恢复；业务事实仍以 repository commit/hidden summary 为准。 |
| `RepositoryImportArtifact` | L0 或 operation artifact | 否 | 面向 Dolt import provider 的 staging 输入。 |
| `ProjectionTableArtifact` | L3 或 operation artifact | 否 | 由 SnapshotTable + table rules 派生的 compare-ready table，属于 comparison-derived artifact。 |
| `ComparisonRecords` artifact | L3 或 operation artifact | 否 | comparison capability 输出，可重算。 |
| `OrderedComparisonRecords` artifact | L3 或 operation artifact | 否 | ordered diff provider 输出的有序表 records，可重算，属于 comparison records extension。 |
| `ComparisonRecordsClosure` | operation artifact 或 L3 cache member | 否 | 绑定 ComparisonFacts 与 records artifacts 的闭合 manifest。 |
| `DoltNativeRawDiff` artifact | L0 / provider-local cache optional | 否 | Dolt native provider 的原始输出，只能用于 diagnostics 或 provider-local optimization，不能作为 comparison core cache value。 |
| `RiskReport` artifact | operation artifact 或 L3 cache member | 否 | risk evaluation 的可展示/可下载摘要，不是前端 surface。 |
| `RiskAnnotation` artifact | operation artifact 或 L3 cache member | 否 | 大量 risk annotations 的物理承载，可重算。 |
| `ComparisonSurface` artifact | operation artifact 或 L3 cache member | 否 | comparison/risk 输出的展示层结构，不包含 flow binding。 |
| `ComparisonBundle` artifact | operation artifact 或 flow assembly cache | 否 | 一个或多个 surface 及其 artifacts 的闭合交付单元。 |
| `WorkbenchBundle` / download bundle | flow assembly cache 或 operation artifact | 否 | 可下载/离线加载包。 |

## Retention / Cleanup

默认策略是“正式结果保留，临时态可清理”。

- L0 临时态包括 operation 临时目录、provider staging、server session workdir、socket 和 scratch files。cleanup 可以删除或回收这些资源，但前提是不会影响后续 READY / readback / diagnostics。
- L1 已暂存持久态包括 `SourcePackage`、`SubmitSourcePackage`、`PreviewInputBinding`、benchmark summary/report 等。它们默认保留到明确过期或人工删除。
- L2 业务事实包括 immutable repository commit/ref 和审核后业务状态。它们不得由 flow cleanup 自动删除，只能通过显式 repository GC 或外部 retention job 处理。
- L3 可重算缓存允许 TTL / pin / eviction，cleanup 可以异步执行，但不能改变业务事实。
- `RepositoryImportArtifact` 在 formal submit finalize 中属于 operation-local 运行产物。当前实现会保留 `run_dir` 和 `repository_path` 供诊断和后续 open/readback 使用，不能把它们当成会被自动清空的临时目录来理解。

## Source Artifact

Source artifact 负责证明系统收到过哪些原始输入。它不包含 parsed rows、comparison records 或 Dolt commit。

规则：

- submit acceptance 返回 `ACCEPTED` 前，`SubmitSourcePackage` 必须 L1 durable。
- upload preview 可按策略决定是否保存完整 source；如果不保存，submit full package 必须能通过 binding 复现 preview-relevant input。
- 当前业务 SourcePackage 是多目录多文件包；业务 materialization 消费唯一 `/sql/dbcfg.sql`，并可选消费 `/comps/logic/logics.xml` 对应的 `SourceDocumentRef`。
- 其他 package entries 只作为 source manifest 或未来 parser 输入记录；composite XML 通过独立 capability 生成 `composite_signal_point` SnapshotTable。
- Source artifact 缺失不是 cache miss，除非已按过期策略显式释放。

## SnapshotTableArtifact

`SnapshotTableArtifact` 是 `SnapshotTableDescriptor + rows` 的物理承载。

建议 manifest：

```text
SnapshotTableArtifactManifest:
  artifact_contract_version
  snapshot_digest
  table_name
  descriptor
  row_file_refs
  row_format
  compression
  row_materialization_profile
  artifact_content_digest
  created_at
  diagnostics optional
```

第一版推荐：

```text
manifest + Parquet rows
```

原因：

- 适合 summary、comparison、bundle 和 Polars/Python 读取。
- 压缩和列式读取对大表友好。
- Dolt import staging 可以从它转换为 CSV/TSV/SQL fragment。

规则：

- artifact manifest 必须能还原 `SnapshotTableDescriptor + SnapshotTableReader`。
- `artifact_content_digest` 校验物理文件，不替代 `raw_content_digest`。
- artifact 可作为 cache artifact，但 operation READY 需要的 artifact 必须进入 operation artifact closure。

## SnapshotRowsArchive

`SnapshotRowsArchive` 是 submit finalize 为已提交 FINAL snapshot 产出的 L1 durable artifact，
contract 为 `backend-vnext/snapshot-rows-archive/v1`。它以单一 tar artifact 存入
`LocalArtifactStore`，包含 snapshot/summary payload、logical table mapping，以及每个物理表的
descriptor 与 `rows.parquet`。

规则：

- archive source of truth 是 artifact store 中的单一 archive artifact，不是 repository import 的临时目录。
- 物理 rows parquet 可以在 artifact 内按 canonical/physical table 去重；restore 后必须恢复完整 logical table map。
- FULL upload 构造 archived baseline pair 时优先 restore `SnapshotRowsArchive`，命中后跳过 archived source package staging、SQL parse 和 materialize。
- restore 的完整性边界是 artifact-level content digest 与 restore cache marker；restore 阶段只恢复 summary、descriptor 与 logical table map，不提前读取所有 parquet rows。
- `rows.parquet` 由 lazy reader 在首次访问时读取，并校验 schema 与 row_count；显式诊断仍可调用 row digest validation。
- restore cache 是可重建目录，`.restore-complete.json` marker 必须匹配 artifact manifest/content digest；缺失或不匹配时重新解包。
- artifact 缺失或校验失败只能作为性能 miss/fallback，不改变 repository commit/hidden summary 的业务事实。

## RepositoryImportArtifact

`RepositoryImportArtifact` 是面向 repository/Dolt import provider 的 staging 输入。

允许格式：

```text
CSV / TSV
Parquet
JSON
SQL dump fragment
provider-private staging file
```

规则：

- 它不等同于 `SnapshotTableArtifact`。
- 它可以由 `SnapshotTableArtifact` 转换得到，也可以由 `SnapshotTableReader` streaming 生成。
- 它不是业务事实，缺失时应能从 source package 或 SnapshotTableSet 重建。
- 具体格式、转义、压缩和 digest 在 `capabilities/repository-import.md` 中定义。

## Operation Artifact Closure

Operation 对外 READY 前，前端或下载包需要读取的所有 artifacts 必须闭合。

规则：

- READY 不得依赖未来 cache warmup。
- Capability cache 命中可以复制、硬链接或引用进 operation artifact root。
- Operation-local refs 保持 bundle-relative 或 operation-relative，不使用 cache refs 作为前端 contract。
- Cache registration 可以在 READY 后异步发生。
- Operation 负责声明 READY 所需 artifact closure；`artifacts.closure` 负责生成、校验和恢复 closure。
- Flow 不应手写 cache-local 到 operation-local 的 artifact copy/restore 逻辑。

`artifacts.closure` 是 flow-neutral 支撑能力：

```text
build closure manifest
validate closure manifest
validate member manifest/content digest
restore cache-local refs to operation-local refs
copy or hardlink artifacts according to artifact_policy
rewrite refs without changing content/facts digest
```

Comparison records closure 第一版：

```text
operation artifact root
  comparison/
    facts.json
    records/
      <table>.records.jsonl
      <table>.records.manifest.json
    records-closure.json
```

规则：

- `facts.json` 可以包含 operation-local `records_ref`。
- `records_ref` 不进入 `comparison_digest`，因此 cache restore 或 bundle assembly 可以重写 ref。
- `records-closure.json` 必须能校验 facts core digest、records manifest digest 和 records content digest。
- READY 不得只引用 `comparison_core_cache` 中的 records path。
- 如果 comparison 输出要求 records artifact，closure 不完整时 operation 不能对外 READY。

Risk artifacts 第一版：

```text
operation artifact root
  risk/
    risk-evaluation.json
    risk-report.json
    annotations/
      <table>.risk-annotations.json
      <table>.risk-annotations.manifest.json
```

规则：

- `RiskReport` 是 risk capability 输出摘要，不是 ComparisonSurface 或 WorkbenchBundle。
- 大量 row-level annotations 应写入 `RiskAnnotation` artifact，不全部内联到 report。
- 如果 `RiskReport` 引用 annotation artifacts，operation READY 前必须进入 operation artifact closure。
- annotation refs 可在 cache restore 或 bundle assembly 时重写，不进入 `risk_evaluation_digest`。
- annotation artifact manifest/content digest 可以进入 `risk_evaluation_digest`。

Surface / bundle artifacts 第一版：

```text
operation artifact root
  surfaces/
    <pair_id>/comparison-surface.json
  bundles/
    <bundle_id>/
      manifest.json
      artifact-closure.json
      pairs/
        <pair_id>/...
      adapters/
        workbench/...
```

规则：

- `ComparisonSurface` 是 flow-neutral 展示结构，不包含 upload/submit/history binding。
- `ComparisonBundle` 可以包含一个或多个 pair surface。
- Workbench bundle 是 adapter artifact，不替代 `ComparisonBundle`。
- Surface refs 可以在 bundle assembly 时重写，不进入 `surface_digest`。
- Bundle refs 必须是 bundle-relative，不允许 host path 或 cache-local ref。
- Bundle READY 前必须闭合 surface、records、risk、diagnostics 和共享 snapshot artifacts。

## Cache Artifact

Cache artifact 属于 L3。

初始 cache 层：

```text
source_snapshot_cache
source_package_index_cache optional
snapshot_table_artifact_cache
projection_table_cache
comparison_core_cache
comparison_surface_cache optional
flow_assembly_cache
risk_evaluation_cache optional
workbench_bundle_adapter_cache optional
```

不属于 backend vNext capability cache 的技术 cache：

```text
repository_server_table_cache
```

`snapshot_table_artifact_cache` scope：

```text
repository_id
table_name
compare_schema_digest
raw_content_digest
row_count
compare_key_digest
scalar_encoding_version
artifact_contract_version
export_format
sort_or_row_order_contract
```

规则：

- `source_package_index_cache` 只复用 package entry index / manifest，不替代 L1 source artifact。
- `source_snapshot_cache` 的 source 输入应是 SQL document 层的 `sql_source_digest`，不是整个 zip bytes digest。
- 支持同 `repository_id` 内跨 commit/ref 复用。
- 不支持跨 project/repository_id 全局复用。
- 不包含 operation id、workspace id、preview id、history operation id 或 host path。

`comparison_core_cache` 第一版 scope：

```text
before_snapshot_digest
current_snapshot_digest
comparison_contract_version
projection_contract_version
scalar_encoding_version
table_ruleset_digest
requested_tables
comparison_options
```

第一版 cache entry：

```text
comparison-core-cache/
  cache-entry.json
  facts-core.json
  records/
    <table>.records.jsonl
    <table>.records.manifest.json
  records-closure.json
```

规则：

- 第一版使用 pair-level comparison core entry，不做 table-level comparison cache，也不把 surface/bundle 合并成单一 pair-total cache。
- `facts-core.json` 使用 neutral refs 或无 refs；命中恢复时生成 operation-local refs。
- `records-closure.json` 在 cache entry 内闭合 cache-local records，同时命中恢复时必须生成 operation-local closure。
- `comparison_core_cache` 不缓存 risk evaluation、ComparisonSurface 或 WorkbenchBundle。
- 后续可增加 table-level comparison cache、records 压缩/列式格式、dedup、promotion 和 eviction 策略。

Provider-neutral 规则：

- `comparison_core_cache` key 默认不包含 provider name；同一 pair/rules/options 的 SQL path、Snapshot path、Dolt native path 可以共享 canonical cache。
- cache value 必须是 canonical `ComparisonFacts + ComparisonRecordsClosure`，不是 provider raw output。
- provider semantic version 只有在会改变 canonical comparison 语义时才进入 comparison options / contract version；纯性能路线或输出顺序差异不进入 key。
- records 顺序差异必须通过 canonical sort 或 order-insensitive digest 消解。
- provider-local raw diff cache 如有需要，应单独命名，不得替代 comparison core cache。
- Dolt native provider 只有在完成 projection/schema/scalar/key/counter 归一化后，才能写入 provider-neutral comparison core cache。
- Ordered diff records 进入 comparison core cache 时必须作为 canonical comparison facts/records extension，而不是 surface-only artifact。

`risk_evaluation_cache` 第一版不要求实现，只保留边界。未来 cache key 至少包含：

```text
comparison_digest
risk_contract_version
risk_model_version
risk_ruleset_digest
risk_options
annotation_artifact_contract_version
```

规则：

- `risk_evaluation_cache` 不缓存 ComparisonSurface 或 WorkbenchBundle。
- `comparison_core_cache` 命中不等于 `risk_evaluation_cache` 命中。
- risk cache hit 仍需校验 annotation artifact manifest/content digest。

`comparison_surface_cache` 第一版不要求实现，只保留边界。未来 key 至少包含：

```text
comparison_digest
risk_evaluation_digest optional
surface_contract_version
records_closure_manifest_digest optional
risk_annotation_closure_manifest_digest optional
```

规则：

- `comparison_surface_cache` 只缓存 thin surface assembly 输出，不缓存 pair-total delivery 或 Workbench adapter truth。
- `comparison_surface_cache` 不缓存 Workbench adapter 或 flow envelope。
- surface cache hit 必须恢复为 operation-local 或 bundle-local refs。
- surface cache miss 不改变 comparison/risk 语义。

`flow_assembly_cache` / `workbench_bundle_adapter_cache` 是交付层 cache：

- 可以缓存 bundle artifact 或 adapter output。
- 不缓存 comparison facts、risk facts 或 surface core identity。
- 命中后仍需校验 artifact closure。
- 它们是交付层复用，不是 pair-total 比较事实缓存。
- 第一版不实现；Workbench adapter 也不默认实现。

### Repository Server Table Cache

`repository_server_table_cache` 是 repository server / Dolt repository module 的内部技术 cache，用于减少跨 API session 的 repository IO。

可缓存内容：

```text
RepositoryTableCatalog
table describe/count facts
repository table root/hash metadata
repository-local export artifacts
provider-private readback/export intermediates
```

建议 key：

```text
repository_id
resolved_commit_hash / immutable_ref
table_name optional
dolt_version
repository_server_contract_version
table_root_hash optional
export_format optional
```

规则：

- 它不是 `snapshot_table_artifact_cache`，不使用 Snapshot digest、projection digest、comparison digest。
- 它不使用 `PROVISIONAL` / `COMMIT_VALIDATED` 业务 validation status，可使用 repository server 自己的 integrity status。
- 它不理解 Workspace、Submission、Comparison、table ruleset 或 business digest。
- 它可以加速 `repository_ref_materialization`，但不能替代 Snapshot materialization 的 descriptor/digest 计算。
- 它的 cache miss 不改变业务语义。
- 如果命中 repository-local export artifact，backend vNext 仍必须校验生成的 SnapshotTableDescriptor、raw content digest 和 artifact manifest。

第一版简化策略：

- 可以实现跨 session read-through/write-through cache，优先缓存 catalog、describe/count facts、table root/hash metadata 等小型技术事实。
- key 必须包含 `repository_id`、resolved immutable commit/ref、`dolt_version` 和 `repository_server_contract_version`。
- cache entry 损坏、版本不匹配或校验失败时直接丢弃并回退 repository IO。
- 不实现 TTL、pin、eviction、quota、远端存储或跨项目复用。
- 不默认缓存 export artifacts、table data 文件或 provider-private 大对象。
- cache root 可以被人工整体清空；清空不改变业务语义。

必须补充设计后才能启用：

- 长时间运行环境需要自动 cleanup、quota 或磁盘预算控制。
- 需要缓存 repository-local export artifacts 或大表文件。
- 多进程/多容器共享同一 cache root。
- 需要 pin/release、TTL、eviction、metrics 或后台 cleanup。
- 需要把 cache 状态暴露给运维/API。

## Cache Validation Status

未经权威校验的输入可能已经具备可复用的内容形状，但不能直接视为正式 cache。Cache entry 需要区分内容候选和 repository/commit validated 产物。

建议状态：

```text
validation_status:
  PROVISIONAL
  CONTENT_VERIFIED
  COMMIT_VALIDATED
```

建议 metadata：

```text
CacheEntry:
  cache_layer
  cache_key_digest
  artifact_ref
  producer_role:
    DIRECT_RESPONSE
    WARMUP
    FINALIZE_WRITE
    REPOSITORY_READBACK
    READ_ONLY
  validation_status
  producer_operation_id
  source_package_digest optional
  sql_source_digest optional
  snapshot_digest optional
  repository_id optional
  commit_hash optional
  created_at
  ttl / pin metadata
```

规则：

- Cache key 仍不包含 generation、operation id、workspace id、preview id 或业务对象 ID；这些只作为 metadata/diagnostics。
- `WARMUP` 类 producer 可以写 `PROVISIONAL` cache candidate。
- 正式写入类 caller 可以读取 `PROVISIONAL` candidate，但必须从 L1 source artifact 和 binding 重新校验 descriptor/digest。
- Repository/readback 或等价权威校验通过后，cache entry 才能 promote 为 `COMMIT_VALIDATED`。
- 只读类 caller 通常只读取 repository/commit validated cache。
- Provisional cache 校验失败时应丢弃 candidate 并回退重算，不应直接导致业务失败。

Repository/readback validation 是 Dolt 数据和正式 cache 的权威流程点；具体业务流程如何触发它由 `flows.md` 定义。

## Projection Artifact Boundary

`ProjectionTableArtifact` 是由 raw `SnapshotTable` 应用 table rules 后生成的 compare-ready table，例如主键修正、列忽略、scalar normalization 或 ordered-table policy 之后的表。

它不属于 `SnapshotTableArtifact`：

```text
SnapshotTableArtifact
  raw snapshot table materialization
  面向 summary、bundle、repository import、comparison fallback

ProjectionTableArtifact
  comparison-derived table materialization
  面向 comparison_compute / provider planning / native projection diff
```

`projection_table_cache` 应作为 comparison/projection capability 的 cache 层保留；完整 key、artifact 格式、provider 和命中策略由 `contracts/comparison.md` 定义。

当前阶段只保留边界：

- Projection artifact 由 `SnapshotTableArtifact + table_ruleset` 或 `SnapshotTableReader + table_ruleset` 派生。
- Projection artifact 不是业务事实。
- 预热类 producer 只能写 `PROVISIONAL` candidate。
- Repository/readback 或等价权威校验后才可 promote 为 `COMMIT_VALIDATED`。
- 只读类 caller 只使用 commit/repository validated projection cache。
