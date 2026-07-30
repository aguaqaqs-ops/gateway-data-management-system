# Phase 2 Consolidated Design Review

状态：**Resolved Review / Formalized**

日期：2026-07-30

适用范围：Backend vNext Phase 2 — Repository Service Foundation

本文件是Round 0–11确认后的整体一致性review，不是formal contract，也不复制
Decision Ledger的完整语义。冲突时以accepted formal authority、随后显式
supersede它的accepted Decision及最终formalization结果为准。

## 1. Review conclusion

整体设计在当前accepted decisions下闭合，没有发现必须重开Round 0–11的架构
冲突：

- Repository Service是独立、通用、容器化的table repository，不解释业务流程；
- VersionedTableStore与CurrentTableStore共享read/data-plane primitives，但拥有
  独立write、identity和recovery authority；
- disposable process与durable root、registry/control/current/Dolt authority边界
  一致；
- public operation、journal phase、effect truth、failure和cleanup正交；
- caller可以显式选择verification、concurrency和read freshness，但不能关闭
  authorization、input safety、idempotency、effect attribution、fencing或recovery；
- Local/Remote走同一application semantics，production backend只使用Remote；
- security、resource、deployment、recovery和exit gates均有唯一owner；
- WP0–WP9、37个R、有限并行和exact-commit exit形成可审核、可回滚主线。

Review outcome：**READY_FOR_BOUNDED_PHASE_3_CONSUMER_ADEQUACY_CHECK**。

这不是formalization授权。Consumer check通过后仍须由用户明确回复
“整体设计确认，可以 formalize”。

## 2. Goal, scope and non-goals

### 2.1 Goal

交付一个独立Repository Service，使backend/worker只通过稳定client/wire使用
repository、ref、commit、table、artifact和operation identity，不依赖Dolt CLI、
database connection或server local path。

Service同时提供：

- `VersionedTableStore`：Dolt-backed immutable history、ref、commit、diff、import；
- `CurrentTableStore`：SQLite-backed latest-only table、bulk replace和bounded
  row/field mutation；
- repository lifecycle、artifact transfer、journal/recovery、retention/GC、
  backup/restore/delete；
- thin auth/ACL、resource governance、observability和containerized deployment。

### 2.2 Fixed boundary

Repository Service不判断：

- 哪个store是业务authority；
- 同名Current/Versioned table是否相等；
- 是否应该dual-write；
- Preview、Submission、Review、Archive、Baseline、History等业务状态；
- storage/comparison projection的业务column policy、candidate或risk。

Caller显式选择store、read binding、concurrency mode和verification level，并自行
编排跨store或业务一致性。

### 2.3 Non-goals

- arbitrary SQL/DDL、cross-table join或cross-store transaction；
- table/row/column ACL和通用policy language；
- multi-node shared writer或active-active durable root；
- per-repository container/process/UID；
- service-owned cron、audit database、monitoring time-series、object storage；
- resumable multipart upload、presigned URL、caller path/URL ingress；
- generic provider/plugin/DAG/workflow framework；
- legacy repository migration/cutover；
- numeric performance claim、premature Rust/native optimization；
- Phase 3 capability、Phase 4 business Operation Runtime或Phase 5 workflow实现。

## 3. Component and dependency topology

```text
Backend / Worker / Operator
        |
gateway-repository-client (Remote SDK)
        |
deployment-owned TLS ingress
        |
Repository Service ASGI process
  transport/auth/capacity
        |
  application/domain
   |       |       |
operations storage observability
   |       |
 registry/control/current/artifacts
           |
 DoltRuntimeCoordinator
   | offline CLI | repository-scoped sql-server
        |
single-writer durable root
```

Python distributions：

1. `gateway-repository-contracts`
   - public DTO、closed enum、schema codec；
   - 无HTTP、storage、provider或业务规则。
2. `gateway-repository-client`
   - Repository Port、Fake、Remote SDK；
   - 依赖contracts。
3. `gateway-repository-service`
   - application/domain、Local adapter、transport、Dolt/SQLite/runtime；
   - 依赖contracts，不被backend production直接依赖。

