# P3-R3-S0 Entry, Applicability and Budget Freeze

状态：S0 complete；S1–S8 complete；R3 gate pass；handoff: [p3-r3-source-materialization-handoff.md](p3-r3-source-materialization-handoff.md)

日期：2026-08-19

Owner：Backend vNext Source Materialization

本文是 P3-R3 的 **S0 权威记录**。它冻结 SourcePackage 格式与 zstd 范围、R3 owner
DAG、resource/security budgets、结果状态、cache trust、digest/failure 原子性、
fixture 根目录、allowlist 与 reopen 条件。字段级 public contract 由 S1 落成；
SQL/XML 业务 materializer、RepositoryRef provider 与 artifact publish 由 S2–S5
实现。不得从 R1 skeleton 或 capability 文档中的 flow-facing 名称猜测 R3 语义。

上级计划：[P3-R3 Source Materialization and Snapshot Execution Plan](p3-r3-source-materialization-execution-plan.md)
设计基线：[P3 Capability Foundation Design §4.2](p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline)
R2 入口：[P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)
R2 冻结：[P3-R2-S0 Entry, Applicability and Budget Freeze](p3-r2-s0-entry-and-budget-freeze.md)

```yaml
handoff_kind: p3_r3_s0_entry_and_budget_freeze
round: P3-R3-S0
p3_r2_exit: pass
p3_r3_ready: yes
p3_r3_s0_exit: pass
p3_r3_s1_authorized: yes
p3_r3_s2: completed
p3_r3_s3: completed
p3_r3_s4: completed
p3_r3_s5: completed
p3_r3_s6: completed
p3_r3_s7: completed
p3_r3_s8: completed
p3_r3_exit: pass
p3_r4_ready: yes
p3_implementation_authorized: no
r2_validated_code_sha: 2a799cf30508ab6a380718eeacd6f721fc247b20
r2_handoff_documentation_sha: 3c142f8e7616fb4cc2594a61128b2ccce494dd46
s0_worktree: dirty_docs_only
container_rebuild: no
benchmark: not_applicable
zstd_scope: internal_fixture_and_staging_only
formal_source_package: TAR_GZ
```

`r2_validated_code_sha` 是 R2-S6 已审且 S7 复跑通过的代码 tip。
`r2_handoff_documentation_sha` 是 R2-S7 handoff 文档 commit。S0 开始时工作树仅有
未提交的 R3 detail plan 与上级状态同步文档，无 `vnext/` 代码变更。本文件和
plan/index 状态更新是本次 S0 文档交付。

## 1. Review boundary and evidence

本审查按照 [P3-R3 execution plan](p3-r3-source-materialization-execution-plan.md)
S0 只读范围执行。语义 authority 依次采用 P3 contracts/ADR、P3 design §4.2、R2
handoff 与 R2-S0 freeze，再采用现有 architecture/import tests 作为边界 evidence。
legacy 与过程文档不作为当前 contract。capability 文档中的 upload/preview/submit
helper 名称不授权 HTTP 或 application flow。

已读取并用于本结论的 authority：

- [P3-R2 Table Access and Parser Handoff](p3-r2-table-access-parser-handoff.md)；
- [P3-R2-S0](p3-r2-s0-entry-and-budget-freeze.md)；
- [P3 Capability Foundation Design §4.2](p3-capability-foundation-design.md#42-p3-r3-source-materialization-and-snapshot-design-baseline)；
- [SourcePackage](../../../contracts/source-package.md)、[Snapshot](../../../contracts/snapshot.md)、
  [Snapshot Table Access](../../../contracts/snapshot-table-access.md)；
- [Snapshot Materialization](../../../capabilities/snapshot-materialization.md)、
  [Repository Ref Materialization](../../../capabilities/repository-ref-materialization.md)、
  [Composite Signal Device](../../../capabilities/composite-signal-device.md)；
- [Artifact and Persistence](../../../artifacts.md)；
- [Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)；
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)；
- [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)；
- [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)、
  [ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)；
- [Testing Conventions](../../../testing-conventions.md)、[Testing Fixtures](../../../testing-fixtures.md)；
- `vnext/backend/src/gateway_backend/capabilities/{table_access,snapshot_materialization,table_rules}/`、
  `vnext/backend/src/gateway_backend/artifacts/`、
  `vnext/backend/tests/test_architecture.py`、
  `vnext/backend/tests/support/artifact_staging.py`。

本次没有修改业务代码、parser 实现、fixture 文件、artifact schema 或正式
contract/ADR。S0 不 reopen ADR 0012、ADR 0013 或 SourcePackage owner contract。

## 2. R2 handoff applicability

| P3-R3 entry requirement | Evidence | Result |
| --- | --- | --- |
| R2 module gate pass | handoff `p3_r2_exit: pass`；`p3_r3_ready: yes` | **PASS** |
| stable public parser surface | `parse_sql` / `parse_xml`、`ParseStatus`、descriptors/readers、`RESOURCE_BUDGETS`；禁止 import `_sql_*` / `_xml_parser` / `_parser_runtime` | **PASS** |
| accepted SQL/XML budgets | R2-S0 §8；S7 未修订；`table_access.RESOURCE_BUDGETS` 与 freeze 一致 | **PASS** |
| typed row / SQL NULL / unknown-type | READY reader 禁 unknown；R2 handoff §7–§8 | **PASS** |
| `COMPLETE \| PARTIAL \| FAILED` 与 stream commit point | R2 `ParseResult` / XML events；successful end-of-stream | **PASS** |
| no Repository/Dolt in `table_access` | architecture forbidden tokens；R2 handoff §4 | **PASS** |
| `R2-D04`–`R2-D09` explicitly linked | R2 handoff §5 | **PASS** |
| parser output without provider-private state | `TableReader` protocol；不构造 private `TupleSpan` | **PASS** |
| no-open-blocker | R2 handoff §5；无未处理 P1/P2 | **PASS** |
| R2 未授权 materialization | `p3_implementation_authorized: no` 保持 | **PASS** |
| R3 skeleton 未预声明字段 | `snapshot_materialization/contracts.py`、`table_rules/contracts.py` 仅 owner 注释；本 S0 从 §4.2 与 contracts 读取 | **PASS** |

