# Repository Service Contract

状态：Accepted Simplified Baseline

日期：2026-08-02

阶段：Phase 2 Repository Service Foundation；Phase 3+ consumer

Contract ID：`gateway-vnext.repository-service`

Owner：Repository Service（public wire、Versioned repository effect、import recovery
和服务运行边界）

首个激活HTTP版本：`/v1/`

## 1. Authority and scope

Repository Service是独立内网服务，保存Dolt-backed immutable table history。它不
理解Workspace、Preview、Submission、Archive、Baseline、History、Snapshot、
Comparison、Risk、Bundle、业务审批或business finalize。

V1只拥有：

- Repository创建和server-owned持久化目录；
- repository-bound临时import artifact；
- Versioned import、commit、ref、catalog和row stream；
- import operation、幂等和有限启动恢复；
- 服务健康、认证、容量admission和部署级恢复边界。

CurrentTableStore、cross-store inventory、通用query/diff/export、public GC、
backup/restore/delete/repair、typed audit subsystem和multi-node writer不属于V1。
未来Current作为additive sibling加入，不改变本合同的Versioned语义。

## 2. Component and dependency boundary

保留三个Python distribution：

```text
gateway-repository-contracts
  <- gateway-repository-client

gateway-repository-contracts
  <- gateway-repository-service
```

- `contracts`只保存薄Pydantic DTO、少量enum和共享类型，不依赖HTTP、Dolt、
  filesystem或业务module。
- `client`拥有Remote client和Backend可依赖的Repository Port adapter。
- `service`拥有HTTP、application、Dolt、filesystem和operation实现。
- Backend production不依赖或import `gateway-repository-service`。
- `contracts/client/service`均不依赖Shared Kernel、Rust compute、Backend artifacts或
  generic conformance distribution；Service也不依赖Client。

T2简化阶段只替换contracts和delivery skeleton，不注册返回占位结果的业务route。
首个真实纵切实现时，FastAPI route生成的OpenAPI才成为激活wire authority。

## 3. Trust and authentication

V1是单一信任域：

- production使用一个global static bearer token；
- 有效token可访问全部Repository；
- 除`healthz`和部署限定的`readyz`外，所有业务route必须认证；
- 不提供CallerIdentity、per-repository ACL、policy generation或存在性隐藏；
- TLS由deployment ingress/sidecar拥有；
- token泄漏等价于完整Repository写权限泄漏，这是已接受的边界。

Production token优先从只读secret file加载；environment只允许dev/test profile。
Production缺失或空token必须启动失败。V1不支持hot rotation，token变更通过rolling
restart完成。`healthz`是未认证liveness；`readyz`不使用业务bearer，但必须由部署网络
限制访问。ready至少检查root lock、layout、control DB、provider、durable root可写和
free-disk admission。

输入安全保留server-owned path、regular-file、size、路径穿越、secret/log脱敏和
非shell执行检查。`replay.sql`由受信Backend生成；Service不建设完整SQL grammar、
semantic package签名或防篡改体系。

## 4. Contract and compatibility

Pydantic model和激活route生成的FastAPI OpenAPI是HTTP wire authority。不维护：

- 自定义strict JSON/JCS wire；
- deep-freeze JSON tree；
- 重复runtime validator；
- 手写JSON Schema和schema snapshot hash；
- 每个DTO独立version轴；
- N/N-1 client兼容矩阵。

T2/T3尚无兼容承诺，可破坏性修改。`/v1/`激活后允许新增route、可选请求字段和
响应字段；删除字段、改变含义或改变必填性使用`/v2/`。

Error统一为：

```text
code: string
message: string
details?: object
request_id?: string
```

HTTP status表达请求层结果；不公开通用`category/phase/recovery/effect`状态空间。

## 5. Public identity and value rules

