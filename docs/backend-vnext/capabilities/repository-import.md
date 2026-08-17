# Repository Import Capability

本文定义把 `Snapshot` / `SnapshotTableSet` 导入 repository/Dolt 并创建可校验 commit/ref 的能力边界。它是 repository/Dolt 技术能力，不包含 Workspace、Preview、Submission、Review、ArchiveSelection 等业务模型。

## 定位

Repository import 是重负载 repository write capability。未来 Dolt 版本库可以封装为独立 API 容器，对外暴露网络 API 或 Unix socket。本 capability 的 contract 应保持 repository-level，不绑定业务流程。

模块职责：

```text
Dolt repository operations
Dolt ref/branch/commit 操作
Dolt table import/export/readback
Dolt table IO cache / export cache
Dolt-local multi-step import workflow
Dolt server lifecycle
provider benchmark / diagnostics
```

不负责：

```text
Workspace / Preview / Submission / Review / ArchiveSelection
业务状态机
人工审核语义
PreviewInputBinding 业务校验
```

## 调用者策略

Repository import capability 按调用者类型约束使用方式。

| 调用者类型 | 是否执行 import | 说明 |
| --- | --- | --- |
| `DIRECT_RESPONSE_CALLER` | 否 | 效率优先的直接反馈路径不执行重负载 repository import。 |
| `READ_ONLY_CALLER` | 否 | 只读流程只做 repository readback/export/cache materialization。 |
| `WARMUP_CALLER` | 可选 | 可执行 shadow/precommit import 或 cache warmup，结果只能作为 candidate。 |
| `FINALIZE_WRITE_CALLER` | 是 | 正式写入路径持有 writer lease，完成 import、commit/ref、readback validation。 |

业务流程如何映射到调用者类型见 `../flows.md`，异步 operation 边界见 `../operations.md`。

## 输入输出

```text
RepositoryImportInput:
  snapshot
  summary
  table_set optional
  source_package optional
  import_plan
  writer_lease_context
  caller_policy:
    WARMUP_CALLER | FINALIZE_WRITE_CALLER
  idempotency_key
```

```text
RepositoryImportResult:
  repository_id
  target_ref
  commit_hash optional
  import_provider
  imported_table_count
  source_snapshot_digest
  readback_snapshot_digest optional
  validation_result
  diagnostics
```

Capability 输出 commit/ref 和 diagnostics，不直接改变业务状态。

正式 submit finalize 路径还必须把 FINAL SnapshotSummary 持久化为 repository commit/ref 内的隐藏系统表；这份 hidden summary 是 history compare / archive 的正式事实来源，不是可选 cache，也不是可以事后重建的轻量摘要。

## RepositoryImportPlan

```text
RepositoryImportPlan:
  repository_id
  base_ref_or_commit
  target_branch_ref
  source_snapshot_id
  source_snapshot_digest
  table_ruleset_version
  import_contract_version
  provider_preference:
    AUTO
    SQL_DUMP_REPLAY
    SINGLE_TABLE_CLI_IMPORT
    MULTI_TABLE_CLI_IMPORT
    BATCH_INSERT_SQL
    DOLT_TABLE_IMPORT
    LOAD_DATA
    PARQUET_IMPORT
    DOLT_SERVER_BULK_LOAD
    SERVER_SESSION_BULK_LOAD
  benchmark_modes optional
  server_mode:
    DISABLED | PER_IMPORT | WARM_SESSION
  tables:
    - table_name
      descriptor
      target_table_name
      import_mode: REPLACE_TABLE | UPSERT_TABLE | CREATE_ONLY
      schema_mode: SOURCE_CREATE_SQL | DESCRIPTOR_DDL | IMPORT_SCHEMA_FILE
      import_artifact_ref optional
  commit_message
  validation_policy:
    DISABLED | VERIFY_SCHEMA_ROW_COUNT_SUMMARY | VERIFY_TABLE_DIGESTS | VERIFY_ROW_COUNT_ONLY
  validation_table_names optional
```

第一版 `schema_mode` 默认：

```text
SOURCE_CREATE_SQL
```

即 Dolt import 优先使用原始 `CREATE TABLE`。业务 schema change 判定由 compare schema facts 负责，不由 Dolt import capability 判断。

