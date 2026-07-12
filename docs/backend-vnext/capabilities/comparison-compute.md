# Comparison Compute Capability

本文定义 `Comparison Contract` 的第一版实现设计。Contract 见 `../contracts/comparison.md`；本文只描述 capability 内部模块、执行路径、缓存接入点和验收方式。

Comparison compute 是 flow-neutral capability。它不判断自己服务 upload、submit、commit finalize 还是 history compare；它只消费已经物化的 `SnapshotSummary`、`SnapshotTableSet` / `SnapshotTableReader` 和调用方传入的 ruleset。

## 设计原则

规则：

- Flow 负责选择 ruleset、输入来源、同步/异步策略、cache policy、artifact policy 和 records detail policy。
- Capability 负责应用 ruleset，生成 projection、diff facts、records artifact 和 digest。
- Capability 不读取或修改 Workspace、Submission、Preview、History request、RepositoryImportResult 等业务状态。
- Capability 不直接读取 SourcePackage、SqlDumpSource、RepositoryRef 或 RepositoryImportArtifact。
- Capability 不直接调用 repository server `list_tables`、`describe`、`count`、`export` 或 `select`。
- 同一输入、版本、ruleset 和 semantic options 下，重复计算必须得到相同 `comparison_digest`。
- 旧实现只作为行为、性能和业务语义参考，不作为 vNext 依赖或 adapter 来源。
- stage 5 暂存的共享模型与 digest helper 只是基础件，不是 stage 7 的内部结构约束；后续如果需要调整 planner / projection / provider 的组织方式，可以改，只要继续满足 `contracts/comparison.md` 和模块间约定即可。

## 能力列表

```text
comparison_compute
comparison_planning
projection_materialization
snapshot_table_compare
comparison_records_artifact
comparison_core_cache handoff
```

第一版只实现 `SUMMARY_EARLY_EXIT` 和 `SNAPSHOT_TABLE_COMPARE` 两类 provider。`DOLT_NATIVE`、`ORDERED_TABLE_COMPARE`、projection table artifact 复用和 risk/surface 组装分阶段接入。

`DOLT_NATIVE` 的第一版设计见 `dolt-native-provider.md`。Dolt native provider 只能作为 comparison compute provider；正式 cache value 仍必须是 canonical `ComparisonFacts + ComparisonRecordsClosure`，不能直接缓存 Dolt raw diff 作为 comparison core。

`ORDERED_TABLE_COMPARE` 已拆出 contract 与 capability 设计，见 `../contracts/ordered-diff.md` 与 `ordered-diff-compute.md`。有序表语义不属于普通 key-based diff，也不由 surface/bundle 定义算法。

## 建议代码模块

Comparison compute 主算法建议落点：

```text
gateway-data-management-system/backend/backend_vnext/capabilities/comparison/
```

同时抽取 flow-neutral 支撑模块：

```text
gateway-data-management-system/backend/backend_vnext/artifacts/
  records.py
  closure.py

gateway-data-management-system/backend/backend_vnext/cache/
  comparison_core.py
  validation_status.py
```

`capabilities/comparison/` 内部拆分：

```text
models.py
planner.py
projection.py
digest.py
engine.py
native_provider.py
records_builder.py
facts_builder.py
ruleset_registry.py
ordered/
  policy.py
  preparation.py
  classifier.py
  replay.py
  records.py
  digest.py
  provider.py
```

职责：

| Module | 职责 |
| --- | --- |
| `models` | `ComparisonComputeInput`、`ComparisonPlan`、`ProjectionSchema`、`ComparisonFacts`、`ComparisonRecord` 等纯模型。 |
| `planner` | 基于 summary、requested tables、ruleset 和 options 生成表级计划。 |
| `projection` | 字段交集、ignored columns、effective key、scalar canonicalization、projection digest。 |
| `digest` | `projection_schema_digest`、`projection_logical_digest`、`comparison_digest`。 |
| `engine` | orchestration：plan、table dispatch、projection compare/self-project、provider fallback 串联。 |
| `native_provider` | RepositoryRef -> RepositoryRef 的 native diff 优化路线、native snapshot/table descriptor canonicalization 和 fallback diagnostics。 |
| `records_builder` | row diff records、side records、records artifact 和 record sort key。 |
| `facts_builder` | table facts、summary、facts core digest、records closure 和 descriptor payload helper。 |
| `ordered` | 有序表 position/move/interval diff provider，独立于 Dolt native。 |
| `artifacts.records` | JSONL records artifact、单表 manifest、content digest、写失败清理和校验。 |
| `artifacts.closure` | records closure manifest、cache-local 到 operation-local ref 恢复、copy/hardlink 策略。 |
| `cache.comparison_core` | comparison core cache lookup/write、validation status、cache hit restore。 |
| `cache.validation_status` | `PROVISIONAL` / `CONTENT_VERIFIED` / `COMMIT_VALIDATED` 等 cache 可信等级。 |

