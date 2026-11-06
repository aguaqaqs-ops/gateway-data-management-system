# Canonical Storage and Repository Boundary Contract

状态：正式设计（Accepted）；`3.1.0` 于 2026-09-27 接受（[ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)）；`3.2.0` 于 2026-10-12 按 owner 决议 DC29 修订；`3.3.0` 于 2026-10-26 按 Phase 6 S1a 修订；`3.4.0` 于 2026-10-27 按 DC58 修订；`3.5.0` 于 2026-11-06 按 DC85 增补 S2b A 内存 codec 边界

阶段：Phase 0 结论；Phase 2、Phase 3、Slice 5A/5B 实现

Contract ID：`gateway-vnext.canonical-storage-and-repository-boundary`

Owner：Table Rules/Storage Projection（canonical content）；Repository Service（generic repository effect）

Semantic version：`3.5.0`（2026-11-06，DC85；前版 `3.4.0`、`3.3.0`、`3.2.0`、`3.1.0`、`3.0.0`）

Storage projection version：`3`（Phase 6 S1a 统一 manifest 表摘要为 `raw_content_digest`，并删除 `ordering_digest`；前版 `2` 于 P5 收口 S2a-F1 的负零规范化时提升）

## 1. Authority boundary

```text
Immutable SourcePackageArtifact (raw upload authority)
  -> parse + frozen table rules + storage projection
  -> CanonicalizationManifest + RepositoryImportArtifact
  -> Repository Service generic import/commit
  -> caller-policy import result + immutable CommitId
```

SourcePackageArtifact 保存原始 bytes、provenance 和 replay authority。Dolt commit 保存 canonical business state，不保证复原原始 SQL schema、所有物理列或原始 DDL。Submit 成功时 source artifact retention 提升为 submission durable；读取原始输入必须回到该 artifact。

Source artifact digest、storage projection digest、canonical business digest、
CanonicalizationManifest digest和Dolt commit hash是不同语义域，不能互换。

canonical storage snapshot 之间的 `REBUILD_TABLE | PATCH_DML | NOOP` 计划、target-neutral
`ChangeSetArtifact` 和 renderer boundary 由 [Storage Mutation and Change Set](storage-mutation-and-change-set.md)
唯一拥有；本 contract 只拥有 canonical storage、projection、manifest 和 Repository
generic effect 的边界。

## 2. Storage projection 与比较规则视图

Storage projection 在 import 前决定 Dolt 长期保存的 canonical schema、physical key 与 structural fact。比较在规范域进行：两侧都是规范快照（storage projection 输出或 Repository commit 读取）。比较语义由 table_rules 的 `ComparisonRuleView` 提供、由 comparison 消费，使用运行期规则集。`StorageRuleView` 与 `ComparisonRuleView` 来自同一 table-rules source，各有独立的 digest。比较不使用 native diff，始终按列名与有效键对齐（§7）。R4 已确认：legacy `ignored_columns` 是 canonical storage policy，不再只是 comparison-time filter；这些列从 canonical schema/Dolt business state 中删除，但仍保留在 SourcePackageArtifact、Snapshot facts 和 LegacyRuleDecision 中供 parity、provenance 与原始数据读取使用。

列策略只允许：

| Policy | 语义 |
| --- | --- |
| `PERSIST_BUSINESS` | canonical business identity/value |
| `RETAIN_FOR_STRUCTURE` | 恢复顺序/结构所需，不一定参与普通 modified 判断 |
| `DROP_FROM_STORAGE` | ruleset 明确声明不属于 canonical identity/value/order 的列；R4 legacy `ignored_columns` 使用此策略 |

只有 `DROP_FROM_STORAGE` 在写 Dolt 前删除；manifest 必须记录列、理由、规则版本和 source/canonical schema digest。

R4 对每个 legacy `ignored_columns` 生成 `DROP_FROM_STORAGE`，manifest reason 至少包含
`legacy_ignored_column` 和 owning selector。被标记为 ignored 的列不得同时作为 effective key、
ordered identity 或其他 required structural column；出现冲突时 ruleset validation 失败，不能
通过保留该列或退回 comparison-only 语义来继续。

`compare_excluded_columns` 表示保留在存储中（`PERSIST_BUSINESS`）、但不参与值比较的列，不得与
`ignored_columns`、有效键、ordered identity 或结构列重叠。ordered 表的位置列（如 `no`）是
`RETAIN_FOR_STRUCTURE` 列，由 ordered 语义处理，不得列入 `ignored_columns`。

