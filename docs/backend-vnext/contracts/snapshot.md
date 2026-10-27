# Snapshot Contract

本文定义 `Snapshot`、`SnapshotSummary`、`SnapshotTableDescriptor` 和 schema policy。`Snapshot` 表示一次 flow-neutral 的可比较配置状态，不表达 package 容器，也不表达具体 row reader 或 artifact 位置。

## Snapshot

```text
Snapshot:
  snapshot_id
  source_kind: SQL_DUMP_SOURCE | DOLT_COMMIT | IMMUTABLE_REPOSITORY_REF | EXISTING_SNAPSHOT
  source_package_id optional
  source_document_ref optional
  repository_id optional
  repository_ref optional
  parser_version
  table_ruleset_version
  scalar_encoding_version
  snapshot_materialization_contract_version
  row_materialization_profile
  materialization_stage: PROVISIONAL | FINAL
  snapshot_digest
  raw_state_digest
  business_state_digest optional
  summary_ref optional
  source_context optional
  created_at
  diagnostics_ref optional
```

规则：

- `snapshot_id` 是对象引用 ID，不等同于 `snapshot_digest`。
- `snapshot_digest` 是 flow-neutral 内容身份。
- `materialization_stage=PROVISIONAL` 的 Snapshot / SnapshotSummary 只表示 upload-local provisional fact，不应作为最终 compare / export / persistence 事实。
- `materialization_stage=FINAL` 才代表 canonical fact，能够进入后续稳定链路。
- Snapshot 不包含 full rows、artifact path、cache key、operation id 或 host path。
- 调用方可以把 Snapshot 记录为 L1 execution/source fact；是否可被 supersede 由 flow/operation 层决定。
- immutable repository snapshot/ref 是 L2 业务事实来源。
- Snapshot 成功创建不表示 comparison、risk、bundle 或 repository import 已 ready。

## SnapshotSummary

```text
SnapshotSummary:
  snapshot_id
  snapshot_digest
  raw_state_digest
  business_state_digest optional
  materialization_stage: PROVISIONAL | FINAL
  parser_version
  table_ruleset_version
  summary_contract_version
  table_count
  row_count_total optional
  tables:
    - SnapshotTableDescriptor
  missing_or_unsupported_tables optional
  source_context:
    source_kind
    source_package_digest optional
    sql_source_digest optional
    composite_logic_source_digest optional
    source_document_ref optional
    repository_ref optional
  diagnostics
```

用途：

- Provider planning。
- Summary early exit。
- Digest 校验。
- 按需 resolution `SnapshotTableSet`。

规则：

- Summary 不包含 full rows。
- Summary 的 FINAL 事实应可作为 repo 内隐藏系统表持久化，并可被 history compare / archive readback 读取。
- Summary 可做 index/cache，但 cache 只负责 readback 加速，不是事实本身。
- `PROVISIONAL` summary 仅用于 upload-local 快判、preview packaging 或异步补齐前的中间态。
- Summary 中的 table digest 必须能被 `SnapshotTableSet` 逐表校验。
- FINAL duplicate group 可由 `tables[].canonical_artifact_ref` 推导：同一 ref 下的 logical tables 共享 canonical 数据。
- PROVISIONAL summary 不产生 FINAL `canonical_artifact_ref`；upload preview 如需 alias，只能使用 flow-local `PROVISIONAL_FAST` mapping。

## Canonical Hidden Summary Table

FINAL SnapshotSummary 的 canonical 事实应在 repository commit/ref 内以隐藏系统表持久化。
这张表是 protected derived fact，不是业务比较表，也不进入普通 table listing。

建议语义：

- 每个业务表一行，外加少量 snapshot 级头信息。
- 由 submit finalize 在 readback validation 通过后写入。
- 由 history compare / archive 以只读方式读取。
- cache 可以加速读取，但 cache miss 时必须还能从 repo readback。
- 缺失、损坏或版本不匹配应视为完整性错误，而不是 summary 重建机会。

建议承载的 compare-ready facts：

- `snapshot_id`
- `repository_id`
- `repository_ref`
- `source_kind`
- `table_name`
- `table_role`
- `compare_key_columns`
- `compare_schema_digest`
- `raw_content_digest`
- `business_content_digest`
- `row_count`
- `degraded_reason`
- `projection_status`
- `canonical_artifact_ref`
- `previous_canonical_artifact_ref`

## SnapshotTableDescriptor

