# Phase 2 Decision Ledger — Round 8–11

状态：**Draft / Active Interview Record**

配套指南：[interactive-design-session-guide.md](interactive-design-session-guide.md)

本文件是 Round 8–11 的唯一 Decision Ledger 正文位置。Decision ID 使用
`P2-R<round>-D<sequence>`；状态只能是 `ACCEPTED`、`REJECTED`、`DEFERRED`、
`OPEN` 或 `SUPERSEDED`。每项 decision 必须记录语义、理由、被拒方案、约束、
downstream impact、formal owner 和 reopen condition。被推翻的记录保留并标为
`SUPERSEDED`，不得删除或在主指南复制正文。

## Round 8 — Security and resource governance

### P2-R8-D01 — Thin static service-bearer authentication

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D01` |
| Topic | Phase 2 production authentication provider |
| Status | `ACCEPTED` |
| Decision | v1只实现`auth_mode = DISABLED | STATIC_BEARER`。DISABLED仅允许显式dev/test profile；production profile必须使用STATIC_BEARER且未配置有效provider/transport security时fail readiness。Credential格式为`Authorization: Bearer <key-id>.<random-secret>`；deployment secret file将key-id映射到stable CallerIdentity并保存高熵token digest，验证使用constant-time comparison。一个principal可同时配置current/next credential用于轮换，更新通过受控secret reload或restart完成，不建设key-management service。Production channel必须经过TLS，可由受信ingress/sidecar终止，endpoint不得外部公开。只保留窄CallerIdentityResolver port供未来替换，首版不实现OIDC/JWKS或mTLS provider。 |
| Rationale | Static service token足以认证已确认的backend/worker/operator内部主体，避免引入用户系统、外部issuer或证书生命周期；双credential允许简单轮换。TLS与internal-only ingress防止bearer在传输中暴露。 |
| Rejected alternatives | Direct mTLS provider：增加证书签发/轮换/撤销和server TLS ownership；OIDC/JWT/JWKS：当前没有issuer/claim/network authority；production disabled auth：unsafe by default。 |
| Constraints | Token、digest、secret path和TLS private key不得进入repository aggregate、backup、log、metric或error。Credential key-id不是CallerIdentity，credential轮换不改变idempotency scope。Liveness可由本机/编排器访问，但不得返回敏感状态；普通API全部经过auth。 |
| Downstream impact | 新增auth middleware、secret schema、TLS deployment requirement、readiness fingerprint、credential rotation、401 behavior、sanitization和production auth negative tests。 |
| Formal owner | Repository Service security/wire contract；Phase 2 deployment security design。 |
| Reopen condition | 平台提供accepted统一mTLS/service-mesh或OIDC identity contract，或出现外部consumer并需要标准federated identity。 |

### P2-R8-D02 — Deployment-global grants with versioned per-repository ACL

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D02` |
| Topic | Authorization authority, policy mutation and existence hiding |
| Status | `ACCEPTED` |
| Decision | Authorization default-deny。Deployment secret/config只保存global actions，例如repository create/restore及break-glass operator；每个repository的control SQLite保存versioned`CallerIdentity -> closed Action set` ACL，并随aggregate backup/restore。CreateRepository caller必须具备global create action且request显式提供initial grants，不自动推断project owner。`GetRepositoryPolicy`/`UpdateRepositoryPolicy`使用独立POLICY_READ/POLICY_WRITE action；policy mutation携带expected policy generation和idempotency key，并与new generation在同一SQLite transaction提交。Persisted ACL只保存具体closed actions，不保存条件语言、wildcard、业务role或row/table规则；SDK convenience bundle在提交前展开。ACL cache只按policy generation索引。未认证统一401；authenticated principal对repository完全无访问时返回404隐藏存在性；已具备repository某项访问但缺少当前action时返回403。GC、backup、repair、restore和delete plan/execute使用独立operator actions；destructive execute要求exact plan和非空reason，不在Repository Service实现双人审批、MFA或业务审批。 |
| Rationale | Per-repository ACL可随上万项目独立变化并纳入aggregate recovery，global grants解决create/restore及control损坏时的break-glass；closed action避免通用policy engine。 |
| Rejected alternatives | 全部ACL放deployment config：规模化变更与backup closure差；认证后访问全部repository：不满足隔离；table/row/column ACL或表达式语言：复制业务authorization和policy runtime。 |
| Constraints | Route、stream、artifact和provider open前完成authorization。Control authority损坏时普通ACL不得从Dolt猜测，只有global operator可进入accepted restore/repair路径。Action enum和policy schema必须版本化。Restore造成ACL rollback的activation边界由`P2-R8-D06`收口。 |
| Downstream impact | 新增ACL schema/generation/API、global grant config、initial-policy provisioning、action registry、404/403规则、operator reason、cache invalidation及authorization matrix tests。 |
| Formal owner | Repository Service authorization/policy contract；operator security contract。 |
| Reopen condition | Accepted平台policy service成为唯一repository/action authority并提供availability、versioning、backup/recovery和cache invalidation contract。 |

### P2-R8-D03 — Repository-bound artifact transfer with no URL or host-path ingress

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D03` |
| Topic | Artifact ingress/download, SSRF and compressed package safety |
| Status | `ACCEPTED` |
| Decision | v1 artifact只通过authenticated Repository Service-owned HTTP upload、server-created output及authenticated download进入/离开；request不接受URL/URI、redirect target、host path、file descriptor或remote bucket locator，因此不存在server-side URL fetch/SSRF surface。Upload先创建repository-bound identity并声明media type、size、raw digest、content contract和intended action，bytes流式写isolated staging；只有完整close、measured size/digest和versioned manifest匹配后才发布ArtifactRef。Artifact不得跨RepositoryId直接复用。Download每次重新检查当前repository/action authorization与expiry，不提供匿名presigned URL。只允许closed versioned media types。多文件package必须manifest-first，拒绝absolute/traversal、duplicate entry、symlink、hardlink、device/FIFO、NUL及未知required entry，并同时限制compressed/per-entry/aggregate expanded bytes、entry count和100:1 expansion ratio。Canonical SQL replay只消费服务生成并验证的closed grammar，禁止shell、任意SQL endpoint、network/file instruction和database/user/grant mutation。Download filename由server生成并清洗。 |
| Rationale | 移除URL/path输入比建设复杂SSRF allowlist更小且更可靠；repository binding、staged publish和closed package grammar保持artifact identity、授权和解压边界一致。 |
| Rejected alternatives | Allowlisted URL fetch：引入DNS rebinding/redirect/private-address/credential/egress矩阵；caller mounted path：泄漏host boundary；匿名presigned download：新增独立credential/revocation语义；按扩展名猜media：可混淆parser。 |
| Constraints | Upload声明值不是authority，server必须流式测量。断连、超限、digest mismatch或未publish bytes按Round 6/7 cleanup语义处理。Artifact read/write actions分离。Future object storage必须保持相同opaque ref、authorization和no-caller-path contract。 |
| Downstream impact | 新增upload lifecycle、repository binding、media registry、safe package reader、download authorization、staging cleanup、SQL grammar negatives、SSRF/path/archive bomb tests。 |
| Formal owner | Repository Service artifact transfer/security contract；RepositoryImportArtifact content owner拥有其closed package schema。 |
| Reopen condition | Accepted deployment要求cross-node/object-store transfer，并提供受控resolver、credential、egress、SSRF和lifecycle contract。 |

### P2-R8-D04 — Fixed parser limits with mandatory production capacity policy

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D04` |
| Topic | Wire/parser safety limits and capacity admission |
| Status | `ACCEPTED` |
| Decision | v1固定以下wire/parser hard limits：control JSON 1 MiB；inline Current mutation body 4 MiB、最多1000 operations和100000 scalar cells；table/column name最多64 Unicode scalar且不超过256 UTF-8 bytes；RefName总计255 ASCII bytes、单segment 63 bytes；每表最多1024 columns；filter AST depth 16、nodes 256、IN values 1000；metadata page最多1000；cursor最多8 KiB且TTL 15分钟；Arrow frame uncompressed最多64 MiB、server target batch不超过8 MiB；stream/upload idle timeout 60秒、direct stream最长1小时、single upload最长2小时。大型数据容量由production必填、启动校验且有限的ResourcePolicy配置，至少覆盖single artifact compressed/expanded bytes、tables/rows/package entries、per-repository data/artifact/staging quota、node disk high/critical watermark、active uploads/streams/async operations/Dolt runtimes、per-caller/per-repository queue depth及verification/readback byte budget。生效值通过typed ServiceResourceLimits capability公开；caller只能预检，measured usage是authority且请求不能提高limit。Malformed/oversized返回400/413；caller/repository admission返回429+Retry-After；node/disk capacity返回503；均在acceptance前不创建operation。Accepted operation继续按Round 6 effect evidence分类，不因client deadline取消。 |
| Rationale | 固定parser上限防止在admission前耗尽内存/CPU，deployment capacity适配不同数据规模和机器；禁止unlimited保证生产配置明确。 |
| Rejected alternatives | 所有容量固定全局常数：无法兼容不同项目/节点；全部配置且无wire cap：parser可在admission前被滥用；caller请求override：普通请求可绕过service safety。 |
| Constraints | Round 9基于container measurement给出production capacity profile数值，但任何值都必须finite。Size/count检查必须增量执行，不得为验证上限先完整buffer。Batch size不得隐式改变operation sync/async response或atomicity。Config缩紧与accepted operation由`P2-R8-D07`收口，per-repository physical isolation边界由`P2-R8-D10`收口。 |
| Downstream impact | 约束wire schemas、parser/filter/cursor/Arrow codecs、ResourcePolicy/capability、admission queues、quota accounting、HTTP error、load/oversize tests和Round 9 measurement。 |
| Formal owner | Repository Service wire/input/resource-governance contract；deployment capacity policy。 |
| Reopen condition | Accepted真实dataset合法超过某个semantic hard limit，或measurement证明limit过低/过高；breaking wire limit调整必须版本化并保留compatibility策略。 |

### P2-R8-D05 — Hardened single-trust-domain container and metadata-only audit

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D05` |
| Topic | Process/storage isolation, secrets, encryption and security audit |
| Status | `ACCEPTED` |
| Decision | v1明确为internal trusted service-principal、single trust-domain内的多repository逻辑隔离，不宣称对互不信任tenant提供OS sandbox；互不信任tenant需要独立Repository Service/durable root。Production container使用non-root UID、read-only image/root filesystem、独立writable durable root和scratch、no-new-privileges、drop capabilities，禁止Docker socket和任意host mount，默认deny outbound egress。Dolt subprocess使用同一受限identity、固定cwd、sanitized env、显式argv或受控script file、`shell=False`、process-group timeout/kill及resource limits。Server-derived path拒绝symlink/hardlink/traversal/cross-root。Secret、TLS key、token及cursor-integrity key由deployment secret mount注入并排除backup；cursor使用versioned HMAC-SHA-256及current/previous key。Production data root和backup target要求deployment-managed encryption at rest；v1不建设per-repository application encryption/key hierarchy。Security audit至少覆盖auth failure、authz deny、policy change、credential key-id、mutation acceptance/effect、artifact publication/access和全部operator action；operator event记录caller、reason、plan/request digest、before/after identity及result，禁止token、raw row、filter literal、SQL、path或stack。Round 9拥有external audit sink/rotation/alert；effect journal不冒充完整security audit。 |
| Rationale | Container/process hardening与无egress降低Dolt/subprocess和artifact parser风险，同时保持上万repository的单服务模型；强敌对租户隔离通过部署边界解决而非伪造每repo sandbox。 |
| Rejected alternatives | 每repository独立进程/UID/container：重新引入上万运行单元；只做应用路径检查：subprocess/secret/egress边界过宽；per-repository application encryption：增加密钥authority/rotation/restore矩阵且无当前需求。 |
| Constraints | Deployment必须证明TLS及volume/backup encryption profile；Repository Service不接收caller提供的encryption key/path。日志、metric、error和diagnostic统一执行redaction。Filesystem-level quota不属于v1强保证，精确边界由`P2-R8-D10`固定。 |
| Downstream impact | 约束container spec、volume/secret mounts、network policy、subprocess runner、path resolver、cursor codec、backup environment validation、audit events及security/container negatives。 |
| Formal owner | Repository Service security/deployment contract；Round 9 observability/runbook contract。 |
| Reopen condition | Threat model升级为互不信任tenant共享同一service/root，或法规要求application-level per-tenant encryption并提供完整key lifecycle authority。 |

### P2-R8-D06 — Restricted restore activation with an explicitly replaced ACL

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D06` |
| Topic | Authorization rollback after restoring an older aggregate backup |
| Status | `ACCEPTED` |
| Decision | Aggregate restore验证和publication完成后先进入`RESTORED_RESTRICTED`，不得直接READY；该状态只允许当前deployment的global restore/break-glass operator访问。Backup内ACL作为完整evidence保留但不自动生效。`ActivateRestoredRepository`必须显式提交new complete ACL、expected backup ACL digest、current RepositoryIncarnationId、idempotency key和operator reason；即使沿用backup ACL也必须重新提交相同内容。Service在restored control SQLite中原子写new ACL generation及activation evidence，验证后才发布READY。普通repository caller、stream、artifact和mutation在activation前全部拒绝。 |
| Rationale | Older backup可能包含之后已撤销的grant。Restricted activation防止restore静默重新授权，同时让operator决定采用旧policy还是替换，而不引入外部policy service。 |
| Rejected alternatives | Restore后直接启用backup ACL：可能恢复撤销权限；完全丢弃backup ACL：失去审计和恢复参考；迁移到外部policy service：新增authority、availability和DR依赖。 |
| Constraints | Global operator authority来自当前deployment config，不从backup恢复。Activation是独立journaled/idempotent operator mutation，不改变backup evidence。ACL activation失败使repository保持RESTORED_RESTRICTED，不回退到READY或自动使用旧ACL。 |
| Downstream impact | 新增RESTORED_RESTRICTED lifecycle、ActivateRestoredRepository action/result、ACL replacement transaction、restore runbook及stale-grant security tests。 |
| Formal owner | Repository restore/lifecycle contract；repository authorization policy contract。 |
| Reopen condition | Accepted外部policy authority保证non-rollback policy generation并成为restore时唯一授权来源。 |

