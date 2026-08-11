# P2 Versioned Repository Implementation Design

状态：Accepted — P2-R5 functional exit complete, P2-R6 ready

日期：2026-08-02

更新：2026-08-09（P2-R5 design freeze）

适用范围：Phase 2 `P2-R1`至`P2-R6`

Owner：Backend vNext Architecture（实施分解）；Repository Service Contract（public、
persisted与runtime语义）

## 1. Outcome

Phase 2交付一个独立内网、Dolt-backed、single-owner的Versioned Repository Service。
设计已覆盖runtime feasibility、HTTP shell、同步create/upload、异步import、
commit-pinned read、Remote client、恢复和运维闭环。P2不需要再次讨论总体设计即可从
P2-R1开始实现；每轮只能在前一轮exit通过后进入。

## 2. Authority order

冲突时按以下owner处理，不由本计划复制第二套规范：

1. [Repository Service Contract](../contracts/repository-service.md)：wire、状态、
   verification、CAS、layout与recovery。
2. [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)：
   package与business/Repository语义分界。
3. [External Effect and Recovery](../contracts/external-effect-and-recovery.md)：T1/T2/T3与
   business occupancy。
4. [P2-R1 Runtime and Provider Feasibility](p2-r1-runtime-provider-feasibility.md)：provider
   matrix、probe与选择。
5. 本文：R2-R6组件切分、实现顺序和组合验收。

## 3. Accepted facts and assumptions

- 单一信任域、global bearer、single ASGI process、single durable-root owner。
- package通常10–100 MB，边界接近200 MB；日常10–200、极端1,000 imports/day且分散
  在多个Repository；同Repository通常低频写。
- 首版部署为Linux container与single-node local/block-backed durable filesystem。
- Dolt exact version和offline CLI/sql-server provider由P2-R1 matrix确定。
- P2-R5已首次激活Repository `/v1/` wire；激活前无published wire或production durable
  data，因此不保留旧compatibility adapter。

## 4. Scope and non-goals

V1只交付create、repository-bound artifact、Versioned import/operation/ref/catalog/row
stream、health/readiness和private recovery CLI。不交付CurrentTableStore、ACL、
multi-node writer、multipart/resume、object storage、public repair/delete/backup、
standalone ref CAS、table/schema CAS、partial merge/rebase、diff/export或业务语义。

未来Current使用`current/<repository_key>/`平级component、独立SQLite data file与
`/current/` routes。Control DB固定在`service-state/`，不占用Current namespace，因此
现有component-first layout不会堵塞未来非版本库扩展。

## 5. Component topology and dependency direction

```text
gateway-repository-contracts <- gateway-repository-client <- Backend adapter
gateway-repository-contracts <- gateway-repository-service -> Dolt/filesystem/SQLite
```

Contracts只含薄Pydantic DTO与enum；Client不import Service；Service不import Client、
Backend、Shared Kernel或canonical corpus。Service内部按`http -> application -> ports ->
adapters`单向组织，provider、filesystem、control store均为private adapter。

## 6. Durable layout and provider

使用Repository contract的component-first layout与publication barrier。P2-R1在
disposable root验证root lock、same-filesystem rename/fsync、Dolt create/replay/marker/
catalog/pinned read/Arrow stream、restart与fault point，并按simplicity-first规则选择
offline CLI或sql-server。P2-R1不得创建production control DB或激活HTTP业务route。

## 7. Service lifecycle and configuration

P2-R2 composition root按顺序：load/validate settings → validate layout marker → acquire
root lock → migrate/open control DB → verify selected provider capability → become ready。
P2-R2不创建import worker pool；bounded import worker lifecycle在P2-R4激活。Shutdown先
停止intake，关闭cursor/provider/control DB，最后释放root lock；provider子进程必须
terminate/wait/reap。Production缺token、layout版本过新、lock被占用、DB不可迁移或
provider不可用均fail closed。

## 8. Authentication and request boundary

Production bearer优先secret file，env只用于dev/test；不hot rotate。`healthz`未认证，
`readyz`由部署网络保护，其余route验证同一bearer。Server生成request ID并统一
SimpleError；日志不得包含token、idempotency raw key、replay SQL、host path或完整
sensitive row。

## 9. HTTP and DTO activation

P2-R2只激活healthz/readyz与共同HTTP middleware，不注册stub业务route。P2-R3激活
create/upload并首次建立真实`/v1/` OpenAPI；P2-R4增加import/operation，P2-R5增加
ref/catalog/rows。每个route都与真实service behavior、client和integration test同轮
出现。Upload使用raw body与四个必需header，不使用multipart。Framework validation也
映射到统一error。Wire兼容由`/v1/`拥有，不为DTO增加独立v2 alias或compatibility shim。

## 10. Control persistence