`validation_table_names` 是运行时参数，不要求固定写死在配置文件里。业务流程可以根据已解析的 SQL、表风险分级或业务节点类型动态构造 `RepositoryImportPlan`，再把需要做 row digest 的关键表传进来。`dataset.yaml` 里的 `validation_tables` 只是 benchmark 和本地样本的默认值来源。

## Dolt Repository API Boundary

未来独立 Dolt repository service/API 应接受 repository-level contract。

允许出现：

```text
repository_id
base_commit / base_ref
target_ref / target_branch
source_snapshot_digest
table descriptors
import artifact refs
validation policy
provider preference
benchmark modes
idempotency key
```

不得出现：

```text
workspace_id
preview_id
upload_generation
submission_id
review status
archive business state
```

如果业务侧需要关联这些 ID，应在业务 operation metadata 中保存，不进入 Dolt repository API contract。

## Provider Modes

Dolt repository 模块可以在内部封装多种 import 模式。

| Mode | 输入形态 | 角色 |
| --- | --- | --- |
| `SQL_DUMP_REPLAY` | 原始 SQL 或规范化 SQL fragment | correctness baseline，第一阶段默认候选。 |
| `SINGLE_TABLE_CLI_IMPORT` | 单表 CSV/JSON/Parquet + schema | 单表 CLI import 对照和 fallback。 |
| `MULTI_TABLE_CLI_IMPORT` | 多表 staging artifacts | 多表 CLI 批量导入候选。 |
| `BATCH_INSERT_SQL` | reader rows -> 多行 `INSERT` | 小表、测试、fallback、对照实验。 |
| `DOLT_TABLE_IMPORT` | Dolt table import 支持的 staging artifact + schema | Dolt CLI import 的通用能力名；benchmark 中应进一步细分为单表、多表、Parquet 等模式。 |
| `LOAD_DATA` | CSV/TSV staging file | bulk load 候选。 |
| `PARQUET_IMPORT` | Parquet staging file + explicit schema | 列式 staging 候选，适合与 CSV/TSV bulk load 对比。 |
| `DOLT_SERVER_BULK_LOAD` | 临时 Dolt sql-server + client loader | 大包实验路线。 |
| `SERVER_SESSION_BULK_LOAD` | warm server session + client loader | 一段时间内复用 server 的批量导入路线。 |

规则：

- 业务后端表达 provider preference 或 benchmark modes，不直接管理 CLI/server 细节。
- CLI/server/provider 选择、server lifecycle、Dolt-local cache 使用由 Dolt repository 模块诊断和封装。
- `SnapshotTableReader` 不输出 SQL literal，不选择 provider。
- `BATCH_INSERT_SQL` 不应成为大表主路径。
- schema-backed import 是安全 contract；不带 schema 的 CSV create-import 不进入第一批 benchmark，因为可能产生 keyless table。
- `LOAD_DATA` 第一版固定走 `dolt sql-server` 路由，不把离线 `dolt sql` 当作正确 contract。
- CSV/TSV staging 必须固定行尾、NULL token 和列顺序；当前实现使用 LF 行尾，并通过内部哨兵分别编码 SQL `NULL` 与字面量 `"NULL"`，列顺序来自 table descriptor/schema。
- 仓库目录名或数据库名含连字符等特殊字符时，server/client provider 必须正确引用 database name。

## 实现注意事项

第一轮实现和真实数据 smoke 中确认了几条容易踩坑的约束，后续 provider 扩展时应默认遵守：