| Value | Rule |
| --- | --- |
| `RepositoryId` | Service生成的普通UUID；caller不得解析时间或版本 |
| `ArtifactId` | Service生成的普通UUID；只在所属Repository内有效 |
| `RepositoryOperationId` | Service生成的普通UUID；只在所属Repository内查询 |
| `CommitId` | Dolt生成的repository-scoped opaque string（1..1024 code points）；逻辑值出现在JSON body（catalog/ref response等） |
| `CommitIdPathSegment` | HTTP path `{commit_id}` 的canonical **base64url（RFC 4648 §5，无 padding）** 编码，承载UTF-8逻辑`CommitId`；caller不得在path中直接放置逻辑CommitId（如`commit-c1`）；非法或非canonical segment → `422 REQUEST_VALIDATION_FAILED`；最大长度`MAX_COMMIT_ID_PATH_SEGMENT_LENGTH`（5464） |
| `RefName` | V1 mutation与resolve只接受literal `main` |
| `IdempotencyKey` | caller生成的1..255 UTF-8 opaque string |
| provider token | bounded opaque string，不施加UUID或canonical grammar |

`RepositoryId`、`ArtifactId`和`RepositoryOperationId`可以直接使用`uuid.UUID`；
不得为每个ID复制自定义比较、hash、wire parser和schema版本。

Table、column和primary-key column name均为1..64 Unicode code points；拒绝NUL、
ASCII control和`/`、`\\`路径分隔符。table name额外禁止leading/trailing whitespace；
column name与primary-key column name保持exact identifier规则（允许embedded space）。
Service比较catalog时exact、case-sensitive，不做
Unicode normalization或case fold；访问Dolt必须使用driver/adapter的MySQL identifier
quoting，禁止把identifier直接拼接进SQL。Row route的table name只允许query parameter，
不得进入path segment。V1不接受caller自定义Repository display name。

## 6. V1 capability surface

```text
CreateRepository
UploadArtifact
SubmitVersionedImport
GetOperation
ResolveVersionedRef
GetVersionedCatalog(commit_id)
StreamVersionedTableRows(commit_id)
healthz
readyz
```

首个HTTP surface固定为：

```text
POST /v1/repositories
POST /v1/repositories/{repository_id}/artifacts
POST /v1/repositories/{repository_id}/versioned/imports
GET  /v1/repositories/{repository_id}/operations/{operation_id}
GET  /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows?table_name=...
```

`{commit_id}` path segment使用canonical base64url（无padding）传输逻辑`CommitId`；OpenAPI以`pattern: ^[A-Za-z0-9_-]+$`与`maxLength: 5464`声明。`GetVersionedCatalog`成功JSON body不得超过`MAX_CATALOG_JSON_BYTES`（256 KiB）；超出时Service返回`503 SERVICE_NOT_READY`。`GetOperation`成功JSON body不得超过`MAX_OPERATION_JSON_BYTES`（256 KiB）；超出时Service返回`503 SERVICE_NOT_READY`。

```text
GET  /healthz
GET  /readyz
```

Upload route使用raw request body。`Content-Type`、`Content-Length`、
`Idempotency-Key`和`X-Artifact-SHA256`是必需header；不使用multipart。Mutation的
idempotency key只由header传输，其余request字段使用closed JSON model。

成功status固定为create `201`、upload `201`、import accept/replay `202`、reads
`200`。通用失败status为authentication `401`、malformed/validation `422`、not found
`404`、idempotency/CAS conflict `409`、too large `413`、unsupported media `415`、
admission concurrency `429`、provider/readiness/disk unavailable `503`。所有JSON错误
（包括framework validation）必须映射为第4节SimpleError。每个response带server生成的
opaque `X-Request-ID`；error body回显同一`request_id`，不信任caller输入覆盖它。

不提供独立`CompareAndSetVersionedRef`。当前consumer只需要import创建commit并
原子发布target ref；rollback、promotion、审批发布或独立ref修复出现真实consumer
后，可新增同步CAS API。

T2简化阶段定义DTO和语义但不激活上述业务route。首个真实实现统一使用`/v1/`。

## 7. CreateRepository

`CreateRepository`是同步、幂等操作。成功时必须：

