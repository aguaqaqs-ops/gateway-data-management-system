# Phase 2 Decision Ledger — Round 0–3

状态：**Draft / Active Interview Record**

配套指南：[interactive-design-session-guide.md](interactive-design-session-guide.md)

本文件是 Round 0–3 的唯一 Decision Ledger 正文位置。拆分仅改变文档组织，
不改变任何 Decision ID、状态、语义、supersession 或 formal owner。

每个 decision 使用稳定 ID：

```text
P2-R<round>-D<sequence>
```

例如：`P2-R1-D01`。

状态只能是：

- `ACCEPTED`
- `REJECTED`
- `DEFERRED`
- `OPEN`
- `SUPERSEDED`

每条记录至少包含：

| 字段 | 含义 |
| --- | --- |
| ID | 稳定 decision ID |
| Topic | 决策主题 |
| Status | 当前状态 |
| Decision | 已选择的方案 |
| Rationale | 选择理由 |
| Rejected alternatives | 被拒方案及原因 |
| Constraints | authority、兼容、安全或环境约束 |
| Downstream impact | 影响的 API、data、recovery、deploy、tests、WP |
| Formal owner | 最终应写入的 owning document |
| Reopen condition | 哪些新事实允许重开 |

### P2-R0-D01 — Phase 2 system boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D01` |
| Topic | Phase 2 system boundary |
| Status | `SUPERSEDED` |
| Decision | 采用 Strict Repository Foundation：完整设计独立、通用、容器化的 Repository Service、Local/Remote client、Dolt ownership、read/write/recovery、安全、部署、测试和 exit plan；不纳入业务语义或 Phase 3–5 能力。 |
| Rationale | 这是满足 accepted Phase 2 exit conditions 的最小完整边界，同时保持 Repository Service 与业务系统的 ownership 隔离。 |
| Rejected alternatives | Expanded Foundation：拒绝，因会跨入 Phase 3–5 并混淆 semantic owner；Transport/CRUD Skeleton：拒绝，因无法满足 journal、reconciliation、安全和 recovery exit conditions。 |
| Constraints | Architecture、Implementation Stages、Contract Taxonomy、Canonical Storage 与 External Effect accepted rules。 |
| Downstream impact | 约束全部 public API、data、recovery、deploy、security、tests、gates 和 WP；后续 Round 不得引入业务 wire 语义。 |
| Formal owner | Architecture / Implementation Stages；Phase 2 implementation design and delivery plan 负责组合与追踪。 |
| Reopen condition | Accepted architecture/contract 被正式修改，或发现满足 Phase 2 exit 必须跨越当前 phase owner 的不可解冲突。 |
| Superseded by | `P2-R0-D06` |

### P2-R0-D02 — Frozen authority constraints

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D02` |
| Topic | Accepted formal constraints |
| Status | `ACCEPTED` |
| Decision | 将已审计的 accepted formal contract、architecture、policy、ADR 和 Phase 1 closure 作为冻结约束；发现实质冲突时暂停受影响设计、识别 semantic owner 并先 formalize 收口，不用实现兼容两套语义。 |
| Rationale | 保持单一 semantic authority，防止 Phase 2 重写或冒充 Phase 1 identity 与既有 byte/data/effect contract。 |
| Rejected alternatives | 以 bootstrap implementation、temporary history 或 legacy 行为覆盖 formal：拒绝；在代码中长期兼容冲突语义：拒绝。 |
| Constraints | Authority 顺序为 accepted formal contract/architecture/policy > accepted ADR > accepted evidence/closure > implementation/tests > temporary > legacy。 |
| Downstream impact | 后续每轮的选项必须标明 authority、owner 和 reopen condition；formal 冲突将只阻塞受影响决定。 |
| Formal owner | 各现有 semantic owner；Phase 2 plan 只引用和建立 traceability，不复制规范。 |
| Reopen condition | 出现可定位的 formal 内部冲突、新的 accepted ADR/contract，或正式 owner 修改既有规则。 |

### P2-R0-D03 — Phase 2 non-goals

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D03` |
| Topic | Phase 2 non-goals |
| Status | `SUPERSEDED` |
| Decision | 保持指南 §9 non-goals：不解释业务 hidden-table/Snapshot/Comparison/Risk 语义，不做 candidate/archive workflow，不进入 Phase 3/4/5，不做多节点共享 writer、通用 framework、local-path contract、大文件普通 JSON、Phase 1 identity 修改或无 baseline 的性能收益声明。 |
| Rationale | 防止 foundation 扩张为业务平台或通用框架，并保护 Phase 1 冻结产物及后续 phase owner。 |
| Rejected alternatives | 将业务集成、legacy migration、多节点 writer 或预优化作为 Phase 2 默认范围：拒绝；这些只可按独立 authority 和重新进入条件重开。 |
| Constraints | Architecture §9、Implementation Stages Phase 2、Phase 1 closure、Performance Measurement 与 Rust policy。 |
| Downstream impact | 收窄 API/data model、deploy topology、test matrix 和 WP；但可靠性、安全、恢复、GC 与 backup 仍属于 Phase 2 必需能力。 |
| Formal owner | Architecture / Implementation Stages；Phase 2 plan 记录具体 scope/non-goals。 |
| Reopen condition | 后续 phase 的硬依赖证明当前 non-goal 是 Phase 2 exit 的必要条件，并经 semantic owner 正式批准。 |
| Superseded by | `P2-R0-D07` |

### P2-R0-D04 — Design packages, dependencies and decision budget

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D04` |
| Topic | Design package map |
| Status | `ACCEPTED` |
| Decision | 保留 Round 0–11 的既定顺序和依赖；每轮 2–5 个高价值问题，预计形成约 80 条独立 decision records。数量是审计预算，不是配额或完成条件。 |
| Rationale | 该粒度能独立重开受影响决定，又避免把实现细节提升为架构阻塞项。 |
| Rejected alternatives | 约 45 条粗粒度 ledger：拒绝，因耦合过多可独立决定；110 条以上细粒度 ledger：拒绝，因会机械化访谈并放大局部实现事项。 |
| Constraints | 严格遵守 Round stop、Overall stop 和 Formalization stop；当前轮未确认前不得进入下一轮。 |
| Downstream impact | 固定 transport → API/identity → read/storage/write/recovery → GC/security/operations → gates → WP 的设计依赖。 |
| Formal owner | Phase 2 implementation design and delivery plan 的 decision/requirement/WP/gate traceability。 |
| Reopen condition | 某轮发现新的架构级依赖需要拆分受影响 package；不得仅因局部细节或问题数量重排全部轮次。 |

### P2-R0-D05 — User-confirmed decisions and engineering defaults

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D05` |
| Topic | Decision governance |
| Status | `ACCEPTED` |
| Decision | 架构、contract、data、consistency、recovery、deployment、security、compatibility 和 gate 决定必须由用户逐轮确认；非 public/persisted/wire、且不影响语义的内部命名、私有 helper、测试组织和局部实现风格可采用工程默认值。用户可逐轮选择“全部按推荐”。 |
| Rationale | 在保留用户对不可逆或架构级决定控制权的同时，避免低影响事项阻塞完整设计。 |
| Rejected alternatives | 所有局部事项逐项确认：拒绝，因会把实现细节变为阻塞；除 authority 外全部自动委托：拒绝，因对关键 contract 的审计和用户控制不足。 |
| Constraints | Stable error/metric identity、persisted/wire fields、digest/order、timeout/retention/security limits 不是工程默认值，必须在对应 Round 明确裁决。 |
| Downstream impact | 决定后续问题筛选、ledger 粒度、默认假设标注和 Round confirmation 方式。 |
| Formal owner | Phase 2 implementation design and delivery plan 的 governance/traceability；本指南维护访谈过程状态。 |
| Reopen condition | 用户改变确认粒度，或某个原定工程默认值被发现会影响 public contract、持久化、恢复、安全、兼容或 gate。 |

### P2-R0-D06 — Additive CurrentTableStore scope

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D06` |
| Topic | Phase 2 system boundary after current-store amendment |
| Status | `ACCEPTED` |
| Decision | Phase 2 仍以独立、通用、容器化的 Repository Service foundation 为边界，并新增 optional generic `CurrentTableStore` capability。VersionedTableStore/Dolt 与 CurrentTableStore 独立处理 caller-owned tabular content；Repository Service 不理解 Project、Workspace、Submission 或表的业务语义，不决定哪一侧是业务 authority，也不保证跨 store 内容一致。 |
| Rationale | Caller 的实际数据模型同时需要版本化表与 latest-only 表；把 CurrentTableStore 作为显式隔离的附加能力，可复用 RepositoryId、部署、安全和 artifact 基础设施，而不把服务扩张为业务状态机或双写协调器。 |
| Rejected alternatives | 维持纯 Dolt scope：不能满足 latest-only 表需求；由 Repository Service 自动决定 authority/routing 或保证双存储一致：引入业务 policy 与跨引擎协调；把全部业务 repository/workflow 搬入本服务：违反 ownership boundary。 |
| Constraints | Caller 必须显式选择 store 并在自身 owner contract 记录 persistence policy；同一逻辑表可独立存在于两侧。单 store 调用的 durability、idempotency 和 failure semantics 仍由 Repository Service 负责。Accepted formal architecture/contract 在最终 formalization 时必须由 owning documents 显式吸收本 amendment。 |
| Downstream impact | 扩展 wire API、current table data model、storage layout、backup/restore、security actions、concurrency、failure/recovery、tests 和 Phase 2 exit plan；不重开既有 REST、wire version、client role 或 external artifact decisions。 |
| Formal owner | Architecture / Contract Taxonomy / Implementation Stages；Phase 2 implementation design and delivery plan。 |
| Reopen condition | Current-table requirement 被移出本服务，或 caller 需要 Repository Service 自动 routing、跨 store transaction/join 或业务语义。 |
| Supersedes | `P2-R0-D01` |

### P2-R0-D07 — Current-store non-goals and independence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D07` |
| Topic | Phase 2 non-goals after current-store amendment |
| Status | `ACCEPTED` |
| Decision | 在保留原 Phase 2 non-goals 的基础上，明确 CurrentTableStore 不提供业务 persistence-policy authority、自动 store routing、跨 store transaction/consistency/synchronization、跨 Dolt/SQLite join、通用 query federation、任意 SQL/DDL、业务 workflow/state machine 或 v1 convenience dual-write。服务可报告两侧独立 inventory，但不得推断 authority、同步或等价关系。 |
| Rationale | 将 current storage 限定为 typed generic table capability，避免“附加功能”演化为业务数据库平台、双写协调器或 federated SQL engine。 |
| Rejected alternatives | 只用文档警告但保留 generic SQL/dual-write：接口本身会制造错误预期；禁止两侧同名表：不满足 caller 明确的双份存储场景；服务维护业务 persistence policy：重新耦合业务 owner。 |
| Constraints | Raw paths、普通 JSON 大文件、多节点共享 writer、Phase 1 identity 修改及无 baseline 性能声明仍是 non-goals。每个 store 内部仍必须有明确 schema、transaction、idempotency、authorization、resource limit 和 recovery contract。 |
| Downstream impact | 收窄 current API、catalog vocabulary、operation state、error semantics 和 conformance matrix；把跨 store orchestration 留给 caller/application owner。 |
| Formal owner | Architecture / Repository Service wire contract / Phase 2 implementation design and delivery plan。 |
| Reopen condition | Accepted product requirement 明确需要 server-owned store policy、cross-store query 或 journaled composite operation，并单独完成 consistency/recovery design。 |
| Supersedes | `P2-R0-D03` |

### P2-R0-D08 — Round 0–3 implementation-readiness conformance gate