Canonical effective key、canonical column set 和 dropped-column set 是持久 structural facts：
R4 将它们写入 `CanonicalizationManifest` 与 `RepositoryImportArtifactInput`，Repository
随后据此形成 Dolt 的 canonical schema/physical key。它们不是只供 comparison 的临时选择，
source DDL 仅作为 provenance；当前 canonical commit 的 schema/key 才是权威存储解释。

## 3. Key、行完整性与 ordered table

普通 canonical keyed table 必须验证 effective key 存在且 retained、tuple 非空、整表唯一，且 projection 前后 row count 相同。不得用 dedup、last-write-wins、覆盖或丢行满足主键。失败在 Preview 形成 typed blocker，在 Submit 的 Repository effect 前拒绝。Keyless/multiset 只能由 ruleset 规定：显式规则使用 `EXPLICIT_KEYLESS`；SNAPSHOT_ONLY、BROWSE_ONLY 与 raw-PK 兜底规则使用 `DDL_PRIMARY_KEY_OR_KEYLESS`，源 DDL 有主键时以其为有效键，没有主键时该表按 keyless 存储（DC29）。keyless 表保留全部行（含完全相同的重复行），不去重，投影前后 row count 相同；内容摘要与行顺序无关；内容变化时整表重写，不做按行补丁。其余规则的有效键缺失仍是 typed blocker。

Ordered table 第一版保持单表：

```text
gid  INT UNSIGNED NOT NULL PRIMARY KEY
no   INT NOT NULL                 -- RETAIN_FOR_STRUCTURE
business columns
```

读取顺序必须显式 `ORDER BY no`；Dolt insertion/physical order 不是 contract。`no` 进入 ordering validation/digest/provider，不进入普通 row-content modified 判定。第一版接受罕见 position shift 带来的 Dolt storage diff noise，不建设独立 position/edge table。

Canonical `gid` domain：

```text
real:   1 .. 3_999_999_999
pseudo: 4_000_000_000 .. 4_294_967_295
0:      forbidden
```

Source real gid 必须唯一并处于 real range；source `0 | NULL | empty` 才生成 pseudo。按 canonical `no` 验证、排序后，从 `4_000_000_000` 连续分配；`no` 必须正、唯一、连续。Source 值落入 pseudo range 是 blocker。不得使用 UUID、auto increment、insert order、object identity 或随机值。Pseudo gid 只作 physical identity，不展示为真实业务 gid。

## 4. CanonicalizationManifest

每次 import 的 durable `CanonicalizationManifest`至少记录：contract/storage
projection version，source artifact digest，ruleset ID/version/digest；每表
source/canonical schema digest、source/canonical row count、
retained/structural/dropped columns+reason、canonical key、统一表摘要
`content_digest`（其值等于该表的 `raw_content_digest`）、ordered identity policy 与
gid range/count；以及 manifest digest。Manifest 不包含 `ordering_digest` 或额外的行摘要字段。
Snapshot digest 的每表输入为表名、比较 schema 摘要、业务 schema 摘要、比较键、行数与
表摘要；不读行的 Repository-ref 描述由 catalog 与 manifest 生成，并与读行描述逐字段相同。
Upload、Preview baseline 与 History 两侧使用同一算法，不以 SubmitAttempt 中的 snapshot
digest 替代计算。Manifest 只保存统一表摘要 `content_digest`，不保存额外的逐行摘要。

Table Rules/Storage Projection owner拥有其语义。Repository Service只消费manifest中的
required table、schema和row count做structural check；不验证业务content/ordering
digest，也不得选择业务列、key、pseudo gid或ordered policy。

Backend必须在临时Repository import package可能被删除前durable保存
CanonicalizationManifest。Repository package中的`manifest.json`只携带结构字段和
opaque`canonicalization_manifest_digest`；它不是完整业务manifest，也不取得业务
语义owner。

`canonicalization_manifest_digest` 算法保持
`RFC8785-JCS + gateway-vnext:canonicalization-manifest:v1\0 + SHA-256`。本轮是首次
发布前的 v1 定稿，替换尚未发布的 one-off producer 内容，不增加 `v2` 或兼容字段。