唯一control DB为`service-state/repository-service.sqlite3`：WAL、
`synchronous=FULL`、foreign keys、busy timeout、transactional forward-only
`user_version` migration。保存最小create/upload PENDING/SUCCEEDED ledger、durable
import queue/operation/result、idempotency fingerprint和recovery audit；不保存table
rows。Operation和idempotency metadata在Repository lifetime保留。

## 11. Synchronous CreateRepository

在SQLite写PENDING并分配ID后，在server-owned staging初始化Dolt、initial empty commit
与main，执行publication barrier，再写SUCCEEDED。可见性要求DB SUCCEEDED与完整目录
同时存在。Startup用layout marker恢复PENDING；SUCCEEDED但目录缺失使ready失败。
Same key/same fingerprint重放原201/body，mismatch为409。

## 12. Synchronous UploadArtifact

Raw body直接bounded streaming到staging，增量校验Content-Length与SHA-256；不完整、
超限或hash不符不发布。PENDING先于filesystem effect，atomic rename后SUCCEEDED；
startup以ready file的size/SHA reconcile。Same key重放原201/body。Client仅在source可
rewind/reopen时自动完整重传，不隐式spool非rewindable source。

## 13. Package validation

Media type与`manifest.json + replay.sql` tar+zstd shape固定为v1。Extraction在流式过程
限制entry count、单entry与total expanded size，拒绝path traversal、duplicate、link、
device与extra entry。默认compressed 256 MiB、expanded 4 GiB，均可配置。Manifest只
含structural projection和opaque CanonicalizationManifest digest；Repository不解析
business digest。

## 14. Async import and publication

接受请求前持久化QUEUED并返回202。每Repository单writer，跨Repository bounded
workers。`expected_commit_id`始终必填，既是parent也是main CAS expected；不得关闭CAS。
Worker从expected main创建private operation ref，在其上replay、commit marker、
verification，再recheck main并CAS publication。Verification失败不改变main；
publication ambiguity进入MANUAL_RECOVERY_REQUIRED。

## 15. Verification and SQL/Arrow policy

Caller选择`NONE | STRUCTURAL | FULL_SCAN`，默认STRUCTURAL。所有level都强制package
safety、marker、parent和target CAS；FULL_SCAN只证明全部user table可分批读取、type
conversion成功且row count匹配，不重算business digest。

Unknown type选择`REJECT | STRINGIFY`，默认REJECT。STRINGIFY只把未知列转换成
nullable Arrow large_string并标记原始SQL type与lossy，不影响已知type exact mapping，
不承诺跨Dolt版本文本或digest稳定。Import request、operation和result保存/回显两个
policy；Backend T3核对requested等于completed。V1不提供table/schema CAS。

## 16. Commit-pinned reads

Resolve只接受main并返回opaque CommitId。Catalog和row stream只接受immutable
CommitId；row table name是query parameter。Stream为raw Arrow IPC RecordBatch，内存
有界、cancel/disconnect关闭provider；不保证row/batch顺序。Row read可独立选择unknown
type policy，默认REJECT。

R5固定三个无body的GET endpoint：

```text
GET /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows
    ?table_name=...&unknown_type_policy=REJECT
```

RepositoryId在wire层按UUID验证；ref只接受literal `main`；CommitId保持repository-scoped
bounded opaque token，不增加Dolt hash或UUID grammar。Table、column和primary-key name按
Repository contract的1..64 code-point exact identifier规则验证。Public read先检查
Repository visibility和CommitId existence，再用literal CommitId执行catalog/table
`AS OF`查询；branch在请求期间移动不改变已绑定read。Import的candidate catalog仍要求
唯一parent，public catalog另用不要求parent的`catalog_at(commit_id)`，因此initial empty
commit也可读取。

Arrow mapping采用request/table-scoped immutable compiled plan，不使用caller SQL spelling
驱动的process-lifetime cache。每个plan包含per-column converter、copied immutable metadata
和expected Arrow schema；每表只编译一次。Raw row只转换为nominal `NormalizedRow`一次，
其normalized logical payload用于row/byte batch accounting，RecordBatch builder不再次
normalization，也不暴露`already_normalized` bool。FULL_SCAN与public stream共享同一安全
plan模型但各自创建plan；每批仍比较field count、name、type、nullability和metadata并累计
row count。Converter必须fail closed处理non-null NULL、MEDIUMINT 24-bit range、unsigned、
decimal、temporal、BIT width/high bits、binary和malformed value；错误只保留table、column和
SQL type，不保留raw value。

Arrow response固定为`application/vnd.apache.arrow.stream`。Async response generator通过
容量为1的bounded bridge消费owned non-daemon worker thread；worker拥有Arrow writer、
provider iterator和Dolt subprocess。Disconnect/cancel设置显式event，ProcessStream在有界
poll周期内观察event并执行TERM/KILL/wait/reap。正常结束输出Arrow EOS；response开始后的
provider/conversion failure或cancel保持truncated stream，不追加JSON。空表输出schema+EOS；
单个normalized row超过4 MiB target时独占一个batch，仍受64 MiB encoded-line safety cap；
不得整表materialize。