| 字段 | 值 |
| --- | --- |
| ID | `P2-R0-D08` |
| Topic | Cross-round contract acceptance before implementation |
| Status | `ACCEPTED` |
| Decision | Round 0–3 implementation-ready gate 必须覆盖：opaque identity/path leak与N/N-1/capability；RepositoryId/action隔离和production auth fail-closed；Current CAS/idempotency collision/atomic batch/crash rollback；CommitId/current snapshot/cursor/inventory binding；Arrow schema、tamper、backpressure、disconnect、STREAM_END及Parquet integrity；Fake/Local/Remote与production container matrix；不同repository及同repository跨store并发和per-store writer serialization。所有blocking scenario通过前不得声明Round 0–3 implementation-ready。 |
| Rationale | 当前设计的正确性主要位于wire、进程、provider、restart和并发边界，仅有unit tests无法证明。 |
| Rejected alternatives | 主要依赖unit tests并延后container/Remote/restart：无法验证独立service authority；只测happy path：遗漏effect、isolation与truncation风险。 |
| Constraints | Fake只证明application semantics；Local/Remote共享contract suite；production container+Remote是auth/restart/stream/recovery authority。精确fixture/CI lane在Round 10。 |
| Downstream impact | 约束test architecture、fixtures、provider matrix、CI gates、exit evidence和WP拆分。 |
| Formal owner | Phase 2 implementation design/plan；conformance/fixture plan。 |
| Reopen condition | Owning conformance contract提供更强等价gate且覆盖全部边界。 |

### P2-R1-D01 — Caller and trust boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D01` |
| Topic | Repository Service caller boundary |
| Status | `ACCEPTED` |
| Decision | Repository Service 只在受控 internal service network 暴露；正式 caller 仅为 backend、worker 和受控 operator tooling，终端用户/浏览器不得直连。 |
| Rationale | 保持业务认证与 repository service identity 分离，并缩小通用版本库的攻击面。 |
| Rejected alternatives | 外部客户端直连：拒绝，因扩大 public platform、安全和兼容责任；仅 localhost/Unix socket：拒绝，因不满足独立容器 Remote client。 |
| Constraints | 服务间认证与 repository authorization 必须有接入点；内部网络本身不构成 caller identity。 |
| Downstream impact | 约束 ingress、client distribution、authn/authz、audit、rate limit 和 security tests。 |
| Formal owner | Repository Service wire/security contract；Phase 2 deployment design。 |
| Reopen condition | 出现 accepted 外部 consumer contract，或部署环境不再允许内部 service network。 |

### P2-R1-D02 — Thin authentication boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D02` |
| Topic | Authentication responsibility |
| Status | `ACCEPTED` |
| Decision | 不建设用户系统或独立身份服务；Repository Service 只实现薄 `CallerIdentity` resolver 与 repository/action authorization enforcement。`auth_mode=disabled` 仅允许显式 dev/test profile；production 未配置 provider 时 fail closed。 |
| Rationale | Backend 继续拥有最终用户认证，Repository Service 只验证调用服务主体，避免重复业务认证同时防止匿名生产暴露。 |
| Rejected alternatives | 完整 OAuth/user/RBAC 子系统：拒绝为无需求框架；生产默认无认证：拒绝为 unsafe-by-default。 |
| Constraints | Token、private key、trust secret 不得保存在 repository/Dolt metadata；具体 provider 在 Round 8 裁决。 |
| Downstream impact | 定义 transport middleware、configuration、readiness fingerprint、audit identity 和 repository ACL 接口。 |
| Formal owner | Repository Service security contract / Phase 2 security design。 |
| Reopen condition | 业务要求终端用户直连，或平台提供强制统一 sidecar/service-mesh identity contract。 |

### P2-R1-D03 — Control-plane transport

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D03` |
| Topic | Control-plane transport |
| Status | `ACCEPTED` |
| Decision | 首版 public control plane 使用 REST over HTTP 与 versioned UTF-8 JSON；不引入 gRPC/Protobuf control plane。 |
| Rationale | 当前只有受控 Python client，REST 可用单一 server/client/认证/观测栈满足控制面需求，避免无证据 codegen/runtime 复杂度。 |
| Rejected alternatives | 全量 gRPC：拒绝为首版额外工具链；REST + gRPC 双控制面：拒绝为重复 API authority。 |
| Constraints | JSON 只承载控制和小型 metadata；large rows/import/export 禁止进入普通 JSON。 |
| Downstream impact | 约束 wire schema、HTTP status/error mapping、client SDK、proxy、health 和 contract tests。 |
| Formal owner | Repository Service wire contract；必要的 transport ADR。 |
| Reopen condition | 出现独立多语言 generated-client requirement，或 accepted measurement 证明 REST control plane 不满足需求。 |

### P2-R1-D04 — HTTP bulk data plane

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D04` |
| Topic | Bulk data-plane transport |
| Status | `ACCEPTED` |
| Decision | rows、import、export 使用同一 HTTP 服务的 bounded binary streaming 或受控 artifact download；首版不引入 Arrow Flight。具体 Arrow IPC/Parquet 组合在 Round 3 决定。 |
| Rationale | 保持单 transport、单认证和单错误模型；当前没有独立 Flight consumer 或 accepted 性能证据。 |
| Rejected alternatives | Arrow Flight：拒绝为首版第二 transport/descriptor/action authority；大文件 JSON：被 formal 禁止。 |
| Constraints | 必须支持 backpressure、deadline、cancellation、disconnect cleanup、digest/size/media type 和资源上限。 |
| Downstream impact | 约束 data-plane envelope、artifact lifecycle、HTTP client streaming、security limits 和 stream tests。 |
| Formal owner | Repository Service wire/data-plane contract；必要的 transport ADR。 |
| Reopen condition | Accepted production measurement 显示 HTTP binary plane 无法满足容量，或出现独立多语言 Arrow consumer。 |

### P2-R1-D05 — Wire versioning and rollout

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D05` |
| Topic | API/wire versioning |
| Status | `ACCEPTED` |
| Decision | API major 固定在 `/v1`；持久、异步和 binary contract 使用显式 wire schema version。采用 server-first rollout：新 server 支持 current/previous client schema 一个发布窗口；request version 决定 response version；breaking semantic change 使用 `/v2`。 |
| Rationale | 支持 backend 与 Repository Service 非原子升级，同时避免长期双向 N/N-1 兼容矩阵。 |
| Rejected alternatives | 只有 URL version：拒绝，不能版本化 stream/artifact envelope；强制双向 N/N-1：拒绝，首版复杂度过高。 |
| Constraints | 新 client 不要求兼容旧 server，必须在 server/capability 就绪后启用新行为；版本变化须说明 digest/cache/persistence impact。 |
| Downstream impact | 影响 schema、deployment order、deprecation、unknown fields/enums 和 contract matrix。 |
| Formal owner | Repository Service wire contract。 |
| Reopen condition | 部署平台要求 client-first rollout，或出现无法由一个发布窗口覆盖的外部 consumer。 |

### P2-R1-D06 — Fake, Local and Remote client roles

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D06` |
| Topic | Repository client boundaries |
| Status | `ACCEPTED` |
| Decision | 三类 client 共享 semantic contract：Fake 只用于 domain/application tests；Local 只用于 component/integration 并调用相同 application contract；Remote 是唯一 production client。禁止 Remote 故障时自动 local/Dolt fallback。 |
| Rationale | 保留快速测试与 Local/Remote 等价证明，同时确保 production 不重新获得 Dolt/path ownership。 |
| Rejected alternatives | 删除 Local：拒绝，偏离 Phase 2 delivery；production local fallback：拒绝，破坏独立服务和 effect authority。 |
| Constraints | Public client contract 不得包含 host path、Dolt session 或 provider-private object；Fake 不证明 wire/restart/recovery。 |
| Downstream impact | 约束 package dependency、DI、contract suites、production image 和 failure semantics。 |
| Formal owner | Consuming application Repository Port + Repository Service wire contract；Phase 2 plan 负责 conformance composition。 |
| Reopen condition | Local 无法在不复制 service semantics 的前提下实现，或 accepted deployment 不再允许 remote service boundary。 |

### P2-R1-D07 — Single logical service and durable-state boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D07` |
| Topic | Deployment/runtime ownership |
| Status | `SUPERSEDED` |
| Decision | 每个 backend environment 使用一个逻辑 Repository Service endpoint；一个 disposable container/process 同时独占一个 trust-domain durable storage root，并在内部管理多个 `RepositoryId`。进程是 runtime/composition boundary，不是独立 lower service API；禁止 active-active、共享 writable volume、任意 path/hot-load。 |
| Rationale | Registry、journal、idempotency、authorization policy 和 recovery evidence 需要单一 authority；容器仍可通过挂载同一 durable root 串行替换和恢复。 |
| Rejected alternatives | 每项目一个动态容器：拒绝，需 backend routing/sharding control plane；共享 volume 多副本：拒绝，缺少 distributed ownership/fencing；独立 Dolt container：被首版边界排除。 |
| Constraints | Repository Service 不理解业务 Project；project 只映射为 opaque RepositoryId。Secrets 与 trust roots 由 deployment 注入，不随 repository metadata 复制。 |
| Downstream impact | 约束 registry/storage layout、startup/reconciliation、Compose、backup/restore、routing 和 environment identity。 |
| Formal owner | Phase 2 deployment design / Repository Service ownership contract。 |
| Reopen condition | Accepted capacity evidence要求 repository sharding，且 shared control-plane/routing/fencing 已单独设计。 |
| Superseded by | `P2-R1-D10` |

### P2-R1-D08 — Per-repository concurrency

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D08` |
| Topic | Node concurrency and writer scope |
| Status | `SUPERSEDED` |
| Decision | Single writer serialization 的 scope 是 `RepositoryId`，不是全局 task。不同 repository 的 read/write 可在 bounded node budget 内并发；同 repository read 绑定 immutable commit，可与 write 并发；同 repository write effect 串行。禁止全局单任务锁和无界并行。 |
| Rationale | 同时满足 ref/CAS 正确性和多项目资源利用；只把必要的 external-effect critical section 串行化。 |
| Rejected alternatives | 全局串行：拒绝，资源利用和并发能力不足；无界跨 repository 并发：拒绝，缺少背压和容量控制。 |
| Constraints | 具体 lease/fencing 在 Round 5；worker/resource 数值在 Round 8/9；GC/write 协调在 Round 7。 |
| Downstream impact | 影响 operation queues、resource admission、Dolt lifecycle、metrics、load/failure tests 和未来 sharding。 |
| Formal owner | Repository Service concurrency/effect contract；Phase 2 plan。 |
| Reopen condition | Dolt/runtime 证据证明跨 repository 并发不安全，或 accepted capacity target 需要进一步分片。 |
| Superseded by | `P2-R1-D11` |

### P2-R1-D09 — First-version artifact storage

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D09` |
| Topic | External object storage |
| Status | `ACCEPTED` |
| Decision | Phase 2 首版不引入真实外部对象存储；使用 Repository Service-owned staging/artifact storage 配合 bounded HTTP upload/download，并保留未来 owner-specific storage adapter 边界。 |
| Rationale | 当前没有对象存储 authority、凭据或可用性需求；本地持久边界已足以验证完整 import/export/recovery。 |
| Rejected alternatives | 首版 S3-compatible store：拒绝为无当前 consumer 的额外外部依赖；client host path：被 formal 禁止。 |
| Constraints | Staging/artifact 必须有 digest、size、media type、lifecycle、cleanup 和 backup boundary；不得创建无 consumer 的通用 provider framework。 |
| Downstream impact | 影响 upload/download contract、volume、cleanup、security limits、backup closure 和 future adapter seam。 |
| Formal owner | Repository Service storage/artifact infrastructure design；相关 artifact owner contract。 |
| Reopen condition | Deployment requirement 明确需要跨节点 artifact transfer，或容量/持久性证据要求外部对象存储。 |