依赖方向：

```text
comparison providers
  -> projection / digest
  -> artifacts.records / artifacts.closure
  -> cache.comparison_core
  -> artifacts
  -> core
```

禁止 comparison、records artifact、artifact closure、comparison core cache 依赖 flow、operation、risk、surface、repository import 或旧业务模块。

边界：

- Flow/operation 负责选择输入、ruleset、cache policy、artifact policy 和 READY 条件。
- `artifacts.records` 负责生成和校验 records artifact。
- `artifacts.closure` 负责生成和恢复 operation-local artifact closure。
- `cache.comparison_core` 负责 cache entry 的 lookup/write/restore。
- Flow 不手写 records copy、hardlink、manifest 校验或 cache restore 逻辑。

## TableRulesetSnapshot

ruleset 的选择属于 flow，ruleset 的应用属于 capability。Flow 层应在调用 comparison 前解析并冻结 ruleset。

```text
TableRulesetSnapshot:
  ruleset_id
  ruleset_version
  ruleset_digest
  fallback_key_policy
  projection_policy
  table_rules:
    - table_selector
      static_role
      compare_key optional
      ignored_columns
      artifact_scope
      row_diff_policy optional
```

规则：

- `ruleset_digest` 进入 `comparison_digest` 和 `comparison_core_cache` key。
- `ruleset_digest` 必须由 ruleset 内容和 ruleset contract version 计算，不由 flow name 计算。
- Flow 可以为 upload preview、commit finalize、history compare 选择同一或不同 ruleset，但 capability 不知道这些 flow 名称。
- `backend_vnext.capabilities.table_rules` 是 table semantic 的唯一真源；snapshot materialization、repository readback 和 comparison 都应从同一份规则派生自己的视图。
- `SKIP` / `SNAPSHOT_ONLY` / `BROWSE_ONLY` 这类规则结果不进入 comparison。`NO_COMPARE_KEY` 只保留给“本该参与 comparison 但确实没有可用 key”的表；如果两侧在同一 ruleset / projection 版本下的 canonical digest 已经一致，表可以直接 early-exit 为 `UNCHANGED`，不必先进入降级。
- ruleset 中的 table selector 可以支持 exact name 和 regex；selector 解析结果应在 diagnostics 中可追踪。
- 第一版 ruleset 来源使用 hardcoded `TableRulesetRegistry`。
- `TableRulesetRegistry` 输出 frozen `TableRulesetSnapshot`，而不是让 provider 在运行时直接读取 mutable registry。
- 这份 `TableRulesetSnapshot` 只是 comparison 侧的派生视图；共享语义真源统一放在 `backend_vnext.capabilities.table_rules`，snapshot materialization / repository readback / comparison 各自从同一份规则源派生自己的视图。
- Registry 内容、默认规则、selector 和 ordered policy 必须可序列化并参与 `ruleset_digest`。
- 未来切换为配置文件时，只替换 registry loader；`TableRulesetSnapshot` contract、digest 和 comparison capability 输入保持不变。

## 输入输出

```text
ComparisonComputeInput:
  before: ComparisonInput
  current: ComparisonInput
  table_ruleset: TableRulesetSnapshot
  comparison_contract_version
  projection_contract_version
  scalar_encoding_version
  requested_tables optional
  comparison_options
  cache_policy
  cache_lookup_policy
  validation_status_policy
  artifact_policy
  runtime_policy optional
```

`runtime_policy` 只影响实现资源，不影响 comparison 语义：

```text
runtime_policy:
  preferred_internal_mode:
    AUTO | HASH_STREAM_COMPARE | SQLITE_SPOOL_COMPARE
  memory_budget_bytes optional
  sqlite_temp_dir optional
```

实现上会把这份 `runtime_policy` 先作为 opaque mapping seam 保留；当前 stage 7 不根据它做实际 mode selection。后续在 projection 正式实现时，再补 projected payload 估算、AUTO 切换和 SQLite spill 路径。

输出：

```text
ComparisonComputeResult:
  facts
  summary
  records_artifacts optional
  plan
  cache_diagnostics
  diagnostics
```

规则：

- `runtime_policy` 不应改变 `ComparisonFacts` 语义。如果某选项会改变输出内容，必须进入 `comparison_options` 和 digest。
- `max_inline_record_count` 属于 `comparison_options` 或 `artifact_policy`，只影响内联与 artifact 分流，不影响 facts 中的 counts、status 和 records manifest digest。
- `preferred_internal_mode=AUTO` 的自动切换规则保留为后续实现目标；本阶段只保留 opaque runtime seam，不做 projected payload 估算或 mode selection。
- “大表”只是实现级内部描述，不是 contract 语义；后续实现时应优先使用 `memory_budget_bytes`、projected payload 估算，必要时再用 `row_count` 作为 fallback。

