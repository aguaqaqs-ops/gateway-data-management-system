# Phase 3 Capability Foundation Design

状态：正式设计基线（Accepted）

日期：2026-08-22

阶段：Phase 3 design complete；P3-R1 至 P3-R7 module gates pass；P3 final closure in progress；production integration未授权

Owner：Backend vNext Capability Architecture

## 1. Purpose

Phase 3 建立 backend vNext 的 capability foundation，并为后续 Preview vertical slice
提供稳定、可验证、可跨语言实现的数据面合同。本文拥有 Phase 3 的范围、依赖、交付物和
退出标准；字段级语义由各 owning contract 拥有。

Phase 3 不接 HTTP、Workspace、Submit application flow、durable Operation Runtime 或
生产 PostgreSQL。它可以提供 reference planner、Dolt renderer 和 fault-injectable
external executor，供后续阶段验证和接入。

## 2. First consumer and main chain

首个真实 consumer 是 `BuildUploadPreview`。`FULL` 与 `MODIFIED_ONLY` 共用 capability
主链，`INITIALIZE_BASELINE` 延后到 Workspace/Application flow。

```text
table_access/parser
  -> source materialization
  -> SnapshotTableArtifact
  -> storage/comparison projection
  -> comparison
  -> risk
  -> surface
  -> bundle
```

同一 source 只解析和物化一次；多个 pair 共享 immutable `SnapshotTableArtifact`。Preview
同步阶段只计算前端所需 comparison/risk/surface/bundle；cache、replay、mutation planning
和 external ChangeSet 留在后续异步阶段。

## 3. Capability ownership

| Capability | Phase 3 responsibility | Later consumer |
| --- | --- | --- |
| Source/package admission | format, type, size, diagnostics contract | P5A HTTP/Workspace |
| Source materialization | canonical table and derived-table semantics | P5A Preview/Submit |
| Snapshot artifact | immutable rows, summary, retention profile | P4/P5 runtime |
| Storage projection | canonical key/schema/content digest | P5 Submit/Repository |
| Comparison | standard records and surface facts | P5 Preview |
| Risk | declarative ruleset input and actual evaluation | P5 Preview/Review |
| Bundle | closure and references | P5 PreviewResult |
| Mutation planning | rebuild/patch/no-op plan and ChangeSetArtifact | P5 Submit/external sync |

Composite/derived tables are special only during source materialization. After materialization,
`composite_signal_point` and all other canonical tables use the same storage, comparison,
risk, mutation and transaction contracts as ordinary tables.

## 4. Accepted design decisions

- First HTTP package is `TAR_GZ`; internal fixture/staging may use zstd without adding a formal
  `TAR_ZST` package kind.
- Source compressed ingress is `256 MiB`; expanded SourcePackage is initially `1 GiB` and is
  benchmarked before further tightening.
- Repository import upload is `256 MiB`; `manifest.json` is `16 MiB`; `replay.sql` is
  `200 MiB`; exceeding the replay limit is direct rejection, never split or fallback.
- Unknown SQL types and invalid/missing key semantics fail closed at Submit/storage effect;
  Preview may expose bounded table-level degradation.
- Preview may retain summary/lightweight artifacts, but Submit only reuses a complete bound
  artifact; otherwise it materializes from durable source or asks for a new upload.
- Python owns control plane and reference semantics; Rust owns proven data-plane hotspots.
  Provider language and implementation identity do not enter semantic digests.
- `REBUILD_ALWAYS` is the initial production default. `ADAPTIVE_PATCH` may be globally enabled
  after validation; global enable activates planning and does not force every table to patch.
- History compare uses the program's current default ruleset; historical ruleset snapshots are
  provenance only and do not create a mismatch branch.
- The repository/Dolt commit is authoritative. External targets are asynchronous consumers;
  no two-phase commit is introduced.

## 4.2 P3-R3 Source Materialization and Snapshot Design Baseline

状态：Accepted；R3 gate pass；S8 handoff recorded

S0 冻结记录见 [P3-R3-S0](p3-r3-s0-entry-and-budget-freeze.md)。
S8 handoff 见 [P3-R3 Source Materialization and Snapshot Handoff](p3-r3-source-materialization-handoff.md)。

