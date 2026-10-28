# Snapshot Materialization Capability

本文定义 SourcePackage、SQL dump document、repository ref 与 Snapshot/Table 之间的能力边界。Capability 不绑定 upload、submit 或 history compare 流程。

> **当前权威提示：** 本文中仍要求 FINAL SnapshotSummary 写入 repository hidden system table、并要求
> repository-ref readback 以 hidden summary 为权威的表述，已由 [ADR 0019](../refactoring/formal/adr/0019-commit-canonical-metadata-authority.md)
> 取代；本提示适用于下方“设计原则”“Stable Entrypoints”及 `repository_ref_materialization` 小节中的相应旧句。
> 当前 commit 规范元数据权威是 Backend 持有的 `CanonicalizationManifest`，Repository-ref 采用单遍读取，
> 不写入、不读取或校验 hidden summary。其他 Snapshot materialization 语义仍按本文与 owning Contract 执行。

## 能力列表

```text
source_package_staging
source_package_entry_resolution
optional_source_document_resolution
sql_dump_source_resolution
sql_dump_parse
snapshot_materialization
repository_ref_materialization
business_source_composition
snapshot_summary
snapshot_table_set_resolution
```

## 设计原则

Capability 必须保持 flow-neutral 和显式输入输出。

规则：

- Capability 不读取或修改 Workspace、Submission、Preview、History request 等业务状态。
- Capability 不根据 upload、submit、history compare 等流程名分支。
- Capability 可以接收 `cache_policy`、`artifact_policy`、`validation_status_policy` 等显式策略；这些策略由 flow/operation 层映射。
- Capability 输出只包含结果、diagnostics、artifact refs 和 cache diagnostics，不推进业务状态机。
- 输入中的 audit/producer metadata 只能用于审计和诊断，不进入 content digest、cache key，也不能改变 materialization 语义。
- 外部测试、benchmark 或新功能可以直接调用 capability；只要提供同一输入和版本上下文，应得到同一内容结果。
- “无状态”表示无隐藏业务状态和无隐式 flow context；允许受显式 `cache_policy` 控制的 artifact/cache IO。
- Repository/Dolt 相关能力通过 repository table access provider 注入；本 capability 负责归一化为 Snapshot，不要求 repository server 理解 Snapshot 业务对象。
- Capability 可以暴露多个稳定 entrypoint；SourcePackage 定位、SqlDumpSource resolution、SQL parser/materializer、RepositoryRef materialization 都应能独立测试和复用。
- `backend_vnext.capabilities.table_rules` 是共享语义真源。Snapshot materialization 负责派生自己的 materialization 视图，但 compare-key / compare participation 的语义判定必须来自同一份规则。
- 对于没有可用 compare key 的表，Snapshot materialization 不再自动补全列 surrogate key；它应保留为 keyless 事实，并按 shared rules / comparison contract 进入早退或降级判断。
- **已由 ADR 0019 取代（历史表述）：** submit finalize 写入的 FINAL SnapshotSummary 必须在 repository commit/ref 内以隐藏系统表形式落地；history compare / archive 读取这份正式事实，而不是自己重建摘要。
- `/sql/dbcfg.sql` 是当前项目的 SourcePackage 业务约定，不应成为 SQL dump parser 的唯一入口。
- `/comps/logic/logics.xml` 是可选业务文档，由 `composite_signal` capability 消费；缺失时使用稳定 EMPTY source。
- 正式 upload、submit 和 archive source replay 统一调用 business-source wrapper，组合 SQL SnapshotTable 与 `composite_signal_point` 后再最终化 identity；SQL-only benchmark entrypoint 不改变。
- history compare 直接从 repository/Dolt 回读包含派生表的 FINAL SnapshotTableSet，不重新解析 XML。
- `snapshot_digest` 在 upload、Preview baseline 与 History 中使用同一算法；每表只包含表名、比较 schema 摘要、业务 schema 摘要、比较键、行数与 `raw_content_digest`。Repository-ref 可从 catalog 与 commit manifest 构造未读行表描述。
- upload 阶段可以先调用 `materialize_sql_snapshot_preview(...)` 产出 `PROVISIONAL` snapshot/summary，再由 `finalize_snapshot_materialization(...)` 在异步阶段补齐 canonical `raw_content_digest` 并生成 `FINAL` snapshot/summary。
- `materialize_sql_snapshot_preview(...)` 只负责 provisional 表事实与 reader 初始化，不应提前生成 `canonical_artifact_ref` 或 `previous_canonical_artifact_ref`。
- `finalize_snapshot_materialization(...)` / submit-finalize 阶段负责把 provisional 事实收口为 finalized summary，并在需要时补齐 canonical ref 链。