### P2-R1-D10 — Durable aggregate with independent table stores

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D10` |
| Topic | Deployment/runtime ownership after CurrentTableStore amendment |
| Status | `ACCEPTED` |
| Decision | 每个 backend environment 仍使用一个逻辑 Repository Service endpoint；一个 disposable active container/process 独占一个 trust-domain durable root，并管理多个 RepositoryId。每个 RepositoryId 的 durable aggregate 包含独立的 VersionedTableStore/Dolt、按需创建的 CurrentTableStore/current database、technical control store 和 staging/artifacts。Current table data 与 technical registry 必须分离。Repository lifecycle、backup inventory、quota 和 deletion 识别全部组件，但不声明 Dolt/current 是一致快照。 |
| Rationale | 保持已确认的单 active owner 和可替换容器边界，同时把 caller data、技术控制事实及 artifacts 的生命周期和权限清晰分离。 |
| Rejected alternatives | 所有 repository 共用一个 current SQLite 数据库：形成共享 writer/failure domain；CurrentTableStore 独立服务：首版增加第二套路由、认证、部署和恢复；每项目动态容器：需要未设计的 sharding control plane。 |
| Constraints | 禁止 active-active、共享 writable volume、任意 path/hot-load。Project 只映射为 opaque RepositoryId；secrets/trust roots 由 deployment 注入。Full backup 可包含全部组件，但不提供 cross-store semantic consistency guarantee；精确 backup/restore contract 在 Round 4/9 固定。 |
| Downstream impact | 约束 registry/storage layout、SQLite 与 technical DB separation、startup/reconciliation、Compose、backup/restore、quota、deletion、metrics 和 tests。 |
| Formal owner | Phase 2 deployment/storage design；Repository Service ownership contract。 |
| Reopen condition | Accepted capacity/availability requirement 需要 repository sharding 或独立 CurrentTableStore service，且 routing/fencing/control-plane 已单独设计。 |
| Supersedes | `P2-R1-D07` |

### P2-R1-D11 — Per-store writer and bounded node concurrency

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D11` |
| Topic | Writer serialization after CurrentTableStore amendment |
| Status | `ACCEPTED` |
| Decision | Semantic writer serialization scope 为 `(RepositoryId, StoreKind)`。同 repository 的 VersionedTableStore writes 串行；同 repository 的 CurrentTableStore writes 串行；两种 store 的 writes 可彼此并发，因为不存在 cross-store transaction/consistency。Dolt read 绑定 immutable CommitId，current read 绑定稳定 CurrentGenerationId，均可与各自后续 write 并发。不同 repository operations 在 bounded node budget 内并发。 |
| Rationale | 只序列化各存储引擎真正的 mutation critical section；避免无一致性收益的跨 store lock，同时保持 Dolt CAS 与 SQLite single-writer correctness。 |
| Rejected alternatives | RepositoryId 全局 writer lock：降低并发且不增加跨 store correctness；所有 repository 全局串行：资源利用过低；SQLite table-level concurrent writers：与单 database writer domain 不符；无界并行：缺乏背压。 |
| Constraints | Resource admission 可限制同 repository 或全节点 CPU/memory/IO，但不构成 cross-store semantic lock。Lease/fencing/idempotency 在 Round 5；GC/write 协调在 Round 7；并发数值在 Round 8/9。 |
| Downstream impact | 影响 per-store operation queues、leases、SQLite transaction boundary、Dolt lifecycle、resource admission、metrics、load/failure tests 和 future sharding。 |
| Formal owner | Repository Service concurrency/effect contract；Phase 2 plan。 |
| Reopen condition | Measurement 证明并行 store writes 对共享 disk/Dolt runtime 不安全，或 accepted current workload 需要超出 SQLite single-writer 能力。 |
| Supersedes | `P2-R1-D08` |

### P2-R1-D12 — Common service workload envelope with store-specific profiles

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D12` |
| Topic | Versioned/current workload and SLA boundary |
| Status | `ACCEPTED` |
| Decision | Repository Service 两种 store 共享 table-oriented、bulk-capable、bounded resource、single writer per `(RepositoryId, StoreKind)`、streaming read、typed mutation、无任意 SQL/跨表或跨 store transaction 的 workload envelope；store profile 保持不同：VersionedTableStore 面向 async bulk import/commit/ref/CAS 和 immutable history read，CurrentTableStore 面向 async bulk replace 加 bounded row/field mutation 和 latest-generation read。两侧不承诺相同 mutation capability或写延迟。 |
| Rationale | 统一 admission/transport/observability 以控制系统复杂度，同时尊重 Dolt versioning 与 SQLite current-state 的物理和语义差异，避免强迫 Dolt承担 OLTP或阉割 current 的小型更新能力。 |
| Rejected alternatives | 两侧完全相同 CRUD/concurrency/SLA：忽略引擎语义；把 CurrentTableStore 扩成高并发 OLTP：超出 SQLite/single-writer和本服务边界；完全分离资源治理：无法保护共享节点。 |
| Constraints | 当前没有高频 concurrent transaction、cross-table transaction、任意 index/query management 或极低延迟 OLTP承诺。Small current mutation 的 sync/async边界仍在 cross-round audit裁决；精确容量/SLO在 Round 8/9。 |
| Downstream impact | 约束 admission、queues、SQLite suitability、Dolt/current API、benchmarks、resource budgets、metrics 和 acceptance profiles。 |
| Formal owner | Repository Service workload/deployment contract；Phase 2 plan。 |
| Reopen condition | Accepted workload 需要高并发小事务、跨表事务或统一 store SLA，并提供容量与延迟要求。 |

### P2-R1-D13 — Repository-and-action authorization boundary

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D13` |
| Topic | Authorization granularity |
| Status | `ACCEPTED` |
| Decision | v1 authorization scope 为 `CallerIdentity × RepositoryId × Action`，action至少区分versioned/current read/write、artifact read、repository create、GC plan/execute及operator repair/delete。Repository Service不实现table/column/row ACL；最终用户、业务角色和数据级权限由backend/application owner执行。Operator actions与普通backend/worker actions分离；auth disabled仍只允许explicit dev/test。 |
| Rationale | Repository/action scope满足项目隔离和least privilege，又不要求通用数据服务理解业务字段/行语义或复制用户权限系统。 |
| Rejected alternatives | Table ACL：引入policy lifecycle/rename/drop；row/column ACL：耦合业务语义；只认证不授权：无法隔离RepositoryId/action。 |
| Constraints | Production无provider/config fail closed；所有route/stream/artifact必须在打开provider资源前完成authorization。具体credential/provider与existence-hiding在Round 8。 |
| Downstream impact | 约束security policy、route action registry、CallerIdentity、operator tooling、audit、negative tests和metrics。 |
| Formal owner | Repository Service security/wire contract；Phase 2 security design。 |
| Reopen condition | Accepted requirement需要service-owned table/data ACL，并能定义policy authority、migration、cache和audit。 |

### P2-R1-D14 — Audit metadata and sensitive-data minimization

| 字段 | 值 |
| --- | --- |
| ID | `P2-R1-D14` |
| Topic | Audit and diagnostic data boundary |
| Status | `ACCEPTED` |
| Decision | Audit默认只记录caller、RepositoryId、store/action/table metadata、request/operation identity、idempotency/input/artifact/query digest、before/after commit或generation、row/byte counts、result failure/effect与timing。禁止普通日志记录row/patch values、filter literals、artifact bytes、credentials、server/SQLite/Dolt path、SQL/CLI command或stack trace。Query记录normalized options digest。需要数据级debug evidence必须通过受控operator tooling、显式retention和sanitization。 |
| Rationale | Effect reconciliation和安全审计需要稳定metadata，但复制业务数据/查询字面量会扩大敏感数据、retention和泄漏面。 |
| Rejected alternatives | 记录完整request body：敏感数据风险；只记request/status：无法reconcile和审计；生产随时开启raw debug：绕过治理。 |
| Constraints | Digest不得可逆包含secret；diagnostic refs遵守authorization/retention。精确log fields与redaction tests在Round 8/9。 |
| Downstream impact | 约束logging、tracing、FailureDescriptor sanitization、operator evidence、retention、security tests和incident流程。 |
| Formal owner | Repository Service security/observability contract。 |
| Reopen condition | Regulatory/incident requirement需要更细数据审计，并提供加密、访问控制、retention和purpose limitation。 |

### P2-R2-D01 — Public identifier model

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D01` |
| Topic | Repository public identities and lifecycle |
| Status | `ACCEPTED` |
| Decision | `RepositoryId`、`RepositoryOperationId`、`ArtifactId` 使用 server-generated canonical lowercase UUIDv7，调用方只按 opaque value 比较和传递，resource 删除或过期后 ID 永不重用。`CommitId` 是 repository-scoped provider-generated opaque token；formal signature 沿用 `commit_hash` 字段时仍不得解析其格式。`IdempotencyKey` 是独立的 client-generated opaque value，不与 server identity 混用。 |
| Rationale | 稳定 typed identity 防止业务名称、host path 和 provider encoding 泄漏；UUIDv7 为 registry/index 提供局部性，同时不把其中时间信息提升为客户端 contract。 |
| Rejected alternatives | 全部 UUIDv4：可行但失去局部性；caller-assigned human-readable RepositoryId：拒绝，因冲突、重命名和业务信息泄漏；把 Dolt/path identity 直接暴露为公共资源 ID：拒绝。 |
| Constraints | Field type 确定 identity category；客户端不得从 UUID 或 commit token 推断创建时间、排序、provider 或 storage location。Artifact retention、operation retention 与 idempotency retention 分别在 Round 7/5 裁决。 |
| Downstream impact | 约束 wire DTO、SDK type、registry schema、日志脱敏、URL validation、fixture 和 migration。当前-store extension 如新增 resource identity，必须复用同一 opaque-ID 原则或建立独立 typed identity。 |
| Formal owner | Repository Service wire contract；Repository identity/schema contract。 |
| Reopen condition | 安全边界禁止暴露 time-ordered identifier，或 accepted persistence/provider constraint 无法可靠生成 UUIDv7。 |

### P2-R2-D02 — Ref and immutable-ref resource model

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D02` |
| Topic | Ref naming, binding and lifecycle |
| Status | `ACCEPTED` |
| Decision | `RefName` 是 caller-selected、case-sensitive、受限 ASCII 分段名称，不属于 opaque server ID；禁止空段、`.`、`..`、控制字符、反斜杠和内部保留 namespace。Ref 只能指向同 repository commit；mutable ref 只能通过 `CompareAndSetRef` 移动。Immutable ref 创建后不得改绑；删除后同名 immutable ref 也不得绑定另一 commit。`ResolveRef` 返回 ref kind 与 resolved immutable commit，不创建 server-side session。 |
| Rationale | 将人类可读 selector 与 immutable identity 分离，使 CAS、manifest、cache 和审计绑定稳定，并避免进程内 session 成为一致性前提。 |
| Rejected alternatives | Branch/tag 各自形成完整 API family：首版重复 contract；所有 ref 可变且 immutable 只靠 caller 约定：无法提供可靠绑定；大小写折叠或隐式 normalization：产生跨平台歧义。 |
| Constraints | Commit 本身不可变；后续读请求显式绑定 resolved commit。精确长度、段数和保留词在 Round 8 固定。 |
| Downstream impact | 约束 Resolve/Create/Delete/CAS API、tombstone/registry、GC reachability、cache key、SDK convenience `open_ref()` 和 conformance tests。Current-only table 不得复用 commit/ref 术语伪装版本语义。 |
| Formal owner | Repository Service RepositoryId/Ref/Commit wire contract；GC contract。 |
| Reopen condition | Provider 对名称的更严格限制必须进入公共 grammar，或 immutable-name tombstone 的 accepted retention/capacity 证据不可承受。 |

