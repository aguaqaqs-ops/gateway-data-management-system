# Phase 2 Decision Ledger — Round 4–7

状态：**Draft / Active Interview Record**

配套指南：[interactive-design-session-guide.md](interactive-design-session-guide.md)

本文件是 Round 4–7 的唯一 Decision Ledger 正文位置。Decision ID 使用
`P2-R<round>-D<sequence>`；状态只能是 `ACCEPTED`、`REJECTED`、`DEFERRED`、
`OPEN` 或 `SUPERSEDED`。每项 decision 必须记录语义、理由、被拒方案、约束、
downstream impact、formal owner 和 reopen condition。被推翻的记录保留并标为
`SUPERSEDED`，不得删除或在主指南复制正文。

## Round 4 — Dolt ownership, registry and storage layout

### P2-R4-D01 — Preferred canonical SQL replay import candidate

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D01` |
| Topic | Preferred VersionedTableStore import provider candidate |
| Status | `ACCEPTED` |
| Decision | `CANONICAL_SQL_REPLAY` 是 Phase 2 首版默认优先的 versioned import provider candidate 和 correctness baseline。它消费由 Storage Projection 从 canonical schema/rows 确定性生成、带版本与 digest 的 RepositoryImportArtifact，不消费上传者原始 SQL，也不形成 arbitrary SQL endpoint。Repository-scoped `dolt sql -f` 是优先执行候选；CLI/sql-server 的最终 runtime 协调仍由 Round 4 裁决，production default 仍须通过 containerized Remote path、commit/ref、强制 full committed-ref readback、evidence persistence 和 cleanup 的 accepted measurement。其他 import provider 保留为显式 fallback/benchmark candidate。 |
| Rationale | 旧系统在相同真实业务数据和同机 provider matrix 中，SQL replay 在 small/medium/large 与 cold/warm profiles 均为最快 import 路线，并已作为 submit-finalize replay-only correctness path 使用。Repository-scoped replay 还避免要求一个 node-wide sql-server 注册成千上万个 repository。 |
| Rejected alternatives | 直接把 `LOAD_DATA`、Parquet 或 per-table CLI import 设为首版默认：现有同机真实数据证据持续较慢；直接执行上传者原始 SQL 或公开 generic SQL endpoint：违反 Repository Service 通用、安全和 canonical storage boundary；仅因旧 benchmark 数字直接声明 production 性能收益：旧结果未包含 Phase 2 强制 full readback。 |
| Constraints | Replay grammar 必须封闭并绑定 manifest table/schema/digest；禁止 database/user/grant、文件/网络访问、procedure 和 system mutation。Provider 成功不等于 operation VERIFIED；正常写仍须 commit/ref 后全量 readback匹配。Unknown effect 不得因脚本可重放而 blind replay。精确 SQL validation、subprocess limits 和 restricted identity 在 Round 8 固定。 |
| Downstream impact | 约束 RepositoryImportArtifact media/schema、Storage Projection generator、versioned import provider port、repository-scoped runtime、writer admission、fallback matrix、security negatives、container benchmark 和 conformance。 |
| Formal owner | Storage Projection RepositoryImportArtifact content contract；Repository Service versioned import/provider contract；Phase 2 measurement plan。 |
| Reopen condition | 同数据、同 correctness、同 containerized Remote/full-readback profile 的 accepted measurement 证明另一 provider 更合适，或 constrained replay 无法满足安全、类型 round-trip、streaming artifact size 或 concurrent pinned-read contract。 |

### P2-R4-D02 — Repository-scoped bounded Dolt runtime coordination

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D02` |
| Topic | Dolt CLI/sql-server ownership and activation at large repository count |
| Status | `ACCEPTED` |
| Decision | Repository Service 使用 repository-scoped、node-bounded `DoltRuntimeCoordinator`，不让一个长期 node-wide sql-server 注册全部 repository，也不为每个 repository 永久保留进程。Repository 没有 active sql-server 时，`CANONICAL_SQL_REPLAY` 可在其受控目录通过 offline `dolt sql -f` 执行；已有 active repository-scoped sql-server 时，同一 canonical replay 必须通过该 server 执行，禁止另一个 CLI 直接并发访问底层 repository。Runtime executor 在 operation 进入 PREPARED/effect execution 前持久记录，recovery 不得静默切换。不同 repository 可在 node budget 内并发激活；idle runtime 可回收，runtime cache/process state 不是 authority。 |
| Rationale | 数千至数万 repository 不应全部进入单 server catalog或对应永久进程；按活跃集合激活保留 repository 隔离和资源上限。双 executor 允许无 active server 时复用已验证的 CLI replay 快路径，又让已有 pinned reads 与 write 通过同一 Dolt owner 协调。 |
| Rejected alternatives | 一个 node-wide sql-server 加载全部目录：Dolt 2.1.11 不会热发现外部新增目录且无上万 database capacity evidence；每 repository 永久 sql-server：进程、连接和后台状态无界；所有写强制 offline CLI 并 drain readers：破坏长读可用性；CLI 与 active server 同时直写文件：ownership 不明确。 |
| Constraints | 同 repository 同时只能有一个 Dolt filesystem owner/executor mode；versioned writer serialization仍适用。Runtime acquire/release 必须受 deadline、cancellation、crash cleanup和fencing约束；精确 pool size、idle TTL、connection/process limits在Round 8/9测量后固定。Process restart只丢失runtime cache，不丢失registry/journal/repository evidence。 |
| Downstream impact | 新增 runtime coordinator/handle、repository-scoped server config/socket、executor evidence、admission、idle eviction、shutdown、concurrent pinned-read tests、process-crash tests和capacity profile。 |
| Formal owner | Repository Service Dolt runtime/storage infrastructure contract；Phase 2 deployment and measurement plan。 |
| Reopen condition | Dolt provider证据证明CLI与server executor无法保持相同effect/readback语义，或accepted capacity显示small-shard/node-wide server明显更安全有效。 |

### P2-R4-D03 — Single durable root with sharded repository layout

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D03` |
| Topic | Durable volume and repository directory layout |
| Status | `ACCEPTED` |
| Decision | Phase 2 每个 active Repository Service container 独占一个 trust-domain durable root；root内逻辑划分global registry、prefix-sharded repositories、artifacts、durable staging和quarantine，ephemeral scratch位于独立非备份路径。Repository目录使用server-derived、严格校验且不可由caller指定的storage key，并以固定前缀分片，避免上万repository集中在单目录。每个repository slot包含独立versioned、lazy current和control子边界。Public contract、日志和diagnostics不得返回这些路径。 |
| Rationale | 单root保持首版部署、restore closure和active-owner边界简单；逻辑隔离与quota/admission足以区分容量，前缀分片避免大目录扩张。独立scratch防止可重建临时数据污染备份。 |
| Rejected alternatives | State/artifact双durable volume：首版增加跨volume publish/backup/recovery；每组件独立volume：配置与恢复矩阵过大；caller提供任意repository path：违反path concealment和ownership；平铺所有repository目录：规模扩张下目录操作与运维不佳。 |
| Constraints | Exact目录名和分片宽度是实现默认，但storage layout version必须持久化。Artifacts/staging必须有独立quota和retention，不能耗尽root后破坏registry/journal durability。禁止symlink/path traversal和跨root引用。 |
| Downstream impact | 约束settings、Compose volume、path resolver、registry schema、repository create/delete、artifact publish、quota、backup manifest、reconciliation和filesystem tests。 |
| Formal owner | Repository Service storage layout/deployment contract；Phase 2 runbook。 |
| Reopen condition | Accepted capacity/failure evidence要求artifact独立故障域或external object storage，或底层volume不支持所需atomic publish/backup机制。 |

### P2-R4-D04 — Global registry with per-repository control authority

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D04` |
| Topic | Registry, journal and current metadata topology |
| Status | `ACCEPTED` |
| Decision | 技术状态采用分层SQLite authority。Global registry只保存RepositoryId、lifecycle、layout/format version、内部storage key及create/delete lifecycle/idempotency。每个repository的独立control SQLite保存versioned async operation journal、async idempotency result、lease/fencing和recovery evidence。CurrentTableStore的catalog/table generation及同步mutation idempotency result保存在该repository的current SQLite中，与current data mutation在同一transaction提交。Dolt commit/ref是versioned effect evidence，但不能替代operation journal和VERIFIED readback evidence。JSON/sidecar marker只可作为filesystem reconciliation evidence，不是第二metadata authority。 |
| Rationale | Global registry提供唯一身份和lifecycle入口；per-repository control避免所有普通operation共享一个global SQLite writer/failure domain，并使repository aggregate可独立备份。Current generation/idempotency留在data transaction内满足已确认原子性。 |
| Rejected alternatives | 所有metadata集中global SQLite：形成node-wide writer和更大故障域；只用per-repository sidecar并扫描重建registry：无法可靠保存身份、create/delete和tombstone；把current generation放入control DB：无法与current rows原子提交；仅以Dolt ref推断operation outcome：缺少PREPARED/unknown/readback evidence。 |
| Constraints | Global与per-repository DB之间不声明跨SQLite transaction；create/delete和crash recovery依赖显式lifecycle/evidence reconciliation。SQLite schema version与migration必须fail closed。Secrets不进入任何aggregate metadata。精确journal/lease/idempotency schema在Round 5固定。 |
| Downstream impact | 约束SQLite ownership、transaction boundaries、startup scan、create/delete、operation query、backup closure、migration、concurrency和fault injection。 |
| Formal owner | Repository registry/storage contract；Repository operation/effect contract；CurrentTableStore transaction contract。 |
| Reopen condition | Accepted metadata load证明per-repository DB数量不可管理，或需要shared multi-node control plane/sharding并完成distributed ownership设计。 |