## Stable Entrypoints

Snapshot materialization 第一版建议暴露以下稳定 entrypoints：

```text
stage_source_package(input) -> SourcePackageStagingResult
resolve_required_sql_document(source_package_ref, required_path="/sql/dbcfg.sql") -> SourceDocumentRef
resolve_sql_dump_source(source_document_ref | sql_file_compat | sql_gz_compat) -> SqlDumpSource
parse_sql_dump_source(sql_dump_source, parser_context) -> SqlDumpParseResult
materialize_sql_snapshot_preview(materialization_context) -> SnapshotMaterializationResult
materialize_sql_dump_source(sql_dump_source, materialization_context) -> SnapshotMaterializationResult
finalize_snapshot_materialization(materialization_result) -> SnapshotMaterializationResult
materialize_repository_ref(repository_ref, materialization_context) -> SnapshotMaterializationResult
materialize_business_source_package(source_package) -> SnapshotMaterializationResult
materialize_business_source_package_preview(source_package) -> SnapshotMaterializationResult
resolve_snapshot_table_set(snapshot_ref | materialization_result, policy) -> SnapshotTableSet
```

当前代码形状、兼容入口和实现边界的历史笔记见 tag `docs/p2-p3-cleanup-pre-20260817` 中的
`docs/backend-vnext/notes/snapshot-materialization-implementation-notes.md`。本文档仍以 contract 为准。

规则：

- `stage_source_package` 和 `resolve_required_sql_document` 处理容器和 entry 约定。
- `resolve_sql_dump_source` 处理 SQL parser 输入身份、encoding 和 `sql_source_digest`。
- `parse_sql_dump_source` / `materialize_sql_dump_source` 不读取 SourcePackage 容器，只消费 `SqlDumpSource`。
- `parse_sql_dump_source` 先以 statement stream 收集 table facts 与 row_count，`ParsedTableBundle.rows` 仅在 materialization 或 reader 访问时按需展开，不会为所有表提前展开 row values。
- `SnapshotTableReader` 可以持有 deferred row source；preview 阶段的表行数据只应在 `iter_rows()` 或显式 digest 校验时展开，reader init 本身不应触发行 materialization。
- `materialize_sql_snapshot_preview` 输出 `PROVISIONAL` snapshot/summary；未生成 `raw_content_digest` 的表在 snapshot digest 中以缺失表摘要表示。
- `finalize_snapshot_materialization` 负责 canonical row digest 校验、`raw_content_digest` 生成以及 `FINAL` snapshot/summary 落地。
- **已由 ADR 0019 取代（历史表述）：** `finalize_snapshot_materialization(...)` 如果运行在 submit finalize / repository import 路径下，还必须把 FINAL SnapshotSummary 写入 repository commit/ref 的隐藏系统表，并让后续 readback 以这份 hidden summary 为权威事实。
- `materialize_repository_ref` 不读取 SourcePackage 或 SQL，只通过 repository table access provider 归一化 repository row stream。
- Flow-facing helper 可以组合上述入口，但测试、benchmark 或外部项目可以直接调用其中任一稳定入口。
- `materialize_business_source_package*` 是正式业务 flow-facing wrapper；它调用 SQL materialization、composite XML parser/materializer 与通用 Snapshot result rebuild/finalize，不复制 digest 算法。
- Stable entrypoint 的 contract version、digest 输入和 diagnostics 必须可独立断言。

## Packaging And Scheduling

