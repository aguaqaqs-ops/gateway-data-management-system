# P2-R4 Async Versioned Import Detailed Implementation Design

状态：Accepted — Implementation Ready

日期：2026-08-06

适用范围：`P2-R4 — Async Versioned Import`

Owner：Repository Service（R4内部实现、持久化、恢复和交付边界）

Owning contracts：

- [Repository Service Contract](../contracts/repository-service.md) §§5–6、§§9–12、§14.1；
- [External Effect and Recovery Contract](../contracts/external-effect-and-recovery.md)；
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md) §6、§6.1；
- [P2 Versioned Repository Implementation Design](p2-versioned-repository-implementation-design.md) §§13–15、§§18–20；
- [P2 Versioned Repository Execution Checklist](p2-versioned-repository-execution-checklist.md) §§1–2、§6；
- [DX Cross-Phase Interface Reconciliation](dx-cross-phase-interface-reconciliation.md) §§3–4；
- [P2-R1 v8 Formal Go Decision](p2-r1-v8-go-decision-2026-08-05.md)。

分阶段执行和逐阶段实现提示词见
[P2-R4 Async Versioned Import Staged Execution Plan](p2-r4-async-versioned-import-execution-plan.md)。

本文是上述正式authority的从属实现设计，只固定R4内部结构、组合顺序、fault seam和
交付方法。若本文与owning contract冲突，以owning contract为准并暂停实现；不得用本文
覆盖public、persisted或cross-owner语义。

## 1. Outcome and baseline

P2-R4交付Repository Service唯一的异步业务operation：受信Backend上传固定
`tar+zstd` package后，通过`SubmitVersionedImport`取得durable operation ID，worker在
private operation ref上replay、commit、verify，再以mandatory expected-value CAS发布
`main`。Caller通过`GetOperation`取得当前状态、最终result或stable failure。

设计检查基线为：

```text
repository = /root/gateway-data-management-system
branch = phase1/gate-ownership-repair
start_sha = a0ef723e0a8043beee09a0b0cb4f1408db5ffc5e
worktree_clean = yes
previous_round = P2-R3
previous_round_exit = pass
selected_provider = candidate_a_offline_cli
control_db_user_version = 6
```

P2-R3 gate不在R4重复证明。只有发现可复现且会破坏R4 prerequisite的证据时才暂停并
报告；不得覆盖或回退后续用户改动。

## 2. Fixed scope and explicit non-goals

R4 allowed scope：

- import和operation contracts、headers、HTTP routes与OpenAPI；
- SQLite durable import operation、idempotency、result/error和recovery audit；
- bounded package validation和server-owned extraction staging；
- global bounded workers与per-repository single writer；
- Candidate A private ref、operation marker、expected parent和main publication CAS；
- `NONE | STRUCTURAL | FULL_SCAN`与`REJECT | STRINGIFY`；
- startup reconciliation、最多一次automatic replay和graceful shutdown；
- private stopped-service/root-lock admin CLI；
- success artifact cleanup、ordinary failure TTL eligibility和manual retention；
- readiness、simple capacity admission、structured diagnostics、fault matrix和Compose gate。

R4明确不实现：

- P2-R5 resolve/catalog/row routes、Repository Client import/read纵切或fixture consumer；
- Backend/Phase 3 consumer、SubmitAttempt或Archive业务实现；
- business digest、canonical equality或Repository侧digest重算；
- table/schema CAS、LWW、public force ref、独立publication API或rollback；
- generic journal、lease、fencing、epoch或`UNKNOWN/APPLIED/VERIFIED`状态机；
- public admin/recovery API或任意SQL endpoint；
- gzip/gz、multipart、resume、URL、host path或object storage package输入；
- TTL scheduler、完整R6 capacity/backup/snapshot closure；
- Candidate B、Current store或Phase 3 capability。

## 3. Authority and production boundary

R4 production path可以复用现有经过R2/R3验证的窄边界：

- `DurableLayout`和server-generated repository key；
- `DurableRootLock`；
- `ControlStore`的WAL/FULL/foreign-key/forward-only migration lifecycle；
- `DoltRunner`的exact binary、allowlisted environment、`shell=False`、process group、bounded
  output、timeout和wait/reap规则；
- `OfflineCliCapabilityGate`；
- free-disk admission与filesystem publication primitives；
- SQL type normalization、Arrow mapping与bounded record batches；
- bearer、request ID、readiness和`SimpleError` HTTP boundary；
- P2-R3 artifact identity、ready-file visibility和upload integrity evidence。

下列文件和路径只属于P2-R1 probe/diagnostic，不得被R4 production orchestration导入：

```text
gateway_repository_service.workflow
gateway_repository_service.workflow_worker
gateway_repository_service.fixtures
gateway_repository_service.matrix
gateway_repository_service.target_gate
repository-probe Compose profile
P2-R1 benchmark/formal artifact paths
Candidate B SqlServerProvider
```

现有`providers.py`聚合了probe measurement、ad-hoc catalog解析和两个候选provider，不能
整体充当R4 authority。R4应建立production-owned import port/adapter；需要共享已验证
primitive时提取窄helper，并让probe和production分别依赖该helper，禁止production反向
依赖workflow、fixture或benchmark路径。

## 4. Public HTTP and DTO shape

激活routes固定为：

```text
POST /v1/repositories/{repository_id}/versioned/imports
GET  /v1/repositories/{repository_id}/operations/{operation_id}
```

Submit必需header：

```text
Idempotency-Key: 1..255 UTF-8 opaque string
```

`SubmitVersionedImportRequest`是closed JSON model：

```text
repository_id
artifact_ref:
  artifact_id
  media_type
  size_bytes
  raw_sha256
target_ref
expected_commit_id
verification_policy = STRUCTURAL
unknown_type_policy = REJECT
```

