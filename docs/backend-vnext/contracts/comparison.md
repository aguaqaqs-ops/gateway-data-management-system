# Comparison Contract

> v2 增加 `comparison_mode`、project identity assessment digest 和 `REPLACED` table status。v3 定义 schema 演进分类与整表新增/删除不生成逐行记录。formal upload 在 `DIFFERENT_PROJECT` 时使用 `DATASET_REPLACEMENT`，不生成 records closure；完整规则见 `../capabilities/project-identity-and-dataset-replacement.md`。

本文定义 backend vNext 第一版 directed comparison contract。Comparison 只消费已经物化的 Snapshot/Summary/Table access，不解析 SourcePackage，不执行 repository import，不生成风险结论或前端 surface。

## 范围

Comparison 负责：

- 接收 before/current 两侧 `ComparisonInput`。
- 基于 `SnapshotSummary` 做 summary early exit 和 provider planning。
- 将 raw `SnapshotTable` 按 table rules 投影为 compare-ready `ProjectionTable`。
- 计算表级、schema 级和行级 diff facts。
- 输出 flow-neutral `ComparisonFacts` 和可选 records artifacts。

Comparison 不负责：

- 解析 SourcePackage、SqlDumpSource 或 SQL。
- 写 Dolt repository、创建 commit/ref 或管理 writer lease。
- 计算 RiskEvaluation。
- 组装 ComparisonSurface、WorkbenchBundle 或前端专用 wrapper。
- 推进 Workspace、Submission、History request 等业务状态。

## 对象链路

```text
before ComparisonInput + current ComparisonInput
  -> DirectedComparisonInput
  -> ComparisonPlan
  -> ProjectionTable pair per table
  -> ComparisonFacts
  -> optional ComparisonRecords artifacts
  -> RiskEvaluation / ComparisonSurface / Bundle
```

规则：

- Comparison 是有向比较，方向固定为 `before -> current`。
- 方向影响 added/deleted、risk 和展示语义。
- Comparison contract 不关心两侧 Snapshot 来自 upload、submit、history compare 还是 repository ref。
- Provider 可以不同，但输出必须统一成 `ComparisonFacts`。

## Repository-backed Inputs

ComparisonInput 固定以 Snapshot 为输入。Repository/Dolt ref 必须先经过 `snapshot_materialization.repository_ref_materialization`，得到 `Snapshot + SnapshotSummary + optional SnapshotTableSet` 后才能进入 comparison。

路径：

```text
Dolt RepositoryRef
  -> repository_ref_materialization
  -> SnapshotSummary + SnapshotTableSet
  -> ComparisonInput

SqlDumpSource
  -> snapshot_materialization
  -> SnapshotSummary + SnapshotTableSet
  -> ComparisonInput
```

输入组合：

| Pair | 处理方式 |
| --- | --- |
| SQL -> SQL | before/current 都通过 SQL materialization 变成 Snapshot，再比较。 |
| Dolt -> SQL | Dolt ref 先 materialize 为 before Snapshot；SQL source materialize 为 current Snapshot。 |
| SQL -> Dolt | SQL source materialize 为 before Snapshot；Dolt ref 先 materialize 为 current Snapshot。 |
| Dolt -> Dolt | 第一版 fallback 是两侧都 materialize 为 Snapshot；`DOLT_NATIVE` 是后续优化 provider。 |

规则：

- Comparison provider 不直接调用 repository server `list_tables`、`describe`、`count`、`export` 或 `select`。
- 表清单只能来自 `ComparisonInput.summary`。
- 行数据只能通过 `ComparisonInput.table_set_ref` / `SnapshotTableReader` 请求。
- repository_server 的 catalog/session/cache 是 snapshot materialization 的实现细节，不进入 `comparison_digest`。
- `DOLT_NATIVE` 即使绕过部分 SnapshotTableReader IO，也必须输出同一 `ComparisonFacts` contract，并接受同等 validation。

## ComparisonInput

```text
ComparisonInput:
  role: BEFORE | CURRENT
  snapshot
  summary
  table_set_ref optional
  table_access_policy:
    SUMMARY_ONLY | TABLE_READERS_ON_DEMAND | TABLE_READERS_REQUIRED
  source_context optional
  diagnostics optional
```