### P2-R8-D07 — Authorization snapshot at acceptance and current authorization for later access

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D07` |
| Topic | ACL, credential and resource-policy changes after operation acceptance |
| Status | `ACCEPTED` |
| Decision | Operation acceptance是该closed request的执行授权边界；journal持久化CallerIdentity、Action、acceptance ACL/policy generation及resource policy generation。Operation一旦accepted，后续credential吊销、ACL删除或普通ResourcePolicy缩紧不自动取消、重分类或阻止内部worker完成/reconcile原请求；授权变化立即适用于所有新request。`GetOperation`、artifact download及其他后续public access始终按current authentication/ACL重新授权，因此被撤销caller可能无法查询原operation，由global operator继续处理。Plan resource本身不授予execute capability；Execute必须按current policy重新授权，允许与plan creator不同的已授权operator执行并同时审计双方。Accepted resource reservation按acceptance policy继续；node critical safety watermark仍可在effect未开始时使operation以NOT_APPLIED终止，EFFECT_STARTED后保持evidence-first recovery。 |
| Rationale | 逐worker-step撤销会把ACL变化引入external-effect crash matrix；acceptance snapshot保证已接受effect可解释，current access check又确保撤权后不能继续读取结果或创建新effect。 |
| Rejected alternatives | 每一步重新授权并自动cancel：可能在effect窗口制造UNKNOWN；存在operation时冻结ACL：阻塞紧急撤权；撤权后仍允许poll/download：泄漏后续结果。 |
| Constraints | Authorization snapshot只适用于原request，不可派生新target、artifact或follow-up effect。Credential/ACL不进入semantic request digest，但policy generation进入audit/evidence。Idempotent retry在current authorization通过后才可返回历史结果。Emergency critical policy属于service safety，不是普通config shrink。 |
| Downstream impact | 约束acceptance middleware、journal fields、worker context、revocation behavior、plan/execute authorization、resource reservation及mid-operation policy-change tests。 |
| Formal owner | Repository authorization and operation/effect contract；resource admission contract。 |
| Reopen condition | Provider支持可证明的effect撤销且产品要求immediate revocation of accepted work，或外部policy service提供transactional authorization/effect coupling。 |

### P2-R8-D08 — Opaque deployment-configured mounted backup target

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D08` |
| Topic | Backup destination under no-egress and no-caller-path rules |
| Status | `ACCEPTED` |
| Decision | v1只实现deployment-owned mounted backup store adapter。Backup store位于active durable root之外的专用、deployment-encrypted volume；operator API只提交opaque BackupTargetId、RepositoryId和typed backup policy，不接受path、URL、bucket或credential。TargetId到固定backup root的映射由deployment配置；所有physical location由server-derived path resolver生成。Backup先写target-local staging，完成manifest/component digest、durability sync及closure validation后原子发布BackupId。Restore只接受已登记的BackupTargetId/BackupId。Dedicated declared backup mount不属于caller-provided arbitrary host mount；container继续deny outbound egress。Future object storage必须新增受控adapter并重新设计credential、egress、SSRF和lifecycle。 |
| Rationale | Separate mounted target提供最小可用DR failure domain，同时保持v1无外联、无任意path和无云credential；同root backup不能覆盖root loss。 |
| Rejected alternatives | Backup放active root：共同故障；caller提供S3/HTTP URL：重新引入SSRF/credential/egress；任意mounted path：绕过path policy。 |
| Constraints | BackupTarget config/volume identity进入readiness environment fingerprint但不进入repository public identity。Target不可位于active root或其子目录。Backup deletion/retention由operator backup policy管理，不由repository GC。 |
| Downstream impact | 新增BackupTargetId/config、backup store port、separate mount、atomic publisher、target readiness、restore lookup及path/volume/DR tests。 |
| Formal owner | Repository backup/restore storage contract；deployment security/runbook。 |
| Reopen condition | Accepted RPO/RTO或deployment要求remote object storage，并完成provider-specificsecurity与durability contract。 |

### P2-R8-D09 — Stable non-reusable caller and credential identities

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D09` |
| Topic | Principal identity lifetime across credential rotation and service replacement |
| Status | `ACCEPTED` |
| Decision | CallerIdentity是deployment-assigned opaque UUIDv7 principal-instance ID，在同一trust domain永久不可分配给另一主体；human/service display name和credential key-id均不是identity。Credential轮换保持CallerIdentity，因此ACL、idempotency和audit continuity不变。新service actor即使沿用同一显示名称也必须使用新CallerIdentity；retired identity不得复用。CredentialId同样不可复用，retired ID只保留非secret审计/tombstone。Deployment identity config拥有principal assignment/non-reuse责任；Repository Service验证格式、同一配置内重复映射和credential-to-principal一致性，但不升级为身份签发/目录服务。 |
| Rationale | 以credential或名称作为identity会在rotation/redeploy后错误继承ACL或丢失idempotency关联；独立principal instance ID把认证材料生命周期与effect identity分离。 |
| Rejected alternatives | 从当前token/key推导identity：轮换改变authority；使用显示名称：新旧actor混淆；Repository Service签发和管理principal：超出薄认证边界。 |
| Constraints | Credential ID/tombstone不含token digest之外的secret，普通日志最多记录sanitized credential ID。部署误把retired CallerIdentity赋给新actor属于invalid security configuration并必须fail readiness when detectable。 |
| Downstream impact | 约束secret/config schema、ACL/idempotency keys、audit records、rotation/redeployment runbook及principal-reuse negative tests。 |
| Formal owner | Repository Service caller identity contract；deployment identity policy。 |
| Reopen condition | Accepted platform identity提供等价、不可复用且跨credential rotation稳定的principal identifier。 |

### P2-R8-D10 — Honest logical quota without a false hard tenant-isolation claim

| 字段 | 值 |
| --- | --- |
| ID | `P2-R8-D10` |
| Topic | Per-repository quota strength and shared-volume exhaustion |
| Status | `ACCEPTED` |
| Decision | v1承诺per-repository logical accounting、admission、reservation和finite quota，但不宣称application accounting形成不可突破的physical filesystem sandbox。Durable root为registry/control/journal/recovery预留独立emergency reserve，普通data/artifact/staging不能消费该预算。High watermark拒绝新bulk mutation/upload，仍允许read/status/reconciliation/GC/delete；Critical watermark只允许维持authority和释放空间所需的status/reconciliation/GC/delete等动作，新effect在acceptance前拒绝。Accepted但尚未EFFECT_STARTED的operation可因critical safety以NOT_APPLIED终止；EFFECT_STARTED后按evidence-first规则收口。Dolt/storage amplification超过reservation时记录actual usage并停止新的admission，但不得伪造rollback。Filesystem project/subvolume quota可作为deployment hardening，不是v1 portability/compatibility requirement。需要抵御恶意tenant或严格物理容量隔离时使用独立trust-domain service/root。 |
| Rationale | 单共享root和provider amplification无法仅靠应用计数证明硬隔离；明确logical guarantee、control reserve和watermark behavior既保护recovery authority，又不绑定特定filesystem。 |
| Rejected alternatives | 强制XFS project quota/subvolume provider：降低部署可移植性；把logical counter称为hard quota：保证不真实；无reserve只看全盘水位：数据增长可使journal/recovery无法写入。 |
| Constraints | Reserve/watermark/capacity数值由Round 9 measurement profile固定且必须finite。Backup通常在high/critical watermark拒绝，除非target-local staging和source read不消耗active-root reserve并由runbook显式允许。Quota failure必须按acceptance/effect阶段返回typed evidence。 |
| Downstream impact | 约束disk layout/accounting、admission state、readiness、operation failure、GC/delete priority、capacity metrics、volume tests及trust-domain deployment guidance。 |
| Formal owner | Repository Service resource governance/storage contract；Round 9 capacity/readiness runbook。 |
| Reopen condition | Production threat model要求同一root内对恶意tenant提供hard storage isolation，并选定可验证filesystem/backend quota authority。 |

## Round 9 — Observability, measurement and operations

### P2-R9-D01 — Standard telemetry surfaces with deployment-owned audit retention

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D01` |
| Topic | Logs, traces, metrics, correlation and external security audit |
| Status | `ACCEPTED` |
| Decision | Repository Service向stdout输出结构化JSON application log和独立typed `security_audit` event stream；传播W3C `traceparent`/`tracestate`并生成或接纳`request_id`，在acceptance后关联`repository_operation_id`、`repository_id`、`store_kind`、`action`、provider/version及必要commit/artifact digest。Typed spans采用OpenTelemetry语义和可配置OTLP exporter；未配置或暂时不可用的exporter不改变请求结果。`/metrics`使用Prometheus/OpenMetrics，只暴露低基数label；RepositoryId、CallerIdentity、operation/ref/commit/artifact/table、request ID不得成为metric label。Idempotency key、token、SQL、raw row、filter literal和内部path禁止记录，idempotency只记录versioned digest。Mutation、operator action、安全拒绝和关键lifecycle transition必须产生不可采样掉的structured event；普通成功read trace可配置采样。v1不建设Repository Service持久audit outbox，也不把effect journal冒充完整security audit；journal/control DB继续持久保存恢复所需的mutation/operator事实，deployment日志采集器拥有完整audit流的持久化、rotation和明确retention。Exporter/collector异常产生drop/backlog/health告警，但不阻塞普通请求。 |
| Rationale | 标准wire和低基数metrics可直接接入常见平台，同时避免自建telemetry协议和高基数成本。把external audit retention放在deployment collector保持Repository Service边界简洁；恢复事实仍由durable journal保护。 |
| Rejected alternatives | 仅自由文本日志：无法稳定关联和测量；自定义trace/metric协议：增加collector与SDK维护；把每次read审计同步写入Repository control DB：放大热路径并把audit变成第二业务authority；collector故障时全服务fail closed：外部可观测依赖会阻断repository effect。 |
| Constraints | Telemetry绝不作为effect、authorization、idempotency或recovery authority。Public error、probe、metric和普通日志必须统一redact；security audit schema与event version必须版本化。Production deployment必须配置collector、外部retention和collector/drop告警，Repository Service不承诺collector已接收。OTLP/metrics scrape endpoint必须受deployment network policy保护。 |
| Downstream impact | 新增telemetry envelope、correlation middleware、typed span/counter registry、redaction tests、OpenMetrics endpoint、optional OTLP adapter、security audit schema及collector runbook。 |
| Formal owner | Repository Service observability and security-audit contract；deployment logging/retention runbook。 |
| Reopen condition | 法规要求Repository Service自身提供transactional immutable audit delivery，或accepted平台audit API提供可证明ack/retention并成为新的sink authority。 |

### P2-R9-D02 — Layered liveness, admission readiness and repository-scoped degradation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D02` |
| Topic | Liveness, readiness, detailed health and failure-domain isolation |
| Status | `ACCEPTED` |
| Decision | `/livez`只证明process/event loop能够及时响应，不探测Dolt、全部repository、backup target或普通dependency；`/readyz`表示服务可安全接纳至少一部分public workload。Global registry不可读、production required identity缺失/不匹配、unknown storage major、control emergency reserve不可用或production auth配置无效时整体not-ready。单repository、单StoreKind、单个Dolt runtime、GC/backup target或per-repository recovery故障只标记对应repository/capability degraded/unavailable，不使全服务not-ready。Startup验证global authority并启动recovery scheduler后即可ready，不等待遍历上万个repository；首次访问尚未检查的repository时，mutation admission前必须完成该repository按需reconciliation。Unauthenticated probes只返回sanitized状态；authenticated operator health返回component、水位、reconciliation backlog、runtime pool、audit collector和capability degradation详情。Legacy `/healthz`如保留，只作为`/readyz`兼容alias，不定义第四套health语义。 |
| Rationale | Liveness与依赖解耦避免restart storm，global readiness与repository degradation分离保持故障域可控；按需检查允许大规模repository集合快速安全启动。 |
| Rejected alternatives | Liveness探测Dolt/磁盘：依赖故障触发无效重启；ready前扫描全部repository：启动时间随项目数无界；任意单库故障全局not-ready：降低隔离和资源利用；始终ready：无法阻止authority损坏后的新请求。 |
| Constraints | Ready不表示每个repository健康，也不表示benchmark环境quiescent。尚未reconcile的repository不能因service-wide ready而直接接受mutation。Probe不得泄漏repository存在性、path、identity或安全配置；详细health使用独立operator action。 |
| Downstream impact | 新增live/readiness state machine、component health model、operator health API、per-repository availability、orchestrator probes、startup/on-demand reconciliation和degradation tests。 |
| Formal owner | Repository Service deployment/readiness contract；repository lifecycle/recovery contract。 |
| Reopen condition | 部署平台要求实例只能以all-or-nothing shard提供服务，或future shared control plane在流量进入前提供完整repository placement/health authority。 |

### P2-R9-D03 — Evidence-aware bounded shutdown and incremental reconciliation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D03` |
| Topic | Graceful/non-graceful restart, startup scan and recovery retry |
| Status | `ACCEPTED` |
| Decision | 收到SIGTERM后service立即not-ready并拒绝新mutation、upload、long stream和maintenance；已开始的请求及status/recovery在有限grace period内收口。默认grace period为60秒，production必须显式配置，允许范围10–300秒。Accepted但未开始effect的operation可停在durable checkpoint；`EFFECT_STARTED`后不得伪装为cancelled，deadline到期强制退出后由新process按journal/store evidence reconcile。SQLite WAL checkpoint、Dolt runtime drain和非结果性cleanup均为best effort，不允许形成无限shutdown。Startup先验证global authority、runtime/storage compatibility及durable root，再启动incremental recovery scheduler。Registry枚举page size初始为100、最多并发打开4个per-repository control DB；普通扫描不启动Dolt runtime，只有发现需要store evidence的nonterminal/UNKNOWN operation才acquire。优先级固定为当前API触达repository、已知nonterminal index、全量后台扫描。单operation自动retry backoff为`1s/5s/30s/2m/5m`，之后保持5分钟上限；连续10次失败或持续30分钟没有取得可推进的新evidence时进入`ATTENTION_REQUIRED`。Operator recheck复用同一reconciler、operation identity、lease和fencing，不创建新的effect attempt。 |
| Rationale | Durable checkpoint和有界drain允许rolling restart，evidence-first恢复避免把process lifetime误当effect边界；incremental control scan不会为上万个repository常驻Dolt process。 |
| Rejected alternatives | shutdown无限等待所有operation：阻塞部署；立即kill且不drain：增加可避免的UNKNOWN；ready前加载/扫描全部Dolt：资源无界；失败后blind replay或建立新operation：可能重复effect。 |
| Constraints | 这些值是安全和调度初始预算，不是throughput或RTO声明，可在versioned deployment profile中基于capacity evidence调整。扫描index/cache可从global registry和control DB重建且不是第二authority。Grace deadline届满不能抹除accepted/effect evidence；non-graceful crash遵循相同startup reconciler。Periodic scan cadence与cross-repository fairness由`P2-R9-D08`收口。 |
| Downstream impact | 新增drain state、signal handling、runtime termination、startup scheduler、priority queue、retry/attention policy、recovery metrics及graceful/kill/restart tests。 |
| Formal owner | Repository Service runtime/recovery contract；deployment restart runbook。 |
| Reopen condition | Capacity evidence证明固定page/concurrency无法满足恢复目标，或orchestrator提供新的durable work queue/placement authority接管repository discovery。 |