规则：

- `idempotency_key`从JSON body删除，只由header传输；
- body `repository_id`必须与path一致；
- `target_ref`必须是literal `main`；
- `expected_commit_id`必填；
- `artifact_ref.media_type`必须是固定Repository import media type；
- policy使用contracts-owned `StrEnum`，Service的Arrow实现不得再拥有第二套wire enum；
- request validation、path/body mismatch和framework validation统一映射为`SimpleError`。

Submit accept和same-key replay固定返回：

```text
HTTP 202
{
  "operation_id": "<uuid>"
}
```

即使operation已经terminal，same-key/same-fingerprint仍返回原operation ID和原`202`，
不会把当前状态嵌入Submit response。Same-key/different-fingerprint返回`409`。

GetOperation固定返回`200`与closed representation：

```text
operation_id
status = QUEUED | RUNNING | SUCCEEDED | FAILED
result = VersionedImportResult | null
error = SimpleError | null
```

状态不变量：

| Status | Result | Error |
| --- | --- | --- |
| `QUEUED` | null | null |
| `RUNNING` | null | null |
| `SUCCEEDED` | required | null |
| `FAILED` | null | required |

`VersionedImportResult`固定包含：

```text
commit_id
target_ref
artifact_id
canonicalization_manifest_digest
expected_commit_id
completed_verification_policy
unknown_type_policy
```

Operation terminal failure的stable code只有：

```text
IMPORT_REJECTED
EXPECTED_COMMIT_MISMATCH
VERIFICATION_FAILED_NOT_PUBLISHED
MANUAL_RECOVERY_REQUIRED
```

本文后续的“MANUAL row/operation”均只是简写，精确定义为
`status = FAILED`且`error.code = MANUAL_RECOVERY_REQUIRED`；不得新增第五种operation状态。

HTTP request-layer仍可使用authentication、validation、not-found、idempotency、admission和
readiness code；这些code不得写进Repository operation terminal result。

Persisted operation error不绑定某次HTTP poll request，因此其`SimpleError.request_id`固定
为空。GetOperation response header使用当前poll的server-generated `X-Request-ID`；不得在每次
poll时重写durable operation error。普通HTTP error body继续回显当前request ID。

## 5. Request identity and idempotency

Import idempotency scope为：

```text
(mutation_kind = versioned_import, repository_id, SHA-256(raw idempotency key))
```

Raw key不得持久化或写日志。Internal fingerprint使用带版本前缀的deterministic binary
encoding，至少覆盖：

```text
repository_id
artifact_ref.artifact_id
artifact_ref.media_type
artifact_ref.size_bytes
artifact_ref.raw_sha256
target_ref
expected_commit_id
verification_policy
unknown_type_policy
idempotency_key_hash
```

Fingerprint不依赖JSON field order、Pydantic dump细节或Python object repr。首版前缀建议为
`versioned_import/v1\0`，变更字段解释时必须新增fingerprint版本，不得悄然改变已有row的
matching结果。

新effect admission发生在same-key lookup之后：已存在的same-key/same-fingerprint不是新
effect，不消耗新的queue slot并返回原202。新key在queue/concurrency admission、disk
headroom或provider readiness失败时不得写QUEUED。

## 6. Package and streaming extraction

Media type固定为：

```text
application/vnd.gateway.repository-import.v1+tar+zstd
```

Upload compressed-size上限继续由P2-R3 `max_upload_bytes`控制，默认256 MiB。R4读取ready
artifact时再次核对Repository scope、artifact ID、media type、declared size和raw SHA
binding；解码流同时增量计算raw size/SHA，最终不匹配即`IMPORT_REJECTED`，不得发布。

Archive必须恰有两个entry并按以下顺序出现：

```text
manifest.json
replay.sql
```

两个entry必须是regular file。拒绝：

- absolute path、`..` traversal、路径分隔变体或NUL；
- duplicate、extra或out-of-order entry；
- symlink、hardlink、directory、device、FIFO或sparse member；
- global/member PAX header、GNU longname/longlink或其他extended filesystem metadata；
- concatenated/trailing malformed archive内容；
- declared size与实际stream bytes不一致；
- 解码器未到合法EOF或任一counter越界。

实现不得调用`extractall`，也不得把完整archive或`replay.sql`读入内存。使用counted zstd
decoder和streaming tar reader，逐member复制到server-owned operation staging regular
file；文件名由Service常量决定，不直接使用archive path创建filesystem path。每次write
前检查counter，失败时关闭reader、删除可重建staging并保留原Repository artifact。
`manifest.json`可以在完整写入staging并确认不超过16 MiB后做有界内存解析。

V1不限制合法zstd frame是否启用content checksum。Checksum trailer属于compressed frame
metadata，不计入decompressed tar stream；当expanded counter恰好达到上限但decoder仍需消费
checksum trailer或frame terminator时，实现必须继续以bounded zero/one-byte output probe完成合法
EOF判定。若decoder在probe时`needs_input`且compressed artifact尚未到物理EOF，必须先读取下一
个有界compressed chunk再继续probe；只有物理输入耗尽仍未到合法EOF时才可判定frame incomplete。
任何新增decompressed output仍按越界拒绝，metadata消费不得增加decompressed counter。该probe
只在expanded budget恰好耗尽时触发；metadata应按既定有界compressed chunk推进，不得退化为逐字节
读取compressed artifact或无界递归。Required regression必须使用启用content checksum、checksum
trailer跨64 KiB input read boundary且decoder output恰好等于配置上限的合法package，防止把“需要
更多compressed metadata”误判为truncated frame。