- `LOAD DATA` 只能通过 `dolt sql-server` 配合 `local_infile=1` 路由，不应把离线 `dolt sql` 当作等价实现。
- `PER_IMPORT` 和 `WARM_SESSION` 两类 server provider 的实际工作目录应以活跃 `DoltServerSession.repo_dir` 为准，不能仅依赖预先推导的 repo 路径。
- `dolt table import` 的 staging 文件可以按 provider 单独生成，CLI import 更适合使用 JSONL / Parquet 这类明确表达 schema 的临时文件，而不是直接复用面向 artifact 输出的 CSV/TSV。
- `Dolt` 的 JSON readback 可能省略 `NULL` 列，并且对部分值做字符串化或保留原始字段名大小写；读回校验必须先做列名 canonical 化和类型归一化，再计算 digest。
- `SOURCE_CREATE_SQL` 路径下的 staging 文件必须优先使用 `display_name` 对应的原始标识符，而不是 snapshot 里的 canonical `name`；否则混合大小写的业务表会在 `JSONL` / `Parquet` / `LOAD DATA` 阶段出现列名找不到或值错位的问题。
- `small_cut` 里暴露的 `U_INT32`、`1:INT` 这类值属于常规业务数据，不是极端样本；归一化逻辑必须基于列的 `scalar_type` family 做判断，不能靠字符串子串猜测类型，也不能因为局部值解析失败就让整条 import 直接崩溃。
- `LOAD DATA` 的 TSV staging 不能直接把字面量 `NULL` 当普通文本输出，否则 MySQL 可能把它当成真正空值；当前实现对 SQL `NULL` 和字面量 `"NULL"` 使用不同内部哨兵，并在 `SET` 阶段分别还原为真正空值和字符串值，保证文本列语义不丢失。
- readback validation 对字符串型 compare key 需要使用二进制排序语义，而不是默认的大小写不敏感排序，否则业务数据里同名不同大小写的键会出现顺序偏差。
- `PARQUET_IMPORT` 需要在 staging 前把日期、时间、整型、decimal 等值规范化成适合 parquet writer 的类型，不能直接把字符串表示原样写入。
- `SERVER_SESSION_BULK_LOAD` 的 commit / validation 必须针对同一个活跃 server repo 进行，导入成功后仍要显式 `add` / `commit` / `readback`，不要假定 server 已自动提交。

## 归一化性能

当前归一化位于 staging / readback / validation 层，属于按行按列的线性处理。它的目的不是做复杂推断，而是把真实业务数据中的常规表示统一到稳定的比较形式。

- 对 `small_cut` 这类常规业务子集，归一化开销主要体现在 Python 侧的轻量字符串和类型转换，不在 SQL parser 热路径里。
- 近期 `business_small_cut` benchmark 显示，`LOAD DATA` 的 staging 仍然只有几十毫秒量级，整体耗时主要由数据库 import 和 readback validation 决定。
- 如果后续数据量显著放大，再考虑把最热的逐值转换改成更批量化的实现；当前不建议为了这类常规数据把归一化降级成可选功能。

## Writer Lease 与幂等

正式 repository import 必须持有 repository writer lease。

Lease 范围包含：

```text
checkout/reset target branch
drop/replace/import tables
commit
create/update allowed ref
cleanup provider staging state
```

幂等要求：

- 同一 idempotency key 和相同 import plan 重试应得到同一 commit/ref 或等价成功。
- branch reset、drop table、replace table 需要记录 before/after commit。
- 失败后必须能重试或明确 final failure。

Warmup/shadow import 可以使用临时 branch/ref，但也必须有 cleanup 和 idempotency boundary。

## Retention / Cleanup

Repository import 的默认策略是“保留正式结果，回收临时资源”。

- `repository_path`、`commit_hash`、`target_ref` 和 validation/readback 结果属于正式导入结果；只要 import 被视为 `PASSED`，这些输出就应保留，不能由 flow cleanup 自动删除。
- `cleanup_duration_ms` 只表示临时资源回收成本，不表示 committed repo 已被删除。
- 当前实现会保留 `run_dir`、`repository_path` 和 benchmark / diagnostic 产物，方便后续 open/readback、排障和结果复盘。
- cleanup 只负责关闭 owned server session、释放 scratch files 和 provider-private staging workdir 等临时资源。
- 如果后续要引入 TTL / pin / eviction，优先作用于 caller-owned run roots 和 caches，不要把 immutable repository refs 作为默认可清理对象。

## Validation

成功分两层：

```text
Dolt write succeeded
Snapshot validation succeeded
```

正式写入成功依赖第二层。

Validation 输入：

```text
source_snapshot_digest
source_raw_state_digest
readback_snapshot_digest
readback_raw_state_digest
validation_policy
```

规则：

