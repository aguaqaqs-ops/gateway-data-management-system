# P7 S2a 固定多 worker 详细实施计划

日期：2026-11-11。状态：**候选，等待本轮 GPT-6-Astra 独立审核；不得据本页宣称可直接开工或产品已验证。** 源码基线 `38da5bf35cc97f85fe0834ea104d36552155386b`，产品 tree 继承 `p7-s1b-exit`。用户已授权本会话编写、独审并修复文档直到具备编码条件；未授权执行产品实现、测试、push 或部署。最终结论及候选摘要放 `/home/dev/gdds-stage-exchange/p7-s2a/reviews/`。

依据：[S2 正式设计](p7-s2-design.md)、[S0 §12](p7-s0-owner-decisions.md#12-s2-简单性与业务边界收口2026-11-11)、[比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)。固定单组、单 backend/RS 服务实例，同规格 W=K；N1、多 Workspace/兄弟候选及同库 Submit 受理冲突保留。S2b、S3、S4b 的范围不提前实现。

## 1. 实现选型与最小机制

采用**固定 worker 实例、各自恢复自己的遗留任务**，不采用健康 peer 周期扫全组抢占的方案。每个实例有配置编号 1..W、一个进程生命周期文件锁和稳定 worker_id；lease_token 仍每次领取随机产生，CAS 和原请求身份继续保护业务结果。固定编号不是动态可租借槽位，不存在 W>K 或新的持久租约表。

该方案对应当前具体风险：复制启动同一 worker 会超出预算；租约过期而旧计算仍运行时，另一实例重算会使实际活动计算超出静态计划。标准同机 flock 加受控容器退出检查足够，不增加监督服务、心跳注册表或 worker 互相杀进程。代价是一个实例故障后该实例的任务等待它重启，其他实例不会自动救援；Owner 已接受降容和人工处理。此处必须同步 S2 设计中“恢复竞争”的含义为同固定实例重复启动竞争，而非任意 peer 自动接管。

没有历史数据兼容要求：旧随机 worker_id 不建设别名/双读/回填。开发本地 DB 按仓库单基线规则重建；已有正式恢复状态来源若不匹配本设计，拒绝启动并报告，不静默改归属。

## 2. 源码接点与明确改动

下表为基线实际源码（路径以 `vnext/` 为根），新文件标明“新增”。

| 接点 | 当前事实 | 本轮改动 |
| --- | --- | --- |
| `backend/.../operations/worker_startup.py` | 一致读事务扫描完整性/拓扑，随后逐对 recovery，二次门禁；worker_id 默认 UUID | 注入固定实例身份；跨实例任务只验证、不恢复；保留同读事务拓扑一致性 |
| `backend/.../operations/recovery.py` | `StartupRecovery.recover_pair` 对任意 live RUNNING 返回 RETRYABLE_BLOCK；只在启动扫描 | live foreign lease 不阻塞；只对 own instance 旧任务等待到期并按 fresh-read/CAS 恢复；局部 manual/backoff 不阻塞整个组 |
| `backend/.../operations/persistence.py`、`infrastructure/control_db/sqlite_operations.py` | claim 位于 BEGIN IMMEDIATE 事务，按 eligible_at/created_at/step_id 取首个任务 | 原算法保留；不添加第二队列或优先级；对并发连接做实际领取测试 |
| `backend/.../bootstrap/operation_worker.py` | 生产用 `_R4WorkerStartup` 覆盖 claim，`_StartupBudget` 有限等待；run 建 native kernel/telemetry | 身份/锁先于 kernel、startup、telemetry；真实生产与普通 startup 路径同规则；生命周期锁不得过早释放 |
| `backend/.../settings.py` | worker 无固定实例参数；启动60s、租约30s、心跳10s、drain180s | 新增严格整数 `instance_index`；保留原时间参数，不通过增加超时掩盖恢复问题 |
| `backend/.../bootstrap/worker_instance.py`（新增） | 无固定实例所有权 | 封闭身份生成、普通生命周期 flock、校验实例范围；没有持久业务状态 |
| `backend/.../deployment_config.py`、`repository_service/.../deployment_config.py` | 两份同契约 parser 把 count/active_limit 限为1；host adapter加载backend版 | 同步 count/active_limit 的1..32与相等校验；预算公式保持；更新共用向量与文档，不建新共享包 |
| `scripts/render-runtime-config.py`、`deploy/compose.yaml` | renderer 用单 worker 服务的 replicas=count；worker restart=unless-stopped | 生成固定编号服务且每服务replicas=1，共用同一镜像/预算；标准命令不自动扩容/重启；维护入口见§7 |
| `backend/.../http/dependencies.py`、`app.py`、`settings.py` | ClosableAdmissionGate 仅 close，计数私有；HTTP shutdown关闭门但停止服务 | 增加只读快照；维护启动配置和内部关闭/查询接线，保留HTTP读取与原operator recovery |
| `backend/.../application/submission/{accept,accept_transaction,finalize_transaction,abort_transaction}.py` | T1 占用并冻结expected technical commit；finalize/确认abort释放repository占用 | 不改业务语义；并发验证先冲突、后释放、UNKNOWN不误释放 |
| `backend/.../infrastructure/artifact_store/{layout,local_store,maintenance}.py`、control_db各cache | root SH/EX、no-replace发布、短SQL/保护、discard_if_same 已有 | 按§6证明多进程协作，只有实证缺口才作局部修复，不新增生成者协调协议 |
| RS `runtime.py`、`versioned_import/{locks,worker}.py`、`versioned_read/{application,provider,http_service,arrow_bridge,wire}.py` | import使用同库reservation；冷读取未接入；流错误可能发生在200之后 | §6.1复用同一registry保护实际CLI访问，许可在200前取得、实际退出后释放；释放唤醒dispatcher |
| `repository_contracts/.../versioned_read_constants.py`；`repository_client/.../{client,retry,arrow_stream}.py` | 503只做3次短重试，不足以等待分钟级争用 | §6.2专用busy码及有界read admission等待；不改变其他故障重试 |
| `backend/.../infrastructure/statistics/queries.py`、`statistics/queries.py`、`http/{schemas,routes}/statistics.py` | group查询每role只取1个进程，DTO最多3项 | §6.3返回有界多实例观测；保留进程代际，不将统计用作锁/在线注册表 |

表中 `repository_contracts/...` / `repository_client/...` 分别为 `repository_contracts/src/gateway_repository_contracts/` / `repository_client/src/gateway_repository_client/`；`backend/...` 完整前缀为 `backend/src/gateway_backend/`，RS 为 `repository_service/src/gateway_repository_service/`。实施前基线若前进，只核增量，不重新设计已确认业务。

## 3. 固定实例身份和进程边界

### 3.1 配置与锁

- `GATEWAY_BACKEND_OPERATION_WORKER_INSTANCE_INDEX` 为必填严格正整数，范围1..resource_profile.worker.count；无默认猜编号，bool/小数/越界拒绝。同组同规格、count=active_limit且1..32，32是配置输入有界上限而非已验证容量。
- worker_id 固定为 `worker-<namespace_sha256>-<index>`：namespace 为已有canonical JSON编码的 `[environment_id, group_id]`，完整SHA256十六进制；index为无前导零十进制。仅这个封闭格式用于新持久记录，lease_token 仍按现有 UUID4 生成。无新schema字段；统计的process_instance_id仍每次启动随机。
- 锁文件为已校验 `be-metadata` 内 `.gateway-worker-<index>.lock`；普通文件、O_NOFOLLOW、同mount/权限/euid边界沿 deployment identity，flock EX|NB。重复实例立即非零失败，不等待、不删旧锁、不替换inode；文件存在不表示被占用，进程锁才表示占用。普通metadata维护不得删除/重命名这些文件。
- 在运行preflight、compare_configuration和实例参数校验后获取锁，随后才初始化kernel/组装runtime/开始统计。锁FD不继承到exec；运行期间root身份变化沿现有锁存拒绝。采用同机协作信任域，不加恶意同UID防护平台。
- 锁持有至整个进程退出；尤其不能在 `run()` 的 finally 返回时先释放，因为未join的non-daemon executor可能仍活着。实现用进程级FD保持到OS关闭，正常退出亦由OS收尾，不以GC析构作为释放依据。测试独立子进程，不让多次调用run共享测试进程伪装进程生命周期。
- 正式入口每容器一个worker进程；替代实例必须等旧容器停止且其cgroup内执行进程退出。flock不能证明未继承FD的子进程已退出，不能据它单独启动额外算力。基线backend计算为进程内线程/Rust；若实现新增子进程，必须继续由同容器生命周期约束，不新建监督器。

### 3.2 部署与配置变化

renderer保留服务 `worker` 代表实例1，新增 `worker-2`…`worker-W`；每服务注入对应编号、replicas=1、相同CPU/内存/镜像。新增服务用标准Compose `extends` 继承基础worker服务并覆盖编号和已渲染mount/预算，引用绝对base compose路径；不得假设Compose副本序号是应用配置。用compose config实际验证继承结果，不手写第二套镜像/环境清单。基础worker镜像显式统一tag，新增服务不各自构建不同源码镜像。

基线worker的restart改为 `no`，故障后由运维使用标准命令启动原固定服务；不声称自动救援。禁止通过 `--scale` 增加同服务副本，重复编号仍会被flock拒绝。render/check与维护脚本按明确Compose project labels查询实际实例；不按宿主全局容器名或字符串前缀碰其他栈。

改W、环境/组身份或root前先在旧配置处理全部RUNNING/UNKNOWN，确认worker退出。队列与已完成记录可保留，但不能带无法被新实例识别的RUNNING状态启动。启动扫描遇到RUNNING的worker_id格式/namespace/编号不匹配当前配置时组级拒启，要求恢复旧配置完成处置，或按明确开发重建流程处理；不自动转派或清记录。合法终态中的旧身份不阻塞扫描。部署配置记录仍由backend明确启动发布，worker不能改写它。

## 4. 启动、恢复和领取算法

### 4.1 一致性和恢复范围

保持 `scan_active_integrity`、拓扑/registry版本校验和二次门禁；每次扫描在一个既有read UoW快照内，不因别的worker提交而把跨快照片段拼成损坏。扫描完成后不要把旧pair当写入事实，恢复在write UoW重读operation/step、状态、租约、版本与实例owner。

| 扫描到的状态 | 处理 |
| --- | --- |
| PENDING/RETRY_WAIT | 原规则待领取；future retry_not_before不阻塞worker ready |
| MANUAL_RECOVERY_REQUIRED | 保留占用和警告、不自动claim；其他合法任务继续 |
| 合法其他实例RUNNING，无论lease是否过期 | 不改、不抢占、不阻塞本实例ready；由对应固定实例重启恢复，过期不证明进程已死 |
| 本实例遗留RUNNING且lease尚有效 | 只等待本实例原lease自然到期，沿60s startup budget；绝不提前清租约。拿到锁证明原同实例进程不再持有锁，但不改变原lease语义 |
| 本实例遗留RUNNING且lease已过期 | 短write UoW fresh-read/CAS，沿原能力分类转RETRY_WAIT或MANUAL；原token/版本作为写前置 |
| 不支持schema/job版本、拓扑损坏、非法RUNNING owner | 按现有完整性规则拒启，不降级成“跳过坏任务” |

同固定实例符合单executor不变量，至多一个遗留RUNNING；多个属于该实例的RUNNING视为完整性失败，不任意选择。own live lease等待超过原startup预算时非零退出并诊断，不新增无限轮询。foreign live/expired不进入该等待预算。

`StartupRecovery`注入当前实例worker_id（生产强制；测试显式提供），在任何lease判断之前过滤owner；普通WorkerStartup和 `_R4WorkerStartup`一致。`recover_pair`写事务再次确认own owner，已成为终态/RETRY_WAIT则NO_ACTION，fresh live只阻塞本实例。恢复CAS失败回下一次有限startup重读，StoreBusy沿既有退避，不改成功状态。

### 4.2 保留既有恢复分类

PURE_RECOMPUTE 转原RETRY_WAIT，保留checkpoint、frozen input、prior outputs与保护；attempt_count仍在下一次claim按原规则增加。EXTERNAL_EFFECT只调度原reconcile路径，带原固定package/key查RS结果，不重做T1或换key。预算耗尽、NON_RETRYABLE或operator恢复会话失租按原规则进入MANUAL且保留业务占用。

`startup_disposition_after_recovery`须区分“已持久化的任务局部manual/backoff”和组级失败：前者完成转换后READY，后者拒启。不为了READY吞异常或改变后续handler的失败语义；保留 `classify_startup`/transition的现有业务diagnostic，只有必要语义改变才修订Contract与golden。

恢复准备完成后沿原claim算法领取任意符合条件的任务，不把日常任务永久分配到实例；固定owner只针对当前RUNNING窗口。重启恢复后的RETRY_WAIT已清旧租约，其他实例可以按原队列领取，因为旧执行者已退出且恢复事实已提交。

不新增周期全组recovery扫描；某实例崩溃而尚未重启时其任务可以停留RUNNING/过期，其他实例照常工作。运维依据进程状态和原operation诊断重启对应实例；统计丢失不阻止恢复。lease/CAS仍拒绝旧token结果，即使worker_id跨重启相同。

## 5. 配置、资源和版本

两份 deployment_config parser、host renderer、共享配置向量同步改count/active_limit范围及相等关系，不增schema别名。默认单worker配置保留E32GiB/reserve8GiB/M24GiB/N1；本阶段不开放N>1调参，N2同输入核对最迟S5且开放前完成。

新增双worker验证profile作为**工程建议，实施准备需确认后方可在节点执行**：W=K=2，N1，每worker E16GiB/reserve8GiB/M8GiB、CPU2、swap0；backend2GiB/CPU1，RS4GiB/CPU2，host reserve8GiB/CPU2；合计46GiB/CPU9，可在满足条件的64GiB/32CPU节点保留余量。scratch/staging沿原合法上限，仍受各任务/磁盘实际空间限制。该profile只证明明确小输入的正确性，不推广为t4或生产容量结论；真实节点内存、祖先cgroup及缓存实查，不凭历史配置选机。

若Owner不接受此档位，实施前选能容纳2×现有E32GiB与共享服务的获准节点，或暂停双worker取证；不在运行中降reserve、扩大M或超配。这属于运行资源确认，不阻止A–E编码准备。产品依赖/lock不主动变更；需要新依赖先讨论最小标准库方案。

## 6. 缓存与 RS 协作验证/修复范围

保留现有 `LocalArtifactStore.put_chunks` 私有staging、no-replace发布和已有对象校验；root借用先于DB事务，hash/计算在DB事务外。计算cache先pin完整refs、写完再store索引；旧值读取者自己的operation保护不能被新索引替换清掉。snapshot export、canonical和comparison/risk缓存按各自真实路径验证，不以某一cache测试代表全部。

同key miss可以重复计算。仅在发现明确失败时修复相应发布/保护/discard原子边界，不增加生成者租约、缓存全局锁或可靠投递。root级cleanup拿不到EX跳过；损坏canonical修复busy沿既有有限错误/重试，不阻塞整个设备的所有业务。

### 6.1 RS 同库物理访问

RS保持单服务进程、DurableRootLock及原versioned_import repository reservation。现有MAX_IMPORT_WORKERS/MAX_ROW_STREAMS等配置继续有限，不按backend W盲目倍增。采用保守的**同repository物理CLI访问独占**，包含read/read与read/import；不同repository独立，已经完整命中的backend缓存不进入该许可。该锁不跨上传、预览、人工确认或整个History任务，不改变业务SubmitAttempt占用。当前采用离线CLI，不把SQL server多连接能力当成多个CLI进程安全的证明。

- 复用 `RepositoryLockRegistry` 的进程内reservation状态，不加DB表/RW锁/新队列。import保留先try_reserve再durable claim的流程；read通过同一原子try_reserve获得一次可幂等release的许可。read失败立即返回busy，不持有线程等待；import遇到read占用继续留在既有队列。
- runtime把同一registry注入read provider factory。`read_ref`、`commit_exists`、`catalog_at`各自包住整次实际CLI调用（catalog内部存在性查询不嵌套取锁）。stream在 `stream_table_at` 返回iterator之前取许可，覆盖直到Dolt进程及producer确实结束；缓存catalog与row stream可分次获取，均指定exact commit，不依赖两次之间main不变化。
- 许可用显式可关闭对象/iterator管理，不依赖generator从未启动时不会执行的finally；构造失败、未消费close、正常结束、断连/取消、bridge创建失败在确认无执行者后唯一归还。HTTP200发出前必须已取得许可，不能把busy藏到首次next中。metadata或stream异常后若无法证明Dolt child/producer已退出，保留该repository reservation并记录结构化故障诊断，同库后续访问返回busy，其他库可继续；不提前放下一次访问，也不宣称已有全服务fault latch/not-ready。人工核实进程退出后按受控流程重启RS以重建进程内registry，不提供在线强制清许可接口；不能仅等300秒或看到请求结束就释放。不得把流中途的真实故障伪装busy或重开输出流。
- read和writer释放reservation都在registry锁外通知原dispatcher；`Condition.wait()`无timeout，遗漏通知会使待执行import永久睡眠。注册唯一唤醒回调，关闭时解除；不在registry锁内回调dispatcher，保持既有guard/scheduler锁顺序与entry淘汰保护。无需轮询常驻服务。
- 不承诺读写公平或无限负载零等待。实际Dolt集成证明同库CLI无交叠、不同库可交叠、读结果绑定原commit、取消后进程已退出；不是仅mock一把锁即完成。

### 6.2 争用与真实错误分开

私有RS Contract新增 `REPOSITORY_BUSY`（HTTP503，沿现有有界错误DTO，仅表示上述许可未取得）；reader/wire必须在200前映射。普通 `SERVICE_NOT_READY`、网络/格式/磁盘错误保持原分类。同步constants导出、client错误识别和wire golden；无兼容别名。

在 `repository_client` 的versioned read请求及Arrow **open阶段**复用 `RequestControl` 实现busy等待：每次逻辑请求首次尝试锚定300秒read-admission上限，与调用者已有deadline取较早者；只对合法 `REPOSITORY_BUSY` 固定间隔1秒可取消重试同repository/commit/table请求，不计普通3次故障重试预算、不重置等待起点。每次等待前后检查cancel/deadline；关闭响应/连接后再等，不持有RS permit或半成品spool。成功200后恢复原caller deadline/流idle限制，不用新增admission预算截断已经打开的流。

300秒是本轮有限争用等待上限，不是新增业务期限，也不是已测性能承诺。基线production kernel的deadline可能为None，不能假称已有operation绝对deadline：无caller deadline仍用这一个有限上限。超时沿原client timeout及任务有限重试/失败规则，持续超过上限可能失败，不能承诺无限等待后必成功。已有Workspace等绝对期限及重试预算不延长；不借用只适用于已受理RS operation的 `healthy_external_operation_wait`，不新增持久checkpoint或任务状态。

接线覆盖 `bootstrap/composition.py` 的resolve_ref、`infrastructure/repository_read/parent_catalog.py`及`http_arrow.py`的catalog/row两种读取；底层client统一处理，避免每handler复制等待。`resolve_versioned_ref`补可选cancel/deadline参数及RequestControl接线；T1主引用解析无kernel context，只有300秒上限，不能声称受worker drain控制。worker内读取传现有context cancel/deadline，原heartbeat继续。普通502/503的原3次短重试不变；已暴露Arrow bytes后绝不因busy自动重放。Repository Contract同步修订“每请求最多3次且不叠加重试”的明确busy例外。测试用注入时钟验证分钟级busy后成功、300秒截止、较早caller deadline/取消、真假busy区分、响应释放和流不重放，不实际sleep5分钟。

### 6.3 多实例统计查询

修正 `SQLiteStatisticsReader.group` 每role LIMIT1的遗漏：在现有查询时间窗内按 `(role, process_instance_id)` 去重，以 `MAX(sampled_at_us) DESC, role, process_instance_id` 稳定排序，取最多101条用于判定截断，只返回前100条。保留SQL时间/扫描结果/字节预算，昂贵查询仍沿原budget错误处理，不引入全量历史扫描服务。

`GroupRead`和 `GroupStatistics`增加必填 `instances_truncated: bool`，`current_instances`上限改100；元素继续只有role/process_instance_id。该字段明确表示“时间窗内最近观测到的实例”，不表示在线或固定W，不从缺少采样判worker死亡；旧进程和重启的新进程分开。更新 [Statistics Contract](../contracts/statistics-and-query.md)、HTTP DTO/OpenAPI、query/contract测试；无需改statistics DB schema，也不把稳定worker_id塞进现有resource_sample。该变更属于工作包C。

双worker同库Submit的竞争应在AcceptSubmit就拒绝后者，已受理者finalize后才放行；不改expected technical commit冻结点，不建设待提交队列。异常后工作流占用不随普通task terminal自动释放，维护/API新增接线不能绕过它。

## 7. 维护入口：闭门、停止领取、保留队列

新增内部维护接口仅控制当前backend进程已存在的AdmissionGate，不新增数据库状态机或公共前端交互：

- `POST /internal/v1/maintenance/drain`：沿 `require_internal_bearer` 授权，无任意路径/命令参数；幂等close gate、ready=false，返回 `{accepting_new_work:false,in_flight:<非负整数>}`。
- `GET /internal/v1/maintenance/drain`：同权限，返回同一锁下的门状态/在途受理请求数，供维护脚本等待归零。不是组任务队列数，不暴露token/PID/路径。
- 不提供在线open；恢复服务通过明确重启。`GATEWAY_BACKEND_MAINTENANCE_MODE` 为默认false的严格布尔启动配置；true时启动完成仍闭门/not-ready，查询与原operator recovery可用。记录在Compose配置，不写control DB；操作说明要求维护期间以该配置重启，避免意外恢复受理。
- 复用所有原 `acquire_new_work` 路由（包括上传、Preview/History发起、Submit、Review/Archive变更）的关闭语义与原错误码；既有GET读取/下载及内部operator恢复不经过该门。不能仅禁上传而遗漏其他任务入口。OpenAPI路由allowlist和权限测试同步。

新增 `vnext/scripts/manage-worker-group.py` 为一次性运维命令，不常驻、不自动重启或kill。`drain`接收既有Compose配置文件/project及凭据文件引用，认证值不进入argv/日志；先校验profile、实际project服务清单/编号与无额外副本，闭backend门并等待in_flight=0，再对该project所有worker发送SIGTERM（Docker signal接口，不能使用带超时SIGKILL的compose stop/down）。固定有限180s等待，超时非零、列明仍运行实例并保留栈，不再发KILL、不删卷或锁。

worker原signal/drain/协作handoff保留，正常结束退出0；异常/超时不伪装排空成功。停止所有worker后，核容器状态及cgroup进程为空；此时只称worker已停，RS/backend保留供查询/恢复，仍可能写缓存/统计或有已受理import，不能称整组QUIESCED。脚本失败保持AdmissionGate关闭，不自动回滚开门。

仅重启同配置worker可止于上述drain。改root、组身份、W或版本/schema前，先用旧配置核清RUNNING/UNKNOWN及RS原请求结果，再执行脚本 `stop-group`：先drain，再SIGTERM backend并等其容器/cgroup完全退出，最后SIGTERM RS并等其进程及Dolt children完全退出；每步有限180s，任何失败/超时即停，不强杀或开始变更。不通过HTTP“ready=false”代替进程退出，也不因进程退出删除UNKNOWN业务事实。先停调用方再停RS；停止失败保留原配置/卷以便恢复。两项均满足才进入维护变更：业务已达到本次变更要求、整组全部写入进程已静止。S4b副本捕获可保留故障事实的独立规则不由此实现。

为恢复旧配置遗留RUNNING，可在backend maintenance模式下**显式**启动对应worker，但Compose service_healthy依赖会阻止默认up；运维命令只在检查backend进程可读、storage/config健康和RS ready后使用原容器start（不recreate、不绕配置验证）。此时worker可能领取已有任务，这是明确恢复步骤，不称静止状态；完成后再drain确认无RUNNING/UNKNOWN。正常恢复以已确认配置重启backend至ready，再启动固定worker；原绝对期限/恢复预算不延长。

## 8. 工作包、风险及逐包交付

每包交付代码、相应Contract/文档和最小测试，按main规则实施/独审；当前会话只准备这些计划。A–F是工作包，不是六个阶段退出。

| 包 | 改动与依赖 | 风险/测试owner | 完成条件 |
| --- | --- | --- | --- |
| A 配置与身份 | §3/§5 parser/固定identity/生命周期锁，两个parser与共享vectors；依赖无 | B；deployment/worker process | 越界/重复进程拒绝、同组身份稳定/token随机、资源累计校验、锁直到进程退出 |
| B 启动与恢复 | §4，依赖A；普通/生产_R4路径同步，claim本身不重写 | B，涉及effect的A；Operations/Submission | foreign有效/过期不误接管；own等待/恢复，manual/backoff局部化，旧token拒绝 |
| C 共享资源 | §6缓存/RS许可与client等待/多实例统计；依赖A/B并发harness | C缓存，A/B发布及RS事实；各现有owner | 同key写/读取/cleanup/中断、exact-commit/import互斥与忙等待、Submit占用、统计两实例可查 |
| D 固定部署 | renderer/base compose/共用镜像/配置/实例枚举；依赖A/B | B；部署/容器 | 两个真实进程同时工作，重复实例失败、资源限制生效；现有单worker门禁仍成立 |
| E 维护与重启 | §7 API/脚本/settings/HTTP路由allowlist；依赖D | B，原业务A不变；HTTP/lifecycle/容器 | 闭门在途归零、保留GET/operator、所有worker停claim、无强杀、队列重启和期限保留 |
| F 最终核收 | A–E收敛后，实施总结/独审/受影响权威包+容器+获准真实范围 | 按阶段 | 无未关闭阻塞，证据绑定最终H，明确未测/移交，不提前打tag |

A/B类按现行流程逐包独审，C/D只做比例化必要核查；F一次新上下文全范围独审覆盖全部包，不重复同一全量审核。实施者focused，协调者调用自动门禁，无专职测试者。正式源码/Contract入库；过程报告放 `/home/dev/gdds-stage-exchange/p7-s2a/`。本轮Astra是计划独审，不替代未来产品代码独审。

## 9. 测试清单与执行入口

复用既有文件，每不变量一个owner；新增用例名按业务行为，不按审核编号。真实时序/进程/Dolt测试按现有markers，不能把以下表全部强塞unit。参数差异用共享参数表，不为纯映射/校验启动Dolt。

| 现有测试owner（backend/tests，注明RS除外） | 必增/调整行为 |
| --- | --- |
| `test_deployment_config.py`、`test_deployment_identity.py`；RS对应配置测试 | 两parser和共享向量：W=K=1/2合法、W≠K/越界/预算不足拒绝；runtime配置不符拒绝 |
| `test_operation_worker_process.py`（实例锁用子进程） | 重复编号不能启动；不同编号同时存活；异常返回但executor未退出时锁仍持有；同slot重启获取锁且新lease token |
| `test_operation_worker_startup.py`、`test_operation_job_recovery.py`、`test_operation_recovery_policy.py` | foreign live/expired、own live→expired、fresh状态改变、manual与backoff不全局拒启、非法owner/损坏仍拒启；更新原“任意有效租约阻塞”断言 |
| `test_operation_worker_integration.py`、`test_operation_recovery_process.py` | 两进程对同一SQLite不同连接领取，每step只一个有效执行窗口；崩溃后的原slot重启，peer继续；旧token结果不能覆盖 |
| `test_submit_transactions.py`、`test_submit_recovery.py`、`test_submit_compose_e2e.py` | 同repo T1竞争唯一受理、成功后放行；UNKNOWN/RS已commit未finalize原key恢复，不重复Submission/commit |
| `test_computation_cache.py`、`test_snapshot_export_cache.py`、`test_canonical_table_cache.py`及artifact现有owner | 同key双进程miss、不同key并写、旧读者保护、discard_if_same、cleanup交错、发布中断；无半成品/错删 |
| RS `test_versioned_read_provider.py`、`test_versioned_read_process.py`、`test_versioned_read_http_integration.py`、`test_versioned_read_arrow_bridge.py`及import owner | 同库read/read/import不交叠，不同库可交叠；200前busy、未消费close/断流/取消归还、join失败不放许可、release唤醒队列；输出绑定原commit |
| repository_contracts/client现有wire/retry/Arrow测试；backend repository adapter owner | 专用busy码、300s锚定预算/取消与普通故障重试分离；resolve/parent catalog/History覆盖，不重播部分流 |
| `test_statistics_queries.py`、`test_statistics_contracts.py` | 两worker同时可查、重启代际分开、100条截断明确、预算和权限保持，不误称在线集合 |
| HTTP admission/shutdown、`test_operator_recovery_http.py`、OpenAPI allowlist | 内部maintenance权限/幂等/计数；已开始上传持有名额直至结束；关闭后拒新工作且GET/operator仍按原权限可用 |
| `test_operation_worker_lifecycle.py`、Compose harness新增多worker旅程owner | 维护超时不SIGKILL、不自动开门；queued保留、checkpoint交接、过期不延时；实际全部固定实例、容器cgroup与镜像身份 |

Compose harness `tests/support/compose_gate_harness.py` 现写死worker-1和单镜像/ready日志：按project labels+固定实例编号枚举全部worker，并逐实例核日志ready、镜像、资源、退出；默认W1路径保留语义，不以任一worker ready冒称全部ready。新增一个内聚多worker容器旅程，不把每个unit场景复制到Compose。

调试入口示例（只能在专用节点、clean已提交worktree执行）：`UV_OFFLINE=1 CARGO_NET_OFFLINE=true TMPDIR=/home/dev/gdds-test-tmp vnext/scripts/uv-consume.sh -C vnext/backend run pytest tests/test_operation_worker_startup.py tests/test_operation_recovery_policy.py`；进程组按实际serial marker单进程运行，RS真实Dolt组显式integration。Rust无改动不主动重编新方案；backend环境同步仍按仓库规则重装并核Rust build input。

F用 `scripts/run-stage-gate.py <完整SHA> --packages repository_contracts,repository_client,backend,repository_service --purpose stage` 起步，本轮私有busy Contract/client已受影响；其余shared/Rust路径按真实闭包补包，不照抄固定包清单；实际CLI和配置以main scripts/README为准。Compose/env/harness已变，最终候选必须有实际容器结果，不能拿S1b旧镜像当本轮通过。无依赖输入变化时复用合法dependency-base，离线本机构建。五包ruff/mypy及适用其它检查按AGENTS，不在开发机运行。

真实范围建议在实施准备一次按DC33确认：已有t1最小上传→Preview→Submit→Review/Archive→查询及重复无变化，叠加独立Workspace Preview/History在固定commit上的重叠；不同设备并发用明确小fixture覆盖，不伪造真实设备身份。绑定输入/配置，单worker与双worker核正式业务结果，耗时仅报告观测。无新增t2–t4全旅程/性能矩阵；没有批准前不运行这部分，但可做已授权编码/非真实focused。此前S1b真实范围不自动继承。

## 10. Contract、文档和退出条件

实施按包修订：[Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md)的实例owner、startup/恢复及维护语义；[External Effect](../contracts/external-effect-and-recovery.md)说明同slot重启不改变原key/UNKNOWN；[Business Lifecycle](../contracts/business-lifecycle-and-state.md)仅澄清既有Submit受理占用与维护不等于取消，不改candidate/归档规则；[Repository Service](../contracts/repository-service.md)更新配置、物理访问许可、busy码和有界等待的3次重试例外；[Statistics](../contracts/statistics-and-query.md)更新实例列表与截断语义；[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)与API/部署说明按实际接线同步。不为普通锁文件新增业务schema或兼容协议。

最终交付必须包含：A–E源码与Contract同步、原审finding关闭、各实例真实进程/资源证据、最终受影响包/容器门禁、获准真实范围或明确阻塞、原始失败及修复引用、D24移交与本人资源收尾。阶段退出tag的创建须由后续实施授权明确覆盖，本轮不预授予。

编码准备完成的判断：所有表内行为/错误/owner/接线有明确方案，独审无未关闭阻塞finding。资源档位和DC33真实范围属于**执行前确认项**，必须在相关运行前落实，不能写成已授权/通过；它们不要求产品算法另作设计。源码增量若推翻本计划、必须引入新持久协议/服务、扩大业务承诺或修改信任边界，停止受影响工作交Owner；普通可逆细节及已审方案修订由实施者/原审解决。