R2 可作为 R3 输入。S0 不把 R1/R3 skeleton 或 capability 文档中的 Preview/Submit
helper 当作已实现合同。无 blocking finding 要求暂停 R3 entry。

## 3. Owner graph

目标 DAG（S1 落成 architecture checks；当前测试仍只登记 `snapshot_materialization -> {table_access, table_rules}`）：

```text
Shared Canonical Encoding (Shared Kernel)
  ^
  | public identifier ASCII fold / scalar / null / DigestRef
  |
artifacts envelope (not a capability owner)
  |-- four-field ArtifactRef; no host path; raw transport integrity only
  `-- ArtifactStorePort; LocalArtifactStore stays in infrastructure

table_access (R2 leaf)
  |-- SQL dump grammar, typed positional rows, generic XML events
  `-- no capability upstream; R3 consumes public surface only

table_rules (leaf)
  |-- immutable TableRulesetSnapshot + table_ruleset_version injection surface
  `-- full comparison/storage rule matrix remains R4

source_package_staging (R3 leaf)
  |-- bounded package extraction, normalized path, entry/document digest
  |-- required /sql/dbcfg.sql and optional /comps/logic/logics.xml refs
  `-- may import artifacts envelope + Shared Kernel; not table_access or snapshot_materialization

composite_signal (R3)
  |-- logics.xml business AST and composite_signal_point derived rows
  `-- may import table_access.contracts only; not snapshot_materialization

snapshot_materialization (R3 consumer/composer)
  |-- SQL Snapshot / summary / table-set / digest
  |-- business composition of SQL tables + composite derived table
  |-- RepositoryRef provider protocol + fake provider
  `-- SnapshotTableArtifact publish and cache/trust metadata
```

Allowed capability edges after S1：

```text
source_package_staging: frozenset()
composite_signal: frozenset({"table_access"})
snapshot_materialization: frozenset({
    "table_access",
    "table_rules",
    "source_package_staging",
    "composite_signal",
})
table_rules: frozenset()
table_access: frozenset()
```

跨 capability 只允许 `*.contracts`。capability 可 import `gateway_backend.artifacts`
与 `gateway_shared_kernel` public primitives。测试通过
`tests/support/artifact_staging.py` 注入 `LocalArtifactStore`；production capability
代码不得 import `gateway_backend.infrastructure`。

Forbidden directions:

```text
table_access / table_rules / source_package_staging / composite_signal
  -X-> snapshot_materialization
source_package_staging -X-> table_access / table_rules / composite_signal
composite_signal -X-> source_package_staging / table_rules
any R3 owner -X-> gateway_repository_service / candidate_a.sql / dolt
any R3 owner -X-> HTTP / Workspace / Submit / Operation Runtime
any R3 owner -X-> storage_projection / canonicalization_* / repository_import_artifact
any R3 owner -X-> capabilities/common / capabilities/utils
any R3 owner -X-> infrastructure.LocalArtifactStore
artifacts -X-> capability-private metadata / Snapshot schema
```

S1 扩展 DAG 与 public contracts，不得改变上述方向。不得创建 `capabilities/common`
或 `capabilities/utils`。

## 4. Decision register

