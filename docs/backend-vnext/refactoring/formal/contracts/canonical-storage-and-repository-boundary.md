# Canonical Storage and Repository Boundary Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 2、Phase 3、Slice 5A/5B 实现

Contract ID：`gateway-vnext.canonical-storage-and-repository-boundary`

Owner：Table Rules/Storage Projection（canonical content）；Repository Service（generic repository effect）

Semantic version：`2.0.0`

Storage projection version：`1`

## 1. Authority boundary

```text
Immutable SourcePackageArtifact (raw upload authority)
  -> parse + frozen table rules + storage projection
  -> CanonicalizationManifest + RepositoryImportArtifact
  -> Repository Service generic import/commit
  -> structural import result + immutable CommitId
```

SourcePackageArtifact 保存原始 bytes、provenance 和 replay authority。Dolt commit 保存 canonical business state，不保证复原原始 SQL schema、所有物理列或原始 DDL。Submit 成功时 source artifact retention 提升为 submission durable；读取原始输入必须回到该 artifact。

Source artifact digest、storage projection digest、canonical business digest、SnapshotManifest digest 和 Dolt commit hash 是不同语义域，不能互换。

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

每次 import 的 manifest 至少记录：contract/storage projection version，source artifact digest，ruleset ID/version/digest；每表 source/canonical schema digest、source/canonical row count、retained/structural/dropped columns+reason、canonical key、canonical content digest、optional ordering digest/ordered identity policy 与 gid range/count；以及 manifest digest。

Table Rules/Storage Projection owner拥有其语义。Repository Service只消费manifest中的
required table、schema和row count做structural check；不验证业务content/ordering
digest，也不得选择业务列、key、pseudo gid或ordered policy。

## 5. Artifact lifecycle

`SnapshotTableArtifact` 是 Preview 产生的 immutable full-row table facts。仅在尚未被接受的 current Preview 或 active SubmitAttempt 需要时持久 pin。AcceptSubmit T1 将 pin responsibility 从 Preview 原子转给 Attempt；历史 Preview 引用本身不继续 pin。Attempt 进入 `FINALIZED/ABORTED` 后释放 pin，artifact 转为可重算 cache material。第一版不长期保存重复 full-row archive。

长期审计/恢复权威为durable SourcePackageArtifact、accepted canonical Dolt commit、
CanonicalizationManifest和所请求level的verification evidence。需要重算未pin
full-row facts时，从source artifact按固定parser/ruleset contract重建。

Submit 从 exact Preview-bound SnapshotTableArtifact 开始，不重新解析 SQL。`RepositoryImportArtifact` 包含 canonical schema/rows 与 content digest；每个 Attempt 只构建一次并持久 checkpoint。Retry、takeover/reconcile 复用相同 ref/digest，不能重建后以新请求替换。

若Preview-bound canonical business digest与base相同，AcceptSubmit在Attempt前返回
`NO_CANONICAL_CHANGE`：不构建RepositoryImportArtifact、不提升source artifact
retention、不调用Repository。Attempt终态后RepositoryImportArtifact也解除durable
pin；accepted commit的长期authority由SourcePackageArtifact、
CanonicalizationManifest、所请求level的verification evidence与canonical Dolt
history共同提供。

## 6. Repository import、journal 与 readback

Repository Service通过public wire contract接收RepositoryImportArtifact，只执行
writer serialization、Dolt apply/commit、operation marker、target ref CAS、catalog/
stream和固定structural check。

Repository Service不提供`NONE | STRUCTURAL | FULL`或VerifyCommit。成功只表示：

1. upload size/raw SHA匹配；
2. 带matching operation marker的commit存在；
3. target ref指向该commit；
4. committed table set、schema和row count匹配manifest。

业务content/ordering digest在import前由Storage Projection owner计算和保存。业务
流程是否额外读取immutable commit做诊断或复核，由其owner决定，不成为Repository
Service通用verification状态。

RepositoryImportArtifact是Storage Projection owner的content contract；通用artifact
引用由Artifacts owner拥有。Repository Service只解释structural fields，其他
canonical fields语义仍由Storage Projection owner定义。

### 6.1 RepositoryImportArtifact v1 package

V1 media type为
`application/vnd.gateway.repository-import.v1+tar+zstd`。解压后必须恰有两个regular
file，顺序固定：

```text
manifest.json
replay.sql
```

禁止其他entry、absolute/traversal path、duplicate、link、device、FIFO和extended
filesystem metadata。`manifest.json`是UTF-8 JSON，至少向Repository Service提供
ordered table list和每表schema/row count。Storage Projection可以保存自身的
contract、ruleset、source/content/ordering digest，但这些字段的业务语义不由
Repository Service解释。Package传输完整性只使用ArtifactRef size/raw SHA-256。

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
- 每次write成功都匹配operation commit、target ref和manifest table/schema/row count。
- 业务digest继续由Storage Projection/业务owner验证，不转换成Repository
  verification level。
- Attempt retry 复用相同 RepositoryImportArtifact；活跃期结束后 full-row pin 被释放。
- Projection version change 使用 alignment/fallback，不错误使用 native diff。

## 10. 关联文档

- [Shared Canonical Encoding](shared-canonical-encoding.md)
- [External Effect and Recovery](external-effect-and-recovery.md)
- [Repository Service](repository-service.md)
- [ADR 0004](../adr/0004-raw-source-artifact-and-canonical-dolt-storage.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