- bundle assembly 默认采用磁盘型文件物化路径，保证稳定的 artifact 语义和可追踪的落盘结果；内存打包可以作为受控优化项和 benchmark 对照项，但不应成为默认主路径。
- Snapshot Materialization SQL Path 的默认同步结果应保持 row-stream-first，只产出 `SnapshotTableReader` / provisional summary 所需的最小事实；CSV/TSV/Parquet 作为下游 staging / export 能力按需开启，不应被视为同步阶段的默认输出。
- 后续是否把某些物化前移到 upload 同步阶段，应在 `diff compute`、`risk` 和 `bundle` 串联完成后统一评估。
- 如果一次 upload 同时携带两份独立业务数据，默认调度策略可以是并行，但这属于 flow / orchestration 层决策，不由 capability 自己分支。
- 并行调度只影响吞吐和 wall time，不改变 snapshot / summary / digest 语义。

### Provenance / Diagnostics

这些字段可以存在于 parser 输出、descriptor、summary diagnostics 或日志中，但它们只服务于 traceability / replay / debug，不参与主判据链：

- `table_raw_sql_digest`：raw SQL 诊断 hash，用于回放、定位和粗粒度排查。
- `base_table_fingerprint`：表级 provenance / 身份元数据，用于展示和诊断。

## source_package_staging

职责：

```text
持久化 SourcePackage，索引 package entry，并计算 package/document digest。
```

输入：

```text
SourcePackageInput:
  bytes or stream
  package_kind hint: ZIP | TAR_GZ | DIRECTORY | SQL_FILE | SQL_GZ
  source_origin optional
  producer_context optional
  retention_policy
```

`retention_policy` 只影响存储保留和外部清理策略，不进入 digest、cache key 或 materialization 语义。

输出：

```text
SourcePackageStagingResult:
  source_package_id
  source_package_digest
  package_manifest_digest
  required_entries_manifest_digest optional
  entries
  artifact_ref
  required_sql_document_ref optional
  diagnostics
```

不负责：

- 解析 SQL。
- 解析 XML 或其他业务文件。
- 创建 Snapshot。
- 计算 Comparison。
- 写业务状态。

错误：

```text
SOURCE_PACKAGE_INVALID
SOURCE_PACKAGE_UNSUPPORTED
SOURCE_PACKAGE_DIGEST_MISMATCH
SOURCE_PACKAGE_STORAGE_RETRYABLE
```

规则：

- 当前业务 package 是多目录多文件压缩包。
- 当前业务 SourcePackage entry resolution 必须从唯一 `/sql/dbcfg.sql` 创建 `SourceDocumentRef`。
- 多个 SQL 文件合并、排序和覆盖不是第一版能力。
- `SQL_FILE` 仅用于测试或 benchmark 裸 SQL 输入。
- `SQL_GZ` 仅用于单个 gzip 压缩 SQL 文件；解压后映射为 `/sql/dbcfg.sql`。
- `TAR_GZ` 是多文件 gzip package；普通 `.gz` 不是多文件容器。

## source_package_entry_resolution

职责：

```text
从 SourcePackage 中定位 required SQL document，生成 SourceDocumentRef。
```

输入：

```text
SourcePackageEntryResolveInput:
  source_package_ref
  required_path: /sql/dbcfg.sql
```

输出：

```text
SourceDocumentRef:
  source_package_id
  normalized_path
  document_kind: SQL_DUMP
  document_content_digest
  size_bytes
  encoding_hint optional
  entry_manifest_digest
  diagnostics
```

规则：

- 当前项目默认 required path 是 `/sql/dbcfg.sql`。
- 缺少或重复 `/sql/dbcfg.sql` 是 source package final failure。
- 其他 package entries 只记录为 unconsumed members，不进入 SQL Snapshot materialization。
- 未来 XML 等文件应通过新的 document resolver/parser 入口处理，不塞进 SQL dump parser。

## sql_dump_source_resolution

职责：

```text
从 SourceDocumentRef、SQL_FILE 或 SQL_GZ 生成 SqlDumpSource。
```

输入：

```text
SqlDumpSourceResolveInput:
  source_document_ref optional
  sql_file_ref optional
  sql_gz_ref optional
  parser_input_contract_version
  encoding_policy
```

输出：

```text
SqlDumpSource:
  source_document_ref
  sql_source_digest
  parser_input_contract_version
  encoding
  source_size_bytes
  diagnostics
```