- `DISABLED` 直接跳过 readback validation，只适合临时降级或纯吞吐观察，不参与 correctness 结论。
- `VERIFY_ROW_COUNT_ONLY` 只比较表是否可读和 row count，成本最低，适合最轻量的健康检查。
- `VERIFY_SCHEMA_ROW_COUNT_SUMMARY` 比较所有表的 schema facts + row count summary，不读取整表数据。
- `VERIFY_TABLE_DIGESTS` 在 summary 校验之外，对 `validation_table_names` 指定的少量关键表追加 row digest 校验。
- 如果 `validation_table_names` 为空，`VERIFY_TABLE_DIGESTS` 默认退化为对全部表做 row digest 校验，保持当前全量校验行为。
- row digest 读取全表内容，主要用于捕捉列值错位、NULL / 转义 / 类型归一化错误、行丢失或重复等问题，成本明显高于 summary 校验，因此只建议用于小 fixture、关键表或高风险首次落库节点。
- 业务第一次创建项目或首次落库时，可以选更严格的 `VERIFY_TABLE_DIGESTS`；后续常规节点通常只保留 `VERIFY_SCHEMA_ROW_COUNT_SUMMARY`；如果 summary 校验也过重，可以显式切到 `DISABLED`。
- provider 自报 digest 不能替代 readback/summary provider 校验。
- readback validation 还应验证 hidden summary table 的存在、版本和摘要一致性；若该表缺失或损坏，应视为 final failure。
- validation mismatch 是 final failure。
- validation succeeded 是 cache 正式化的权威信号；commit/finalize 是 Dolt 数据和正式 cache 的权威流程点。

## Cache Handoff

Repository import 可以使用 warmup 产生的 cache candidate，但必须按候选处理。

readback validation 和 repository-ref readback 的 cache 优化应由 repository_server / provider / session 层自动完成；调用方只需要提供 `repo_dir`、`plan` 和验证策略，不需要手动查询 cache key。cache miss 时回退到直接 readback 和验证，语义不变。

Lookup policy：

```text
WARMUP_CALLER:
  can_write: PROVISIONAL
  can_promote: false

FINALIZE_WRITE_CALLER:
  can_read: PROVISIONAL | CONTENT_VERIFIED | COMMIT_VALIDATED
  must_validate_again: true
  can_promote: true

READ_ONLY_CALLER:
  can_read: COMMIT_VALIDATED
  must_validate_again: descriptor/manifest digest check
```

Promotion 条件：

```text
repository import succeeded
readback snapshot/table digest matched source Snapshot
artifact manifest digest matched
```

Promotion 输出 metadata：

```text
validation_status = COMMIT_VALIDATED
repository_id
commit_hash
validated_by_operation_id
validated_at
```

规则：

- Promotion 不改变 cache key payload。
- producer operation/workspace/upload generation 只作为 metadata/diagnostics。
- Promotion 失败不得回滚已成功的 L2 repository commit/ref，但应记录 operation diagnostics 并允许后续重建 cache。

## Import Artifact

`RepositoryImportArtifact` 可以由以下来源生成：

```text
SourcePackage SQL
SnapshotTableReader streaming rows
SnapshotTableArtifact Parquet rows
```

格式候选：

```text
CSV / TSV
Parquet
JSON
SQL fragment
provider-private staging
```

第一版建议：

- 保留原始 SQL replay，作为 `SUBMIT_FINALIZE` 和 correctness baseline 的默认输入。
- CSV/TSV/Parquet 只作为 provider-specific staging 候选，replay-only finalization 可以不生成它们。
- 不要求 `SnapshotTableArtifact` 与 `RepositoryImportArtifact` 是同一个对象。
- `RepositoryImportArtifactBuilder` 可以在 legacy / provider-specific layout 下按 `row_layout_digest` 复用已经生成的 row files；`row_layout_digest` 由 canonical raw content digest 和 canonical export schema content 组合而成，后出现的重复表可以直接指向先出现表的 CSV/TSV/Parquet 文件。
- 这类复用只影响物理 row file 数量，不等于 replay.sql 已按“权威重复关系”剪枝；当前 replay.sql 仍按 table 逐个生成，是否进一步按重复分组压缩 replay 内容，需要单独的设计决策。
- 这类复用只影响物理 row file 数量，不改变 table manifest、summary、validation 或 canonical cache 的语义。
- 对于 `SUBMIT_FINALIZE` replay-only 和 replay-only benchmark，当前默认 artifact layout 是 `REPLAY_ONLY_MINIMAL`：每表只生成一个 `tables/<table>/table.json`，bundle 只生成 `bundle.json`，同时生成顶层 `replay.sql`。
- 该 layout 不生成 CSV/TSV/Parquet，也不生成 per-table `manifest.json` / `schema.json`。
- 这类收缩后，单次 build 的文件数大致等于 `table_count + 2`，具体仍以实际选中的表数为准。
- 如果后续仍要进一步减少 small file fan-out，优先考虑把 table-level replay / metadata 聚合成更粗粒度的 artifact bundle；这属于 artifact layout 优化，不是当前 flow contract 必须立即重写的部分。