### P2-R4-D05 — Registry-authoritative startup reconciliation and explicit format upgrade

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D05` |
| Topic | Repository creation publication, startup reconciliation and format migration |
| Status | `ACCEPTED` |
| Decision | Global registry是repository identity/lifecycle authority，filesystem是必须核对的evidence。Create先持久化`PROVISIONING`及目标storage key，在durable staging初始化并验证aggregate，再发布为`READY`；跨SQLite/filesystem的crash由lifecycle和marker继续或收口。未登记目录禁止自动接管，进入quarantine/operator attention；已登记但目录缺失、损坏或format不兼容只使对应repository unavailable。Global registry不可读、Dolt runtime identity不匹配或service layout为未知新major时服务整体不ready。普通startup不自动执行Dolt/storage/SQLite format migration；upgrade必须经过兼容检查、backup、显式operator action、验证和rollback gate。 |
| Rationale | Registry authority防止旧库、残留staging或植入目录被误注册；per-repository degradation保持多项目故障隔离。显式upgrade避免启动时不可逆批量迁移数千repository。 |
| Rejected alternatives | 启动扫描并自动收编目录：身份、授权和tombstone不可靠；任一repository异常阻止全服务：故障域过大；启动自动升级全部repository：不可控停机且难回滚；发现不一致后静默删除：丢失恢复证据。 |
| Constraints | `PROVISIONING/READY/unavailable`是storage lifecycle概念，不替代Round 5 operation states或Round 6 failure taxonomy。Quarantine不得自动删除或对普通caller暴露path。Exact migration batches、resume和rollback在Dolt upgrade/runbook owning round固定。 |
| Downstream impact | 约束CreateRepository executor、registry schema、staging publish、readiness、per-repository availability、startup reconciler、operator tooling、upgrade tests和crash matrix。 |
| Formal owner | Repository lifecycle/registry/storage contract；Repository Service deployment and upgrade runbook。 |
| Reopen condition | Provider获得可证明atomic create/publish primitive，或future shared control plane成为identity authority并定义目录adoption协议。 |

### P2-R4-D06 — Repository-aggregate quiescent backup and restore boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R4-D06` |
| Topic | Minimum backup/restore unit |
| Status | `ACCEPTED` |
| Decision | Repository aggregate是语义restore unit；Phase 2首版只保证repository-quiescent backup。Backup admission暂停该repository的mutation/GC并等待或拒绝nonterminal effect，随后捕获global registry record、versioned Dolt、已物化current SQLite、per-repository control及retention内仍须有效的artifact/evidence。Credentials、cache和ephemeral scratch排除。Restore保留RepositoryId和resource identities，在目标存在同ID或不兼容format时fail closed；full-service disaster backup是global registry加多个aggregate backup的组合。共同捕获Dolt/current是运维closure，不声明两侧内容一致或同一业务snapshot。 |
| Rationale | Repository级单元支持上万项目的隔离备份、恢复和未来sharding，又避免首版用active-operation online snapshot提前承担journal/GC跨组件crash matrix。保留公开artifact/evidence防止restore后资源ID失效。 |
| Rejected alternatives | 只支持整服务停机/root backup：项目数增长后停机和恢复粒度过粗；首版active-operation online backup：提前扩大Round 5–7协调复杂度；只备份Dolt：丢失registry/current/journal/idempotency和公开artifact；restore时自动换RepositoryId：破坏外部引用。 |
| Constraints | Quiescent不等于Dolt/current业务一致；只保证各组件在backup manifest列出的合法状态。Exact drain timeout、SQLite checkpoint、Dolt flush/backup mechanism、artifact retention、encryption和backup manifest在Round 7/8/9固定。Backup失败不得留下可恢复成功标记。 |
| Downstream impact | 约束backup manifest、repository admission、runtime drain、component inventory、restore collision/validation、operator API、runbook和smoke/failure tests。 |
| Formal owner | Repository Service backup/restore and storage contracts；Round 7 retention/GC design；deployment runbook。 |
| Reopen condition | Accepted RPO/RTO要求non-quiescent online backup、cross-node restore或partial component restore，并完成相应consistency/recovery design。 |

## Round 5 — Write journal, idempotency, lease and CAS

### P2-R5-D01 — Monotonic effect journal with durable effect-start evidence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R5-D01` |
| Topic | Repository effect journal and publication boundary |
| Status | `ACCEPTED` |
| Decision | Versioned async operation 的正式状态保持 `PREPARED -> APPLIED -> VERIFIED`；per-repository control SQLite 另在实际调用 Dolt 或实施 ref effect 前持久化内部 `EFFECT_STARTED` evidence。该 marker 不是第四个公开成功状态，而是区分尚未尝试 effect 与 effect outcome 未知的 durable boundary。`PREPARED` 固定 RepositoryOperationId、idempotency namespace/key、带版本的 canonical request digest、repository/store/ref/table binding、precondition 和 artifact digest（如有）；`APPLIED` 固定 executor/fencing token、effect timestamp 及 exact before/after CommitId/ref evidence；`VERIFIED` 固定 committed-ref SnapshotManifest 或 ref verification evidence。状态只能单调前进，既有 transition/evidence 不得就地抹除。Import 按已记录 executor 完成 canonical replay、commit/ref publication 后进入 APPLIED，再从 committed ref 全量 readback 匹配才进入 VERIFIED；readback 不匹配时保留已发生 effect 和占用，交由 reconciliation，不盲目回滚或重放。 |
| Rationale | Formal authority 要求区分 accepted request、repository effect 与 business finalize，并禁止把 timeout、disconnect 或 lease expiry 当作未执行。单独的 effect-start evidence 关闭“调用外部 effect 前后崩溃”的关键观测缺口，同时不改变正式三阶段语义。 |
| Rejected alternatives | 只保存 PREPARED/APPLIED/VERIFIED：effect 调用窗口崩溃时缺少已开始证据；从 Dolt log/ref 临时推导全部状态：无法恢复 request digest、幂等碰撞、未形成 commit 的尝试或 Current effect；provider 返回成功即 VERIFIED：绕过强制 committed-ref readback。 |
| Constraints | `EFFECT_STARTED` 后没有足够 evidence 时必须分类为 UNKNOWN；accepted operation 不得换 key、换等价 artifact 或静默切换 executor重放。APPLIED 与 VERIFIED evidence 必须可供 QueryOperation、reconciliation、审计和 retention/GC 使用。精确 failure taxonomy 与逐 crash-point 动作由 Round 6 固定。 |
| Downstream impact | 约束 control SQLite schema、operation API、executor protocol、Dolt import/ref adapter、readback manifest、reconciler、fault injection 和 observability。 |
| Formal owner | Repository operation/effect contract；external-effect-and-recovery contract。 |
| Reopen condition | 底层 provider 提供可证明覆盖 request acceptance、effect、verification 的单一 durable transaction，或正式 recovery authority 改变三阶段 publication 语义。 |

### P2-R5-D02 — Action-scoped caller idempotency with permanent compact tombstone

| 字段 | 值 |
| --- | --- |
| ID | `P2-R5-D02` |
| Topic | Idempotency namespace, digest collision and retention semantics |
| Status | `ACCEPTED` |
| Decision | 普通 mutation 的 idempotency uniqueness scope 为 `(CallerIdentity, RepositoryId, Action, IdempotencyKey)`；尚无 RepositoryId 的 CreateRepository 使用 `(CallerIdentity, Action, IdempotencyKey)`。同 scope、同 canonical request digest 返回原 operation、原结果或其当前状态；同 scope、不同 digest 返回 idempotency conflict。Digest 输入包括 digest schema version、canonical semantic request、repository/store/table/ref binding、expected generation/commit 等 precondition 与 artifact digest；deadline、correlation ID、认证 token、retry count 和 transport headers 不进入 digest。历史 payload/evidence 可按后续 retention policy 压缩，但 compact tombstone 必须持续保留 key hash、request digest、operation/result identity 与 effect classification，过期 key 不得静默解释为新 mutation。Current 小型同步 mutation 的相同语义在 current SQLite 内与数据 effect 原子实现。 |
| Rationale | Action 与 caller scope 避免无关操作互相碰撞，同时允许同一逻辑调用者安全取回丢失响应。Versioned semantic digest 防止仅比较 key 却接受不同请求；compact tombstone 在控制长期存储成本的同时避免迟到重试制造重复 effect。 |
| Rejected alternatives | 只使用 `(RepositoryId, IdempotencyKey)`：不同 action 和 caller 产生不必要冲突；仅比较 key、不比较 digest：允许不同 payload 冒充重试；TTL 到期后自动复用 key：可能把迟到的 accepted request 解释为新 effect；把 transport/auth 元数据纳入 digest：正常重试会因非语义字段变化而冲突。 |
| Constraints | CallerIdentity 必须是认证后稳定 service principal identity，不得取可伪造显示名。Digest encoding/version migration 必须确定、可测试且 fail closed。Exact full-payload/evidence retention、compaction 和 GC 周期由 Round 7 固定，但不得删除防止 key 再利用所需的 compact tombstone。 |
| Downstream impact | 约束请求 envelope、SQLite unique keys、canonical encoding、operation/result lookup、auth identity、conflict taxonomy、retention 和 replay/conformance tests。 |
| Formal owner | Repository API/idempotency contract；shared canonical encoding；Repository Service retention policy。 |
| Reopen condition | Future trust model 无法提供稳定 CallerIdentity，或引入跨 trust-domain/global operation identity 并重新定义安全的 namespace 与 migration。 |