规则：

- `sql_source_digest` 是后续 SQL Snapshot cache 的主要 source 输入。
- zip 物理元数据变化不应改变 `sql_source_digest`。
- `SQL_FILE` 和 `SQL_GZ` 可以直接进入该入口，用于测试或 benchmark 输入。
- compat 输入需要生成 synthetic `SourceDocumentRef` 或等价 document identity，确保后续 digest/diagnostics 仍可追踪。
- 该入口不负责选择 SourcePackage required path。

## sql_dump_parse

职责：

```text
把 SqlDumpSource 解析为 parser-internal table stream / descriptors。
```

输入：

```text
SqlDumpParseInput:
  sql_dump_source
  parser_version
  parser_input_contract_version
  scalar_encoding_version
  requested_tables optional
```

输出：

```text
SqlDumpParseResult:
  parser_tables
  parse_summary
  parser_diagnostics
```

规则：

- SQL parser 是通用能力，只消费 `SqlDumpSource`。
- SQL parser 不知道 SourcePackage、Workspace、Submission、History request 或 repository。
- Parser internal table 不跨 capability 边界；跨边界输出必须转换成 SnapshotTableDescriptor / SnapshotTableReader / SnapshotSummary。
- 该入口可被单元测试、SQL fixture、benchmark 或其他项目直接调用。

## snapshot_materialization

职责：

```text
把 SqlDumpSource、repository ref 或 existing Snapshot ref 转成 Snapshot、SnapshotSummary 和可选 table access。
```

输入：

```text
SnapshotMaterializationInput:
  source:
    SqlDumpSource | RepositoryRef | ExistingSnapshotRef
  parser_version
  digest_contract_version
  table_ruleset_version
  table_rule_registry optional
  scalar_encoding_version
  snapshot_materialization_contract_version
  row_materialization_profile
  requested_tables optional
  materialization_policy:
    DESCRIPTOR_ONLY | READERS_REQUIRED | ARTIFACTS_REQUIRED
  cache_policy:
    DISABLED | READ_ONLY | WRITE_THROUGH
```

输出：

```text
SnapshotMaterializationResult:
  snapshot
  summary
  table_set optional
  table_artifact_refs optional
  cache_diagnostics
  diagnostics
```

规则：

- 只需要 provider planning 时，可以输出 `snapshot + summary`，延迟构建 `table_set`。
- 调用方对外声明 READY 前需要 table refs 时，必须 materialize caller artifact closure。
- Cache hit 只加速，不替代 source/ref 校验。
- Capability 不知道自己服务 upload、submit、history compare 还是 archive diagnostics。
- SQL parser 只消费 `SqlDumpSource`，不直接读取 SourcePackage 容器。
- `table_rule_registry` 是显式注入的表规则入口；若不传，则由实现提供默认业务规则，默认来源统一收口到 `backend_vnext.capabilities.table_rules` 共享真源。
- `table_ruleset_version` 应与实际使用的 `table_rule_registry` 保持一致。
- snapshot materialization 只消费共享规则派生出的分类和 key 决策，不再维护独立规则真源。
- Snapshot digest 只使用表级身份事实；provenance / diagnostics 信息只用于 traceability / replay / debug，不进入 `raw_content_digest` 的语义定义，也不作为 row file / export IO cache 的主判据。
- upload / export build 阶段应使用 `row_layout_digest` 作为物理 row file 复用键；它由 canonical raw content digest、完整源列编码 schema 与 ordered row metadata 组合而成，不应把 `table_name` 或 `compare_schema_digest` 混进去。跨 operation export cache 另外以 repository scope 与 Parquet writer contract version 限定命中。这只减少物理文件数量，不改变 canonical digest 或 summary 语义。
- upload / preview 允许先完成 `provisional summary + lightweight reader_init`，canonical digest validation、final summary 和 cache 生成可以在异步阶段完成，不要求同一同步调用里一次做完。

## repository_ref_materialization

具体实现设计见 `repository-ref-materialization.md`。本节只保留 capability 总览和跨模块边界。

职责：