```text
SnapshotTableDescriptor:
  table_name
  display_table_name optional
  table_role optional
  columns:
    - name
      display_name optional
      column_comment optional
      scalar_type optional
      nullable optional
  primary_key_columns
  compare_key_columns
  row_count
  materialization_stage: PROVISIONAL | FINAL
  source_ddl_digest optional
  raw_ddl_digest optional
  compare_schema_digest
  raw_content_digest
  business_content_digest optional
  table_ruleset_version
  row_materialization_profile
  scalar_encoding_version
  degraded_reason optional
  table_raw_sql_digest optional
  base_table_fingerprint optional
  canonical_artifact_ref optional
  previous_canonical_artifact_ref optional
  projection_digests optional:
    - SnapshotProjectionDigest
  diagnostics optional
```

规则：

- `table_name` 和 `columns.name` 使用 canonical identifier。
- `display_*` 保留原始 DDL 标识符用于导入、展示和诊断；列注释单独保存在 `column_comment`，不得复用 `display_name`。
- `primary_key_columns` 表达原始 DDL 主键；`compare_key_columns` 表达 table rules 解析后的比较键，两者可以不同。
- `column_comment`、原始标识符和 presentation rules 不进入 compare schema、content、projection、risk 或 row-layout digest。
- `source_ddl_digest` / `raw_ddl_digest` 不进入业务 `snapshot_digest`。
- Snapshot digest 的每表输入只包括可由表描述与 manifest 获得的事实：表名、比较 schema 摘要、业务 schema 摘要、比较键、行数与表摘要。Repository-ref 未读行的描述必须与读行描述逐字段相同；上传、Preview 基线与 History 使用同一算法。
- `materialization_stage=PROVISIONAL` 时，`raw_content_digest` 可以暂缺；FINAL materialization 必须提供 `raw_content_digest`。
- `materialization_stage=FINAL` 时，`raw_content_digest` 必须存在。
- `compare_schema_digest` 只表达 canonical 字段集合和 compare key 选择，不表达字段顺序。
- `raw_content_digest` 表达 canonicalized raw rows，row order 和 field order 不应改变结果。
- `row_layout_digest` 是 row file / export IO cache 的物理复用键，基于 canonical raw content digest 和 canonical export schema content 组合而成；它不应混入 table name 或 compare schema 语义。
- Descriptor 不包含 full rows。
- Descriptor 可以包含可选的 `projection_digests` 派生摘要；它属于该真实 logical table 的 compare-ready projection summary，不是独立 summary table row，不增加 `SnapshotSummary.table_count` 或 `row_count_total`。缺失该字段表示没有预计算 projection 摘要，comparison 必须回退正常 projection 路径。
- Descriptor 不包含 artifact path、cache key、operation id 或 host path。
- `canonical_artifact_ref` 只在 FINAL summary 中表达当前 logical table 所属 canonical group / artifact。
- `previous_canonical_artifact_ref` 只保留上一版映射的单跳指针；summary 不保存完整 group history。
- 分组变化后不得因后续内容再次相同而自动回退旧 ref，除非上层业务显式 resolution 允许 merge。

### SnapshotProjectionDigest

```text
SnapshotProjectionDigest:
  projection_schema_digest
  selected_columns
  ignored_columns
  effective_compare_key
  row_identity_columns
  row_identity_digest
  projected_row_value_digest
  projection_logical_digest
  table_ruleset_version
  projection_contract_version
  scalar_encoding_version
  digest_authority: FINAL | PROVISIONAL_FAST
```

规则：

- 第一版仅允许为 `STANDARD_DIFF` 且存在有效 compare key 的表生成；`SKIP`、`SNAPSHOT_ONLY`、`BROWSE_ONLY`、`ORDERED_DIFF` 和无 key 表不生成。
- 生成由 materialization 的 `projection_digest_policy` 显式控制，默认 `DISABLED`；upload preview / provisional materialization 默认不生成 `PROVISIONAL_FAST` projection digest。
- `FINAL_ONLY` 仅在 final materialization 中生成 `FINAL` authority；`PROVISIONAL_AND_FINAL` 保留当前 provisional + final 实验路径，不是正式 upload preview 默认成本。
- `FINAL` authority 可用于正式/history/final comparison；`PROVISIONAL_FAST` 只允许 upload preview/provisional comparison 使用。
- Comparison core 只有在实际 `projection_schema_digest`、ruleset/projection/scalar 版本和允许 authority 全部匹配时才能复用该摘要。
- 摘要只能替代 projection logical digest 的 normalize/hash 计算，或在 before/current projection digest 相同的场景证明业务等价；需要行级 records 时仍必须读取 rows 并构造 projection rows。
- Projection digest 不替代 raw digest、canonical artifact ref、row artifact closure 或行级 diff records。