### P2-R5-D03 — Store-scoped writer lease with monotonic fencing and reconciled takeover

| 字段 | 值 |
| --- | --- |
| ID | `P2-R5-D03` |
| Topic | Writer lease acquisition, renewal, fencing, expiry and takeover |
| Status | `ACCEPTED` |
| Decision | Worker execution claim 与 repository writer lease 是不同机制。Async writer lease 以 `(RepositoryId, StoreKind)` 为 scope，持久化 owner operation、单调递增 fencing token、acquired/renewed/expiry timestamps；effect 前及 commit/ref/journal evidence publication 前均校验 token。Lease expiry、heartbeat timeout、worker loss 或 HTTP disconnect 只触发 RECONCILING，不自动授权下一 writer。Takeover 必须先确保旧 Dolt runtime 已停止、drain 或被目录 ownership 隔离，再检查 journal 与实际 store evidence：只有明确 NOT_APPLIED 才可继续或重放，APPLIED 转 verification，UNKNOWN 保持占用并调查。Dolt 与 Current 不同 StoreKind 可并发，同 store writer 串行。Current 小型同步 mutation 仅使用短 SQLite transaction、generation CAS 和数据库 writer lock；异步 Current replace/bulk 才获取 Current store lease。 |
| Rationale | TTL lock 无法阻止暂停后恢复的旧 worker继续写。Durable fencing token 加 runtime isolation 将调度 ownership 与实际 filesystem owner 对齐，并保留已确认的 per-store concurrency；同步小 mutation 不承担不必要的长 lease 成本。 |
| Rejected alternatives | Lease 到期立即由新 writer 接管：可能形成双 writer；只用进程内 mutex：重启或多副本后失效；把 worker claim 当作 writer lease：无法覆盖 effect execution 与 executor lifecycle；所有 Current mutation 都取长 lease：降低小型 CAS mutation 并发且无额外 correctness 收益。 |
| Constraints | Dolt 不原生校验 fencing token，DoltRuntimeCoordinator 必须在新 owner写入前完成旧 executor 隔离；仅在应用层重新读取 token 而不隔离旧 runtime 不足以 fencing。Lease clock、renew interval、takeover timeout 和 admission budget 在 Round 8/9 通过测量固定；未知 effect 的占用释放规则由 Round 6 收口。 |
| Downstream impact | 约束 control schema、worker runtime、runtime coordinator、SQLite transaction path、admission、shutdown/restart、metrics 和 concurrent/crash tests。 |
| Formal owner | Repository concurrency and external-effect recovery contract；Dolt runtime ownership contract。 |
| Reopen condition | Dolt provider 支持可持久验证的原生 fencing/transaction token，或部署拓扑引入 shared multi-node coordinator 并提供更强等价保证。 |

### P2-R5-D04 — Journaled optimistic ref mutation without force paths

| 字段 | 值 |
| --- | --- |
| ID | `P2-R5-D04` |
| Topic | Ref create, compare-and-set, immutable name and delete semantics |
| Status | `ACCEPTED` |
| Decision | `CreateRef` 的 target 必须是同一 repository 内现有 CommitId，名称已存在则冲突。`CreateImmutableRef` 还必须在删除后永久保留 name tombstone，禁止同名重新绑定。`CompareAndSetRef` 必须给出 exact expected current commit；ref 缺失或 expected stale 均冲突。实际 ref 已等于 target 时，只有同一 idempotency/journal evidence 匹配才返回原请求成功，禁止仅凭 ref 相等推断。`DeleteRef` 必须给出 expected commit 与 expected ref kind；protected/internal ref拒绝删除；mutable name 删除后可重新创建，immutable name 不可。所有 ref mutation 均写 journal，保存 before/after/current-ref verification evidence；响应丢失后只能使用原 idempotency key取回结果。不存在 unconditional update、force delete 或 force rebind public path。 |
| Rationale | Exact precondition 防止 lost update；journal evidence 区分“本请求成功”与其他请求碰巧得到相同 target。永久 immutable-name tombstone 维持不可变外部引用含义，protected/internal 拒绝规则保护 Repository Service 自身 recovery refs。 |
| Rejected alternatives | actual 等于 target 即统一成功：错误归因并掩盖并发 mutation；允许 unconditional/force ref mutation：绕过 optimistic concurrency；删除 immutable ref 后允许重用名称：历史外部引用可被重绑定；只返回 provider boolean、不保存 evidence：丢失响应后无法确定 outcome。 |
| Constraints | Ref kind、protected/internal classification 与 tombstone 必须是 durable authority，不从名称约定临时猜测。Ref VERIFIED 依据 request/before/after/current-ref evidence，不执行无关的全表 readback。Stable conflict/error code 和 operator-only repair boundary 在 Round 6/9 固定。 |
| Downstream impact | 约束 ref API、ref registry/tombstone schema、Dolt adapter、journal verification、authorization、error mapping、concurrency 和 retry tests。 |
| Formal owner | Repository ref and optimistic concurrency contract；repository authorization policy。 |
| Reopen condition | Provider 提供具备等价 idempotency evidence 的原子 named-ref primitive，或正式 contract 改变 immutable ref 的名称生命周期。 |

### P2-R5-D05 — Transaction-local sync Current recovery and effect-marked async bulk recovery

| 字段 | 值 |
| --- | --- |
| ID | `P2-R5-D05` |
| Topic | CurrentTableStore mutation effect, verification and crash recovery |
| Status | `ACCEPTED` |
| Decision | Current 小型同步 row/field/table mutation 不强制创建异步 RepositoryOperationId；单个 current SQLite transaction 原子提交 data/schema effect、resulting generation、canonical request digest、idempotency result 及 applied/verified evidence。Commit 前 crash 为 NOT_APPLIED；commit 后即使响应丢失，也能用原 key 取回确定结果。其 verification 使用 constraints、affected-row/result evidence 与 resulting generation，不要求整表 readback。异步整表 replace/bulk 在 per-repository control journal 先写 PREPARED/EFFECT_STARTED；随后 current SQLite transaction 原子提交 replacement/bulk effect、new generation、operation/idempotency/request-digest applied marker 以及 row count/content digest 等 evidence。若 Current commit 后、control journal 推进前 crash，reconciler 读取 Current marker 判定 APPLIED，再核验 schema、generation、row count/content digest 后推进 VERIFIED。Control 与 Current SQLite 之间不声明跨数据库原子事务。 |
| Rationale | SQLite transaction 为同步 mutation 提供明确、低成本的 effect boundary；把 idempotency result 与数据放在同一 transaction 可消除响应丢失歧义。Bulk operation 跨 control/current DB 时，Current 内的 effect marker 是识别“数据已提交但 journal 未推进”的必要证据。 |
| Rejected alternatives | 全部 Current mutation 复用 Dolt full-readback journal：成本高且忽略 SQLite transaction boundary；只在 control journal 保存 applied marker：Current commit 与 journal 更新之间仍有未知窗口；同步请求另建独立 control transaction：无法与 rows/generation/idempotency 原子提交；Current 与 control 使用分布式 transaction：首版复杂度与运行依赖不合理。 |
| Constraints | 同步 mutation 仍必须提供 expected generation 和 idempotency key；不提供 force overwrite。Async applied marker 必须由 Repository Service 保留且不可被普通 table API修改。Content digest 的 canonical encoding 必须版本化；精确 bulk threshold、streaming/chunk strategy 和 large verification budget 在 Round 8 固定，crash classification/action 在 Round 6 固定。 |
| Downstream impact | 约束 Current SQLite schema、sync response、bulk operation API、generation CAS、digest implementation、reconciler、retention、performance profiles 和 transaction fault injection。 |
| Formal owner | CurrentTableStore mutation/transaction contract；Repository operation/effect contract。 |
| Reopen condition | Current provider 不再提供满足要求的原子 local transaction，或 workload 证明必须引入跨数据库 transaction/shared operation store 才能满足 recovery objective。 |

## Round 6 — Failure, unknown outcome and reconciliation