```text
把 RepositoryRef 通过 repository table access provider 归一化为 Snapshot、SnapshotSummary 和可选 SnapshotTableSet。
```

分层：

```text
repository_server / dolt_repository module
  -> RepositoryTableAccessProvider
  -> RepositoryRefSession
  -> RepositoryTableCatalog / RepositoryTableReader / RepositoryTableExportArtifact
  -> snapshot_materialization.repository_ref_materialization
  -> Snapshot + SnapshotSummary + optional SnapshotTableSet
```

关键边界：

- repository server 不产出 `Snapshot`、`SnapshotSummary` 或 `SnapshotTableSet`。
- repository server 不理解 Workspace、Submission、Comparison、table ruleset 或 business digest。
- repository server 只提供 repository-local 的表 catalog、reader、export 和生命周期控制。
- snapshot materialization 负责 canonical identifier、scalar encoding、compare schema digest、raw content digest、state digest 和 SnapshotSummary。
- **已由 ADR 0019 取代（历史表述）：** repository ref materialization 负责读取 repository commit/ref 内的 hidden summary table，并在该事实基础上恢复 SnapshotSummary；它不应在 summary 缺失时自己重建一套轻量摘要来掩盖不完整数据。

输入：

```text
RepositoryRefMaterializationInput:
  repository_ref
  repository_table_access_provider
  digest_contract_version
  parser_version optional
  table_ruleset_version
  scalar_encoding_version
  snapshot_materialization_contract_version
  row_materialization_profile
  requested_tables optional
  materialization_policy:
    DESCRIPTOR_ONLY | READERS_REQUIRED | ARTIFACTS_REQUIRED
  cache_policy
  cache_lookup_policy
  artifact_policy
```

输出：

```text
SnapshotMaterializationResult:
  snapshot
  summary
  table_set optional
  table_artifact_refs optional
  cache_diagnostics
  diagnostics
```

Repository table access provider：

```text
RepositoryTableAccessProvider:
  open_ref(repository_ref, timeout_policy) -> RepositoryRefSession

RepositoryRefSession:
  get_catalog() -> RepositoryTableCatalog
  open_table_reader(table_name) -> RepositoryTableReader
  export_table_artifact(table_name, format) -> RepositoryTableExportArtifact
  close()
```

第一版规则：

- `open_ref()` read-only，成功后 session pin 到 `resolved_commit_hash`。
- `open_ref()` 语义幂等，但不保证返回同一个 session 对象。
- `open_ref_timeout_ms` 必须支持；其他 timeout field 先预留。
- `get_catalog()` eager load，session 内 memoize。
- `open_table_reader()` 第一版不要求并发、thread-safe 或 rewind。
- repository row stream 使用 tuple + catalog column order。
- `snapshot_materialization.scalar_encoding` 负责 Snapshot 层 scalar encoding；后续稳定后可下沉到 `core.scalar_encoding`。

Repository catalog 建议至少包含：

```text
RepositoryTableCatalog:
  repository_id
  repository_ref
  resolved_commit_hash
  repository_server_contract_version
  dolt_version optional
  tables:
    - table_name
      columns
      primary_key_columns
      row_count optional
      repository_table_version optional
      table_root_hash optional
      schema_facts_digest optional
```

避免重复 list/describe 规则：

- 每个 `repository_ref_materialization` run 对同一 ref 最多加载一次 catalog。
- `SnapshotSummary` 的 table list 必须来自该 catalog。
- `SnapshotTableSet` resolution 必须以已生成的 Summary/catalog 为表清单来源，不得再次独立 `list_tables`。
- Comparison provider 不得为同一 ref 直接调用 repository server 重新 list tables；只能通过 `ComparisonInput.summary` 和 `table_set_ref` 请求表数据。
- Row reader/export 可以 lazy 打开，但必须复用同一个 `RepositoryRefSession` 或同一 catalog identity。

Repository table cache：