1. 由Service分配RepositoryId和server-owned staging目录；
2. 初始化Dolt repository；
3. 创建初始空commit和默认`main` ref；
4. 原子发布repository目录；
5. 返回`repository_id + default_ref + initial_commit_id`。

响应丢失后，same key/same request返回原结果；same key/different request返回冲突。
发布前失败不得产生可见Repository，允许清理明确的staging目录。

不建立public create operation、通用effect journal、lease、fencing或后台executor。
Create必须使用第11节SQLite最小幂等ledger：filesystem effect前持久化`PENDING`和已分配
RepositoryId，atomic publication后持久化`SUCCEEDED`。Repository只有在SQLite
`SUCCEEDED`和matching complete filesystem同时存在时可见；startup以layout marker
reconcile `PENDING + complete directory`，`SUCCEEDED + missing directory`使ready失败并
要求operator处理。

## 8. UploadArtifact

Upload是同步、repository-bound、one-shot streaming操作。Caller声明：

```text
media_type
declared_size
raw_sha256
idempotency_key
```

Service边读边写staging file并增量计算size和SHA-256；完整close和匹配后使用
同filesystem atomic rename发布ArtifactRef。不得把完整package读入内存，不接受
URL、host path、file descriptor、bucket locator、anonymous presigned URL、
multipart或range resume。

中途断连不发布partial artifact，caller完整重传。发布后响应丢失时，same key、
same size和same SHA返回原ArtifactRef；不同内容冲突。

Upload同样在filesystem effect前写入SQLite `PENDING`并分配ArtifactId，atomic rename
后写入`SUCCEEDED`。Startup用published artifact的size/SHA reconcile PENDING；
SQLite SUCCEEDED但ready artifact缺失或不匹配使ready失败。这里的最小ledger只服务
同步幂等与crash reconciliation，不把create/upload变成异步Operation。

V1 `RepositoryArtifactRef`只包含：

```text
artifact_id     opaque service-owned id
media_type
size_bytes
raw_sha256
```

Repository不把table schema、row count、business digest、retention或access policy塞入
ArtifactRef；这些语义分别属于canonicalization manifest、capability result和上游
业务policy。

Backend local `BackendArtifactRef`与本文DTO是不同nominal type。Upload request只
传输bytes、media type、declared size/raw SHA和idempotency key；Repository必须分配
新的repository-scoped ArtifactId。成功response的media type、size和raw SHA必须与
Backend声明exact一致。

已确认规模为通常10–100 MB、极端约200 MB。初始建议默认单包上限256 MiB并允许
部署配置提高；该数值是可调admission默认值，不是稳定wire常量。

## 9. Import package

V1 package固定为`tar+zstd`，只包含：

```text
manifest.json
replay.sql
```

Service对所有verification policy都检查：

- entry是固定名称的regular file；
- 无absolute path、traversal、duplicate、link、device或额外required entry；
- compressed和expanded size在部署上限内；
- manifest具备`package_version`、opaque
  `canonicalization_manifest_digest`以及每张table的name/schema/row_count；
- upload bytes的raw size和SHA-256已匹配。

业务digest和canonical content equality由Storage Projection/capability owner拥有。
Repository verification只按第10节检查Repository自身可读取性与manifest structural
facts，任何level都不重算业务digest。

该package只是Repository import transport。Backend必须在清理package前持久化独立的
`CanonicalizationManifest`；Repository只把其digest当opaque binding，不解释或重算
业务语义。

`package_version`固定为integer `1`。Manifest object使用closed Pydantic model：

```text
tables[]
  name
  schema
    columns[]: name, sql_type, nullable
    primary_key[]: column name in key order
  row_count
```

`row_count`是非负integer；table/column name唯一；primary key只能引用已声明column。
Tables按canonical name bytes排序，columns保持DDL order。`sql_type`是bounded
normalized physical SQL type，Repository与Dolt catalog projection exact compare。
JSON只要求strict UTF-8与closed shape，不要求JCS。Repository把
`canonicalization_manifest_digest`作为bounded opaque string保存并原样返回，不
import Shared Kernel `DigestRef`。