### P2-R9-D04 — Separate immutable build identity from comparable environment fingerprint

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D04` |
| Topic | Runtime identity, storage compatibility and measurement series identity |
| Status | `ACCEPTED` |
| Decision | Phase 2定义独立`RuntimeBuildIdentity`，固定Repository Service source revision、service image/base-image digest、Python、uv、dependency lock digest、Dolt version与binary digest，以及wire/contract/schema version；production缺失required identity、binary与声明不匹配、storage layout/control schema为未知major或Dolt compatibility不满足时fail readiness。另定义`EnvironmentFingerprint`记录CPU/memory quota、cgroup、kernel/container runtime、volume/filesystem、host CPU/disk class、ResourcePolicy digest、auth provider configuration digest及measurement-required provider identity。Environment变化通常不阻止service启动，但会创建新的measurement series或使正在执行的benchmark invalid。Durable root保存versioned storage compatibility identity而非永久绑定某个source revision；合法升级必须经过显式compatibility、backup、migration/rollback gate。Phase 2 identity不修改、复用或冒充frozen Phase 1 source/runtime/image identity。 |
| Rationale | Build真实性、持久格式兼容性和性能可比环境是不同问题；拆分后既能阻止错误binary/format启动，又允许经过控制的正常部署升级和不同机器运行。 |
| Rejected alternatives | 一个全量exact hash控制所有readiness：host/quota变化也会无意义停服；只写启动日志不校验：无法证明container与Dolt身份；把Phase 1 closure identity沿用为Phase 2：污染已冻结证据。 |
| Constraints | OCI/deployment必须提供可核对的expected image/build identity；仅靠可伪造的普通runtime env字符串不足以声明accepted production identity。Secret值不得进入fingerprint，只记录provider/config schema及安全digest。EnvironmentFingerprint不是repository public identity，也不进入业务/content digest。 |
| Downstream impact | 新增build manifest、OCI labels/attestation evidence、startup verifier、storage compatibility manifest、operator version capability、benchmark preflight和identity drift tests。 |
| Formal owner | Repository Service build/deployment identity contract；Performance Measurement environment profile；storage upgrade runbook。 |
| Reopen condition | 平台提供accepted signed workload identity/SBOM attestation并成为build authority，或Dolt/storage compatibility contract允许安全的版本范围而非exact binary pin。 |

### P2-R9-D05 — Explicit production capacity profiles and verification-separated measurement

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D05` |
| Topic | Capacity defaults, performance measurement eligibility and minimum operations runbook |
| Status | `ACCEPTED` |
| Decision | Design authority不臆造跨环境通用production容量数值。`development`与`conformance`可提供有限的小型profile；`production`不提供隐式node-capacity default，deployment必须提交启动校验、全部finite的ResourcePolicy。Dolt runtime slots、queue depth、per-repository quota、control reserve、disk high/critical watermark及verification/readback budget等具体值由目标container/volume环境的capacity characterization生成、版本化并纳入EnvironmentFingerprint；Round 8固定parser hard limits保持不变。Authoritative benchmark只通过Remote production client/wire，显式记录`NONE/STRUCTURAL/FULL`verification level、provider、resource policy、concurrency和environment fingerprint；任何一项不同均为独立series，不得混合aggregate。每个caller请求的verification level按其自身contract正常得到PASSED/ASSERTION_FAILED/HARNESS_ERROR，不把非FULL自动分类为降级或例外。Runner只观察production typed spans/counters，不得使用private step、benchmark-only fast path或绕过journal/effect evidence。Gate前不得声明numeric baseline、性能收益或legacy speedup。最小runbook覆盖identity/readiness、graceful/crash recovery、UNKNOWN/ATTENTION、disk watermark/GC、backup/restore、credential rotation、audit collector故障及Dolt upgrade/rollback；告警至少覆盖prolonged reconciliation backlog、ATTENTION_REQUIRED、writer lease异常、runtime crash loop、verification failure、audit drop和high/critical watermark。 |
| Rationale | 容量与硬件、filesystem、dataset和verification policy强相关；强制显式production profile比虚构安全默认值更诚实。按verification分series保持caller choice与measurement可比性。 |
| Rejected alternatives | 设计阶段发布统一production数值：缺少container evidence；production使用无限或隐式default：无法审计capacity边界；所有measurement强制FULL：重新收紧caller-selected verification；混合verification/concurrency series：数字不可解释。 |
| Constraints | 本decision显式替代`P2-R8-D04`与`P2-R8-D10`中“Round 9直接固定通用production capacity数值”的局部条款；其finite policy、reserve、水位和admission语义保持ACCEPTED。现有formal performance contract仍把full readback作为唯一aggregate资格，必须等整体formalization授权后与`P2-R6-D09`一并显式supersede，当前实现不得同时宣称两套authority。Capacity characterization产生profile值但不自动授予production acceptance；Round 10定义evidence gate。 |
| Downstream impact | 新增profile schema/capability、capacity characterization、verification-keyed baseline series、benchmark preflight、runbook/alert inventory，并修改formal measurement eligibility。 |
| Formal owner | Performance Measurement and Baseline contract；Repository Service resource policy/deployment runbook。 |
| Reopen condition | Accepted平台提供统一且经过目标volume/dataset验证的capacity class，或法规/业务contract规定不可由caller选择的最低verification level。 |

### P2-R9-D06 — Durable-root exclusive ownership with a process epoch

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D06` |
| Topic | Single-active process ownership, persistent-volume semantics and restart fencing |
| Status | `ACCEPTED` |
| Decision | v1以deployment和service两层共同强制single-active durable-root ownership。Deployment必须使用single-writer volume及`Recreate`或等价无重叠策略；Repository Service在打开global registry、control DB或任意Dolt repository前，必须取得durable root内固定lock identity的OS exclusive lock。未获锁实例保持not-ready且不得执行recovery。获锁后在global authority中递增持久`ServiceEpoch`，worker claim、runtime owner和writer lease/effect executor evidence绑定该epoch；意外失锁时实例立即not-ready并终止，不继续使用旧epoch写入。支持的filesystem/volume profile必须证明同filesystem atomic rename、file和directory fsync、stable ownership及exclusive lock语义；未经验证的NFS/object-filesystem、多写volume和active-active不属于v1支持范围。Process crash释放OS lock，新实例取得lock并生成新epoch后仍须按journal/store evidence reconciliation，不能仅因epoch变化认定旧effect未发生。 |
| Rationale | Orchestrator策略降低重叠概率，service lock和epoch使错误overlap可检测并把runtime evidence绑定具体process generation；这实现既有single-active约束而不引入distributed coordinator。 |
| Rejected alternatives | 只信任deployment无service lock：误配置时可能并发打开root；只使用持久owner marker：crash后无法安全判断stale；共享可写volume上active-active：缺少distributed lock和provider fencing；把新epoch当作NOT_APPLIED proof：可能重放旧process已产生的effect。 |
| Constraints | OS lock只是process/root排他，不替代per-store writer lease、Dolt executor isolation、CAS或effect reconciliation。`ServiceEpoch`是内部fencing identity，不是RepositoryIncarnationId或public resource identity。Lock文件/path不得对caller暴露或进入backup semantic content。 |
| Downstream impact | 新增root capability preflight、exclusive lock holder、ServiceEpoch schema/evidence、orchestrator deployment rule、lock-loss fatal path及overlap/crash/takeover tests。 |
| Formal owner | Repository Service deployment/runtime ownership contract；persistent-volume compatibility profile。 |
| Reopen condition | Future shared multi-node coordinator提供accepted distributed ownership/fencing，或deployment改为每shard独立durable root并完成routing authority设计。 |

### P2-R9-D07 — Epoch-aware leases and profile-bounded Dolt runtime eviction

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D07` |
| Topic | Lease timing, clock semantics, runtime acquisition and idle eviction |
| Status | `ACCEPTED` |
| Decision | Async store writer lease初始TTL为30秒并每10秒renew；同process内deadline/renew调度使用monotonic clock，持久wall timestamps只用于诊断和跨restart evidence排序，不能单独授权takeover。Restart后旧lease因旧`ServiceEpoch`成为suspect owner evidence，新process仍须隔离旧executor并检查journal/store；TTL到期或epoch变化均不自动释放UNKNOWN occupancy。Production ResourcePolicy必须显式给出finite `max_dolt_runtimes`、每runtime connection/process limits、idle TTL和runtime acquire timeout，不提供跨环境通用production值。RuntimeCoordinator使用idle LRU作为容量回收策略，但存在active reader、writer、maintenance、recovery或pinned runtime handle时不得驱逐；process cache丢失不影响durable state。Runtime capacity在acceptance前不足时返回typed capacity failure；已经accepted的operation只能按其reservation、deadline和effect evidence等待或收口，不能被重建为新operation。 |
| Rationale | 明确renew比例和clock边界便于检测stalled worker，但真正安全来自epoch、executor isolation和store evidence。Profile-owned runtime数值适配不同container容量，pin-aware eviction避免回收仍被读写使用的Dolt owner。 |
| Rejected alternatives | TTL到期立即接管：可能形成双writer；持久化monotonic timestamp跨restart比较：时钟域无意义；固定全局runtime count/idle TTL：缺少环境证据；强制驱逐最旧runtime：可能中断active pinned read或effect。 |
| Constraints | Lease时间是failure detection hint，不是provider-native fencing。30/10秒可由versioned capacity evidence调整，但renew必须显著短于TTL且配置校验fail closed。Admission必须区分queue/capacity failure与accepted operation recovery；runtime queue不得形成绕过per-store serialization的第二writer队列。 |
| Downstream impact | 约束lease schema/heartbeat、monotonic scheduler、runtime pool/pins、ResourcePolicy、capacity metrics、stall/expiry/eviction/restart tests。 |
| Formal owner | Repository writer-lease/runtime coordination contract；deployment capacity profile。 |
| Reopen condition | Dolt/provider提供native fencing lease，或measurement证明不同renew模型对目标平台更安全且保持相同takeover evidence contract。 |

### P2-R9-D08 — Fair incremental reconciliation with bounded clean-scan cadence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D08` |
| Topic | Periodic scan cadence, scheduling classes and starvation prevention |
| Status | `ACCEPTED` |
| Decision | Reconciliation scheduler使用三类work：API触达但尚未检查的repository立即进入on-demand检查；nonterminal operation按`P2-R9-D03` backoff进入due queue；clean repository完成control scan后默认15分钟加`±20%` jitter再次eligible。Registry按持久稳定顺序分页并用可重建ephemeral cursor循环扫描；cursor/index/cache不是authority，丢失后从registry重建。初始4个control-scan permit中，只要background backlog存在，至少保留1个给oldest-last-scanned repository，其余优先服务API触达和到期nonterminal work；空闲保留permit可被其他队列借用，但任何priority stream都不得使background永久饥饿。服务不声明固定全量cycle completion time，而暴露oldest scan age、cycle duration、due/backlog数量、per-class wait和attention count。Production可依据capacity evidence调整cadence、jitter、permit和配额，但必须finite并保留oldest-first eventual-scan guarantee。 |
| Rationale | On-demand和nonterminal优先缩短直接恢复路径，保留background permit又确保冷repository最终被重新检查；可重建cursor避免引入第二durable scheduler authority。 |
| Rejected alternatives | 只在startup扫描：运行期stale/abandoned work可能长期不发现；每个repository固定timer：上万timer和burst；严格priority不保留background容量：热流量可永久饿死冷库；承诺固定full-cycle时间：没有目标volume/capacity evidence。 |
| Constraints | Background clean scan只打开必要control metadata，不默认启动Dolt runtime。15分钟是v1安全调度默认而非RTO/SLO；改变profile不得关闭periodic scan、on-demand pre-admission check或nonterminal retry。Attention operation只在operator recheck或明确配置的只读evidence refresh时重新进入，不自动创建新effect attempt。 |
| Downstream impact | 新增scheduler classes、last-scanned evidence/cache、fair semaphore、jitter、scan-lag metrics和large-registry starvation/restart tests。 |
| Formal owner | Repository reconciliation/runtime contract；operations capacity profile。 |
| Reopen condition | Accepted durable external work queue成为scheduler authority，或capacity/RTO evidence要求repository sharding和独立scan workers。 |

### P2-R9-D09 — Externally scheduled maintenance with deployment-owned service objectives

| 字段 | 值 |
| --- | --- |
| ID | `P2-R9-D09` |
| Topic | Backup/GC scheduling, maintenance wait policy, RPO/RTO and alert thresholds |
| Status | `ACCEPTED` |
| Decision | v1 Repository Service只提供journaled/idempotent Plan/Execute maintenance mechanisms，不内置cron、自动backup policy或自动GC scheduler；deployment/operator controller拥有调用计划。Quiescent backup必须由operator显式选择`REJECT_IF_BUSY`或finite `WAIT_UP_TO`，无implicit或unbounded wait；production ResourcePolicy限制最大maintenance wait，超限在无effect时返回typed busy/deadline结果。Phase 2在没有accepted measurement和业务目标前不声明availability SLO、RPO或RTO；service暴露last successful backup age、restore drill result/time、GC eligible/estimated bytes、maintenance backlog及recovery duration，由deployment配置versioned目标、schedule和告警阈值。`ATTENTION_REQUIRED`、critical watermark、runtime/build identity mismatch及audit drop等离散安全/完整性状态立即告警；backlog age、backup age、latency和capacity headroom等数值阈值来自production profile，不硬编码为通用产品保证。 |
| Rationale | Backup频率、恢复目标和数值告警依赖业务与部署环境。把调度和SLO交给deployment controller保持Repository Service通用，同时通过typed mechanism/metrics/runbook保留可操作性。 |
| Rejected alternatives | Service内置通用cron：形成第二调度/HA状态机；无需求即承诺RPO/RTO：无法验收；backup无限等待quiescence：阻塞maintenance lane；所有告警使用固定阈值：对不同容量环境失真。 |
| Constraints | 外部调度不允许绕过Plan/Execute、authorization、reason、idempotency、maintenance barrier或audit。未声明RPO/RTO不降低backup/restore correctness gate；production仍必须配置backup/restore-drill policy或显式声明不启用并接受风险。Automatic emergency admission/watermark行为仍由Round 8拥有，不属于cron maintenance。 |
| Downstream impact | 新增maintenance wait enum/deadline、operator-controller integration seam、backup/restore/GC freshness metrics、deployment objective schema、runbook和busy/schedule/alert tests。 |
| Formal owner | Repository Service maintenance contract；deployment operations/SLO/DR runbook。 |
| Reopen condition | 产品获得明确RPO/RTO/availability requirement，或accepted platform scheduler/backup controller要求更强的service-side scheduling handshake。 |

## Round 10 — Test, gate and exit matrix

### P2-R10-D01 — Phase-specific gates with fail-closed affected-scope routing

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D01` |
| Topic | Phase 2 gate taxonomy, PR cadence and Phase 1 regression cost |
| Status | `ACCEPTED` |
| Decision | Phase 2新增四个唯一gate class：`P2-PR-STATIC`拥有offline schema/wire、architecture、unit/property、Fake及不启动外部process的Local checks；`P2-PR-CONTRACT`拥有固定Dolt identity下的真实Local/Remote public contract、stream、auth和provider integration；`P2-PR-RECOVERY`拥有journal crash matrix、UNKNOWN、lease/takeover、service/Dolt restart、persistent-root、GC及backup/restore fault scenarios；`P2-PHASE-EXIT-CONTAINER`只在clean exact commit拥有production image、多container Remote client、persistent/backup volume、identity和完整exit aggregation。每项assertion只有一个primary gate owner，exit引用已有result/evidence而不另造第二结论。PR使用versioned、tested、fail-closed affected-scope router：Repository普通实现运行相关Phase 2 static/contract，journal/runtime/recovery变更追加recovery；shared kernel、fixture schema、conformance core/vector触发受影响Phase 1 correctness；Rust/native/backend及其lock/build触发对应Phase 1 correctness/native；未知路径或跨边界变化默认扩大到全部相关gate。Phase 2 exit candidate无条件运行全部Phase 2 gates及完整Phase 1 correctness/native regression，但不重跑、不重签也不生成新的Phase 1 `PHASE-EXIT-CONTAINER` identity。 |
| Rationale | Phase 1回归必须在最终exit证明，但每个Repository-only PR全量构建Rust/backend会显著增加反馈时间。显式path ownership在保持fail-closed的同时只为受影响边界付费。 |
| Rejected alternatives | 每个Phase 2 PR无条件运行全部Phase 1 gates：成本过高；Phase 2完全不跑Phase 1 regression：最终可能破坏shared authority；复跑Phase 1 container exit：冒充已冻结identity；人工选择跳过lane：不可审计且易漏。 |
| Constraints | Required gate内不得skip、xfail、`UNSUPPORTED`、advisory-only或automatic retry掩盖。Docs-only变化可只运行文档/ledger validation，但router无法确定时必须升级范围。定期全量诊断可提供早期信号但不能替代exact-commit exit evidence。Gate名称、owner、routing rules和toolchain/lock input均须版本化。 |
| Downstream impact | 新增Phase 2 gate entrypoints、change classifier、routing unit tests、gate evidence schema、Phase 1 regression adapter及CI/exit aggregation。 |
| Formal owner | Phase 2 verification and delivery plan；cross-stage regression policy。 |
| Reopen condition | CI平台提供accepted dependency graph/content-addressed test selection并能证明等价fail-closed coverage，或Phase 1组件从monorepo/compatibility boundary移除。 |

### P2-R10-D02 — Layered Fake, Local and Remote conformance without cross-run opaque-ID equality

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D02` |
| Topic | Required client/provider matrix and Local/Remote equivalence |
| Status | `ACCEPTED` |
| Decision | Conformance matrix分三层：semantic-core suite在Fake、Local、Remote全部required；real storage/provider suite在Local、Remote required；HTTP/auth/stream/process/container suite只在Remote required。Phase 2全部public v1行为至少由Local与Remote共同验证，不能只由Fake证明。Fake只服务domain/application tests，不冒充Dolt、wire、restart或filesystem保证；其声明的required semantic cell不得返回`UNSUPPORTED`。不适用组合由versioned matrix在执行前显式声明，不使用runtime skip表达。Local/Remote独立run之间比较owner-defined canonical observation及identity关系，不要求server-generated RepositoryId、OperationId、ArtifactId或CommitId字节相同；opaque identity必须在各自run内稳定、可查询、可pin、可关联journal/result并满足相同contract，catalog/rows/diff/error/state transition/evidence等semantic payload按owner contract精确比较。 |
| Rationale | 分层matrix让Fake保持轻量且不伪造provider保证，同时确保每个公开语义有真实storage和wire证明。跨run比较关系而非随机/时间相关opaque ID避免把实现生成值错误提升为oracle。 |
| Rejected alternatives | 所有cell强制Fake模拟Dolt/process：维护第二实现；只测Remote不测Local等价：失去adapter contract；比较独立run生成ID字节：非semantic且不稳定；用skip表达N/A：required coverage不可审计。 |
| Constraints | Required cell missing、`UNSUPPORTED`或非PASSED使 owning gate失败。Provider-specific metadata/path/layout不得进入golden；需要稳定ID的单scenario使用logical clock/seed或在同run验证，不跨run假设相同随机结果。 |
| Downstream impact | 新增capability-layer matrix、Fake/Local/Remote adapters、canonical observation schemas、identity-relation assertions和required-cell aggregator。 |
| Formal owner | Repository client contract suite；Fixture Oracle required profile matrix。 |
| Reopen condition | Fake被移除，或Local不再作为公开可交付client；此时必须重新分配semantic-core和provider equivalence owner。 |