- repository server 可以维护跨 session 的 repository-local table cache，用于 catalog、describe/count、table root/hash、export artifact 等低层结果。
- repository server 的 row 访问仍以 table reader / stream 为主；export artifact 只作为可选 fast path，不应取代 row stream 作为第一版主路径。
- repository server table cache 不是 backend vNext capability cache，不使用 `PROVISIONAL` / `COMMIT_VALIDATED`。
- repository server table cache key 可以包含 `repository_id`、resolved commit hash、table name、Dolt version、repository server contract version、export format、table root/hash。
- repository server cache hit 只能减少 repository IO，不能替代 Snapshot materialization 的 descriptor/digest 校验。
- 如果 repository server 返回 `table_root_hash` 或等价 table version，可作为加速和 diagnostics 输入；在语义未验证前不能直接替代 `raw_content_digest`。
- repository_server_table_cache 的 TTL、pin、cleanup、export artifact cache 是后续独立设计。

## snapshot_summary

职责：

```text
在已有 Snapshot 或 SnapshotTableDescriptor set 上生成 SnapshotSummary。
```

输入：

```text
SnapshotSummaryInput:
  snapshot
  descriptor_set
  summary_contract_version
```

输出：

```text
SnapshotSummary
```

规则：

- Summary 不读取 full rows，除非 descriptor/digest 尚未计算且调用方明确要求。
- Summary 可写入 index/cache，但不是业务事实。
- Summary index 是可重算优化层。
- Summary 可以先以 provisional 形式输出，再在 canonical digest 完成后收敛为 final 形式；稳定读路径只应消费 final summary。
- repository ref materialization / history compare 的 summary 读取失败应视为完整性错误，而不是 summary 重建机会。

## snapshot_table_set_resolution

职责：

```text
根据 Snapshot + SnapshotSummary 按需打开 SnapshotTableReader。
```

输入：

```text
SnapshotTableSetResolveInput:
  snapshot
  summary
  requested_tables optional
  materialization_policy
  cache_policy
  artifact_policy
```

输出：

```text
SnapshotTableSetResolveResult:
  table_set
  resolved_table_count
  skipped_table_count
  cache_diagnostics
  artifact_refs optional
  diagnostics
```

Resolution 顺序：

1. caller-local artifact。
2. capability cache。
3. L1 source package -> SqlDumpSource rematerialization。
4. L2 repository ref through `RepositoryRefSession` catalog + lazy reader/export。

规则：

- 所有来源都必须用 descriptor digest 校验。
- Reader 第一版只要求 full-row streaming。
- Column projection 和 predicate pushdown 不是第一版 contract。

## Cache 接入点

### Source Snapshot Cache

Key 输入：

```text
sql_source_digest
required_entries_manifest_digest
parser_input_contract_version
parser_version
scalar_encoding_version
table_ruleset_version
snapshot_materialization_contract_version
row_materialization_profile
```

输出：

```text
SnapshotSummary
SnapshotTableDescriptor set
optional SnapshotTableArtifact refs
parse/materialization diagnostics
```

规则：

- Cache key 不使用整个 zip bytes digest。
- `/sql/dbcfg.sql` 不变时，zip entry 顺序、压缩参数或 mtime 变化不应导致 SQL Snapshot cache 失效。
- 其他 unconsumed package files 不进入 SQL Snapshot cache key。
- provenance / diagnostics 元数据可以随 upload / preview 结果一并传递，但不应替代 `sql_source_digest` 作为稳定 Source Snapshot cache key。

### Snapshot Table Artifact Cache

Key scope：

```text
repository_id
row_layout_digest
scalar_encoding_version
snapshot_table_artifact_contract_version
export_format
sort_or_row_order_contract
```

规则：

- 支持同 `repository_id` 内跨 commit/ref 复用。
- 不支持跨 project/repository_id 复用。
- Cache key 不包含业务流程 ID、table name 或 host path。
- `row_layout_digest` 由 canonical raw content digest、完整源列编码 schema 与 ordered row metadata 组合而成；table name 不进入 digest。源列类型、ENUM/SET 标签、nullability 或 Parquet 字段布局变化会改变 layout。Repository scope 与 Parquet writer contract version 是 export cache 的独立键字段。
- `validation_status_policy=PROVISIONAL_ONLY` 时只能写入 `PROVISIONAL` candidate。
- 调用方允许读取 `PROVISIONAL` candidate 时，必须重新校验 source binding、descriptor 和 digest，并具备 fallback recompute 路径。
- Repository/readback 或等价权威校验通过后，cache entry 才能 promote 为 `COMMIT_VALIDATED`。
- `READ_COMMIT_VALIDATED_ONLY` lookup policy 只读取 `COMMIT_VALIDATED` 或 repository readback 产生的 cache。