### P2-R6-D01 — Separate operation, journal, effect and typed failure dimensions

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D01` |
| Topic | Caller-visible operation status and FailureDescriptor taxonomy |
| Status | `ACCEPTED` |
| Decision | RepositoryOperationStatus 使用 `ACCEPTED/RUNNING/RECONCILING/SUCCEEDED/FAILED/CANCELLED/ATTENTION_REQUIRED`，并与 journal phase、effect classification、cleanup state 和 FailureDescriptor 分字段表达。SUCCEEDED 只对应 VERIFIED；FAILED 只用于已证明 `NONE/NOT_APPLIED` 且自动处理终止；CANCELLED 同样要求 `NONE/NOT_APPLIED`；ATTENTION_REQUIRED 是可继续修复的 operational parking，不证明无 effect，也不释放 writer occupancy。Repository phase 固定为 `ACCEPT/PREPARE/EXECUTE/PUBLISH/VERIFY/RECONCILE/CLEANUP`。接受前 rejection 返回 typed problem response且不创建operation；接受后 failure由GetOperation representation承载，查询已存在operation本身不是HTTP失败；Current同步mutation直接返回typed failure并把确定结果绑定原idempotency key。Repository Service维护versioned stable code与typed details，至少覆盖request invalid、idempotency conflict、repository readiness/not-found、generation/ref/name/protected conflict、artifact/import rejection、dependency/capacity failure、effect unknown、readback integrity、recovery attention和internal invariant；`retryable`如保留只从recovery派生。 |
| Rationale | Operation调度状态、Repository effect事实和调用方恢复动作不是同一维度。分离后才能在UNKNOWN/APPLIED时阻止legacy式FAILED_FINAL或retryable boolean错误终结effect，并让同步、异步和HTTP transport共享同一typed failure语义。 |
| Rejected alternatives | 仅用成功/失败与retryable boolean：无法表达unknown effect；仅依赖HTTP status/异常文本：响应丢失和异步执行后不可恢复；把ATTENTION_REQUIRED当作无effect终态：会错误释放占用。 |
| Constraints | FailureDescriptor公共category/recovery/effect枚举沿用formal authority；stable code、phase和details由Repository use case owner版本化。认证类code在Round 8细化。Operation terminal status不得被业务侧直接解释为T3业务终局。 |
| Downstream impact | 约束wire schema、OpenAPI/SDK、GetOperation、problem response、SQLite operation representation、client recovery、error fixtures和compatibility tests。 |
| Formal owner | Repository Service API/operation contract；Shared Kernel FailureDescriptor仅拥有公共维度。 |
| Reopen condition | Formal FailureDescriptor维度或Repository operation lifecycle发生breaking change，并提供跨persisted/wire状态迁移方案。 |

### P2-R6-D02 — Evidence-first crash classification matrix

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D02` |
| Topic | Crash-point classification and allowed recovery action |
| Status | `ACCEPTED` |
| Decision | 请求未accepted为NONE；PREPARED但无EFFECT_STARTED且已证明无executor可继续时为NOT_APPLIED；EFFECT_STARTED后缺少充分store evidence默认为UNKNOWN。Provider错误、exit code、HTTP code、timeout或worker消失不能单独证明NOT_APPLIED。只有operation-scoped internal staging effect、target未发布且旧executor已fenced时，请求target effect才可判NOT_APPLIED并单独清理staging；target commit/ref与operation identity、request/artifact digest、binding和executor evidence精确匹配，或Current SQLite存在匹配的committed effect marker时，可从store evidence重建APPLIED。APPLIED后只补journal/readback/verification；VERIFIED后丢失响应返回原结果。Full readback mismatch保持APPLIED并记录INTEGRITY_FAILURE/OPERATOR_INTERVENTION，禁止重放。无法唯一归因的orphan commit/ref不得自动关联operation。 |
| Rationale | 固定矩阵把每个允许动作绑定到可验证evidence，而不是绑定异常类型，覆盖request、Dolt、Current、journal和response各持久边界的crash window。 |
| Rejected alternatives | Provider报错或超时默认NOT_APPLIED：可能重复effect；所有异常永久UNKNOWN：放弃精确marker/ref支持的自动恢复；通过猜测相似digest或时间窗口关联orphan：可能把他人effect归错请求。 |
| Constraints | Reconciler只能推进evidence已证明的状态，不能制造成功证据。NOT_APPLIED还必须证明旧请求已停止且不会再应用。Internal staging与target publication的边界必须持久、可审计；逐fault injection场景必须断言journal、store、occupancy与下一动作。 |
| Downstream impact | 约束Dolt executor、Current marker、journal repair、recovery state machine、fault injection、provider error handling和conformance matrix。 |
| Formal owner | External-effect-and-recovery contract；Repository provider evidence contract。 |
| Reopen condition | Provider新增可证明覆盖effect attempt/outcome的原子事务或原生operation token，并通过crash conformance替代现有evidence组合。 |

### P2-R6-D03 — Repository-owned bounded reconciliation and store-scoped isolation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D03` |
| Topic | Reconciliation ownership, scheduling and failure domain |
| Status | `ACCEPTED` |
| Decision | Repository Service是T2 journal/store evidence reconciler的唯一owner；Business Operation Runtime只能查询Repository operation/evidence，不直接读取Dolt目录推断outcome。Accepted worker、lease takeover、service restart、bounded periodic scan和operator recheck均可触发同一reconciler。Startup按global registry进行有界、分片、增量的per-repository control scan，不一次加载全部Dolt repository；同一operation只有一个reconciliation claim并服从store lease/fencing。UNKNOWN默认阻塞相同`(RepositoryId, StoreKind)`的后续mutation，不阻塞其他repository或同repository另一StoreKind；storage健康时，独立有效的immutable pinned reads可继续。READBACK_INTEGRITY_MISMATCH或store corruption使受影响StoreKind unavailable，另一StoreKind保持可用。单repository故障不使全服务unready。自动reconciliation耗尽有界策略后进入ATTENTION_REQUIRED，但保留原effect与occupancy。 |
| Rationale | Evidence owner与业务owner分离避免上层复制Dolt/SQLite恢复逻辑；store-scoped隔离与已确认writer scope一致，并防止一个项目的unknown effect拖垮所有repository。 |
| Rejected alternatives | 业务worker自行检查store并reconcile：破坏通用Repository边界；任意UNKNOWN全局停服：故障域过大；不加claim让多个reconciler并发修复：可能竞争journal和runtime ownership。 |
| Constraints | Periodic scan index/cache不是第二authority，必须可从registry和control DB重建。UNKNOWN lane解除只能依据本round accepted evidence规则。Exact scan budget、backoff、attention threshold和readiness metrics在Round 9固定。 |
| Downstream impact | 约束reconciler component、startup流程、registry enumeration、admission、repository availability、GetOperation、business client和large-repository-count tests。 |
| Formal owner | Repository Service recovery/runtime contract；deployment readiness contract。 |
| Reopen condition | Future shared multi-node control plane接管T2 evidence ownership，或accepted capacity证明per-repository incremental scan不能满足恢复目标并引入新的durable index authority。 |

### P2-R6-D04 — Durable effects outlive client cancellation and permit only evidence-gated repair

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D04` |
| Topic | Timeout, disconnect, cancellation, retry and operator repair |
| Status | `ACCEPTED` |
| Decision | Acceptance前deadline/cancel返回NONE且不创建durable operation；acceptance后客户端timeout、disconnect或停止polling不取消operation，caller以原operation ID/idempotency key继续查询。Phase 2 v1不向普通caller提供CancelRepositoryOperation mutation endpoint。内部cancel只有在effect未开始、executor已停止且Repository authority证明NOT_APPLIED时才能终止为CANCELLED；EFFECT_STARTED后的cancel request只能作为请求记录，operation仍须reconcile。自动retry只允许acceptance前transient work、APPLIED后的readback/verification、cleanup，以及explicit NOT_APPLIED后以原key/digest/artifact重试原effect；UNKNOWN不得retry，也不得换key、artifact、target或precondition。Operator repair首版只允许InspectOperationEvidence、ResumeReconciliation、ResumeVerification，以及持有系统签发NOT_APPLIED proof时重试原effect；不提供MarkVerified、ForceNotApplied、强制释放occupancy或修改原binding。 |
| Rationale | Durable effect必须独立于transport lifetime。把repair限制为向前验证或有proof的原请求重试，能提供人工恢复入口而不允许operator伪造store事实。 |
| Rejected alternatives | Accepted后允许caller随时取消并释放lease：可能遗留已发生effect；UNKNOWN自动retry：可能重复写；operator直接改journal outcome或force unlock：制造与store不一致的evidence。 |
| Constraints | NOT_APPLIED proof必须绑定operation、effect attempt、fencing generation和evidence snapshot，且只能消费于同一原请求。Operator action的认证、双重确认、reason和审计强度在Round 8/9固定，但不得削弱本decision的动作闭包。 |
| Downstream impact | 约束client deadline语义、worker cancellation、retry scheduler、operator API、proof token、authorization actions、audit和timeout/disconnect tests。 |
| Formal owner | Repository operation/recovery contract；operator repair contract。 |
| Reopen condition | Future provider支持真正可撤销的原子effect，或产品明确要求caller cancellation并完成已发生effect的补偿语义设计。 |

### P2-R6-D05 — Cleanup state is orthogonal to effect truth and preserves recovery evidence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D05` |
| Topic | Cleanup precedence, stale staging, quarantine and audit evidence |
| Status | `ACCEPTED` |
| Decision | Operation独立维护`NOT_REQUIRED/PENDING/COMPLETE/FAILED_ATTENTION` cleanup state；cleanup failure不得覆盖或降级已证明的effect classification。VERIFIED operation即使非结果性临时资源清理失败仍保持SUCCEEDED，并暴露cleanup attention。UNKNOWN/APPLIED时禁止删除可能用于归因、readback或恢复的artifact、staging ref/commit、request manifest、journal/effect marker；明确NOT_APPLIED或完成VERIFIED后才按资源类别进入安全cleanup。Startup发现stale staging时，只有证明无registry、journal、operation或artifact引用后才可自动清理，否则quarantine。Cleanup failure可触发repository/store admission restriction以保护durability，但不能触发effect replay。Append-only audit evidence至少记录operation/journal transition、effect classification变化、request/artifact/evidence digest、executor/fencing、recovery action/reason、caller/operator identity、cleanup/quarantine结果及sanitized diagnostic refs；禁止记录raw rows、secret、token或内部path。 |
| Rationale | Cleanup是资源生命周期，不是effect事实。正交建模既避免清理失败诱发重复写，也避免restart误删unknown outcome所需的唯一证据。 |
| Rejected alternatives | Cleanup失败把operation改成普通FAILED：掩盖已成功effect；restart直接删除所有staging：破坏recovery；UNKNOWN时先清理再判断：消灭权威evidence。 |
| Constraints | VERIFIED只允许忽略不影响已发布结果完整性的cleanup；若待清理对象仍是公开结果或verification依赖，则不能先标VERIFIED。Grace period、retention、GC计划与audit sink寿命在Round 7/9固定；disk watermark和admission阈值在Round 8/9固定。 |
| Downstream impact | 约束operation schema、staging manager、startup reconciler、artifact refs、quarantine、admission、audit/redaction和cleanup crash tests。 |
| Formal owner | Repository cleanup/recovery contract；Round 7 resource lifecycle；Round 9 audit/operations contract。 |
| Reopen condition | 底层storage提供transactional publish-and-cleanup且可证明消除所有staging/evidence窗口，或结果artifact生命周期被重新定义。 |