规则：

- `ComparisonInput` 不直接持有 full rows。
- `table_set_ref` 是按需打开 reader 的内部引用，不是 host path。
- `role` 不进入 `snapshot_digest`。
- Comparison 不直接消费 SourcePackage、SqlDumpSource 或 RepositoryImportArtifact。
- 同一 Snapshot 可以在不同 comparison 中扮演不同 role。

## DirectedComparisonInput

```text
DirectedComparisonInput:
  before: ComparisonInput
  current: ComparisonInput
  comparison_contract_version
  projection_contract_version
  table_ruleset_version
  scalar_encoding_version
  requested_tables optional
  comparison_options
  cache_policy
  cache_lookup_policy
  validation_status_policy
  artifact_policy
```

`comparison_options` 第一版只允许影响 comparison 语义的稳定选项：

```text
comparison_options:
  include_unchanged_tables: true | false
  row_diff_detail_policy:
    COUNTS_ONLY | CHANGED_COLUMNS | FULL_BEFORE_AFTER_VALUES
  max_inline_record_count optional
```

规则：

- ignored columns、compare key override、有序表策略等应属于 versioned table ruleset，而不是临时 request option。
- `comparison_options` 进入 `comparison_digest` 和 `comparison_core_cache` key。
- `max_inline_record_count` 只影响 records 内联与 artifact 分流，不应改变 diff facts 内容；如果实现难以保证，应进入 cache key。
- 输入中的业务对象 ID、operation ID、request ID、host path 不进入 digest 或 cache key。

## Summary Early Exit

第一版允许在不打开 row reader 的情况下做 early exit。

Pair 级 early exit：

- before/current `snapshot_digest` 相同。
- `table_ruleset_version`、`comparison_contract_version`、`projection_contract_version` 和 comparison semantic options 相同。

Table 级 early exit：

- 两侧均存在同名 table。
- `compare_schema_digest` 相同。
- `row_count` 相同。
- `raw_content_digest` 相同。
- 相关 table rules 不要求额外 projection normalization。

结果：

- Pair 级 early exit 可直接输出 `UNCHANGED` comparison summary。
- Table 级 early exit 可输出 table status `UNCHANGED`，不读取 rows。
- 如果 only business digest 相同但 raw digest 不同，可输出 `BUSINESS_EQUIVALENT`，但不能伪装 raw unchanged。

## Summary-Driven Alias Reuse

Comparison planner 可以基于 summary alias mapping 跳过重复表的投影、row compare、records 和 cache 生成。

Alias scope：

```text
PROVISIONAL_FAST
CANONICAL
```

规则：

- `CANONICAL` alias 来自 FINAL summary 中相同的 `canonical_artifact_ref`，可用于 repository readback、history compare 和 archive 前的正式 compare。
- `PROVISIONAL_FAST` alias 来自 upload preview 的 fast 判据，只能用于 preview compare、preview bundle 和 preview cache。
- alias member 不执行真实 row compare；planner 只对 canonical table 建 projection/provider/records。
- alias member 的 table fact 由 canonical result 加 logical table metadata 派生，不能改变 comparison status 或 records digest。
- `SKIP`、`BROWSE_ONLY`、`SNAPSHOT_ONLY` 等不进入业务 compare 的表仍由 table rules 先过滤，alias reuse 不覆盖表规则。
- 当 alias mapping 缺失、不一致、scope 不允许或 canonical table 结果不可用时，必须回退普通 per-table compare 或降级，不能伪造 unchanged。

## ProjectionTable

`ProjectionTable` 是 raw `SnapshotTable` 应用 table rules 后的 compare-ready 逻辑表。它是 comparison-derived 对象，不属于 raw `SnapshotTableArtifact`。

```text
ProjectionTable:
  source_snapshot_digest
  source_table_name
  projection_schema
  projection_logical_digest optional
  row_count
  reader optional
  artifact_ref optional
  diagnostics optional
```

### ProjectionSchema

```text
ProjectionSchema:
  table_name
  selected_columns
  ignored_columns
  before_only_columns optional
  current_only_columns optional
  effective_compare_key
  projection_schema_digest
  table_ruleset_version
  projection_contract_version
  scalar_encoding_version
```