Read-specific status/code和response开始前/后的失败边界由Repository Service Contract §13
拥有。R5使用stdlib bridge，默认不新增Service production dependency；若实际实现触碰
Service lockfile、Dockerfile、Compose或container harness，立即触发execution checklist
§1.1的提前container gate。

## 17. Remote client semantics

Client提供typed async façade和Backend Port adapter。GET只对network/502/503做bounded
retry；create/import用同一idempotency key重试；upload只对可rewind/reopen source自动
完整重传。202始终返回原operation ID，当前状态由GetOperation查询。Client保留HTTP
status、stable code、request ID，不推断server path或effect taxonomy。

R5完成create、upload、submit import、get/wait operation、resolve、catalog和row stream的
全部V1 façade。Polling使用monotonic deadline与capped backoff。Row response返回async
context-managed raw `ArrowIpcByteStream`，拥有HTTP response/client close；只在任何body byte
暴露前允许stream-open retry，暴露后不重试。Client production不依赖PyArrow；error body与
header request ID不一致、success/error body malformed或Arrow media type错误均为protocol
error。

Contract-owned fixture consumer位于Repository Client测试边界，只依赖public contracts、
Remote client和test-only Arrow decoder。Service测试以外部进程启动consumer，不import
Client package。Consumer使用两个小型opaque package完成create → upload → import → poll →
read C1 → import C2 → read C1/C2，证明old/new commit immutable；断言不依赖row/batch
ordering，不拥有Backend schema、business digest、Submit lifecycle或verification policy。

## 18. Recovery and operator actions

Startup重排QUEUED；遗留RUNNING先查marker/ref，唯一matching published commit补记成功，
无commit且artifact完整时原key自动重放一次，正常失败不隐藏重试，矛盾进入manual。
Private CLI要求service停止并持有root lock，默认inspect；`--apply`只能补记SUCCEEDED或
确认NOT_PUBLISHED/FAILED并写audit，不得force main、执行任意SQL或删除history。

## 19. Capacity, retention and disaster recovery

默认8 uploads、4 import workers、per-repository single writer、24h ordinary failed/
orphan artifact TTL，保留`max(5 GiB, 10% volume)`加P2-R1测得import headroom。成功
result durable后删package；RUNNING/manual artifact不删；Versioned commits和control
metadata永久保留。Backup仅用停止service/provider、checkpoint WAL、quiesce whole root
后的volume snapshot；restore必须恢复整个匹配root。

## 20. Observability, tests and delivery rounds

P2只要求structured logs、health/readiness、request/operation ID、duration/size/result
code和普通container diagnostics；不提前建设metrics platform或audit subsystem。

```text
P2-R1 provider/runtime feasibility
P2-R2 service shell/auth/control DB lifecycle
P2-R3 synchronous create/upload
P2-R4 async import/CAS/verification/recovery
P2-R5 commit-pinned read/client/fixture-consumer e2e
P2-R6 cleanup/capacity/snapshot/container operational closure
```

每轮执行、验证和commit boundary见
[P2 Execution Checklist](p2-versioned-repository-execution-checklist.md)。P2-R5的冻结设计、
allowed paths、green stages、测试矩阵和R6 handoff见
[P2-R5 Commit-pinned Read Staged Execution Plan](p2-r5-commit-pinned-read-execution-plan.md)。

## 21. Risks, reopen conditions and P3 timing

已知风险包括production retest尚未完成、STRINGIFY文本受Dolt版本影响、single-node
恢复依赖operator且无RPO/RTO保证。这些是实现/测量风险，不是未决架构问题。P2-R1
v8 formal 已选择Candidate A offline CLI作为默认 provider，Candidate B保留但默认禁用；
若出现untrusted tenant、
shared writer、partial merge/table CAS、object storage或Current真实consumer，按Repository
contract reopen condition另行设计。

P3完整设计不穿插P2。P2-R5只运行contract-owned fixture consumer以验证公开边界；
P2-R6全部exit通过后，才开始P3 capability的完整`grill-me`/design阶段。此时P3可依据
真实P2 client与stream行为选择各业务use case的verification policy，而不反向预建P2
feature。

结论：整个P2在设计层面完备，P2-R1 v8 exit=`go`，P2-R2至P2-R4 exit均已通过；
P2-R5 functional exit complete，`p2_r6_ready=yes`；完整handoff见
[P2-R5 Commit-pinned Read Staged Execution Plan — P2-R5-S7 final handoff — 2026-08-12](p2-r5-commit-pinned-read-execution-plan.md#p2-r5-s7-final-handoff--2026-08-12)。
R5与R6仍必须遵守顺序gate，不得用R4历史镜像证明R5代码，也不得在R6关闭container与
production retest前宣告Phase 2 complete。