Local client绑定已启动的application runtime，只绕过HTTP serialization和bearer
parsing；authorization、admission、idempotency、journal和recovery不绕过。

Service v1是单ASGI process、单durable-root owner、进程内bounded scheduler。
不引入Celery、Redis、external work queue或ORM。

## 4. Authority and persisted-state model

| Authority | Owned facts | Explicitly not owned |
| --- | --- | --- |
| Deployment config/secrets | credential→CallerIdentity、global actions、ResourcePolicy、backup target、TLS/collector config | repository ACL、business role、repository data |
| Global registry SQLite | RepositoryId、storage key、lifecycle、format、create/delete operation与tombstone | ordinary per-repository operation、table generation |
| Per-repository control SQLite | ACL、async operation journal、idempotency、lease/fencing、recovery/maintenance evidence | Current rows/generation、Dolt content |
| Current SQLite | Current catalog/rows/generation、sync idempotency/effect marker | version history、Dolt ref |
| Dolt repository | versioned tables、commit/ref及provider effect evidence | operation authority、business workflow |
| Artifact store | repository-bound published bytes/manifest及staging | caller path、anonymous credential |
| External audit collector | audit retention/index/query | effect/journal authority |
| Ephemeral process state | runtime cache、connections、scheduler cursor、bounded buffers | any durable semantic fact |

Repository aggregate包含registry record、control、Dolt、materialized Current及仍在
retention内的artifact/evidence。Cache和scratch可重建，不进入backup authority。

## 5. Public identity and API closure

### 5.1 Identity

- `RepositoryId`：opaque、永不复用；
- `RepositoryIncarnationId`：restore后轮换，所有mutation防止旧caller重放；
- `CallerIdentity`：deployment-assigned、稳定且不可复用；
- `RepositoryOperationId`：在operation retention内durable；
- `OperationRef`：CREATE scope或RepositoryId-bound scope，不建立全局普通operation
  locator；
- `CommitId`：immutable versioned binding；
- `RefName/ref identity`：mutable、immutable、protected/internal分类；
- `CurrentTableGenerationId`/catalog generation：latest-only equality binding；
- `ArtifactRef`：repository-bound、带manifest/expiry；
- cursor：opaque、HMAC保护、有TTL且可跨restart/upgrade失效，不是durable identity。

所有identity均不得泄漏path、storage key、provider command或business key。

### 5.2 Public surfaces and owner

| Surface | Semantics | WP owner |
| --- | --- | --- |
| Auth、live/readiness、capabilities/limits | service-level discovery/admission | WP1、WP9 |
| Create/GetRepository、GetOperation | async create和scoped operation lookup | WP4 |
| Get/UpdateRepositoryPolicy | generation/idempotency-protected ACL | WP4 |
| Upload/DownloadArtifact | one-shot authenticated streaming | WP4 |
| Current catalog/table/create/drop | latest-only table lifecycle | WP5 |
| Current Apply/Replace/SubmitBulk | sync bounded batch或explicit async bulk | WP5 |
| Current stream/export | generation-pinned Arrow/Parquet | WP5 |
| ResolveRef/GetCommit/GetCatalog | versioned metadata/read binding | WP6 |
| Versioned stream/export/diff | commit-pinned Arrow/Parquet/raw diff | WP6 |
| Ref create/update/delete | immutable/protected rules、CAS/LWW | WP7 |
| SubmitImport/VerifyCommit | canonical replay和caller-selected verification | WP7 |
| GetTableInventory | independently bound cross-store inventory | WP7 |
| Retention/GC | roots、exact plan、quiescent execute | WP8 |
| Backup/restore/activate | manifested aggregate、new incarnation、restricted ACL | WP8 |
| Inspect/resume repair | evidence-gated operator actions | WP8 |
| Plan/execute delete | permanent tombstone、checkpointed purge | WP8 |
| Resource usage/operator health | thin current projection | WP9 |