| ID | Decision | Rationale |
| --- | --- | --- |
| `R3-S0-D01` | R2 public surface 是 R3 唯一 parser 输入；不 import parser-private 模块 | R2 handoff §7；关闭“入口未就绪”歧义；`R2-D04` 实现仍属 S3 |
| `R3-S0-D02` | 新增 `source_package_staging`（leaf）与 `composite_signal`（只依赖 `table_access.contracts`）；`snapshot_materialization` 上游扩展为四者 | 执行计划 §3.1–§3.2；architecture 必须在 S1 登记 |
| `R3-S0-D03` | 正式 SourcePackage 仅 `TAR_GZ`；`ZIP`/`DIRECTORY` 为 capability/local fixture；`SQL_FILE`/`SQL_GZ` 为 test/benchmark；zstd 只作内部 staging/fixture transport 与既有 Repository `tar+zstd`；不新增 `TAR_ZST`，不把 zstd 伪装成 `TAR_GZ` | design §4.2；SourcePackage contract；`R3-D01` |
| `R3-S0-D04` | 外层 256 MiB / 1 GiB 与 R2-S0 parser budgets 继承且不修订；§8 另冻 package-security 上限；无吞吐 SLO | 执行计划 §2.2；extraction fail-closed 不是性能目标 |
| `R3-S0-D05` | 结果状态 `COMPLETE \| PARTIAL \| FAILED`；包/源/业务 XML/全局 identity 失败为结果级 `FAILED`；独立表失败可为 `PARTIAL`；失败表无 reader/artifact；全部表失败升级 `FAILED` | 与 R2 `ParseStatus` 对齐；design §4.2 |
| `R3-S0-D06` | `Snapshot.materialization_stage` 保持 `PROVISIONAL \| FINAL`；cache/result trust 为 `PROVISIONAL \| CONTENT_VERIFIED \| COMMIT_VALIDATED`。stage=PROVISIONAL ↔ trust=PROVISIONAL；capability 闭合 FINAL ↔ `CONTENT_VERIFIED`；`COMMIT_VALIDATED` 仅由显式 repository authority 输入 promote。preview/finalize 名称是策略别名，不是 HTTP/Submit API。hidden summary 写入不在 R3 | snapshot.md 与 design §4.2 正交标签；`R3-D02` |
| `R3-S0-D07` | reader 保 INSERT 序；raw/business digest 为 order-insensitive multiset 且保留重复；压缩元数据/zip 顺序/mtime 不进入 SQL Snapshot identity；无 surrogate key、dedup、overwrite、LWW。R3 拥有 materialization digest；storage projection 属 R4 | design §4.2；`R2-D06` 拆分 / `R3-D04` |
| `R3-S0-D08` | 生产入口必须显式注入不可变 `TableRulesetSnapshot` + matching `table_ruleset_version`；禁止 hidden mutable global。S1 可在 `table_rules/contracts.py` 增加最小注入面。effective key：`table_ruleset compare_key > DDL PK > keyless fact` | design §4.2；R4 仍拥有完整 comparison/storage 规则矩阵 |
| `R3-S0-D09` | `SnapshotTableArtifact` v1 = `manifest + Parquet rows`；使用已钉 `pyarrow==25.0.0`。consumer 只用 reader + opaque `ArtifactRef`。发布：staging write → validation → atomic publish。cache miss 必须能从 source/ref 重建。retention/eviction 延后 | snapshot-table-access；artifacts 四字段 envelope；`R3-D03` |
| `R3-S0-D10` | in-process cancel/deadline 沿用 R2 `ParserInvocationContext`；stdlib `tarfile`/`gzip`/`compression.zstd` + 现有 pyarrow；不加第三方 archive/XML/SQL 库。durable checkpoint/takeover 仍是 `R2-D09` / `R3-D07` | 与 R2-S0-D06/D08 一致；不新增依赖 |

无 S0 blocking finding。不新增 shared primitive。不 reopen ADR。

## 5. Package formats and zstd scope

| Layer | Accepted input | R3 status |
| --- | --- | --- |
| Production HTTP business package | `TAR_GZ` only | formal V1；R3 不实现 HTTP admission |
| Capability/local fixture | `ZIP`, `TAR_GZ`, `DIRECTORY` | supported resolver inputs |
| SQL-only helper | `SQL_FILE`, `SQL_GZ` | test/benchmark only；解压后映射 `/sql/dbcfg.sql` |
| Internal staging transport | explicit zstd compression | allowed；**no** `TAR_ZST` package kind |
| Repository import transport | fixed `tar+zstd` | separate Repository contract；R3 不复制 writer |

所有 kind 使用同一套 normalized-path、traversal/root/symlink 拒绝、streaming size
与 entry digest 语义。Compression metadata 不是 SQL Snapshot identity 的一部分。
未来正式 `TAR_ZST` 必须 reopen SourcePackage owner contract/ADR（`R3-D01`）。

Required / optional documents：

```text
required_sql_document:
  normalized_path: /sql/dbcfg.sql
  document_kind: SQL_DUMP

optional_composite_logic_document:
  normalized_path: /comps/logic/logics.xml
  document_kind: XML
```

缺少或重复 `/sql/dbcfg.sql`、canonical path 冲突是 package-level `FAILED`。
`/comps/logic/logics.xml` 缺失 = 稳定 EMPTY source，不产生 package diagnostic。
`TAR_GZ` 流式 staging 只物化这两份文档；其余成员 metadata-only。

## 6. Result, trust and lifecycle

### 6.1 Materialization status

```text
SnapshotMaterializationStatus: COMPLETE | PARTIAL | FAILED
```

- 包/源解析失败、业务 XML 结构/语义失败、全局 identity/digest mismatch、无法建立
  完整 Snapshot identity → 结果级 `FAILED`；不发布 Snapshot、SnapshotTableSet 或
  artifact。
- 独立表 schema/type/key/reader 问题可为 `PARTIAL`；成功表可提供 descriptor /
  reader / artifact；失败表仅保留 bounded diagnostics/degraded fact，不发布
  partial reader 或 artifact。
- 所有表均失败时升级为 `FAILED`。
- composite 业务不变量失败使整个 business materialization `FAILED`；不发布
  `composite_signal_point`；源 SQL 表不被改写。
- successful stream completion 是 reader 发布提交点。

### 6.2 Stage vs trust

两套正交标签，S1 必须同时出现在 public contract 中，不得合并成一个 enum。

| Snapshot.materialization_stage | Cache/result trust | Meaning in R3 |
| --- | --- | --- |
| `PROVISIONAL` | `PROVISIONAL` | upload/local fast facts；`fast_row_digest` 可用；`raw_content_digest` 可暂缺 |
| `FINAL` | `CONTENT_VERIFIED` | source binding、descriptor、rows、manifest 与 digest 在 capability 内闭合 |
| n/a (promotion input) | `COMMIT_VALIDATED` | 仅 repository commit/readback 或等价权威输入；R3 不得自提升 |