### Projection Table Cache

`projection_table_cache` 由 comparison/projection capability 负责，不属于 snapshot materialization 的第一版 contract。

当前能力只预留边界：

- `SnapshotTableArtifact` 是 raw table materialization。
- Projection table 是 `SnapshotTable + table_ruleset` 的派生产物。
- Projection table cache 不应并入 `snapshot_table_artifact_cache`。
- 完整 key、artifact 格式、provider 和命中策略由 `contracts/comparison.md` 定义。

## 策略输入

本 capability 不绑定业务流程。业务流程到策略输入的映射见 `../flows.md`，异步 operation 规则见 `../operations.md`。

建议策略：

```text
cache_policy:
  DISABLED
  READ_ONLY
  WRITE_THROUGH

cache_lookup_policy:
  READ_COMMIT_VALIDATED_ONLY
  READ_PROVISIONAL_WITH_REVALIDATION
  READ_ANY_WITH_REVALIDATION

validation_status_policy:
  NO_CACHE_WRITE
  PROVISIONAL_ONLY
  PROMOTE_AFTER_AUTHORITY_VALIDATION

artifact_policy:
  NONE
  CALLER_LOCAL_REQUIRED
  CACHE_ARTIFACT_ALLOWED
```

规则：

- 直接反馈类调用通常使用 `READ_ONLY` 或 `DISABLED`，不等待 warmup。
- 只读类调用通常使用 `READ_COMMIT_VALIDATED_ONLY`。
- 预热类调用通常使用 `PROVISIONAL_ONLY`。
- 正式写入类调用可以使用 `READ_PROVISIONAL_WITH_REVALIDATION`，但必须从 durable source/ref 重新校验并具备 fallback recompute 路径。

## 验收标准

- 同一 source 内容、parser/table rules/materialization contract 下，重复 materialization 得到相同 `snapshot_digest`。
- Summary 可独立用于 provider planning，不打开 row reader。
- 删除 L3 cache 后，仍能从 L1 source package 或 L2 repository ref 重建 summary/table artifacts。
- Reader 能 streaming 大表，不要求一次性读入内存。
- Cache hit 后仍校验 descriptor、digest 和 artifact manifest。
- `READ_COMMIT_VALIDATED_ONLY` 不得读取 `PROVISIONAL` candidate。
- 读取 `PROVISIONAL` candidate 时，必须有 fallback recompute 和 promote/丢弃路径。

## 第一版取舍与后续演进

第一版固定选择：

- 当前业务 SourcePackage 必须消费唯一 `/sql/dbcfg.sql`，并可选消费 `/comps/logic/logics.xml`；后者缺失等价于 EMPTY source。
- `SQL_FILE` / `SQL_GZ` 只用于测试和 benchmark 裸 SQL 输入。
- SQL parser 只处理当前业务常见的 `DROP` / `CREATE` / `INSERT` 简单 dump。
- `SnapshotTableReader` contract 只要求 full-row streaming。
- `SnapshotTableArtifact` 是 raw table artifact，不包含 projection table。
- `repository_ref_materialization` 通过 repository table access provider 注入，comparison 不直接访问 repository server。
- `snapshot_table_artifact_cache` 支持同 `repository_id` 内跨 commit/ref 复用，不支持跨项目复用。

后续可能变化：

- 支持 SourcePackage 中 XML 或其他业务文件进入独立 parser。
- 支持更复杂 SQL dump 语法或更严格 parser diagnostics。
- 按 benchmark 结果评估 column projection / predicate pushdown 是否进入公开 reader contract。
- 引入 projection table cache，但它属于 comparison/projection capability，不并入 raw snapshot table artifact cache。
- repository server table cache 可加速 repository ref materialization，但仍不能替代 Snapshot descriptor/digest 计算。
- cache promotion、TTL、cleanup 和跨 operation artifact dedup 后续由 cache/operation 设计补全。
