# Snapshot Table Access Contract

本文定义 `SnapshotTableSet`、`SnapshotTableReader`、`SnapshotTableArtifact` 和 raw table artifact cache 的边界。它们是 Snapshot 行数据访问层，不是 repository/Dolt 写入层。

## SnapshotTable

```text
SnapshotTable:
  descriptor: SnapshotTableDescriptor
  reader: SnapshotTableReader
  source_ref optional
  diagnostics optional
```

规则：

- `SnapshotTable` 是 capability 边界上的 L0 逻辑对象。
- Descriptor 表达表事实；reader 提供 row stream。
- `SnapshotTable` 不表达业务流程状态，也不等同于 cache entry。

## SnapshotTableSet

```text
SnapshotTableSet:
  snapshot_id
  snapshot_digest
  table_ruleset_version
  tables:
    table_name -> SnapshotTable
  resolution_plan
  diagnostics
```

规则：

- 默认是 L0 逻辑对象。
- 支持 lazy resolution。
- 同一 set 可以混合 SQL parser、repository export/readback、table artifact、cache artifact 等 reader 来源。
- 必须与 `SnapshotSummary` 的 table facts 一致。
- `SnapshotTableSet` 不直接作为业务事实持久化。

## SnapshotTableReader

Reader 同时提供 full-row streaming 与精确单列值计数。后者用于只需要完整性摘要、但不需要行内容的消费方。

```text
SnapshotTableReader:
  descriptor() -> SnapshotTableDescriptor
  iter_rows() -> RowIterator
  count_column_values(column_name) -> SnapshotColumnValueCounts
  close()
```

`SnapshotColumnValueCounts` 包含 canonical `column_name`、原始 scalar `value -> row count`、`total_row_count` 和内部读取策略。计数必须覆盖所有行并包含 `NULL`；业务层自行决定是否忽略或转换某类值。

约束：

- row 使用规范化 scalar encoding。
- reader 输出按 descriptor canonical columns 映射的完整 row。
- reader 应能在需要时校验 `raw_content_digest`，但这可以放在显式 validation/readback 阶段，不要求 reader init 阶段完成。
- `reader init` 应尽量保持轻量，只负责 descriptor、row stream 句柄和预览所需元数据准备，不应把 canonical digest 校验耦合进对象构造。
- reader 可以持有 deferred row source，并在第一次 `iter_rows()`、`rows` 访问或 digest 校验时才 materialize rows；这类 lazy reader 依然必须对外表现为稳定的 full-row streaming。
- reader 不暴露 host path、Dolt internal path 或 cache key。
- reader 不拼接 SQL literal。
- reader 不管理 Dolt branch、server、commit 或 ref。
- 第一版要求调用方能够重新打开 reader；不强制同一个 reader 支持 rewind。
- 单列计数不得为了生成 cache key 触发完整 content digest 计算；只有 descriptor 已携带不可变 content/raw SQL/fast-row digest 时才允许持久缓存。
- SQL reader 只解析目标 INSERT literal，Parquet reader只投影目标列，repository reader将聚合下推到 provider，内存 reader只访问目标列。优化路径不可用时调用方可以回退 full-row streaming，但不得把失败解释为空表。

### Row Path First

- `SnapshotTableReader` 是 repository-backed row access 的第一选择，调用方应优先消费 row stream，再决定是否做 snapshot、diff 或 artifact 打包。
- repository source provider 不需要把 row access 先转成文件再回读；只要能稳定输出 canonical rows，就满足第一版 contract。
- `SnapshotTableArtifact` 或其它物理化产物可以由上层在需要时再派生，不要求 repository server 在第一版把导出格式矩阵纳入主职责。

未来可选扩展：

```text
PredicatePushdownReader
```

通用多列 projection 和 predicate pushdown 仍不是当前 contract；精确单列计数是已落地的受限统计能力，不扩展为任意查询接口。

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

规则：

- artifact manifest 必须能还原 `SnapshotTableDescriptor + SnapshotTableReader`。
- `artifact_content_digest` 校验物理文件，不替代 `raw_content_digest`。
- artifact 可作为 cache artifact；调用方对外声明 READY 前需要的 artifact 必须进入调用方自己的 artifact closure。
- `SnapshotTableArtifact` 是 raw table materialization，不包含 ignored columns、effective key 修正后的 projection 语义。

## 与 Repository Import 的边界