R3 建立从 SourcePackage、SQL dump、business XML 和 pinned RepositoryRef 到 Snapshot、
SnapshotSummary、SnapshotTableSet 与 immutable `SnapshotTableArtifact` 的 capability
边界。R3 不接 HTTP、Workspace、Submit、Operation Runtime 或 storage/comparison
projection。

### Input and admission boundary

- 生产 HTTP 业务 SourcePackage 首版正式接收格式只有 `TAR_GZ`；`ZIP`、`DIRECTORY`、
  `SQL_FILE`、`SQL_GZ` 是 capability/local fixture/benchmark 输入，其中 `SQL_FILE` /
  `SQL_GZ` 不代表正式多文件业务包。
- zstd 可用于内部 fixture/staging transport，也继续用于独立的 Repository import
  `tar+zstd` contract；R3 不新增正式 `TAR_ZST` package kind，不把 zstd 伪装成
  `TAR_GZ`。只有出现真实 consumer、部署要求或测量证据时才 reopen SourcePackage
  contract/ADR，增加正式输入格式。
- SourcePackage staging 负责 bounded streaming extraction、normalized path、entry
  manifest/digest、required `/sql/dbcfg.sql` 和 optional `/comps/logic/logics.xml`
  resolution；不解析 SQL/XML，不创建 Snapshot。
- 现有 `256 MiB` compressed ingress、`1 GiB` expanded package、`512 MiB` decoded SQL
  与 R2 parser/XML budgets 共同构成 R3 输入上限。解压、解包和 artifact 写入必须
  在 streaming/staging 中执行上限检查，不先完整展开再校验。

### Materialization result and failure atomicity

- 正式入口要求显式、不可变的 `TableRulesetSnapshot` 与 matching
  `table_ruleset_version`；版本不一致或规则真源无法校验时 fail closed。
- package/source resolution、business XML structural/semantic violation、global digest
  mismatch、materializer contract violation 和无法建立完整 Snapshot identity 是
  materialization-level `FAILED`；不得发布 Snapshot、SnapshotTableSet 或 artifact。
- 单表 schema/type/key/reader 问题可形成 `PARTIAL`；成功表可以继续提供 descriptor/
  reader/artifact，问题表仅保留 bounded diagnostics/degraded fact，不发布 partial
  reader/artifact。所有表均失败时升级为 `FAILED`。
- reader/artifact 使用 staging write -> manifest/descriptor/digest validation -> atomic
  publish。cancel、timeout、I/O 或进程错误只能留下可清理 transient，不能发布半成品。
- R3 只提供 in-process cancellation/deadline；durable checkpoint、takeover、retry
  ownership 属于 P4 Operation Runtime。

### Canonical facts and digest

- R3 负责 materialization facts、`fast_row_digest`、`raw_content_digest`、
  `business_content_digest`（可为 `NOT_COMPUTED`）和 `snapshot_digest`；R4 负责
  storage projection、canonical storage key/schema、`CanonicalizationManifest` 与
  RepositoryImportArtifact semantics，R3 不复制这些规则。
- Reader 保留 source INSERT order；raw/business digest 以 canonical scalar row 的
  deterministic order-insensitive multiset 计算，保留重复行计数。字段使用 descriptor
  canonical order；row order 或 package compression metadata 不改变 digest。
- 不为 keyless 表补 surrogate key。duplicate effective key 不做 dedup、覆盖或
  last-write-wins；按 table rules/comparison contract 形成表级 degraded/failure fact。
- `PROVISIONAL` 只表示 upload/local fast facts；`CONTENT_VERIFIED` 表示 source
  binding、descriptor、rows、manifest 和 digest 在 capability 内闭合；
  `COMMIT_VALIDATED` 只能由 Repository commit/readback 或等价权威校验产生。

### Business XML and RepositoryRef

- `logics.xml` 由独立 `composite_signal` provider 消费；缺失等价稳定 EMPTY source，
  XML digest/EMPTY marker、parser/materializer versions 和 ruleset version进入业务
  Snapshot identity。原始 SQL 表不被改写。
- composite 业务不变量失败（重复顶层公式、孤儿公式、特殊装置身份不满足等）使整个
  business materialization `FAILED`；不发布 `composite_signal_point` 派生表。
- RepositoryRef provider 只接受 pinned immutable commit/ref；Repository hidden FINAL
  SnapshotSummary 缺失、版本不匹配或 digest 不一致直接失败，不从 catalog/rows 重建
  summary。R3 module gate 使用 protocol-conformant fake provider；真实 Repository
  Service/Dolt readback 属于独立 integration gate。

