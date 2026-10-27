# Identity 与 Digest

本文定义 backend vNext 中业务 ID、内容 digest、内部 ref 和 cache key digest 的边界。设计目标是避免一个字段同时承担业务身份、内容校验、缓存 key 和存储路径。

## 核心原则

1. 业务 ID 表示对象身份，不表示内容完整性。
2. 内容 digest 表示规范化内容身份，不包含 operation、workspace、preview、history request、artifact ref、cache key 或 host path。
3. Ref 表示内部引用，不等同于 digest，也不直接暴露 host path。
4. Cache key digest 只用于 cache registry 索引和诊断，不作为 API contract。
5. Cache 命中后仍必须做内容 digest 校验。

## 业务 ID

业务 ID 用于引用一等对象：

```text
workspace_id
submission_id
operation_id
source_package_id
binding_id
snapshot_id
comparison_id
bundle_id
archive_selection_id
```

规则：

- ID 可以随创建事件变化。
- 同一内容重复上传可以有不同 `source_package_id`。
- ID 不进入内容 digest payload。

## Source Digest

Source digest 分为 package 容器层和 document/parser 输入层。

| Digest | 覆盖内容 | 用途 |
| --- | --- | --- |
| `source_package_digest` | SourcePackage 容器规范身份 | source artifact 审计、重复输入诊断。 |
| `package_manifest_digest` | 完整 package entry 集合、normalized path、entry digest、size/type | 证明系统收到的目录树。 |
| `required_entries_manifest_digest` | 当前流程关心的 required entries | preview/submit binding 和快速复现。 |
| `document_content_digest` | 单个 package entry 内容 | document parser 输入校验。 |
| `sql_source_digest` | SqlDumpSource 的 SQL parser 输入 | SQL Snapshot materialization cache key；当前业务默认由 `/sql/dbcfg.sql` 派生。 |
| `composite_logic_source_digest` | `/comps/logic/logics.xml` 内容或稳定 EMPTY marker | 正式业务 Snapshot identity。 |

规则：

- 当前业务 package 是多目录多文件包；正式业务 Snapshot 消费唯一 `/sql/dbcfg.sql` 与可选 composite XML，通用 SQL-only 入口仍可直接消费 `SqlDumpSource`。
- SQL Snapshot materialization 主要依赖 `sql_source_digest`，不直接依赖整个 zip bytes digest。
- zip entry 顺序、压缩参数、mtime 等物理元数据变化不应改变 SQL Snapshot。
- composite XML 变化必须改变业务 Snapshot identity；其他 unconsumed package files 不进入业务 Snapshot digest。

这些 digest 都不参与：

```text
source_package_id
workspace_id
operation_id
upload generation
host path
临时文件名
cache key
```

兼容说明：旧草案中的泛称 `source_digest` 在具体 contract 中应拆成上述更精确的 digest；如果短期代码仍保留 `source_digest` 字段，必须在字段说明中标明它等价于 package 层还是 document/parser 输入层。

## Snapshot Digest

