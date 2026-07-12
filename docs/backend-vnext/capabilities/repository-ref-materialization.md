# Repository Ref Materialization Capability

本文定义 `RepositoryRef -> Snapshot + SnapshotSummary + SnapshotTableSet` 的第一版实现设计。它是 `snapshot_materialization` 的 repository source provider，不是业务 flow，也不是 repository import。

总览 contract 见 `snapshot-materialization.md`。本文补充实现边界、`RepositoryRefSession` API、row stream 格式、scalar encoding 责任、cache 关系和验收标准。

## 定位

`repository_ref_materialization` 消费 repository/Dolt 中已存在的 commit/ref，把它归一化为 backend vNext 的 Snapshot 模型。

```text
RepositoryRef
  -> RepositoryTableAccessProvider.open_ref()
  -> RepositoryRefSession
  -> RepositoryTableCatalog
  -> RepositoryTableReader / RepositoryTableExportArtifact
  -> snapshot_materialization.repository_ref_materialization
  -> Snapshot + SnapshotSummary + optional SnapshotTableSet
```

规则：

- Capability 不知道 upload、submit、history compare、archive 等 flow 名称。
- Capability 不推进业务状态，不创建 repository commit，不执行 repository import。
- Capability 不直接消费 table ruleset 的业务语义；`table_ruleset_version` 只作为 Snapshot version context。
- Capability 可以被 flow、operation、benchmark、测试直接调用。
- 对外 `source_kind` 固定使用 `IMMUTABLE_REPOSITORY_REF`，不再保留旧别名。
- 同一 immutable repository ref、digest contract version、materialization contract、scalar encoding version 下，重复 materialization 应得到相同 `snapshot_digest`。
- Capability 应优先读取 repository commit/ref 内的 hidden summary table 来恢复 SnapshotSummary；如果该表缺失、版本不匹配或摘要不一致，应直接失败，而不是重新计算一套“轻量摘要”。
- 没有可用 compare key 的表保持 keyless 事实，不应在 repository ref materialization 侧自动补 surrogate key。

## 分层边界

### Flow / Operation

负责：

- 选择要 materialize 的 `repository_ref`。
- 选择同步或异步。
- 选择 `requested_tables`。
- 选择 `materialization_policy`、`cache_policy`、`timeout_policy`、`artifact_policy`。
- 要求 operation READY 前完成必要 artifact closure。
- 推进业务状态。

不负责：

- 手写 repository table reader。
- 手写 Snapshot digest。
- 手写 repository server cache restore。

### Snapshot Materialization Capability

负责：

- 调用 `RepositoryTableAccessProvider`。
- 用 catalog 生成 `SnapshotTableDescriptor` 和 `SnapshotSummary`。
- 把 repository row stream 归一化为 Snapshot row stream。
- 计算 `compare_schema_digest`、`raw_content_digest`、`snapshot_digest`。
- 输出 `SnapshotTableSet` 或 table artifacts。
- 记录 diagnostics 和 cache diagnostics。

不负责：

- repository ref/branch 写入。
- repository import / commit。
- repository server lifecycle 私有优化。
- comparison projection、risk、surface。

### Repository Server / Dolt Repository Module

它是独立技术模块，可以未来容器化为网络 API 或 Unix socket 服务。

负责：

- repository open / close。
- ref resolve。
- catalog read。
- table stream read（primary row path）。
- table export（optional secondary fast path）。
- native diff access for repository-backed comparison provider。
- repository-local table cache。
- Dolt CLI / sql-server / API 细节。

不负责：

- 产出 `Snapshot`、`SnapshotSummary` 或 `SnapshotTableSet`。
- 产出 `ComparisonFacts`、`ComparisonRecords`、RiskEvaluation、ComparisonSurface 或 Bundle。
- 理解 Workspace、Submission、History request 等业务模型。
- 理解 table ruleset、ignored columns、comparison digest 或 business digest。
- 使用 backend vNext capability cache 的 `PROVISIONAL` / `COMMIT_VALIDATED` 可信等级。

repository server 内部可以按 technical capability 拆分：

```text
repository_server/
  ref_session.py
  catalog.py
  table_reader.py
  table_export.py
  native_diff.py
  table_cache.py
  dolt_backend.py
```

这些是 repository-local technical capabilities，不是业务 capabilities。

## 输入输出