## 执行流程

```text
validate input
  -> build ComparisonPlan from summaries
  -> run summary early exits
  -> for each planned table:
       build ProjectionSchema
       run SnapshotTableCompare when row diff is required
       write ComparisonRecords artifact when required
       compute table fact digest
  -> assemble ComparisonFacts
  -> write comparison_core_cache when enabled
```

第一版以表为最小失败隔离单元。单表 key 异常或 schema 异常应使该表 `DEGRADED`，不阻塞其他表。

## Planning

`comparison_planning` 只读取 `before.summary`、`current.summary`、`requested_tables`、`table_ruleset` 和 comparison options。

表级决策：

| Decision | 条件 | 行为 |
| --- | --- | --- |
| `SKIP` | ruleset 标记跳过 | 输出 skipped diagnostics，不打开 reader。 |
| `SNAPSHOT_ONLY` / `BROWSE_ONLY` | 规则不允许进入 comparison | 继续保留 materialization / preview 语义，但不进入 comparison。 |
| `ADDED_TABLE` | before 缺表，current 有表 | 需要 records 时只读 current。 |
| `DELETED_TABLE` | before 有表，current 缺表 | 需要 records 时只读 before。 |
| `RAW_UNCHANGED` | schema、row_count、raw_content_digest 均相同 | 输出 unchanged，不打开 reader。该早退同样适用于 `NO_COMPARE_KEY` 表。 |
| `BUSINESS_EQUIVALENT` | projection digest 已存在且相同 | 输出 business equivalent，不打开 reader。 |
| `SNAPSHOT_TABLE_COMPARE` | 需要行级 diff | 通过 `SnapshotTableReader` streaming rows。 |
| `DEGRADED` | effective key/schema 规则无法满足 | 输出降级事实和原因。 |

规则：

- 表清单来自 `ComparisonInput.summary`，不从 repository 或 source package 重新发现。
- Pair 级 snapshot digest 相同且 semantic versions/options 相同，可直接输出 pair unchanged。
- raw digest 相同只能证明 raw unchanged；ignored columns 导致的业务等价应通过 projection digest 或 row diff 表达。
- 第一版没有 projection digest 缓存时，raw digest 变化后必须重新投影才能判断业务等价。

## Projection

`ProjectionSchema` 是两侧 raw table 在 ruleset 下的 compare-ready schema。

构造步骤：

1. canonicalize table name 和 column name，字段大小写变化不算 schema change。
2. 取 before/current 字段交集。
3. 移除 ignored columns。
4. 选择 effective compare key。
5. 记录 before-only/current-only columns 作为 schema diagnostics。
6. 计算 `projection_schema_digest`。

Key 选择：

```text
table_ruleset compare_key > DDL primary key > fallback_key_policy
```

补充说明：

- `FULL_ROW_DIGEST_SET_DIFF` 作为 `fallback_key_policy` 的显式 opt-in 语义保留，但 stage 7 默认仍应采用 `DEGRADE_NO_COMPARE_KEY`，不把整行集合差异误当作 modified 语义。

降级规则：

| Reason | 触发条件 |
| --- | --- |
| `EFFECTIVE_KEY_MISSING` | effective key 任一字段在任一侧不存在。 |
| `EFFECTIVE_KEY_IGNORED` | effective key 被 ignored columns 移除。 |
| `EFFECTIVE_KEY_CHANGED` | before/current effective key 不一致。 |
| `EFFECTIVE_KEY_DUPLICATE` | 投影后任一侧出现重复 key。 |
| `NO_COMPARE_KEY` | 没有 key 且 fallback policy 为 `DEGRADE_NO_COMPARE_KEY`。 |
| `EMPTY_SELECTED_COLUMNS` | selected columns 为空，只输出 schema-only 结果。 |

规则：

- row identity 使用 effective compare key 的 canonical scalar tuple。
- ignored columns 不参与 row value digest 和 modified 判定。
- before-only/current-only columns 不参与 row diff，但进入 schema diagnostics 和后续 risk input。
- 字段顺序无业务意义；digest 按 canonical set 和 key 计算。
- 第一版不做列级 digest 优化和 predicate pushdown。

## SnapshotTableCompare Provider

`SNAPSHOT_TABLE_COMPARE` 是第一版主 provider。它只通过 `SnapshotTableReader` 读取 full rows，由 projection 层过滤字段。

内部执行模式：

注意：下列 mode 切换规则是 projection 正式实现后的目标行为；当前 stage 7 只保留 `runtime_policy` 输入，不执行实际切换。

