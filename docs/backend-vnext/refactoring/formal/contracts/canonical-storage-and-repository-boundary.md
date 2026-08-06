# Canonical Storage and Repository Boundary Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 2、Phase 3、Slice 5A/5B 实现

Contract ID：`gateway-vnext.canonical-storage-and-repository-boundary`

Owner：Table Rules/Storage Projection（canonical content）；Repository Service（generic repository effect）

Semantic version：`3.0.0`

Storage projection version：`1`

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

## 2. Storage 与 comparison projection

Storage projection 在 import 前决定 Dolt 长期保存的 canonical schema、physical key 与 structural fact。Comparison projection 在比较时负责跨版本 alignment、selected value columns、ordered semantics 和 records。二者来自相同 table-rules source，但具有不同 contract、DTO、version 和 cache identity。

列策略只允许：

| Policy | 语义 |
| --- | --- |
| `PERSIST_BUSINESS` | canonical business identity/value |
| `RETAIN_FOR_STRUCTURE` | 恢复顺序/结构所需，不一定参与普通 modified 判断 |
| `DROP_FROM_STORAGE` | 已证明不影响 identity、value、order、审计解释或恢复的波动列 |

只有 `DROP_FROM_STORAGE` 在写 Dolt 前删除；manifest 必须记录列、理由、规则版本和 source/canonical schema digest。

## 3. Key、行完整性与 ordered table

普通 canonical keyed table 必须验证 effective key 存在且 retained、tuple 非空、整表唯一，且 projection 前后 row count 相同。不得用 dedup、last-write-wins、覆盖或丢行满足主键。失败在 Preview 形成 typed blocker，在 Submit 的 Repository effect 前拒绝。Keyless/multiset 必须由 ruleset 显式分类，不能作为 fallback。

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

每次import的durable`CanonicalizationManifest`至少记录：contract/storage
projection version，source artifact digest，ruleset ID/version/digest；每表
source/canonical schema digest、source/canonical row count、
retained/structural/dropped columns+reason、canonical key、canonical content
digest、optional ordering digest/ordered identity policy与gid range/count；以及
manifest digest。

Table Rules/Storage Projection owner拥有其语义。Repository Service只消费manifest中的
required table、schema和row count做structural check；不验证业务content/ordering
digest，也不得选择业务列、key、pseudo gid或ordered policy。

Backend必须在临时Repository import package可能被删除前durable保存
CanonicalizationManifest。Repository package中的`manifest.json`只携带结构字段和
opaque`canonicalization_manifest_digest`；它不是完整业务manifest，也不取得业务
语义owner。

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

## 6. Repository import、journal 与 readback

Repository Service通过public wire contract接收RepositoryImportArtifact，执行writer
serialization、Dolt apply/commit、operation marker、mandatory commit CAS，以及caller
选择的`NONE | STRUCTURAL | FULL_SCAN` verification。默认`STRUCTURAL`；精确含义由
[Repository Service](repository-service.md)唯一拥有。

所有level都检查upload size/raw SHA、package safety、matching marker、expected parent
和target CAS。`NONE`只跳过catalog检查；`STRUCTURAL`比较table/schema/row count；
`FULL_SCAN`再以bounded batches读取全部user rows并验证type conversion与实际row
count。任何level都不计算business content/ordering digest或防篡改evidence。

业务content/ordering digest在import前由Storage Projection owner计算和保存。Caller
根据业务风险选择Repository verification level，并为低保障选择负责；Repository的
FULL_SCAN仍不能替代业务digest validation。

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
opaque关联值。完整contract、ruleset、source/content/ordering digest保存在Backend
durable CanonicalizationManifest，不复制到临时package。Package传输完整性只使用
minimal ArtifactRef的size/raw SHA-256。

`package_version`固定为integer `1`；`row_count`是非负integer。`tables`按canonical
table name bytes排序，table name唯一且不得含leading/trailing whitespace；`columns`保持DDL order且name唯一；
`primary_key`按key order引用已声明column。`sql_type`是bounded normalized physical
SQL type，`nullable`是boolean。Object unknown field、duplicate或invalid key
reference全部拒绝。`manifest.json`使用strict UTF-8 JSON，但不要求JCS，也不建立
package semantic/self digest。

`replay.sql`是受信Storage Projection生成的确定性snapshot replay，不是外部用户
提交的任意SQL。Repository Service将其限制在server-owned Repository/Dolt runtime
内执行，不建设完整SQL grammar或semantic package validator。若信任边界改变为
不可信上传者，必须重开ADR 0009。

## 7. Projection upgrade/schema alignment

每个 commit 记录 `storage_projection_version + ruleset_digest`。同版本可走 normal/native route；版本不同必须进入 schema-change alignment，禁用不安全 native data diff，按 compatible columns/effective key streaming fallback。无法安全 alignment 时明确 table-level degraded。

不回写/迁移整个历史。Key set 改变不得假设 native diff 正确；新规则所需而旧 commit 未保存的列不得从 Dolt 猜测，可从 durable SourcePackageArtifact 显式重算。Schema change source 标记为 `SOURCE_SCHEMA | STORAGE_PROJECTION_POLICY | BOTH`。

旧 Dolt repository 的迁移/兼容策略不由本文决定，必须作为独立 cutover gate。

## 8. Classification 与版本

Module public：是。Persisted：SourcePackageArtifact、manifests、RepositoryImportArtifact checkpoint 和 Dolt commit。Wire：artifact refs + Repository public contract + stream.

改变列 policy/key/ordered identity/canonical bytes 必须升级相应 storage projection、ruleset 或 canonical encoding version，并建立新 digest/cache identity。纯 Repository implementation 优化不得改变 canonical content。

## 9. 验收标准

- Raw source 可从 SourcePackageArtifact 完整读取；Dolt export 明确是 canonical schema。
- Dropped-column-only change 得到相同 canonical business digest，且 no-change Submit 无 effect。
- Missing/duplicate key、row loss、reserved gid、非法 no 全部 fail closed。
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
- [DX Cross-Phase Interface Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