### P2-R6-D06 — Deterministic private operation ref for versioned effect attribution

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D06` |
| Topic | Unique attribution of a committed Dolt effect to one operation |
| Status | `ACCEPTED` |
| Decision | 每个versioned import在PREPARED时生成并持久化server-derived、caller不可指定的OperationRefKey，并在Repository Service私有且不可枚举的operation/staging ref上执行canonical replay和commit，使commit与internal ref推进形成provider durable boundary。Commit metadata或等价provider marker保存版本化correlation evidence，至少绑定RepositoryOperationId内部编码、request/artifact digest、target binding digest与fencing token；control journal保存operation ref、result commit和target before/after evidence。Target ref仍通过已确认CAS发布。Recovery必须交叉核对journal mapping、internal ref、commit marker/digest和target ref；不一致进入integrity attention。Internal ref只在VERIFIED且满足cleanup/retention条件后删除。 |
| Rationale | Deterministic operation ref关闭“commit成功、APPLIED journal尚未写入即crash”的归因窗口，不需要扫描history猜测，也让orphan与目标publication effect可以分开判断。 |
| Rejected alternatives | 只依赖control journal：journal publication前crash留下无法唯一归因commit；按时间/content扫描history：可能关联错误operation；将public target ref直接作为唯一working ref：中间commit与target publication边界不清。 |
| Constraints | Internal ref namespace、OperationRefKey和correlation encoding不得暴露path或允许caller碰撞；provider若不能可靠承载commit metadata，必须提供经过crash conformance的等价durable marker。Marker不能替代control journal或full readback。 |
| Downstream impact | 约束Dolt import protocol、ref namespace、commit metadata、journal schema、cleanup/GC、tamper detection、recovery tests和provider feasibility gate。 |
| Formal owner | Repository versioned-write/effect evidence contract；Dolt provider adapter contract。 |
| Reopen condition | Dolt提供原生、可查询且具备同等crash原子性的operation token，或accepted provider spike证明operation ref无法满足所需归因语义。 |

### P2-R6-D07 — Fail-closed on missing, corrupt or contradictory recovery authority

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D07` |
| Topic | Control journal loss and journal/store evidence contradiction |
| Status | `ACCEPTED` |
| Decision | Per-repository control SQLite缺失、损坏、schema不兼容或无法通过integrity validation时，受影响repository fail closed为unavailable；不得仅从Dolt/current data自动重建operation authority，只能通过完整repository aggregate restore或受控operator evidence-preserving repair恢复。Journal与store evidence矛盾时不设置任一方自动获胜规则：journal result commit与internal ref不同、Current effect marker digest与journal不同、VERIFIED但必要commit/readback evidence缺失等均为`INTEGRITY_FAILURE/OPERATOR_INTERVENTION`，保留冲突双方evidence并quarantine受影响StoreKind，停止其普通读写与cleanup；另一StoreKind和其他repository继续运行。绕过Repository Service直接修改Dolt、SQLite或durable root均属unsupported out-of-band mutation，发现后按integrity failure处理。 |
| Rationale | Journal拥有request/idempotency历史，store拥有实际effect evidence，两者任一损坏都不能被另一方无条件覆盖。Fail-closed避免自动“修复”制造虚假成功或重复effect，同时维持store/repository级故障隔离。 |
| Rejected alternatives | Journal永远优先：可能宣布不存在或已漂移effect成功；store永远优先并重建journal：丢失request identity与acceptance evidence；发现矛盾后继续普通服务：后续mutation会覆盖诊断现场。 |
| Constraints | Global registry不可读的service-wide readiness规则继续沿用Round 4。Partial component restore与aggregate identity/manifest由Round 7固定。Diagnostics不得向普通caller泄露内部path、SQL或raw rows。 |
| Downstream impact | 约束startup integrity checks、repository/store availability、quarantine、restore/repair tooling、diagnostics、tamper tests和operator runbook。 |
| Formal owner | Repository control/effect authority contract；backup/restore contract；deployment integrity policy。 |
| Reopen condition | 获得形式化并通过故障测试的journal reconstruction protocol，能从不可伪造provider evidence恢复全部request、idempotency和effect语义。 |

### P2-R6-D08 — Lifecycle-specific crash closure for repository creation and lazy Current

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D08` |
| Topic | CreateRepository and first Current materialization recovery |
| Status | `ACCEPTED` |
| Decision | CreateRepository在per-repository control authority尚未可用前，由global registry原子保存PROVISIONING、create operation identity、idempotency/request digest和storage key。在deterministic durable staging slot初始化control DB与Dolt repository，写入repository identity/layout marker并验证initial commit/ref、format和aggregate closure后，原子发布目录；随后global registry同一transaction写READY与APPLIED evidence，再通过正式path重开并验证初始状态后进入VERIFIED。Recovery按evidence推进：无staging/final aggregate且executor已停止可判NOT_APPLIED；matching staging继续验证/发布；aggregate已发布而registry仍PROVISIONING时验证marker后补READY/APPLIED；identity不匹配则quarantine/ATTENTION_REQUIRED；无registry identity目录不自动收编。Lazy Current文件存在本身不是公开data effect；首次mutation前创建并验证repository-bound current identity/schema，数据、generation、idempotency和effect marker仍在首个mutation transaction原子提交。Crash只留下合法empty Current DB时可验证复用且首个mutation仍为NOT_APPLIED；identity/schema不匹配则Current Store unavailable，不自动覆盖。 |
| Rationale | Create跨global SQLite与filesystem且尚无repository control DB，需要独立lifecycle journal；lazy materialization则必须区分物理空文件与公开Current mutation effect，避免把初始化残留误判为业务数据写入。 |
| Rejected alternatives | 同步CreateRepository：无法消除timeout/partial directory uncertainty；扫描目录决定create成功：绕过registry identity/idempotency；发现Current文件就认为首个mutation成功：缺少transaction effect marker。 |
| Constraints | Filesystem publish的exact atomic primitive、marker fsync和directory durability必须通过目标volume crash tests。Global create journal不能被普通per-repository operation schema替代。Repository deletion仍由Round 7的plan-before-execute lifecycle拥有。 |
| Downstream impact | 约束global registry schema、Create executor、staging publisher、initial Dolt bootstrap、lazy Current initializer、startup reconciler和crash matrix。 |
| Formal owner | Repository lifecycle/registry contract；CurrentTableStore materialization contract。 |
| Reopen condition | Storage backend提供覆盖registry与aggregate publication的原子provision primitive，或Current provider改为无需持久materialization的remote service。 |

### P2-R6-D09 — Caller-selected verification policy and caller-owned rigor

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D09` |
| Topic | Versioned write verification levels, defaults and downstream responsibility |
| Status | `ACCEPTED` |
| Decision | `SubmitImport`必须由caller显式提供、且无server default的`verification_level = NONE | STRUCTURAL | FULL`。具备该write action权限的caller可选择任意level，不增加独立降级authorization action，由caller对所选严谨程度负责。NONE不执行committed table readback，但仍强制journal、operation/commit/ref attribution、atomic target publication evidence和effect reconciliation；STRUCTURAL从committed ref检查catalog、required table set、schema、row count及通用protected metadata；FULL再流式检查全部required canonical/protected rows、content/ordering digest和ordered invariants。三个level完成各自policy后均可进入VERIFIED/SUCCEEDED并正常推进downstream；VERIFIED只表示requested policy完成，不再隐含FULL。Result/journal/audit必须记录requested/completed level、policy version和level-specific evidence；level进入request digest与idempotency collision判断。后验检查使用独立、异步、只读`VerifyCommit(repository_id, commit_id, verification_level, idempotency_key)` operation，不改写原import operation或既有业务结果；其成功/失败按本次检查普通结果处理，不建立verification upgrade、integrity overlay或retroactive business state machine。 |
| Rationale | Repository Service是通用表版本库，应提供可观测、可选择的可靠性机制，而不是替所有caller强制最高成本的内容证明。显式必填level避免隐藏默认；operation独立性让caller可以按场景在性能与严谨性之间取舍，同时保持effect safety不可降级。 |
| Rejected alternatives | 所有normal write强制FULL：把业务风险偏好固化为Repository全局成本；server提供隐式默认：caller可能在不知情时采用错误严谨度；为降低level增加独立权限：超出所需授权复杂度；后验FULL失败追溯改写原operation/业务结果：引入跨operation状态机；完全跳过journal/ref publication evidence：混淆内容验证选择与effect correctness。 |
| Constraints | Caller choice只能降低内容/结构verification，不能关闭authentication/authorization、input safety、idempotency、atomic effect publication、writer fencing、effect evidence或reconciliation。所有consumer不得把裸VERIFIED解释为FULL，必须读取completed level；需要FULL的业务caller自行请求并检查。CurrentTableStore的transactional mutation correctness不受本decision降级。该decision显式替代`P2-R4-D01`、`P2-R5-D01`、`P2-R6-D02`、`P2-R6-D05`、`P2-R6-D06`和`P2-R6-D07`中“normal import必须full readback才可VERIFIED”及“VERIFIED必然存在full SnapshotManifest”的局部条款，并扩展`P2-R2-D03`的closed action surface加入VerifyCommit；其余语义保持ACCEPTED。对应Accepted formal contracts与ADR必须在整体formalization时显式supersede，不得静默兼容两套VERIFIED语义。 |
| Downstream impact | 新增verification enum、level-specific evidence union、VerifyCommit operation、journal/idempotency/audit字段、SDK分支、Fake/Local/Remote conformance、三档provider/measurement profile，并修改T3 consumer和formal authority。 |
| Formal owner | Repository import/verification contract；External Effect and Recovery中VERIFIED语义；Business caller的T3 acceptance policy；performance measurement contract。 |
| Reopen condition | 实际consumer无法安全处理level-specific success，监管/合规要求固定最低验证，或measurement证明FULL成本可忽略且减少选择面更有价值。 |