HTTP使用direct-resource GET与closed action-specific POST；不提供generic execute或
SQL endpoint。Endpoint-specific success schema携带wire version；接受前错误使用
typed problem，接受后failure通过Operation representation表达。

## 6. Read, write and data-plane consistency

### 6.1 Read

Caller必须显式选择：

```text
EXACT(binding)
LATEST_AT_START
```

Provider真正打开snapshot时解析LATEST，并在response/stream/cursor/artifact中返回
resolved CommitId或Current generation。同一次read保持pinned；多个LATEST请求
不承诺相同结果。

Versioned commit read可与同repository后续write并发。Current read绑定generation，
但旧generation在mutation后不提供历史读取；长Current read受duration/bytes/batch
限制，防止WAL/checkpoint starvation。

### 6.2 Data plane

- Direct rows：framed Arrow IPC，bounded buffer、backpressure、STREAM_END和integrity；
- durable export：async Parquet ArtifactRef；
- Versioned import：single canonical SQL replay artifact；
- Current bulk import：versioned Arrow IPC artifact；
- 大表禁止普通JSON、全表`to_pylist()`和无必要第二份全量serialization；
- staging完成close/hash/size/schema/manifest验证后才atomic publish。

不宣称真正zero-copy。SQLite binding、Dolt SQL parsing和Parquet encoding仍是合法
必要转换。

### 6.3 Mutation concurrency

语义writer scope为`(RepositoryId, StoreKind)`：

- 同store mutation串行；
- Current与Versioned可彼此并行；
- 不同repository在node ResourcePolicy内并行；
- reads使用pinned snapshot，不取得全程exclusive writer lock。

Mutable resource由caller显式选择：

```text
CHECK_EXPECTED
LAST_WRITE_WINS
```

Create name uniqueness、immutable/protected/internal/operation refs不能用LWW绕过。
Versioned import即使LWW publication仍要求base CommitId定义parent/content。

### 6.4 Verification

Async content write必须显式选择，无server default：

```text
NONE
STRUCTURAL
FULL
```

- NONE：journal、effect attribution、atomic publication和reconciliation仍强制；
- STRUCTURAL：检查catalog/schema/row count等结构；
- FULL：从committed snapshot流式检查全部required rows/digest/invariants。

`VERIFIED`表示requested policy完成，不隐含FULL。后验`VerifyCommit`是独立只读
operation，不追溯改写原operation或业务结果。

## 7. Operation, journal and recovery model

### 7.1 Orthogonal dimensions

Public status：

```text
ACCEPTED | RUNNING | RECONCILING | SUCCEEDED
FAILED | CANCELLED | ATTENTION_REQUIRED
```

Internal phase：

```text
ACCEPT → PREPARE → EXECUTE → PUBLISH
       → VERIFY → RECONCILE → CLEANUP
```

Effect truth：

```text
NONE | NOT_APPLIED | UNKNOWN | APPLIED | VERIFIED
```

Cleanup另有`NOT_REQUIRED/PENDING/COMPLETE/FAILED_ATTENTION`。FailureDescriptor不
代替上述任何状态。

`P2-R6-D15`修正早期一般规则：requested verification mismatch可以终止为
`FAILED + effect=APPLIED`，持久failure evidence后释放Repository mutation lane；
禁止自动重放。只有authority contradiction或真实storage corruption才quarantine。

### 7.2 Durable boundaries

Mutation acceptance持久化operation/idempotency/request digest；调用provider前
持久化`EFFECT_STARTED`。Timeout、disconnect、lease expiry、process exit或provider
error均不能单独证明NOT_APPLIED。

- 未accept：NONE；
- PREPARED且证明无executor/effect：NOT_APPLIED；
- EFFECT_STARTED后证据不足：UNKNOWN；
- matching commit/ref/Current marker：APPLIED；
- requested verification完成：VERIFIED。

UNKNOWN阻塞同一`(RepositoryId, StoreKind)` mutation lane，不阻塞另一store、其他
repository或合法pinned read。Reconciler只能依据evidence推进，不猜测、不换key/
artifact/executor blind replay。