### P2-R10-D03 — Typed single-fault conformance with production-profile fault exclusion

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D03` |
| Topic | Fine-grained fault injection, crash boundaries and production-image validation |
| Status | `ACCEPTED` |
| Decision | Recovery scenario沿用formal single typed fault、armed/consumed exactly-once及after-failure/after-recovery checkpoints。Production request/wire永远不包含fault字段。细粒度fault通过test composition注入closed `FaultController` port，只能由conformance profile及隔离test-only side channel启用；production profile检测到fault-controller配置必须fail readiness。Fine-grained matrix至少覆盖acceptance durable boundary、`EFFECT_STARTED`前后、provider effect完成但journal未推进、target publication/CAS前后、APPLIED后、verification中、VERIFIED后响应前、Current SQLite commit前后，以及GC/backup/restore durable checkpoints。Production container exit使用同一发布image做外部SIGTERM/SIGKILL、Dolt process kill、persistent-volume restart和duplicate-root-owner竞争，不依赖直接修改SQLite/Dolt ref/目录。恢复只调用生产restart/reconcile/takeover/operator入口；runner不得伪造journal/store evidence。 |
| Rationale | Test composition提供确定的内部边界，black-box container kill又证明发布artifact的真实restart行为；两者组合比在public API暴露故障开关或只做随机kill更安全可诊断。 |
| Rejected alternatives | Production wire携带fault字段：扩大攻击面；runner直接改DB/ref：绕过恢复contract；只做unit mock：不证明process/restart；只做随机kill：难以覆盖关键窗口；每scenario多个primary fault：outcome归因不清。 |
| Constraints | Fault target/boundary/action及parameters必须owner-versioned、schema-closed并在preflight验证；未arm、未消费、重复消费或checkpoint evidence缺失均为HARNESS_ERROR。Conformance profile/side-channel secret不得进入production config、repository backup或public diagnostics。 |
| Downstream impact | 新增FaultController port、fault legality registry、test composition、logical barriers、container kill harness、checkpoint observations和crash coverage inventory。 |
| Formal owner | Repository recovery conformance contract；Fixture Oracle fault/recovery protocol；production deployment safety gate。 |
| Reopen condition | 平台fault-injection infrastructure可在不修改production wire/store的情况下精确命中全部logical boundary并提供等价receipt。 |

### P2-R10-D04 — Caller-policy conformance and strict runner result authority

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D04` |
| Topic | Verification/concurrency matrix and expected failure classification |
| Status | `ACCEPTED` |
| Decision | Required matrix按caller-selected policy而非旧strict-only规则验收。Versioned与async Current均覆盖`NONE/STRUCTURAL/FULL`成功；STRUCTURAL/FULL分别覆盖其应检测的mismatch；NONE须证明不执行内容readback但仍保存journal/effect attribution/recovery evidence；独立`VerifyCommit`覆盖成功与普通失败且不得改写原operation。Mutable Current、SubmitImport target publication和mutable ref update/delete必须显式覆盖`CHECK_EXPECTED`成功/stale conflict及`LAST_WRITE_WINS`覆盖结果；缺失`concurrency_mode`是schema rejection。Versioned import在两种mode下仍须base CommitId；immutable/protected/internal/operation ref及name uniqueness拒绝LWW。两种mode均验证idempotency、journal、lease/fencing和crash recovery。Schema-valid typed rejection、verification failure、UNKNOWN/ATTENTION等若与golden匹配，scenario为PASSED；无法形成可信observation、fault/barrier失败或cleanup泄漏为HARNESS_ERROR。Runner禁止automatic retry；显式同key retry是scenario stimulus并保留首次evidence。 |
| Rationale | Gate应证明服务正确实现caller选择，而不是偷偷恢复FULL/CAS-only约束；business failure是可比较输出，harness基础设施失败才是运行错误。 |
| Rejected alternatives | 所有write gate强制FULL/CAS：违背已确认caller responsibility；非FULL标成降级/豁免：引入第二成功等级；期待失败即让pytest失败：无法作为正式golden；自动retry flaky/fault run：覆盖首次证据。 |
| Constraints | Caller choice不能关闭auth/input safety/idempotency/journal/fencing/attribution/reconciliation。现有formal FULL-only/CAS-only条款必须在整体formalization授权后显式supersede；在此之前不得实现同时接受两套VERIFIED/required-matrix authority的gate。 |
| Downstream impact | 新增verification×concurrency scenario matrix、readback observation、LWW lost-update fixtures、expected failure goldens、VerifyCommit suite及formal supersession dependency。 |
| Formal owner | Repository verification/concurrency contracts；Fixture Oracle result semantics；Phase 2 exit matrix。 |
| Reopen condition | 业务或监管正式规定不可选的最低verification/concurrency policy，并同步修改caller contract。 |

### P2-R10-D05 — Separate conformance-client container and exact-commit Phase 2 exit evidence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D05` |
| Topic | Phase 2 exit topology, immutable evidence and Phase 1 identity preservation |
| Status | `ACCEPTED` |
| Decision | Phase 2 exit topology为独立Repository conformance-client container通过production `RemoteRepositoryClient`/public wire调用Repository Service production image；只有service挂载active durable volume和独立backup volume，client不得挂载root、调用private endpoint或使用provider/path。Conformance client使用后续backend消费的同一Remote SDK，不要求修改或冒充Phase 1 backend image。Clean exact commit上必须完成四个Phase 2 gates、全部required cell、image/source/base/Python/uv/locks/Dolt identity、live/readiness/static bearer/ACL negatives、Versioned/Current及三档verification、pinned streams、graceful/kill/Dolt restart、root-lock conflict、idempotency/CAS/LWW/lease/UNKNOWN/mismatch、GC、backup、删除active test aggregate后的restore和restricted ACL activation，以及Phase 1 correctness/native regression。Phase 1既有sign-off和container identity保持不变。Exit生成content-addressed immutable evidence，至少绑定gate/schema version、exact commit、image/component/lock digests、environment fingerprint、required cell results、fault receipts、cleanup及external evidence refs。 |
| Rationale | 独立client容器证明真实wire和volume隔离，同时避免为Phase 2 repository capability篡改已冻结backend image。Exact identity/evidence使phase exit可重放、可审计。 |
| Rejected alternatives | Harness直接挂载root：绕过public contract；复用并改写Phase 1 image：污染identity；只用Local client做exit：不证明wire/container；允许partial evidence或不同commit拼接：无法确定发布候选。 |
| Constraints | Exit不设置numeric performance threshold，capacity/benchmark不能替代correctness。外部registry/network failure只能记录BLOCKED且不算pass；重新执行产生新run/evidence，不覆盖首次失败。Phase 2正式gate必须等冲突formal authority获准更新后才能宣称accepted exit。 |
| Downstream impact | 新增conformance client image、Phase 2 Compose、volume lifecycle harness、identity bundle、exit aggregator、cleanup proof及closure sign-off模板。 |
| Formal owner | Phase 2 container/deployment verification plan；Repository client packaging；immutable release evidence policy。 |
| Reopen condition | Phase 2正式范围加入真实backend业务integration，或平台提供等价remote conformance runner且仍使用同一production SDK/public wire。 |

### P2-R10-D06 — Real-version compatibility gates with explicit stale-state coverage

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D06` |
| Topic | Wire/storage compatibility, initial-version boundary and stale resources |
| Status | `ACCEPTED` |
| Decision | 初始`/v1`只将真实current schema设为required，不用legacy或虚构v0冒充previous vNext release。从首次发布后的下一版开始，server必须通过current/previous client schema一个发布窗口；server-first rollout不要求new client调用old server。Canonical OpenAPI/JSON Schema、problem/error registry、closed action/enum及stream envelope形成versioned contract snapshot，compatibility由schema diff和真实previous-client fixture共同证明，不能仅凭semver声明。初始storage gate只验证current layout/control schema、损坏identity和unknown future major；真实previous accepted storage version出现后，相应显式upgrade/rollback scenario才进入required。普通startup不自动migration；unknown major、不支持的control schema或Dolt runtime/storage identity不匹配必须fail readiness。Stale-state required inventory至少覆盖Current generation、CommitId/ref、cursor/query binding、GC/delete plan、ACL policy generation、RepositoryIncarnationId、artifact expiry及same-key/different-digest idempotency collision。 |
| Rationale | Compatibility必须基于真实已发布版本；伪造旧版本会增加无意义矩阵并误导迁移保证。Schema snapshot加真实client fixture同时覆盖结构与行为。 |
| Rejected alternatives | Legacy作为v1 previous：把旧系统提升为vNext wire authority；初版虚构storage v0 migration：测试无真实格式；只做OpenAPI diff：不证明SDK/wire行为；startup自动迁移：扩大restart风险。 |
| Constraints | N/A由versioned preflight matrix声明且只用于真实不存在的版本轴，不得用于已发布required版本。Breaking semantic change使用`/v2`；current/previous window仍服从既有server-first rollout。Stale rejection必须验证effect为NONE或既有operation不被改写。 |
| Downstream impact | 新增contract snapshots、compatibility diff policy、previous-client lane、storage compatibility fixtures、stale-resource scenarios和upgrade matrix activation规则。 |
| Formal owner | Repository wire/versioning contract；storage compatibility and upgrade contract；Phase 2 exit matrix。 |
| Reopen condition | 出现首个previous vNext wire/storage release，或部署改为client-first/bidirectional compatibility并接受更大矩阵。 |

### P2-R10-D07 — Deterministic pinned-stream and bounded-resource conformance

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D07` |
| Topic | Stream pinning, backpressure, cancellation, cursor and artifact publication |
| Status | `ACCEPTED` |
| Decision | `P2-PR-CONTRACT` required stream matrix同时覆盖`EXACT`与`LATEST_AT_START`，验证返回resolved binding且stream打开后保持pinned，随后并发write不得改变该结果。Harness使用logical barrier及controllable slow sink，直接证明bounded queue达到配置上限后暂停upstream read；不以固定sleep、RSS猜测或numeric throughput作为correctness oracle。Disconnect、consumer cancel、idle timeout和total deadline必须关闭Dolt reader/SQLite read transaction并产生cleanup evidence；Current long read还必须在既有duration/bytes/batch limit下不无限阻塞WAL/checkpoint。Partial frame、缺失`STREAM_END`、length/hash corruption和oversized frame不得成为成功。Cursor resume只在相同resolved snapshot/query/options及有效codec/TTL下成功；expired、generation变化或unsupported codec返回typed stale/expired failure。Async export在client断连后继续，只有Parquet完整close并通过hash/size/schema/manifest验证才发布ArtifactRef；unpublished staging在success、failure、cancel和restart路径均须证明cleanup或保留为合法recovery root。 |
| Rationale | 直接观察queue/read control比宽泛内存测试更稳定；logical barrier可重复覆盖pin、cancel和并发竞态。Artifact publication与direct stream的生命周期必须分开验证。 |
| Rejected alternatives | 仅测最终rows：不证明backpressure/resource释放；固定sleep模拟慢client：flaky；以进程RSS作为唯一bounded证据：噪声且无法定位；断连自动取消accepted export：违背operation语义；部分stream作为成功输入：完整性不明。 |
| Constraints | Buffer/frame/deadline值来自effective ResourcePolicy/已固定wire limits，scenario验证边界而不声明性能SLO。Unpublished但属于UNKNOWN/APPLIED recovery evidence的staging不能为满足cleanup断言而删除。Proxy-specific行为只有accepted deployment包含该proxy时才成为exit topology requirement。 |
| Downstream impact | 新增slow-sink harness、queue/read probes、pinned-read races、cursor corpus、frame corruption fixtures、export disconnect/restart和resource-release evidence。 |
| Formal owner | Repository streaming/read/export contract；Remote client conformance suite。 |
| Reopen condition | Transport不能提供可观察的backpressure/cancel，或产品选择只提供durable artifact而移除direct streaming。 |