### P2-R2-D03 — Explicit HTTP operation surface

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D03` |
| Topic | Public HTTP resource and action model |
| Status | `ACCEPTED` |
| Decision | v1 使用 direct-resource `GET` 与 operation-specific action `POST`：repository、commit、repository operation 可直接 GET；ResolveRef、GetCatalog、StreamTableRows、ExportTable、DiffRefs、SubmitImport、ref mutations 与 GC 使用 `/v1/repositories/{repository_id}/actions/{operation-name}` 的独立封闭 schema。禁止 generic `/execute`、任意 command bag 和通用 SQL endpoint。`SubmitImport` 与 `ExecuteGarbageCollection` 接受后返回 `202 + RepositoryOperationId`；`GetOperation` 是异步状态、结果和 failure 的权威查询入口。 |
| Rationale | 显式 action 保留 use-case schema、鉴权、幂等、审计和兼容边界，又避免把 CAS/diff/resolve 强行伪装成不自然 CRUD。 |
| Rejected alternatives | 全量 CRUD resource graph：对 CAS、diff、resolve 和 GC 语义不自然；generic command endpoint：破坏 schema 演进、鉴权和可观测性；公开 SQL：越过通用能力与安全边界。 |
| Constraints | 每个 operation 独立 versioned request/response；已接受异步 operation 的终态失败通过 `GetOperation` representation 表达，不重新映射为普通 HTTP 500。Export/Diff 的具体 stream 或 artifact 返回方式留给 Round 3。 |
| Downstream impact | 固定 HTTP router、OpenAPI/SDK、authorization action、operation mapping、contract tests 和 observability dimensions。Current-store extension 必须新增显式 typed actions，不得借扩展重新引入 generic SQL/execute。 |
| Formal owner | Repository Service wire contract；HTTP interface contract。 |
| Reopen condition | Accepted client/tooling requirement 证明 action surface 无法生成或兼容，或新增资源具有独立生命周期并更适合稳定 resource URI。 |

### P2-R2-D04 — Success schemas, cursor, deadline and cancellation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D04` |
| Topic | Common interaction controls |
| Status | `ACCEPTED` |
| Decision | 成功响应采用 endpoint-specific closed schema，不使用全局 `data/error` envelope，并携带 `wire_schema_version`。Request ID、trace context、deadline 使用 HTTP metadata；业务参数与 `idempotency_key` 位于 versioned body。Control pagination 使用 opaque cursor，并绑定 RepositoryId、immutable CommitId、query/options digest 与 schema version。Deadline、断连或取消会停止未接受的读取并 cleanup；mutation 一旦返回 operation ID，断连只停止等待，不取消 durable operation。v1 不提供 `CancelOperation`，调用方使用 `GetOperation` reconcile。 |
| Rationale | Endpoint-specific schema 避免无类型 envelope；snapshot-bound cursor 防止跨 commit 漂移；把 transport cancellation 与 durable effect 分离可避免误判为安全重试。 |
| Rejected alternatives | 全局 data/meta envelope：增加 streaming 和 schema 映射负担；body 承载所有 transport metadata：削弱基础设施互操作；server-side pagination/session state：违反 disposable process 和 immutable binding。 |
| Constraints | Cursor 不可解析、修改或跨 binding 重用；具体 token protection、TTL、page/chunk 上限在 Round 3/8 固定。没有明确 `NOT_APPLIED` evidence 时不得因 timeout/断连 blind replay mutation。 |
| Downstream impact | 约束 DTO、headers、cursor codec、stream cleanup、operation polling、timeout tests、SDK retry policy 和 load shedding。Current-only reads 若分页，必须绑定可稳定识别的 current snapshot/generation，不能错误复用 CommitId binding。 |
| Formal owner | Repository Service wire/timeout contract；HTTP interface contract；相关 operation recovery contract。 |
| Reopen condition | Current-store extension 证明无法提供稳定 current snapshot/generation 且产品明确接受弱分页语义，或 accepted cancel use case 需要独立 journaled CancelOperation。 |

### P2-R2-D05 — Problem details and failure compatibility

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D05` |
| Topic | HTTP error envelope and compatibility |
| Status | `ACCEPTED` |
| Decision | HTTP error 使用 `application/problem+json` 基础字段 `type/title/status/detail/instance`，并扩展 formal `FailureDescriptor.code/category/phase/recovery/effect/details/diagnostic_refs`、`request_id` 与 `wire_schema_version`。`detail` 仅供人阅读；`category/recovery/effect` 是机器处理 authority，HTTP status 不决定 retry 或 effect。新增可选字段和 owner-versioned stable code 可 additive 演进；改变既有 code、公共 enum 或 recovery/effect 含义属于 breaking。未知字段须忽略；未知 code 可按已知公共维度降级；未知 recovery/effect 必须 fail closed 且不得自动重放 mutation。 |
| Rationale | RFC Problem Details 提供标准 HTTP surface，同时保留正式 effect/recovery contract；客户端无需解析 message 或从 status 猜测外部 effect。 |
| Rejected alternatives | 只返回自定义 FailureDescriptor：失去标准 media type/tooling；只返回 status + text：无法表达 UNKNOWN/APPLIED 和 reconcile authority；为所有服务建立单一业务 ErrorCode registry：违反 use-case owner 边界。 |
| Constraints | Interface 可为安全调整 message/details，但不得改变 application code/recovery/effect；不得泄漏 stack、server path、Dolt command、SQLite path 或凭据。已接受 operation 的执行 failure 保存在 operation representation；直接 problem response 表示请求未被接受或 interface failure。 |
| Downstream impact | 固定 HTTP exception mapping、SDK fallback、retry/reconcile、sanitization、failure fixtures 和 N/N-1 compatibility tests。Current-store extension 必须复用公共 failure primitive并由其 use-case owner定义 stable code/phase/details。 |
| Formal owner | Repository Service wire error contract；Shared Kernel FailureDescriptor；HTTP interface contract。 |
| Reopen condition | Formal FailureDescriptor 公共维度改变，或 HTTP transport 被正式替换且不再需要 Problem Details mapping。 |

### P2-R2-D06 — Explicit independent store routing

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D06` |
| Topic | Versioned/current store selection and routing |
| Status | `ACCEPTED` |
| Decision | Public API 将 VersionedTableStore 与 CurrentTableStore 暴露为显式、独立的 typed operation families；caller 在每次调用中选择 store，并在自己的 owner contract 保存 table persistence policy。Repository Service 不保存或解释该 policy，不提供按 table name 自动选路的统一读写接口。 |
| Rationale | 显式路由使 authority 和 orchestration 留在 caller，避免服务因隐式 policy 演化、配置漂移或名称冲突写错存储。 |
| Rejected alternatives | Repository Service 持有 policy 并自动 routing：引入新的业务 truth 与 migration contract；统一 `Get/WriteTable` 猜测位置：两侧同名时语义不确定；要求每 repository 只能使用一种 store：不满足需求。 |
| Constraints | 两个 operation family 共享 RepositoryId/security/transport conventions，但使用独立 request、idempotency、operation、cursor/snapshot identity 和 error code owner。 |
| Downstream impact | 新增 CurrentTableStore port/wire schema/SDK actions；application adapter 负责 persistence policy 与显式 route；authorization、metrics 和 fixtures 必须按 store/action 区分。 |
| Formal owner | Repository Service wire contract；caller Application Repository Port。 |
| Reopen condition | Accepted product requirement 要求 server-owned persistence policy，且 policy lifecycle、migration、authority 和 recovery 已单独设计。 |

### P2-R2-D07 — Independent table inventory and same-name coexistence

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D07` |
| Topic | Catalog semantics across stores |
| Status | `ACCEPTED` |
| Decision | 同一 RepositoryId 下允许同名表分别存在于 VersionedTableStore 与 CurrentTableStore，内容可不同。Inventory/catalog 按 store 分别报告 `table_name`、`store_kind`、`exists`、schema identity，以及适用的 CommitId 或 CurrentGenerationId；两侧存在时返回独立 entry，不合并为一张逻辑表，不报告 authority、synchronized 或 equivalent。 |
| Rationale | 满足 caller 有意保存两份的场景，同时防止 catalog 输出虚假的关联或一致性承诺。 |
| Rejected alternatives | 禁止同名：不满足明确需求；按名称合并并选择优先级：产生隐式 routing/authority；由服务比较两侧内容：引入昂贵且无 owner 的一致性语义。 |
| Constraints | `store_kind` 是公共 closed enum；inventory 不返回 server/SQLite/Dolt path。跨 store join、diff 和统一 pagination 不属于 v1。 |
| Downstream impact | 约束 catalog DTO、SDK key、authorization filters、UI/operator display、backup inventory 和 catalog conformance tests。 |
| Formal owner | Repository Service wire/catalog contract。 |
| Reopen condition | Caller 需要受 contract 管理的逻辑-table identity 跨 store 关联，并能定义唯一 authority 与 lifecycle。 |

### P2-R2-D08 — Typed CurrentTableStore API

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D08` |
| Topic | Current-table public operations |
| Status | `SUPERSEDED` |
| Decision | v1 CurrentTableStore 提供显式 typed operations：CreateCurrentTable、GetCurrentCatalog、ReplaceCurrentTable、UpsertCurrentTableRows、DeleteCurrentTableRows、StreamCurrentTableRows、DropCurrentTable。Schema、key、projection、predicate 和 row payload 使用 versioned DTO/artifact/stream contract；禁止 arbitrary SQL、arbitrary DDL、PRAGMA、extension loading 和直接数据库连接/文件访问。 |
| Rationale | Typed surface 覆盖 latest-only table 的必要 CRUD/bulk 能力，同时维持鉴权、配额、schema evolution、注入防护和跨 client 兼容。 |
| Rejected alternatives | 只允许全表 replace：过度限制增量 current workload；公开任意 SQL/DDL：扩大安全与兼容边界并把服务变成数据库代理；复用 Dolt import/ref API：混淆版本与 current semantics。 |
| Constraints | 精确 scalar/schema encoding、filter grammar、batch limits、stream format、DDL subset 和 sync/async threshold 在 Round 3/4/8 裁决；所有标识符经公共 grammar 校验和参数化执行。 |
| Downstream impact | 扩展 wire/API/SDK、current store adapter、artifact ingestion、error registry、security tests、resource limits 和 acceptance fixtures。 |
| Formal owner | CurrentTableStore wire contract；HTTP interface contract；Phase 2 plan。 |
| Reopen condition | Accepted workload 证明 typed operations 无法表达必要查询/transaction，或决定只支持 replace-only 更小 surface。 |
| Superseded by | `P2-R2-D16` |