Compressed upload默认上限256 MiB，expanded package默认上限4 GiB。Service必须在
streaming extraction中同时限制entry count、单entry expanded size与total expanded
size，不能先完整解压再检查。接受新upload/import前保留
`max(5 GiB, durable volume容量的10%)` free space；import额外headroom由P2-R1测得的
staging high-water与Dolt增长计算。上述值均可配置，P2-R1可在P2-R3激活wire前依据
测量修订内部默认值。

外部原始package备份由上游流程拥有。Repository Service不调用、等待或查询外部
备份系统。

## 10. SubmitVersionedImport

Import是V1唯一异步业务operation。请求至少包含：

```text
repository_id
artifact_ref
target_ref
expected_commit_id
verification_policy
unknown_type_policy
idempotency_key
```

`target_ref`必须是`main`。`expected_commit_id`必填并同时是：

- 新commit的parent；
- target ref发布时的CAS预期值。

Service不得提供LWW、force ref、关闭CAS、table/schema CAS或独立publication mode。
Import固定使用private operation ref：

1. 确认`main == expected_commit_id`，从expected commit创建private operation ref；
2. 在private ref执行受信`replay.sql`并创建唯一operation-marker commit；
3. 对immutable candidate commit执行caller选择的verification；
4. 再次确认`main == expected_commit_id`；
5. 以expected commit为precondition CAS发布`main`到candidate commit；
6. 持久化SUCCEEDED result后删除private ref并清理成功artifact。

VerificationPolicy为：

| Policy | Required behavior |
| --- | --- |
| `NONE` | 跳过candidate catalog structural/full scan；不跳过package safety、marker、parent与target CAS |
| `STRUCTURAL` | 默认；exact核对user table set、column order/type/nullability、primary-key order与manifest row count |
| `FULL_SCAN` | 包含STRUCTURAL；以bounded batches扫描全部user table，Arrow/type conversion成功且scanned row count等于manifest |

Verification失败且`main`仍为expected commit时删除private ref并返回
`VERIFICATION_FAILED_NOT_PUBLISHED`；`main`不得改变。若publication outcome、private
ref或marker证据矛盾，保留恢复所需artifact/ref并终止为
`MANUAL_RECOVERY_REQUIRED`。Request/operation持久化`requested_verification_policy`，
SUCCEEDED result返回相同的`completed_verification_policy`；不得自动升降级。

UnknownTypePolicy为`REJECT | STRINGIFY`，默认`REJECT`，与verification正交：

- 已知normalized SQL type始终映射为exact Arrow type；不得因STRINGIFY而降级；
- 未知type在REJECT下即使verification为NONE也在publication前以`IMPORT_REJECTED`
  失败；read则返回type错误；
- 未知type在STRINGIFY下使用Dolt/driver文本值转为Arrow `large_string`，NULL保持NULL，
  field metadata至少包含`gateway.sql_type=<original>`与`gateway.lossy=true`；
- 文本转换本身失败则操作/读取失败；STRINGIFY不承诺跨Dolt版本文本稳定性、
  canonical equality或digest可比性。

V1 exact mapping识别下列normalized SQL grammar；Service对Dolt catalog归一化后与
manifest exact compare，并使用固定Arrow mapping：