每表 schema digest 的 canonical payload 必须包含：normalized `sql_type`（因此包含
ENUM label / SET member 的声明顺序）、`nullable`、primary-key order。表按 canonical
name bytes 排序，列保持 DDL order，与 Repository package manifest 一致。charset /
collation 列修饰符不属于 v1 schema identity。Arrow 物理类型不进入 schema digest。

该每表 schema digest 保持 DDL 列序，用于 manifest 发布时的自洽核对与 mutation planning 的 schema
变化判断，并计入 manifest digest；Repository STRUCTURAL 比较的是包内 `manifest.json` 的列、主键与
行数，不使用它。比较、规范状态摘要与 `NO_CANONICAL_CHANGE` 使用 Snapshot Materialization 拥有、与
列序无关的 business schema digest（ADR 0018），二者不可互换。

每表的 `content_digest` 使用 Snapshot Materialization 定义的 `raw_content_digest`：先按
[Shared Canonical Encoding](shared-canonical-encoding.md) §3.2 对保留列的每个规范单元格编码，
形成行摘要，再以无序 row-hash 聚合计算表摘要。它与行顺序无关，保留重复行；空表摘要不包含
schema 输入，任何使用方都必须同时检查行数、schema digest、StorageRuleView 与投影版本。
Ordered 表的规范行包含结构列 `no` 与伪 gid，因此它们的变化会改变统一表摘要。

单元格 bytes 由 [Shared Canonical Encoding](shared-canonical-encoding.md) §3.2 唯一拥有：

```text
ENUM 单元格 = string 或 null 的 scalar_frame
SET NULL 单元格 = null scalar_frame
SET 非 null 单元格 = sequence_frame 本身，不再外包 scalar tag
```

空 SET 是长度为 0 的 `sequence_frame`，不得写成 null。不使用 Shared Kernel `encode_row`，
不升 `canonical_encoding_version`。ordinal、
dictionary index 与未规范化的 SET 输入顺序不得进入 row preimage。Repository 任一 verification
level 都不重算这些业务 digest。

## 5. Artifact lifecycle

`SnapshotTableArtifact` 是 Preview 产生的 immutable full-row table facts。仅在尚未被接受的 current Preview 或 active SubmitAttempt 需要时持久 pin。AcceptSubmit T1 将 pin responsibility 从 Preview 原子转给 Attempt；历史 Preview 引用本身不继续 pin。Attempt 进入 `FINALIZED/ABORTED` 后释放 pin，artifact 转为可重算 cache material。第一版不长期保存重复 full-row archive。

长期审计/恢复权威为durable SourcePackageArtifact、accepted canonical Dolt
commit和CanonicalizationManifest。需要重算未pin full-row facts时，从source
artifact按固定parser/ruleset contract重建。

Submit从exact Preview-bound SnapshotTableArtifact开始，不重新解析SQL。
`RepositoryImportArtifact`包含canonical schema/rows和临时structural manifest；
每个Attempt只构建一次并持久checkpoint。Retry、takeover/reconcile先复用
`BackendArtifactRef`与raw SHA完成upload，再复用Repository返回的独立
`RepositoryArtifactRef`执行import；不能在unknown outcome后重建package或分配新key。
两个ref字段同形但ID scope与nominal type不同，不能共享class或相互复制artifact ID。

若Preview-bound canonical business digest与base相同，AcceptSubmit在Attempt前返回
`NO_CANONICAL_CHANGE`：不构建RepositoryImportArtifact、不提升source artifact
retention、不调用Repository。Attempt终态后RepositoryImportArtifact也解除durable
pin；accepted commit的长期authority由SourcePackageArtifact、
CanonicalizationManifest与canonical Dolt history共同提供。

### 5.1 Canonical IPC v1 内存 codec（S2b A）

本节拥有 backend 内部规范表的物理映射与纯内存编解码边界。A 不接管本节前述 artifact 生命周期、文件/mmap、引用、冻结恢复或 worker；这些接线按 S2b 后续小节实施。新增物理表示不改变 storage projection version、业务 schema/content digest、Repository wire 或客户端 Parquet。

调用者提供已完成业务物化、规范投影、按 owning 语义排好行的 Arrow batches 与规范列声明。`sql_type` 必须是本 Contract 规范投影所用 `normalize_sql_type_spelling` 的既有输出；codec 不再提供另一个 SQL normalizer。输入按 canonical 列名绑定，重复/缺失/不匹配的列拒绝；内存输出物理列按 canonical 名 UTF-8 排序，解码可按绑定的外层列名顺序重排，不依赖原始 ordinal/display name。