```text
RepositoryRefMaterializationInput:
  repository_ref
  repository_table_access_provider
  digest_contract_version
  table_ruleset_version
  scalar_encoding_version
  snapshot_materialization_contract_version
  row_materialization_profile
  requested_tables optional
  materialization_policy:
    DESCRIPTOR_ONLY | READERS_REQUIRED | ARTIFACTS_REQUIRED
  cache_policy:
    DISABLED | READ_ONLY | WRITE_THROUGH
  cache_lookup_policy optional
  artifact_policy optional
  timeout_policy optional
```

`timeout_policy` 第一版：

```text
RepositoryRefTimeoutPolicy:
  open_ref_timeout_ms optional
  operation_timeout_ms optional
  catalog_timeout_ms optional reserved
  table_reader_open_timeout_ms optional reserved
  table_read_idle_timeout_ms optional reserved
```

第一版要求支持：

- `open_ref_timeout_ms`
- 上层 operation 总 timeout
- `digest_contract_version` 作为 snapshot digest 语义输入

其他 timeout 先作为 diagnostics / future fields 预留。

规则：

- `digest_contract_version` 应与 `snapshot_digest` 生成口径一致，并进入同一输入集合。
- `digest_contract_version` 只描述内容 digest 语义，不描述 repository provider 实现版本。

输出沿用 `SnapshotMaterializationResult`：

```text
SnapshotMaterializationResult:
  snapshot
  summary
  table_set optional
  table_artifact_refs optional
  cache_diagnostics
  diagnostics
```

## RepositoryRefSession API

第一版 API：

```text
RepositoryTableAccessProvider:
  open_ref(repository_ref, timeout_policy) -> RepositoryRefSession

RepositoryRefSession:
  get_catalog() -> RepositoryTableCatalog
  open_table_reader(table_name) -> RepositoryTableReader
  export_table_artifact(table_name, format) -> RepositoryTableExportArtifact optional
  close()
```

### Row Path First

- `open_table_reader()` / `stream_rows()` 是 repository-backed materialization 和 readback 的默认 row path。
- repository_server 第一版不需要把 `table_export` 扩展成格式矩阵来承载 cache 语义；如果只是为了拿到 rows 再做后续 diff、snapshot 或打包，优先由调用方消费 row stream 并在下游转换。
- `export_table_artifact()` 保持 optional，先作为后续 benchmark 证明必要时再打开的 fast path。

### open_ref

语义：

- read-only。
- 不修改 repository。
- 不创建 backend vNext durable artifact。
- 不推进业务状态。
- 成功后 session 必须 pin 到 `resolved_commit_hash`。
- 对同一 `repository_ref` 重复调用可以返回不同 session 对象。
- 如果传入可变 branch/ref，两次调用之间 ref 移动时，可以 resolve 到不同 commit；每个成功 session 内必须固定自己的 commit。
- 调用方需要完全相同输入时，应传 immutable commit hash 或 immutable ref。
- 失败不得留下需要业务层清理的 visible state。

timeout：

- `open_ref_timeout_ms` 覆盖打开 repository、resolve ref 和初始化 session。
- 超时返回 retryable failure：`REPOSITORY_REF_OPEN_TIMEOUT`。
- 如果已 resolve commit 但 session 未完整初始化，不能返回半初始化 session。
- timeout 后 provider 必须尽力关闭底层进程、连接或临时资源。
- timeout policy 不进入 Snapshot digest，只进入 diagnostics。

不要求：

- 返回同一个 session 对象。
- 默认启动长期 server session。
- flow-aware session reuse。

### get_catalog

第一版：

- eager load catalog。
- session 内 memoize。
- 同一 materialization run 对同一 ref 最多加载一次 catalog。
- catalog load 失败返回 `REPOSITORY_CATALOG_LOAD_FAILED`。

不要求：

- lazy partial catalog。
- 多次 list/describe 合并优化公开为 contract。
- catalog 增量更新。

### open_table_reader

第一版：

- 只能打开 catalog 中存在的表。
- 不要求并发 reader。
- 不要求 thread-safe。
- 不要求 reader rewind；调用方需要重读时重新打开 reader。
- reader 失败不影响 session close 幂等。

错误：

```text
REPOSITORY_TABLE_NOT_FOUND
REPOSITORY_TABLE_READER_OPEN_FAILED
REPOSITORY_TABLE_READ_FAILED
```

### export_table_artifact

第一版 optional。

规则：