| Normalized SQL type | Arrow type |
| --- | --- |
| `BOOLEAN` | `bool` |
| `TINYINT [UNSIGNED]` | `int8 | uint8` |
| `SMALLINT [UNSIGNED]` | `int16 | uint16` |
| `MEDIUMINT [UNSIGNED]` | `int32 | uint32`，并保持24-bit range |
| `INT [UNSIGNED]` | `int32 | uint32` |
| `BIGINT [UNSIGNED]` | `int64 | uint64` |
| `DECIMAL(p,s)`，`p=1..65`、`s=0..30`、`s<=p` | `p<=38`为`decimal128(p,s)`，否则`decimal256(p,s)` |
| `FLOAT` / `DOUBLE` | `float32 | float64` |
| `BIT(n)`，`n=1..64` | `binary` + field metadata `gateway.bit_width=n` |
| `DATE` | `date32` |
| `TIME(fsp)`，`fsp=0..6` | `duration[us]` |
| `DATETIME(fsp)`，`fsp=0..6` | `timestamp[us]`，无timezone |
| `TIMESTAMP(fsp)`，`fsp=0..6` | `timestamp[us, UTC]` |
| `CHAR(n)` / `VARCHAR(n)` / `TINYTEXT` / `TEXT` / `MEDIUMTEXT` / `LONGTEXT` | `utf8` |
| `BINARY(n)` / `VARBINARY(n)` / `TINYBLOB` / `BLOB` / `MEDIUMBLOB` / `LONGBLOB` | `binary` |
| `JSON` | `utf8` + field metadata `gateway.logical_type=json` |

Nullability来自catalog/manifest field，不由Arrow value推断。Integer display width、
ZEROFILL、character collation/charset modifier不属于normalized grammar。ENUM/SET、
YEAR、spatial、vector和其他未列type均为unknown：manifest可携带其bounded normalized
spelling，但只有caller显式STRINGIFY才允许publication/row conversion；STRUCTURAL仍
要求manifest与catalog spelling exact一致。spatial type带SRID时normalized spelling为
`TYPE SRID n`（例如`POINT SRID 4326`），catalog从Dolt version comment形态归一化到该
形式。P2-R1 probe固定实际Dolt catalog spelling与
driver value shape；adapter不得依据单个row值推断type或改变上述mapping。

SUCCEEDED result还必须原样返回package绑定：

```text
artifact_id
canonicalization_manifest_digest
expected_commit_id
target_ref
completed_verification_policy
unknown_type_policy
```

Operation request fingerprint至少覆盖RepositoryId、RepositoryArtifactRef全部字段、
target ref、expected commit、verification policy、unknown type policy和idempotency key。
Backend必须核对result artifact ID、manifest digest、expected parent、target ref、
requested/completed verification和type policy后才能业务finalize。

Package中高度重复的数据由Dolt内容寻址和结构共享利用；去重率必须在真实数据上
测量，不能作为未经验证的容量保证。

## 11. Operation, idempotency and recovery

Operation状态只有：

```text
QUEUED | RUNNING | SUCCEEDED | FAILED
```

`GetOperation`使用`repository_id + operation_id`查询。Operation result和error必须
足以让response-loss caller取得原结果。

Mutation使用`idempotency_key + internal request fingerprint`：

- scope为`(mutation_kind, repository_id nullable, SHA-256(idempotency_key))`；create为
  service-global，upload/import为repository-scoped且kind隔离；raw key不得写日志；
- same key/same fingerprint返回原resource/body与原成功status：create重放`201`、
  upload重放`201`、import即使已terminal也返回原operation ID和原`202`；caller通过
  GetOperation读取当前状态；
- same key/different fingerprint返回冲突；
- terminal failure后要发起新的业务尝试，caller使用新key。

`service-state/repository-service.sqlite3`是唯一control DB，保存create/upload ledger、
import queue/operation/result、idempotency fingerprint和recovery audit。启用WAL、
`synchronous=FULL`、foreign keys和bounded busy timeout；migration使用transactional
`PRAGMA user_version`只向前升级，遇到newer version启动失败。Control DB不保存table
data，也不占用未来`current/<repository_key>/`的SQLite namespace。

Import先在SQLite持久化QUEUED再返回202。Worker claim为RUNNING；graceful shutdown先
停止intake，在短grace内等待active work，未完成RUNNING在下次startup reconcile。
Startup规则为：

1. QUEUED重新入队；
2. 遗留RUNNING且`main`已指向唯一matching marker/parent commit时补齐SUCCEEDED；
3. `main`仍为expected且private ref存在唯一matching candidate时，从已保存request继续
   verification与CAS，不重复执行replay SQL；该continue路径在replay证据充分时**无条件以
   `STRUCTURAL`复核candidate**（证据补强，不是policy升级）。`completed_verification_policy`
   仍等于`requested_verification_policy`；automatic replay（规则4）仍按requested policy
   执行；