## Dolt Server Lifecycle

如果启用 server bulk load：

```text
acquire writer lease
start or reuse dolt sql-server
health check
bulk load
commit
shutdown or release server session
cleanup
release lease
```

`server_mode`：

```text
DISABLED
PER_IMPORT
WARM_SESSION
```

需要诊断：

```text
server_start_ms
health_check_ms
load_ms
commit_ms
shutdown_ms
port_or_socket_id
dolt_version
failure_phase
```

不得把 server lifecycle 暴露给前端或业务 contract。

## Benchmark Contract

Benchmark 可在 Dolt repository 模块内独立运行，也可由上层 operation 以 shadow mode 调用。Shadow result 不参与业务状态。

Benchmark orchestration 是基于正式 capability 的诊断组合层，不定义新的 repository import contract。正式能力的输入、输出和错误语义仍以 `RepositoryImportPlan` / `RepositoryImportResult` / readback validator 为准；runner 只负责把 dataset / profile / provider 组合映射为正式 capability 调用，并把结果写成 summary/report。
当前四类 benchmark profile 都通过 `FINALIZE_WRITE_CALLER` 执行完整写入路径，benchmark 只显式传递正式 caller policy，不在 benchmark contract 里引入新的 caller 语义。`SERVER_SESSION` profile 可以复用 warm server session，但这个复用只属于 benchmark 编排，不改变 capability contract。

Runner 的边界原则：

- 不在 runner 内引入 lease、branch policy、idempotency 规则或 provider 语义的第二份实现。
- `profile` 只影响 benchmark 编排，不进入 repository import capability contract。
- `requested_tables`、server reuse 和 validation 选择应由 benchmark 场景层决定，但必须最终收敛到正式 capability 的单一输入源。
- 如果 benchmark 暴露出 capability 设计问题，优先修正式 capability，而不是让 benchmark 继续长出独立分支。

### Functional Baseline

截至 2026-06-20 的功能测试结果：

```text
dolt_version: 2.1.8
test_result: git tag docs/p2-p3-cleanup-pre-20260817 path docs/backend-vnext/dolt-test/dolt-import-provider-functional-test-result-2026-06-20.md
```

已通过 correctness smoke test 的 provider：

```text
SQL_DUMP_REPLAY
SINGLE_TABLE_CLI_IMPORT
MULTI_TABLE_CLI_IMPORT
LOAD_DATA
PARQUET_IMPORT
DOLT_SERVER_BULK_LOAD
SERVER_SESSION_BULK_LOAD
```

该结论只说明这些 provider 具备进入 benchmark 的功能条件，不代表默认 provider 已确定。

统一输入：

```text
repository_id
base_commit
source_snapshot_digest
same table set / import artifacts
same validation policy / validation_table_names
isolated target ref / temp branch
same cleanup policy
```

第一批 benchmark provider：

```text
SQL_DUMP_REPLAY
SINGLE_TABLE_CLI_IMPORT
MULTI_TABLE_CLI_IMPORT
LOAD_DATA
PARQUET_IMPORT
DOLT_SERVER_BULK_LOAD
SERVER_SESSION_BULK_LOAD
```

不进入第一批大表性能 benchmark：

```text
BATCH_INSERT_SQL
```

`BATCH_INSERT_SQL` 只保留为小表 fallback、调试和 correctness 对照。

### Benchmark Data Strategy

第一版 benchmark 以真实业务 SQL 为主输入。可提供的数据形态是原始 SQL 文件，通常只包含：

```text
DROP TABLE optional
CREATE TABLE
INSERT INTO ... VALUES ...
```

数据准备分阶段进行：