规则：

- `selected_columns` 默认是 before/current 两侧 canonical column name 交集，再移除 ignored columns。
- before-only/current-only columns 不进入 row diff，但进入 schema diagnostics 和前端风险输入。
- 字段顺序无业务意义；projection schema digest 按 canonical set 和 effective key 计算。
- 字段大小写变化不算 schema change。
- 普通字段类型细节默认不进入 projection schema digest。

### Effective Compare Key

Key 选择：

```text
table_ruleset compare_key > DDL primary key > fallback_key_policy
```

第一版 fallback 策略：

```text
fallback_key_policy:
  DEGRADE_NO_COMPARE_KEY
  FULL_ROW_DIGEST_SET_DIFF optional
```

建议默认使用 `DEGRADE_NO_COMPARE_KEY`，不猜测业务 row identity。`FULL_ROW_DIGEST_SET_DIFF` 只能用于明确允许“整行集合差异”的表；它只能表达 added/deleted，不能把一行内容变化解释成 modified。

如果两侧在相同比较语义版本下的 canonical digest 已经一致，表可以直接 early-exit 为 `UNCHANGED`，不必先走 `NO_COMPARE_KEY` 的降级分支；`DEGRADE_NO_COMPARE_KEY` 只适用于 digest 不一致且确实没有可用 key 的情况。

降级规则：

- effective key 在任一侧不存在：`EFFECTIVE_KEY_MISSING`。
- effective key 被 ignored columns 移除：`EFFECTIVE_KEY_IGNORED`。
- effective key 后出现重复 key：`EFFECTIVE_KEY_DUPLICATE`。
- before/current effective key 不一致：`EFFECTIVE_KEY_CHANGED`，可输出全表变化或表级降级。
- selected columns 为空：输出 schema-only change，不做 row diff。

## Projection Digest

```text
projection_schema_digest
projection_logical_digest
```

`projection_schema_digest` 输入：

- canonical table name。
- selected columns。
- ignored columns。
- effective compare key。
- table ruleset version。
- projection contract version。
- scalar encoding version。

`projection_logical_digest` 输入：

- projection schema digest。
- projected rows。
- row identity digest。
- normalized scalar values。

规则：

- projection logical digest 不受 row order 影响。
- raw digest 不变、projection schema digest 不变时，可以复用 projection table。
- SnapshotTableDescriptor 可以携带可选的 `projection_digests[]` 派生摘要；comparison core 在构造 ProjectionTable 前可按 `projection_schema_digest + table_ruleset_version + projection_contract_version + scalar_encoding_version + digest_authority` 做 exact lookup。
- lookup 命中且 before/current `projection_logical_digest` 相同，可直接生成 `UNCHANGED`、`BUSINESS_EQUIVALENT` 或 schema-only table fact，不构造 projection rows、不生成 records。
- lookup 命中但 before/current `projection_logical_digest` 不同时，comparison core 仍必须构造 projection rows 并生成行级 records；此时可以复用 descriptor 中的 `row_identity_digest`、`projected_row_value_digest` 和 `projection_logical_digest`，避免重复执行 projection digest normalize/hash。
- lookup miss、descriptor digest parts 不完整、authority 不允许或 schema/version 不匹配时，必须回退现有 ProjectionTable / records 路径。
- 当普通表已经进入行级 records 路径时，records correctness 只依赖 projection rows、effective compare key 和 row value compare；projection logical digest 是可选 metadata。为降低 upload preview 响应时间，该路径可以跳过 projection logical digest 重算，并在 table fact 中省略 before/current projection digest。
- upload preview / provisional materialization 默认不生成 projection digest；只有显式 `projection_digest_policy` 开启时才会产生 `PROVISIONAL_FAST` digest。
- `PROVISIONAL_FAST` digest authority 只可用于 upload preview/provisional comparison；纯 FINAL/history comparison 只接受 `FINAL` authority。
- raw digest 变化且没有可用 descriptor projection digest summary 时，第一版必须重算 projection 后才能知道 projection digest 是否变化。
- 第一版不做列级 digest 优化。
- projection digest 不替代 raw digest 校验。