capability 文档中的 `materialize_sql_snapshot_preview` /
`finalize_snapshot_materialization` 映射为上述策略，不是 HTTP Preview 或 Submit
API，也不写入 hidden FINAL summary。hidden summary **写入** 属于 P5B / `R3-D02`。
S4 只定义 pinned 只读 provider、fail-closed hidden-summary readback 与
protocol-conformant fake provider。缺失、损坏或 version/digest mismatch 的 hidden
summary 直接失败，不得从 catalog/rows 重建。

### 6.3 Cancel, timeout and publish

```text
ParserInvocationContext:
  cancel_requested: is_set() protocol
  deadline_monotonic: float | None
```

R3 staging/materializer/artifact 路径在 statement、INSERT tuple、XML node、package
entry、artifact write 边界检查同一形状。稳定码沿用或并列 `PARSER_CANCELLED` /
`PARSER_TIMEOUT` 与 materialization 级等价码。上层映射 HTTP/operation deadline；
R3 无默认 timeout。durable checkpoint/takeover 仍是 `R2-D09` / `R3-D07`。

Artifact publication：staging write → manifest/descriptor/digest validation →
atomic publish。cancel、deadline、I/O 或 provider 失败不得发布不完整 rows 或
manifest；只能留下可清理 transient。

## 7. Digest and table-rules injection

- Reader 顺序保持 source INSERT order。
- `raw_content_digest` / `business_content_digest` 使用 canonical scalar rows 的
  deterministic order-insensitive multiset，保留 duplicate counts。
- 字段使用 descriptor canonical order；row order 或 package compression metadata
  不改变 digest。
- 不为 keyless 表补 surrogate key。duplicate effective key 不做 dedup、覆盖或
  last-write-wins。
- `business_content_digest` 允许 `NOT_COMPUTED`；未引入额外 business normalization
  时可以与 raw 相同，但不能用 business 伪装 raw 不变。
- R3 计算 materialization facts：`fast_row_digest`、`raw_content_digest`、
  `business_content_digest`、`snapshot_digest`、artifact digest。R4 拥有 storage
  projection、canonical storage key/schema、`CanonicalizationManifest` 与
  RepositoryImportArtifact。
- 正式入口要求显式、不可变的 `TableRulesetSnapshot` 与 matching
  `table_ruleset_version`；版本不一致或规则真源无法校验时 fail closed。
- effective key 优先级：`table_ruleset compare_key > DDL primary key > keyless fact`。

## 8. Resource budget table

R3 不宣称 numeric throughput 或 SLO。SQL/XML/table/row/field/diagnostic 上限的
权威是 [R2-S0 §8](p3-r2-s0-entry-and-budget-freeze.md) 与
`table_access.RESOURCE_BUDGETS`；本步不修订、不复制为第二份 parser 表。

| Budget | Limit | Owner/evidence |
| --- | ---: | --- |
| `max_source_package_compressed_bytes` | 256 MiB | SourcePackage / P3 design；compressed ingress |
| `max_source_package_expanded_bytes` | 1 GiB | P3 design；benchmark before tightening |
| `max_source_package_entries` | 8192 | package-security fail-closed；含 metadata-only members |
| `max_normalized_path_bytes` | 1024 | package-internal path；拒绝绝对路径与 traversal |
| `max_path_segments` | 32 | 防止深层 nesting；空 segment 已拒绝 |
| decoded SQL document | 512 MiB | R2-S0 `max_sql_source_bytes` |
| XML document | 64 MiB | R2-S0 `max_xml_document_bytes` |
| SQL/XML table, row, field, node, diagnostic | R2 frozen values | R2-S0 §8 / `RESOURCE_BUDGETS` |
| artifact manifest and row files | bounded by remaining expanded budget and table/row limits | artifact validation in S5 |

Extraction、decompression、parser streams 和 artifact writes 必须增量执行上限检查。
不允许先完整展开再校验，也不允许无界 DOM、host path、SQL executor、shell、
external XML resource 或 automatic fallback。超限产生稳定 resource 诊断并
fail closed，不发布 document ref、READY reader 或 artifact。

`max_source_package_entries` / `max_normalized_path_bytes` / `max_path_segments`
是 extraction 安全门，不是吞吐目标；若已确认业务 fixture 需要提高，必须先 reopen
本 S0 记录。

## 9. Package-security matrix

对 `TAR_GZ`、`ZIP`、`DIRECTORY`、`SQL_FILE`、`SQL_GZ` 使用同一套规则。

| Threat / fault | Required behavior |
| --- | --- |
| absolute path, `..`, empty segment, NUL, unreadable encoding | refuse；package-level `FAILED` |
| host path in entry, ref, manifest or ArtifactRef | refuse；`assert_no_host_path_identity` |
| symlink, hardlink, device, sparse or non-regular member as document | refuse；`SYMLINK_UNSUPPORTED` / equivalent |
| case or canonical path collision on required entry | package-level `FAILED` |
| missing or duplicate `/sql/dbcfg.sql` | package-level `FAILED` |
| missing `/comps/logic/logics.xml` | stable EMPTY source；no package diagnostic |
| extra members | metadata-only；不进入 SQL Snapshot identity |
| compressed ingress > 256 MiB | fail closed during streaming read |
| expanded bytes > 1 GiB | fail closed during incremental extraction |
| SQL document > 512 MiB or XML > 64 MiB | fail closed；不交给 parser |
| entry count / path length / segment count exceeded | fail closed with the named budget |
| zstd used as SourcePackage kind | refuse；not a package kind |
| zstd as internal staging transport | allowed；decompressed size still counts against expanded budget；must not be labeled `TAR_GZ` |
| truncated gzip/zstd/tar | fail closed；no partial document ref |
| required entry digest mismatch | package-level `FAILED` |