| Dataset | 来源 | 目标 | 第一版要求 |
| --- | --- | --- | --- |
| `business_small_cut` | 实际业务数据裁切 | 快速 correctness 和小规模性能反馈 | 必选。 |
| `business_small` | 小型实际业务数据 | 验证真实表结构、真实行分布和 provider contract | 必选。 |
| `business_medium` | 最常见业务规模 | 第一版默认路线选择的主要依据 | 必选。 |
| `business_large` | 偏大的实际业务规模，不追求极限 | 验证大包异步 import、server provider 和 cleanup 成本 | 建议。 |
| `generated_correctness` | 程序构造 | 补充真实数据难覆盖的 `NULL`、引号、逗号、宽表等语义 | 可选。 |
| `generated_stress` | 程序构造 | 在真实大业务数据跑过后，按需寻找容量上限或瓶颈 | 延后。 |

规则：

- 不把明显脱离业务实际的数据分布放进第一批 benchmark。
- `generated_stress` 不能替代 `business_medium` / `business_large` 的结论。
- 如果 `business_large` 已经暴露主要瓶颈，第一阶段不需要额外构造极限大数据。
- 数据准备可以分批完成；runner 必须允许只跑已准备好的 dataset，并保留可追加结果。
- 每个 dataset 必须记录 dataset manifest，不要求公开业务内容。

Dataset manifest 至少包含：

```text
dataset_id
dataset_kind: BUSINESS_SMALL_CUT | BUSINESS_SMALL | BUSINESS_MEDIUM | BUSINESS_LARGE | GENERATED_CORRECTNESS | GENERATED_STRESS
source_sql_digest
source_sql_bytes
table_count
row_count_total
largest_table_row_count
insert_statement_count optional
validation_table_names optional
business_label optional
anonymization_note optional
created_at
```

目标机器资源暂时不作为设计 blocker。Benchmark 结果只允许在同一个 machine profile 内横向比较 provider；跨机器结果只能看趋势，不能直接判定默认 provider。

Machine profile 至少记录：

```text
machine_profile_id
os
cpu_model optional
cpu_count
memory_total_mb
disk_type optional
filesystem optional
dolt_version
python_version
mysql_client_version optional
```

### Benchmark Profiles

第一版至少分四类 profile：

| Profile | 目标 | 说明 |
| --- | --- | --- |
| `IMPORT_HEALTH_SMOKE` | 验证 provider contract | 小 fixture，全 provider 跑 schema/row-count summary，必要时对关键表追加 row digest。 |
| `END_TO_END_COLD` | 比较从原始 SQL 到 Dolt commit 的完整冷路径成本 | parse、staging、import、commit、validation 都计时。 |
| `IMPORT_ONLY_WARM_ARTIFACT` | 比较已有 import artifact 时的导入成本 | 排除或单独记录 parse/staging 生成时间。 |
| `SERVER_SESSION` | 验证 warm server 复用收益 | 多轮顺序导入，记录 server startup amortization。 |

每个 provider 必须使用同一份逻辑输入：

```text
same Snapshot / SnapshotTableSet
same table descriptors
same raw CREATE TABLE or schema files
same row values and NULL semantics
same validation policy / validation_table_names
same target Dolt version
```

Provider-specific staging 可以不同，但必须记录 manifest digest 和生成耗时。

记录：

```text
run_id
profile
provider
server_mode
table_count
row_count
staging_artifact_bytes
parse_duration_ms
staging_duration_ms
server_start_ms optional
import_duration_ms
commit_duration_ms
validation_duration_ms
cleanup_duration_ms optional
total_duration_ms
rows_per_second
memory_peak optional
dolt_version
provider_contract_version
import_artifact_manifest_digest
source_snapshot_digest
readback_snapshot_digest
validation_result
failure_phase optional
failure_reason optional
```

Dataset 和环境字段也必须进入 result：

```text
dataset_id
dataset_kind
machine_profile_id
source_sql_digest
source_sql_bytes
table_count
row_count_total
largest_table_row_count
```

### Runner Contract

Benchmark runner 是诊断工具，不是业务 API。它可以调用 repository import capability，但不得依赖 Workspace、Preview、Submission 等业务模型。

Runner 分层：