### P2-R10-D08 — Layered security, resource and hardened-container negative gates

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D08` |
| Topic | Authorization, input safety, quota, redaction and container hardening tests |
| Status | `ACCEPTED` |
| Decision | Security negative matrix分层且全部required。Remote contract层覆盖401/403/404 existence hiding、每个closed action的ACL、credential current/next rotation、RESTORED_RESTRICTED、撤权后GetOperation/download、operator reason及execute时current-policy检查。Input层覆盖unknown field/enum、malformed JSON/Arrow/cursor、host path、URL/SSRF、canonical SQL grammar escape、archive traversal/duplicate/symlink/hardlink/device/bomb、digest/media mismatch；oversize/bomb使用小型生成器和declared-length/stream limit边界，不实际消耗巨量资源。Resource层覆盖parser hard limits、queue/quota、high/critical watermark、control emergency reserve及accepted-operation行为。Telemetry层扫描log/trace/metric/error/audit，确保token、raw row、filter literal、SQL、internal path和secret不泄漏。Container exit验证non-root、read-only rootfs、独立scratch/durable/backup mounts、drop capabilities、no-new-privileges、无Docker socket、default-deny egress及single-writer volume。每个public route/action必须出现在machine-readable authorization coverage inventory；缺项使gate失败。 |
| Rationale | 将语义授权、parser/resource和OS hardening分别放在能证明其边界的gate，既减少重复又避免只靠静态manifest声称安全。小型对抗材料可稳定验证限制而不制造CI DoS。 |
| Rejected alternatives | 只做unit auth test：不证明wire路由；真实超大bomb：测试本身耗尽资源；只检查Dockerfile文本：不证明运行配置；抽样route授权：新增route可能漏检；人工查日志泄漏：不可重复。 |
| Constraints | Security test credential/secret必须run-scoped且不进入evidence；sanitization failure不能用测试日志本身泄漏原值。Egress/container capability验证在目标container runtime执行；平台确实无法表达某hardening时为exit blocker，不降级为advisory。 |
| Downstream impact | 新增route/action inventory、auth matrix、malformed corpus、bounded adversarial generators、watermark harness、telemetry secret canary和runtime container inspection。 |
| Formal owner | Repository security/resource-governance conformance；Phase 2 container exit gate。 |
| Reopen condition | Trust model、auth provider、artifact ingress或container runtime发生正式变化并重新定义相应negative surface。 |

### P2-R10-D09 — Obligation-based coverage instead of a Cartesian scenario explosion

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D09` |
| Topic | Machine-readable coverage inventory and interaction selection |
| Status | `ACCEPTED` |
| Decision | Phase 2不要求`store × action × verification × concurrency × fault × client × auth`完整笛卡尔积，而维护machine-readable `RequirementCoverageInventory`：每项accepted decision、public action、stable failure code和durability primitive映射至少一个required scenario/cell及唯一primary gate owner；semantic core覆盖Fake/Local/Remote。每个durability family完整覆盖自己的logical crash boundaries，至少包括Versioned async effect、Current async bulk、Current sync SQLite transaction、ref publication、repository lifecycle及GC/backup/restore；相同primitive被多个action复用时不为每个action重复全套crash scenario。Verification、concurrency和read-binding各自覆盖完整enum；仅在interaction会改变结果或恢复时增加pairwise，例如concurrency×target publication、verification×verification crash、store kind×recovery、restore×ACL/incarnation、stream binding×concurrent write。Inventory缺项、重复primary owner、unknown decision/action/code或required cell未执行均使owning gate失败。 |
| Rationale | Obligation mapping证明每项contract和durability mechanism都有证据，同时避免大量只重复相同底层边界的低价值组合。Machine-readable inventory能在新增action/decision时fail closed。 |
| Rejected alternatives | 完整Cartesian matrix：运行时间和维护量无界；人工Markdown清单：容易漂移；仅按代码coverage百分比：不证明语义/failure义务；每action重复相同crash matrix：成本高且不增加primitive证据。 |
| Constraints | 省略组合必须能追溯到已覆盖的相同primitive且无额外交互；不能用pairwise原则省略已知高风险interaction。Coverage inventory不是test result authority，仍由runner/gate evidence给出PASSED/FAIL。Round 11只拆分实现，不得静默减少本inventory义务。 |
| Downstream impact | 新增decision/action/failure registries、coverage compiler/lint、scenario tags、gate owner map和matrix completeness report。 |
| Formal owner | Phase 2 verification plan；Fixture Oracle required matrix governance。 |
| Reopen condition | Test generation平台能经济地执行更完整组合，或生产事故/新provider证明当前interaction partition遗漏必要耦合。 |

### P2-R10-D10 — Immutable gate attempts with constrained, auditable reruns

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D10` |
| Topic | Gate outcome, blocking, retry, flake and evidence supersession |
| Status | `ACCEPTED` |
| Decision | Gate外层状态只有`PASS | FAIL | BLOCKED`。Required runner cell为ASSERTION_FAILED、HARNESS_ERROR、UNSUPPORTED、missing或cleanup非CLEAN时gate=FAIL；timeout、unexpected process exit和无法分类错误默认FAIL。BLOCKED只允许在semantic执行前证明的external registry/network/platform unavailable，不能包含已开始的business comparison。Required test不得quarantine、flaky allowlist、advisory-only或automatic retry。BLOCKED解除后可对同一commit新建attempt；ASSERTION_FAILED必须由新commit修复，不能同commit重跑变绿；HARNESS_ERROR只有harness/gate/environment identity发生明确、可审计修复后才能新建attempt。每次attempt immutable、content-addressed并保留首次结果；新attempt记录supersedes/reason及变化的gate/environment identity。Ordinary local diagnostic rerun不是formal evidence。Exit aggregator只接受明确提名、identity完整且同一candidate closure的PASS attempts，同时保留此前FAIL/BLOCKED history，不覆盖删除。 |
| Rationale | 区分外部阻塞、产品错误和harness错误，既允许真实基础设施恢复，又阻止随机重跑掩盖不稳定或语义失败。Immutable attempt history保持审计链。 |
| Rejected alternatives | 任何失败自动重跑：掩盖flaky/first evidence；一次失败永久毒化所有修复：不允许基础设施/harness纠正；只保留最后结果：丢失历史；把network failure算pass或runner第五态：破坏formal result contract。 |
| Constraints | HARNESS_ERROR重跑不能只写“flaky”；必须引用修复commit/config/environment evidence。Exit required attempts绑定exact source、toolchain、locks、image/component digests和gate schema；不同candidate closure的PASS不能拼接。BLOCKED不是phase完成或partial verification。 |
| Downstream impact | 新增gate-attempt schema、content-addressed store、supersession chain、candidate closure aggregator、blocked classifier及no-retry/no-quarantine checks。 |
| Formal owner | Phase 2 gate/evidence contract；release sign-off policy。 |
| Reopen condition | CI平台提供更强immutable retry provenance并能证明不覆盖首次结果，或组织正式改变release evidence retention policy。 |

### P2-R10-D11 — Linux/amd64 as the first verified deployment platform

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D11` |
| Topic | Initial production platform and multi-platform gate boundary |
| Status | `ACCEPTED` |
| Decision | Phase 2 v1唯一正式production/exit平台为`linux/amd64` OCI container，使用固定digest的glibc Debian-family base image、固定Python/uv及Dolt linux-amd64 binary/version/digest，并要求已确认的POSIX atomic rename、file/directory fsync、stable ownership及exclusive-lock volume profile。Public HTTP/SDK/schema保持平台中立，但arm64、musl、Windows、rootless-runtime差异和未经验证network filesystem不进入v1 required matrix。Deployment preflight在不支持的OS/architecture/runtime/filesystem capability上fail readiness，不能启动后把不兼容伪装为普通provider failure。未来增加平台时，每个platform identity拥有独立image build、container exit、filesystem crash/lock evidence和compatibility statement。 |
| Rationale | 当前Dockerfile与Dolt artifact实际只有linux-amd64证据；明确单一首发平台比声称未经验证的可移植性更诚实，同时不污染wire contract。 |
| Rejected alternatives | v1同时承诺多architecture：缺少image/provider/volume证据；只写“Docker compatible”：掩盖glibc和filesystem要求；在unsupported平台尝试启动：可能在effect中途失败。 |
| Constraints | Platform N/A是明确v1scope，不是required cell的UNSUPPORTED豁免。Base image tag不足以证明identity，必须记录resolved digest。Host kernel/runtime和volume/fs进入EnvironmentFingerprint；变化不一定拒绝服务，但必须满足最低capability preflight并创建独立measurement series。 |
| Downstream impact | 新增platform manifest、runtime/fs preflight、linux-amd64 image build、volume capability tests和future multi-platform activation checklist。 |
| Formal owner | Repository Service deployment/platform contract；Phase 2 container exit matrix。 |
| Reopen condition | Accepted consumer要求另一architecture/runtime，且相应Dolt artifact、image、filesystem semantics和exit evidence可用。 |

### P2-R10-D12 — Deployment-owned TLS ingress in the production exit topology

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D12` |
| Topic | TLS termination, plaintext isolation and production bearer validation |
| Status | `ACCEPTED` |
| Decision | `P2-PHASE-EXIT-CONTAINER`在conformance client与Repository Service之间加入pinned deployment-owned TLS ingress/sidecar。Client只通过HTTPS和production `RemoteRepositoryClient`发送static bearer；Repository Service明文listener只存在于隔离internal network，不发布host port且client container不可直接加入/访问该network。Service本身不拥有certificate issuance/rotation或private key lifecycle。Exit使用run-scoped test CA/certificate，验证trusted CA成功、unknown CA、hostname mismatch、expired/not-yet-valid certificate失败及plaintext不可达；Authorization header、bearer和TLS private key不得出现在proxy/service log、trace、error或evidence。Readiness/liveness可由编排器在受限internal/loopback路径探测，但普通API必须经过TLS入口。TLS proxy配置/identity进入deployment evidence而不进入repository aggregate/backup。Audit collector不新增为exit runtime dependency；harness捕获typed stdout audit stream并模拟collector异常告警。 |
| Rationale | Round 8 production bearer依赖TLS。由deployment sidecar终止TLS保持Repository Service薄认证边界，同时在真实exit topology证明证书验证和明文隔离。 |
| Rejected alternatives | Exit使用纯HTTP：没有验证production trust boundary；Repository Service直接管理TLS：增加证书生命周期和reload责任；client可绕过proxy访问service：TLS只成表面配置；把private key写evidence：泄漏secret。 |
| Constraints | Proxy image/config/cipher baseline和CA trust identity必须固定、可审计；test certificate不复用于production。Forwarded header不得成为CallerIdentity authority。TLS失败发生在Repository request acceptance前，不创建operation。Deployment若使用service mesh可替代sidecar，但必须通过等价exit obligations。 |
| Downstream impact | Phase 2 Compose增加TLS ingress、双network隔离、certificate fixtures、TLS negative suite、proxy redaction和deployment identity evidence。 |
| Formal owner | Repository Service deployment security contract；Phase 2 container exit topology。 |
| Reopen condition | Accepted平台service mesh提供等价mTLS/TLS termination与identity evidence，或Repository Service正式接管server TLS lifecycle。 |

### P2-R10-D13 — Design and formal closure as a non-bypassable exit preflight

| 字段 | 值 |
| --- | --- |
| ID | `P2-R10-D13` |
| Topic | Governance entry conditions for the Phase 2 exit gate |
| Status | `ACCEPTED` |
| Decision | 不新增第五个runtime gate；`P2-PHASE-EXIT-CONTAINER`在任何build/test前必须验证machine-readable design/formal closure preflight。Entry要求Round 0–11全部明确确认、Consolidated Design Review通过、用户明确授权且formalization完成、FULL-only/CAS-only/exact-only等formal冲突已显式supersede、`requirement → decision → formal owner → WP → gate → evidence`追踪无缺项、Decision Ledger无blocking OPEN/DEFERRED、formal无UNRESOLVED、blocking register为空、implementation plan/runbook/contract/schema/gate version一致、Phase 1 frozen identity/locks/vectors/golden/scenario/sign-off未被修改或冒充，并且exit candidate是clean exact commit。任一entry缺失使preflight=FAIL；代码、unit test或container smoke通过不能绕过设计/formal closure宣布Phase 2完成。 |
| Rationale | Phase 2 ledger与现有formal之间存在已知待supersede冲突；若exit不验证设计closure，可能发布同时声称两套authority的实现。把治理条件放入现有exit preflight避免新增重复gate class。 |
| Rejected alternatives | 仅人工检查Markdown：容易漂移；代码通过即可exit：formal冲突未解决；另建独立第五gate：与exit entry重复；允许DEFERRED blocker：实现范围不确定。 |
| Constraints | Non-blocking future/non-goal可以保留，但必须有owner、reopen condition且不影响v1exit；是否blocking由formal blocking register而非名称猜测。Phase 1保护检查比较冻结identity/closure，不要求把当前Phase 2 commit伪装成Phase 1 exit source。Round 11负责生成WP/gate traceability，但不得削弱本preflight。 |
| Downstream impact | 新增closure manifest/schema、decision/formal/traceability lints、blocking-register check、Phase 1 protected-identity comparison及exit preflight evidence。 |
| Formal owner | Phase 2 implementation plan and release governance；Consolidated Design Review；container exit preflight。 |
| Reopen condition | 项目采用具备等价owner/traceability/blocking证明的外部release governance system。 |

## Round 11 — Implementation plan

### P2-R11-D01 — Formal-closure entry followed by vertical work-package delivery

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D01` |
| Topic | Phase 2 implementation work-package spine and entry boundary |
| Status | `ACCEPTED` |
| Decision | Phase 2 implementation使用一个非代码前置`F0 Formal closure`和十个纵向WP：`WP0 delivery skeleton and gates`；可有限并行的`WP1 public contracts/client/service shell`与`WP2 Dolt/SQLite/filesystem feasibility`；随后`WP3 repository durable foundation`、`WP4 operation/journal/recovery runtime`；可有限并行的`WP5 CurrentTableStore`与`WP6 versioned read/runtime`；再串行完成`WP7 versioned write/ref/verification`、`WP8 retention/GC/backup/restore/delete`及`WP9 production hardening/deployment/Phase exit`。F0要求整体设计确认、Consolidated Design Review、用户formalization授权、已知formal冲突显式supersede及blocking closure；F0通过前不得开始实现WP0。每个WP必须交付可执行的纵向能力或交付控制，不建设无consumer的通用framework。 |
| Rationale | 先固定authority和可执行交付控制，再沿durable foundation、effect runtime、两类store与运维闭环推进，可让每批具有明确消费者、rollback和证据；provider feasibility提前阻止在未经验证的Dolt/FS假设上堆叠实现。 |
| Rejected alternatives | 先实现后formalize：会同时面对冲突authority；按contracts/domain/storage等水平层一次性铺开：形成长期不可运行骨架；先完整实现Dolt再补operation/recovery：effect边界无法审核；把全部功能放入一个大WP：不可独立回滚。 |
| Constraints | WP编号描述依赖和审核边界，不授权改变accepted semantics。WP1/WP2及WP5/WP6的并行仍受`P2-R11-D05`限制；所有WP的详细R、entry/exit、gate和evidence必须在Round 11后续decision中固定。 |
| Downstream impact | 约束正式implementation plan目录、traceability map、依赖图、review sequence、gate activation和release roadmap。 |
| Formal owner | Phase 2 implementation design and delivery plan。 |
| Reopen condition | Feasibility证明关键provider假设不可行，或Consolidated Design Review发现必须改变纵向dependency spine的blocking缺口。 |

### P2-R11-D02 — Three-package client boundary and single-process service runtime

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D02` |
| Topic | Python distribution boundaries, dependency direction and initial runtime topology |
| Status | `ACCEPTED` |
| Decision | Phase 2建立三个单向依赖的Python distribution：`gateway-repository-contracts`只拥有公共DTO、closed enum、schema codec与versioned contract assets，不含HTTP、provider、storage或业务规则；`gateway-repository-client`依赖contracts并拥有Repository Port、Fake及Remote SDK；`gateway-repository-service`依赖contracts并拥有application/domain、Local adapter、HTTP transport、Dolt/SQLite/storage/runtime。Backend只依赖contracts/client，不依赖service。Conformance可显式依赖三者以运行Fake/Local/Remote matrix。Service v1使用单ASGI process、单durable-root owner和进程内有界scheduler/task group；不引入Celery、Redis、外部work queue、ORM或通用plugin/provider framework。SQLite由显式transaction adapter封装标准`sqlite3`；Dolt streaming driver在WP2后锁定。 |
| Rationale | 独立wire DTO避免service/client复制schema，又不共享业务源码；client与service分包保护backend不获得local path/provider依赖。单process与既有root lock/ServiceEpoch相符，避免在单writer设计上叠加第二调度authority。 |
| Rejected alternatives | Service依赖完整client包：反转server ownership；backend直接依赖service以取得Local实现：泄漏provider/runtime；把全部内容放一个package：无法证明部署边界；首版引入distributed queue/ORM：扩大recovery和transaction语义。 |
| Constraints | Contracts包不得成为Shared Kernel业务算法的新位置；Local adapter只用于同进程集成和conformance，不授权backend访问durable root。未来更换auth/provider只通过现有窄port，不提前建立动态plugin framework。 |
| Downstream impact | 新增两个distribution、dependency/architecture tests、SDK packaging、service module layout及container lock identities。 |
| Formal owner | Repository Service architecture/module boundaries；Repository client packaging plan。 |
| Reopen condition | OpenAPI code generation完全替代共享wire DTO且能证明Local/Remote无漂移，或accepted multi-process/multi-node runtime重新定义durable ownership。 |

### P2-R11-D03 — Provider and filesystem feasibility as an early stop/go gate

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D03` |
| Topic | Exact-provider feasibility, driver selection and implementation stop condition |
| Status | `ACCEPTED` |
| Decision | WP2必须在durable schema和正式public capability实现前，以固定Dolt `2.1.11`、目标`linux/amd64` image及受支持volume profile验证：`dolt sql -f` canonical replay；repository-scoped sql-server启动、停止与目录切换；offline CLI和active sql-server排他ownership；commit/ref/metadata marker、pinned read、stream/cancel；service/Dolt kill与restart；SQLite WAL/transaction/backup；POSIX exclusive lock、same-filesystem atomic rename、file和directory fsync。MySQL protocol driver不在设计阶段凭偏好锁定，由小型候选矩阵按streaming、cancel、type handling、connection lifecycle、packaging和固定Dolt兼容性选择并记录decision evidence。关键假设失败时停止依赖WP、报告并重开owning decision；不得静默改provider、退化为未声明语义或以mock通过。 |
| Rationale | 真实binary、driver和filesystem行为决定runtime ownership、streaming及crash recovery能否成立；在schema和业务路径之前验证可把高成本返工限制在早期。 |
| Rejected alternatives | 直接固定记忆中的driver：缺少当前Dolt证据；仅用mock/unit test：不能证明process/FS语义；失败后自动fallback到另一executor：改变effect/recovery contract；等WP7再测canonical replay：依赖链过深。 |
| Constraints | Feasibility result不是性能收益声明，也不替代后续contract/recovery/container gates。CANONICAL_SQL_REPLAY仍是默认优先候选；driver选择不得引入caller-visible SQL或provider/path contract。 |
| Downstream impact | 新增feasibility harness、exact identity manifest、driver decision evidence、filesystem capability probe及WP stop/go entry check。 |
| Formal owner | Phase 2 provider feasibility appendix；Dolt runtime/storage compatibility plan。 |
| Reopen condition | Dolt/binary、Python/base image、driver或supported filesystem profile升级，或生产平台增加新的architecture/runtime。 |