### P2-R2-D09 — No v1 convenience dual-write

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D09` |
| Topic | Cross-store convenience operation |
| Status | `ACCEPTED` |
| Decision | v1 不提供同时写 VersionedTableStore 与 CurrentTableStore 的 convenience/composite API。Caller 发起两个独立请求并拥有 orchestration、一致性判断和恢复策略；服务不生成 aggregate success，也不隐藏 partial outcome。 |
| Rationale | 即使声明非原子，server-side dual-write 仍需 composite operation identity、per-leg idempotency、timeout reconciliation 和 PARTIAL 终态，会重新引入已排除的协调器复杂度。 |
| Rejected alternatives | Best-effort 双写并返回单一 boolean：会掩盖 partial effect；跨引擎 transaction：Dolt/SQLite 无共同 atomic commit；v1 composite operation：没有足够 consumer evidence 支持其 recovery 成本。 |
| Constraints | 两个独立调用各自遵守正式 failure/effect/idempotency contract。Caller 不得把第一个成功推断为第二个成功；重试必须使用各自 key/evidence。 |
| Downstream impact | 避免新增 composite journal/API/tests；application port/use case 负责需要的双调用编排和业务 outcome。 |
| Formal owner | Repository Service non-goals / wire contract；caller Application owner。 |
| Reopen condition | Accepted use case 反复需要 server-side orchestration，并已定义 per-leg result、PARTIAL、reconciliation、idempotency 与 cancellation contract。 |

### P2-R2-D10 — Current generation and repository-scoped concurrency

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D10` |
| Topic | Current state identity, isolation and optimistic concurrency |
| Status | `ACCEPTED` |
| Decision | CurrentTableStore 以 RepositoryId 为 logical isolation/writer scope，并使用 opaque `CurrentGenerationId` 表示可读取的当前状态 revision；它只支持 equality/CAS binding，不提供历史读取或版本语义。Mutation 可携带 `expected_generation` 防止 lost update；read cursor/stream 必须绑定稳定 generation。首版 storage 采用每 RepositoryId 独立 current SQLite database 的方向，禁止所有 repository 共用一个 SQLite writer domain。 |
| Rationale | Generation token 为 timeout reconciliation、optimistic concurrency、stable pagination 和 cache invalidation 提供最小 identity；per-repository SQLite 保持跨 repository 并发并与已确认隔离边界一致。 |
| Rejected alternatives | 无 generation 的 live pagination：会产生重复/遗漏与 lost update；复用 CommitId：错误暗示版本历史；所有 repository 共用一个 SQLite file：把 writer lock 扩大为全局瓶颈。 |
| Constraints | CurrentGenerationId 不可用于读取旧 generation；exact generation granularity（repository/table）、SQLite schema/file layout、transaction scope、WAL/checkpoint 与 backup 在 Round 1 impact check、Round 3/4/5 固定。Public contract 不返回 SQLite path。 |
| Downstream impact | 约束 current DTO、cursor、CAS、idempotency、cache key、storage layout、concurrency/lease、backup、metrics 和 tests。 |
| Formal owner | CurrentTableStore identity/concurrency contract；storage design；Phase 2 plan。 |
| Reopen condition | Accepted workload 需要同 repository 多 writer 并发且 SQLite measurement 不满足，或 generation granularity 无法支持所需 atomic batch。 |

### P2-R2-D11 — CurrentTableStore minimum public operation set

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D11` |
| Topic | CurrentTableStore public API surface |
| Status | `SUPERSEDED` |
| Decision | v1 public contract 包含 cross-store `GetTableInventory`，以及独立的 `GetCurrentCatalog`、`GetCurrentTable`、`StreamCurrentTableRows`、`ExportCurrentTable`、`CreateCurrentTable`、`ReplaceCurrentTable`、`UpsertCurrentTableRows`、`DeleteCurrentTableRows`、`DropCurrentTable`；current mutation 复用通用 `GetOperation` 查询结果。禁止 generic `QueryCurrentDatabase`、SQL endpoint、跨表 join 与 cross-store query。 |
| Rationale | 该 surface 覆盖 table discovery、descriptor、bulk/incremental mutation、stream/export 和 lifecycle，同时保持每个 use case 的 schema、鉴权和恢复边界。 |
| Rejected alternatives | 只支持 create/replace/stream/drop：不能满足增量 latest-only workload；通用 query/SQL：把服务扩张为数据库代理；复用 VersionedTableStore ref/commit API：混淆 current semantics。 |
| Constraints | 每个 operation 使用显式 store-specific versioned DTO；GetTableInventory 只报告独立 presence/identity，不进行 routing、join 或 consistency inference。 |
| Downstream impact | 固定 HTTP routes、OpenAPI/SDK、CurrentTableStore port、authorization actions、operation result types、fixtures 和 Round 3 read/export design。 |
| Formal owner | CurrentTableStore wire contract；HTTP interface contract；Phase 2 plan。 |
| Reopen condition | Accepted workload 证明增量 mutation 不需要，或需要新的独立-lifecycle current resource/use case。 |
| Superseded by | `P2-R2-D17` |

### P2-R2-D12 — Durable asynchronous current mutations

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D12` |
| Topic | Current mutation acceptance and completion model |
| Status | `SUPERSEDED` |
| Decision | Create/Replace/Upsert/Delete/Drop current table 均作为 durable async operation：请求接受后返回 `202 + RepositoryOperationId`，通过 `GetOperation` 返回 store-specific result 与新的 CurrentTableGenerationId/CurrentCatalogGenerationId。请求携带 idempotency key、适用的 expected generation、schema/input digest，以及 artifact 或 bounded row input。每个 operation 只 mutation 一张 current table。 |
| Rationale | 统一 acceptance/recovery model，避免 payload 大小时同步/异步 threshold 进入客户端 contract，并使 timeout/断连后的 effect 可通过 operation evidence 查询。 |
| Rejected alternatives | 小请求同步、大请求异步：客户端和兼容矩阵必须处理不稳定 threshold；全部同步：大表写入产生 timeout uncertainty；一个 operation mutation 多表：引入未要求的 transaction/generation 语义。 |
| Constraints | 接受前 rejection 直接返回 problem response；接受后 failure 进入 Operation representation。Mutation 不与 Dolt operation 合并，不提供 cross-store transaction。Inline row/input 上限在 Round 8 固定。 |
| Downstream impact | 约束 current operation journal、idempotency、result DTO、worker/queue、cancellation、recovery、metrics 和 crash tests。 |
| Formal owner | CurrentTableStore wire/operation contract；Round 5 journal design。 |
| Reopen condition | Accepted latency/capacity evidence证明所有 current mutation 都可安全同步，或明确需要 journaled multi-table operation。 |
| Superseded by | `P2-R2-D20` |

### P2-R2-D13 — Catalog and table generation identities

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D13` |
| Topic | Current snapshot and optimistic-concurrency granularity |
| Status | `ACCEPTED` |
| Decision | CurrentTableStore 使用两个 typed opaque UUIDv7 token：`CurrentCatalogGenerationId` 标识 table set/schema catalog revision；`CurrentTableGenerationId` 标识单表当前 schema+rows revision。建表、删表或 schema identity 变化更新 catalog generation；成功 replace/upsert/delete/schema replacement 更新 table generation。Mutation 使用 expected table generation CAS；stream/cursor 绑定 table generation。其他表写入不使当前表 cursor/CAS 失效。 |
| Rationale | 分离 catalog 与 per-table revision，既提供稳定 discovery 和 read binding，又避免 repository-global token 造成无关 invalidation。 |
| Rejected alternatives | 每 repository 单一 generation：任意表写入使全部 cursor/CAS 失效；无 generation：产生 lost update 与不稳定分页；复用 CommitId：错误暗示可查询历史。 |
| Constraints | Generation 只支持 equality/binding，不保证顺序，也不允许读取旧 generation。Schema replacement 同时影响相关 table generation 与 catalog generation；原子落盘方式留给 Round 4。 |
| Downstream impact | 固定 current descriptor、cursor、CAS、operation result、cache/ETag、catalog refresh、tests 和 observability。 |
| Formal owner | CurrentTableStore identity/wire contract。 |
| Reopen condition | Accepted transaction model 需要多表 snapshot/generation，或 measurement 证明 catalog/table 双 token 复杂度无收益。 |

### P2-R2-D14 — Current schema, key and replacement rules

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D14` |
| Topic | Current table schema and mutation eligibility |
| Status | `ACCEPTED` |
| Decision | CreateCurrentTable 必须提供 versioned typed `TableSchema`；primary key 可选。Keyless table 只允许 replace/stream/export/drop；Upsert/Delete 只适用于有 primary key 的表，Delete v1 只接受显式 key 或 bounded key artifact。Upsert 不改变 schema；v1 不提供 AlterCurrentTable。Schema 变化通过带 expected generation 的 ReplaceCurrentTable 原子替换 schema 与全部 rows。 |
| Rationale | 保留 keyless imported table 支持，同时使增量 mutation、冲突和删除语义可验证；用 full replacement 收口 schema migration，避免通用 DDL surface。 |
| Rejected alternatives | 强制所有表有 primary key：排除合法 keyless 数据；任意 predicate delete：删除范围难以审计和限额；通用 ALTER TABLE：扩大 migration/compatibility contract；upsert 隐式扩 schema：不可预测。 |
| Constraints | TableSchema/scalar encoding 必须 versioned；Replace 的 schema+rows 在 CurrentTableStore 内是单 operation outcome，不涉及 Dolt。Key、column 和 table grammar/limits 在 Round 4/8 固定。 |
| Downstream impact | 约束 DTO、SQLite DDL/transaction adapter、artifact validation、operation codes、schema digest、fixtures 和 migration tests。 |
| Formal owner | CurrentTableStore schema/mutation contract；SQLite adapter design。 |
| Reopen condition | Accepted workload 要求在线 schema evolution、keyless incremental mutation 或 predicate delete，并有明确 safety/compatibility contract。 |

### P2-R2-D15 — Bounded typed current reads

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D15` |
| Topic | Current read/query capability boundary |
| Status | `ACCEPTED` |
| Decision | StreamCurrentTableRows 支持 projection、optional versioned typed bounded filter、optional explicit order、opaque cursor 和 CurrentTableGenerationId binding；不接受 SQL text，不支持 JOIN、GROUP BY、aggregate、subquery 或 user function。无 explicit order 时不承诺 row order。精确 filter grammar、ordering、cursor/chunk 与 wire format由 Round 3裁决。 |
| Rationale | 提供常见 selective read 并减少无效 IO，同时避免把 CurrentTableStore 提升为通用 SQL/query engine。 |
| Rejected alternatives | 只允许全表 stream：造成明显 IO 放大；公开 SELECT SQL：扩大注入、资源、兼容和 planner contract；跨表/cross-store query：违反独立 store ownership。 |
| Constraints | Filter AST、projection 和 order 是 versioned DTO；cursor 必须绑定 table generation、schema、query/options digest。具体复杂度和资源上限在 Round 3/8 固定。 |
| Downstream impact | 约束 Round 3 read consistency、cursor codec、SQLite query compiler、authorization/resource limits、SDK、cache 和 conformance tests。 |
| Formal owner | CurrentTableStore wire/read contract；HTTP data-plane contract。 |
| Reopen condition | Accepted workload 需要 aggregate/join，或 typed filter 实现与安全成本高于全表 stream 的测量收益。 |

### P2-R2-D16 — Closed Current TableMutationBatch and no versioned row mutation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D16` |
| Topic | Row/field mutation vocabulary and versioned-store scope |
| Status | `ACCEPTED` |
| Decision | CurrentTableStore 使用 closed single-table `TableMutationBatch`，variant 为 `InsertRow`（full row）、`UpdateFields`（primary key + field mask + values）、`UpsertRow`（full row）和 `DeleteRow`（primary key）。Field mask 区分 omitted 与 explicit NULL；primary key 不得由 UpdateFields 修改，改 key 使用 Delete+Insert。只有有 primary key 的 current table 可使用 row mutation；keyless table 仅支持 replace/read/export/drop。VersionedTableStore v1 不提供行/字段 mutation，只保留 canonical full import/replace；不为接口对称提前暴露 SubmitVersionedTableMutations。 |
| Rationale | 满足 current latest-state 的行级/字段级需求并消除 sparse/full-row歧义，同时保持 Dolt 已有 full canonical import、commit/readback/CAS主线，避免无 consumer 的版本化增量写复杂度。 |
| Rejected alternatives | Upsert 同时表示 sparse patch：NULL/omitted歧义；任意 predicate/SQL update：扩大安全/query contract；为了对称给 Dolt 增加 row mutation：没有实际用例且扩张 Round 5。 |
| Constraints | Batch 只针对一张表；exact atomicity、duplicate/missing-key behavior 与 sync/async completion在 cross-round audit继续裁决。共享 mutation payload 不等于共享 store outcome。 |
| Downstream impact | 扩展 current wire DTO/SDK/query validation/SQLite adapter/tests；明确 Dolt API和journal无需新增 incremental mutation路径。 |
| Formal owner | CurrentTableStore mutation contract；Repository Service non-goals；Phase 2 plan。 |
| Reopen condition | 出现明确 use case 需要直接修改已版本化表并形成 commit/ref/evidence，或 current row mutation不再需要。 |
| Supersedes | `P2-R2-D08` |