| Mode | 适用 | 说明 |
| --- | --- | --- |
| `HASH_STREAM_COMPARE` | 默认优先路径 | before 侧投影进内存 dict，current 侧流式匹配，通常是吞吐更高的首选。 |
| `SQLITE_SPOOL_COMPARE` | 明确超预算或显式要求落盘 | 投影写入临时 SQLite，使用索引和 join/lookup 生成 diff。 |

选择规则：

- `preferred_internal_mode=AUTO` 时，优先保留 `HASH_STREAM_COMPARE`，只有在 projected payload 估算明显超过预算或调用方显式要求落盘时才切到 `SQLITE_SPOOL_COMPARE`。更具体的切换准则和 benchmark 口径见 `../adr/0002-comparison-hash-sqlite-mode-selection.md`。
- 如果 summary 缺少可靠 row_count，先用 projected payload 估算和现有 reader 元数据做保守判断，row_count 只作为 fallback。
- 内部模式必须输出同一 `ComparisonTableFact` 和 records artifact contract。
- 内部模式名进入 diagnostics；只有会改变 canonical comparison 语义的 provider semantic change 才通过 `comparison_options` 或 contract version 进入 digest/cache key。
- 后续 `DOLT_NATIVE` provider 也遵守同一原则：provider 可以不同，但输出必须归一化为同一 comparison contract。records 物理顺序、chunk、path 或 provider diagnostics 差异不应影响 canonical records digest。

## 普通表 Diff Compute

普通表 diff 是第一版 comparison compute 的核心闭环。本阶段需要定义并实现普通表的 key-based row diff；不在本阶段实现有序表 position/move 语义。

适用条件：

- table ruleset 将表标记为普通内容比较表，并且该表没有被共享语义层过滤出 comparison。
- before/current 均能构造同一 `ProjectionSchema`。
- effective compare key 存在且未被 ignored columns 移除。
- 投影后 before/current 任一侧都不存在重复 key。

输入：

```text
StandardTableDiffInput:
  table_name
  before_descriptor optional
  current_descriptor optional
  projection_schema
  before_reader optional
  current_reader optional
  row_diff_detail_policy
  artifact_policy
  runtime_policy
```

输出：

```text
StandardTableDiffResult:
  table_fact
  row_added_count
  row_deleted_count
  row_modified_count
  before_projection_logical_digest optional
  current_projection_logical_digest optional
  records_artifact optional
  diagnostics
```

行级判定：

| Case | 判定 |
| --- | --- |
| key 只在 current 存在 | `ROW_ADDED` |
| key 只在 before 存在 | `ROW_DELETED` |
| key 两侧都存在且 projected row value digest 不同 | `ROW_MODIFIED` |
| key 两侧都存在且 projected row value digest 相同 | unchanged row，不输出 record |

规则：

- row identity 使用 effective compare key 的 canonical scalar tuple。
- row value digest 只包含 selected columns，不包含 ignored columns、before-only columns 或 current-only columns。
- 字段顺序和 reader 原始行顺序无业务意义。
- records 输出必须使用 canonical order，默认按 row identity、record kind、canonical column name 排序。
- schema 变化时，row diff 只比较 before/current 字段交集减 ignored columns 后的 selected columns。
- before-only/current-only columns 进入 `schema_changes` 和 diagnostics，不制造 row modified。
- selected columns 为空时输出 `SCHEMA_ONLY_CHANGED` 或 unchanged schema-only fact，不做 row diff。
- effective key 变化、缺失、被忽略或重复时，输出 `DEGRADED`，不做复杂 row identity 映射。

Table presence：

- 新增表可按 policy 输出 `ADDED_TABLE`，并在需要 records 时把 current rows 输出为 `ROW_ADDED`。
- 删除表可按 policy 输出 `DELETED_TABLE`，并在需要 records 时把 before rows 输出为 `ROW_DELETED`。
- 对全表新增/删除，records 仍需遵守 canonical order 和 artifact 分流策略。

Digest：

- 普通表 diff 过程中应同时计算 before/current `projection_logical_digest`。
- 如果 raw digest 变化但 projection logical digest 相同，表可标记为 `BUSINESS_EQUIVALENT`。
- 如果 projection logical digest 不同，则按 row counts 和 records 结果标记 `MODIFIED`。
- `ComparisonTableFact` digest 应由 table status、projection schema digest、projection logical digest、row counts、records manifest digest 和稳定语义版本组成。

失败与降级：