### 7.3 Store-specific closure

- Create：global registry `PROVISIONING`、deterministic staging、aggregate marker、
  atomic publication、formal-path reopen；
- Current sync：rows/generation/idempotency/result同一SQLite transaction；
- Current async：control journal加Current transaction-local effect marker；
- Versioned：private operation ref/commit metadata、target publication和committed
  snapshot evidence；
- Restore/delete/GC：maintenance barrier、plan/checkpoint和repository-scoped recovery。

## 8. Repository lifecycle and irreversible effects

```text
PROVISIONING → READY
READY → RESTORING → RESTORED_RESTRICTED → READY
READY → DELETE_PLANNED → DELETING → DELETED(tombstone)
```

损坏、identity mismatch或authority contradiction进入repository/store unavailable或
quarantine，不自动收编目录或选一侧覆盖。

Versioned retention roots包括public refs、operation/recovery refs、active read/export/
backup pins和terminal diagnostic hold。Current不保存历史generation。

GC、restore和delete都是显式Plan/Execute或等价operator workflow：

- plan绑定exact digest/epoch/expiry；
- execute重新检查current policy、pins和preconditions；
- effect checkpointed、crash可resume/reconcile；
- 已GC/purge的数据不能通过image rollback恢复；
- restore依赖manifested backup并生成新incarnation；
- restore后ACL不自动生效，必须显式完整replacement activation；
- delete保留永久RepositoryId tombstone。

Repository Service只提供maintenance mechanism，不内置cron、RPO/RTO或自动backup
policy。

## 9. Security and resource governance

### 9.1 Trust model

v1是single trust-domain internal service，不宣称同root内抵御恶意tenant。互不信任
tenant使用独立service/root。

Production：

- `STATIC_BEARER`，DISABLED仅dev/test；
- deployment-owned TLS ingress，service plaintext只在隔离internal network；
- per-repository default-deny ACL与closed actions；
- authorization在provider/path/artifact open前执行；
- current authorization用于GetOperation/download等后续访问；
- accepted effect使用acceptance policy snapshot继续收口。

### 9.2 Input and container safety

- 不接受URL、host path、FD、arbitrary SQL/DDL；
- package拒绝traversal、duplicate、symlink/hardlink/device和bomb；
- closed identifier/filter/type/media grammar；
- non-root、read-only rootfs、drop capabilities、no-new-privileges、无Docker socket、
  default-deny egress；
- deployment-managed volume/backup encryption；
- secrets不进入aggregate、backup、log、metric或error。

### 9.3 Resource governance

Parser/wire hard limit固定；大型容量由finite production ResourcePolicy显式配置。
Logical quota/admission不是physical filesystem tenant sandbox。Durable control/
recovery reserve不能被普通data/artifact/staging耗尽。

`GetRepositoryResourceUsage`只投影已有accounting/scheduler状态，不扫描全库、不启动
idle runtime、不提供history/profiling或精确共享CPU/memory归因。RepositoryId禁止
成为Prometheus label。

## 10. Runtime, deployment and observability

一个production process取得durable-root OS exclusive lock后递增ServiceEpoch。
Deployment同时使用single-writer volume和无重叠更新策略。失锁立即not-ready并终止。

DoltRuntimeCoordinator按活跃repository有界启动runtime：

- 无active server可用offline `dolt sql -f`；
- 有active repository-scoped server时所有访问走该owner；
- 同repository禁止CLI/server并发打开；
- idle runtime只在无reader/writer/maintenance/recovery pin时回收。

Startup验证global authority、build/storage identity并启动增量reconciliation，不遍历
打开全部Dolt。`livez`只证明process/event-loop；`readyz`表示可安全接纳至少部分
workload。单repository故障不使整个service不ready。

Observability：

- structured JSON application log；
- versioned typed `security_audit` stdout stream；
- W3C trace context与optional OTLP；
- low-cardinality OpenMetrics；
- audit collector负责retention/index/query，collector故障告警但不阻塞普通请求；
- RuntimeBuildIdentity与EnvironmentFingerprint分离；
- capacity/benchmark按verification/provider/policy/environment分series，不混合。