具体类型、唯一 metadata 与 file profile 固定为已获 DC85 批准的[规范表 Arrow 映射 v1 §2–§4](../plans/p6-s2b-arrow-mapping-design.md)：

- 整数 Int64/UInt64、Boolean、Float32/64、Binary、定宽 BIT；其余规定的逻辑类型用规范 UTF-8 文本；SET 文本与业务 sequence framing 保持各自职责。可空性来自规范声明，small/large 按整列 payload 决定。
- schema metadata 仅 `gdds.canonical_mapping_version=1`，field metadata 仅 `gdds.canonical_type`；四键 JCS 声明由规范 schema 决定，不能保存使相同规范身份产生不同 bytes 的原始拼写或实例字段。业务 schema digest 已含表名，不据此承诺跨不同表名去重。
- 单一 Arrow IPC file writer/reader，V5、64-byte alignment、非 legacy、无压缩/字典/自定义 footer metadata；65,536 行固定切批，空表零 batch。offset、validity、Boolean 尾位和 NULL slots 按映射 profile 规范化，N/chunk/DDL 列序不改变同一规范输入的 IPC bytes。

合法规范业务值是物化/projection owner 的前置。codec 验证实际映射所需的类型、声明、可空性、整数范围、有限浮点及 SET/BIT 约束，保持值不变；不复制完整 DECIMAL、时间或 JSON 业务语法算法。其内存 decoder 证明格式/profile/类型与绑定描述一致以及资源边界，不独立证明所有业务值合法，也不作为外来 IPC 的业务导入验收器。后续存储由已验证生产者、raw SHA 和绑定身份共同保护；外来输入仍走其 owning 校验。

标准 reader 前必须在借用输入上检查 footer/block 的长度与范围、必要 raw metadata 的唯一键及版本/绑定一致，避免重复键被 HashMap 覆盖或伪长度触发超预算分配。复用第三方公开 safe API，不新建 IPC 格式实现或 unsafe FFI。

局部 options 明示行、列、输入/输出 bytes 与 codec 峰值预算，增长前用 checked 运算拒绝超限。`max_input_bytes` 独立限制借用输入的保守字节求和；`max_codec_peak_bytes` 限制 codec/adapter 拥有的同时存活分配，包括 schema/metadata、布局索引、规范数组、当前 batch、writer 内部 encoded data、累计输出及 adapter 输出复制。整体保守占用须合看两个上限，不把借用输入漏掉，也不重复算成 codec 拥有。A 不建立共享 allocation registry；估计口径与完整 worker M/RSS 分开。取消和可选有限单调 deadline 在有界循环及标准编解码调用前后检查；不返回可被当作成功的部分结果。错误区分 schema、value、resource、cancelled、deadline、IPC 格式类别，adapter 保留类别并按既有 policy 处理 panic，不把 native abort 伪装成正常失败。

`max_output_bytes` 仅限制 encoder 生成的 IPC 文件长度；decoder 以 `max_input_bytes` 限制借用的文件 bytes，以 codec peak 预算限制其解码结果及其他同时存活分配，不以输出 quota 代替输入限制。零列批次仍须保留显式行数，使用标准 Arrow row-count 选项，不静默归零，也不新增匿名行计数格式。

core 接受 caller-owned pool，不创建每表/每调用新池，不做文件 I/O；Python adapter 仅粗粒度 Arrow C Stream 和小型 metadata，主计算区间释放 GIL，不构造整表 Python row/list/dict。固定向量依据 Shared Kernel/现有 owner 与独立 IPC 布局核对，不能仅从新实现生成期待值后自证；实际局部 bytes 在 A handoff 记录，不宣称生产容量、FULL 或 W2 通过。

## 6. Repository import、journal 与 readback

Repository Service通过public wire contract接收RepositoryImportArtifact，执行writer
serialization、Dolt apply/commit、operation marker、mandatory commit CAS，以及caller
选择的`NONE | STRUCTURAL | FULL_SCAN` verification。默认`STRUCTURAL`；精确含义由
[Repository Service](repository-service.md)唯一拥有。