`snapshot_digest` 表示一次可比较配置状态的规范化内容身份。它必须是 flow-neutral 的，同一可比较状态不应因为来自 upload、submit 或 history compare 而不同。

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
repository_id
repository_ref
workspace_id
operation_id
artifact_ref
cache_key
host path
diagnostics
```

## Raw 与 Business Digest

`raw_state_digest` 表示 schema-independent 的规范化 raw table state，由表名、行数与 `raw_content_digest` 组成；它不等同于含 business schema 的规范状态摘要。`raw_content_digest` 缺失时，raw state 仍记录该表的行数与缺失摘要状态。

`business_state_digest` 表示应用 table rules 后的业务等价状态，可用于 summary early exit。第一阶段字段应落地，但允许部分表或部分规则返回 `NOT_COMPUTED`。

规则：

- `business_state_digest` 不能替代 raw 校验。
- ignored column 变化可以保持 business digest 不变，但不能伪装 raw digest 不变。
- row order 无业务意义的表不应让纯顺序变化影响 raw digest 或 business digest。
- raw digest 只表达按 canonical column-name mapping 还原后的 row content，不表达显示顺序。

## Table Digest

表级 digest 分为 schema、content 和 DDL 事实。

| Digest | 用途 | 说明 |
| --- | --- | --- |
| `source_ddl_digest` / `raw_ddl_digest` | 审计、诊断、Dolt import source identity | 基于原始 `CREATE TABLE` 或规范化 DDL facts；不进入业务 `snapshot_digest`。 |
| `compare_schema_digest` | 业务 schema 判定和 provider planning | 基于 canonical 字段集合和 compare key，不包含 comment、engine、charset、字段顺序等细节。 |
| `raw_content_digest` | raw row 内容校验 | 覆盖 canonicalized full rows；row order 和 field order 不影响结果。 |
| `business_content_digest` | 业务等价内容 | 应用 table rules / ignored columns / projection 语义后计算；可为 `NOT_COMPUTED`。 |
| `artifact_content_digest` | 物理 artifact 校验 | 校验 Parquet/CSV/manifest 等 artifact 文件，不替代 raw content digest。 |
| `row_layout_digest` | 表导出布局复用 | 由 canonical raw content digest 和 canonical export schema content 组成，用于 row file / export IO cache 命中；不包含 table name 或 compare key 语义。 |
| `projection_schema_digest` | projection schema 校验 | 由 `contracts/comparison.md` 定义，基于规则加工后的 compare-ready schema。 |
| `projection_logical_digest` | projection 内容校验 | 由 `contracts/comparison.md` 定义，基于规则加工后的 compare-ready rows。 |

`content_digest` 如果作为短名出现，应等价于 `raw_content_digest`。

在 upload / export build 阶段，artifact builder 应使用 `row_layout_digest` 作为物理 row file 复用键；它可以作为 row file / export IO cache 命中依据，但不应把 table name 或 compare schema 语义混入这个键里。

### Provenance / Diagnostics

- `table_raw_sql_digest`：upload parse 阶段的 raw SQL hash，用于诊断、回放和粗粒度路由，不替代语义 digest。
- `base_table_fingerprint`：表级 provenance / 身份元数据，可用于展示和诊断。
- 这些字段可以由 `table_raw_sql_digest`、parser diagnostics 或 replay metadata 派生或携带，但不应进入 `raw_content_digest` 的语义定义，也不应替代 `row_layout_digest` 作为主判据。
- `canonical_artifact_ref` / `previous_canonical_artifact_ref` 如果存在，应视为 finalized summary metadata，而不是 digest 输入或 digest 结果的一部分。

Projection digest 不进入当前 Snapshot materialization 的第一版 contract。它由 `contracts/comparison.md` 定义，输入应包含 raw table facts、table ruleset、compare key、ignored columns、scalar normalization 和 projection contract version。

## Schema Digest Policy

原始 `CREATE TABLE` 是 schema facts 的来源，但业务 schema change 不直接比较整段 DDL。

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

标识符 canonical 规则：

```text
canonical_identifier = case-insensitive normalized identifier
display_identifier = 原始 DDL 中的名字
```

大小写变化不算 schema change。字段顺序无业务意义。

降级规则：

- 同一张表中字段名 canonical 后冲突，表级降级，原因 `IDENTIFIER_CANONICAL_CONFLICT`。
- 明显不兼容字段类型变化，例如 `int -> varchar`，不做复杂类型族和值等价处理，表级降级，原因 `COLUMN_TYPE_INCOMPATIBLE`。
- DDL 不支持解析或关键 facts 缺失，表级降级。

降级表不阻塞其他表比较。前端应展示风险/诊断。

## Ref

Ref 是内部引用：

```text
artifact_ref
storage_ref
repository_ref
download_ref
```

规则：

- Ref 不等同于 host path。
- Ref 不进入内容 digest。
- API 不暴露 host path。
- Repository ref 需要能解析到 immutable commit/hash 后才能作为 L2 业务事实来源。

## Cache Key Digest

`cache_key_digest` 是 cache key payload 的摘要，用于 registry 索引和 operation diagnostics。

规则：

- cache key payload 可包含输入事实、能力版本和输出 contract。
- cache key 不包含 operation id、workspace id、preview id、history operation id、host path 或临时目录。
- diagnostics 不记录完整 SQL payload 或敏感原始 key payload。

Cache key digest 只描述候选内容地址；cache entry 是否可被某个 flow 采用，还需要结合 `validation_status`、producer phase 和调用方 lookup policy。
