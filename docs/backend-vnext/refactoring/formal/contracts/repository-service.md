# Repository Service Contract

状态：过渡期正式设计（仅用于完成旧设计WP1-R1 checkpoint）

日期：2026-07-30

阶段：Phase 2 Repository Service Foundation；Phase 3+ consumer

Contract ID：`gateway-vnext.repository-service`

Owner：Repository Service（public wire、repository effect、Current/Versioned generic
storage、recovery、security和resource semantics）

Semantic version：`1.0.0`

Wire version：`1`

## 0. Transition authority

2026-07-31已接受
[ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)。
本文完整内容只继续拥有正在进行的WP1-R1旧设计checkpoint。该checkpoint不发布、
不建立wire兼容义务；完成后允许破坏性删除strict JSON、FailureDescriptor、custom
stream envelope、schema snapshot和其他旧WP1-R1表面。

WP1-R2及后续不得依据本文当前双存储、ACL、verification level、journal/fencing、
maintenance或exact-evidence条款继续实现。Phase 2 simplification必须先发布精简后的
Repository owner contract，再恢复修订后的WP1-R2。

## 1. Authority boundary

Repository Service 是独立、通用、容器化的table repository。它提供两个显式、
相互独立的store：

- `VersionedTableStore`：Dolt-backed immutable commit history、ref、import、read、
  export和technical raw diff；
- `CurrentTableStore`：SQLite-backed latest-only catalog/table、bulk replace和bounded
  row/field mutation。

Caller在每次调用中显式选择store，并在自己的owner contract中保存table
persistence policy。Service不判断哪个store是业务authority，不自动routing，
不比较同名表，不保证dual-write或cross-store consistency。同一RepositoryId下
同名表可以分别存在于两个store且内容不同。

Service不拥有或解释Workspace、Preview、Submission、Archive、Baseline、History、
Snapshot、Comparison、Risk、Surface、Bundle、业务审批或business finalize。
它不提供arbitrary SQL/DDL、cross-table join、cross-store transaction、通用
workflow/plugin framework或业务policy language。

## 2. Component and dependency boundary

正式Python distribution为：

```text
gateway-repository-contracts
  <- gateway-repository-client

gateway-repository-contracts
  <- gateway-repository-service
```

- `gateway-repository-contracts`只保存public DTO、closed enum、schema codec和
  versioned contract assets，不含HTTP、storage、provider或业务规则。
- `gateway-repository-client`拥有Repository Port、Fake与Remote SDK。
- `gateway-repository-service`拥有application/domain、Local adapter、HTTP
  transport、Dolt/SQLite/storage/runtime。
- Backend/worker production只能依赖contracts/client，不依赖service。

Local与Remote执行同一application semantics。Local只绕过HTTP serialization和
bearer parsing，不绕过authorization、admission、idempotency、journal、fencing、
provider effect或recovery。

## 3. Public identity

| Identity | Rule |
| --- | --- |
| `RepositoryId` | server-generated canonical lowercase UUIDv7；opaque；删除后永不复用 |
| `RepositoryIncarnationId` | restore后轮换；mutation必须绑定current incarnation |
| `RepositoryOperationId` | server-generated UUIDv7；在operation retention内durable |
| `OperationRef` | closed `CREATE`或`REPOSITORY` scope；后者同时携带RepositoryId |
| `ArtifactId/ArtifactRef` | server-generated、repository-bound、带manifest/expiry |
| `CommitId` | repository-scoped provider-generated opaque immutable token |
| `IdempotencyKey` | caller-generated opaque value；不得由server静默生成不可复用key |
| `CallerIdentity` | deployment-assigned stable identity；credential轮换不改变identity |
| `RefName` | caller-selected case-sensitive restricted ASCII segmented name |
| `CurrentTableGenerationId` | current table latest-state equality token |
| `CurrentCatalogGenerationId` | current catalog equality token |
| cursor | opaque、HMAC保护、最长8 KiB、15分钟TTL；不是durable identity |

Client不得解析UUID时间、CommitId/provider格式、cursor、storage key或path。所有
public response禁止包含server path、Dolt/SQLite目录、run directory、CLI command、
file descriptor或internal network locator。