| Reason | 行为 |
| --- | --- |
| `NO_COMPARE_KEY` | compare-eligible 表默认 `DEGRADED`，不猜测业务 row identity。 |
| `EFFECTIVE_KEY_DUPLICATE` | 表级 `DEGRADED`，记录重复 key diagnostics。 |
| `READER_FAILED` | 表级 `DEGRADED` 或 table failure diagnostics，不影响其他表。 |
| `RECORDS_ARTIFACT_FAILED` | 表级失败或 comparison failure，不能输出不完整 artifact manifest。 |
| `MEMORY_BUDGET_EXCEEDED` | AUTO 模式切换 SQLite；强制 hash 模式下表级 `DEGRADED`。 |

## 有序表 Provider Slot

有序表 diff 不属于普通表 diff 的实现细节。它涉及 position、move、空位修复、replay guarantee、前端展示和风险语义，应作为独立 `ORDERED_TABLE_COMPARE` provider。

第一版行为：

- ruleset 可以标记 `ORDERED_DIFF` 或类似 static role。
- planner 能识别该 role。
- 如果没有启用 ordered provider，输出 `DEGRADED`，并保留 ordered diagnostics；不再使用旧的 ordered 未启用占位状态作为对外结果。
- 第一版不把普通 key-based fallback 作为 ordered role 的默认退路。
- `SNAPSHOT_TABLE_COMPARE` 不偷偷解释 move、position 或 slot repair。
- `DEGRADED` 继续作为表级降级事实保留，不得伪装成普通表 diff。

阶段建议：

- `ORDERED_TABLE_COMPARE` 的 contract 和 capability 第一版已拆出，后续实现时按 `../contracts/ordered-diff.md` 与 `ordered-diff-compute.md` 接入。
- `surface / bundle contract` 只消费 ordered diff facts，不定义 ordered diff 算法。
- 如果首批业务必须准确展示有序表变化，则 ordered provider 应早于 surface/bundle 正式集成。

## Hash Stream Compare

算法：

```text
before reader:
  project row
  build row_identity
  detect missing/duplicate key
  store key -> row_digest + optional projected values

current reader:
  project row
  build row_identity
  detect missing/duplicate key
  if key absent in before index: ROW_ADDED
  if key present and row_digest differs: ROW_MODIFIED
  mark key seen

remaining before keys:
  ROW_DELETED
```

规则：

- output order 必须稳定，按 canonical row identity、record kind 和 canonical column name 排序。
- Hash mode 可以在内存预算内暂存待写 records 并排序；如果 records 或 before index 超过预算，应切换到 SQLite spool。
- `ComparisonFacts` 不应持有 full records；records 应输出到 artifact writer 或 provider-local 临时 spool。
- 如果 `row_diff_detail_policy=COUNTS_ONLY`，仍可只保留 counts 和 row digest，避免保存 full values。
- 如果发现 duplicate key，应终止该表行级 diff，输出 `DEGRADED`，并关闭该表 records writer。

适用边界：

- 优先用于 correctness、单元测试、小型业务数据和普通中等表。
- 不作为大表唯一实现路径。

## SQLite Spool Compare

算法：

```text
create temp sqlite db
create before_rows(key_digest primary key, key_json, row_digest, payload_json optional)
create current_rows(key_digest primary key, key_json, row_digest, payload_json optional)
stream/project before into before_rows
stream/project current into current_rows
detect duplicate key via unique constraint
query added/deleted/modified rows
write records artifact
drop temp db
```

规则：

- SQLite temp DB 是 operation-local transient state，不是 capability artifact。
- key 需要同时保存 digest 和 canonical JSON；digest 用于索引，canonical JSON 用于 records 和稳定排序。
- 输出顺序必须按 canonical key JSON、record kind 和 canonical column name 稳定排序。
- `payload_json` 是否保存由 `row_diff_detail_policy` 决定；`COUNTS_ONLY` 可以只保存 digest。
- 临时 DB 大小、写入耗时、query 耗时和清理结果进入 diagnostics。

选择 SQLite 的理由：

- Python 标准库可用，不引入新部署依赖。
- 能通过 unique index 自然发现重复 key。
- 比纯内存 dict 更适合大表和 records 很多的场景。

后续可在 benchmark 证明必要后，再讨论 Polars、DuckDB、Parquet projection 或 Dolt native。

## Records Artifact

第一版 records artifact 固定使用未压缩 JSONL，Parquet、压缩和列式 records 后续再评估。

`records_artifact` 是 flow-neutral artifact support capability，可以被 comparison compute、comparison core cache restore、bundle assembly 或测试工具复用。

职责：

```text
write JSONL records
write per-table records manifest
compute records_content_digest
validate records manifest and content digest
cleanup failed partial writes
provide RecordsArtifactRef / RecordsArtifactManifest models
```

不负责：

```text
flow / operation state
table ruleset selection
cache lookup
risk / surface assembly
front-end display shaping
```