`SnapshotTableReader` 需要提供足够的导入输入事实：

- canonical table name。
- raw CREATE TABLE / DDL facts。
- canonical columns 和 scalar encoding。
- row stream。
- row count、compare schema digest、raw content digest。
- primary key / compare key hints。

但 `SnapshotTableReader` 不负责：

- 选择 Dolt import provider。
- 拼接 SQL import statements。
- 生成 CSV/TSV/Parquet staging artifact。
- 启动或关闭 Dolt server。
- 管理 writer lease、commit、branch 或 ref。

这些职责属于 `repository_import` capability。`RepositoryImportArtifact` 可以由 `SnapshotTableReader` streaming 生成，也可以从 `SnapshotTableArtifact` 转换得到。

## Snapshot Table Artifact Cache

`snapshot_table_artifact_cache` 只缓存 raw table materialization。

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
- Cache key 不包含 flow ID、operation ID、preview ID、workspace ID、table name 或 host path。
- `row_layout_digest` 由 canonical raw content digest、完整源列编码 schema 与 ordered row metadata 组合而成；table name 不进入 digest。源列类型、ENUM/SET 标签、nullability 或 Parquet 字段布局变化会改变 layout。Repository scope 与 Parquet writer contract version 是 export cache 的独立键字段。
- `PROVISIONAL` candidate 只能作为候选加速输入，不能作为业务事实。
- 调用方允许读取 `PROVISIONAL` candidate 时，必须重新校验 source binding、descriptor 和 digest，并具备 fallback recompute 路径。
- Repository/readback 或等价权威校验通过后，cache entry 才能 promote 为 `COMMIT_VALIDATED`。
- `READ_COMMIT_VALIDATED_ONLY` lookup policy 只读取 `COMMIT_VALIDATED` 或 repository readback 产生的 cache。

S1b 的 Parquet export cache 是独立的可重建 IO cache：精确键为 repository scope、`row_layout_digest` 与
`parquet_writer_contract_version`。layout digest 覆盖完整源列编码 schema 和 ordered row metadata；layout 或 writer 版本不同不得命中。
命中行文件经 `artifact_protection_intents` 登记并按 TTL 延长/释放保护，过期清理由有界 prune 完成；
cache miss、损坏引用或 Parquet 校验失败时回退到规范表读取与导出。Cache ref 不进入 surface 或 bundle，
对外产物仍需闭合为当前 operation 或 bundle 的相对引用。

## SQL Reference Parser Semantics

参照解析器拒绝 BIT 负数、超宽值与非 ASCII `b'..'`，并以确定诊断报告；BIT 数字字面量按十进制解释。
`_binary` 后接字符串或十六进制字面量，只能写入 BINARY、VARBINARY、BLOB 系列列；`\%` 与
`\_` 保留反斜杠。列类型中的 SQL 注释被忽略。JSON 拒绝 `NaN`、`Infinity`、孤立代理与超过
100 层嵌套的值，深度检查以迭代方式完成。零日期与零日期时间保持拒绝。

## Projection Table Boundary

Projection table 是 comparison-derived artifact，不属于 `SnapshotTableArtifact`。

```text
SnapshotTableArtifact
  raw snapshot table materialization
  面向 summary、bundle、repository import、comparison fallback

ProjectionTableArtifact
  comparison-derived table materialization
  面向 comparison_compute / provider planning / native projection diff
```

规则：

- Projection artifact 由 `SnapshotTableArtifact + table_ruleset` 或 `SnapshotTableReader + table_ruleset` 派生。
- ignored columns、effective primary key、schema intersection 和 projection row identity 由 `contracts/comparison.md` 定义。
- `projection_table_cache` 不并入 `snapshot_table_artifact_cache`。
- 第一阶段只能预留 boundary，不要求实现 projection cache。

## 验收标准

- `SnapshotTableReader` 能 streaming 大表，不要求一次性读入内存。
- Reader digest 校验失败时，该表 resolution 或 validation 明确失败。
- `SnapshotTableSet` 与 `SnapshotSummary` 的 descriptor/digest 一致。
- 删除 L3 cache 后，仍能从 L1 source package 或 L2 repository ref 重建 table access。
- Cache hit 后仍校验 descriptor、digest 和 artifact manifest。
- `SnapshotTableReader` contract 测试不依赖 Dolt 写入。
- Repository import benchmark 应调用正式 table access / artifact builder，不长期维护独立 row/digest 实现。