`SQL_FILE` / `SQL_GZ` 必须由调用方显式标记；不得把裸 `.sql` 或普通 `.gz` 认作多文件
业务包。普通 `.gz` 不是多文件容器。

## 10. Fixture naming and parameter-table ownership

Owner：`source_package_staging`、`snapshot_materialization`、`composite_signal`
按目录划分。S0 只冻结命名；最小 valid/invalid shape 由 S1 建立。

```text
vnext/fixtures/golden/snapshot-materialization/
vnext/fixtures/golden/composite-signal/
vnext/fixtures/vectors/snapshot-materialization/
vnext/fixtures/vectors/composite-signal/
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/test_source_package_*.py
vnext/backend/tests/test_composite_signal_*.py
vnext/backend/tests/test_repository_ref_materialization_*.py
vnext/backend/tests/test_snapshot_artifact_*.py
vnext/backend/tests/support/*materialization*
vnext/backend/tests/support/*snapshot*
```

同构错误使用模块级参数表，例如 package path/archive faults、digest mismatch、
trust-promotion rejects。不恢复 legacy compatibility matrix。不把
`vnext/fixtures/vectors/repository/` 或 `table-access/` 当作 R3 通用 corpus；
R3 可引用 R2 public parser output，但 golden 由 R3 owner 维护。纯 R3 unit tests
不创建 Dolt、不依赖永久 workspace path、不使用宽泛 skip。真实 Repository
Service/Dolt 必须 `@pytest.mark.integration`。固定时间预算必须
`@pytest.mark.serial`。

## 11. Allowed and forbidden paths

S0 确认并登记最终 allowlist。相对 R3 execution plan §3.2，本步新增：

```text
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
```