### P2-R6-D10 — Caller responsibility does not waive effect-safety identity

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D10` |
| Topic | Boundary between caller-owned result rigor and mandatory effect safety |
| Status | `ACCEPTED` |
| Decision | Caller可选择内容验证、并发覆盖和读取freshness等业务policy，但所有mutation仍必须提供caller idempotency key；Repository Service始终强制request digest、RepositoryOperationId、journal、effect attribution、writer fencing和evidence-first reconciliation。不存在无idempotency的fire-and-forget public write path。Caller选择宽松结果policy不改变response丢失后的同key查询/重试规则，也不允许把UNKNOWN当作NOT_APPLIED。 |
| Rationale | Idempotency与journal不是替caller保证业务内容正确，而是让服务和caller能识别“这个请求是否已经被接受或执行”。保持单一路径比同时支持recoverable与不可recoverable mutation更简单，也避免宽松policy破坏内部crash recovery。 |
| Rejected alternatives | Idempotency key可选：响应在operation ID返回前丢失时无法关联原请求，并产生两套retry语义；关闭journal/fencing：服务自身无法安全恢复；把所有可靠性选项打包成单一strict/loose profile：不同语义耦合且容易误用。 |
| Constraints | Server可提供SDK helper生成key，但不得静默替caller生成一个caller无法在response loss后复用的key。Idempotency retention由Round 7固定；compact collision evidence不得因verification/concurrency policy宽松而省略。 |
| Downstream impact | 保持统一mutation envelope、journal schema、SDK retry helper、operation lookup和crash conformance；限定caller-responsibility原则的非降级边界。 |
| Formal owner | Repository API/idempotency contract；external-effect-and-recovery contract。 |
| Reopen condition | Public transport提供可证明等价的client request identity与lost-response lookup，且能在不分裂recovery语义的情况下省略显式key。 |

### P2-R6-D11 — Caller-selected concurrency for mutable resources

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D11` |
| Topic | Optimistic check versus last-write-wins mutation policy |
| Status | `ACCEPTED` |
| Decision | Mutable write必须显式、无default地选择`concurrency_mode = CHECK_EXPECTED | LAST_WRITE_WINS`。CHECK_EXPECTED要求observed generation/commit并在同一effect boundary校验；LAST_WRITE_WINS不要求expected token，caller承担覆盖并发更新的风险。该选择适用于Current Replace/Apply/Drop、SubmitImport的mutable target publication和mutable ref update/delete；Versioned import仍必须提供base CommitId定义commit parent/content，LAST_WRITE_WINS只放宽target publication。Ref surface保留CompareAndSetRef并新增显式SetRef或等价closed LWW action，不把缺失expected token隐式解释为LWW。Create名称唯一性、immutable ref、protected/internal ref、operation ref及technical metadata不允许LWW绕过。所有模式仍使用idempotency、journal和effect evidence。 |
| Rationale | Lost-update protection属于caller可理解和承担的业务并发policy；显式mode同时支持严谨流程和简单覆盖流程，又避免optional expected token产生含糊行为。 |
| Rejected alternatives | 所有mutable write强制CHECK_EXPECTED：过度固定caller风险偏好；缺失expected即默认LWW：隐式降级；允许immutable/protected ref force update：破坏资源语义与内部恢复。 |
| Constraints | 该decision显式替代`P2-R2-D13`、`P2-R2-D14`、`P2-R2-D18`、`P2-R2-D20`、`P2-R5-D04`与`P2-R5-D05`中“所有mutable write必须expected token/CAS且不存在任何public unconditional path”的局部条款，并扩展`P2-R2-D03`的closed action surface加入SetRef或等价typed LWW action；其余generation publication、checked CAS、immutable、tombstone、journal和ref verification语义保持ACCEPTED。Concurrency mode进入request digest、result和audit。 |
| Downstream impact | 新增concurrency enum、Current request字段、SubmitImport target publication policy、SetRef/LWW delete action、authorization action mapping、fixtures和lost-update tests。 |
| Formal owner | Current mutation contract；Repository import/ref mutation contract。 |
| Reopen condition | Consumer evidence显示LWW频繁误用，或底层provider无法在保持journal/effect evidence时实现deterministic unconditional publication。 |

### P2-R6-D12 — Caller-selected verification for asynchronous Current content writes

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D12` |
| Topic | Current bulk content verification rigor |
| Status | `ACCEPTED` |
| Decision | Async Current Create/Replace/SubmitCurrentTableMutationBatch等table-content write必须显式、无default地选择与versioned import同名的`verification_level = NONE | STRUCTURAL | FULL`。SQLite data transaction、resulting generation、idempotency和committed effect marker在所有level均强制：NONE完成这些effect evidence即成功；STRUCTURAL再从committed Current snapshot验证schema与row count；FULL再读取committed snapshot并匹配versioned canonical content digest。三个level完成各自policy后均可VERIFIED/SUCCEEDED。小型同步ApplyCurrentTableMutations不增加verification_level，其constraints、affected-row result、generation和idempotency与mutation处于同一transaction，且不执行全表scan。Drop没有table content可验证，使用transaction/effect evidence。 |
| Rationale | Current整表写与Dolt import具有相同的成本/严谨度取舍，统一enum减少概念数量；SQLite transaction correctness仍不可选，额外readback才由caller决定。 |
| Rejected alternatives | Current bulk始终FULL：重新引入强制整表读取成本；Current永远NONE：无法满足需要独立post-commit证明的caller；同步小mutation也做FULL：与局部transaction effect不成比例。 |
| Constraints | 该decision替代`P2-R5-D05`中async Current bulk必须row-count/content verification后才VERIFIED的局部条款；control/current crash marker与APPLIED recovery语义保持ACCEPTED。Level进入request digest、journal、result和audit；后验Current verification若需要，使用独立read-only operation，不改写原mutation。 |
| Downstream impact | 统一verification DTO/evidence union、Current worker、SQLite readback provider、SDK、measurement和三档conformance matrix。 |
| Formal owner | CurrentTableStore mutation/verification contract；Repository operation result contract。 |
| Reopen condition | SQLite transaction evidence已满足所有consumer且无人使用STRUCTURAL/FULL，或合规要求Current content write固定最低验证。 |

### P2-R6-D13 — Caller-selected exact or latest-at-start read binding

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D13` |
| Topic | Read/export snapshot strictness and freshness |
| Status | `ACCEPTED` |
| Decision | Versioned/current catalog、stream和export request必须显式、无default地选择`read_binding = EXACT(binding) | LATEST_AT_START`。Versioned EXACT携带CommitId，LATEST_AT_START携带RefName并在真正打开provider snapshot时resolve；Current EXACT携带CurrentTableGenerationId，LATEST_AT_START在打开SQLite read transaction时取得current generation。所有response、stream header、cursor和artifact manifest必须返回并绑定实际resolved CommitId/generation；一旦resolved，同一次读取保持pinned snapshot。Async export的LATEST_AT_START指worker开始获取snapshot时，不是request acceptance时；多个独立LATEST请求不承诺同一版本。DiffRefs等天然比较两个明确历史点的operation继续要求exact commits。 |
| Rationale | Exact binding为需要可复现结果的caller保留最高保证；LATEST_AT_START让只关心执行时最新数据的caller避免额外resolve/stale-retry，同时不牺牲单次流内部一致性。 |
| Rejected alternatives | 所有读取强制EXACT：把freshness选择固定给服务；只提供LATEST：无法复现、resume或审计；在请求acceptance解析后仍称LATEST_AT_START：异步排队语义误导。 |
| Constraints | 该decision扩展并局部替代`P2-R3-D01`与`P2-R3-D06`的exact-only入口；resolved snapshot pin、generation/ref evidence和cursor binding仍保持ACCEPTED。LATEST_AT_START不允许cursor跨新snapshot续读。Read mode进入query/options digest和audit。 |
| Downstream impact | 新增discriminated read binding、server-side resolve path、stream/artifact evidence、SDK convenience、async export tests和cache key维度。 |
| Formal owner | Repository read/export consistency contract；wire binding schema。 |
| Reopen condition | Consumer无法理解worker-start freshness，或provider不能在resolve与read之间形成同一snapshot boundary。 |