### Artifact and cache boundary

- `SnapshotTableArtifact` 第一版固定为 `manifest + Parquet rows`；public consumer 只依赖
  `SnapshotTableReader` 与 opaque `ArtifactRef`，不依赖 Parquet API。
- Cache 只加速，不替代 source/ref 校验。`PROVISIONAL` candidate 需要重新验证并有
  fallback recompute；`COMMIT_VALIDATED` 仅可被 repository/readback authority promotion。
- R3 不实现 retention/eviction/quota、durable lifecycle、projection cache 或 export
  format matrix；删除 L3 cache 后必须能从 L1 source 或 L2 repository ref 重建。

## 4.1 P3-R2 Table Access and Parser Design Baseline

状态：Accepted；R2 gate pass；S7 handoff recorded

R2 的目标是建立可独立调用、bounded、可诊断的 source table-access foundation。R2
只产出 parser facts、descriptor、deferred reader 和 diagnostics；不产出 Snapshot、
canonical storage projection 或业务派生表。

### Ownership and boundary

- `table_access` 拥有 source SQL parser、generic XML document parser、typed descriptor、
  row-reader 和 parser diagnostics contract。
- Repository Service 继续拥有 repository manifest/catalog validation；Backend 不 import
  `gateway_repository_service`，R2 不实现 Repository/Dolt-backed reader。
- ADR 0013 已在 R2-S0 修订为 source parser 与 repository import validation 的
  明确双边界；不得共享 parser implementation 或创建 `sql_utils`、
  `capabilities/common`、`capabilities/utils`。权威记录见
  [P3-R2-S0](p3-r2-s0-entry-and-budget-freeze.md)。
- R2 不实现 SourcePackage staging、business-source wrapper、Snapshot materialization、
  `composite_signal` business materializer、storage/comparison projection、HTTP、Workspace、
  Submit、Operation Runtime 或 artifact retention。

### SQL source parser

- 输入是 `SqlDumpSource` 或显式标记的 SQL-only test/benchmark source；parser 不读取
  SourcePackage 容器，不执行 SQL，也不连接 Repository。
- 首版只接受显式 allowlist 中的 `CREATE TABLE`、`INSERT INTO` 和 bounded、无语义的
  dump boilerplate。完整 allowlist、known type closure 与 numeric budgets 已在
  [P3-R2-S0](p3-r2-s0-entry-and-budget-freeze.md) 冻结；未列 statement、`REPLACE`、
  upsert、需推导的 DDL mutation、trigger/procedure/event、隐式执行语义均 fail
  closed。既有 256 MiB compressed ingress、1 GiB expanded SourcePackage 是外层边界，
  不是 R2-specific budget 的替代品。
- 同一 table 重复定义、duplicate column、duplicate primary key、canonical identifier
  collision 和 row shape 不一致均为明确错误；不做 dedup、覆盖或 last-write-wins。
- 首版 INSERT 必须显式提供完整列值；省略列、依赖 `DEFAULT`、generated column 或
  expression default 不由 parser 推导。
- `SnapshotTableDescriptor` 保留 canonical identifier、display name、DDL column order、
  nullability、primary-key order 和 bounded normalized SQL type。row 是与 descriptor 对齐的
  immutable positional tuple；SQL `NULL` 保持独立状态。
- known SQL types 沿用 Repository contract 的 v1 closed mapping；ENUM/SET 族内 malformed
  一律 `SQL_TYPE_MALFORMED`，非法值一律 `SQL_VALUE_ILLEGAL`，不得落入 unknown/stringify。
  unknown type 可以保留 bounded descriptor/diagnostic，但不发布 READY reader。
- parser 不计算 canonical business digest。`document_content_digest`、`sql_source_digest`、
  `parser_input_contract_version` 和 semantic `parser_version` 分层；provider implementation
  identity 不进入 semantic digest。

### XML document parser

- R2 只提供 domain-neutral XML document boundary；`logics.xml` schema interpretation 和
  `composite_signal_point` materialization 延后到 R3。
- 输入只接受严格 UTF-8；禁止 DTD、external entity、XInclude、网络/外部资源读取。
  XML depth、node、attribute、text 和 document size 必须 bounded；malformed/超限 fail closed。