### P2-R11-D04 — Atomic capability activation with review-sized revisions and explicit storage rollback

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D04` |
| Topic | Revision slicing, public activation, intermediate gates and durable-format rollback |
| Status | `ACCEPTED` |
| Decision | 每个WP拆为2–4个single-semantic-axis、可独立revert的R，按能力需要覆盖contract/schema/fixture、core/local、remote/recovery/negative及evidence/activation，而非强制每个WP套同一模板。未端到端完成的endpoint不注册、capability不advertise、required matrix cell不activate；不能以runtime `UNSUPPORTED`冒充中间完成态。能力route、SDK surface、authorization inventory和required gate cell必须在最终activation R原子对齐；每个R保持当时已激活required gates全绿。首个v1发布前的开发/conformance durable volume可声明为run-scoped disposable，但首次持久化实现即写layout/control schema version。Storage format未变时允许image revert；format改变时只能按该R事先验证的backup/restore、forward fix或明确丢弃run-scoped data回滚，禁止silent downgrade和破坏性startup auto-migration。 |
| Rationale | 小R和原子激活让review/rollback可解释，同时避免半完成公开能力污染compatibility与required matrix。明确storage rollback可防止代码revert被误当作持久格式回退。 |
| Rejected alternatives | 先注册全部stub route：形成虚假capability；required test先skip/UNSUPPORTED：削弱fail-closed gate；每个WP单一巨型R：难审计难回滚；代码回退自动降级DB：可能破坏authority；v1前完全不写version：无法识别stale/future state。 |
| Constraints | Contract-first R只允许落地即将被同WP消费的closed contract和fixture，不得建设空framework。Format-changing R必须在entry中声明compatibility/rollback class；首次accepted v1 exit冻结第一个正式supported storage version。 |
| Downstream impact | 约束每个WP的R模板、route/capability registry、matrix activation、migration manifest、backup fixture和review checklist。 |
| Formal owner | Phase 2 implementation plan；wire/storage compatibility and rollback plan。 |
| Reopen condition | 项目采用具备等价feature activation与schema rollback证明的deployment platform，或正式支持online multi-version migration。 |

### P2-R11-D05 — Two-track maximum with serialized shared authorities and one exact-commit exit

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D05` |
| Topic | Limited parallelism, shared-owner serialization and exit evidence closure |
| Status | `ACCEPTED` |
| Decision | Phase 2最多同时存在两个feature implementation track：WP1与WP2可以并行；WP5与WP6可以在共同WP4 dependency commit后并行。Public contracts、registry/control schema、operation journal、gate/evidence schema及共享fixture的语义变更只有一个owner并串行合入；并行track只能消费固定版本，不得各自分叉authority。WP3、WP4及WP7–WP9按dependency serial closure推进。每个R基于其精确dependency commit并完成affected-scope gates；Phase exit只接受同一clean exact commit、同一candidate closure的完整PASS evidence，禁止拼接不同commit、image、lock或environment identity的通过结果。 |
| Rationale | 两条独立纵切可缩短等待，但共享durable/contract authority并发修改会制造merge后未验证组合。串行最终写入和运维闭环使critical path与recovery证据保持清晰。 |
| Rejected alternatives | 所有WP完全串行：不利用独立provider/contract及Current/Versioned read工作；多于两条长期feature branch：共享authority漂移；并行修改同一schema再merge：组合未被任一track验证；跨commit拼接exit：不能证明发布候选。 |
| Constraints | Tests/fixtures可以在owner contract固定后并行补充，但不得借此改变语义。Merge后的新exact commit必须按router重新运行受影响gate；通过结果不能从parent commit继承为formal evidence。 |
| Downstream impact | 约束依赖图、critical path、branch/review policy、ownership map、CI routing与exit aggregator。 |
| Formal owner | Phase 2 implementation/delivery plan；exact-commit evidence policy。 |
| Reopen condition | CI/build graph能为更多并行track证明content-addressed组合等价，或团队/仓库拓扑变化消除共享authority冲突。 |

### P2-R11-D06 — Thin repository resource snapshot without a monitoring subsystem

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D06` |
| Topic | Future repository-scoped performance monitoring support |
| Status | `ACCEPTED` |
| Decision | Phase 2只提供薄的authenticated `GetRepositoryResourceUsage`当前快照，复用ResourcePolicy、quota/admission、runtime coordinator和operation scheduler已经维护的数据；返回repository级逻辑storage usage、artifact/staging/control占用、reservation/quota、active/queued operation、stream/upload及Dolt runtime状态，并携带`observed_at`和数据freshness。接口使用独立closed `RESOURCE_USAGE_READ` action及既有404 existence hiding。Service不为该接口遍历全库、启动闲置Dolt runtime或执行昂贵即时采样；不能自然归因的共享Python CPU/memory不伪装为repository精确值。细粒度operation/runtime duration、I/O等仅沿用带`repository_id`的typed trace/event，由未来外部应用自行聚合。Prometheus/OpenMetrics继续禁止RepositoryId label。 |
| Rationale | 已有quota和scheduler数据足以提供低成本当前视图；历史趋势、精确共享进程归因和高基数metrics应由外部监控系统承担，避免Repository Service变成第二套performance platform。 |
| Rejected alternatives | Service内置per-repository时序库、采样器、profiler、趋势分析或告警：超出通用版本库责任；请求时递归扫描目录/启动runtime：成本和延迟不可控；RepositoryId作为metric label：高基数；把共享CPU/memory估算称为精确占用：误导caller。 |
| Constraints | Snapshot是observability projection，不是计费或OS级隔离证明；admission仍以内部measured accounting和ResourcePolicy为authority。字段只在现有组件自然拥有数据时加入，不为“完整监控面板”扩张durable schema。 |
| Downstream impact | 在WP1固定轻量response/action，在WP3/WP4接入已有accounting/scheduler projection，在WP9增加authorization、bounded-cost、freshness和redaction contract tests。 |
| Formal owner | Repository Service resource-governance/observability contract；Phase 2 implementation plan。 |
| Reopen condition | Accepted consumer提出计费级归因、强制repository CPU/memory隔离或service-owned历史查询要求，并提供相应measurement和retention authority。 |

### P2-R11-D07 — External repository audit query over a thin typed event boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D07` |
| Topic | Future repository-scoped audit query support |
| Status | `ACCEPTED` |
| Decision | Phase 2不新增Repository Service audit database、audit list/query endpoint、过滤语言或持久outbox。Service继续输出versioned typed `security_audit` event；request已经解析到repository时携带`repository_id`以及既有caller/action/operation/result/digest关联字段，由deployment collector/store负责持久化、索引、retention和未来repository级查询。Repository Service durable journal/control只保存effect recovery、idempotency和operator action本来需要的事实；caller对已知operation使用`GetOperation`取得权威operation/effect representation，不把journal扩成通用审计查询模型。Collector异常继续告警但不阻塞普通repository request。 |
| Rationale | 现有typed event边界已经让外部审计应用按repository索引；在Service内再建设审计存储与查询会复制collector责任、扩大热路径和retention/backup语义。 |
| Rejected alternatives | Repository Service内建完整审计查询：形成第二日志平台；通过扫描journal回答通用审计：恢复schema被查询需求绑架且不覆盖read/auth事件；同步等待collector确认后才处理普通请求：引入外部availability dependency。 |
| Constraints | Event schema/version、redaction和不采样关键事件规则保持Round 8/9 authority；auth failure等尚未可信解析RepositoryId的事件不得猜测归属。当前边界不宣称collector故障期间零丢失或合规级immutable delivery。 |
| Downstream impact | WP9只需固定event schema/collector fixture、repository correlation、redaction和drop alert evidence；不新增service-side audit storage/query WP。 |
| Formal owner | Repository Service security-audit event contract；deployment audit retention/query runbook；Phase 2 implementation plan。 |
| Reopen condition | 法规或accepted consumer要求Repository Service自身提供transactional、零丢失、immutable audit delivery/query，并明确ack、retention和failure semantics。 |

### P2-R11-D08 — Implement the Phase 2 consumer path before detailed Phase 3 design

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D08` |
| Topic | Phase 2 implementation and Phase 3 design sequencing |
| Status | `ACCEPTED` |
| Decision | Round 11与Consolidated Design Review完成后，先做一次bounded Phase 3 consumer-adequacy check，只验证已知storage projection、RepositoryImportArtifact、SubmitImport、readback及Repository Client需求是否被Phase 2 public contract覆盖，不展开完整Phase 3设计。随后完成Phase 2 formalization并优先实施Phase 2。WP5–WP7完成、真实Local/Remote contract通过并形成consumer-ready checkpoint后，可以开始Phase 3详细交互设计，同时Phase 2继续WP8–WP9 hardening/exit；Phase 3 production implementation必须等待Phase 2 clean exact-commit exit通过。 |
| Rationale | Phase 3明确消费Repository contract，完全先设计会建立在未验证provider/runtime之上；先完成核心consumer path可用真实反馈约束Phase 3，而允许晚期设计重叠又不必等待所有运维加固才开始思考消费者。 |
| Rejected alternatives | Phase 2设计后立即完整设计/实现Phase 3：可能在虚构服务行为上堆叠；Phase 2所有后期工作结束前禁止任何Phase 3设计：不必要延长串行时间；两阶段顺序任意：忽略RepositoryImportArtifact和client contract依赖。 |
| Constraints | Consumer-adequacy check只能发现Phase 2 contract缺口，不能把Phase 3业务/capability语义移入Repository Service。Phase 3设计重叠不得修改已冻结Phase 2 contract；需要semantic change时必须按authority流程显式reopen。 |
| Downstream impact | 在Phase 2 consolidated review加入bounded consumer checklist，在WP7定义consumer-ready checkpoint，并把Phase 3 implementation entry绑定Phase 2 exit evidence。 |
| Formal owner | Phase 2 implementation plan；cross-phase delivery sequence；Phase 3 entry criteria。 |
| Reopen condition | Phase 3 accepted consumer contract发生blocking变化，或组织交付约束要求阶段严格全串行且接受相应周期。 |

### P2-R11-D09 — Static-only gate bootstrap without empty passing gate classes

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D09` |
| Topic | WP0 revisions, initial gate activation and rollback |
| Status | `ACCEPTED` |
| Decision | WP0分三批：`WP0-R1`建立三个Python distribution的workspace、独立lockfile及architecture/import boundary；`WP0-R2`建立versioned affected-scope router、`P2-PR-STATIC`入口及fail-closed negative router tests；`WP0-R3`建立immutable gate-attempt schema、closure/traceability lint和Phase 1 protected-identity comparison。WP0只激活`P2-PR-STATIC`；`P2-PR-CONTRACT`、`P2-PR-RECOVERY`和`P2-PHASE-EXIT-CONTAINER`在尚无真实required cell时不执行、不产生空PASS或占位evidence。 |
| Rationale | 先建立真实可执行的静态交付控制，避免未实现gate以零required cell产生虚假成功；后续gate随首个真实owner capability激活。 |
| Rejected alternatives | WP0一次创建四个空runner：空PASS会冒充coverage；等全部功能后才建router/evidence：早期R没有fail-closed交付控制；引入通用task framework：当前无额外consumer。 |
| Constraints | 每个R入口要求F0通过及dependency exact commit已提名；出口要求离线可重复、gate前后tracked worktree不变、active static checks全PASS。WP0不改变durable format，rollback为逐R代码/lock revert并重新运行static gate。 |
| Downstream impact | 约束workspace topology、gate routing、evidence schema、Phase 1保护检查及WP1以后每个R的entry/exit模板。 |
| Formal owner | Phase 2 implementation plan；gate/evidence delivery contract。 |
| Reopen condition | Accepted CI平台提供等价fail-closed router、immutable attempt和protected identity authority且项目决定由其完全拥有这些能力。 |

### P2-R11-D10 — Incremental public contracts activated only with real service-level behavior

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D10` |
| Topic | WP1 contract breadth, revisions and first Remote contract activation |
| Status | `ACCEPTED` |
| Decision | WP1分三批：`WP1-R1`只交付公共ID、closed enum、problem schema、wire version、stream envelope等真实跨能力基础contract；`WP1-R2`交付Repository Port、Fake/Remote transport基础及service application/HTTP composition root；`WP1-R3`端到端交付auth、`livez/readyz`、service capability/resource-limit surface并激活相应Fake/Local/Remote observations。Repository、table、ref、operation等DTO和route由后续owning WP在首次真实消费时增量加入，WP1不得一次声明完整v1 surface或stub endpoint。 |
| Rationale | 基础wire/transport只有真实service-level consumer时落地，既建立SDK/Remote边界，又避免大批未验证DTO和route成为兼容性负担。 |
| Rejected alternatives | WP1冻结全部v1 OpenAPI：provider/storage尚未验证且容易漂移；先注册stub route：违反atomic capability activation；只建service不建Remote：无法证明transport/client边界。 |
| Constraints | WP1入口要求WP0 PASS；R3出口要求OpenAPI/schema snapshot、SDK round-trip、401/403、redaction及Local/Remote canonical observation通过。只激活service-level `P2-PR-CONTRACT` cells；无Dolt/Repository required cell。WP1不写durable state，各R可直接revert并重新生成/验证contract snapshot。 |
| Downstream impact | 约束contracts/client/service package首批内容、contract snapshot、service-level conformance matrix及后续endpoint owner规则。 |
| Formal owner | Phase 2 implementation plan；Repository wire/client contract。 |
| Reopen condition | Consumer必须在storage implementation前获得完整固定OpenAPI，且接受相应compatibility和regeneration成本。 |

### P2-R11-D11 — Permanent narrow provider probes under existing gate classes

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D11` |
| Topic | WP2 revisions, feasibility evidence lifetime and gate ownership |
| Status | `ACCEPTED` |
| Decision | WP2分四批：`WP2-R1`验证exact image/Dolt identity、filesystem lock/fsync/rename及SQLite WAL/backup；`WP2-R2`在临时repository验证`dolt sql -f` canonical replay、commit/ref/marker；`WP2-R3`验证repository-scoped sql-server、driver candidates、pinned stream/cancel及CLI/server owner exclusion；`WP2-R4`完成kill/restart证据、driver/lock选择、stop/go conclusion和upgrade rerun入口。最小probe、fixture和evidence schema作为repository-owned长期upgrade gate保留，但不得扩张为通用provider framework。Provider/driver/stream cells由`P2-PR-CONTRACT`拥有，kill/restart cells由`P2-PR-RECOVERY`拥有，不新增第五种feasibility gate。 |
| Rationale | 这些假设会在Dolt、driver、image和filesystem升级时重新成为风险，保留窄probe比一次性spike更可审计；复用既有gate class避免重复result authority。 |
| Rejected alternatives | 验证后删除spike：升级无法重现证据；建立通用provider certification framework：当前只有一个provider/platform；新增独立feasibility gate：与Contract/Recovery owner重复。 |
| Constraints | WP2入口要求WP0，允许与WP1并行；所有probe使用临时repository，不发布public capability、不建立accepted storage format、不产生numeric performance claim。任一stop/go关键项失败阻塞WP3并重开owning decision。Rollback删除相应dependency/probe R及临时数据，不触碰accepted durable root。 |
| Downstream impact | 约束provider integration tests、driver dependency evidence、upgrade matrix、Contract/Recovery cell activation及WP3 entry preflight。 |
| Formal owner | Phase 2 implementation plan；Dolt/provider compatibility and upgrade evidence。 |
| Reopen condition | Provider/platform identity变化，或正式增加第二provider并确实需要共享certification abstraction。 |