### P2-R6-D14 — Atomic Current mutation batch remains the only batch outcome

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D14` |
| Topic | Caller responsibility versus partial row-batch success |
| Status | `ACCEPTED` |
| Decision | TableMutationBatch继续保持single-table all-or-nothing，v1不增加BEST_EFFORT或partial-success mode。任一duplicate/missing/existing/schema/key/constraint conflict使整batch失败且generation不变；caller通过UpsertRow等closed variant表达允许的单row语义，需要独立失败域时拆分batch并为每个请求使用独立idempotency key。Caller-responsibility原则不要求服务提供每一种宽松policy；可由请求拆分组合得到的行为不扩张batch transaction、partial checkpoint或per-row recovery contract。 |
| Rationale | Partial batch会新增per-row outcome、部分generation、重复投递和crash recovery语义，复杂度远高于caller拆分请求。Atomic batch是更简单、可组合且易于解释的primitive。 |
| Rejected alternatives | BEST_EFFORT batch：产生partial effect和复杂retry；遇错停止并保留前缀：结果依赖row顺序且难以幂等；自动把conflict改为no-op：隐藏caller数据问题，现有Upsert/拆分已足够。 |
| Constraints | `P2-R2-D21`全部语义继续ACCEPTED。Round 8可调整batch size/resource limits，但不得按size隐式改变atomicity。 |
| Downstream impact | 避免新增partial journal/result schema；固定Current transaction、SDK batching、conflict handling和fault tests。 |
| Formal owner | CurrentTableStore TableMutationBatch contract。 |
| Reopen condition | Accepted workload证明请求拆分造成不可接受的固定成本，且已定义deterministic per-row idempotency、generation和partial recovery contract。 |

### P2-R6-D15 — Verification mismatch is an ordinary operation failure, not authority corruption

| 字段 | 值 |
| --- | --- |
| ID | `P2-R6-D15` |
| Topic | Requested verification failure versus repository integrity incident |
| Status | `ACCEPTED` |
| Decision | 必须区分“requested content/structure verification未匹配”与“Repository authority自相矛盾”。SubmitImport或async Current content write的STRUCTURAL/FULL检查不匹配时，mutation effect仍记录为APPLIED，operation以typed verification failure结束而不进入VERIFIED/SUCCEEDED；它可以呈现`FAILED + effect=APPLIED`，writer lease和Repository mutation lane在failure evidence持久化后释放，禁止自动重放，caller自行决定后续write或业务处理。该失败本身不使StoreKind unavailable、不创建integrity overlay，也不追溯修改其他operation。独立只读VerifyCommit mismatch仅使该verification operation FAILED、effect=NONE，原import/业务结果不变。只有journal、internal ref、commit marker、Current effect marker或provider storage evidence彼此矛盾、缺失authority identity或证明实际storage corruption时，才使用INTEGRITY_FAILURE、quarantine和operator intervention。Known verification failure终态后可按Round 7 retention清理transient staging/internal ref，但必须保留journal、result commit/target evidence、request digest和failure evidence。 |
| Rationale | Caller主动选择verification level也必须承担检查失败的普通结果；把任意内容不匹配升级为repository corruption会重新引入过度冻结。另一方面，authority contradiction意味着服务无法解释自身状态，仍必须fail closed。 |
| Rejected alternatives | 所有verification mismatch都quarantine store：把caller数据不匹配误当provider损坏；FULL mismatch自动回滚target：产生新的未journaled effect；后验VerifyCommit失败追溯原operation：引入跨operation状态机；APPLIED failure自动重放：可能重复或覆盖effect。 |
| Constraints | 该decision显式替代`P2-R6-D01`中FAILED仅允许NONE/NOT_APPLIED、`P2-R6-D02`中所有full-readback mismatch必须attention、`P2-R6-D03`中所有READBACK_INTEGRITY_MISMATCH均使store unavailable，以及`P2-R6-D05/D06`中transient evidence只有NOT_APPLIED或VERIFIED后才能cleanup的局部条款。UNKNOWN effect、authority contradiction和真实storage corruption规则保持ACCEPTED。Business owner是否在APPLIED verification failure后保留自己的T1 occupancy由其contract决定，Repository Service不替其自动finalize或rollback。 |
| Downstream impact | 扩展operation status/effect合法组合、verification failure codes、lease release、cleanup eligibility、business client handling和failure fixtures；缩小quarantine触发条件。 |
| Formal owner | Repository verification/failure contract；external-effect recovery中operation/effect分离；business T3 recovery policy。 |
| Reopen condition | 合规要求任何requested verification mismatch都冻结repository，或provider证据无法区分caller input mismatch与storage corruption。 |

## Round 7 — GC, retention and backup/restore

### P2-R7-D01 — Reachability-based versioned retention without a second public pin model

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D01` |
| Topic | Versioned commit roots and Current generation lifecycle |
| Status | `ACCEPTED` |
| Decision | Versioned commit 在可从protected/mutable/immutable public ref到达、被nonterminal operation/internal operation ref/recovery evidence引用、被active read/export/backup pin，或仍处于terminal operation的30天diagnostic hold时保留。全部root和hold解除后commit可由GC删除，后续exact lookup返回typed `COMMIT_GONE`。v1不新增通用`RetentionLease`公共资源；caller需要长期保留不能由其他ref到达的commit时创建immutable ref。CurrentTableStore仍只保存当前状态，mutation后旧CurrentTableGenerationId不可用于读取历史内容，也不为GC复制旧SQLite generation。 |
| Rationale | 复用ref、operation和active-use identity形成单一retained closure，避免新增容易泄漏的第二套pin/lease协议；有限diagnostic hold关闭operation完成到caller建立长期ref之间的窗口。Current不因通用GC重新变成版本库。 |
| Rejected alternatives | 新增caller-managed RetentionPin/lease：增加续期、权限、泄漏和backup语义；永不删除任何commit：orphan与失败import无限增长；保存旧Current generations：违反已确认的latest-only store边界。 |
| Constraints | GC root计算必须覆盖ref ancestry、internal recovery ref、active pins和diagnostic hold；Plan本身不偷偷延长candidate生命周期。CommitId在被GC后不得重新绑定或复用。Immutable-ref name tombstone继续永久保留。 |
| Downstream impact | 约束ref registry、operation result hold、read/export pin、GC closure、GetCommit failure、SDK retention guidance、history/GC tests和capacity measurement。 |
| Formal owner | Repository commit/ref lifecycle and GC contract；CurrentTableStore generation contract。 |
| Reopen condition | Accepted consumer需要大量无named ref的长期commit pin，或immutable-ref tombstone/capacity evidence证明该路径不可承受。 |

### P2-R7-D02 — Tiered evidence, idempotency, artifact and staging retention

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D02` |
| Topic | Retention classes, compaction and public expiry |
| Status | `ACCEPTED` |
| Decision | Nonterminal、UNKNOWN、ATTENTION_REQUIRED及authority-conflict recovery closure不设TTL，直到明确收口或repository删除。Terminal operation的完整request/journal/verification/diagnostic evidence及result-commit hold保留30天；之后压缩为repository生命周期内持续存在且`GetOperation`可返回的`details_compacted=true`终态记录。Compact record至少保存idempotency scope/key hash、request digest、operation/result identity、commit/generation、effect classification、requested/completed verification level和evidence digest，并与永久compact idempotency tombstone合并或等价去重；不得保存raw rows/payload。Export/Diff等公开结果artifact由caller显式选择1小时至30天TTL且无隐藏default，publish时固定`expires_at`。Repository-local import artifact/staging在nonterminal期间pin，known terminal后保留24小时再GC；已证明无effect/recovery引用的unpublished scratch立即清理。Quarantine evidence不自动过期；immutable-name及RepositoryId deletion tombstone永久保留。 |
| Rationale | 大型payload和诊断证据有限保留控制容量，compact终态仍支持迟到poll、幂等碰撞和effect解释；只有消费期限属于caller选择，服务自身recovery authority不允许被普通请求缩短。 |
| Rejected alternatives | 只定义类别、不固定时间：无法形成稳定expiry/capacity contract；所有TTL由caller决定：可能删除service recovery authority；完整journal/payload永久保存：规模与敏感数据成本无界；TTL后把旧idempotency key当新请求：可能重复effect。 |
| Constraints | Expiry只使资源进入GC eligibility，不授权绕过active pin或recovery root。Same-key/same-digest在full detail压缩后返回compact原结果事实，不创建新mutation。Backup artifact自身由operator backup policy管理，不由repository aggregate GC静默删除。Audit sink的独立retention由Round 9拥有。 |
| Downstream impact | 约束operation/idempotency schema、compactor、GetOperation representation、artifact request/manifest、staging cleanup、backup inventory、privacy/capacity tests和SDK handling。 |
| Formal owner | Repository operation/idempotency/artifact/cleanup lifecycle contracts；Round 9 audit retention contract。 |
| Reopen condition | 法规要求更长/更短固定evidence retention，accepted recovery objective超过30天且compact evidence不足，或capacity measurement证明永久compact记录不可承受并提供等价anti-reuse authority。 |

### P2-R7-D03 — Exact-plan repository-quiescent garbage collection

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D03` |
| Topic | GC Plan/Execute, staleness, interruption and concurrency |
| Status | `ACCEPTED` |
| Decision | `PlanGarbageCollection`只读地产生持久`GcPlanId`、plan digest、root epoch/digest、candidate分类与估算bytes、创建时间及15分钟expiry，并提供summary与可分页candidate inventory；plan本身不pin candidate。`ExecuteGarbageCollection`必须携带exact plan identity/digest及idempotency key，取得该repository的maintenance barrier，暂停新mutation、backup和其他GC并drain direct readers/runtime；任何删除前重新核对epoch、active pins和expiry，不匹配则以`GC_PLAN_STALE`在无effect状态失败且不自动replan。执行按durable checkpoint分阶段清理eligible operation refs、staging、expired artifact/evidence和Dolt unreachable objects；crash后保持repository GC maintenance lifecycle并由reconciler续跑同一plan。可在safe batch boundary终止恢复，但已回收内容不回滚，operation记录`effect=APPLIED`，解除barrier后必须重新plan。其他repository继续服务。Result报告planned/actual reclaimed bytes、duration和最终retained closure。 |
| Rationale | Quiescent exact-plan使dry-run与实际删除集合可核对，并把首版竞态限制在单repository maintenance lifecycle；checkpoint避免长GC crash后从不透明状态重做。 |
| Rejected alternatives | Execute时静默重算：用户确认的plan不再对应实际删除；首版online concurrent GC：需要完整read pin/ref/artifact/Dolt竞态设计；plan创建即永久pin：过期plan会阻止正常回收；全服务停机GC：扩大故障和可用性范围。 |
| Constraints | GC永不删除public ref、未到期artifact、nonterminal/recovery evidence或永久tombstone。Provider GC实际释放量可与estimate不同，但不得扩大semantic candidate closure。GC/backup/delete/restore在同repository内互斥。Background scheduling若后续增加必须复用相同Plan/Execute contract。 |
| Downstream impact | 新增GC plan store、root epoch、maintenance lifecycle、checkpoint、admission/drain、typed stale/partial result、Dolt provider adapter、crash/concurrency tests和GC metrics。 |
| Formal owner | Repository Service GC/resource lifecycle contract；deployment maintenance runbook。 |
| Reopen condition | Accepted availability目标禁止repository-quiescent maintenance，且完成可证明的online pin/fencing/provider GC设计；或provider无法按semantic retained closure执行安全GC。 |