- 输出是 bounded event/node stream，不建立无上限通用 DOM；保留 namespace-expanded name，
  不做业务 namespace alias 或字段解释。

### Reader, result and diagnostics

- reader 是 single-consumer、non-rewind、可重新打开的 deferred reader；`close()` 幂等，
  close 后访问返回稳定 `READER_CLOSED`。并发 `iter_rows()`/`count_column_values()` 不受支持。
- reader 接受显式 deadline/cancellation signal；timeout、cancel、resource limit 和 stream
  parse failure 都是稳定 diagnostics。上层决定具体 timeout policy。
- stream successful end-of-stream 是提交点。中途已经产生的 rows 是 transient；任何 error、
  timeout 或 cancel 都禁止发布 READY reader/artifact，调用方必须丢弃部分结果。
- `ParseResult` 使用 `COMPLETE | PARTIAL | FAILED`。PARTIAL 只为成功表提供 reader，失败表
  只保留 bounded diagnostics；FAILED 不发布可消费 reader。
- `table_access` 拥有 parser-specific code registry；diagnostic 至少含 code、severity、
  source、table/column 和 byte offset，按 source offset/code 稳定排序，并有数量/字节上限。

### R2 Provider, Assurance and Deferred Register

- R2 首版使用 bounded Python provider；不引入 Rust parser、automatic fallback、新 service 或
  新 security principal。S0 可行性结论：stdlib custom SQL scanner 与
  `xml.parsers.expat` incremental handler；不加入第三方 parser library。
- golden、malformed、XML security、partial-stream、cancel/timeout fixture 由 table_access
  owner 维护；同构错误使用模块级参数表，不恢复 legacy compatibility matrix。纯 R2 tests
  不创建 Dolt。

R2 延后项必须在后续设计中显式引用本表，不得从 parser skeleton 推断为已实现。
S0 关闭项的权威记录见 [P3-R2-S0](p3-r2-s0-entry-and-budget-freeze.md)。

| ID | Deferred item | Owner / earliest phase | Required guard before use |
| --- | --- | --- | --- |
| R2-D01 | exact parser/XML/batch/diagnostic numeric budgets | **Closed in R2-S0** | [S0 budget table](p3-r2-s0-entry-and-budget-freeze.md)；S2/S3 boundary tests |
| R2-D02 | complete SQL boilerplate allowlist and type grammar closure | **Closed in R2-S0 / ADR 0013** | [S0 allowlist](p3-r2-s0-entry-and-budget-freeze.md)；ADR 0013 dual-boundary |
| R2-D03 | concrete Python parser library/provider feasibility | **Closed in R2-S0** | stdlib custom SQL scanner + `xml.parsers.expat`；无第三方 parser |
| R2-D04 | `logics.xml` business schema and derived-table materializer | R3 | owning materialization contract |
| R2-D05 | Repository/Dolt-backed reader and hidden summary readback | R3 / P2 integration boundary | repository provider contract and integration tests |
| R2-D06 | canonical raw/business digest and storage projection | R3/R4 | storage owner contract; R2 must not duplicate it |
| R2-D07 | artifact retention, pinning and durable lifecycle | P4/P5 | lifecycle/retention owner decision |
| R2-D08 | Rust parser/provider or parser optimization | P6 or later | accepted profile and Python differential oracle |
| R2-D09 | durable cancellation/checkpoint/takeover | P4 | Operation Runtime contract |

## 4.3 P3-R4 Storage Projection Design Baseline

状态：Accepted；R4 detail plan accepted；S0 freeze complete；S8 module gate complete，R4 gate pass；R5 module gate complete；R6 detail plan accepted；S0 complete；implementation authorization pending

设计与执行基线见 [P3-R4 Storage Projection Design Baseline](p3-r4-storage-projection-design.md)
和 [P3-R4 Storage Projection Execution Plan](p3-r4-storage-projection-execution-plan.md)。
S0 冻结见 [P3-R4-S0 Entry, Applicability, Legacy Matrix and Budget Freeze](p3-r4-s0-entry-and-budget-freeze.md)。
R4 gate / R5 entry 见 [P3-R4 Storage Projection and Canonicalization Handoff](p3-r4-storage-projection-handoff.md)。