```text
ComparisonRecordsArtifactManifest:
  table_name
  record_format: JSONL
  record_contract_version
  row_diff_detail_policy
  record_count
  records_content_digest
  projection_schema_digest optional
  artifact_size_bytes optional
  diagnostics
```

JSONL record：

```text
ComparisonRecord:
  table_name
  record_kind
  row_identity optional
  changed_columns optional
  before_values optional
  current_values optional
  diagnostics optional
```

规则：

- `ComparisonFacts` 第一版不内联 records，只保留 counts、`records_ref` 和 records manifest digest。
- `COUNTS_ONLY` 不输出 full values。
- `CHANGED_COLUMNS` 输出 changed column names 和 row identity。
- `FULL_BEFORE_AFTER_VALUES` 输出投影后的 before/current values，不输出 ignored columns。
- JSONL 使用 UTF-8、LF 行尾、canonical JSON 和 canonical record order。
- `records_content_digest` 只由 JSONL bytes 计算。
- records manifest 不包含 `comparison_digest`，避免与 `comparison_digest` 汇总 records manifest digest 形成循环。
- Artifact writer 必须支持 close/fail cleanup，失败时不能留下可被误认为有效的 manifest。

第一版后续可能变化：

- records format 可增加 Parquet 或压缩 JSONL。
- surface/bundle 层可为了展示少量 diff 而内联 records 摘要，但 comparison core facts 仍应保持 ref/manifest 为主。
- table-level comparison cache 成熟后，records artifact 可按 table cache entry 独立复用。

## Records Artifact Closure

Records artifact closure 负责把 `ComparisonFacts` 中的 records refs 闭合为当前 operation 可读取、可下载、可校验的 artifact 集合。

`artifact_closure` 是 flow-neutral artifact support capability。第一版只要求服务 comparison records；后续可扩展到 SnapshotTableArtifact、WorkbenchBundle 或 repository import artifact closure。

职责：

```text
build ComparisonRecordsClosureManifest
validate facts_core_digest
validate records manifest digest
validate records content digest
restore cache-local records refs to operation-local refs
copy or hardlink artifact files according to artifact_policy
rewrite refs without changing facts digest inputs
```

不负责：

```text
operation READY 状态推进
业务 flow 判断
risk / surface / bundle 结构组装
cache key 选择
row diff compute
```

第一版 operation-local layout：

```text
comparison/
  facts.json
  records/
    <table>.records.jsonl
    <table>.records.manifest.json
  records-closure.json
```

第一版 cache entry layout：

```text
comparison-core-cache/
  cache-entry.json
  facts-core.json
  records/
    <table>.records.jsonl
    <table>.records.manifest.json
  records-closure.json
```

Closure manifest：