- reader streaming 是默认路径。
- export artifact 用于后续性能优化、repository server table cache、或 SnapshotTableArtifact 快速生成。
- provider 不支持 export 时返回明确 unsupported diagnostics。
- export artifact 仍必须经 snapshot materialization 校验 descriptor/digest 后才能作为 SnapshotTableArtifact。

### native_diff

第一版 optional。

规则：

- `native_diff` 是 repository server 暴露给 `DOLT_NATIVE` provider 的 repository-local technical API。
- 它只返回 Dolt/repository raw diff、raw schema diagnostics 或 provider-private timing。
- 它不应用 table ruleset、ignored columns、projection、scalar encoding 或 vNext schema policy。
- 它不产出 `ComparisonFacts`、`ComparisonRecords` 或 `comparison_core_cache` value。
- `DOLT_NATIVE` provider 必须通过 `NativeDiffCanonicalizer` 才能把 raw diff 写成 canonical comparison result。

### close

规则：

- 幂等。
- 可以重复调用。
- 必须释放底层进程、连接、临时文件 handle 或 server session lease。
- close failure 进入 diagnostics；不应改变已计算 Snapshot digest。

## RepositoryTableCatalog

第一版 catalog：

```text
RepositoryTableCatalog:
  repository_id
  repository_ref
  resolved_commit_hash
  repository_server_contract_version
  dolt_version optional
  catalog_digest optional
  tables:
    - table_name
      display_table_name optional
      columns:
        - name
          display_name optional
          ordinal
          scalar_type optional
          nullable optional
          raw_type optional
      primary_key_columns
      row_count optional
      repository_table_version optional
      table_root_hash optional
      schema_facts_digest optional
```

规则：

- `table_name` 和 column `name` 可以是 repository server 初步 canonical 后的名称，但 Snapshot materialization 仍必须重新 canonicalize 并检查冲突。
- `display_*` 用于审计、诊断和必要时保持 Dolt 查询引用，不进入业务 digest。
- `row_count` 可选；缺失时 Snapshot materialization 在读表时计数。
- `table_root_hash` / `repository_table_version` 是 repository 技术事实，只能作为加速、cache key 或 diagnostics 输入。
- catalog 不包含 table ruleset、ignored columns、projection schema 或 comparison facts。

## RepositoryTableReader

第一版 row stream 格式建议使用 tuple，而不是 dict。

```text
RepositoryTableReader:
  catalog_table
  column_order: tuple[column.name, ...]
  stream_rows() -> Iterator[tuple[object | None, ...]]
  close()
```

规则：

- tuple 顺序必须等于 catalog column order。
- row 长度必须等于 catalog column count。
- Dolt/driver 传输层省略的 NULL 字段由 repository reader 按 catalog 补齐为 `None`。
- reader 不要求稳定 row order；Snapshot content digest 必须 row-order insensitive。
- reader 不做 business projection，不应用 ignored columns。
- reader 可以做 driver 层必要修正，例如补 NULL、修正字段大小写映射、处理 Dolt JSON 返回结构。
- reader 不做 Snapshot scalar encoding 的最终判定。

不使用 dict 作为第一版 row 格式的理由：

- 避免大小写差异、缺列、额外列在多处重复处理。
- catalog column order 已经足够表达 row shape。
- tuple 更适合 streaming 和 digest 计算。

## Scalar Encoding

第一版正式位置：

```text
backend_vnext/capabilities/snapshot_materialization/scalar_encoding.py
```

共享对象：

- SQL -> Snapshot materialization。
- RepositoryRef -> Snapshot materialization。
- Repository import readback validation。
- Comparison projection digest。

责任：

- 根据 catalog / descriptor 中的 scalar type family 做轻量归一化。
- 输出 canonical JSON-safe scalar。
- 保证同一业务值从 SQL parse 和 Dolt readback 进入 Snapshot 后得到同一 digest。

建议第一版类型族：

```text
NULL -> null
text-like -> string
integer-like -> canonical integer representation
decimal-like -> canonical decimal string
float-like -> stable string/decimal-safe representation; non-finite values forbidden
date/time-like -> normalized string
binary-like -> stable bytes/base64 policy
unknown -> string-preserving fallback + diagnostic
```

异常策略：

- 类型族识别失败：降为 `unknown/text`，记录 diagnostic，不直接失败。
- 值无法按声明类型解析：保留原始字符串形式，记录 diagnostic。
- canonical column 冲突：表级 materialization failure。
- 行缺列：repository reader 应补 `None`；仍缺则 table failure。
- 行多列：忽略 catalog 外额外字段并记录 diagnostic。