### Provenance / Diagnostics

- `table_raw_sql_digest` 可以作为 parser / replay / diagnostics metadata 保留。
- `base_table_fingerprint` 可以作为 table-level provenance metadata 保留。
- 这些字段不进入 `snapshot_digest`、`row_layout_digest` 或 row file / export IO cache 的主判据链。
- `base_table_fingerprint` 可辅助 candidate grouping，但 FINAL 权威分组以 `canonical_artifact_ref` 为准。

## Snapshot Digest Payload

建议 payload：

```text
snapshot_digest_payload:
  digest_contract_version
  materialization_stage
  parser_version
  table_ruleset_version
  scalar_encoding_version
  snapshot_materialization_contract_version
  row_materialization_profile
  tables:
    - canonical_table_name
      compare_schema_digest
      business_schema_digest
      compare_key_columns
      row_count
      raw_content_digest
  composite_logic_source_digest optional
  composite_signal_contract_version optional
```

不参与：

```text
snapshot_id
source_package_id
source_document_ref
repository_id
repository_ref
workspace_id
operation_id
artifact_ref
cache_key
host path
diagnostics
```

## Schema Policy

原始 `CREATE TABLE` 是 schema facts 来源，但业务 schema change 由 compare schema facts 判定。

进入 `compare_schema_digest`：

```text
canonical table name
canonical column name set
canonical compare key / primary key set
```

不进入 `compare_schema_digest`：

```text
字段 COMMENT
表 COMMENT
ENGINE
AUTO_INCREMENT
CHARSET
CHECKSUM
字段类型长度或细节，例如 varchar(64) -> varchar(128)
字段顺序
raw_ddl_digest
```

Identifier 规则：

- 业务大小写不敏感。
- 大小写变化不算 schema change。
- 字段顺序无业务意义。
- table ruleset 中的 compare key 也按 canonical identifier 匹配。

Key 规则：

```text
table_ruleset compare_key > DDL primary key > fallback key policy
```

Schema mismatch policy：

- key 未变时，两侧只比较共有字段。
- before-only/current-only columns 不进入 row diff，但进入前端风险和 diagnostics。
- key 变化时，该表视为全表变化或降级为 key-changed table-level change。
- 共有字段为空时，输出 schema-only change。

Degraded table policy：

- identifier canonical 后冲突：`IDENTIFIER_CANONICAL_CONFLICT`。
- 明显不兼容字段类型变化，例如 `int -> varchar`：`COLUMN_TYPE_INCOMPATIBLE`。
- DDL 不支持解析或关键 facts 缺失：`UNSUPPORTED_SCHEMA`。

降级表不阻塞其他表比较。前端应展示风险。

## Raw 与 Business Digest

`raw_state_digest` 由表名、行数与 `raw_content_digest` 组成，不包含 schema；`raw_content_digest` 表示规范化 raw rows，含重复行但忽略无业务意义的行顺序。

`business_state_digest` / `business_content_digest` 表示应用 table rules 后的业务等价状态。第一阶段字段应落地，但允许部分表或部分规则返回 `NOT_COMPUTED`；如果尚未引入额外 business normalization，可以与 raw digest 相同。

规则：

- business digest 不能替代 raw 校验。
- ignored column 变化可以保持 business digest 不变，但不能伪装 raw digest 不变。
- row order 无业务意义，不应让纯顺序变化影响 raw digest 或 business digest。
- projection digest summary 是 `SnapshotTableDescriptor.projection_digests[]` 的派生摘要；完整 projection rows / projection table artifact 仍由 `contracts/comparison.md` 定义。

## 验收标准

- 同一 SQL source、parser version、table ruleset 和 materialization contract 下，重复 materialization 得到相同 `snapshot_digest`。
- `SnapshotSummary` 可独立用于 provider planning，不打开 row reader。
- 字段大小写或字段顺序变化不触发业务 schema change。
- `varchar(64) -> varchar(128)` 等普通字段类型细节变化默认不触发业务 schema change。
- canonical row 内容变化会改变 `raw_content_digest` 和 `raw_state_digest`。
- 仅调整 row order 或 field order 不改变 raw digest。
- 极端 schema 情况按表级降级处理，不做复杂类型族和值等价推理。