```text
DatasetResolver
  -> DatasetManifestBuilder
  -> SourceSqlAnalyzer / SnapshotMaterializer
  -> ImportArtifactBuilder
  -> ProviderRunner
  -> DoltReadbackValidator
  -> BenchmarkResultWriter
```

每层职责：

| Layer | 职责 | 可独立测试 |
| --- | --- | --- |
| `DatasetResolver` | 解析外部 dataset root、选择 dataset/profile/provider 矩阵。 | 是 |
| `DatasetManifestBuilder` | 计算 source SQL digest、规模统计和 dataset manifest。 | 是 |
| `SourceSqlAnalyzer` / `SnapshotMaterializer` | 从原始 SQL 生成 Snapshot/Summary/TableSet 或等价 provider 输入。 | 是 |
| `ImportArtifactBuilder` | 为 CLI/LOAD DATA/Parquet/server provider 生成 staging artifact。 | 是 |
| `ProviderRunner` | 执行单个 provider 的导入、commit 和 cleanup。 | 是 |
| `DoltReadbackValidator` | 从 Dolt readback 并校验 digest。 | 是 |
| `BenchmarkResultWriter` | 写入 `summary.json`，并从 JSON 生成报告。 | 是 |

Runner 输入建议：

```text
--dataset-root <external business benchmark data root>
--run-root /tmp/backend-vnext-repository-import-benchmark/<run_id>
--result-out docs/backend-vnext/_tmp/repository-import-benchmark-result-<date>.md
--profiles IMPORT_HEALTH_SMOKE,END_TO_END_COLD,...
--providers SQL_DUMP_REPLAY,PARQUET_IMPORT,...
--datasets business_small_cut,business_medium,...
```

业务 SQL 数据不进入 git。Dataset root 建议结构：

```text
business-benchmark-data/
  business_small_cut/
    dbcfg.sql
    dataset.yaml optional
  business_small/
    dbcfg.sql
    dataset.yaml optional
  business_medium/
    dbcfg.sql
    dataset.yaml optional
  business_large/
    dbcfg.sql
    dataset.yaml optional
```

`dataset.yaml` 只保存非敏感描述：

```yaml
dataset_id: business_medium_001
dataset_kind: BUSINESS_MEDIUM
business_label: common-real-project
notes: real business sql, not committed
source_sql_file: dbcfg.sql
validation_tables:
  - critical_table_a
  - critical_table_b
```

Runner 输出：

```text
<run-root>/
  summary.json
  report.md
  datasets/
  artifacts/
  repos/
  logs/
```

`summary.json` 是权威结果；`report.md` 必须由 `summary.json` 生成，不手工维护结论，避免报告与机读结果不一致。

`summary.json` 顶层结构：

```json
{
  "run_id": "repository-import-benchmark-2026-06-20-001",
  "created_at": "2026-06-20T00:00:00Z",
  "machine_profile": {},
  "datasets": [],
  "providers": [],
  "results": []
}
```

单条 result 至少包含：

```json
{
  "dataset_id": "business_medium_001",
  "dataset_kind": "BUSINESS_MEDIUM",
  "profile": "END_TO_END_COLD",
  "provider": "PARQUET_IMPORT",
  "status": "PASSED",
  "validation_result": "PASSED",
  "commit_hash": "optional",
  "source_snapshot_digest": "sha256...",
  "readback_snapshot_digest": "sha256...",
  "parse_duration_ms": 0,
  "staging_duration_ms": 0,
  "server_start_ms": null,
  "import_duration_ms": 0,
  "commit_duration_ms": 0,
  "validation_duration_ms": 0,
  "cleanup_duration_ms": null,
  "total_duration_ms": 0,
  "failure_phase": null,
  "failure_reason": null
}
```

建议执行阶段：

| Phase | Dataset | Profile | Provider |
| --- | --- | --- | --- |
| A | `business_small_cut` | `IMPORT_HEALTH_SMOKE` | all first-benchmark providers |
| B | `business_small`, `business_medium` | `END_TO_END_COLD` | all first-benchmark providers |
| C | `business_medium`, `business_large` | `END_TO_END_COLD`, `IMPORT_ONLY_WARM_ARTIFACT`, `SERVER_SESSION` | top candidates from Phase B |

有效性规则：