### P2-R2-D17 — CurrentTableStore operation surface after mutation-batch amendment

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D17` |
| Topic | CurrentTableStore public operation set |
| Status | `ACCEPTED` |
| Decision | v1 current surface 为 `GetCurrentCatalog`、`GetCurrentTable`、`StreamCurrentTableRows`、`ExportCurrentTable`、`CreateCurrentTable`、`ReplaceCurrentTable`、`ApplyCurrentTableMutations`、`DropCurrentTable`，并复用 `GetOperation`；cross-store仍有独立 `GetTableInventory`。原独立 UpsertCurrentTableRows/DeleteCurrentTableRows actions 由 closed ApplyCurrentTableMutations 取代。禁止 generic query/write command、SQL、join和cross-store operation。 |
| Rationale | 一个封闭 mutation endpoint 可在同一 table batch 中表达 insert/update/upsert/delete，而不产生四套重复 acceptance/idempotency contract；它仍是 typed use case，不是 generic command bag。 |
| Rejected alternatives | 每个 row variant 一个 endpoint：重复 schema与operation语义；保留独立 Upsert/Delete同时新增Apply：重叠能力；generic execute/query：失去类型和鉴权边界。 |
| Constraints | Apply 的 completion mode、atomicity和limits仍需审计确认；Replace 保持独立 bulk/schema-replacement operation。GetTableInventory不自动route。 |
| Downstream impact | 修改 HTTP routes、OpenAPI/SDK、authorization action、operation result、fixtures 和 current adapter。 |
| Formal owner | CurrentTableStore wire contract；HTTP interface contract。 |
| Reopen condition | 不同 mutation variant 需要实质不同授权/operation lifecycle，或 accepted client generation无法处理 tagged union。 |
| Supersedes | `P2-R2-D11` |

### P2-R2-D18 — Mandatory optimistic write preconditions and no force overwrite

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D18` |
| Topic | Cross-store lost-update protection |
| Status | `ACCEPTED` |
| Decision | 两侧 mutation 都必须绑定 caller observed state：Dolt import/ref mutation 使用 base CommitId 与 expected target CommitId/CAS；Current Replace/Apply/Drop 使用 expected CurrentTableGenerationId。CreateCurrentTable 断言名称不存在并用 idempotency key处理重试。v1 不提供 blind/force overwrite，也不把缺失 expected token解释为 force。GetCurrentTable 只返回 descriptor metadata，不读取全表；generation还由catalog/inventory和成功mutation result返回。 |
| Rationale | CAS 防止不同请求基于旧状态互相覆盖；idempotency只防同一请求重复，不能替代 lost-update protection。Metadata generation获取与表大小无关，且正常 workflow 可沿用前一结果。 |
| Rejected alternatives | Expected token optional：普通请求可能无意last-write-wins；独立ForceReplace：当前无必要高风险用例；通过读取全表判断冲突：成本高且仍有竞态。 |
| Constraints | Generation/commit check 必须与 mutation处于同一 atomic effect boundary。Mismatch 返回 typed STATE_CONFLICT，不产生数据 effect；具体 failure code/recovery在 Round 5/6对齐。 |
| Downstream impact | 约束 request DTO、client state、operation journal、SQLite transaction、Dolt CAS、authorization、audit和concurrency tests。 |
| Formal owner | Repository Service mutation/concurrency wire contract；Round 5 journal/CAS contract。 |
| Reopen condition | Accepted workflow明确需要 operator force overwrite，并单独定义 authorization、reason、audit、effect和recovery。 |

### P2-R2-D19 — Shared read abstractions with store-specific wire semantics

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D19` |
| Topic | Cross-store API unification boundary |
| Status | `ACCEPTED` |
| Decision | Application Port/SDK 共享 TableSchema/RepositoryLogicalType、projection/filter/order、framed Arrow/Parquet、ArtifactRef、FailureDescriptor及 discriminated `TableReadBinding = VersionedBinding(CommitId) | CurrentBinding(CurrentTableGenerationId)`；wire route、mutation command、snapshot token、result与recovery保持 store-specific。禁止用一个带 store_kind 的 generic Get/Write endpoint抹平 commit/ref 与 current generation语义。 |
| Rationale | 复用真正相同的 read/data-plane contract，降低 client/fixture重复；保留不同 write/effect模型，避免隐藏 routing和错误抽象。 |
| Rejected alternatives | 单一 generic Get/Write endpoint：语义分支和错误恢复隐蔽；两侧连 schema/query/stream DTO都完全复制：产生漂移；强制相同mutation API：忽略version/history差异。 |
| Constraints | Shared DTO不能包含 provider/path或store-only字段；store-specific binding必须closed/discriminated且fail closed。Local/Fake/Remote共享同一高层port，但production仍只Remote。 |
| Downstream impact | 约束 client package、DTO ownership、OpenAPI/SDK、adapter mapping、conformance suite和未来provider替换。 |
| Formal owner | Application Repository Port；Repository Service Versioned/Current wire contracts。 |
| Reopen condition | Generated client/tooling无法安全表达discriminated binding，或两种store的read semantics出现不可共享差异。 |

### P2-R2-D20 — Explicit synchronous small and asynchronous bulk current mutations

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D20` |
| Topic | Current mutation completion model |
| Status | `ACCEPTED` |
| Decision | Current mutation 使用caller-explicit双路径：`ApplyCurrentTableMutations` 接受严格 bounded inline TableMutationBatch，同步返回 `200 + CurrentTableGenerationId`；数据、generation与idempotency result在同一SQLite transaction提交，response丢失可用原key重取原结果。`SubmitCurrentTableMutationBatch` 接受ArtifactRef并返回 `202 + RepositoryOperationId`；Replace/Create/Drop/schema replacement保持async。禁止按隐藏size threshold让同一endpoint改变response type。 |
| Rationale | 小型row/field更新避免不必要polling，大型/破坏性操作保留durable operation与recovery；显式endpoint使client contract单义。 |
| Rejected alternatives | 全部async：单字段更新成本高；全部sync：大批量timeout uncertainty；同endpoint按size切换：行为随配置漂移。 |
| Constraints | Inline rows/bytes/deadline limits在Round 8固定。Sync mutation仍必须CAS、idempotent和crash-safe；bulk operation通过GetOperation。 |
| Downstream impact | 约束HTTP status/routes、client SDK、SQLite transaction/idempotency、operation journal、limits和timeout tests。 |
| Formal owner | CurrentTableStore wire/operation contract；Round 5 idempotency design。 |
| Reopen condition | Accepted workload不需要低延迟小mutation，或sync path无法与idempotency result原子持久化。 |
| Supersedes | `P2-R2-D12` |

### P2-R2-D21 — Atomic Current TableMutationBatch semantics

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D21` |
| Topic | Row mutation atomicity and conflict behavior |
| Status | `ACCEPTED` |
| Decision | 每个TableMutationBatch是single-table all-or-nothing transaction；任一schema/key/row/constraint错误使全batch失败且不改变rows/schema/generation。同一target primary key在batch内最多一次，重复直接拒绝。Insert existing、UpdateFields missing、Delete missing均为STATE_CONFLICT；UpsertRow是唯一同时接受existing/missing的variant。成功batch只产生一个新CurrentTableGenerationId。大型async batch保持相同外部原子性，可用staging/shadow实现。 |
| Rationale | 确定、可重试的batch语义避免输入顺序、partial progress和补偿状态进入公共contract。 |
| Rejected alternatives | 顺序执行同key多次：结果依赖ordering；逐行best effort：需要partial/resume/compensation；chunk commit：暴露中间generation。 |
| Constraints | Mutation、generation、idempotency/effect publication必须共享atomic boundary。Exact validation/error codes在Round 5/6；batch limits在Round 8。 |
| Downstream impact | 约束SQLite transaction/staging、operation result、client retry、failure codes、crash tests和capacity。 |
| Formal owner | CurrentTableStore mutation/transaction contract。 |
| Reopen condition | Accepted use case需要partial success，并能定义稳定per-row outcome、resume和compensation。 |

### P2-R2-D22 — Independently bound cross-store inventory

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D22` |
| Topic | GetTableInventory observation consistency |
| Status | `ACCEPTED` |
| Decision | GetTableInventory请求显式Versioned CommitId，并在独立CurrentTableStore read snapshot内取得CurrentCatalogGenerationId；响应分别携带versioned commit/catalog schema binding与current catalog generation，以及按store拆分的table presence/schema/CommitId或CurrentTableGenerationId。两侧不是atomic snapshot，不产生unified generation，不比较同名表schema/content。未物化current store返回有binding的empty catalog且不创建SQLite文件。 |
| Rationale | 可重现的独立bindings准确表达两个无协调store的观测点，避免“latest inventory”产生隐式一致性承诺。 |
| Rejected alternatives | 无binding读取两侧latest：不可重现；跨store锁：引入无必要coordination；合并同名表：隐藏store/authority。 |
| Constraints | Current旧catalog generation不可查询；caller需要更新时重读。响应不返回path/provider metadata。 |
| Downstream impact | 约束inventory DTO、SQLite/Dolt read transaction、catalog cache、SDK和concurrency tests。 |
| Formal owner | Repository Service inventory/wire contract。 |
| Reopen condition | Accepted requirement需要server-owned cross-store snapshot/consistency，并有coordination与recovery设计。 |

### P2-R2-D23 — Repository creation and operator-governed deletion

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D23` |
| Topic | Repository aggregate lifecycle |
| Status | `ACCEPTED` |
| Decision | CreateRepository是durable async operation，接收idempotency key并返回202 + RepositoryOperationId；完成后返回RepositoryId和初始Versioned state，创建technical control state与Dolt repository。CurrentTableStore逻辑可用但物理database首次current mutation时lazy-create；只读empty catalog不物化文件。v1普通backend/worker caller无直接DeleteRepository；repository删除由Round 7定义operator-authorized plan-before-execute lifecycle，覆盖dry-run、active-use检查、全部store/control/artifact删除、tombstone/audit和crash recovery；RepositoryId永不复用。 |
| Rationale | Async/idempotent create处理filesystem/provider partial effect；lazy current避免空资源；高风险aggregate deletion需要独立operator gate和recovery，而非普通业务CRUD。 |
| Rejected alternatives | Sync create：timeout/partial directory难reconcile；普通caller直接delete：扩大危险权限；eager current文件：产生未用migration/backup噪声；永不删除：不满足生命周期。 |
| Constraints | 精确delete plan/evidence/retention在Round 7；Create完成前repository不可接受普通操作。Secrets不进入aggregate。 |
| Downstream impact | 新增create operation result、repository provisioning state、lazy-store reconciliation、operator deletion plan、authorization/audit和failure tests。 |
| Formal owner | Repository Service lifecycle/wire contract；Round 7 GC/deletion design。 |
| Reopen condition | Deployment要求预配全部store，或业务caller必须自助删除并完成高风险authorization/recovery设计。 |

### P2-R2-D24 — Primary-key-only public indexing in v1

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D24` |
| Topic | CurrentTableStore indexes and relational constraints |
| Status | `ACCEPTED` |
| Decision | v1 public TableSchema只支持columns、nullability和optional primary key；不提供CreateIndex/DropIndex、secondary unique constraint或foreign key。Adapter可拥有generation/metadata等service-private indexes。PK equality/range可利用primary index；其他typed filter允许scan但受deadline、scan rows/bytes和admission限制。分析型读取优先stream/export；secondary index只在accepted measurement后以versioned typed SecondaryIndexSpec扩展。 |
| Rationale | 当前workload以bulk/PK mutation为主；提前开放index/constraint lifecycle会扩大schema digest、migration、quota和write-cost contract。 |
| Rejected alternatives | Caller-managed indexes：当前无性能证据且增加DDL；自动建索引：磁盘和行为不可预测；禁止非PK filter：过度限制读取。 |
| Constraints | Filter支持不等于性能保证；scan limits在Round 8，measurement/profile在Round 9/10。SQLite private indexes不得泄漏为public schema。 |
| Downstream impact | 约束TableSchema、SQLite DDL、query planner expectations、resource limits、docs和performance tests。 |
| Formal owner | CurrentTableStore schema/query contract；SQLite adapter design。 |
| Reopen condition | Accepted workload/benchmark证明稳定secondary filter是SLO必需且full scan不可接受。 |