### P2-R11-D12 — Concrete non-public durable foundation before lifecycle activation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D12` |
| Topic | WP3 revisions, public-route boundary and intermediate storage rollback |
| Status | `ACCEPTED` |
| Decision | WP3分三批：`WP3-R1`实现durable-root lock、ServiceEpoch、server-derived path resolver及layout/storage identity；`WP3-R2`实现global registry、per-repository control schema、ACL及基础accounting transaction adapters；`WP3-R3`实现deterministic aggregate staging、Dolt initial state、atomic directory publication及formal-path reopen verifier。WP3使用真实Dolt/SQLite/filesystem并交付具体storage/provisioning primitives及测试，但不注册`CreateRepository`或其他public lifecycle route；公开create必须在WP4与journal/recovery语义一起原子激活。 |
| Rationale | 同步或无journal地提前公开Create会违反accepted async recovery contract；先把具体storage boundary验证完成可让WP4只负责真实operation orchestration，而不是同时猜测filesystem行为。 |
| Rejected alternatives | WP3提前公开同步Create：与accepted contract冲突；只写interface/mock：不证明layout和publication；把全部foundation延后WP4：单批同时承担root、registry、Dolt、journal和wire，难review/rollback。 |
| Constraints | WP3入口要求WP1、WP2共同PASS。每个R持久写入明确layout/control schema version；出口覆盖identity mismatch、duplicate root owner、atomic publication、unsupported future schema和reopen validation。首版exit前中间format只支持run-scoped volume丢弃重建，不承诺版本迁移；不得silent downgrade。 |
| Downstream impact | 约束storage module、registry/control schema、provisioning primitives、WP4 Create executor dependency及storage compatibility fixtures。 |
| Formal owner | Phase 2 implementation plan；Repository durable layout/registry/control contract。 |
| Reopen condition | Accepted storage backend提供跨registry与aggregate的原子provision primitive，或产品要求WP3本身成为可发布milestone并愿意重新定义public lifecycle。 |

### P2-R11-D13 — CreateRepository as the first real operation-runtime consumer

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D13` |
| Topic | WP4 revisions, first durable effect consumer and deferred store-specific recovery |
| Status | `ACCEPTED` |
| Decision | WP4使用真实`CreateRepository`而非dummy effect或提前搬入完整Current/Versioned write来验证operation runtime。`WP4-R1`实现RepositoryOperation、FailureDescriptor、idempotency、global create journal及GetOperation representation；`WP4-R2`实现Create executor、claim/lease/fencing、FaultController、staged-publication reconciler；`WP4-R3`原子激活Local/Remote `CreateRepository`、`GetRepository`、`GetOperation`及create crash/restart matrix；`WP4-R4`交付repository-bound artifact upload/download和staged publication，为WP5/WP7提供真实输入边界。WP4只宣称Create与artifact已经证明的operation/recovery cells；Current/Versioned的per-store journal marker、UNKNOWN及writer recovery cells分别随WP5/WP7真实mutation激活，不以test-only effect宣称通用runtime完成。薄`GetRepositoryResourceUsage`在自然拥有完整字段的后续WP激活，不为WP4扩张监控责任。 |
| Rationale | Create具有真实async、idempotent、filesystem/Dolt external effect和特殊global authority，足以锚定operation model；推迟store-specific cells避免空框架及跨WP重复实现。Artifact transfer紧随可用repository，为两类store提供共同安全输入。 |
| Rejected alternatives | Test-only dummy effect：维护第二语义且不证明生产路径；WP4提前完整Current/Versioned mutation：破坏WP5/WP7边界；只实现抽象journal无consumer：无法验证状态/恢复；Create无journal同步返回：违反accepted semantics。 |
| Constraints | WP4入口要求WP3 PASS。R3出口覆盖same-key同/异digest、accept/effect/publish/verify/response crash points、service/Dolt restart、identity mismatch、quarantine和GetOperation；R4覆盖upload close/digest/authorization/staging cleanup。R1无public activation；R2/R3的global registry format rollback只允许run-scoped重建或已验证registry backup/restore；已发布artifact按正式retention处理，不能用rollback删除。 |
| Downstream impact | 约束operation application/domain、global journal、Create lifecycle、FaultController/reconciler、client routes、artifact transfer及WP5/WP7 journal adapter接入点。 |
| Formal owner | Phase 2 implementation plan；Repository operation/create/artifact contracts。 |
| Reopen condition | Provider获得原子、可证明且无需durable operation的create primitive，或WP5/WP7发现共用runtime接口不能承载已接受的store-specific recovery semantics。 |

### P2-R11-D14 — One-way deterministic wire-contract publication

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D14` |
| Topic | Wire model source, OpenAPI publication and package version coordination |
| Status | `ACCEPTED` |
| Decision | Implementation authority单向流动为formal semantic contract → `gateway-repository-contracts` typed models/schema registry → service route composition确定性生成的OpenAPI/JSON Schema snapshot → service/client conformance。Checked-in snapshot是发布、diff和兼容性证据，但不得手工维护一套与typed model平行的DTO；生成结果变化必须与owning contract/model/route在同一activation R review。三个distribution独立构建wheel，但v1使用同一协调的Repository contract version。初版Remote SDK直接消费contracts，不增加完整SDK codegen工具链；未来非Python consumer可从已发布snapshot生成。 |
| Rationale | 固定生成方向消除Pydantic、OpenAPI和SDK三套模型漂移，又保留language-neutral发布材料；协调version避免初版组合兼容矩阵无界。 |
| Rejected alternatives | 手写OpenAPI和Python DTO双维护：容易漂移；初版引入全量codegen：增加工具链而当前只有Python consumer；三个package独立演进contract version：形成未经验证的组合。 |
| Constraints | Formal owner继续拥有语义，生成器不能以代码现状覆盖formal规则。Snapshot必须deterministic、offline、diffable；breaking change遵守既有`/v2`和compatibility policy。 |
| Downstream impact | 约束WP1 schema pipeline、package version、contract snapshot tests和未来SDK发布。 |
| Formal owner | Repository wire/client contract；Phase 2 implementation plan。 |
| Reopen condition | 出现accepted non-Python primary consumer并要求OpenAPI-first code generation成为唯一implementation source。 |

### P2-R11-D15 — Local client below transport but above application policy

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D15` |
| Topic | LocalRepositoryClient lifecycle, authentication bypass and semantic parity |
| Status | `ACCEPTED` |
| Decision | `LocalRepositoryClient`绑定已经启动并持有durable-root ownership的`RepositoryApplicationRuntime`；只绕过HTTP serialization和bearer credential parsing，通过显式CallerIdentity/RequestContext进入与Remote相同的authorization、admission、idempotency、journal、effect和recovery application path。Local不得自行打开root、另启scheduler、直接构造provider或管理Dolt process lifecycle。Backend production只依赖Remote/client contract，不使用Local；Local用于conformance和受控同进程集成。 |
| Rationale | Local若绕过policy/effect path就无法证明Local/Remote语义等价；由runtime拥有生命周期又避免多个Local client争用同一root。 |
| Rejected alternatives | Local直接调用storage adapter：绕过authz/journal；每client创建runtime：重复root owner/scheduler；生产backend使用Local：重新耦合volume/provider。 |
| Constraints | Remote-only transport authentication/TLS cells不要求Local模拟，但application authorization和resource policy仍执行。Runtime shutdown后Local必须返回typed unavailable而非隐式重启。 |
| Downstream impact | 约束client port、composition root、test fixtures、CallerContext及Local/Remote matrix。 |
| Formal owner | Repository client/application boundary；Phase 2 conformance plan。 |
| Reopen condition | Local从public deliverable移除，或accepted embedded deployment正式让业务进程成为runtime owner。 |

### P2-R11-D16 — Scoped operation references without a global locator for every operation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D16` |
| Topic | Create-operation lookup and ordinary per-repository operation routing |
| Status | `ACCEPTED` |
| Decision | SDK返回closed typed `OperationRef`。Create使用`scope=CREATE + RepositoryOperationId`并通过service-scoped create-operation GET查询；普通operation使用`scope=REPOSITORY + RepositoryId + RepositoryOperationId`并通过repository-scoped GET查询。SDK暴露统一`GetOperation(OperationRef)`并按scope选择closed route。OperationId保持opaque，不编码path、storage key或RepositoryId；global registry只拥有create/delete等global lifecycle operation，不为所有per-repository operation维护global locator/index。 |
| Rationale | Create尚无RepositoryId，需要service scope；普通operation留在per-repository control authority可避免每项operation形成global SQLite写热点，同时SDK仍保持统一体验。 |
| Rejected alternatives | 所有operation全局查询：需要node-wide locator写入；OperationId编码repository/path：泄漏并固化routing；Create成功前伪造RepositoryId route：identity尚未发布；两个不相关SDK方法：增加caller分支。 |
| Constraints | 两类GET都按current auth/ACL重新授权并执行existence hiding；Create未成功时依据acceptance caller/global action授权，成功后结果访问不得绕过当前repository policy。OperationRef wire/schema必须closed且进入compatibility snapshot。 |
| Downstream impact | 约束WP4 global/per-repository route、client polling、registry/control lookup和authorization tests。 |
| Formal owner | Repository operation/wire/client contract；registry topology。 |
| Reopen condition | Accepted shared control plane成为全部operation locator authority，或operation storage从per-repository control迁移到全局sharded service。 |

### P2-R11-D17 — Bounded parallel repository creation with short registry transactions

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D17` |
| Topic | CreateRepository concurrency and global registry serialization |
| Status | `ACCEPTED` |
| Decision | 不同CreateRepository operation可在production ResourcePolicy显式、finite的`max_concurrent_repository_creates`内并行初始化；global registry只在acceptance、lifecycle/evidence transition和publication时使用短SQLite transaction，不持锁覆盖Dolt/control初始化。每个operation使用独立deterministic staging/storage key、claim和ServiceEpoch/fencing evidence；相同idempotency scope coalesce到原operation，不产生第二executor。Durable-root process lock只限制active service owner，不把全部create串成全局单任务队列。 |
| Rationale | 独立repository create没有语义冲突，长时间全局串行会让单个慢Dolt初始化阻塞所有项目；短authority transaction与有界并行兼顾吞吐和registry一致性。 |
| Rejected alternatives | 全部create全程串行：资源利用低且head-of-line blocking；无界并行：耗尽process/disk/registry；长registry transaction包住filesystem effect：锁期不可控；同key启动多个executor：可能重复publish。 |
| Constraints | Design不声明通用production并发数；capacity profile必须测量并显式配置。并行create仍受node disk watermark、queue、root reserve和shutdown/recovery规则约束。 |
| Downstream impact | 约束WP4 create scheduler、ResourcePolicy、registry transaction、staging、load/crash tests及capacity evidence。 |
| Formal owner | Repository create/runtime/resource-governance contract；Phase 2 implementation plan。 |
| Reopen condition | Measurement证明Dolt/filesystem create不能安全并行，或global registry迁移到支持不同transaction/concurrency语义的authority。 |

### P2-R11-D18 — One-shot idempotent artifact streaming without resumable upload state

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D18` |
| Topic | WP4 artifact upload protocol and thin resumability boundary |
| Status | `ACCEPTED` |
| Decision | v1 artifact ingress使用one-shot authenticated streaming upload。Caller提交idempotency key、media type、declared size/raw digest、content contract和intended action；Service持久化最小repository-bound upload/staging record，完整close、measured validation及manifest publication后返回ArtifactRef。中途disconnect/restart不发布，caller以原key完整重传；publish后响应丢失时same-key/same-digest返回原ArtifactRef，different digest冲突。v1不提供public multipart/session/chunk、parallel或range-resume upload，也不提供anonymous URL；artifact download使用bounded authenticated stream且不承诺HTTP Range，失败后重新下载。 |
| Rationale | 单请求加幂等结果覆盖当前内部caller和response-loss恢复，不引入chunk map、partial hash、resume token及额外expiry state machine；真实需求出现前保持artifact边界薄。 |
| Rejected alternatives | 首版resumable multipart：显著扩大state/recovery/security；无idempotency upload：response loss可能产生重复artifact；把partial staging发布为ArtifactRef：完整性不明；presigned URL：新增credential/egress authority。 |
| Constraints | 上传仍增量执行size/digest/parser limits，不完整buffer；staging record不是RepositoryOperation，不进入通用effect status。Unknown/published attribution、cleanup和retention必须遵守既有artifact evidence规则。超大文件重传成本是明确v1 tradeoff。 |
| Downstream impact | 约束WP4 upload route/SDK、staging metadata、idempotency、cleanup/restart tests及future resume reopen boundary。 |
| Formal owner | Repository artifact transfer contract；Phase 2 implementation plan。 |
| Reopen condition | Accepted workload证明重传成本不可接受并明确要求multipart/range resume、chunk integrity、expiry和recovery semantics。 |