- 只有 `validation_result = PASSED` 的 result 可以参与性能排序。
- `status = PASSED` 必须同时表示 provider 执行成功、commit 成功、readback validation 成功和 cleanup 达到可接受状态。
- 命令成功但 digest mismatch 必须记录为 failed result。
- `report.md` 中的推荐 provider 必须来自同一 machine profile、同一 dataset/profile 横向比较。
- runner 可以分批追加 dataset 或 profile，但每次追加必须保留独立 `run_id` 或明确 parent run。

### Selection Rules

Provider 入选为可用候选必须满足：

- `IMPORT_HEALTH_SMOKE` 通过 schema/row-count summary 校验，关键表可以额外启用 row digest。
- staging contract 可重复生成，manifest digest 稳定。
- import 成功后 commit/ref 可审计。
- validation mismatch 必须被识别为 final failure。
- 临时文件、branch/ref、server session 可清理或可过期回收。

默认 provider 的选择不能只看单次耗时。第一版建议按以下顺序判定：

1. correctness 与可重试性优先。
2. 优先以 `business_medium` 的 `END_TO_END_COLD` 作为默认路线选择依据。
3. 对 server provider 单独比较 `server_start_ms` amortization，确认 warm session 是否覆盖生命周期成本。
4. 对 staging-heavy provider 同时比较 `END_TO_END_COLD` 和 `IMPORT_ONLY_WARM_ARTIFACT`。
5. 用 `business_large` 验证大包异步 import 的稳定性和 cleanup 成本。
6. 失败率、cleanup 成功率、diagnostics 完整度必须进入决策。

在 benchmark 结论固化前，`SQL_DUMP_REPLAY` 继续作为 correctness baseline；性能默认路线可由 shadow benchmark 逐步切换，但不能跳过 readback validation。

## 第一版取舍与后续演进

第一版固定选择：

- Repository import 是异步重负载能力，不进入 upload preview、history compare 等直接反馈路径。
- `SOURCE_CREATE_SQL` 是默认 schema mode，优先使用原始 `CREATE TABLE`。
- `SQL_DUMP_REPLAY` 保留为 correctness baseline。
- `SUBMIT_FINALIZE` 当前固定为 `SQL_DUMP_REPLAY` replay-only；provider 切换仍保留在 repository import capability / benchmark 低层，后续如需切换 submit finalize，再单独修改 flow contract。
- `LOAD_DATA` 固定通过 `dolt sql-server` 路由。
- 第一批 provider benchmark 以真实业务 SQL 的小、中小、中、大四档为主。
- 默认 validation 优先使用 `VERIFY_SCHEMA_ROW_COUNT_SUMMARY`；`DISABLED` 只用于纯吞吐观察，不参与 correctness 结论。
- Provider 成功不等于 import 成功；commit 和 readback validation 仍是 import result 的必要组成。

后续可能变化：

- 根据 benchmark 结果选择默认 import provider，可能从 `SQL_DUMP_REPLAY` 切换到 server/bulk/staging 路线。
- `VERIFY_TABLE_DIGESTS` 可只对关键表或首轮项目创建启用，避免全量行校验成为常规负载。
- JSONL / Parquet / CSV / TSV staging 格式可继续优化，但 provider contract 仍以 Snapshot/TableSet 为输入。
- Dolt repository module 可独立容器化，对外暴露网络 API 或 Unix socket。
- server warm session、provider staging cache、repository server table cache 的 TTL、清理和并发策略后续单独设计。
- benchmark orchestration 直接复用正式 capability，不额外维护独立 parser、digest 或 staging contract；如需优化，只在编排层调整 provider / session 组合。

## 验收标准

- Dolt repository API contract 不包含业务模型 ID 或业务状态。
- Direct-response/read-only caller 不执行 repository import。
- Finalize/write caller 的 import 在 writer lease 范围内执行。
- 第一批 benchmark provider 对同一 Snapshot 执行 `IMPORT_HEALTH_SMOKE` 后，summary 校验一致；必要时关键表的 row digest 也应一致。
- `SQL_DUMP_REPLAY` 作为 correctness baseline 保留，任何性能候选都不得绕过导入后 validation。
- Repository import 写入成功但 readback digest mismatch 时，operation final failure。
- 临时或 warm Dolt server 失败能区分 retryable/final 并记录 lifecycle diagnostics。