## ComparisonPlan

```text
ComparisonPlan:
  pair_kind:
    SNAPSHOT_TO_SNAPSHOT | REPOSITORY_TO_SNAPSHOT | REPOSITORY_TO_REPOSITORY
  providers:
    - table_name
      provider
      reason
      required_inputs
  diagnostics
```

第一版 provider：

| Provider | 用途 | 说明 |
| --- | --- | --- |
| `SUMMARY_EARLY_EXIT` | 无需 row diff | 基于 summary/digest 输出 unchanged 或 business equivalent。 |
| `SNAPSHOT_TABLE_COMPARE` | 通用 row diff | 通过 `SnapshotTableReader` streaming full rows，构造 projection 后比较。 |

后续 provider：

| Provider | 用途 | 说明 |
| --- | --- | --- |
| `PROJECTION_TABLE_COMPARE` | projection artifact 已存在时复用 | 读取 projection table artifact 后比较。 |
| `DOLT_NATIVE` | repository 两侧可原生比较时 | 必须经 canonicalizer 输出同一 `ComparisonFacts` contract；设计见 `../capabilities/dolt-native-provider.md`。 |
| `ORDERED_TABLE_COMPARE` | 有序表语义比较 | 实际进入 ordered provider 的表输出 ordered extension；完全未变化且被 `SUMMARY_EARLY_EXIT` 短路的 ordered 表可省略该 extension。contract 见 `ordered-diff.md`，实现设计见 `../capabilities/ordered-diff-compute.md`。 |

规则：

- Provider planning 不改变业务状态。
- Provider 输出必须统一成 `ComparisonFacts`。
- Provider-private projection 可以存在，但跨 capability 输出必须是 `ProjectionTableArtifact`、`ComparisonFacts` 或 `ComparisonRecords` artifact。

## ComparisonFacts

```text
ComparisonFacts:
  comparison_digest
  comparison_contract_version
  projection_contract_version
  table_ruleset_version
  before_snapshot_digest
  current_snapshot_digest
  direction: BEFORE_TO_CURRENT
  summary
  tables:
    - ComparisonTableFact
  records_ref optional
  diagnostics
```

`comparison_digest` 输入：

- before/current snapshot digest。
- comparison contract version。
- projection contract version。
- table ruleset version。
- scalar encoding version。
- requested tables。
- comparison semantic options。
- table fact digests or table result summary digest。

不进入 `comparison_digest`：

- comparison ID。
- workspace/submission/history request ID。
- operation ID。
- artifact refs。
- cache key。
- host path。
- diagnostics。

## ComparisonSummary

```text
ComparisonSummary:
  status:
    UNCHANGED | CHANGED | BUSINESS_EQUIVALENT | DEGRADED | FAILED
  table_count
  unchanged_table_count
  changed_table_count
  added_table_count
  deleted_table_count
  schema_changed_table_count
  degraded_table_count
  row_added_count optional
  row_deleted_count optional
  row_modified_count optional
  diagnostics_count
```

规则：

- Summary 可以内联在业务 record 或 operation result 中。
- Summary 不包含 full row diff records。
- Row count 可以按 policy 延迟或省略，但 table status 必须稳定。

## ComparisonTableFact

```text
ComparisonTableFact:
  table_name
  status:
    UNCHANGED
    BUSINESS_EQUIVALENT
    ADDED_TABLE
    DELETED_TABLE
    MODIFIED
    SCHEMA_CHANGED
    SCHEMA_ONLY_CHANGED
    DEGRADED
  before_descriptor optional
  current_descriptor optional
  projection_schema optional
  projection_schema_digest optional
  before_projection_logical_digest optional
  current_projection_logical_digest optional
  row_counts optional
  schema_changes optional
  records_ref optional
  diagnostics
```

`schema_changes`：

```text
SchemaChanges:
  before_only_columns
  current_only_columns
  selected_columns
  effective_compare_key_before optional
  effective_compare_key_current optional
  effective_compare_key_changed: true | false
  schema_evolution: NONE | COLUMNS_ADDED | COLUMNS_REMOVED | INCOMPATIBLE
```