所有level都检查upload size/raw SHA、package safety、matching marker、expected parent
和target CAS。`NONE`只跳过catalog检查；`STRUCTURAL`比较table/schema/row count；
`FULL_SCAN`再以bounded batches读取全部user rows并验证type conversion与实际row
count。任何level都不计算business content/ordering digest或防篡改evidence。

业务表摘要在 import 前由 Storage Projection owner 计算和保存。Ordered Diff 的逻辑摘要与
occupancy 摘要仍由 Comparison owner 按当前有效 pair 策略计算；它们与表摘要是不同语义。
Caller 根据业务风险选择 Repository verification level，并为低保障选择负责；Repository 的
FULL_SCAN 仍不能替代业务表摘要 validation。

RepositoryImportArtifact是Storage Projection owner的content contract；minimal
ArtifactRef只包含opaque ID、media type、size和raw SHA。Repository Service只解释
structural fields，其他canonical fields语义仍由Storage Projection owner定义。

Backend effect checkpoint必须先保存Backend package ref、durable manifest ref/digest、
upload/import idempotency key、RepositoryId、target ref与expected commit；upload成功
后追加Repository artifact ref，import接受后追加Repository operation ID。完整handoff
顺序见
[DX Cross-Phase Interface Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)。

### 6.1 RepositoryImportArtifact v1 package

V1 media type为
`application/vnd.gateway.repository-import.v1+tar+zstd`。解压后必须恰有两个regular
file，顺序固定：

```text
manifest.json
replay.sql
```

禁止其他entry、absolute/traversal path、duplicate、link、device、FIFO和extended
filesystem metadata。`manifest.json`是UTF-8 JSON，最小shape为：

```text
package_version
canonicalization_manifest_digest
tables[]
  name
  schema
    columns[]
      name
      sql_type
      nullable
    primary_key[]
  row_count
```

`canonicalization_manifest_digest`由Storage Projection拥有，Repository只把它作为
opaque关联值。完整contract、ruleset、source/table digest保存在Backend
durable CanonicalizationManifest，不复制到临时package。Package传输完整性只使用
minimal ArtifactRef的size/raw SHA-256。

`package_version`固定为integer `1`；`row_count`是非负integer。`tables`按canonical
table name bytes排序，table name唯一且不得含leading/trailing whitespace；`columns`保持DDL order且name唯一；
`primary_key`按key order引用已声明column。`sql_type`是bounded normalized physical
SQL type，`nullable`是boolean。Object unknown field、duplicate或invalid key
reference全部拒绝。`manifest.json`使用strict UTF-8 JSON，但不要求JCS，也不建立
package semantic/self digest。

`replay.sql`是受信Storage Projection相对 expected parent 生成的确定性 replay，不是外部用户
提交的任意SQL。满足完整未变化条件的表不进入 replay；新增或变化表按冻结的修改策略写入，删除表生成
`DROP`。Package manifest 仍列出目标 ref 的全部表，以便 Repository 校验完整 catalog。Parent 为
INITIAL、缺少 manifest 或 projection version 不同时，所有当前表均按变化处理。Repository Service
将 replay 限制在 server-owned Repository/Dolt runtime 内执行，不建设完整 SQL grammar 或 semantic
package validator。若信任边界改变为
不可信上传者，必须重开ADR 0009。

## 7. Projection upgrade/schema alignment

每个 commit 记录 `storage_projection_version + ruleset_digest`。同版本可走 normal/native route；版本不同必须进入 schema-change alignment，禁用不安全 native data diff，按 compatible columns/effective key streaming fallback。无法安全 alignment 时明确 table-level degraded。

不回写/迁移整个历史。Key set 改变不得假设 native diff 正确；新规则所需而旧 commit 未保存的列不得从 Dolt 猜测，可从 durable SourcePackageArtifact 显式重算。Schema change source 标记为 `SOURCE_SCHEMA | STORAGE_PROJECTION_POLICY | BOTH`。

旧 Dolt repository 的迁移/兼容策略不由本文决定，必须作为独立 cutover gate。

Ruleset 改变 canonical key、字段集合（包括 ignored-column drop/restore）、类型、null 语义或 storage projection 时，按
[Ruleset Activation and Migration](ruleset-activation-and-migration.md) 标记为
`STORAGE_BREAKING`，不得由普通 Submit 或 `ADAPTIVE_PATCH` 隐式处理。

## 8. Classification 与版本

Module public：是。Persisted：SourcePackageArtifact、manifests、RepositoryImportArtifact checkpoint 和 Dolt commit。Wire：artifact refs + Repository public contract + stream.