`RefName`总计不超过255 ASCII bytes，单segment不超过63 bytes；禁止空segment、
`.`、`..`、control character、backslash和reserved internal namespace。
Mutable ref可显式checked或LWW更新；immutable ref创建后不得改绑，删除后同名
immutable ref也不得绑定其他commit。Protected/internal/operation ref不能使用LWW。

## 4. Public surface

HTTP使用direct-resource `GET`与operation-specific closed action `POST`。禁止
generic `/execute`、command bag或SQL endpoint。Public v1至少包含：

```text
Service:
  GetServiceCapabilities
  GetServiceResourceLimits
  livez / readyz

Repository lifecycle and policy:
  CreateRepository
  GetRepository
  GetRepositoryPolicy
  UpdateRepositoryPolicy
  GetRepositoryResourceUsage
  GetOperatorHealth
  GetOperation

Artifact:
  UploadArtifact
  DownloadArtifact

Versioned metadata/read:
  ResolveRef
  GetCommit
  GetCatalog
  StreamTableRows
  ExportTable
  DiffRefs

Versioned mutation:
  SubmitImport
  VerifyCommit
  CreateRef
  CreateImmutableRef
  CompareAndSetRef
  SetRef
  DeleteRef

Current:
  GetCurrentCatalog
  GetCurrentTable
  StreamCurrentTableRows
  ExportCurrentTable
  CreateCurrentTable
  ReplaceCurrentTable
  ApplyCurrentTableMutations
  SubmitCurrentTableMutationBatch
  DropCurrentTable

Cross-store inventory:
  GetTableInventory

Maintenance:
  PlanGarbageCollection
  ExecuteGarbageCollection
  CreateBackup
  RestoreRepository
  ActivateRestoredRepositoryPolicy
  InspectRepair
  ResumeRepair
  PlanDeleteRepository
  ExecuteDeleteRepository
```

成功使用endpoint-specific closed schema并携带`wire_schema_version`。接受前failure
使用`application/problem+json`和typed `FailureDescriptor`；接受后的状态、结果和
failure由`GetOperation` representation拥有。HTTP status、message和`detail`不决定
retry或effect。

未知optional field可以忽略；未知stable code按已知category/recovery/effect安全
降级；未知recovery/effect必须fail closed，不自动重放mutation。改变既有field、
closed enum、code或effect语义是breaking change。

## 5. Common request policy

Mutation必须携带caller `IdempotencyKey`。Idempotency scope为
`CallerIdentity × RepositoryId/incarnation × Action × IdempotencyKey`；Create使用
service/create scope。Request的versioned canonical digest覆盖所有semantic input，
包括artifact digest、concurrency mode和verification level。Same key/same digest
返回原result；same key/different digest为collision，不执行新effect。

Mutable write必须显式且无default地选择：

```text
concurrency_mode =
  CHECK_EXPECTED(expected_commit_or_generation)
  | LAST_WRITE_WINS
```

`CHECK_EXPECTED`在同一effect boundary验证expected token。`LAST_WRITE_WINS`由
caller承担覆盖风险。Versioned import在两种mode下仍必须携带base CommitId；
LWW只放宽target ref publication。Create uniqueness、immutable/protected/internal/
operation ref和technical metadata不能用LWW绕过。

Async content write必须显式且无default地选择：

```text
verification_level = NONE | STRUCTURAL | FULL
```

- `NONE`：不执行content readback；journal、effect attribution、atomic publication、
  fencing和reconciliation仍强制。
- `STRUCTURAL`：从committed snapshot检查required table set、schema、row count及
  protected metadata。
- `FULL`：再流式读取全部required canonical/protected rows并检查content/ordering
  digest和ordered invariants。

`VERIFIED`只表示requested policy完成。Result、journal和audit必须记录requested/
completed level、policy version及level-specific evidence。独立`VerifyCommit`是
只读operation，不改写既有import operation或业务结果。

Read/catalog/stream/export必须显式且无default地选择：

```text
read_binding = EXACT(commit_or_generation) | LATEST_AT_START(selector)
```

LATEST在真正打开provider snapshot时resolve；async export在worker开始获取snapshot
时resolve。Response、stream、cursor和artifact必须返回resolved immutable
CommitId或current generation。同一次read保持pinned；不同LATEST请求不承诺相同
snapshot。

## 6. Logical table and data plane