4. 完全未找到matching commit且artifact完整时，以原request/key自动重放最多一次；
5. 正常validation/provider failure直接终止，不做隐藏通用retry；
6. 多commit、ref矛盾、artifact缺失或无法判断时终止为
   `FAILED / MANUAL_RECOVERY_REQUIRED`。

不建设lease、fencing、ServiceEpoch、takeover或
`UNKNOWN/APPLIED/VERIFIED`状态机。

Repository operation与idempotency metadata在Repository lifetime内永久保留；只清理
artifact bytes、staging和可重建temporary data。Stable import failure code仅为：

```text
IMPORT_REJECTED
EXPECTED_COMMIT_MISMATCH
VERIFICATION_FAILED_NOT_PUBLISHED
MANUAL_RECOVERY_REQUIRED
```

前三者在语义适当时允许caller abort或用新key开始新attempt；
`MANUAL_RECOVERY_REQUIRED`不得释放业务occupancy。Repository不公开generic
category/recovery/effect taxonomy。

Private local admin CLI只用于`MANUAL_RECOVERY_REQUIRED`：必须停止service并取得root
lock；默认只inspect，`--apply`只允许根据既有marker/ref/filesystem证据补记SUCCEEDED，
或确认NOT_PUBLISHED后记FAILED。CLI不得force移动main、执行任意SQL或删除history，且
每次apply写入control DB recovery audit record。

## 12. Artifact lifecycle

Artifact是临时import输入，不是长期对象存储：

- RUNNING operation引用的artifact不得清理；
- import成功且operation结果已持久化后删除本地package；
- 成功清理必须使本地package与Service-owned filesystem对象实际收敛：不得每次成功
  永久净增对象；允许严格常数残差（残差形态与ownership边界由私有实现/ADR规定，
  不进入本Contract的UID/helper细节）；
- orphan和普通失败artifact使用可配置TTL做best-effort清理；
- 初始建议TTL为24小时；
- `MANUAL_RECOVERY_REQUIRED`引用的artifact保留到人工处理；
- 不提供public artifact delete、retention或GC API。

Artifact清理失败不得改变已经成功的commit或operation结果；通过普通日志和磁盘
admission暴露，不建立独立cleanup evidence状态机。容量circuit breaker若存在，只作
运维背压，不得替代「成功后实际收敛」语义。

## 13. Catalog and row stream

Catalog和row stream必须绑定caller提供的immutable CommitId，不提供
`LATEST_AT_START`。需要读取当前main时，caller先ResolveVersionedRef取得CommitId。

`StreamVersionedTableRows`直接返回media type
`application/vnd.apache.arrow.stream`的标准Arrow IPC stream HTTP body：

- 不使用JSON/base64 frame envelope；
- 不增加checkpoint frame或末尾内容SHA；
- schema和截断由Arrow reader/HTTP失败表达；
- server必须按RecordBatch bounded streaming，不全表materialize；
- disconnect/cancel关闭provider reader。

Row stream不保证row或batch ordering；需要稳定顺序的caller自行按业务key排序。Catalog
返回normalized SQL type；row route要求caller显式传`unknown_type_policy`（省略时
`REJECT`），并按第10节type mapping执行。Read result不继承某次import的type policy，
因为同一immutable commit可由不同caller读取；response schema metadata使STRINGIFY
降级可见。

Read route的稳定失败语义为：

| 场景 | HTTP status | stable code |
| --- | --- | --- |
| Repository不存在或不可见 | `404` | `REPOSITORY_NOT_FOUND` |
| literal `main`不存在 | `404` | `REF_NOT_FOUND` |
| caller提供的opaque CommitId不存在或provider不能定位 | `404` | `COMMIT_NOT_FOUND` |
| exact、case-sensitive table不存在 | `404` | `TABLE_NOT_FOUND` |
| `REJECT`下catalog含unknown SQL type | `422` | `UNKNOWN_SQL_TYPE` |
| RepositoryId、ref、table name或policy不满足wire validation | `422` | `REQUEST_VALIDATION_FAILED` |
| response开始前provider、timeout或Dolt output不可用/损坏 | `503` | `SERVICE_NOT_READY` |