首发verified platform仅`linux/amd64`、固定Debian-family digest、Python/uv/locks和
Dolt 2.1.11 binary digest。

## 11. Conformance and release gates

唯一gate classes：

1. `P2-PR-STATIC`
2. `P2-PR-CONTRACT`
3. `P2-PR-RECOVERY`
4. `P2-PHASE-EXIT-CONTAINER`

Affected-scope router fail closed；未知路径扩大范围。Phase 1 correctness/native只在
受影响PR运行，但Phase 2 exit candidate无条件运行完整Phase 1 regression，不重签
Phase 1 container identity。

Fake/Local/Remote matrix：

- semantic core：三者required；
- real storage/provider：Local、Remote required；
- HTTP/auth/stream/process/container：Remote required。

Required cell不得skip、xfail、UNSUPPORTED、advisory或automatic retry。
Gate outcome只有PASS/FAIL/BLOCKED；attempt immutable并保留supersession history。

Exit使用独立conformance-client container，经production Remote SDK和TLS ingress调用
production service image。Client不挂载durable root或private endpoint。

## 12. Implementation plan and critical path

```text
Round 11 / Consolidated Review
  → bounded Phase 3 consumer-adequacy check
  → F0 formal closure
  → WP0
  → max(WP1, WP2)
  → WP3
  → WP4
  → max(WP5, WP6)
  → WP7 ───────────────→ Phase 3 detailed design
  → WP8                         |
  → WP9-R1..R3                  |
  → WP9-R4 exact exit ──────────┴→ Phase 3 implementation entry
```

WP1/WP2和WP5/WP6最多两条feature track并行；contracts、registry/control schema、
journal、gate/evidence schema和shared fixtures由单owner串行合入。

WP职责：

- WP0 delivery/gates；
- WP1 contracts/client/service shell；
- WP2 provider/FS feasibility；
- WP3 durable foundation；
- WP4 create/operation/policy/artifact；
- WP5 CurrentTableStore；
- WP6 Versioned read/runtime；
- WP7 Versioned write/ref/verification；
- WP8 lifecycle/maintenance；
- WP9 production/release closure。

未端到端完成的route不注册、capability不advertise、required cell不activate。
每个R绑定exact dependency commit、gate evidence和rollback class。

## 13. Exact-commit exit

1. 设计、consumer check、formal和blocking closure完成；
2. clean worktree提名唯一candidate commit；
3. 从该commit构建全部wheels/images并记录digest；
4. 同commit运行全部Phase 2 gates及完整Phase 1 correctness/native；
5. 同service image/Remote SDK/TLS/volume运行container exit；
6. 验证coverage、fault receipt、cleanup和identity bundle；
7. 只聚合同一candidate closure的PASS attempt；
8. assertion failure必须新commit；
9. tracked code/config/lock变化产生新candidate并重跑全部exit gates；
10. 最终sign-off后才声明Phase 2 exit。

BLOCKED仅适用于semantic执行前的外部环境不可用；恢复后可按规则创建新immutable
attempt。不同commit、image、lock或environment的PASS不得拼接。

## 14. Review-level traceability