Versioned与Current共享Repository logical type system、TableSchema、projection、
closed filter AST、ordering vocabulary和Arrow/Parquet mapping，但拥有独立wire
request、snapshot identity、write、idempotency和recovery语义。

V1 table/column name不超过64 Unicode scalar和256 UTF-8 bytes；每表不超过1024
columns。Public index只允许declared primary key；不提供secondary-index management。
Filter AST只支持bounded `eq/ne/lt/lte/gt/gte/in/is_null/and/or/not`，最大depth 16、
nodes 256、IN values 1000。禁止function、aggregate、subquery和join。

Public ordering不使用provider default collation：

- string：有效UTF-8 binary/code-point order；
- binary/BIT：unsigned bytes lexicographic；
- numeric：数值顺序；
- temporal：logical chronology；
- boolean：`false < true`；
- 每项显式ASC/DESC与NULLS FIRST/LAST。

Direct row delivery使用Repository-owned framed Arrow IPC：

```text
STREAM_HEADER
ARROW_BATCH*
CHECKPOINT*
STREAM_END | STREAM_ERROR
```

Header绑定repository、store、resolved snapshot、table、declared schema/schema
digest和query options。STREAM_END包含此前frames的raw SHA-256和最终row count；
缺失或mismatch表示incomplete。Arrow frame uncompressed最大64 MiB，server target
batch不超过8 MiB；v1不使用HTTP gzip或Arrow IPC compression。

Cursor绑定repository、store、resolved snapshot、table、schema/projection/filter/
order digest、wire version、next position和expiry。只有deterministic total order
提供cursor；primary key必须是最终tie-breaker。Keyless table不提供resumable
cursor。Current cursor只在generation仍current时有效；需要跨mutation保留结果时
使用export artifact。

Export为durable async operation，v1生成ZSTD Parquet ArtifactRef。DiffRefs由caller
显式选择framed Arrow stream或Parquet artifact。`RepositoryRawDiff`只表达provider
可完整证明的technical added/removed/modified；不能表达业务comparison。无法完整
归一时返回table-level `UNSUPPORTED`且不返回partial records，caller回退为读取两个
exact commits。

Direct stream使用`provider reader -> bounded RecordBatch buffer -> HTTP writer`
backpressure chain。Disconnect/deadline/cancel关闭reader并清理未发布bytes。未
accept的read停止；已accept的durable operation不因client断连取消。Direct stream
idle timeout为60秒、最长1小时。

## 7. Artifact and import

V1 artifact ingress只允许authenticated repository-bound one-shot streaming
upload；不接受URL、URI、redirect、host path、FD、bucket locator或anonymous
presigned URL。Caller声明media、size、raw digest、content contract、intended
action和idempotency key；server增量测量并验证。完整close、size/digest、closed
media/package manifest通过后才atomic publish ArtifactRef。

Upload断连/restart不发布partial artifact；caller用原key完整重传。Publish后response
丢失时same key/same digest返回原ArtifactRef。V1不提供multipart、parallel、range
resume或download Range；download重新认证、授权并检查expiry。

多文件package必须manifest-first，拒绝absolute/traversal、duplicate、symlink、
hardlink、device/FIFO、NUL、unknown required entry，并限制compressed/expanded
bytes、entry count和100:1 expansion ratio。