Tar logical EOF至少包含两个连续512-byte zero blocks。为兼容stdlib `tarfile`的record padding，
第二个EOF block后允许任意数量的完整512-byte全零block；这些bytes仍计入decoder stream counter。
EOF后的partial block或任一非零byte均属于malformed trailing data并拒绝，不得把“全零”单独作为
接受partial tail的充分条件。

四类size counter必须独立：

| Counter | Default | Meaning |
| --- | ---: | --- |
| compressed artifact | 256 MiB | P2-R3 ready artifact raw bytes |
| `manifest.json` expanded entry | 16 MiB | manifest member实际输出bytes |
| `replay.sql` expanded entry | 200 MiB | replay member实际输出bytes |
| total decompressed tar stream | 4 GiB | zstd decoder累计输出，包括tar header、padding和member payload |

同时以4 GiB限制全部member payload之和。当前合法package的effective payload上限由16 MiB
和200 MiB单entry上限先行约束；4 GiB是防止decoder、padding或恶意archive放大的总安全
ceiling，不表示首版支持4 GiB `replay.sql`。

建议settings名称：

```text
max_manifest_json_bytes = 16 MiB
max_replay_sql_bytes = 200 MiB
max_total_expanded_entry_bytes = 4 GiB
max_decompressed_tar_stream_bytes = 4 GiB
```

这些是deployment configuration，不进入wire。提高`max_replay_sql_bytes`时必须同步调整
import headroom并在目标资源上重新构建/部署、运行真实Dolt、restart和fault tests后才可
声明新支持边界；超过4 GiB total ceiling必须修订formal contract并重开one-shot
streaming能力审核。

## 7. Closed manifest model

`manifest.json`必须是strict UTF-8 JSON。Parser拒绝duplicate object key，再交给closed
Pydantic model验证；不得依靠ad-hoc dict/string处理。

Shape固定为：

```text
package_version = 1
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

Validation固定为：

- top-level、table、schema和column object均`extra="forbid"`；
- table/column name为1..64 Unicode code points，拒绝NUL、ASCII control、`/`和`\\`；
- table name额外禁止leading/trailing whitespace；column name保持exact identifier规则（允许embedded space）；
- comparison exact、case-sensitive，不做Unicode normalization或case fold；
- `canonicalization_manifest_digest`是bounded opaque string，只保存和回显；
- `row_count`是非负integer，boolean不得作为integer接受；
- table name唯一并按UTF-8 canonical name bytes严格递增；
- column name在table内唯一，columns保持DDL order；
- primary key按key order，元素唯一且只能引用已声明column；
- `sql_type`是bounded normalized physical spelling；
- manifest不得携带business/source/content/ordering digest或Backend path。

Repository不重算`canonicalization_manifest_digest`，也不import Shared Kernel digest type。

## 8. Control DB v7 logical schema

R4使用一次transactional forward-only migration把`PRAGMA user_version`从6提升到7。V7不
改写现有create/upload成功语义；newer version继续fail closed。

建议新增`repository_import_operations`，一row同时拥有import idempotency identity和
operation，避免为扩展现有同步mutation CHECK而重建已经通过R3 gate的表。Logical fields：

```text
operation_id TEXT PRIMARY KEY
repository_scope TEXT NOT NULL
key_hash BLOB NOT NULL CHECK length = 32
request_fingerprint BLOB NOT NULL

artifact_id TEXT NOT NULL
artifact_media_type TEXT NOT NULL
artifact_size_bytes INTEGER NOT NULL
artifact_raw_sha256 TEXT NOT NULL
target_ref TEXT NOT NULL CHECK target_ref = 'main'
expected_commit_id TEXT NOT NULL
requested_verification_policy TEXT NOT NULL
unknown_type_policy TEXT NOT NULL

status TEXT NOT NULL CHECK four-state set
private_ref_name TEXT NOT NULL
operation_marker TEXT NOT NULL
canonicalization_manifest_digest TEXT NULL
automatic_replay_count INTEGER NOT NULL DEFAULT 0 CHECK 0..1

result_json TEXT NULL
error_json TEXT NULL
created_at TEXT NOT NULL
started_at TEXT NULL
updated_at TEXT NOT NULL
completed_at TEXT NULL