CommitId仍是repository-scoped bounded opaque token；`COMMIT_NOT_FOUND`不得反向引入
Dolt hash、UUID或其他provider grammar。Response headers发送后发生provider、value
conversion或transport失败时，server终止body且不得在Arrow bytes后拼接JSON error；
caller通过HTTP/Arrow截断失败和已收到的`X-Request-ID`观察该结果。

## 14. Concurrency and capacity

运行模型为single ASGI process、single durable-root OS lock和per-repository
process-local writer lock。不同Repository可以有限并行。

已确认负载：

- 日常10–200次upload/import；
- 极端1,000次/天，分布在多个Repository；
- 单Repository通常一周一次写入；
- Versioned history永久保留，package不常驻。

初始建议最多8个并发upload、4个跨Repository import worker和同Repository单writer，
均为可调配置。极端负载是否可消化由真实Dolt import测量决定。

保留简单的单包上限、并发上限和最低剩余磁盘admission。超限在接受新effect前返回
429或503；不建设通用ResourcePolicy、per-caller quota或accounting subsystem。

### 14.1 Durable-root layout and publication

首个layout使用component-first结构，内部`layout_format_version`固定为integer `1`：

```text
<data_root>/
  control/
    layout.json
    service.lock

  versioned/
    <repository_key>/

  staging/
    versioned/
      <repository_key>.<nonce>/
    artifacts/

  artifacts/
    <repository_key>/
      staging/
      ready/

  service-state/
    repository-service.sqlite3
  provider/
```

- `<repository_key>`是Service生成`RepositoryId`的lowercase UUID hex，不包含caller
  提供的名称或路径片段；所有public response和log均不得暴露内部path。
- `versioned/<repository_key>/`直接保存Dolt repository；sql-server候选的
  `data_dir`只允许指向`versioned/`。
- `control/`拥有layout marker和进程生命周期lock；P2-R2+在`service-state/`惰性创建
  第11节control DB。P2-R1 probe不得提前创建该数据库。
- `artifacts/`是Repository-scoped临时transport；P2-R1只验证同filesystem staging
  与publication primitive，不提前实现UploadArtifact生命周期。
- `provider/`只保存最终选中provider需要的server-owned config/runtime metadata，
  不保存caller secret或host path。
- namespace按所属round惰性创建。P2-R1只使用disposable probe root；通过后固定首个
  layout，P2-R2+才可在真实durable root激活相应namespace。

未来CurrentTableStore只允许作为平级`current/<repository_key>/`component加法加入。
当前不得创建`current/`、SQLite文件或Current marker，也不得为了目录复用引入
StoreKind、generic store adapter、自动routing、dual-write或cross-store transaction。
未来layout migration可以增加Current component，但不得搬迁或改写现有
`versioned/` Dolt repository。`layout_format_version`是内部磁盘格式，不建立新的
HTTP、package或DTO版本轴。

首版支持Linux local或block-backed durable filesystem，包括经目标环境验证的Docker
named volume。`control/`、`versioned/`、`staging/`、`artifacts/`、
`service-state/`和`provider/`必须位于同一mounted filesystem。NFS、SMB、共享RWX
volume、FUSE、tmpfs和container writable layer不属于首版production支持面；若目标
部署需要其中任一项，必须重新执行P2-R1 filesystem probe并显式修订支持边界。

Service在ASGI lifecycle开始时对`control/service.lock`取得非阻塞exclusive
`flock`，并保持同一file descriptor直到进程退出。获取失败时进程不得进入ready；
lock file本身不因正常或异常退出而删除。该lock是单一信任域内的advisory owner
boundary，operator不得在Service运行时绕过它直接执行Dolt写命令。

Service-owned publication使用以下barrier：

