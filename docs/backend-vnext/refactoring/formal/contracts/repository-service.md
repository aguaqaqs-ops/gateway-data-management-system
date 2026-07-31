# Repository Service Contract

状态：Accepted Simplified Baseline

日期：2026-07-31

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
| `CommitId` | Dolt生成的repository-scoped opaque string |
| `RefName` | bounded string；V1只保证`main`存在 |
| `IdempotencyKey` | caller生成的bounded opaque string |
| provider token | bounded opaque string，不施加UUID或canonical grammar |

`RepositoryId`、`ArtifactId`和`RepositoryOperationId`可以直接使用`uuid.UUID`；
不得为每个ID复制自定义比较、hash、wire parser和schema版本。

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

不建立create operation、全局create journal、lease、fencing或后台executor。

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

已确认规模为通常10–100 MB、极端约200 MB。初始建议默认单包上限256 MiB并允许
部署配置提高；该数值是可调admission默认值，不是稳定wire常量。

## 9. Import package

V1 package固定为`tar+zstd`，只包含：

```text
manifest.json
replay.sql
```

Service检查：

- entry是固定名称的regular file；
- 无absolute path、traversal、duplicate、link、device或额外required entry；
- compressed和expanded size在部署上限内；
- manifest具备table、schema和row count的基本结构；
- upload bytes的raw size和SHA-256已匹配。

业务digest和canonical content equality由Storage Projection/capability owner拥有。
Repository Service不提供`NONE | STRUCTURAL | FULL`，不默认读取全部committed rows
重算业务digest。

外部原始package备份由上游流程拥有。Repository Service不调用、等待或查询外部
备份系统。

## 10. SubmitVersionedImport

Import是V1唯一异步业务operation。请求至少包含：

```text
repository_id
artifact_ref
target_ref
expected_commit_id
idempotency_key
```

V1只保证`target_ref = main`可用。`expected_commit_id`同时是：

- 新commit的parent；
- target ref发布时的CAS预期值。

Service不得提供LWW、force ref或独立publication mode。成功必须满足：

1. Dolt执行受信`replay.sql`；
2. 创建带operation marker的新commit；
3. committed catalog的table set、schema和row count匹配manifest；
4. target ref仍指向`expected_commit_id`；
5. CAS发布target ref到新commit；
6. durable operation result保存commit_id和target ref。

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

- same key/same fingerprint返回原接受结果或终态；
- same key/different fingerprint返回冲突；
- terminal failure后要发起新的业务尝试，caller使用新key。

启动时只恢复遗留RUNNING import：

1. 找到唯一matching operation commit且ref一致：补齐SUCCEEDED；
2. 未找到matching commit：使用原artifact和原key自动重试一次；
3. 多commit、ref矛盾、artifact缺失或无法判断：终止为
   `FAILED / MANUAL_RECOVERY_REQUIRED`。

不建设lease、fencing、ServiceEpoch、takeover或
`UNKNOWN/APPLIED/VERIFIED`状态机。

## 12. Artifact lifecycle

Artifact是临时import输入，不是长期对象存储：

- RUNNING operation引用的artifact不得清理；
- import成功且operation结果已持久化后删除本地package；
- orphan和普通失败artifact使用可配置TTL做best-effort清理；
- 初始建议TTL为24小时；
- `MANUAL_RECOVERY_REQUIRED`引用的artifact保留到人工处理；
- 不提供public artifact delete、retention或GC API。

Artifact清理失败不得改变已经成功的commit或operation结果；通过普通日志和磁盘
admission暴露，不建立独立cleanup evidence状态机。

## 13. Catalog and row stream

Catalog和row stream必须绑定caller提供的immutable CommitId，不提供
`LATEST_AT_START`。需要读取当前main时，caller先ResolveVersionedRef取得CommitId。

`StreamVersionedTableRows`直接返回标准Arrow IPC stream HTTP body：

- 不使用JSON/base64 frame envelope；
- 不增加checkpoint frame或末尾内容SHA；
- schema和截断由Arrow reader/HTTP失败表达；
- server必须按RecordBatch bounded streaming，不全表materialize；
- disconnect/cancel关闭provider reader。

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

## 15. Persistence and disaster recovery

Versioned commit history永久保留。Repository Service不提供public backup/restore
API。部署方对整个quiescent durable root执行一致性volume snapshot并由operator
恢复。

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
- import CAS、operation marker、catalog结构检查和幂等通过；
- commit前中断、commit后响应丢失和人工恢复分支通过；
- raw Arrow IPC可由client直接读取，截断时由HTTP/Arrow失败；
- package成功后清理且RUNNING/manual-recovery artifact不被删除；
- Phase 0–1 canonical bytes、Python/Rust核心golden保持不变。

## 18. Reopen conditions

以下变化需要新增或修订ADR/contract：

- untrusted tenant、外网直连或per-repository授权；
- multi-node/shared writable root；
- rollback、promotion或审批发布需要独立CAS；
- resumable/multipart upload或外部对象存储；
- public backup/restore/delete/repair；
- exact CommitId灾难恢复、明确RPO/RTO；
- CurrentTableStore或cross-store consistency；
- Service-owned业务content verification；
- package超过当前one-shot streaming能力。

## 19. Related authority

- [ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Phase 2 Implementation Design and Delivery Plan](../plans/phase-2-implementation-design-and-delivery-plan.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
