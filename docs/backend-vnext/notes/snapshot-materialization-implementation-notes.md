# Snapshot Materialization Implementation Notes

本文记录 `snapshot_materialization` capability 当前代码的实现形状。它是对 `snapshot-materialization.md` 的补充，不是新的 contract；如果两者有冲突，以 `snapshot-materialization.md` 为准。

## 定位

当前实现把能力拆成三段：

```text
SourcePackage staging
  -> SqlDumpSource resolution
  -> SQL parse / Snapshot materialization
```

其中：

- `SourcePackage` 负责容器、目录树和 required entry 索引。
- `SqlDumpSource` 负责把 SQL 文档收敛成稳定的 parser 输入。
- `SnapshotMaterializationResult` 负责把解析后的 SQL dump 归一化成 Snapshot、Summary 和 table set。

当前第一版只把 `/sql/dbcfg.sql` 作为 required SQL document。Repository-backed 路径仍然留在后续 capability。

## 当前稳定入口形状

### `stage_source_package`

```text
stage_source_package(
  input_value: SourcePackageInput | Path | str | bytes | bytearray | memoryview,
) -> SourcePackageStagingResult
```

当前行为：

- 负责把容器型输入 staging 成 `SourcePackage`。
- 支持 `DIRECTORY`、`ZIP`、`TAR_GZ`、`SQL_FILE`、`SQL_GZ`。
- 最终会产出 `SourcePackageStagingResult`，其中带有 `artifact_ref`、`required_sql_document_ref` 和 `source_package`。
- 裸 SQL 输入 `SQL_FILE` 和 `SQL_GZ` 主要用于测试、benchmark 和裸 SQL 调试，不是正式业务包格式。
- `source_bytes` 和 `source_text` 主要服务于 SQL 兼容入口；容器型包当前仍以 `source_path` 为主。

### `resolve_required_sql_document`

```text
resolve_required_sql_document(
  source_package_ref: SourcePackageStagingResult | SourcePackage | str | ArtifactRef | DigestRef,
  required_path: str = "/sql/dbcfg.sql",
) -> SourceDocumentRef
```

当前行为：

- 只解析 required SQL document，不负责 SQL 内容解析。
- 依赖 `SourcePackage` 已经完成 staging 和 entry 索引。
- 结果是 `SourceDocumentRef`，可被后续 parser 直接消费。

### `resolve_sql_dump_source`

```text
resolve_sql_dump_source(
  source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | Path | str | bytes | bytearray | memoryview,
  *,
  parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION,
  encoding_policy: str = "utf-8",
) -> SqlDumpSource
```

当前行为：

- 把所有入口收敛成 `SqlDumpSource`。
- 如果输入是 `SourceDocumentRef`，会从 staged package artifact 读取真实文档 bytes。
- 如果输入是 `Path`、`str`、`bytes` 或 `bytearray`，会走兼容路径，必要时把 `*.gz` 作为单文档 gzip 输入处理。
- 如果输入是长 SQL 字符串，当前实现会避免把它误判为文件路径。
- `sql_source_digest` 以规范化后的 SQL 文本为准，用于后续 cache / identity。

### `parse_sql_dump_source`

```text
parse_sql_dump_source(
  sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | Path | str | bytes | bytearray | memoryview,
  parser_context: SqlDumpParseContext | SnapshotMaterializationInput | None = None,
) -> SqlDumpParseResult
```

当前行为：

- 只消费 `SqlDumpSource`，不读取 `SourcePackage` 容器。
- 返回 `ParsedSqlDump`、`SqlDumpParseSummary` 和 parser diagnostics。
- `parser_context` 可以直接给 `SqlDumpParseContext`，也可以给 `SnapshotMaterializationInput` 让它提取 parser 相关版本字段。
- 当前 parser 先按 statement stream 聚合 table facts、row_count 和 `raw_sql_digest`，`ParsedTableBundle.rows` 是按需展开的 lazy view；这让 parse-only benchmark 不必为所有表提前展开 row values。

### `materialize_sql_dump_source`

```text
materialize_sql_dump_source(
  sql_dump_source: SqlDumpSource | SourceDocumentRef | SourcePackageStagingResult | SourcePackage | Path | str | bytes | bytearray | memoryview,
  materialization_context: SnapshotMaterializationInput | None = None,
) -> SnapshotMaterializationResult
```

当前行为：

- 这是 SQL path 的核心入口。
- 如果没有显式 `materialization_context`，会构造一个默认 `SnapshotMaterializationInput`。
- 当前实现会同时产出 `Snapshot`、`SnapshotSummary` 和 `SnapshotTableSet`。
- `table_set`、`table_artifact_refs` 和 `cache_diagnostics` 在 contract 上是可选扩展点，当前 SQL path 主要先把 table set 做出来。
- preview / finalization 两段式下，table set 可以先带 lazy reader；只有真正读取 rows 的表才会 materialize rows，canonical digest 需要时才会触发全量 row materialization。

### `resolve_snapshot_table_set`

```text
resolve_snapshot_table_set(
  snapshot_ref_or_result: SnapshotMaterializationResult | Snapshot | SnapshotTableSet,
  policy: str = "READERS_REQUIRED",
) -> SnapshotTableSet
```

当前行为：

- 如果结果里已经带 `table_set`，直接返回。
- 如果只有 `Snapshot`，会从 `source_context` 或 `source_package_id` 反查 required SQL document，再重新 materialize。
- 这个入口主要用于按需恢复 table reader，不是重新设计一套新的 Snapshot contract。

### 便捷包装