改变列 policy/key/ordered identity/canonical bytes 必须升级相应 storage projection、ruleset 或 canonical encoding version，并建立新 digest/cache identity。纯 Repository implementation 优化不得改变 canonical content。

`3.1.0`（2026-09-27）：§2 改为规范域比较与 `ComparisonRuleView`，增加 `compare_excluded_columns` 约束；§4
说明 manifest 每表 schema digest 与 business schema digest 的区分。manifest 载荷结构与
`canonicalization_manifest_digest` 算法不变；CanonicalizationManifest 的 `contract_version` 自
[P5 架构收口](../plans/p5-arch-closure-design.md) S2a 起记录 `3.1.0`，读取接受历史版本。storage projection
version 不变；若 S1 kickoff 普查触发 JSON 以 LONGTEXT 存储，在 S2a handoff 中按本节写明是否提升。实现随收口
S1–S5 交付，交付前现行源码仍按 `3.0.0` 行为运行（已随 P5 收口交付，tag `p5-exit`）。

`3.2.0`（2026-10-12，DC29）：§3 增加 `DDL_PRIMARY_KEY_OR_KEYLESS`，SNAPSHOT_ONLY、BROWSE_ONLY 与 raw-PK 兜底规则在源 DDL 无主键时按 keyless
存储，取代“keyless 不能作为 fallback”；manifest 每表条目的 canonical key policy 增加该取值。CanonicalizationManifest 的
`contract_version` 自 P5 收口 S2b 起记录 `3.2.0`，读取接受 `3.0.0`、`3.1.0`、`3.2.0`。DC29 不提升 storage projection version（当前为 `2`，由 P5 收口
S2a-F1 的负零规范化 `26560b2595` 从 `1` 提升）：此前能投影成功的表规范字节与内容摘要不因 DC29 改变，新路径只用于此前被拒绝的表；规则集版本随规则变化提升。

## 9. 验收标准

- Raw source 可从 SourcePackageArtifact 完整读取；Dolt export 明确是 canonical schema。
- source 仅改变已 `DROP_FROM_STORAGE` 列的值时，R4 canonical schema/content/storage-business digest 保持不变，且 `NO_CANONICAL_CHANGE` 无 Repository effect；R3 `business_content_digest` 若反映原始快照差异仍作为 provenance 保留，不能与 R4 canonical digest 混用。
- 新增/移除 ignored-column drop policy 改变 canonical 字段集合时进入 `STORAGE_BREAKING`/`MIGRATION_REQUIRED`，不得伪装成 comparison-only change。
- Missing/duplicate key、row loss、reserved gid、非法 no 全部 fail closed。
- `DDL_PRIMARY_KEY_OR_KEYLESS` 规则下源 DDL 无主键的表按 keyless 投影、写入并读回，重复行保留，读回后的行数与规范状态摘要与投影一致（DC29）。
- Pseudo gid 在重算、retry、Rust/Python 和 readback 后确定一致。
- 每次write成功都匹配operation commit、mandatory target CAS与requested/completed
  Repository verification；STRUCTURAL/FULL_SCAN时匹配相应manifest facts。
- 业务digest继续由Storage Projection/业务owner验证，不由Repository任一
  verification level替代。
- Attempt retry复用相同RepositoryImportArtifact ID和raw SHA；活跃期结束后
  full-row pin被释放。
- Projection version change 使用 alignment/fallback，不错误使用 native diff。
- Accepted Submission的SourcePackageArtifact保持durable；
  `NO_CANONICAL_CHANGE`输入不提升为submission durable。
- Backend durable manifest与package中的opaque manifest digest一致；Repository只
  解释table/schema/row-count。
- Backend/Repository artifact ID不互换；跨upload的media type、size和raw SHA保持
  exact一致。
- Repository成功result原样echo artifact ID、manifest digest、parent/ref和completed
  policies，Backend T3与checkpoint/durable manifest核对后才finalize。

## 10. 关联文档

- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [External Effect and Recovery](external-effect-and-recovery.md)
- [Repository Service](repository-service.md)
- [ADR 0004](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)
- [ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、[ADR 0019](../adr/0019-commit-canonical-metadata-authority.md)
  与 [P5 架构收口设计](../plans/p5-arch-closure-design.md)（`3.1.0`）
- [DX Cross-Phase Interface Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