### P2-R11-D19 — Bounded single-pass whole-table data plane

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D19` |
| Topic | Whole-table import/export serialization and materialization cost |
| Status | `ACCEPTED` |
| Decision | Whole-table data plane必须bounded、streaming且不产生无必要的第二份全量表示。Versioned import上传后只保存一份canonical SQL replay artifact；Service增量验证size/digest/closed grammar，Dolt executor直接消费该文件或流，不先解析为全表Python rows、JSON或重新生成等价SQL。Current async bulk/Create/Replace的首选input artifact固定为versioned Arrow IPC；adapter按RecordBatch校验并通过prepared/batched SQLite binding写入staging/shadow boundary，禁止全表`to_pylist()`或全量Python object materialization。Direct export从pinned Dolt/SQLite reader按bounded RecordBatch输出framed Arrow；durable export按batch写Parquet staging，完整close并验证manifest/hash/size/schema后才原子发布。Upload staging到正式artifact在同filesystem优先atomic rename，provider复用已发布bytes，不做无语义的整文件复制。`NONE/STRUCTURAL` verification不得隐式执行FULL row readback；FULL的额外扫描是caller显式选择的正常成本。 |
| Rationale | 已确认的SQL replay、Arrow和Parquet能够避免大型JSON及逐行wire开销；进一步禁止重复全量物化和无意义copy，可在不增加新provider/framework的情况下控制CPU、内存和I/O放大。Current input codec此前未明确，Arrow IPC与既有logical type/stream boundary一致。 |
| Rejected alternatives | 大表普通JSON或逐行RPC：序列化与调用开销高；Current接受caller SQLite文件：信任、schema和compatibility边界过宽；统一强制Parquet import：旧Versioned measurement不支持且SQLite仍需decode/bind；设计阶段宣称zero-copy：SQLite binding、Dolt SQL parsing和Parquet encoding仍有必要转换；未测量即引入native loader：扩大实现和安全面。 |
| Constraints | 本decision不声明numeric speedup或真正zero-copy。Incremental validation不得降低artifact/parser安全；Current最终SQLite publication仍满足atomic batch/generation/idempotency contract。WP5/WP7 measurement分别记录upload validation、decode、provider write、commit/publication、requested verification、export encoding及bounded-buffer evidence；只有accepted measurement证明serialization为主要瓶颈后才重开native/alternate provider优化。 |
| Downstream impact | 约束RepositoryImportArtifact消费、Current bulk artifact schema、Arrow/Parquet codecs、SQLite adapter、Dolt executor、artifact staging、WP5/WP7 tests和measurement spans。 |
| Formal owner | Repository whole-table data-plane contract；Current/Versioned provider implementation plan；performance measurement contract。 |
| Reopen condition | Accepted container measurement证明single-pass SQL replay或Arrow→SQLite路径无法满足容量，或caller明确需要另一closed import/export codec并提供兼容、安全和恢复语义。 |

### P2-R11-D20 — Four vertical revisions for CurrentTableStore

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D20` |
| Topic | WP5 CurrentTableStore revisions, activation, evidence and rollback |
| Status | `ACCEPTED` |
| Decision | WP5分四批：`WP5-R1`实现lazy current SQLite materialization、identity/schema version、catalog/table generation及transaction adapter，不公开mutation；`WP5-R2`端到端交付Create/DropCurrentTable、GetCurrentCatalog/GetCurrentTable及async operation/generation/idempotency/concurrency/verification；`WP5-R3`交付同步ApplyCurrentTableMutations和StreamCurrentTableRows的projection/filter/order/cursor、generation pin、backpressure/cancel，并保持data/generation/idempotency/effect marker单SQLite transaction；`WP5-R4`交付Arrow IPC驱动的ReplaceCurrentTable、SubmitCurrentTableMutationBatch、ExportCurrentTable、三档verification、control/current crash reconciliation及完整Local/Remote matrix。 |
| Rationale | 先固定Current transaction authority，再按table lifecycle、同步局部mutation/read、异步bulk/export形成真实纵切，避免一次提交全部Current surface或用隐藏size阈值改变completion model。 |
| Rejected alternatives | 全部Current能力单批交付：review/recovery矩阵过大；先公开无持久语义stub；所有mutation统一async或按size隐式切换；为Current复制Dolt commit/ref模型。 |
| Constraints | Entry要求WP4 PASS及Current formal owner closure。R1以Static为主；R2–R4随真实能力激活Contract和对应Recovery cells。Exit要求全部Current public surface、Arrow/Parquet integrity、bounded buffers、verification和restart closure通过。Schema rollback只允许run-scoped重建或已验证Current backup/restore；已成功mutation不因image rollback撤销。 |
| Downstream impact | 约束Current modules/routes/client、SQLite schema、operation adapters、fixtures、gate matrix、evidence及WP7 cross-store inventory dependency。 |
| Formal owner | Phase 2 implementation plan；CurrentTableStore contract。 |
| Reopen condition | SQLite provider无法满足accepted atomic bulk/generation语义，或Current public workload发生架构级变化。 |

### P2-R11-D21 — Separate Versioned read/runtime and write/publication work packages

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D21` |
| Topic | WP6/WP7 revisions, dependency and Versioned rollback |
| Status | `ACCEPTED` |
| Decision | WP6分四批：`WP6-R1`交付DoltRuntimeCoordinator、ResolveRef、GetCommit、GetCatalog及runtime pin/eviction；`WP6-R2`交付StreamTableRows的EXACT/LATEST_AT_START、cursor/filter/order和immutable pin；`WP6-R3`交付ExportTable及DiffRefs的显式Arrow/Parquet路径；`WP6-R4`完成driver/process restart、cancel/backpressure、artifact cleanup和Local/Remote read closure。WP7在WP5、WP6均PASS后分四批：`WP7-R1`交付mutable/immutable/protected ref lifecycle、CHECK_EXPECTED/LWW、name/tombstone及ref verification；`WP7-R2`实现非公开SubmitImport executor、canonical replay、internal operation ref、commit marker和effect attribution；`WP7-R3`公开SubmitImport target publication、NONE/STRUCTURAL/FULL及完整crash reconciliation；`WP7-R4`交付VerifyCommit、GetTableInventory、write conformance和Phase 3 consumer-ready checkpoint。 |
| Rationale | 只读runtime先证明pinned snapshot和stream，再引入不可逆commit/ref effect；WP7等待并行Current/Versioned read两线收口可冻结共享DTO、operation和inventory binding。 |
| Rejected alternatives | Read/write同一大WP；import先于pinned read/provider ownership；WP7在WP5未稳定时并行修改共享contract；用rollback image自动撤销已发布commit/ref。 |
| Constraints | WP6主要由Contract gate拥有，export/restart追加Recovery；WP7-R1起运行Contract/Recovery，R3覆盖完整write crash matrix。Read-only runtime cache可直接回退；已发布commit/ref不因代码rollback撤销，只能通过新的显式ref mutation，format变化遵循backup/forward-fix。 |
| Downstream impact | 约束Dolt runtime/read/write modules、client/routes、ref registry、import executor、verification、inventory、evidence和Phase 3 handoff。 |
| Formal owner | Phase 2 implementation plan；Versioned Repository contract。 |
| Reopen condition | Dolt provider无法分离read/runtime和write publication，或consumer-ready check发现blocking public contract缺口。 |

### P2-R11-D22 — Irreversible maintenance effects with explicit recovery, not rollback fiction

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D22` |
| Topic | WP8 revisions and rollback semantics for retention, GC, restore and delete |
| Status | `ACCEPTED` |
| Decision | WP8分四批：`WP8-R1`实现retention roots、operation/idempotency compaction、artifact expiry、safe cleanup和quarantine；`WP8-R2`实现Plan/ExecuteGarbageCollection、root epoch/pins、maintenance barrier和crash checkpoint；`WP8-R3`实现quiescent backup/restore、新RepositoryIncarnationId及RESTORED_RESTRICTED activation；`WP8-R4`实现Plan/ExecuteDeleteRepository、tombstone、trash/purge及operator evidence/repair入口。每类不可逆effect必须有plan、current-policy authorization、reason、checkpoint、recovery和exact evidence，且故障限于目标repository。 |
| Rationale | Retention/GC/restore/delete共享aggregate maintenance边界，但effect不可用“回退代码”伪装为撤销；四批按资源生命周期逐步扩大破坏面。 |
| Rejected alternatives | 将全部maintenance合并；无plan直接GC/delete；把restore当普通copy；声称image rollback恢复已删除数据；只用mock验证destructive path。 |
| Constraints | Entry要求WP7 consumer-ready及全部store recovery cells PASS。Contract验证plan/schema/auth，Recovery覆盖真实checkpoints。Rollback只表示部署/代码回退：已GC/purge数据只能从事先验证的backup恢复，成功restore的新incarnation不得被旧image改回。WP8中间R不进production，conformance data为run-scoped disposable。 |
| Downstream impact | 约束retention/maintenance modules、operator API、backup manifests、tombstone/quarantine、destructive gates、runbook和evidence。 |
| Formal owner | Phase 2 implementation plan；Repository maintenance/lifecycle contracts。 |
| Reopen condition | Product要求online/non-quiescent backup、跨节点restore或可撤销delete并提供相应authority和storage primitive。 |

### P2-R11-D23 — Production closure before a source-frozen exit revision

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D23` |
| Topic | WP9 revisions, production hardening and candidate closure |
| Status | `ACCEPTED` |
| Decision | WP9分四批：`WP9-R1`完成telemetry、typed audit、thin resource snapshot、readiness/degradation、shutdown/reconciliation scheduler、RuntimeBuildIdentity和EnvironmentFingerprint；`WP9-R2`完成production image、non-root/read-only rootfs、mount/network/capability hardening、TLS ingress、STATIC_BEARER rotation及persistent/backup volume topology；`WP9-R3`完成compatibility snapshots、authorization/RequirementCoverageInventory、全部gate runner、capacity characterization、runbook、cleanup proof和Phase 1 regression adapter；`WP9-R4`不再修改source，只提名clean exact commit、构建发布artifacts、执行完整gate并生成immutable evidence/sign-off。 |
| Rationale | 先把operations、deployment和verification机制作为可review实现收口，再冻结source运行exit，避免为了让gate通过而在同一attempt修改candidate或证据。 |
| Rejected alternatives | Container/hardening只在最终脚本临时拼装；边跑exit边修改source；把capacity数字当correctness gate；跨commit复用通过证据。 |
| Constraints | Entry要求WP8 PASS和blocking register为空。R1–R3按storage compatibility rollback；R4失败不能修改证据，tracked code/config/lock修复必须形成新candidate。Exit要求Remote只经TLS、required cells唯一owner、identity/locks/images/environment/commit一致。 |
| Downstream impact | 约束observability/deploy/conformance modules、Compose/images、gate aggregation、runbook、release manifest和sign-off。 |
| Formal owner | Phase 2 implementation/deployment/verification plan。 |
| Reopen condition | Accepted deployment平台提供等价production topology/evidence authority，或release governance改变exact-candidate规则。 |

### P2-R11-D24 — Critical path with two explicit Phase 3 handoffs and exact-commit exit

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D24` |
| Topic | Critical path, Phase 3 overlap and exact-commit exit procedure |
| Status | `ACCEPTED` |
| Decision | Phase 2主关键路径为`Round 11/consolidated review → bounded Phase 3 consumer-adequacy check → F0 formal closure → WP0 → max(WP1,WP2) → WP3 → WP4 → max(WP5,WP6) → WP7 → WP8 → WP9-R1..R3 → WP9-R4`。WP7 consumer-ready PASS后显式分出Phase 3详细交互设计支线，可与WP8–WP9并行；Phase 3 production implementation仍以Phase 2 clean exact-commit exit PASS为entry。WP9-R4流程固定为：确认Round 0–11/consolidated/formal/blocking closure；在clean worktree提名唯一candidate；从该commit构建contracts/client/service/conformance artifacts与images并记录digests；同commit运行全部Phase 2 Static/Contract/Recovery、完整Phase 1 correctness/native及production TLS/container exit；验证required-cell coverage、fault receipts、cleanup和identity bundle；只聚合同一candidate closure的PASS attempts；最终sign-off后才声明exit。 |
| Rationale | 两处Phase 3 handoff既在实现前验证consumer adequacy，又在真实consumer path稳定后允许详细设计重叠；exact commit和完整重跑保证最终artifact而非拼接历史结果被验证。 |
| Rejected alternatives | 完全遗漏Phase 3 handoff；现在先完整设计/实现Phase 3；等WP9结束才开始任何Phase 3设计；跨commit/image/environment拼接PASS；修改candidate后沿用旧gate result。 |
| Constraints | BLOCKED可按既有规则在外部环境恢复后对同commit新建attempt；assertion failure必须新commit。任何tracked code/config/lock修复产生新candidate并无条件重新运行全部exit gates。Phase 3设计不得静默改变已冻结Phase 2 contract；需改变时显式reopen。Phase 1 frozen container identity不重签或冒充。 |
| Downstream impact | 约束正式dependency graph、delivery calendar、consumer checkpoint、candidate nomination、CI/release orchestration和Phase 3 entry。 |
| Formal owner | Phase 2 implementation/release plan；cross-phase delivery sequence；Phase 3 entry criteria。 |
| Reopen condition | Phase 3 consumer contract出现blocking变化，或accepted release system能证明跨attempt/content-addressed evidence组合与单candidate closure等价。 |

### P2-R11-D25 — Repository policy surface activates with public lifecycle

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D25` |
| Topic | Work-package owner for repository policy read/write |
| Status | `ACCEPTED` |
| Decision | `GetRepositoryPolicy`和`UpdateRepositoryPolicy`明确归属`WP4-R3`，与CreateRepository、GetRepository和首次public repository lifecycle同时激活。它们复用WP3已建立的per-repository control SQLite ACL authority；Update携带expected policy generation和idempotency key，并与new ACL generation/idempotency result在同一control transaction提交。Route同时注册`POLICY_READ/POLICY_WRITE` closed actions、401/403/404 existence hiding、generation cache invalidation及Fake/Local/Remote authorization coverage。 |
| Rationale | Repository创建后必须能够读取和轮换initial grants；把policy surface放在lifecycle激活点可关闭public-action coverage缺口，又不新增WP、R或通用policy engine。 |
| Rejected alternatives | 延后到WP9：repository在WP4–WP8期间缺少正式policy mutation；放WP3提前公开：Create尚未安全激活；deployment config拥有全部per-repository ACL：破坏aggregate authority。 |
| Constraints | Policy只保存CallerIdentity到closed Action set，不增加role、wildcard、condition或data-level ACL。Create caller若未授予自身后续权限，成功后访问按current policy处理，不推断owner。 |
| Downstream impact | 补全WP4-R3 routes/client/contracts、control transaction、authorization inventory、conformance和evidence。 |
| Formal owner | Repository authorization/policy contract；Phase 2 implementation plan。 |
| Reopen condition | Accepted external policy service成为唯一repository policy authority并提供transaction/version/recovery contract。 |

### P2-R11-D26 — Physical ownership and forbidden-content materialization

| 字段 | 值 |
| --- | --- |
| ID | `P2-R11-D26` |
| Topic | Required file/module/test/evidence ownership in the formal implementation plan |
| Status | `ACCEPTED` |
| Decision | Formal Phase 2 plan必须为每个WP/R列出exact files/modules、fixtures/tests和evidence owner，并保持以下物理职责：WP0拥有workspace/locks/gate routing，禁止feature/storage；WP1拥有contracts/client transport/service composition/auth，禁止repository provider/data stub；WP2拥有窄Dolt/SQLite/filesystem probes，禁止public capability/provider framework；WP3拥有layout/registry/control/ACL/accounting，禁止public lifecycle；WP4拥有operation/create/policy/artifact，禁止Current/Versioned mutation和monitoring platform；WP5拥有Current storage/application/transport，禁止Dolt/ref/cross-store transaction；WP6拥有Dolt runtime/versioned read/stream/diff/export，禁止public write；WP7拥有ref/import/verification/inventory，禁止business workflow/dual-write；WP8拥有retention/GC/backup/restore/delete/repair，禁止service cron/multi-node writer/rollback fiction；WP9拥有observability/security/deploy/compatibility/release，禁止新product capability，且R4禁止source mutation。每个formal R block必须显式包含goal、scope、non-goals、prerequisites、contract/schema/API delta、files/modules、fixtures/tests、required gate、evidence、rollback、entry/exit及forbidden content。 |
| Rationale | Round 11语义和R已闭合，但formal plan若不固定physical owner和禁止混入内容，实施时仍可能跨包复制authority或把后续能力偷渡进较早R。 |
| Rejected alternatives | 只列逻辑WP不列module/test owner：review无法界定diff；现在预建全部目录/stub：违反atomic activation；允许同一规则由多个WP拥有：traceability和rollback不唯一。 |
| Constraints | Exact filename可在formalization时按实际repository topology细化，但不得改变三package依赖方向、WP职责或public activation boundary。新增文件必须映射唯一WP/R和gate owner。 |
| Downstream impact | 直接约束formal implementation plan、review checklist、architecture tests、requirement traceability及affected-scope router。 |
| Formal owner | Phase 2 implementation design and delivery plan；architecture/gate ownership policy。 |
| Reopen condition | Repository/package topology在implementation前发生accepted结构性变化，并重新建立等价无环owner与traceability map。 |