现有 benchmark/readback 代码可以作为经验来源：

- Dolt JSON readback 可能省略 NULL 列。
- Dolt 可能字符串化部分数字或时间值。
- 列名大小写需要 canonical 化。
- 字符串 key 排序不能依赖数据库默认大小写不敏感语义。
- 归一化应基于列的 scalar type family，不能靠值字符串猜测。

实现规则：

- 不让 `repository_ref_materialization` import `repository_import.readback`。
- 将可复用逻辑抽到 `snapshot_materialization.scalar_encoding`。
- 当 SQL materialization、repository_ref materialization、readback validation、comparison projection 都稳定共用该模块，且它不再依赖 Snapshot 专有模型时，后续下沉为 `core.scalar_encoding`。

## Materialization 流程

```text
validate input
  -> provider.open_ref(repository_ref, timeout_policy)
  -> session.get_catalog()
  -> build SnapshotTableDescriptor set
  -> build SnapshotSummary from catalog/descriptors
  -> if DESCRIPTOR_ONLY:
       close session or return lazy table_set_ref according to policy
  -> if READERS_REQUIRED:
       build SnapshotTableSet backed by RepositoryTableReader adapters
  -> if ARTIFACTS_REQUIRED:
       stream rows or export table artifact, write SnapshotTableArtifact
  -> compute Snapshot digest
  -> close session when no lazy readers remain
```

规则：

- Table list 只来自 catalog。
- `requested_tables` 只过滤 catalog，不触发 repository server 重新 list。
- `SnapshotSummary` 生成后，后续 `SnapshotTableSet` resolution 复用同一 catalog identity。
- `SnapshotSummary` 的正式事实来源是 hidden summary table；catalog 只负责 row access 和表级校验，不负责替代 summary 事实。
- Comparison 不直接调用 repository server，只消费 `ComparisonInput.summary` 和 `table_set_ref`。
- 如果返回 lazy table readers，必须明确 session/resource 生命周期；第一版建议 operation 内 eager materialize readers/artifacts，避免跨层持有长生命周期 session。

## Digest 责任

repository server 可提供：

```text
table_root_hash
repository_table_version
schema_facts_digest
catalog_digest
```

这些是技术事实。

snapshot materialization 必须计算：

```text
compare_schema_digest
raw_content_digest
snapshot_digest
SnapshotSummary digest
SnapshotTableArtifact manifest digest
```

规则：

- `table_root_hash` 可进入 repository_server_table_cache key。
- `table_root_hash` 可作为 diagnostics 或优化 hint。
- 第一版不得用 `table_root_hash` 直接替代 `raw_content_digest`。
- Snapshot digest 不包含 host path、session id、operation id、flow id 或 repository server cache key。
- row order 不进入 raw content digest。

## Cache 关系

### repository_server_table_cache

它是 repository server 内部技术 cache。

可缓存：

```text
RepositoryTableCatalog
describe/count facts
table root/hash metadata
repository-local export artifacts
provider-private readback/export intermediates
```

建议 key：

```text
repository_id
resolved_commit_hash
table_name optional
dolt_version
repository_server_contract_version
table_root_hash optional
export_format optional
```

规则：

- 不使用 Snapshot digest、projection digest、comparison digest。
- 不使用 `PROVISIONAL` / `COMMIT_VALIDATED`。
- 不理解 table ruleset 或 business digest。
- cache hit 只能减少 repository IO，不能替代 Snapshot descriptor/digest 校验。

第一版简化策略：

- 建议实现跨 session read-through/write-through cache，避免 repository ref materialization 和 history compare 反复执行 catalog/describe/count/table root metadata IO。
- 第一版只缓存小型技术事实：catalog、describe/count facts、table root/hash metadata。
- cache key 必须绑定 immutable resolved commit/ref、`dolt_version` 和 `repository_server_contract_version`。
- cache entry 读取失败、版本不匹配或校验失败时直接丢弃并回退 Dolt IO。
- 不实现 TTL、pin、eviction、quota、远端存储或跨项目复用。
- 不默认缓存 export artifacts 或大表数据文件。
- cache root 可以被人工整体清空；清空不得改变业务语义。

未来计划：

- TTL、pin、eviction、quota、cleanup 后续单独设计。
- export artifact cache 可在 reader streaming 稳定后评估，启用前必须补充 cleanup 和 integrity policy。
- warm server session 与 repository_server_table_cache 可以组合，但对外 API 不变。