当前实现还保留两个便捷入口：

```text
materialize_sql_source(...)
materialize_sql_file(...)
```

它们只是对 `SnapshotMaterializationInput` 的薄包装，方便测试和命令式调用。

## 当前输入对象

### `SourcePackageInput`

当前支持：

```text
source_path
source_bytes
source_text
package_kind
source_origin
producer_context
created_by
retention_policy
required_path
```

要点：

- 至少需要提供 `source_path`、`source_bytes` 或 `source_text` 之一。
- `required_path` 默认就是 `/sql/dbcfg.sql`。
- `producer_context` 只用于审计/诊断，不进 digest。

### `SourceDocumentRef`

当前实现里，它是一个内部文档引用，包含：

```text
source_package_id
normalized_path
document_kind
document_content_digest
size_bytes
encoding_hint
entry_manifest_digest
diagnostics
```

要点：

- `document_kind` 目前只支持 `SQL_DUMP`。
- 它不暴露 host path。
- 它可以被后续不同 parser 复用，但第一版只服务 SQL dump。

### `SqlDumpSource`

当前实现里，`SqlDumpSource` 同时保留：

```text
source_document_ref
sql_source_digest
parser_input_contract_version
encoding
source_size_bytes
diagnostics
source_bytes
source_text
```

要点：

- parser 输入稳定性优先于原始容器形态。
- `source_bytes` 和 `source_text` 会互相补齐。
- `sql_source_digest` 是后续 SQL Snapshot cache 的主输入。

### `SnapshotMaterializationInput`

当前实现支持：

```text
source_path
source_sql
sql_dump_source
source_kind
parser_version
parser_input_contract_version
table_ruleset_version
table_rule_registry
scalar_encoding_version
snapshot_materialization_contract_version
summary_contract_version
row_materialization_profile
requested_tables
materialization_policy
cache_policy
```

要点：

- `sql_dump_source` 是最直接的 materialization 输入。
- `requested_tables` 会做 canonical identifier 归一化。
- `cache_policy` 在 SQL path 第一版主要是保留契约位。
- `table_rule_registry` 把表分类、skip/browse/ordered 规则和 key 选择从 materializer 中抽出来，materializer 只消费规则结果；这份默认规则源现在统一落在 `backend_vnext.capabilities.table_rules`，snapshot materialization 只做派生和执行。

### `table_rule_registry`

当前实现把旧规则整理到共享的 `backend_vnext.capabilities.table_rules` 包中，并允许调用方显式传入：

```text
TableRuleRegistry:
  table_ruleset_version
  classify_static_role(table_name)
  key_rule_for_table(table_name, primary_key_columns)
```

默认 registry 仍然内置旧业务的 `SKIP`、`SNAPSHOT_ONLY`、`BROWSE_ONLY`、`STANDARD_DIFF`、`ORDERED_DIFF` 规则，以及常见表的 compare key 覆盖。

Snapshot 专属的处理决策由 `snapshot_materialization.rules.build_table_handling_decision(table_rule_registry, table_name, row_count, has_schema)` 派生。

### `SnapshotMaterializationResult`

当前输出包含：

```text
snapshot
summary
table_set optional
table_artifact_refs optional
cache_diagnostics
diagnostics
```

要点：

- `snapshot.summary` 和返回的 `summary` 在当前实现中保持一致。
- `table_artifact_refs` 是后续 artifact 化的扩展位。
- `cache_diagnostics` 当前主要为空，先为后续 cache 接入留位。

## 当前实现的 digest 边界

当前实现里，几条关键 digest 的分工是：

- `source_package_digest`：表示容器级身份。
- `package_manifest_digest`：表示完整 entry 清单。
- `required_entries_manifest_digest`：表示当前 required entry。
- `document_content_digest`：表示单个文档内容。
- `sql_source_digest`：表示 SQL parser 输入身份。
- `snapshot_digest`：表示 Snapshot 的内容身份。

当前约束是：

- package 物理元数据变化不应改变 SQL Snapshot 结果。
- `/sql/dbcfg.sql` 内容不变时，重复 staging / materialization 应保持稳定。
- `snapshot_id` 仍然是对象引用，不等同于 `snapshot_digest`。

## 当前实现细节

这些是实现细节，不是 contract 承诺：

- `SourcePackage` 当前通过本地 artifact store 持久化 staged payload。
- `SourcePackage` lookup 当前还保留了一个进程内 registry，便于测试和短链路复用。
- `resolve_sql_dump_source` 当前支持 `.sql.gz` compat 输入，适合测试和 benchmark。
- `parse_sql_dump_source` 与 `materialize_sql_dump_source` 共享同一套 SQL parser 输出。
- `resolve_snapshot_table_set` 当前通过重新 materialize 来恢复 reader/table set，而不是单独引入一条新的 reader contract。

这些实现都可以在后续 repository-backed 或分布式场景中替换，但只要稳定 entrypoint 的输入输出不变，外部调用方不需要感知。

## 当前验收关注点

- `stage_source_package` 对同一内容重复执行时，entry manifest digest 应稳定。
- `resolve_required_sql_document` 必须明确失败于缺失或冲突的 `/sql/dbcfg.sql`。
- `resolve_sql_dump_source` 必须能从 staging 结果、裸 SQL、`.sql.gz` 和测试 fixture 中稳定收敛到同一 parser 语义。
- `materialize_sql_dump_source` 必须把 identifier canonical、schema digest 和 raw digest 规则固定下来。
- `resolve_snapshot_table_set` 必须复用已知 Snapshot 语义，不引入新的业务状态。