```text
ComparisonRecordsClosureManifest:
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

- `closure_manifest_digest` 不进入 `comparison_digest`。
- `comparison_digest` 可以汇总 table fact digests；table fact digest 可以包含 `records_manifest_digest`。
- `records_ref` 是 operation-local 或 cache-local ref，不进入 digest。
- Cache hit 恢复到 operation 时，可以重写 `records_ref`，但不能改变 records manifest digest、content digest 或 facts core digest。
- READY 结果不得引用未来可能被清理的 cache path；必须生成 operation-local closure。
- closure 校验失败时，cache hit 视为 miss；如果正在本次计算写 closure，则结果失败或降级由 `row_diff_detail_policy` 决定。
- Operation 负责要求 closure 完整；`artifact_closure` 负责生成、校验和恢复 closure。

## Digest

`projection_schema_digest` 输入：

```text
canonical table name
selected columns
ignored columns
effective compare key
ruleset_digest
projection_contract_version
scalar_encoding_version
```

`projection_logical_digest` 输入：

```text
projection_schema_digest
row_identity digest
projected row value digest
```

`comparison_digest` 输入：

```text
before_snapshot_digest
current_snapshot_digest
comparison_contract_version
projection_contract_version
scalar_encoding_version
table_ruleset.ruleset_digest
requested_tables
comparison_options
table fact digests
records manifest digests
```

规则：

- row order 不进入 projection logical digest。
- host path、operation id、flow id、workspace id、artifact physical path 和 diagnostics 不进入 digest。
- Artifact ref 不进入 digest；records manifest digest 可以进入 table fact digest。
- JSONL artifact content digest 只有在 records 按 canonical order 写出时才能进入 records manifest digest。
- `runtime_policy` 不进入 digest，除非它改变输出语义。

## Cache 接入点

第一阶段建议先实现 cache interface 和 diagnostics，默认 `DISABLED`，先跑通 cold correctness。

`comparison_core_cache` 是 cache 层 flow-neutral capability，不是 comparison row diff 算法的一部分。Comparison compute 可以通过接口使用它；cache policy、lookup policy 和 validation status policy 由 flow/operation 显式传入。

`comparison_core_cache` 只负责 pair-level core comparison 复用，不承接 surface / bundle 这类 pair-total 结果缓存；如果未来需要复用 higher-level 输出，应由 downstream capability 或 flow 侧分别装配。

Provider-neutral cache 原则：

- `comparison_core_cache` 的 key 默认不包含 provider name。
- cache value 是 canonical `ComparisonFacts + ComparisonRecordsClosure`，不是 SQL path、Snapshot path 或 Dolt native 的原始输出。
- SQL parse path、Snapshot table compare path、Dolt native path 只要归一化后 canonical facts/records 等价，就可以共享命中同一 core cache。
- records 原始顺序不同可以接受；records writer/manifest 必须使用 canonical sort 或 order-insensitive digest，确保 `records_manifest_digest` 稳定。
- provider-specific raw output 只能进入 diagnostics 或 provider-local cache，不能作为 comparison core cache 的权威 value。
- 如果 ignored columns、schema policy、row identity、scalar encoding、degraded reason 或 row counts 无法归一化一致，则该 provider 不能写入 provider-neutral core cache，应 fallback 或使用 provider-local cache。

职责：

```text
build/validate comparison core cache key
lookup pair-level comparison core cache entry
validate cache entry validation status
store neutral facts core + records closure
restore cache hit through artifact_closure
return cache diagnostics
```

不负责：

```text
ruleset/profile selection
row diff compute
records JSONL writing
risk / surface / bundle assembly
business state transition
```

第一版正式 cache 启用顺序：

1. `comparison_core_cache`：缓存 `ComparisonFacts` 和 records artifacts。
2. `projection_table_cache`：缓存 projection table artifact，减少重复 projection/table IO。
3. request-level cache 或 flow assembly cache：只在 flow/operation 层使用，不进入 compute capability，也不作为 pair-total cache。

`comparison_core_cache` key：

```text
before_snapshot_digest
current_snapshot_digest
comparison_contract_version
projection_contract_version
scalar_encoding_version
table_ruleset.ruleset_digest
requested_tables
comparison_options
```

Provider semantic version 只有在会改变 canonical comparison 语义时才进入 `comparison_options` 或 contract version；纯性能路线、records 顺序差异或 provider diagnostics 不进入 key。

第一版 cache granularity：

- `comparison_core_cache` 使用 pair-level core cache entry。
- 不做 table-level comparison cache。
- 表级复用先依赖 `snapshot_table_artifact_cache` 和 `projection_table_cache`，ordered provider 也应优先复用同一批 compare-ready projection artifact 命中结果，后续再评估更高层的 flow assembly cache。
- `facts-core.json` 存 neutral facts，不存 operation-local refs。
- records artifacts 和 `records-closure.json` 与 facts core 一起进入 cache entry。

### 最小 Handoff 协议

`comparison_core_cache` 第一版只需要最小 handoff protocol，不要求先落完整 registry / promotion / eviction 体系。

建议协议：

```text
enabled
lookup(...)
write(...)
```

规则：

- cache value 必须是 canonical `ComparisonFacts + ComparisonRecordsClosure`，不是 provider 原始输出。
- cache hit 恢复时只允许重写 operation-local refs，不允许改变 facts 语义或 digest 输入。
- registry、validation promotion、eviction 和 table-level 复用可以留到后续 cache 正式化阶段再补。
- 如果未来引入 `projection_table_cache`，也应复用同一套 provider-neutral 语义，而不是把 provider name 作为核心区分项。

Cache hit restore：

```text
lookup cache entry
  -> validate cache key and validation status
  -> validate facts_core_digest
  -> validate records closure manifest
  -> validate each records manifest and content digest
  -> copy/hardlink records into operation artifact root
  -> rewrite operation-local records_ref
  -> return ComparisonComputeResult