### vNext Capability Cache

`snapshot_table_artifact_cache` / `source_snapshot_cache` 是 backend vNext capability cache。

规则：

- 使用 Snapshot/table descriptor/digest 作为 key 输入。
- 使用 `PROVISIONAL` / `CONTENT_VERIFIED` / `COMMIT_VALIDATED` 可信等级。
- 可以消费 repository_server 返回的技术事实作为加速 hint，但必须完成 vNext digest 校验。

## Artifact / Export 路线

第一版默认：

- reader streaming 路线。
- 从 `RepositoryTableReader` 生成 `SnapshotTableDescriptor`、`SnapshotSummary` 和可选 `SnapshotTableSet`。
- 需要 operation-local artifact 时，由 snapshot materialization streaming 写 `SnapshotTableArtifact`。

后续优化：

- repository server `export_table_artifact()` 直接导出 repository-local table artifact。
- snapshot materialization 校验后转为 `SnapshotTableArtifact`。
- repository_server_table_cache 缓存 export artifact。
- benchmark 比较 reader streaming 与 export artifact 路线。

## 错误与诊断

建议错误码：

```text
REPOSITORY_REF_NOT_FOUND
REPOSITORY_REF_OPEN_TIMEOUT
REPOSITORY_REF_OPEN_FAILED
REPOSITORY_CATALOG_LOAD_FAILED
REPOSITORY_TABLE_NOT_FOUND
REPOSITORY_TABLE_READER_OPEN_FAILED
REPOSITORY_TABLE_READ_FAILED
REPOSITORY_TABLE_EXPORT_UNSUPPORTED
REPOSITORY_TABLE_EXPORT_FAILED
REPOSITORY_SCHEMA_UNSUPPORTED
REPOSITORY_IDENTIFIER_COLLISION
REPOSITORY_SCALAR_ENCODING_DIAGNOSTIC
REPOSITORY_SNAPSHOT_DIGEST_MISMATCH
REPOSITORY_SESSION_CLOSE_FAILED
REPOSITORY_SERVER_CACHE_ENTRY_INVALID
```

诊断应至少包含：

```text
repository_id
repository_ref
resolved_commit_hash optional
phase
table_name optional
retryable true/false
repository_server_contract_version optional
dolt_version optional
cache_hit optional
elapsed_ms optional
```

## 测试建议

Unit：

- `open_ref()` timeout 和 failure mapping。
- `close()` 幂等。
- catalog -> descriptor canonicalization。
- tuple row length 校验。
- NULL 补齐。
- scalar encoding 稳定性。
- row-order insensitive content digest。

Contract：

- 同一 immutable ref 重复 materialization 得到同一 Snapshot digest。
- `get_catalog()` 同一 run 只调用一次。
- `requested_tables` 不触发额外 list tables。
- `table_root_hash` 不替代 raw content digest。
- repository server cache hit 后仍执行 Snapshot digest 校验。

Integration：

- Dolt commit/ref -> SnapshotSummary。
- Dolt commit/ref -> SnapshotTableSet reader。
- Reader streaming -> SnapshotTableArtifact。
- cache disabled / read-only / write-through diagnostics。

## 第一版取舍与后续演进

第一版固定选择：

- `RepositoryRefSession` 是 read-only、pinned-to-commit、operation scoped。
- `open_ref()` 支持 `open_ref_timeout_ms`，语义幂等但不保证返回同一 session 对象。
- `get_catalog()` eager load 并在 session 内 memoize。
- `open_table_reader()` 不要求并发、thread-safe 或 rewind。
- row stream 使用 tuple + catalog column order。
- repository reader 负责补齐 Dolt/driver 省略的 NULL 字段。
- scalar encoder 放在 `snapshot_materialization.scalar_encoding`。
- reader streaming 是默认路径。
- `export_table_artifact()` optional。
- repository_server_table_cache 可先实现小型技术事实的跨 session cache，但不实现 TTL/cleanup/export 大对象 cache 策略。

后续可能变化：

- scalar encoder 下沉到 `core.scalar_encoding`。
- 支持并发 table readers 或 reader pool。
- 支持 lazy partial catalog。
- 引入 repository server 独立容器/API。
- 启用 repository server export artifact cache。
- 设计 repository_server_table_cache TTL、pin、eviction、quota、cleanup。
- benchmark reader streaming vs export artifact vs warm server session。
- 在不改变 Snapshot contract 的前提下引入更强的 repository table root/hash fast path。