完整允许路径：

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/
vnext/backend/src/gateway_backend/capabilities/source_package_staging/
vnext/backend/src/gateway_backend/capabilities/composite_signal/
vnext/backend/src/gateway_backend/capabilities/table_rules/
vnext/backend/src/gateway_backend/artifacts/
vnext/backend/src/gateway_backend/infrastructure/artifact_store/
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/test_source_package_*.py
vnext/backend/tests/test_composite_signal_*.py
vnext/backend/tests/test_table_rules_contracts.py
vnext/backend/tests/test_repository_ref_materialization_*.py
vnext/backend/tests/test_snapshot_artifact_*.py
vnext/backend/tests/support/*materialization*
vnext/backend/tests/support/*snapshot*
vnext/backend/tests/support/source_package_fixtures.py
vnext/backend/tests/support/artifact_staging.py
vnext/fixtures/golden/snapshot-materialization/
vnext/fixtures/golden/composite-signal/
vnext/fixtures/vectors/snapshot-materialization/
vnext/fixtures/vectors/composite-signal/
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s6-focused-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s7-independent-review.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-handoff.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

`infrastructure/artifact_store/` 仅供测试 helper 与既有 LocalStore adapter 使用；
capability production 代码不得 import 该路径。`table_rules/` 仅允许增加
`TableRulesetSnapshot` / version 注入面，不得在 R3 实现 R4 storage/comparison 规则。

禁止：

```text
vnext/repository_service/
vnext/backend/src/gateway_backend/capabilities/common/
vnext/backend/src/gateway_backend/capabilities/utils/
HTTP / Workspace / Submit / PreviewResult / Operation Runtime
storage_projection / comparison / risk / mutation / application modules
canonicalization_cells.py / canonicalization_manifest.py / repository_import_artifact.py
host path fields, SQL execution, external XML resources
new service/helper/security principal
formal TAR_ZST package admission
```

S1 不得越出本 allowlist。再新增路径必须在后续 step handoff 登记。

S1 在已允许目录内新增并登记：

```text
vnext/backend/src/gateway_backend/capabilities/source_package_staging/__init__.py
vnext/backend/src/gateway_backend/capabilities/source_package_staging/contracts.py
vnext/backend/src/gateway_backend/capabilities/source_package_staging/staging.py
vnext/backend/src/gateway_backend/capabilities/source_package_staging/_paths.py
vnext/backend/src/gateway_backend/capabilities/source_package_staging/_archive.py
vnext/backend/src/gateway_backend/capabilities/composite_signal/__init__.py
vnext/backend/src/gateway_backend/capabilities/composite_signal/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py
vnext/backend/src/gateway_backend/capabilities/table_rules/__init__.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_source_package_contracts.py
vnext/backend/tests/test_source_package_staging.py
vnext/backend/tests/test_source_package_rejects.py
vnext/backend/tests/test_snapshot_materialization_contracts.py
vnext/backend/tests/test_composite_signal_contracts.py
vnext/backend/tests/test_table_rules_contracts.py
vnext/backend/tests/support/source_package_fixtures.py
vnext/fixtures/golden/snapshot-materialization/package/valid/s1-minimal-tar-gz/
vnext/fixtures/golden/snapshot-materialization/package/valid/s1-missing-xml-empty/
```

S2 在已允许目录内新增并登记：

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/materialize.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_reader.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_ruleset.py
vnext/backend/tests/test_snapshot_materialization_sql.py
vnext/backend/tests/test_snapshot_materialization_status.py
vnext/backend/tests/support/snapshot_materialization.py
vnext/fixtures/golden/snapshot-materialization/sql/valid/s2-minimal-create-insert/
vnext/fixtures/golden/snapshot-materialization/sql/valid/s2-duplicate-rows/
vnext/fixtures/golden/snapshot-materialization/sql/valid/s2-keyless/
vnext/fixtures/golden/snapshot-materialization/sql/valid/s2-null-and-types/
vnext/fixtures/golden/snapshot-materialization/sql/partial/s2-unknown-type-mixed/
vnext/fixtures/golden/snapshot-materialization/sql/malformed/s2-document-failed/
```

## 12. Reopen record

S0 未 reopen 任何 owning ADR 或 contract：

| Item | Action | Scope |
| --- | --- | --- |
| ADR 0013 | 不修订 | R2-S0 双边界仍有效；R3 消费 parser public facts |
| ADR 0012 | 不修订 | 同机单一信任域；不新增 broker/sidecar |
| SourcePackage contract | 不扩写 `TAR_ZST` | zstd 保持 internal-only / Repository import |
| Snapshot contract | 不把 trust 并入 `materialization_stage` | S1 并行落成两套标签 |
| table_rules / R4 | 不夺取 storage 规则 | 仅最小注入面 |

若后续发现下列情况，必须先 reopen owning contract/ADR，再改 S0/S1 记录：

- source/package ownership 无法保持 `source_package_staging` 与 materializer 分离；
- zstd 被提升为正式 SourcePackage kind 而未审查 contract/ADR；
- table rules 无法以不可变 snapshot 注入，或出现 hidden mutable global；
- SQL/XML composition 在业务失败时发布 partial `composite_signal_point`；
- hidden summary mismatch 后从 catalog/rows 重建；
- digest 随 row order 或 package compression metadata 变化；
- artifact publication 非原子，或 reader 把 partial rows 伪装为 READY；
- R3 import Repository/application/HTTP implementation details；
- 需要提高 §8 numeric budget 才能接纳已确认业务 fixture。

## 13. Deferred register impact

| ID | S0 status |
| --- | --- |
| `R2-D04` | 入口关闭；S3 实现 `logics.xml` / `composite_signal_point`；S0 冻结业务失败原子性 |
| `R2-D05` | S4 protocol + fake provider；真实 Dolt = `R3-D02` |
| `R2-D06` | R3 做 Snapshot/raw/business digest；storage projection = `R3-D04` / R4 |
| `R2-D07` / `R3-D03` | 仍延后；retention/pinning/eviction/quota |
| `R2-D08` / `R3-D06` | 仍延后；Rust materializer / automatic fallback |
| `R2-D09` / `R3-D07` | 仍延后；durable cancel/checkpoint/takeover |
| `R3-D01` | 仍延后；formal `TAR_ZST` |
| `R3-D02` | 仍延后；Repository Service/Dolt production adapter 与 hidden-summary **write** |
| `R3-D04` | 仍延后；storage projection / CanonicalizationManifest |
| `R3-D05` | 仍延后；projection cache 与 export-format matrix |

composite capability 文档中的 risk、frontend、bundle 与 dataset-replacement 语义
不在 R3 实现。

## 14. Verification record

S0 不宣称 materialization conformance、R3 gate、container 或 production validation
已通过。Container rebuild：**no**。理由：只改 formal docs，未触碰 image、deployment
或 container-only runtime boundary。Last verified image revision：none；source-tree
文档审查是本步权威 evidence。Container gate for current HEAD：`not-applicable`。

S0 执行时工作树仅 docs dirty（含既有未提交的 R3 detail plan 与本步 S0 记录）；
无 `vnext/` 代码变更。

| Command | Result |
| --- | --- |
| `git status --short` | **docs only**；无 `vnext/` 变更。tracked 修改 6 个 plan 文件；untracked `p3-r3-s0-entry-and-budget-freeze.md`、`p3-r3-source-materialization-execution-plan.md` |
| `git diff --check` | **passed**（tracked）；untracked S0/R3 plan 文件 `--no-index` 无 whitespace error |
| forbidden path/import scan | **pass**；现有 capabilities 无 `dolt` / `host_path` / `fastapi` / `workspace`；`source_package_staging` / `composite_signal` 尚未落地属预期 |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py` | **14 passed**（0.63s）；当前 DAG 仍为 `snapshot_materialization -> {table_access, table_rules}` |

```yaml
Current HEAD: 3c142f8e7616fb4cc2594a61128b2ccce494dd46
r2_validated_code_sha: 2a799cf30508ab6a380718eeacd6f721fc247b20
Container rebuild required: no
Reason: formal docs only; no image, deployment, or container-only runtime boundary
Last verified image revision: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none
Required execution point: later R if an image/deployment/container boundary is introduced
```

建议 S1 首轮命令：

```text
cd vnext/backend
uv run pytest -m unit tests/test_architecture.py tests/test_source_package_*.py tests/test_snapshot_materialization_*.py
uv run ruff check .
uv run mypy
git diff --check
```

S1 若尚未创建全部测试 glob，按实际新增文件收敛，不机械扩大范围。无 Dolt。

## 15. S1 entry package

**Recommendation：S0 complete，允许进入 S1 public contract 与 SourcePackage staging
skeleton；不得把本结论表述为 R3 gate 通过或 S2+ 实现授权。**

S1 必须：

- 只在 §11 allowlist 内落成 `source_package_staging`、`snapshot_materialization`、
  `composite_signal` public ports 与 `table_rules` 最小 `TableRulesetSnapshot` 注入面；
- 扩展 `test_architecture.py` 的 `CAPABILITY_OWNERS` / `ALLOWED_UPSTREAM_OWNERS`
  至 §3 DAG；
- 实现 bounded `TAR_GZ` resolver 与 ZIP/DIRECTORY/SQL_FILE/SQL_GZ helpers；
  normalized path 与 symlink/traversal 拒绝；required SQL uniqueness；optional XML
  EMPTY source；entry/package/document digests；opaque artifact refs；explicit
  compression metadata；
- 不实现 SQL/XML 业务解释、Snapshot digest 算法、Repository provider、Parquet
  publish；
- 不引入第三方依赖、不创建 Dolt、不 import infrastructure；
- 最小 valid/invalid fixture shape 使用 §10 命名；同构错误用参数表。

S1 可与 S0 同一对话。本文件不自动授权 S2 SQL Snapshot materializer。
`p3_implementation_authorized` 保持 `no`。

## 16. S1 public contract and SourcePackage staging skeleton record

S1 将 §3/§5/§8–§11/§15 落成可导入的 R3 public ports 与 bounded SourcePackage
staging walking path。不解析 SQL/XML 业务语义，不物化 Snapshot，不引入第三方依赖，
不创建 Dolt。`p3_implementation_authorized` 仍为 `no`。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/source_package_staging/
vnext/backend/src/gateway_backend/capabilities/composite_signal/
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/src/gateway_backend/capabilities/table_rules/contracts.py
vnext/backend/src/gateway_backend/capabilities/table_rules/__init__.py
vnext/backend/tests/test_architecture.py
vnext/backend/tests/test_source_package_contracts.py
vnext/backend/tests/test_source_package_staging.py
vnext/backend/tests/test_source_package_rejects.py
vnext/backend/tests/test_snapshot_materialization_contracts.py
vnext/backend/tests/test_composite_signal_contracts.py
vnext/backend/tests/test_table_rules_contracts.py
vnext/backend/tests/support/source_package_fixtures.py
vnext/fixtures/golden/snapshot-materialization/package/valid/s1-minimal-tar-gz/
vnext/fixtures/golden/snapshot-materialization/package/valid/s1-missing-xml-empty/
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

Public staging entry is `stage_source_package`. Package kinds are
`TAR_GZ|ZIP|DIRECTORY|SQL_FILE|SQL_GZ`; zstd is `StagingTransport` only.
`TAR_ZST` is not a kind. Missing optional XML yields `empty_composite_logic=True`
with no package diagnostic. There is no `NotImplementedError` stub and no
`materialize_*` entrypoint.

S1 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_source_package_*.py tests/test_snapshot_materialization_contracts.py tests/test_composite_signal_contracts.py tests/test_table_rules_contracts.py` | **55 passed**（0.74s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 91 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/staging/test/docs，未触碰
image/deployment boundary。无 Dolt。`p3_implementation_authorized` 仍为 `no`。

S2 必须严格执行 §6–§9；不得从本 skeleton 猜测 Snapshot digest、Repository provider
或 Parquet 语义。

## 17. S2 SQL Snapshot materialization record

S2 将 R2 公开 `ParseResult` 与不可变 `TableRulesetSnapshot` 物化为 SQL-only
Snapshot / SnapshotSummary / 可选 `SnapshotTableSet`。不在 capability 内调用
SQL parser，不实现 XML/composite、RepositoryRef 或 Parquet。
`p3_implementation_authorized` 为 `s2_sql_only`，不授权 S3。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/support/snapshot_materialization.py
vnext/fixtures/golden/snapshot-materialization/sql/
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

Public entry is `materialize_sql_snapshot`. Policy `ARTIFACTS_REQUIRED` fail-closed。
`business_content_digest` 保持 `NOT_COMPUTED`。stage/trust 正交配对；不自提升
`COMMIT_VALIDATED`。

S2 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_snapshot_materialization_*.py tests/test_table_rules_contracts.py` | **43 passed**（0.58s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 98 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/algorithm/test/docs，未触碰
image/deployment boundary。无 Dolt。`p3_implementation_authorized` 为
`s2_sql_only`。S3 不得从本步猜测 XML 业务 AST 或 derived table 语义。

## 18. S3 Composite XML and business-source composition record

S3 实现严格 `logics.xml` 业务 AST、EMPTY source、特殊装置不变量、
`composite_signal_point` 派生表，以及 flow-neutral 的 SQL+XML 业务组合。
不实现 RepositoryRef、Parquet/`SnapshotTableArtifact`、risk、frontend 或 bundle。
`p3_implementation_authorized` 为 `s2_s3`，不授权 S4/S5。

Public entries：

- `materialize_composite_signal`（`composite_signal.contracts`）：消费 XML document
  result 与 special-device catalog DTO；不调用 XML document parser。
- `materialize_business_snapshot`：组合 SQL Snapshot 与派生表并重建业务 identity；
  不改写源 SQL 表；业务不变量失败时整单 `FAILED`，不发布派生表。

SQL-only `materialize_sql_snapshot` identity 保持不变。业务 Snapshot digest 额外纳入
XML/EMPTY digest、`composite_signal_contract_version` 与派生表 descriptor。
`business_state_digest` / `business_content_digest` 仍为 `NOT_COMPUTED`。
`ARTIFACTS_REQUIRED` 继续 fail-closed；派生表将走 S5 同一 artifact 路径，S3 不写 Parquet。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/composite_signal/
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/
vnext/backend/tests/test_composite_signal_*.py
vnext/backend/tests/test_snapshot_materialization_*.py
vnext/backend/tests/support/composite_signal.py
vnext/backend/tests/support/snapshot_materialization.py
vnext/backend/tests/test_architecture.py
vnext/fixtures/golden/composite-signal/
vnext/fixtures/golden/snapshot-materialization/business/
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
```

S3 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_snapshot_materialization_*.py tests/test_composite_signal_*.py tests/test_table_rules_contracts.py` | **87 passed**（0.88s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 108 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/algorithm/test/docs，未触碰
image/deployment boundary。无 Dolt。`p3_implementation_authorized` 为
`s2_s3`。S4 不得从本步猜测 RepositoryRef provider 或 hidden-summary 语义。

## 19. S4 RepositoryRef materialization provider boundary record

S4 冻结只读 `RepositoryTableAccessProvider` / `RepositoryRefSession` 协议、hidden
FINAL summary 权威 readback，以及协议一致的 in-memory fake。不实现真实 Repository
Service/Dolt adapter、hidden summary 写入、Parquet/`SnapshotTableArtifact` 或
`COMMIT_VALIDATED` 自提升。`p3_implementation_authorized` 为 `s2_s3_s4`，不授权 S5。

Public entry：`materialize_repository_ref`。`source_kind` 固定
`IMMUTABLE_REPOSITORY_REF`。Session 通过 `read_hidden_summary()` 读取 hidden FINAL
facts；catalog 只做表级校验与 tuple row access，不得在 mismatch 后重建 summary。
`get_catalog()` session 内 memoize；`requested_tables` 不 relist。成功结果为
`FINAL` + `CONTENT_VERIFIED`。`ARTIFACTS_REQUIRED` 继续 fail-closed。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/repository_ref.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/scalar_encoding.py
vnext/backend/tests/support/repository_ref_materialization.py
vnext/backend/tests/test_repository_ref_materialization_protocol.py
vnext/backend/tests/test_repository_ref_materialization_hidden_summary.py
vnext/backend/tests/test_repository_ref_materialization_digest.py
vnext/backend/tests/test_snapshot_materialization_contracts.py
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S4 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_snapshot_materialization_*.py tests/test_repository_ref_materialization_*.py tests/test_composite_signal_*.py tests/test_table_rules_contracts.py` | **120 passed**（0.82s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 114 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/protocol/test/docs，未触碰
image/deployment boundary。无 Dolt。`p3_implementation_authorized` 为
`s2_s3_s4`。S5 不得从本步猜测 Parquet publish 或 `COMMIT_VALIDATED` promotion。

## 20. S5 SnapshotTableArtifact and cache integrity record

S5 冻结不可变 `SnapshotTableArtifact`（JCS manifest + Parquet rows）的
staging→校验→原子发布，以及进程内 cache 的 `PROVISIONAL` / `CONTENT_VERIFIED` /
`COMMIT_VALIDATED` 校验与显式 promotion。不实现 retention/eviction/quota、
projection cache、hidden summary 写入、真实 Dolt adapter，也不允许
`materialize_*` 自提升 `COMMIT_VALIDATED`。`p3_implementation_authorized` 为
`s2_s3_s4_s5`，不授权 S6/S7 审查。

三个 materialization 入口在 `ARTIFACTS_REQUIRED` 下显式注入 `ArtifactStorePort`；
store 缺失 fail-closed，不发布 Snapshot。失败表不 publish。commit point 是校验
通过后的 manifest `put`；未发布 manifest 的 parquet 不算 ready。Cache key 不含
flow/operation/table name/host path；`PROVISIONAL` 无再校验则拒绝；promotion 必须
带匹配的 `CacheAuthorityInput`。

Changed paths：

```text
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/contracts.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/__init__.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_parquet.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_reader.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/artifact.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/cache.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/materialize.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py
vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/repository_ref.py
vnext/backend/tests/support/snapshot_artifact.py
vnext/backend/tests/support/snapshot_materialization.py
vnext/backend/tests/support/repository_ref_materialization.py
vnext/backend/tests/test_snapshot_artifact_roundtrip.py
vnext/backend/tests/test_snapshot_artifact_faults.py
vnext/backend/tests/test_snapshot_artifact_cache.py
vnext/backend/tests/test_snapshot_materialization_status.py
vnext/backend/tests/test_snapshot_materialization_business.py
vnext/backend/tests/test_snapshot_materialization_contracts.py
vnext/backend/tests/test_repository_ref_materialization_protocol.py
docs/backend-vnext/refactoring/formal/plans/p3-r3-s0-entry-and-budget-freeze.md
docs/backend-vnext/refactoring/formal/plans/p3-r3-source-materialization-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-active-context-index.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-execution-plan.md
docs/backend-vnext/refactoring/formal/plans/p3-capability-foundation-design.md
docs/backend-vnext/refactoring/formal/plans/implementation-stages.md
```

S5 验证（2026-08-19）：

| Command | Result |
| --- | --- |
| `cd vnext/backend && uv run pytest -m unit tests/test_architecture.py tests/test_snapshot_materialization_*.py tests/test_snapshot_artifact_*.py tests/test_repository_ref_materialization_*.py tests/test_composite_signal_*.py tests/test_table_rules_contracts.py` | **139 passed**（0.99s） |
| `cd vnext/backend && uv run ruff check . && uv run mypy` | **passed**；mypy 121 source files |
| `git diff --check` | **passed** |

Container rebuild：**no**。理由：纯 Python contract/algorithm/test/docs，未触碰
image/lock/Compose/entrypoint。无 Dolt。`p3_implementation_authorized` 为
`s2_s3_s4_s5`。S6/S7 不得把本步结果表述为 R3 module gate。