```

规则：

- Cache hit 不能跳过 artifact manifest 和 digest 校验。
- Cache 不缓存 risk evaluation、surface、workbench bundle 或业务状态。
- Cache key 不包含 upload、submit、history compare、operation、workspace、host path。
- PROVISIONAL / COMMIT_VALIDATED 等 validation status 由 cache 层表达，compute 只按显式 `cache_lookup_policy` 使用。
- Cache entry 的 validation status 不应高于 before/current 输入和 records artifacts 的最低可信等级。
- Preview/upload 产生的 comparison core cache 默认为 `PROVISIONAL`，通常由 upload preview 的异步 completion 或 warmup 阶段补齐；commit/mainline 权威流程默认只读 `COMMIT_VALIDATED`。
- 如果 flow 允许读 provisional cache，必须使用显式 `READ_PROVISIONAL_WITH_REVALIDATION`。

第一版后续可能变化：

- 增加 table-level comparison cache。
- 增加 compressed JSONL / Parquet records artifact。
- 增加 projection table cache 后，cache key 可纳入 projection provider semantic version。
- 增加 cache eviction、promotion 和 artifact dedup 策略。
- 增加跨 operation 的 records artifact hardlink 优化；但对外 refs 仍必须 operation-local。

## Benchmark 指标

comparison benchmark 应复用正式 capability，而不是维护独立 diff 实现。

建议指标：

```text
planning_ms
projection_ms
provider_ms
records_write_ms
digest_ms
cache_lookup_ms
cache_write_ms
opened_reader_count
read_table_count
read_row_count
records_count
provider_mode
peak_memory_estimate_bytes optional
sqlite_temp_bytes optional
diagnostics_count
```

数据集：

- 优先使用实际业务数据的小、中小、中、大四档。
- tiny correctness fixture 可由程序构造，用于覆盖 schema/key/ignored columns/duplicate key 等边界。
- 不优先构造脱离业务实际的极端 skewed hot table。

## 测试与验收

单元测试：

- ruleset digest 稳定。
- projection schema digest 对字段顺序不敏感。
- 字段大小写变化不算 schema change。
- ignored columns 不参与 row modified 判定。
- effective key missing/ignored/changed/duplicate 均降级。
- row order 不影响 projection logical digest。

Contract 测试：

- pair summary early exit 不打开 row reader。
- table raw unchanged 不打开 row reader。
- added/deleted 方向在 before/current 交换后反转。
- schema intersection 只比较共有字段。
- no-key 默认 `DEGRADE_NO_COMPARE_KEY`。
- records artifact manifest digest 可复验。

Integration 测试：

- SQL -> Snapshot -> Comparison 的最小闭环。
- `HASH_STREAM_COMPARE` 与 `SQLITE_SPOOL_COMPARE` 在同一 fixture 上输出同一 facts。
- 大表 records 不内联到 facts。
- cache disabled / read-only / write-through diagnostics 可区分。

进入业务 flow 集成前至少满足：

- comparison capability 不 import 旧业务模块。
- comparison capability 不 import flow、operation、risk、surface 或 repository import。
- SQL/Snapshot-to-Snapshot cold path 可独立运行。
- benchmark 能调用正式 capability 并输出分阶段耗时。
- 失败能区分 planning、projection、reader、provider、records artifact、digest、cache phase。

## 第一版取舍与后续演进

第一版固定选择：

- 只实现普通表 key-based diff，不实现有序表 position/move 语义。
- `SNAPSHOT_TABLE_COMPARE` 只通过 `SnapshotTableReader` full-row streaming 读取输入。
- 默认优先 `HASH_STREAM_COMPARE`；只有在 projected payload 明显超预算或显式要求落盘时才使用 `SQLITE_SPOOL_COMPARE`。更具体的切换准则和 benchmark 口径见 `../adr/0002-comparison-hash-sqlite-mode-selection.md`。
- records artifact 使用未压缩 JSONL，按 table 输出。
- `ComparisonFacts` 不内联 full records，只保留 counts、records ref 和 records manifest digest。
- `comparison_core_cache` 使用 pair-level core cache entry，不做 table-level comparison cache。
- `comparison_core_cache` 第一版先定义 handoff 接口和 canonical value 形状，正式 registry / promotion / eviction 留到后续 cache 阶段。
- Cache hit 必须恢复 operation-local records closure，不暴露 cache path。
- 第一版不实现 risk evaluation、surface/workbench assembly、Dolt native diff 或 ordered table diff。

后续可能变化：

- 增加 `ORDERED_TABLE_COMPARE` provider。
- 增加 table-level comparison cache。
- 增加 projection table cache 和 projection artifact provider。
- 增加 records artifact 压缩、Parquet 或列式格式。
- 增加 Dolt native provider，但仍必须输出同一 `ComparisonFacts` contract。
- 增加 risk input contract、surface/bundle contract 和 flow assembly cache。
- 根据 benchmark 结果调整 hash/SQLite 阈值，或评估 Polars、DuckDB 等替代执行引擎。

## 分阶段实施建议

第一阶段：

```text
models + ruleset_contract + planner
projection schema
SUMMARY_EARLY_EXIT
HASH_STREAM_COMPARE
JSONL records artifact
cold correctness tests
```

第二阶段：

```text
SQLITE_SPOOL_COMPARE
large business dataset benchmark
records artifact manifest validation
provider mode diagnostics
```

第三阶段：

```text
comparison_core_cache
projection_table_cache design/implementation
benchmark cache hit/miss path
```

第四阶段：

```text
DOLT_NATIVE provider implementation + benchmark
ORDERED_TABLE_COMPARE implementation
risk engine input contract
surface/workbench assembly
```