规则：

- 新增表输出 `ADDED_TABLE`。
- 删除表输出 `DELETED_TABLE`。
- 仅对 before/current 都存在的表分类 schema 演进。字段只增、ENUM 只增标签（标签位置不限）、SET 只增成员且共有字段兼容时为 `COLUMNS_ADDED`；字段只删且共有字段兼容时为 `COLUMNS_REMOVED`；其余 schema 变化为 `INCOMPATIBLE`。有效比较键变化、键无效或共有字段不兼容时不得归类为只增列。
- ENUM/SET 兼容性按解析后的类型和标签精确比较；只规范化类型关键字，不改写标签字符串字面量。大小写变化或标签替换都是 `INCOMPATIBLE`，不能被其他新增列豁免。
- `COLUMNS_ADDED` 按共有列计算行变化，不改变 table status、不降级，也不产生 schema-change record。新增列名保留在内部 comparison facts 中；surface 不发布新增列列表，Submission/History 面向用户的结果不列出新增列。
- `COLUMNS_REMOVED` 保持 `SCHEMA_CHANGED`；`INCOMPATIBLE` 保持现行 schema-change/degraded 规则。
- key 不变时，row diff 只比较 selected columns。
- before-only/current-only columns 不进入 row diff。
- key 变化时，不做复杂 row identity 映射；输出全表变化或 `DEGRADED`。
- 整表新增/删除只输出表级 fact 与 row count，不生成 `ROW_ADDED` / `ROW_DELETED` 记录。
- 降级表不阻塞其他表比较。

## ComparisonRecords

行级记录建议作为 artifact 保存，summary/facts 只保留 ref 和 counts。

```text
ComparisonRecord:
  table_name
  record_kind:
    ROW_ADDED | ROW_DELETED | ROW_MODIFIED | SCHEMA_CHANGE | TABLE_DEGRADED
  row_identity optional
  changed_columns optional
  before_values optional
  current_values optional
  diagnostics optional
```

规则：

- 大表 diff records 不应全部内联到 `ComparisonFacts`。
- `row_diff_detail_policy` 控制是否输出 changed columns 或 full before/current values。
- `row_identity` 使用 effective compare key 的 canonical scalar encoding。
- 如果使用 `FULL_ROW_DIGEST_SET_DIFF`，row identity 是 full row digest，不能输出 modified，只能输出 added/deleted。
- 正式 bundle/surface records artifact 使用 Parquet；JSON 只用于 manifest、surface、projection、risk 和 diagnostics 等小型 metadata。
- Records artifact manifest 记录 table name、record format、record count、row_diff_detail_policy 和 content digest。
- Records artifact manifest 不记录 `comparison_digest`，避免 digest 循环。

## Comparison Records Closure

`ComparisonRecordsClosure` 把 `ComparisonFacts` 中引用的 records artifacts 闭合为可校验 artifact 集合。

```text
ComparisonRecordsClosure:
  closure_contract_version
  comparison_digest
  facts_core_digest
  records:
    - table_name
      records_ref
      records_manifest_digest
      records_content_digest
      record_count
  closure_manifest_digest
```

规则：

- `records_ref` 是 operation-local、bundle-local 或 cache-local ref，不进入 `comparison_digest`。
- `records_manifest_digest` 可进入 table fact digest，并间接进入 `comparison_digest`。
- `closure_manifest_digest` 不进入 `comparison_digest`。
- Cache hit 或 bundle assembly 可以重写 `records_ref`，但不能改变 records manifest digest、records content digest 或 facts core digest。
- 对外 READY 的 operation 必须拥有自己的 records closure，不能只引用 cache path。

第一版约束：

- records closure 按 comparison pair 生成。
- records artifact 按 table 生成。
- table-level comparison cache 后续再设计。

## Comparison Core Cache

`comparison_core_cache` 缓存 directed comparison capability 输出。

Key 输入：

```text
before_snapshot_digest
current_snapshot_digest
comparison_contract_version
projection_contract_version
table_ruleset_version
scalar_encoding_version
requested_tables
comparison_options
```

输出：