### P2-R7-D04 — Manifested aggregate backup and restore with a new storage incarnation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D04` |
| Topic | Backup manifest, restore validation and restored physical identity |
| Status | `ACCEPTED` |
| Decision | Repository-quiescent backup产生versioned manifest，至少包含BackupId、RepositoryId、source storage incarnation、capture time、registry lifecycle/layout/format、Dolt runtime/storage identity与ref/commit closure digest、Current materialization/schema/catalog/table generations及checkpoint/digest、control schema与retained journal/idempotency/tombstone closure、retained artifact inventory/digest/size/original expiry、component inventory/size/digest及整体manifest digest。Restore先进入`RESTORING`并在隔离staging验证manifest/component digest、identity binding、format compatibility、SQLite integrity/schema、Dolt open/ref closure和artifact closure；禁止partial component restore。Active READY repository同ID时拒绝覆盖；损坏/unavailable repository只能通过显式operator recovery先隔离旧aggregate再以完整backup替换。Restore保留RepositoryId、CommitId、ref、operation、artifact及idempotency identity，但生成新的内部`RepositoryStorageIncarnationId`、提升fencing epoch并记录source BackupId。Runtime process/lease/cursor/cache/scratch/credential不恢复；artifact沿用原expires_at，过期后不获得新生命周期。 |
| Rationale | 完整manifest证明aggregate closure并阻止混合不同备份组件；逻辑identity保持外部引用，新physical incarnation区分恢复后的storage/fencing环境。 |
| Rejected alternatives | 复制原storage incarnation：旧runtime/fencing证据与新环境难区分；任意partial restore：制造journal/store矛盾；自动覆盖active repository：可能回滚仍在服务的数据；restore时换RepositoryId：破坏外部引用。 |
| Constraints | Backup共捕获Versioned/Current只表示运维closure，不声明业务一致snapshot。Backup失败不得发布complete manifest。Full-service DR是global registry backup与多个aggregate backup的组合。Backup target/encryption/authorization由Round 8/9补充，不允许caller提交任意host path。Restore rollback后的caller-visible incarnation/precondition边界由`P2-R7-D06`收口。 |
| Downstream impact | 新增backup/restore operation、manifest schema、component validators、RESTORING lifecycle、storage incarnation/fencing rotation、collision/repair path、DR inventory及corruption/crash tests。 |
| Formal owner | Repository Service backup/restore, registry and storage identity contracts；deployment disaster-recovery runbook。 |
| Reopen condition | Accepted RPO/RTO要求non-quiescent online backup、跨repository atomic snapshot或partial repair，并完成相应journal/fencing/consistency设计。 |

### P2-R7-D05 — Planned repository deletion with permanent tombstone and checkpointed purge

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D05` |
| Topic | Repository aggregate deletion lifecycle |
| Status | `ACCEPTED` |
| Decision | `PlanRepositoryDeletion`生成15分钟有效的plan，绑定RepositoryId、lifecycle/root epoch、aggregate inventory/estimated bytes、active reader/runtime、nonterminal/UNKNOWN operation、GC/backup状态、retained refs/artifacts/quarantine、last-known complete backup summary及plan digest，并要求显式选择`unresolved_operation_policy = REJECT | DELETE_WITH_REPOSITORY`且无default。后者只在全部executor停止并fenced后允许继续，不把UNKNOWN伪装成NOT_APPLIED，并将最终effect摘要写入deletion tombstone。Execute必须携带exact plan/digest/idempotency，校验freshness后将registry置为DELETING、拒绝新普通操作、drain/fence runtime、把aggregate原子移入durable trash/quarantine slot，再写永久DELETED tombstone，记录plan/delete operation/effect summary/last backup identity，最后异步checkpoint物理purge；crash按lifecycle继续，不重新开放repository。Backup-before-delete只提示不强制；external backup不随删除；RepositoryId在同一trust domain永久不可重新创建或restore。 |
| Rationale | Registry tombstone与durable trash publication让删除在crash窗口可解释并最终释放容量；显式unresolved policy把破坏性风险交给operator选择，同时保留真实effect分类。 |
| Rejected alternatives | 直接递归删除：crash后无法确定范围或身份；永久soft delete：不能释放容量；强制先备份：替operator决定数据保留政策；UNKNOWN永远阻塞删除：无法处置明确废弃但有残留evidence的repository。 |
| Constraints | 普通backend/worker caller仍无delete action；精确authorization与审计强度由Round 8/9固定。Delete与GC/backup/restore互斥。Physical purge失败只形成cleanup attention，不撤销DELETED逻辑事实。Global tombstone不得被普通GC删除。 |
| Downstream impact | 新增delete plan/result、global lifecycle journal、trash/quarantine publisher、operation fencing、compact deletion evidence、purge checkpoint、GONE behavior、operator workflow及crash/destructive-action tests。 |
| Formal owner | Repository aggregate lifecycle/deletion contract；operator security/audit contract；deployment runbook。 |
| Reopen condition | 产品要求普通tenant self-service deletion并完成等价高风险authorization/recovery，或storage backend无法提供可验证的staged publish/purge机制。 |

### P2-R7-D06 — Public repository incarnation precondition across restore rollback

| 字段 | 值 |
| --- | --- |
| ID | `P2-R7-D06` |
| Topic | Caller-visible restored incarnation and late mutation retry |
| Status | `ACCEPTED` |
| Decision | `RepositoryIncarnationId`是server-generated opaque public token，CreateRepository、GetRepository、RestoreRepository及所有mutation result返回当前值。所有可能产生effect的普通mutation必须携带`expected_repository_incarnation_id`；若没有matching historical idempotency result且token不是当前值，请求在acceptance前以typed `REPOSITORY_INCARNATION_STALE`拒绝，不创建operation或effect。Read request不强制携带incarnation，但response/stream/artifact binding返回实际值。每次成功aggregate restore生成新incarnation；同一incarnation内继续执行永久compact idempotency tombstone规则。Restore backup中仍存在的旧operation/idempotency record按其原incarnation可查询并返回原结果；backup point之后已丢失的key不会被server伪装成已知结果。Caller取得新incarnation后显式决定是否重新提交恢复窗口内的mutation，该新请求属于新incarnation的idempotency namespace。 |
| Rationale | Backup rollback必然可能丢失backup point之后的effect和幂等记录。公开且mutation-bound的incarnation关闭旧客户端静默重放窗口，同时不要求Repository Service猜测丢失mutation是否应重新执行；决定权仍在caller。 |
| Rejected alternatives | Incarnation只供内部运维：旧客户端可能把迟到重试当成新mutation；restore生成新RepositoryId：破坏逻辑资源引用；建立aggregate之外的永久全局effect ledger：违反repository backup closure并增加第二authority。 |
| Constraints | Public RepositoryIncarnationId是`P2-R7-D04`新storage incarnation的caller-visible identity，不另建第二个并行incarnation token；它不得编码path、node或provider identity。Historical idempotency lookup必须先于新effect admission，使backup内已有请求仍可返回原结果；只有新effect才要求current incarnation。该decision细化`P2-R5-D02`：idempotency在单一incarnation内永久anti-reuse，跨restore discontinuity由caller刷新incarnation后显式选择。GC、backup、delete plan和operation evidence必须记录incarnation binding。 |
| Downstream impact | 新增public typed identity、mutation envelope/result字段、restore rotation、idempotency namespace维度、stale-incarnation error、SDK refresh/reconcile flow及RPO-window tests。 |
| Formal owner | Repository identity/mutation/idempotency contract；backup/restore contract。 |
| Reopen condition | 部署能够证明restore时所有caller和queued request均被原子fence并重新初始化，或采用不回退idempotency authority的外部存储且仍保持aggregate recovery closure。 |