| Requirement family | Owning decisions | Formal owner | WP | Primary gate/evidence |
| --- | --- | --- | --- | --- |
| Boundary/topology/client | R0、R1、R11-D01/D02/D14/D15 | Architecture、wire/client | WP0–WP4 | Static architecture、Local/Remote observations |
| API/identity/versioning | R2、R11-D16/D25 | Repository wire | WP1、WP4–WP8 | schema snapshot、compatibility、auth inventory |
| Current semantics | R0-D06/D07、R2 Current、R5-D05、R6-D11/D12/D14 | Current contract | WP5 | transaction/crash/stream/bulk evidence |
| Versioned reads/data plane | R3、R4-D02、R6-D13、R11-D19/D21 | Repository read/provider | WP6 | pinned stream/export/provider evidence |
| Versioned writes/refs | R4-D01、R5、R6-D02/D06/D09/D11/D15 | import/ref/recovery | WP7 | replay/ref/readback/crash evidence |
| Operation/reconciliation | R5、R6、R9-D03/D06–D08 | external-effect/runtime | WP4、WP5、WP7 | journal/fault/restart/UNKNOWN evidence |
| Retention/lifecycle | R7、R8-D06/D08、R9-D09 | lifecycle/maintenance | WP8 | GC/backup/restore/delete checkpoints |
| Security/resources | R8、R10-D08/D11/D12 | security/deployment | WP1、WP3–WP5、WP8–WP9 | negative matrix、container inspection |
| Observability/measurement | R9、R11-D06/D07 | observability/performance | WP9 | telemetry/redaction/capacity series |
| Gates/release | R10、R11-D04/D05/D09/D23/D24/D26 | verification/release | WP0、WP9 | immutable attempts、coverage、identity/sign-off |

Formalization必须把本表展开为每项requirement/decision的machine-readable
`requirement → decision → formal owner → WP → gate → evidence`映射。

## 15. Formal supersession required before implementation

F0必须显式修改semantic owner，不能让实现兼容两套authority：

1. FULL-only VERIFIED
   → caller-selected NONE/STRUCTURAL/FULL；
2. CAS/expected-only mutable publication
   → explicit CHECK_EXPECTED/LAST_WRITE_WINS；
3. exact-only read
   → EXACT/LATEST_AT_START；
4. verification mismatch一律保持APPLIED occupancy/attention
   → ordinary `FAILED + effect=APPLIED`并释放Repository lane，authority contradiction
   仍quarantine；
5. full-readback-only measurement eligibility
   → verification-keyed measurement series。

至少检查canonical storage、external effect/recovery、architecture、
implementation stages、performance baseline、T3 finalize/Phase 2 exit及必要ADR。

## 16. Consolidated review checklist

| Guide check | Result |
| --- | --- |
| Accepted decisions互相兼容 | PASS |
| API、identity、data model闭合 | PASS |
| Read/write/recovery identity一致 | PASS |
| Journal/lease/idempotency/concurrency无未定义空窗 | PASS |
| Local/Remote contract-equivalent | PASS |
| Public contract不泄漏path或业务语义 | PASS |
| Container/restart满足recovery | PASS |
| Tests/gates覆盖exit | PASS |
| 未越界Phase 3/4/5 | PASS |
| 无重复owner；formal冲突已登记 | PASS WITH F0 SUPERSESSION |
| Deferred均non-blocking | PASS |
| Blocking register允许进入下一步 | PASS FOR CONSUMER CHECK |

## 17. Blocking and deferred register

### 17.1 Pre-formalization conditions

| ID | Condition | Owner | Current status |
| --- | --- | --- | --- |
| B1 | 用户接受本Consolidated Design Review或指定reopen | User | CLOSED — CONFIRMED 2026-07-30 |
| B2 | bounded Phase 3 consumer-adequacy check通过 | Cross-phase design | CLOSED — PASS CONFIRMED 2026-07-30 |
| B3 | 用户明确授权“整体设计确认，可以 formalize” | User | CLOSED — AUTHORIZED 2026-07-30 |
| B4 | Formal supersession、traceability和blocking manifest完成 | Formal owners | CLOSED — F0 PASS |

### 17.2 Non-blocking deferred

- legacy repository migration/cutover；
- second provider/object storage；
- multi-node/shared writer与repository sharding control plane；
- multi-platform container；
- resumable artifact transfer；
- hard untrusted-tenant physical isolation；
- service-owned durable audit outbox/query；
- secondary index、native loader和其他measurement-driven optimization；
- product-specific RPO/RTO/SLO。

## 18. User decision

本review已于2026-07-30由用户确认。后续bounded检查见
[bounded-phase-3-consumer-adequacy-check.md](bounded-phase-3-consumer-adequacy-check.md)，
其结论已由用户确认PASS。

当前已获得formalization授权并进入F0；尚未实现代码。