### P2-R2-D25 — Capability discovery and contract version

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D25` |
| Topic | Deployment capability discovery and rollout |
| Status | `ACCEPTED` |
| Decision | `GetRepository` 返回当前 deployment 支持的 typed capability descriptors，首版至少覆盖 `versioned_tables/v1`、`current_tables/v1`、`current_mutation_batch/v1`、`framed_arrow_stream/v1`、`parquet_export/v1` 和 `repository_raw_diff/v1`。Capability 只声明服务部署能力，不声明某个 repository/table 的 caller persistence policy；因此 current SQLite 尚未物化时仍可报告 `current_tables/v1`。Client 只能调用自己理解且服务已声明支持的能力：未知 capability descriptor 可忽略，已知 capability 的未知 major 必须 fail closed。Rollout 保持 server-first；`/v1` 与各 endpoint wire schema 仍是 API compatibility authority，capability 不形成第二套 API version。Fake、Local、Remote 必须报告并验证同一语义 capability set，Fake 不得宣称自己未实现的能力。 |
| Rationale | 显式 discovery 可防止新 client 在 server 尚未支持时误用能力，又不把调用方的表存储选择错误地下沉为 Repository Service policy。 |
| Rejected alternatives | 通过调用 endpoint 探测能力：以业务失败代替协商且污染审计；假设所有 `/v1` deployment 能力完全相同：无法安全 staged rollout；按 repository 持久化表策略：越过 caller-owned routing boundary。 |
| Constraints | Capability response 只能 additive 演进；不得包含 host path/provider 或业务 policy。当前/前一 client schema 的精确兼容窗口沿用 `P2-R1-D05`。 |
| Downstream impact | 约束 repository representation、SDK feature gate、deployment readiness、Fake/Local/Remote conformance 和 rollout tests。 |
| Formal owner | Repository Service wire/capability contract；client rollout contract。 |
| Reopen condition | Deployment platform 提供另一个 accepted capability authority，或外部 consumer 需要独立、可协商的 protocol version negotiation。 |

### P2-R2-D26 — Ephemeral cursor and durable identity lifecycle

| 字段 | 值 |
| --- | --- |
| ID | `P2-R2-D26` |
| Topic | Cursor, checkpoint and durable identity behavior across restart/upgrade |
| Status | `ACCEPTED` |
| Decision | 明确区分 durable resource identity 与 ephemeral continuation token。`CommitId`、`RepositoryId` 和 ref identity 按各自 lifecycle durable；`RepositoryOperationId`、`ArtifactId` 在其公开 retention 内 durable；`CurrentTableGenerationId` 仅稳定标识当前状态，mutation 后旧 generation 不可读取。Row cursor/checkpoint 是有 TTL、codec version、query/snapshot binding 和 integrity protection 的 opaque ephemeral token，普通 restart 或 rolling upgrade 可以使其失效；新 server 无法验证/解释时返回 typed `CURSOR_EXPIRED_OR_UNSUPPORTED`，client 从稳定 binding 重启查询，或对必须跨更新/升级保存的结果使用 artifact。Cursor codec 明确不属于 `P2-R1-D05` 的 current/previous schema compatibility promise；其余 durable resource representation 仍须满足该 rollout contract。 |
| Rationale | 要求所有分页 continuation 跨版本长期可用会把 query planner/provider state 固化为公共持久协议；把 operation/artifact identity 也做成 ephemeral 则破坏超时恢复、轮询和下载。 |
| Rejected alternatives | 所有 cursor 必须跨升级兼容：扩大 codec 和 provider compatibility surface；server-side cursor session：违反 disposable process；operation/artifact 随进程失效：无法恢复已接受 effect。 |
| Constraints | Cursor 不得包含可篡改 path、SQL、credential 或未保护 filter literal；精确 TTL、签名/加密、size 和错误映射在 Round 8 固定。Restart/upgrade 测试必须分别覆盖 cursor 失效与 durable identity 保持。 |
| Downstream impact | 约束 cursor envelope、client retry/restart、artifact fallback、upgrade matrix、security limits 和 conformance tests。 |
| Formal owner | Repository Service read/data-plane wire contract；operation/artifact lifecycle contracts。 |
| Reopen condition | Accepted consumer 必须无 artifact 地跨长时间升级续读，并能承担 durable cursor state、migration、retention 和 security 成本。 |

### P2-R3-D01 — Immutable commit and current-generation read binding

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D01` |
| Topic | Versioned/current read snapshot consistency |
| Status | `ACCEPTED` |
| Decision | Versioned read 先 ResolveRef 得到 CommitId，后续 Catalog/Stream/Export/Diff 显式绑定 immutable CommitId；ref 移动不影响已开始读取，`open_ref()` 只是 client resolve-and-pin convenience，不创建跨请求 server session。Current read 先取得 CurrentTableGenerationId；同一 direct stream 在一个 read transaction 内验证并 pin generation，后续 current write 不改变该流所见内容。跨请求 cursor 若 generation 已变化返回 `CURRENT_GENERATION_STALE`，不读取旧 generation；需要跨更新保留结果时使用 export artifact。 |
| Rationale | CommitId 提供天然历史 snapshot；current generation 只提供当前状态 binding。区分两者可防止分页漂移，又不把 CurrentTableStore 变成版本库或长期 session service。 |
| Rejected alternatives | Current pagination 混合 generation：产生重复、遗漏和 schema 漂移；保留所有旧 current generations：重新引入版本数据库；server-side long-lived session：违反 disposable/stateless process boundary。 |
| Constraints | CurrentGenerationId 不支持旧值查询；SQLite snapshot 的具体 transaction/WAL 实现在 Round 4。Ref/current generation 必须在读取数据的同一 provider snapshot 内验证，避免 check-then-read race。 |
| Downstream impact | 约束 read DTO、client open helper、cursor stale failure、SQLite/Dolt adapters、export acquisition、cache、conformance 和 race tests。 |
| Formal owner | Versioned/CurrentTableStore read consistency contract；HTTP data-plane contract。 |
| Reopen condition | Accepted requirement 需要可查询旧 current generation，或多节点 provider 无法在无 server session 时提供稳定 snapshot。 |

### P2-R3-D02 — Framed Arrow row stream

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D02` |
| Topic | Row-stream wire framing |
| Status | `ACCEPTED` |
| Decision | v1 使用 Repository Service 自有 versioned HTTP binary frame stream；small control frames 为 typed JSON metadata，data frames 为标准 Arrow IPC schema/RecordBatch bytes。Frame family 至少包含 `STREAM_HEADER`、`ARROW_BATCH`、optional `CHECKPOINT`、`STREAM_END` 和 body-start 后可用的 `STREAM_ERROR`。Header 绑定 store/repository/snapshot/table/declared schema/schema digest/query options；Checkpoint 只在 deterministic total order 时携带 opaque cursor；未收到 STREAM_END 的 response 必须视为 incomplete。 |
| Rationale | 保留 Arrow 批量类型与无逐行 JSON materialization，同时为 checkpoint、next cursor、final integrity 和 HTTP status 已发送后的 typed failure 提供明确 envelope。 |
| Rejected alternatives | 裸 Arrow IPC stream：难以可靠承载 checkpoint/final typed error；JSONL rows：吞吐和类型成本不符合 bulk boundary；Arrow Flight：Round 1 已拒绝额外 data-plane service/protocol。 |
| Constraints | Frame/schema versions 独立显式；未知 required frame fail closed。Arrow metadata 不得覆盖 declared semantic schema。精确 byte framing、length/checksum 和 compression 在 owning wire schema 中 formalize。 |
| Downstream impact | 固定 server/client stream codecs、media type、Arrow mapping、error handling、cursor checkpoints、fixtures、proxy tests 和 SDK。 |
| Formal owner | Repository Service streaming wire contract；HTTP interface contract。 |
| Reopen condition | Accepted HTTP/client tooling 无法可靠实现自有 framing，或标准协议能满足相同 checkpoint/error/compatibility contract。 |

### P2-R3-D03 — Schema, query order and cursor binding

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D03` |
| Topic | Deterministic row read and resume contract |
| Status | `ACCEPTED` |
| Decision | Declared TableSchema 是 semantic authority，Arrow physical schema 必须 exact mapping。Cursor 绑定 repository、store、CommitId 或 CurrentTableGenerationId、table、schema/projection/filter/order digest、wire version、next position 和 expiry。默认 row order unspecified；resumable cursor 要求显式 total order，有 primary key 时 order 必须以完整 primary key作最终 tie-breaker，keyless table 不提供 resumable cursor。Typed filter v1 支持 bounded `eq/ne/lt/lte/gt/gte/in/is_null/and/or/not`，禁止 SQL、function、subquery、join 和 aggregate。 |
| Rationale | Total-order keyset cursor 防止重复/遗漏；完整 context binding 防止 cursor 被跨 snapshot/query 重用；closed filter AST 提供 selective IO 而不建立 SQL engine。 |
| Rejected alternatives | 任意非唯一 order 也发 cursor：无法稳定续读；offset cursor：大表性能和稳定性较差；provider root/hash 作为 semantic digest：未经 formal 验证；公开 SQL：扩大 query/security contract。 |
| Constraints | Current cursor 只在 generation 仍 current 时有效；Versioned cursor 绑定 CommitId。Provider table root/hash 只用于 cache/diagnostics。Filter depth/terms/IN size、cursor TTL 和 page/batch limits 在 Round 8 固定。 |
| Downstream impact | 约束 cursor codec、query compiler、ordering/collation、Arrow schema validation、indexes、cache keys、security limits 和 deterministic fixtures。 |
| Formal owner | Repository Service read/query/cursor contract；HTTP data-plane contract。 |
| Reopen condition | Accepted workloads 需要 keyless resumable read、aggregate/join，或 provider 无法稳定执行公共 ordering/filter semantics。 |