UNIQUE(repository_scope, key_hash)
```

DB constraints或transactional store validation必须强制第4节status/result/error不变量；
`result_json`和`error_json`写入前、读取后均通过contracts DTO验证。Operation ID、request
binding、policies、marker和private ref一旦插入不可改变。允许的普通transition只有：

```text
QUEUED -> RUNNING
RUNNING -> SUCCEEDED
RUNNING -> FAILED
```

Startup可以把遗留`RUNNING`保留为RUNNING并交给recovery owner，不需要新增RECOVERING
状态。Admin apply是唯一允许的terminal correction：

```text
status=FAILED, error.code=MANUAL_RECOVERY_REQUIRED -> SUCCEEDED
status=FAILED, error.code=MANUAL_RECOVERY_REQUIRED -> FAILED/ordinary stable code
```

该transition必须与recovery audit insert处于同一`BEGIN IMMEDIATE` transaction。

建议新增`repository_import_recovery_audit`：

```text
audit_id INTEGER PRIMARY KEY
operation_id TEXT NOT NULL
action TEXT NOT NULL CHECK INSPECT_APPLY_SUCCESS | INSPECT_APPLY_NOT_PUBLISHED
prior_status TEXT NOT NULL
prior_code TEXT NULL
final_status TEXT NOT NULL
final_code TEXT NULL
evidence_summary_json TEXT NOT NULL
applied_at TEXT NOT NULL
```

普通inspect不写audit；只有`--apply`写入。Evidence summary不得包含SQL、secret、raw key、
host path或row value。

V7同时扩展artifact lifecycle，使consumed package不再被readiness误报为丢失：

```text
consumed_by_operation_id TEXT NULL
consumed_at TEXT NULL
bytes_deleted_at TEXT NULL
```

`consumed_by_operation_id`记录首次使artifact具备success-cleanup资格的operation，不拥有全部
引用关系。全部operation reference的source of truth仍是
`repository_import_operations.artifact_id`；cleanup和readiness必须查询该集合。

SUCCEEDED operation与`consumed_*`在同一SQLite transaction写入；随后才best-effort删除
ready package bytes。Crash在transaction后、unlink前允许artifact仍存在；crash在unlink后、
`bytes_deleted_at`前允许根据matching SUCCEEDED operation判定缺失合法并补记cleanup。

## 9. Worker pool and writer ownership

首版运行模型固定为single ASGI process、single durable-root lock、global bounded worker
pool和process-local per-repository writer lock。

建议settings：

```text
max_import_workers = 4
max_queued_imports = 64
import_shutdown_grace_seconds = 10
import_headroom_bytes = 1 GiB
```

四项均可按deployment资源调整，不属于wire或SLO。提高package边界或worker数必须同步
重新验证disk、RSS、Dolt process lifecycle和restart behavior。`max_queued_imports`计算
QUEUED数，不计算same-key replay；达到上限的新effect返回429。

Dispatcher在process-local scheduler lock下维护active repository集合。它按per-repository
`enqueue_sequence`升序查找最早QUEUED且repository不在active集合、也没有未解决MANUAL
barrier的operation，先reserve repository ownership，再以`BEGIN IMMEDIATE`执行
`claim_if_queued(operation_id)`并改为RUNNING；claim race失败立即释放reservation。

FIFO的权威排序键是S2已落地的`enqueue_sequence`（`repository_import_operations`列，按
`repository_scope`单调分配），不是`created_at, operation_id`：`created_at`只有秒级精度
（`utc_now_iso()`截断microsecond），同秒内会退化成UUID字典序。跨repository之间不要求
全局FIFO顺序，只要求每个repository内部严格FIFO；dispatcher在候选repository之间的选择
顺序不属于契约，但必须无starvation（轮转或等价策略，不得固定偏向同一repository）。
`claim_next_queued(repository_id)`已实现per-repository FIFO claim并被
`test_claim_next_queued_is_fifo`固定，S6不得改变该语义。

不得先把同repository多个operation全部claim为RUNNING再让worker阻塞等待repository lock，
否则会耗尽global worker并阻塞其他repository。Worker不在长Dolt operation期间持有SQLite
transaction、scheduler lock或global store lock。同repository只有一个RUNNING writer；不同
repository最多按worker数并行。

Per-repository lock覆盖：

```text
initial main check
private ref create/inspection
package replay
marker commit
verification
second main check
main ref update and readback
operation terminal persistence
private ref cleanup attempt
```

正常failure也在释放repository ownership前写入terminal operation。进程crash不会执行
Python finally，startup recovery必须只依赖SQLite、artifact、marker和ref evidence。

Repository存在未解决`FAILED / MANUAL_RECOVERY_REQUIRED`时形成manual recovery barrier：

- 已存在operation的same-key replay和GetOperation继续可用；
- 新key import在accept前返回`409 / MANUAL_RECOVERY_REQUIRED`；
- 已经QUEUED的同repository operation保持QUEUED且dispatcher跳过；
- 其他repository继续服务；
- admin correction提交后解除barrier并通知dispatcher。

该barrier保护Repository ref/artifact evidence，并与External Effect contract的business
occupancy规则一致；它不新增public operation状态。

## 10. Candidate A production provider port

R4建立窄的production port，至少提供：

```text
read_ref(ref_name) -> CommitId
create_private_ref(private_ref, expected_commit)
checkout_private_ref(private_ref)
replay_sql(private_ref, replay_path, cancellation)
commit_operation_marker(private_ref, marker) -> candidate CommitId
inspect_marker(marker) -> zero | unique(candidate, parent, refs) | ambiguous
read_catalog(candidate) -> bounded catalog projection
stream_table(candidate, table, policy) -> bounded RecordBatch iterator
publish_main(expected_commit, candidate) -> published | mismatch | ambiguous
delete_private_ref(private_ref, expected_candidate?)
```

Private ref和marker由operation ID确定：

```text
private_ref = gateway-import-<operation UUID lowercase hex>
marker = gateway-versioned-import operation_id=<canonical UUID>
```

Provider必须以server-owned repository cwd运行Dolt CLI；`replay.sql`只通过只读file
descriptor/stdin传入，不进入argv、log或memory bytes。不建设SQL parser，因为package由
受信Storage Projection owner生成；若trust boundary改变必须重开ADR 0009。

S4 provider实现约束（Round-4 remediation）：

- `replay_sql(private_ref, ...)` 要求调用方已 checkout 到同名 private ref；provider 在 replay
  前后校验当前 branch 仍为 `private_ref`，否则 `ImportProviderError`；**不**在 replay 内自动
  checkout，避免在 `main` 上误执行 replay SQL。
- `read_catalog(candidate)` 通过 `dolt_log AS OF {candidate}` 解析 direct parent；parent 缺失或
  malformed 必须 `ImportProviderError`，禁止静默空 catalog。
- catalog projection 在 target revision 枚举全部 user tables（`SHOW FULL TABLES AS OF` +
  `SHOW CREATE TABLE ... AS OF` + `COUNT(*) AS OF`），覆盖 schema-stable data-only 增量；不得仅
  依赖 `dolt_schema_diff` 作为主路径。
- `inspect_marker` / `read_catalog` / `stream_table` 将 `CandidateAError`、`ProcessBoundaryError`、
  `csv.Error`、`UnicodeDecodeError` 等边界失败统一包装为 `ImportProviderError`；marker 探测期
  的 provider/validation 失败归类为 `ambiguous`。
- `csv.field_size_limit` 在进程级一次性提升到 stream line bound，stream 迭代内不得 per-stream
  恢复，避免并发 stream 竞态。
- catalog projection内部并行由`RepositoryServiceSettings.catalog_parallel_workers`控制，默认2、
  validator范围1..4。它只约束单次catalog调用，不是node-wide Dolt CLI process budget。
- Candidate A session只保留固定4项catalog memo，用于同一workflow重复读取initial、expected
  parent和candidate；该memo随session释放，不声明byte budget或node-wide cache authority。
- S4不实现node-wide Dolt CLI capacity limiter。Limiter的lease ownership、monotonic deadline、
  exception-safe幂等release，以及真实catalog memory budget统一defer到S7 runtime composition或
  S9 capacity owner，在多import worker的process count、peak RSS和p95证据下落地。

Repository资源配置的可调值集中由`settings.py`拥有，provider/process不得复制production
可调常量。Production可在既有validator范围内通过环境配置调优；扩大允许范围必须同时修改
settings validator、正式容量约束与资源测试，禁止只因单机资源充足而绕过node-wide预算设计。

S4进入provider实现前必须保持S3 package boundary为green，并增加一项cross-stage regression：
启用zstd content checksum、让checksum/frame trailer跨compressed input chunk、令decoder output
恰好等于配置上限，package仍必须成功；增加一个完整512-byte zero padding block仍成功，而
1/511/513-byte partial zero tail和任一非零trailing仍失败。该回归只冻结§6既有语义，不把package
validator接入provider，也不扩大S4 production scope；若回归失败，S4先标记no-go并单独修复S3
边界，不得在provider提交中静默改变package contract。

## 11. Private ref and mandatory main CAS

已确认的Candidate A CAS定义为single-owner serialized expected-value update：

1. 持有root lock与repository writer lock；
2. 读取`main`并要求等于`expected_commit_id`；
3. 从expected commit创建并checkout deterministic private ref；
4. replay SQL并创建唯一marker commit；
5. 要求candidate的direct parent等于expected commit；
6. 完成requested verification；
7. 再次读取`main`并要求仍等于expected commit；
8. 使用Dolt内部branch/ref move primitive把`main`更新到candidate；
9. 立即readback并要求`main == candidate`；
10. 持久化SUCCEEDED result；
11. 删除private ref并cleanup artifact。

第8步可以在private provider adapter内部使用Dolt的force branch-move primitive，但只在
前述writer域和第二次expected check后调用。它不是public force-ref capability，request
不能关闭expected check，admin CLI也不得调用它。

因为Candidate A没有跨两个CLI process的native single-command compare-and-swap，CAS安全性
依赖正式single-owner topology：root lock排除第二个Service owner，per-repository lock排除
本进程第二个writer。绕过root lock直接执行Dolt写命令不属于支持面。

Ref update非零退出、timeout、process loss或readback不一致时，worker不得猜测not-published；
必须重新采集marker/ref evidence。唯一结果不可证明时进入MANUAL_RECOVERY_REQUIRED。

## 12. Verification and unknown-type policy

所有policy都强制：

- package safety、raw size/SHA与closed manifest；
- unique marker和candidate direct parent；
- initial与second target ref expected check；
- known type exact mapping；
- `REJECT`下publication前拒绝任一unknown catalog type。

Policy行为：

| Verification | Required behavior |
| --- | --- |
| `NONE` | 不比较manifest table/schema/row count，不扫描rows；为执行REJECT仍读取最小catalog type projection |
| `STRUCTURAL` | exact比较user table set、column order/type/nullability、PK order和manifest row count |
| `FULL_SCAN` | 包含STRUCTURAL；以bounded batches读取全部user table，全部Arrow/type conversion成功且scanned count匹配manifest |

Unknown type行为：

| Policy | Required behavior |
| --- | --- |
| `REJECT` | 任一unknown normalized SQL type在publication前以IMPORT_REJECTED失败，包括verification NONE |
| `STRINGIFY` | 只把unknown列按Dolt/driver文本转为Arrow `large_string`；NULL保持NULL；metadata写原SQL type与lossy |

`STRINGIFY`不得降级known type，文本转换失败即operation失败。STRUCTURAL在STRINGIFY下仍
要求manifest与catalog unknown spelling exact一致。FULL_SCAN不得materialize全表，沿用
validated RecordBatch row/byte bounds。

Verification failure时若`main`仍为expected，删除private ref并写
`VERIFICATION_FAILED_NOT_PUBLISHED`；main不得改变。若ref/marker/effect evidence矛盾，
不得执行cleanup，转MANUAL。

## 13. Failure mapping

| Condition | Terminal result |
| --- | --- |
| package/manifest/raw integrity/unknown REJECT/provider known no-effect failure | `FAILED / IMPORT_REJECTED` |
| initial或second `main != expected` | `FAILED / EXPECTED_COMMIT_MISMATCH` |
| requested verification失败且可证明未发布 | `FAILED / VERIFICATION_FAILED_NOT_PUBLISHED` |
| publication、marker、private ref或artifact evidence不唯一/矛盾 | `FAILED / MANUAL_RECOVERY_REQUIRED` |

Provider command失败不是自动retry理由。若当前进程能证明main未变且没有marker commit，按
known no-effect failure终止；若无法证明则MANUAL。Connection loss、worker shutdown或
process crash本身不写普通FAILED，保留RUNNING供startup evidence-first recovery。

Public error details只包含bounded safe facts，例如reason code、expected/current commit的
opaque value或policy；不得暴露private ref、filesystem path、SQL、stderr全文或row value。

## 14. Startup reconciliation

Startup顺序固定为：

```text
load settings
create/validate layout
acquire root lock
open/migrate control DB
verify Candidate A capability
reconcile synchronous R3 mutations
reconcile import operations
start import workers
become ready
```

Import reconciler按operation逐项执行：

1. `QUEUED`保持QUEUED并通知worker；
2. `SUCCEEDED`清理残留private ref/package，不改变result；
3. 普通`FAILED`不重试，只执行允许的staging cleanup；
4. MANUAL保持artifact/private evidence和repository barrier，不自动处理；
5. 遗留`RUNNING`先检查main、marker、private ref、parent和artifact；
6. main等于唯一matching candidate且parent/marker匹配时补SUCCEEDED；
7. main仍为expected且private ref有唯一matching candidate时继续verification和CAS，
   不重复replay SQL；continue路径无条件以`STRUCTURAL`复核candidate（证据补强，不改变
   `completed_verification_policy`）；automatic replay仍按requested policy执行；
8. 完全没有matching commit、main仍为expected、artifact完整且
   `automatic_replay_count == 0`时，先在transaction中把count改为1，再从expected重建private
   ref并自动replay；
9. count已经为1且仍无可判定evidence，或存在multiple marker、parent mismatch、ref矛盾、
   artifact缺失/损坏时转MANUAL。

Recovery继续verification/CAS时使用原request、artifact、operation ID、marker和policy。
不得生成新key、operation ID、artifact或marker。自动重放次数在effect前持久化，保证再次
crash不会执行第二次SQL replay。

Startup必须从durable `status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED` rows重建manual
repository barrier，再允许dispatcher claim QUEUED operation；barrier不能只存在于上次
进程的内存lock registry。

## 15. Graceful shutdown

Shutdown顺序固定为：

1. 标记runtime stopping，使新import effect admission失败；
2. 停止claim QUEUED operation；
3. 在configured short grace内等待active worker自然完成；
4. grace到期后设置per-operation cancellation token；
5. active Dolt child执行process-group TERM、grace、KILL、wait/reap；
6. worker停止后关闭control DB；
7. 最后释放root lock。

被shutdown中断且未写terminal result的operation保持RUNNING。Worker cancellation不得映射为
IMPORT_REJECTED，也不得在shutdown路径删除artifact/private evidence。`DoltRunner`需要增加
production cancellation seam或active child registry；不得让daemon thread在DB关闭或root
lock释放后继续写repository。

## 16. Artifact retention and readiness

规则：

- QUEUED/RUNNING operation引用的artifact不可删除；
- SUCCEEDED result与artifact consumed binding先在同一transaction持久化；
- transaction成功且同artifact不存在QUEUED、RUNNING或MANUAL引用后才删除ready package，
  失败只记录safe log；
- verification/CAS/package普通失败保留artifact并记录TTL eligibility；
- R4不启动周期TTL scheduler，scheduler仍属R6；
- MANUAL artifact和private ref保留到admin apply完成；
- admin补SUCCEEDED后可执行success cleanup；
- admin确认NOT_PUBLISHED后artifact转ordinary failure TTL eligibility；
- operation、idempotency metadata、result/error和audit在repository lifetime永久保留。

同一artifact允许被多个operation durable引用。Cleanup必须查询全部operation reference，
不得因第一个SUCCEEDED operation删除仍被QUEUED/RUNNING/MANUAL operation pin住的bytes。最后
一个protected reference终止或由admin处理后重新评估cleanup；普通FAILED reference不阻止
已有SUCCEEDED operation触发删除，但没有任何SUCCEEDED时仍按ordinary TTL处理。

Readiness reconciliation必须区分：

```text
successful upload + no consuming operation + missing bytes = inconsistency
successful upload + matching SUCCEEDED import + missing bytes = valid consumed state
QUEUED/RUNNING/MANUAL import + missing bytes = blocking inconsistency or MANUAL evidence
```

MANUAL operation本身在被完整分类后不使整个Service permanently unready；它通过operation
状态和artifact retention暴露。无法打开DB、读取provider evidence或证明artifact binding时
仍按现有readiness规则fail closed。

## 17. Private admin CLI

Private entry point（模块调用形式；`pyproject.toml`无`[project.scripts]`，不要求新增）：

```text
python -m gateway_repository_service.versioned_import.admin inspect \
  --operation-id <uuid> [--data-root <path>]