`RepositoryImportArtifact v1`内容、media/package、manifest、digest和canonical SQL
replay grammar由
[Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
唯一规定。Service只接受该registered content contract，增量执行owner schema、
grammar、binding和resource validation，并直接bounded消费已发布artifact；不先
转换为全表Python objects、JSON或第二份等价SQL。

`SubmitImport`至少绑定：

```text
RepositoryId + RepositoryIncarnationId
base CommitId
target RefName
concurrency_mode
ArtifactRef + artifact/content digest + content contract version
verification_level
IdempotencyKey
```

成功result至少返回result CommitId、target publication evidence、requested/
completed verification、level-specific evidence digest/ref和OperationRef。

Current bulk/Create/Replace的input artifact为versioned Arrow IPC，adapter按bounded
RecordBatch验证并batched bind至SQLite staging/shadow boundary；禁止全表
`to_pylist()`或普通JSON。Durable export按batch写Parquet staging，完整close、
manifest/hash/size/schema通过后才publish。

## 8. CurrentTableStore

Current只保存latest state，不提供历史generation查询。Catalog和每张table具有
独立generation。Caller可读取descriptor/catalog并显式选择EXACT或LATEST_AT_START；
EXACT旧generation在mutation后返回stale，不读取历史。

`TableMutationBatch`只作用于一张table，closed variant覆盖insert、update、upsert和
delete；batch all-or-nothing。任一duplicate/missing/existing/schema/key/constraint
conflict使整batch失败且generation不变。V1没有BEST_EFFORT或partial prefix commit。

小型`ApplyCurrentTableMutations`受4 MiB、1000 operations、100000 scalar cells
硬限制，同步返回resulting generation。Rows、generation、request digest、
idempotency result和effect marker在同一SQLite transaction提交；response loss后
same key返回原result。该路径不增加verification level或全表scan。

`CreateCurrentTable`、`ReplaceCurrentTable`、`SubmitCurrentTableMutationBatch`和
schema replacement为async operation并显式选择verification level。`DropCurrentTable`
没有content verification，但仍使用transaction/idempotency/effect evidence。
每次operation只mutation一张Current table，不提供cross-table transaction。

Async Current write由control journal记录PREPARED/EFFECT_STARTED；Current SQLite
transaction原子提交data、generation、operation/idempotency/request digest和effect
marker。Control推进前crash时，reconciler以Current marker恢复APPLIED，再执行caller
requested verification。Control和Current SQLite不声明distributed transaction。

## 9. Operation, journal and recovery

Public status、internal phase、effect truth和cleanup是正交字段：

```text
status:
  ACCEPTED | RUNNING | RECONCILING | SUCCEEDED
  | FAILED | CANCELLED | ATTENTION_REQUIRED

phase:
  ACCEPT | PREPARE | EXECUTE | PUBLISH | VERIFY | RECONCILE | CLEANUP

effect:
  NONE | NOT_APPLIED | UNKNOWN | APPLIED | VERIFIED

cleanup:
  NOT_REQUIRED | PENDING | COMPLETE | FAILED_ATTENTION
```

`SUCCEEDED`要求requested verification完成。Requested STRUCTURAL/FULL mismatch可
终止为`FAILED + effect=APPLIED`；持久failure evidence后释放对应store mutation
lane，禁止自动重放或回滚。该failure本身不quarantine。只有journal、internal ref、
commit marker、Current marker或provider authority相互矛盾，identity缺失，或真实
storage corruption时才进入integrity failure、store/repository unavailable和
operator repair。

Mutation acceptance持久化operation、caller/action/policy generation、idempotency、
request digest、repository/store/ref/table binding、precondition和artifact digest。
实际调用provider或publication effect前持久化`EFFECT_STARTED`与fencing identity。
State/evidence只单调推进，不覆盖旧事实。

Effect classification：

- request未accepted：`NONE`；
- PREPARED且无EFFECT_STARTED，并证明executor已停止：`NOT_APPLIED`；
- EFFECT_STARTED后缺少充分store evidence：`UNKNOWN`；
- matching commit/ref/Current marker：`APPLIED`；
- requested verification完成：`VERIFIED`。

Timeout、HTTP/provider status、process exit、lease expiry、worker disappearance或
client cancel不能单独证明NOT_APPLIED。UNKNOWN阻塞同一
`(RepositoryId, StoreKind)` mutation lane，但不阻塞另一store、其他repository或
合法pinned read。Reconciler只能按durable evidence继续、verify、repair或等待；
不得换key、artifact或executor blind replay。

Writer lease按`(RepositoryId, StoreKind)`串行mutation，并包含monotonic fencing
token/ServiceEpoch。Current与Versioned可并行；不同repository受node ResourcePolicy
约束并行。Reads使用pinned snapshot，不取得全程exclusive writer lock。

Versioned import使用deterministic private operation ref、commit metadata和target
publication evidence归因effect。Ref mutation保存before/after/current evidence；
普通ref verification不重复无关content scan。

## 10. Persisted authority and lifecycle

| Authority | Persisted facts |
| --- | --- |
| deployment config/secrets | credential映射、global actions、ResourcePolicy、backup/TLS/collector config |
| global registry SQLite | RepositoryId/storage key/lifecycle/format/create-delete operation/tombstone |
| per-repository control SQLite | ACL、async journal/idempotency、lease/fencing、recovery/maintenance evidence |
| Current SQLite | catalog/rows/generation、sync idempotency/effect marker |
| Dolt repository | versioned tables、commit/ref和provider effect evidence |
| artifact store | repository-bound published bytes/manifest/staging |
| external audit collector | audit retention/index/query |
| ephemeral memory | cache、connection、scheduler cursor、bounded buffers；不拥有durable fact |

Repository aggregate包含registry record、control、Dolt、materialized Current及仍在
retention内的artifact/evidence。Cache和scratch可重建。

Create在global registry原子保存PROVISIONING、operation/idempotency/request digest
和storage key；deterministic staging初始化control与Dolt，写identity/layout marker，
验证closure后same-filesystem atomic publish，registry推进READY/APPLIED，再由formal
path重开验证进入VERIFIED。无registry identity的目录不自动收编。

Lifecycle：

```text
PROVISIONING -> READY
READY -> RESTORING -> RESTORED_RESTRICTED -> READY
READY -> DELETE_PLANNED -> DELETING -> DELETED(tombstone)
```

Restore验证manifested aggregate并生成新RepositoryIncarnationId。Restored ACL不会
自动生效；global operator必须显式完整replacement policy后activate。Delete保留
永久RepositoryId tombstone。Identity mismatch或authority contradictionfail closed。

## 11. Retention, GC, backup and delete

Nonterminal、UNKNOWN、ATTENTION_REQUIRED和authority-conflict evidence无TTL。
Terminal完整request/journal/verification/diagnostic evidence保留30天，之后压缩为
repository生命周期内持续可由GetOperation返回的terminal record。Compact record
至少保存idempotency key hash/scope、request digest、operation/result identity、
commit/generation、effect、requested/completed verification和evidence digest；
永久compact tombstone阻止idempotency key重用。

Export/Diff result artifact由caller显式选择1小时至30天TTL，无server hidden default。
Import artifact/staging在nonterminal期间pin，known terminal后保留24小时再GC。
Quarantine evidence、immutable-name tombstone和Repository deletion tombstone不自动
过期。

Versioned GC roots包括public refs、operation/recovery refs、active read/export/
backup pins和terminal diagnostic holds。Current不保留旧generation。
`PlanGarbageCollection`返回绑定root epoch、exact roots/candidates、digest和expiry的
plan；Execute重新认证、检查current epoch/pins和maintenance barrier。Stale plan
不得部分执行。GC中断按checkpoint resume/reconcile。

Backup是quiescent repository aggregate manifest，覆盖registry identity、control、
Dolt、Current和required artifact/evidence closure。Service只提供mechanism，不拥有
backup schedule、RPO/RTO或remote backup policy。GC/purge后的数据只能由事先验证的
backup恢复，不能用image rollback恢复。

Quiescent backup request必须显式选择`REJECT_IF_BUSY`或finite`WAIT_UP_TO`，没有
implicit/unbounded wait；production ResourcePolicy限制最大wait。Backup、restore
drill和GC由deployment/operator controller外部调度，Service不内置cron或automatic
maintenance scheduler。Deployment拥有versioned schedule、RPO/RTO/SLO和数值告警
阈值；Phase 2只暴露last successful backup age、restore drill result/time、GC
eligible/estimated bytes、maintenance backlog和recovery duration。

Restore、GC和delete execute都要求closed operator action、current authorization、
exact plan、非空reason、checkpoint和evidence。Service不实现双人审批、MFA或业务
审批。

## 12. Authentication, authorization and input safety

`auth_mode = DISABLED | STATIC_BEARER`。DISABLED仅允许explicit dev/test；
production必须STATIC_BEARER并经deployment-owned TLS ingress，否则fail readiness。
Bearer格式为`<key-id>.<random-secret>`；secret file映射stable CallerIdentity并保存
高熵token digest，constant-time验证。Current/next credential支持简单轮换。
Service不拥有OIDC/JWKS、mTLS issuance或certificate lifecycle。

Authorization default-deny：

```text
CallerIdentity × RepositoryId × closed Action
```

Deployment config只保存repository create/restore/break-glass等global actions。
Per-repository control SQLite保存versioned concrete action grants；不保存role、
wildcard、condition、table/row/column ACL。Create显式提供initial grants。
Policy update使用expected policy generation和idempotency，并在同一control
transaction提交new generation/result。

Unauthenticated返回401；authenticated principal对repository无任何access返回404；
已有repository access但缺当前action返回403。Authorization必须在provider、path、
artifact或stream打开前完成。GetOperation/download等后续访问按current ACL重新
授权；accepted operation按acceptance policy snapshot完成/reconcile，不因普通ACL
撤销自动取消。

Service不接受caller URL/path/FD、arbitrary SQL/DDL、archive unsafe entry、unknown
required media/field/enum或unbounded parser input。Control JSON最大1 MiB。Upload
最长2小时；idle timeout 60秒。所有size/count检查增量执行，不先完整buffer。

普通log/trace/metric/error/audit禁止row/patch value、filter literal、artifact bytes、
credential/secret、SQL/CLI command、internal path和unsanitized stack。Audit记录
metadata、identity、digest、before/after token、counts、effect和timing。

## 13. Resource and isolation contract

Production必须配置finite ResourcePolicy，至少覆盖：

- single artifact compressed/expanded bytes、tables/rows/package entries；
- per-repository data/artifact/staging quota；
- node disk high/critical watermark；
- active upload/stream/async operation/Dolt runtime；
- per-caller/per-repository queue depth；
- verification/readback byte budget；
- durable control/recovery emergency reserve。

Effective limits通过typed service capability公开；caller只能预检，measured usage是
authority且request不能提升limit。Malformed/oversized为400/413；caller/repository
admission为429并带Retry-After；node/disk capacity为503，均在acceptance前不创建
operation。Critical safety watermark可在effect未开始时终止为NOT_APPLIED；
EFFECT_STARTED后仍按evidence-first recovery。

V1是single trust-domain内部服务。RepositoryId提供logical isolation、quota和
故障归属，不宣称同root内抵御恶意tenant。互不信任tenant必须使用独立service/
durable root。`GetRepositoryResourceUsage`只投影已有accounting/scheduler事实，
不扫描全库、不启动idle runtime、不保存history或声称精确共享CPU/memory归因。

## 14. Runtime and deployment

V1 production topology是single ASGI process、single durable-root owner和进程内
bounded scheduler；不使用Celery、Redis、external queue、ORM或generic provider
framework。Process取得durable-root OS exclusive lock后递增ServiceEpoch；失锁立即
not-ready并终止。Deployment还必须保证single-writer volume和无重叠更新。

`DoltRuntimeCoordinator`按活跃repository bounded启动：

- 无active server时可使用offline `dolt sql -f` canonical replay；
- 有active repository-scoped sql-server时该owner执行所有访问；
- 同repository禁止CLI/server并发打开；
- runtime只在无reader/writer/maintenance/recovery pin时evict。

Startup验证build/storage identity和global authority，增量调度reconciliation，不
遍历打开全部Dolt。`livez`只表示process/event loop；`readyz`表示可安全接纳至少
部分workload。单repository quarantine不使整个service unready。

Async writer lease初始TTL为30秒并每10秒renew；同process调度使用monotonic clock，
持久wall timestamp只用于诊断和跨restart evidence排序。30/10秒可由versioned
capacity evidence调整，但renew必须显著短于TTL且config validation fail closed。
TTL到期或ServiceEpoch变化都不自动释放UNKNOWN；takeover仍先隔离旧executor并检查
store evidence。

SIGTERM使service立即not-ready并拒绝新mutation、upload、long stream和maintenance。
Grace period默认60秒，production必须显式配置为10–300秒。Accepted operation停在
durable checkpoint；EFFECT_STARTED后不能伪装cancel。Grace到期后退出，由新process
reconcile。WAL checkpoint、runtime drain和非结果cleanup均best effort，不能无限
延长shutdown。

Startup control scan初始registry page size为100，最多并发打开4个repository control
DB；普通scan不启动Dolt runtime。单operation recovery backoff为
`1s/5s/30s/2m/5m`，之后上限5分钟；连续10次失败或30分钟没有新evidence进入
ATTENTION_REQUIRED。Operator recheck复用原operation/reconciler，不创建新effect。

Reconciliation scheduler按API on-demand、due nonterminal和background clean scan
三类调度。Clean repository默认15分钟加`±20%` jitter再次eligible。初始4个
control-scan permit中，background backlog存在时至少保留1个给oldest-last-scanned；
其余优先API/due work。Cursor/cache可重建且不是authority；任何priority class都
不得使background永久饥饿。Production可按capacity evidence调整finite cadence、
jitter和permit，但必须保持oldest-first eventual scan。

首个verified platform只包括`linux/amd64` OCI、pinned glibc Debian-family base、
Python/uv/locks、Dolt 2.1.11 binary digest和通过验证的POSIX local volume profile。
Unsupported OS/architecture/filesystem capability在startup fail readiness。未来
platform必须独立完成image、filesystem crash/lock和container exit evidence。

Production service以non-root、read-only rootfs、independent scratch/durable/backup
mount、dropped capabilities、no-new-privileges、无Docker socket和default-deny
egress运行。Service plaintext listener只在isolated internal network；client只能
经pinned deployment-owned TLS ingress访问。

## 15. Observability

Service输出structured JSON log、W3C trace context、optional OTLP、low-cardinality
OpenMetrics和versioned typed `security_audit` stdout event。RepositoryId不能作为
Prometheus label；可在授权log/trace/audit中作为field。

Audit event在已解析repository时携带RepositoryId、caller/action/operation/result/
digest关联字段。External collector拥有持久化、索引、retention和查询；Service不
新增audit database/query endpoint/outbox。Collector故障告警但不阻塞普通request，
且不宣称零丢失合规delivery。

RuntimeBuildIdentity与EnvironmentFingerprint分离。Capacity/benchmark按provider、
verification、policy、dataset和environment建立独立series，不混合不同rigor的
结果。

## 16. Conformance and compatibility

唯一Phase 2 gate class：

```text
P2-PR-STATIC
P2-PR-CONTRACT
P2-PR-RECOVERY
P2-PHASE-EXIT-CONTAINER
```

Semantic-core cells在Fake/Local/Remote required；real storage/provider在Local/
Remote required；HTTP/auth/stream/process/container只在Remote required。所有
public v1 behavior至少由Local和Remote共同证明。Required cell不得skip、xfail、
UNSUPPORTED、advisory或automatic retry。

Required matrix至少覆盖：

- NONE/STRUCTURAL/FULL成功和对应mismatch；
- CHECK_EXPECTED成功/stale与LWW覆盖；
- exact/latest-at-start pinned reads；
- upload/stream integrity、backpressure、cancel/deadline；
- idempotency collision、accept/effect/publish/verify crash；
- UNKNOWN、restart、lease/fencing、Current transaction marker；
- GC/backup/restore/delete checkpoints；
- authorization/input/resource/redaction/container negatives；
- N/N-1 additive wire compatibility和future persisted-state refusal。

Gate attempt immutable，result只允许PASS/FAIL/BLOCKED。BLOCKED仅表示semantic
execution前的外部环境不可用；assertion failure为FAIL。Retry创建新attempt并保留
supersession history。

Phase exit只聚合同一clean exact candidate commit构建的contracts/client/service/
conformance artifacts、images、locks和environment evidence；任一tracked change
产生新candidate并重跑全部Phase 2 gates及完整Phase 1 correctness/native regression。

## 17. Reopen conditions

以下变化必须由owner显式升级contract/ADR并重跑对应gate：

- server-owned persistence routing、cross-store transaction或业务语义；
- multi-node/shared-writer durable root；
- untrusted tenants共享root；
- new import/export codec、provider或platform；
- resumable/multipart artifact transfer；
- data-level ACL或external policy authority；
- service-owned durable audit query/delivery；
- historical Current generations、secondary index或general query；
- verification、concurrency、read binding或effect classification语义改变。

局部helper、private module、non-semantic batching或measurement-driven provider优化
只要不改变public/persisted/effect contract，不要求升级semantic version。

## 18. Related authority

- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Phase 2 Implementation Design and Delivery Plan](../plans/phase-2-implementation-design-and-delivery-plan.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [External Effect and Recovery](external-effect-and-recovery.md)
- [Fixture Oracle and Conformance](fixture-oracle-and-conformance.md)
- [Performance Measurement and Baseline](performance-measurement-and-baseline.md)
- [ADR 0008](../adr/0008-generic-dual-store-and-caller-selected-rigor.md)