1. 验证staging与target parent位于同一`st_dev`；
2. 完成内容写入，并对Service-owned file执行flush和`fsync`；
3. Dolt create场景等待provider正常完成，并在首次repository publication前同步
   staged tree的regular file和directory；
4. 在target不存在的前提下执行atomic rename；已存在target进入幂等、冲突或恢复
   判断，不得静默覆盖；
5. `fsync` source和target parent directory；
6. 任一步失败均不得确认成功。

`os.replace`只允许用于语义上允许替换的内部metadata，不用于新Repository或Artifact
publication。Provider内部commit durability由Dolt拥有；Service的layout、artifact和
状态publication继续遵守上述barrier。精确probe和provider selection由
[P2-R1 Runtime and Provider Feasibility Contract](../plans/p2-r1-runtime-provider-feasibility.md)
拥有。

## 15. Persistence and disaster recovery

Versioned commit history永久保留。Repository Service不提供public backup/restore
API。部署方对整个quiescent durable root执行一致性volume snapshot并由operator
恢复。

Snapshot runbook顺序固定为：停止intake并等待/终止service-owned provider；停止
Service；取得root lock；对SQLite执行WAL checkpoint并确认无open writer；quiesce
durable filesystem；一次性snapshot整个data root。Restore必须恢复匹配的layout、
control DB、artifact和完整Dolt tree，再启动相同支持版本并通过ready/integrity检查。
不得只snapshot SQLite或单个Dolt repository。

恢复目标是最近一次volume snapshot。之后的package可以从外部备份人工重放，但
CommitId可能改变，外部引用允许人工修正。Contract不承诺RPO、RTO、每commit同步
备份或CommitId跨灾难无损保持。

## 16. Future CurrentTableStore

Current重新进入范围前必须有真实caller、操作集合、生命周期和验收场景。它作为
additive sibling加入：

- 共享RepositoryId、认证、ArtifactRef和基础Operation概念；
- 拥有独立generation、mutation DTO、SQLite adapter和`/current/` route；
- 不引入StoreKind mutation union、自动routing、dual-write或cross-store
  transaction；
- 通过repository layout format version做加法升级，不提前创建空SQLite文件。

## 17. Required verification

- contracts package只使用Pydantic/stdlib实现DTO、ID和error边界；
- global bearer成功/失败路径通过HTTP集成测试；
- create同步幂等、初始commit和atomic publication通过；
- upload streaming、size/SHA、response loss和路径安全通过；
- import mandatory commit CAS、private ref、NONE/STRUCTURAL/FULL_SCAN、
  REJECT/STRINGIFY、operation marker和幂等通过；
- SQLite PENDING/SUCCEEDED visibility、QUEUED/RUNNING restart和same-key original-status
  replay通过；
- commit前中断、commit后响应丢失和人工恢复分支通过；
- raw Arrow IPC可由client直接读取，截断时由HTTP/Arrow失败；
- package成功后清理且RUNNING/manual-recovery artifact不被删除；成功清理后
  Service-owned filesystem对象不得随成功次数`O(n)`永久净增；
- Phase 0–1 canonical bytes、Python/Rust核心golden保持不变。
- Repository package不依赖Shared Kernel/conformance；SUCCEEDED result的artifact与
  manifest binding可由Backend T3核对。

## 18. Reopen conditions

以下变化需要新增或修订ADR/contract：

- untrusted tenant、外网直连或per-repository授权；
- multi-node/shared writable root；
- rollback、promotion或审批发布需要独立CAS；
- resumable/multipart upload或外部对象存储；
- public backup/restore/delete/repair；
- exact CommitId灾难恢复、明确RPO/RTO；
- CurrentTableStore或cross-store consistency；
- Service-owned业务digest、canonical equality或tamper-proof verification；
- table/schema CAS、partial merge/rebase或detached import；
- package超过当前one-shot streaming能力。

## 19. Related authority

- [ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Phase 2 Implementation Design and Delivery Plan](../plans/phase-2-implementation-design-and-delivery-plan.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [DX Cross-Phase Interface Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)