```text
ComparisonFacts
ComparisonRecords artifacts optional
ComparisonRecordsClosure optional
comparison diagnostics
```

规则：

- Cache key 不包含 flow ID、operation ID、workspace ID、history request ID、artifact ref 或 host path。
- Cache hit 不能跳过 artifact manifest 和 digest 校验。
- `comparison_core_cache` 不缓存 risk evaluation 或 surface assembly。
- Projection cache 命中只减少 projection/table IO，不代表 comparison core cache 命中。
- 第一版 `comparison_core_cache` 是 pair-level core cache；不做 table-level comparison facts cache，也不承担 surface / bundle 的 pair-total 结果缓存。
- Cache entry 保存 neutral facts core 和 records closure；命中后必须恢复为 operation-local artifact closure。
- Cache entry validation status 不应高于输入 Snapshot/Table artifacts 的最低可信等级。
- Provider name 默认不进入 key；只有会改变 canonical comparison 语义的 provider semantic change 才应进入 `comparison_options` 或 contract version。
- Provider raw output 不得作为 `comparison_core_cache` value；cache value 必须是 canonical `ComparisonFacts + ComparisonRecordsClosure`。
- `PROVISIONAL_FAST` alias 只能写入/读取 provisional preview cache，不得 promotion 为 history/archive 可直接消费的权威事实。
- `CANONICAL` alias cache 必须绑定 FINAL summary / repository-backed identity；cache hit 恢复到 operation/bundle 时仍需闭合 canonical records 和 alias mapping。

后续可扩展：

- table-level comparison cache。
- records artifact 压缩和列式格式。
- projection table cache 与 comparison core cache 的联合规划。
- cache promotion、eviction、dedup 和跨 operation hardlink 优化。

## Capability Boundary

Comparison compute capability 输入：

```text
ComparisonComputeInput:
  before: ComparisonInput
  current: ComparisonInput
  comparison_contract_version
  projection_contract_version
  table_ruleset_version
  scalar_encoding_version
  requested_tables optional
  comparison_options
  cache_policy
  cache_lookup_policy
  validation_status_policy
  artifact_policy
```

输出：

```text
ComparisonComputeResult:
  facts
  summary
  records_artifacts optional
  cache_diagnostics
  diagnostics
```

规则：

- Capability 不读取或修改业务状态。
- Capability 不根据 upload、submit、history compare 等流程名分支。
- Capability 可以被外部测试、benchmark 或新功能直接调用。
- 同一输入、版本和 ruleset 下，重复 comparison 应得到相同 `comparison_digest`。

## 非目标

第一版不定义：

- RiskEvaluation 规则。
- ComparisonSurface / WorkbenchBundle 的前端结构。
- Dolt native diff 的具体 SQL/CLI 实现；详见 `../capabilities/dolt-native-provider.md`。
- `RepositoryRef -> Snapshot` 的 repository server API 实现细节。
- repository_server 跨 session table cache 的具体存储、TTL、cleanup 策略。
- streaming row diff 算法、外部排序、内存预算或 Polars/SQLite/Python dict 等实现选型。
- Projection table cache 的具体物理格式。
- 列裁剪和 predicate pushdown 的公开 reader contract。
- 有序表 position/move/blank interval 等特殊业务语义；详见 `ordered-diff.md` 和 `../capabilities/ordered-diff-compute.md`。

这些能力可以后续独立设计，但必须消费或输出本文定义的 stable facts。

## 验收标准

- 相同 before/current Snapshot、ruleset、contract version 和 semantic options 下，重复 comparison 得到相同 `comparison_digest`。
- before/current 顺序交换时，added/deleted 方向反转。
- Summary early exit 不打开 row reader。
- raw digest 相同的表不产生 row diff。
- ignored columns 变化不应伪装 raw unchanged；只能影响 projection/business equivalent 结果。
- schema 变化时 row diff 只使用字段交集；before-only/current-only columns 进入 diagnostics。
- effective key 变化或重复 key 时，表级降级或全表变化，不做复杂映射。
- 大表 records 可落 artifact，facts 中只保留 counts/ref/digest。
- Comparison capability 不直接读取 SourcePackage、SqlDumpSource 或 RepositoryImportArtifact。