python -m gateway_repository_service.versioned_import.admin apply \
  --operation-id <uuid> \
  --decision SUCCEEDED|NOT_PUBLISHED [--data-root <path>]
```

该CLI是唯一允许把`FAILED/MANUAL_RECOVERY_REQUIRED` operation推到terminal correction的通道
（见§8）。它运行在stopped service下：durable root lock是"service是否在跑"的唯一判据，
CLI不做任何形式的与运行中service并发写。

CLI必须：

- 使用同一settings/layout resolver：`RepositoryServiceSettings`（`GATEWAY_REPOSITORY_`
  env prefix + `.env`）→ `DurableLayout.create_service(settings.data_root)`；`--data-root`
  只覆盖`data_root`；
- 非阻塞取得`control/service.lock`（`DurableRootLock.acquire()`已是`flock LOCK_NB`，busy时抛
  `RootLockBusy`），lock busy即退出且不inspect/apply；
- 以`ControlStore.open(..., expected_version=CONTROL_DB_USER_VERSION)`打开exact supported
  control DB，newer/invalid version fail closed；不做migration，不bump user_version；
- 只允许查询`status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED` operation；
- 默认inspect只读显示safe operation/evidence summary，零mutation（不写control DB、不写audit、
  不删除任何ref或bytes）；
- apply前重新采集main、marker、parent、private ref和artifact evidence，只用provider只读面
  （`read_ref`、`inspect_marker`、ref存在性）与artifact validity探针，不复用durable row里的
  旧结论；
- `SUCCEEDED`只在matching candidate已发布（`MarkerInspectionUnique`且`main`指向它）且全部
  binding可重建时补**完整**`VersionedImportResult` echo；任一字段无法从evidence重建即fail
  closed，不填占位值；
- `NOT_PUBLISHED`只在main仍为expected且不存在matching published/candidate ambiguity时应用；
- 纯NOT_PUBLISHED默认写`IMPORT_REJECTED`和safe detail
  `operator_confirmed_not_published`；
- evidence精确证明expected mismatch或verification failure时才使用对应ordinary code
  （`EXPECTED_COMMIT_MISMATCH`、`VERIFICATION_FAILED_NOT_PUBLISHED`）；三个code都在
  `ORDINARY_TERMINAL_ERROR_CODES`内且`request_id`为`None`；
- 通过`ImportOperationStore.apply_manual_correction`落库，status correction和audit insert
  共享同一`BEGIN IMMEDIATE` transaction（该API已实现，CLI不另开transaction、不手写SQL）；
- apply后按新terminal状态执行允许的private ref/artifact cleanup，cleanup为best-effort且
  失败不回滚已提交的correction；
- 确保MANUAL解除后worker barrier不再阻塞该repository：barrier判定要么仅以
  `store.has_unresolved_manual_barrier()`为准，要么在内存barrier路径上补齐清除；不允许两条
  判定路径并存而只更新一条。

固定前置顺序与退出码（任一失败立即退出，不做后续采证）：

```text
0  成功
2  参数或decision非法
3  root lock busy（service运行中）
4  control DB version或schema不受支持
5  operation不存在或不满足 status=FAILED && error.code=MANUAL_RECOVERY_REQUIRED
6  evidence不足、不唯一或与decision矛盾
```

stdout只输出single-line JSON safe summary，诊断文本走stderr。

CLI不得：

- 移动或force `main`；调用`publish_main`、`replay_sql`、`commit_operation_marker`或
  `checkout_private_ref`；
- 执行replay SQL或任意caller SQL；
- 创建commit、删除history或接受host repository path、control DB path等直连参数；
- 修改非MANUAL operation；
- 在evidence不唯一时提供`--force`、`--yes-really`或绕过选项；
- 暴露public HTTP route，或把CLI逻辑挂到`app.py`/`http/`。

## 18. Capacity, readiness and logging

新import effect接受前至少检查：

- runtime不在shutdown；
- root lock、control DB和Candidate A capability可用；
- repository和artifact存在且scope/binding匹配；
- repository不存在未解决manual recovery barrier；
- QUEUED count低于configured limit；
- durable root writable；
- free bytes在扣除configured import headroom后仍不低于
  `max(5 GiB, 10% volume)`。

Worker extraction前重复disk/headroom检查，防止accept后资源漂移。该检查失败且可以证明
尚无Dolt effect时终止为IMPORT_REJECTED，不做hidden retry。完整真实样本capacity closure
仍属于R6；R4不把synthetic dedup或throughput提升为SLO。

Structured event至少覆盖：

```text
request accepted/replayed/conflicted
operation claimed/terminal/reconciled
package validation result and bounded sizes
verification policy and duration
CAS outcome
cleanup outcome
admin apply audit identity
worker startup/shutdown/cancellation
```

Safe fields为request ID、operation ID、repository ID、artifact ID、policy、duration、size、
status和stable code。禁止token、raw idempotency key、replay SQL、full stderr、internal/host
path、private credential、complete row或sensitive text conversion value。

`admin apply audit identity`（§17 CLI唯一写audit的路径）的字段集合与
`repository_import_recovery_audit.evidence_summary_json`保持一致，且只取上述safe field：

```text
operation_id / repository_id / artifact_id
decision                     SUCCEEDED | NOT_PUBLISHED
action                       INSPECT_APPLY_SUCCESS | INSPECT_APPLY_NOT_PUBLISHED
prior_status / prior_code    correction前的durable值
final_status / final_code
marker_inspection            zero | unique | ambiguous
main_commit_id / expected_commit_id / candidate_commit_id
manifest_digest
verification_policy / unknown_type_policy
artifact_size_bytes / artifact_bytes_present
private_ref_present
applied_at
```

CLI stdout的single-line JSON summary与该集合同源；`inspect`输出同一形状但不写audit。

## 19. Fault injection model

R4内部fault seam只在test profile启用，不进入public DTO、header、environment默认或
production OpenAPI。Stable points：

```text
after_queued_before_202
after_running_claim
after_package_extracted
after_private_ref_created
after_replay_before_marker
after_marker_before_verification
after_verification_before_second_main_check
after_second_main_check_before_publish
after_main_publish_before_succeeded
after_succeeded_before_private_ref_cleanup
after_succeeded_before_artifact_cleanup
```

Fault harness必须支持真实process crash，而不只是在同进程抛exception；commit前crash、
publication后response loss和legacy RUNNING自动重放都必须用新进程/重启观察durable evidence。
Required fault case不得skip/xfail。

## 20. Verification matrix

Contract tests：

- header-only idempotency、body无key、policy defaults/enums；
- target literal main、path/body repository match；
- full result echo、four-state result/error invariant；
- SimpleError和closed model/OpenAPI status。

Store tests：

- v6 -> v7 migration、fresh v7和newer-version failure；
- QUEUED/RUNNING/SUCCEEDED/FAILED visibility；
- atomic claim和concurrent worker behavior；
- same-key replay、different fingerprint conflict；
- automatic replay count 0 -> 1 only；
- admin correction与audit同transaction；
- consumed artifact readiness rules；
- manual barrier阻止新key和同repository dispatch，但允许same-key replay/GetOperation；
- multi-operation artifact pin阻止premature success cleanup。

Package tests：

- valid package与strict manifest；
- entry count/order/name/type；
- traversal、duplicate、link、device、FIFO、PAX、extra/trailing；
- compressed、manifest、replay、payload-total和decoder-stream exact boundary±1；
- checksum-enabled zstd frame跨compressed chunk且equal decoder boundary成功；
- 双tar EOF后完整512-byte zero padding兼容，partial/non-zero trailing拒绝；
- bounded chunking且不materialize完整entry；
- raw size/SHA mismatch和cleanup。

Provider/verification tests：

- deterministic private ref/marker、expected parent和unique marker；
- initial/second main mismatch；
- internal ref update readback与ambiguous result；
- policy matrix`3 verification × 2 unknown-type`；
- known type exact mapping、STRINGIFY metadata/NULL/conversion failure；
- verification failure保持main且清理private ref；
- FULL_SCAN bounded batches和row counts。

Recovery/admin tests：

- QUEUED requeue；
- published marker补SUCCEEDED；
- private candidate继续且不replay SQL；
- no commit自动replay恰好一次；
- second no-evidence、multiple marker、parent/ref/artifact矛盾转MANUAL；
- normal terminal failure无hidden retry；
- shutdown cancellation保留RUNNING/evidence；
- CLI（全部以真实subprocess调用`python -m ...versioned_import.admin`）：
  - `inspect`输出safe summary且零mutation；
  - `apply --decision SUCCEEDED`补完整result echo并写`INSPECT_APPLY_SUCCESS` audit；
  - `apply --decision NOT_PUBLISHED`写`IMPORT_REJECTED`/`operator_confirmed_not_published`
    并写`INSPECT_APPLY_NOT_PUBLISHED` audit；
  - audit持久化：重开control DB断言action、prior/final status与code、evidence summary无禁止字段；
  - negative：root lock busy（service运行中）、control DB version newer、operation不存在、
    非MANUAL operation（QUEUED/RUNNING/SUCCEEDED/ordinary FAILED各一）、stale evidence、
    ambiguous marker、missing/invalid artifact、invalid decision、重复apply（第二次fail closed
    且不写第二条audit）；
  - 断言exit code与stdout JSON，不只断言非零退出；
  - 至少一个real Dolt case覆盖真实main/marker采证下的positive apply；
  - MANUAL解除后同repository QUEUED operation可被dispatch（barrier不再阻塞）；
- success cleanup、ordinary TTL eligibility和manual retention；
- manual barrier解除前后及同artifact多operation cleanup ordering。

## 21. Required exit gate and handoff

Contracts与Service分别执行：

```bash
uv lock --check
uv run ruff check .
uv run mypy
uv run pytest -q
```

R4不修改Repository Client、Backend、Rust/canonical owner；若实际diff触及这些路径，必须
先暂停并重新确认scope，再运行对应package完整gate。

最终integration必须覆盖真实Candidate A Dolt、正式Dockerfile和Compose build/up、HTTP
create/upload/import/poll、restart/replay、response loss与全部required fault cases。Compose
project name必须唯一，以trap完成project-scoped container/network/volume cleanup；外部build
或registry失败不得报告pass。

最终执行：

```bash
git diff --check
git status --short
```

并对production scope做定向old-reference search：body `idempotency_key`、旧verification名、
generic journal/effect状态、Candidate B、gzip/multipart/URL/path输入、public force/admin、
`workflow.py`/fixture/benchmark import。Historical formal artifacts可以命中，但production
code、tests、OpenAPI和current plans不得依赖旧语义。

Handoff至少记录：

```text
round = P2-R4
start_sha
commit_shas
head_sha
branch
worktree_clean
control_db_user_version
selected_provider and Dolt version
activated_routes
package limits and worker/admission settings
contracts/service command results and test counts
fault_matrix required/passed/skipped/xfail
real_dolt_result
compose_project and cleanup result
startup_replay and manual_recovery results
artifact_cleanup result
old_reference_searches
known_limitations
production_retest_required
p2_r4_exit = pass|no-go
p2_r5_ready = yes|no
```

只有全部required gate通过、required fault case零skip/xfail、runtime cleanup完成且最终
worktree clean时，才可写`p2_r4_exit = pass`和`p2_r5_ready = yes`。

## 22. Risks and reopen conditions

主要实现风险：

- Candidate A的expected-value CAS依赖single-owner topology和相邻CLI操作；
- decoder/tar reader read-ahead可能绕过不正确的counter placement；
- worker shutdown若未拥有active child cancellation会在root lock释放后继续写；
- success artifact删除会破坏现有R3“所有upload永久存在”的readiness假设；
- STRINGIFY文本受Dolt版本影响；
- DB terminal correction若不与audit同transaction会丢失operator evidence；
- 200 MiB以上虽可配置，但未自动获得正式支持。

以下变化必须暂停R4并修订formal owner或ADR：

- 需要multi-process/multi-node/shared-RWX writer；
- 需要不依赖single-owner lock的native remote CAS；
- package上传者变为untrusted tenant或需要SQL semantic validation/signature；
- 单package超过4 GiB total decompression ceiling；
- 需要public rollback、promotion、force ref或recovery API；
- Candidate B转为默认provider；
- artifact转为外部object storage或resumable transport。

在上述条件不变时，P2-R4 implementation readiness为`go`。