### P2-R3-D04 — Stream, Parquet export and diff delivery

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D04` |
| Topic | Bulk read delivery modes and artifacts |
| Status | `ACCEPTED` |
| Decision | StreamTableRows/StreamCurrentTableRows 使用 framed Arrow stream。ExportTable/ExportCurrentTable 是 durable async operation，v1 只生成 Parquet ArtifactRef。Artifact manifest 绑定 source store/snapshot/table/schema/query，包含 row count、size、media type、raw SHA-256、creation/expiry 与 controlled download reference；raw Parquet hash 与 semantic content digest 分离。DiffRefs 由 caller 显式选择 `STREAM`（framed Arrow）或 `PARQUET_ARTIFACT`（async operation）；禁止按 size 隐式切换返回类型。 |
| Rationale | Streaming 服务一次性消费与低首字节延迟；Parquet artifact 服务重复下载、异步处理和稳定留存；显式 delivery mode 保持客户端 contract 单义。 |
| Rejected alternatives | 所有读取先物化 artifact：放大磁盘、延迟和 cleanup；所有读取只 stream：断线恢复与重复消费差；隐式 threshold 切换：返回类型随部署配置漂移。 |
| Constraints | ArtifactRef 不返回 server path；未验证完成的 artifact 不可发布。具体 Parquet schema/options/compression、artifact retention 与 download range 在 Round 3 supplemental/Round 7/8 固定。 |
| Downstream impact | 约束 export/diff operations、artifact manifests、download API、storage/GC、Parquet writers、SDK delivery types 和 integrity tests。 |
| Formal owner | Repository Service data-plane/artifact contract；DiffRefs contract。 |
| Reopen condition | Accepted consumer 需要其他持久格式，或 measurement 证明 framed stream/Parquet 组合不能满足 workload。 |

### P2-R3-D05 — Backpressure, deadline and cleanup

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D05` |
| Topic | Stream lifecycle and resource safety |
| Status | `ACCEPTED` |
| Decision | Direct stream 使用 database reader → bounded RecordBatch buffer → HTTP writer 的 backpressure chain；下游阻塞必须暂停上游读取。Deadline、disconnect 或 consumer cancel 关闭 Dolt reader/SQLite transaction并删除未发布临时 bytes；direct read 不创建 durable operation。Current 长读受 duration/bytes/batches 限制以防 WAL/checkpoint starvation。Async export 接受后不因客户端断连取消；只有完整 write/close、hash/size 校验后发布 ArtifactRef，failure/timeout 清理 staging。 |
| Rationale | Bounded pipeline 控制内存与数据库资源；把 ephemeral stream cancellation 和 durable export effect 分离，与 Round 2 operation semantics 一致。 |
| Rejected alternatives | 断连后继续 direct stream：浪费连接/IO；完整 materialize 内存后发送：大表 OOM 风险；未完成 artifact 可下载：破坏完整性；客户端断连自动取消 accepted export：产生 effect uncertainty。 |
| Constraints | Exact buffer/batch/deadline limits 在 Round 8；shutdown/drain 在 Round 9。Current resume 只有 generation 仍 current 才合法；无有效 STREAM_END 的部分结果不得作为成功输入。 |
| Downstream impact | 约束 async IO、reader ownership、SQLite WAL policy、staging lifecycle、operation state、load shedding、metrics 和 disconnect/crash tests。 |
| Formal owner | Repository Service streaming/timeout/artifact lifecycle contracts。 |
| Reopen condition | Accepted transport 无法传播 backpressure/cancellation，或 workload 要求 detachable/replayable stream resource。 |

### P2-R3-D06 — Current async-export snapshot acquisition

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D06` |
| Topic | ExportCurrentTable generation race |
| Status | `ACCEPTED` |
| Decision | ExportCurrentTable worker 开始执行时，在同一个 current-store read transaction 内验证 requested CurrentTableGenerationId 并取得 snapshot；仍匹配则后续 write 不影响该 export，已变化则 operation 终态为 `STATE_CONFLICT / NEW_USER_INPUT / NONE`、stable code `CURRENT_GENERATION_STALE`。Request acceptance 不同步复制数据库，也不持久保留旧 generation。 |
| Rationale | latest-only store 无法在 queue delay 后读取旧 generation；execution-time CAS 明确暴露竞态，并避免为了 export 引入历史版本或昂贵 acceptance snapshot。 |
| Rejected alternatives | 返回 202 前复制 durable SQLite snapshot：使 acceptance 阻塞并增加 storage/cleanup；保留全部 generation：把 current store 变成版本库；静默导出最新 generation：违反 request binding。 |
| Constraints | Snapshot acquisition 与 generation check 不得分成 check-then-open；stale operation 不发布 artifact，临时 bytes 清理。Caller 重新 resolve generation 后提交新请求。 |
| Downstream impact | 约束 export operation state/code、SQLite transaction、queue race tests、client recovery 和 metrics。 |
| Formal owner | CurrentTableStore export/read consistency contract；Round 5 operation contract。 |
| Reopen condition | Accepted use case 要求 202 后保证精确 generation export，即使其随后变旧，并愿意承担 durable snapshot pin/copy。 |

### P2-R3-D07 — Shared closed repository logical type system

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D07` |
| Topic | Cross-store declared types and Arrow mapping |
| Status | `ACCEPTED` |
| Decision | VersionedTableStore 与 CurrentTableStore 共享 closed `RepositoryLogicalType v1`，复用 accepted `DeclaredType` 与 Arrow mapping：null、boolean、signed/unsigned integer widths、decimal、float32/64、string、binary、BIT(n)、date、civil datetime、UTC timestamp、time duration 和 source-literal anomaly。Current schema 不依赖 SQLite affinity；Dolt catalog 映射到同一 logical types。无法无损映射返回 `UNSUPPORTED_LOGICAL_TYPE`，禁止 stringify、精度降低或隐式 timezone conversion。 |
| Rationale | 单一 logical schema 使 stream/filter/order/export/client contract 跨 store 可复用，并防止 provider storage type 成为 wire authority。 |
| Rejected alternatives | Dolt/SQLite 各自暴露 provider types：产生两套 SDK/query semantics；复杂值统一 string：丢失 round-trip、范围和排序；从 Arrow metadata 推断 logical type：倒置 authority。 |
| Constraints | Declared schema 是 semantic authority；Arrow physical schema exact match。Provider-private type 可保留 diagnostics，但不得替代公共 type。新增 logical type 是 owner-versioned contract change。 |
| Downstream impact | 约束 TableSchema、catalog、SQLite encoding、Dolt mapping、Arrow/Parquet、filter/order、fixtures 和 compatibility。 |
| Formal owner | Repository logical schema/wire contract；Shared Canonical Encoding/Arrow mapping owner。 |
| Reopen condition | 必需业务表包含 v1 无法无损表示的类型，并由 type owner发布新增 mapping和兼容规则。 |

### P2-R3-D08 — Provider-neutral RepositoryRawDiff

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D08` |
| Topic | DiffRefs result semantics |
| Status | `ACCEPTED` |
| Decision | DiffRefs 返回 provider-neutral `RepositoryRawDiff`，包含 before/current CommitId、options digest，以及 table-scoped before/current schemas、availability `COMPLETE | UNSUPPORTED`、raw change records和sanitized diagnostics。Raw record 只表达 provider 可完整证明的 added/removed/modified 与完整 before/current values；不应用 table rules、ignored columns、business projection/key、ordered semantics、ComparisonFacts 或 Risk。Dolt adapter 负责去除 provider-private wire shape；无法完整归一时返回 UNSUPPORTED，caller 回退到分别 stream 两个 commits。 |
| Rationale | 同时满足公共 wire 的 provider independence 与现有 native diff 仅为 technical/raw access 的 ownership；不把部分或 provider-specific结果冒充业务 comparison。 |
| Rejected alternatives | 暴露 Dolt native schema：耦合版本/provider；Repository Service 产出 ComparisonFacts：越过 semantic owner；返回 incomplete records并标记成功：可能生成错误 comparison。 |
| Constraints | UNSUPPORTED 是 typed table outcome，不包含 partial records。Exact table frame/Parquet record schema需与本语义一致；NativeDiffCanonicalizer 位于 consuming comparison provider。 |
| Downstream impact | 约束 DiffRefs stream/artifact schema、Dolt adapter、fallback、diagnostics、provider matrix 和 conformance tests。 |
| Formal owner | Repository Service DiffRefs/raw-diff contract；Dolt native provider adapter。 |
| Reopen condition | Formal owner 决定 DiffRefs 仅为 provider-private port而非 public wire，或新增 provider-neutral完整 diff representation。 |

### P2-R3-D09 — Provider-independent ordering and collation

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D09` |
| Topic | Public filter/order comparison semantics |
| Status | `ACCEPTED` |
| Decision | Public ordering/filter comparison 使用 provider-independent logical ordering：string 按有效 UTF-8 binary/code-point order，binary/BIT 按 unsigned bytes lexicographic，numeric 按数值，temporal 按 logical chronology，boolean 为 false < true。每个 order term 显式指定 ASC/DESC 与 NULLS FIRST/LAST；filter comparison 使用相同规则。禁止 provider default、locale-aware 或 case-insensitive collation成为 v1 wire semantics。 |
| Rationale | Cursor、filter 和跨 provider conformance 需要稳定 order；数据库默认 collation会随 Dolt/SQLite/config/version 漂移。 |
| Rejected alternatives | Provider-native collation：结果不可移植；caller-selected locale：引入 ICU/locale/version contract；隐式 NULL placement：跨 provider 不一致。 |
| Constraints | 只对 RepositoryLogicalType v1 中有 total order 的值开放 comparison/order；source anomaly等不满足者拒绝。Provider adapter 必须显式选择或实现公共 collation。 |
| Downstream impact | 约束 query compiler、indexes、cursor key encoding、SQLite/Dolt collation setup、fixtures 和 migration compatibility。 |
| Formal owner | Repository Service query/ordering contract；logical type owner。 |
| Reopen condition | Accepted workload 必须使用 locale/case-insensitive order，并有版本固定、cursor兼容和provider实现方案。 |

### P2-R3-D10 — Minimal v1 stream compression and integrity

| 字段 | 值 |
| --- | --- |
| ID | `P2-R3-D10` |
| Topic | Direct-stream compression and end-to-end validation |
| Status | `ACCEPTED` |
| Decision | v1 framed Arrow direct stream 不使用 HTTP gzip，也不启用 Arrow IPC compression；frame 具有 type/length/strict boundary，STREAM_END 包含此前 header/data/checkpoint frames 的 raw SHA-256 与最终 row count，缺失或 mismatch 即失败。Parquet artifact 使用 ZSTD，并由 manifest 保存 size/raw SHA-256。Direct Arrow compression 只在 benchmark 后作为显式 negotiated encoding扩展。 |
| Rationale | 先固定确定、可流式验证的 wire，避免 proxy content transformation、双重压缩和多 codec compatibility matrix；持久大对象通过 Parquet ZSTD 获得压缩。 |
| Rejected alternatives | v1 同时支持 Arrow NONE/ZSTD：增加 negotiation和fixtures；HTTP gzip：可能受 proxy 自动处理并弱化 frame级观测；无 final integrity：截断难以与成功区分。 |
| Constraints | TLS/TCP 不替代 application-level completeness；STREAM_END digest 的精确 preimage 必须在 wire schema固定。新增 compression encoding 不得静默改变同一请求的 bytes。 |
| Downstream impact | 约束 frame codec、hashing、proxy config、Parquet writer、SDK validation、goldens 和 corruption/truncation tests。 |
| Formal owner | Repository Service streaming/artifact wire contract。 |
| Reopen condition | Accepted baseline 证明 direct-stream network是瓶颈，且 Arrow IPC ZSTD 的跨 client support/conformance 已验证。 |

用户回答“全部按推荐”仍须将每个推荐方案拆成独立 Accepted decision，不能只记录
一句笼统授权。

如果决定被推翻：

1. 原记录改为 `SUPERSEDED`，不得删除；
2. 创建新 decision ID；
3. 列出受影响的 downstream decisions；
4. 只重开实际受影响的 Round。

---