R4 迁移 legacy `TableRuleRegistry` 的有效 rule-resolution semantics，建立
`LegacyRuleDecision` 与 `StorageRuleView` 两层边界，并产出 canonical storage projection、
`CanonicalizationManifest` 和 `RepositoryImportArtifactInput`。legacy selector precedence、
special cases、ignored columns 和 artifact scopes 必须 parity；每个 legacy
`ignored_columns` 必须在 StorageRuleView 中形成 `DROP_FROM_STORAGE`，而 `UPDATE_ONLY` 等其余
comparison/artifact 语义不得自动变成 storage drop。R4 不实现 Repository effect、comparison、
mutation/replay、HTTP、Operation Runtime 或 ruleset migration executor。

## 5. Phase 3 deliverables

1. Capability contracts and stable failure taxonomy.
2. Python reference providers and deterministic fixtures.
3. Snapshot/materialization, storage projection, comparison, risk, surface and bundle conformance.
4. `StorageMutationPlan` and `ChangeSetArtifact` contracts plus Python reference planner.
5. Deterministic Dolt renderer and golden replay fixtures.
6. Target-neutral external executor contract and fault-injectable reference executor.
7. Golden, differential, malformed-input, capacity, cancellation and fault-injection tests.
8. Benchmark harness for pair concurrency, memory bounds and provider comparison.

Deliverable #8 是 Phase 3 的长期 harness 目标，不等于 P3 exit 必须一次性完成三层
measurement。P3-FINAL 当前只要求 component/multi-pair diagnostic evidence；cross-capability
artifact chain 与 production/reference provider comparison 分别延后到 P5/P6/P7，见
[P3 Capability Foundation Execution Plan](p3-capability-foundation-execution-plan.md#6-benchmark-policy)
与 [P3 Final Closure Execution Plan](p3-final-closure-execution-plan.md)。

## 6. Explicit phase boundaries

| Item | Owning phase | P3 treatment |
| --- | --- | --- |
| Durable Operation Runtime, drain, checkpoint, takeover | P4 | capability cancellation/checkpoint contract only |
| Workspace, HTTP, PreviewResult, artifact retention wiring | P5A | no application integration |
| Submit/finalize, Dolt effect and external ChangeSet wiring | P5B | renderer/reference executor only |
| Rust coverage expansion and risk kernels | P6 | profile and provider boundary only |
| global concurrency/cache tuning | P7 | benchmark inputs and resource contract only |
| cross-capability benchmark chains | P5/P6/P7 | deferred until production consumer exists |
| production/reference provider comparison | P6/P7 | deferred until provider candidate exists |
| shadow traffic/cutover | P8 | deferred |
| cleanup/production hardening | P9 | deferred |
| production PostgreSQL adapter/e2e | future target-specific work | contract and reference executor only |
| online ruleset watcher/hot activation | future optional work | immutable snapshot/activation boundary only |
| `STORAGE_BREAKING` ruleset migration executor | future migration work | impact classification and gating only |

## 7. Phase 3 exit criteria

Phase 3 may be declared complete only when:

- contracts have one owner and no unresolved architecture blocker;
- outputs are deterministic across provider language, thread count and input ordering;
- Python reference and production candidate pass golden/differential fixtures;
- incomplete artifacts cannot be published or used as cache hits;
- cancellation, timeout, panic/OOM mapping and retry semantics are bounded and stable;
- `ADAPTIVE_PATCH` mixed plans, key changes, guards and renderer capability failures are tested;
- reference external executor covers transaction, idempotency, drift, readback and unknown outcome;
- concurrency benchmark records wall time, CPU, RSS, queue wait and cancellation latency;
- HTTP/application integration remains outside the P3 implementation diff.

## 8. Non-goals and reopen conditions

No formal compatibility matrix, live ruleset watcher, automatic Python runtime fallback,
compute network service, production PostgreSQL adapter, 2PC, arbitrary SQL stringify fallback,
or full migration executor is introduced in Phase 3. A future design must reopen the owning
contract/ADR before changing these boundaries.

## 9. Normative owners

- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
- [Storage Mutation and Change Set](../contracts/storage-mutation-and-change-set.md)
- [External Target Sync and Recovery](../contracts/external-target-sync-and-recovery.md)
- [Operation Lifecycle and Integrity Incident](../contracts/operation-lifecycle-and-integrity.md)
- [Ruleset Activation and Migration](../contracts/ruleset-activation-and-migration.md)
- [Implementation Stages](implementation-stages.md)
