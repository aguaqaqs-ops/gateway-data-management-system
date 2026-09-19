# P5 Business Vertical Slices Design Baseline

状态：**ACCEPTED DESIGN BASELINE — 5A/5B EXIT PASS; 5C IMPLEMENTATION AUTHORIZED (S1)**

日期：2026-09-06

状态更新：2026-09-19（P5-5C design accepted；S1 implementation authorized；remediation pending countersign）

Owner：Backend vNext Business Applications and Interfaces

上游：[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Implementation Stages](implementation-stages.md)

5B 入口：[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)

5B exit：[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md)

5C 入口：[P5-5C-S0 Entry Brief](p5-5c-s0-entry-brief.md)

5C design：[P5-5C Review Detailed Design](p5-5c-review-design.md)、
[P5-5C Review Execution Plan](p5-5c-review-execution-plan.md)

5A historical input：[P5-5A S6 Handoff](p5-5a-s6-handoff.md)

## 1. Decision and authorization boundary

```yaml
design_kind: p5_business_vertical_slices
discussion_base_sha: d7cb5b9c2c55e8f8b0814520e9d95c7df0ad00a5
p4_r1_through_r5: pass
p4_r6_exit: pass
p5_design_discussion: converged
p5_design_baseline: accepted
p5_5a_baseline: accepted
p5_5a_slice_exit: pass
p5_5a_s0_entry_brief: closed_historical_input
p5_5b_s0_entry_brief: accepted
p5_5b_design_s0_authorized: yes
p5_5b_implementation_status: completed
p5_5b_implementation_authorized: no
p5b_real_repository_effect_authority: consumed_closed
p5b_real_repository_effect_authorized: no
p5_5b_slice_exit: pass
p5_5c_s0_entry_authorized: yes
p5_5c_design_s0_authorized: yes
p5_5c_design: accepted
p5_5c_design_status: accepted
p5_5c_implementation_authorized: yes
first_authorized_step: P5-5C-S1
p5_implementation_authorized: no
```

P5-5B 的历史 implementation 与 real Repository effect authority 已在 S1–S8 执行链中消费并关闭；
独立 acceptance 已声明 `p5_5b_slice_exit: pass`。P5-5A slice exit 与 container gate 亦已 pass
（证据见 [P5-5A S6 Handoff](p5-5a-s6-handoff.md)）。P5-5C design 已 accepted；S1
implementation 已在 `0e9c131b` 授权并交付于 `82f353de`。不授权新的 P5-5B 实现、P5-5D/P5-5E
implementation、production deployment 或 contract/wire/trust boundary 变更。

## 2. Objective and staged depth

P5按`5A Upload/Preview -> 5B Submit -> 5C Review -> 5D Archive -> 5E History Compare`
交付正式业务纵切。总体基线只冻结跨Slice identity、owner、事务、权限和Repository边界。
**5A** slice exit pass，作为 historical input / slice evidence，不再作为默认详细设计入口。
**5B** slice exit pass；S0 entry、详细设计与执行记录转为 historical input。**5C** design 已
accepted；S1 implementation 在 `0e9c131b` 授权并于 `82f353de` 交付；finding-scoped remediation 于
`1726c2d5` 闭合代码/契约问题，当前 pending independent S1 countersign。**5D–5E** 仍待新的明确授权；
production deployment 未授权。

P5第一屏交付的是可用业务API和前端loader所需bundle，不建设营销或兼容适配层。新vNext HTTP
DTO独立版本化，不承诺旧`/api/*` wire兼容；legacy只用于发现需要保留的业务语义和fixture。

<a id="p5-architecture-guardrails"></a>

## 2A. Architecture guardrails and phase closure

生效日期：2026-09-19。Owner：P5 Application/Capability owners；阶段收口由 Backend vNext
Architecture 负责。依据 repository owner 本轮明确授权，补充 P5 后续设计、实现与评审原则；
遵守 [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)、
[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md) 与
[Proportional Assurance Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

### 2A.1 生效范围与修复时机

本节是 P5 架构纠偏的唯一规则来源，适用于 5C 后续工作、5D/5E 详细设计与实现，以及再次修改
5A/5B 时的增量。5A/5B 历史 exit、5C 已交付步骤的验收记录继续有效；本次文档补充不宣称
源码已修复、测试已增强或当前阶段已获新实现/部署授权。阶段状态与下一步仍见 §13。

后续增量立即遵守下列边界；已有问题集中安排在 P5 业务纵切完成后、P5 整体退出验收前处理。
不以集中修复为由扩散既有例外，也不要求每个 Slice 先完成全量架构清理。若当前工作必须新增
私有依赖、复制 wire 映射、形成反向调用，或同一内部 helper 出现第三个模块消费者，应先做
对应 owner 内的最小边界修正。允许路径内、行为不变的普通整理按既有实现授权执行；确实需要
扩大阶段范围或改变持久/业务 contract 时才更新对应计划与必要授权，不新增逐项审批流程。

### 2A.2 后续实现立即遵守的边界

- **单向依赖与公共入口：**Capability 只依赖上游公共 contract；Application、HTTP、adapter
  等所有消费者都不得新增 capability 私有模块/私有符号依赖。Application 用公共 entrypoint
  编排能力；下层事务、codec、protection helper 不得反向 import job 编排模块，函数内 import
  也不能用来规避依赖方向。具体 adapter/provider 在 composition 中选择。
- **基础层与归属：**Artifacts 等基础单元不依赖 Domain/Application；业务 nominal ref 与通用
  artifact ref 的转换放在能同时依赖两端的 Application/adapter 侧。类型迁移必须服从既有
  Domain 依赖规则，不能为消除一条倒挂而新增 Domain → Artifacts 依赖。Backend/Repository
  ref 的 nominal type、ID scope 和 upload 显式映射继续保持隔离。
  Storage Projection 的 canonical 编码/manifest 语义由该 capability 拥有；用例 publication
  adapter 归 infrastructure，由 composition 接线。包根不新增无明确 owner 的业务胶水。
- **薄契约与 owner：**公共面按真实消费者暴露 Input/Result/Facts、最小 port 和明确入口。
  必要语义校验、canonical digest 和序列化规则仍归原 owner；不以行数判断契约厚度，不复制
  算法，不通过 `__init__` 把 planner 中间状态或具体 provider 扩成普通用例的必需依赖。
  不新增 common DTO、通用 context bag、无消费者版本轴或通用工作流框架。
  `contracts.py` 表示公共语义面而非仅类型集合：允许纯 codec、shape/invariant validator、
  规范 canonical bytes/digest 规则；禁止承载 provider 选择、数据集扫描/比较/投影执行、I/O
  或业务编排。规范摘要规则与执行算法应按职责区分，不能因 digest 也是算法就机械迁出。
  Contract 不反向导入执行实现；facade 可委托同 owner 的实现，但 lazy import 不能掩盖环或
  越界。只 import contract 不应要求初始化具体 provider 或加载重型执行依赖。
- **业务 port 与 wire：**新增业务 port 不返回 Repository wire DTO。Adapter 负责 wire 编解码
  和映射，Application 消费最小业务事实/结果。Submit 已有 exact request bytes、fingerprint、
  same-key replay、matching terminal result 和 verification 语义必须保留；移动编码责任时应
  证明持久证据与实际发送内容一致，不得把恢复依据替换成可能漂移的重新构造请求。
- **流程编排归 Application：**业务身份、权限、场景选择、跨聚合协调、事务与恢复策略留在
  Application。Capability 接受中性的输入和显式计算策略，不新增对 Review/Archive/History
  实体或 application model 的依赖。R5 已接受的 pair/view/applicability 词汇保留；5D/5E 若
  需要增加流程分支，先判断是否可在 Application 映射为已有模式，不能只因新增流程就扩大
  comparison 的业务分支。确需改变语义时由原 contract owner 决定。
- **按职责控制编排复杂度：**payload/checkpoint codec、artifact protection、事务协调与
  capability pipeline 可以分为同一用例 owner 内的模块；job handler 保留步骤选择和恢复协调。
  只有真实重复消费者才提炼共享入口，不为减少单文件行数新增架构层。
- **门禁保护增量：**`tests/test_architecture.py` 是 Backend import 边界的权威测试 owner。
  新规则按精确公共模块/符号检查，不新增按文件 basename 或整层放行的豁免。既有绿灯不能替代
  对实际依赖边的检查；评审覆盖 HTTP/adapter 消费者、函数内 import 和 Application 运行时环，
  区分 TYPE_CHECKING 类型引用与运行时依赖。已有违例收口前只对本次增量执行禁止扩散检查，
  不为每个 Slice 建立另一套扫描框架或复制全部架构测试。
  能力调用许可依据用例职责和精确公共入口，不以“仅 job 文件可调用”为架构不变量，也不把
  basename 豁免替换成 `*_jobs.py`/transaction 通配豁免。同步用例可在 Application 编排能力；
  transaction 模块不因文件名自动获得能力访问权，短事务中也不引入长时间计算或外部 I/O。

### 2A.3 为渐进 Rust 改造保留边界

遵守 [ADR 0001](../adr/0001-python-rust-hybrid-compute-strategy.md)。Python 保留业务编排、
Repository/Artifact I/O、事务和 Operation 生命周期；Rust 承接经测量确认的批量计算热点。

- 普通用例依赖 capability 公共入口；provider 选择集中在 composition，业务 payload、checkpoint
  和 digest 不新增对 Python/Rust class 或实现版本的身份依赖。
- 保留 Arrow/Parquet 批处理边界，检查逐行 FFI、Python object graph、重复编码和重复 artifact
  读写；不为未来热点预建 provider framework，也不要求 P5 新增 Rust 实现。
- Rust 替换复用 owner 现有 contract/golden 与小规模 Python oracle，核对排序、null/decimal、
  digest、错误语义、资源上限和取消边界；不要求完整 Python 生产双实现或自动 fallback。
- P5 收口选择一条已完成的真实业务链路，用代表性 workload 记录端到端耗时与 Repository/I/O、
  Python 转换、计算的主要开销，形成 Phase 6 热点候选。测量遵守现有 performance policy；
  只作迁移排序依据，不新增性能通过阈值或 benchmark/evidence 平台，不凭模块行数承诺加速。

### 2A.4 已知问题与收口责任

以下是 2026-09-19 架构评估的源码观察，不是已完成修复声明，也不把已接受设计折中自动判为
功能缺陷。实际修复时复核届时源码；已由后续 Slice 解决的项目直接引用结果，不重复改造。

| 已知问题/风险 | Owner | P5 整体退出前的处置 |
| --- | --- | --- |
| `application/submission/ports.py` 返回 `VersionedOperation`；`submit_jobs.py` 编解码 wire | Submit Application + Repository adapter | 收窄业务 port，将 wire 映射移至 adapter；保持请求证据、实际发送与恢复语义一致 |
| HTTP admission 导入 `source_package_staging._archive`；read adapter 导入 `snapshot_materialization._digest` | Source Package / Snapshot + 对应消费者 | 建立最小 owner 公共入口并迁移消费者，不复制安全校验或摘要算法 |
| finalize/abort transaction 反向调用 `submit_jobs` 的 checkpoint protection helper | Submission Application | 将 helper 放回用例 owner 内的下层模块，消除运行时依赖环 |
| 架构测试存在 basename 整体豁免，未覆盖上述消费者与运行时环 | Backend Architecture | 收窄例外并在现有测试 owner 补齐边界，避免同包合法内部导入或纯类型引用误报 |
| `artifacts/nominal_refs.py` 导入 `domain.submission.models` | Artifacts + Submission Application/adapter | 优先将跨层转换上移至 Application/adapter；若迁移类型须同时满足 Domain 依赖规则，保持 Backend/Repository nominal ref 与 scope 隔离 |
| 包根 `canonicalization_cells.py` / `canonicalization_manifest.py` 与 `repository_import_artifact.py` 混放 owner 逻辑和 Submit adapter | Storage Projection + Submit publication adapter + Architecture | 按职责拆分归位；保持 canonical bytes、manifest/package 版本和 digest 兼容；删除无消费者入口，避免只搬目录或让 capability 反向依赖 Application |
| 契约公共面与执行实现的区分缺少明确约束 | Capability owners + Architecture | 按 §2A.2 核对 codec/validator/规范摘要与执行算法的边界；仅修复确认的反向依赖、加载副作用或执行混入，不把所有契约函数或 lazy import 判为缺陷 |
| Preview/Submit 编排职责集中；Comparison 公共面及流程词汇扩大 | 对应 Application + Comparison | 按实际调用方收窄入口和拆分职责；保留已有正式语义，记录必要设计折中，不按文件大小强拆 |
| `comparison_projection` / `business_projection` 仍为占位契约 | 对应 capability owner + Architecture | 根据 5D/5E 真实消费者明确实现、合并或延期，并同步总纲/ownership 与架构测试 owner 集合、DAG 白名单；无真实消费者时不强行实现，延期不保留虚假的已落地依赖边 |

补充核对：`repository_write/http.py` 当前从包根 manifest 模块导入的是
`REPOSITORY_IMPORT_MEDIA_TYPE` 常量，并非调用 manifest 组装器。收口应消除该常量对组装模块的
不必要依赖；常量的来源按实际 wire/content owner 决定，不能据此推断该 adapter 执行了 canonical
组装。以上不宣称 nominal-ref 倒挂是全仓唯一基础层违例，也不以某次文件计数作为验收依据。

### 2A.5 收口验收

在既有 P5 exit review 中检查本节，不新增独立审批链或持久治理状态机：

1. 已确认的 wire 泄漏、私有导入、事务/编排环、基础层倒挂与包根归属问题完成修复，架构
   门禁补齐相应边界；canonical/manifest 归位还须复用现有语义测试核对 bytes/digest 兼容。
   不得仅因 5A/5B 曾通过而视为关闭。
2. 契约面/执行边界、编排集中度及 projection 占位风险完成实际消费者复核与文档处置；
   有必要的既有公开语义可保留，明确 owner 和理由。
3. 记录本轮新增依赖是否遵守本节、既有问题已解决/待收口的位置，以及真实链路测量结果与
   Phase 6 候选；使用已有 handoff 的简短文字或表格，不重复复制本节问题清单。
4. 按改动范围完成语义回归、五包静态检查及既有阶段退出的权威 runner/容器要求；模块移动
   不自动增加全故障点矩阵。P5 整体 exit 不能先通过再无限期延期这次收口。

## 3. Deployment and trust boundary

- Backend HTTP与worker使用同一镜像、不同进程；single host、single worker。
- Business facts、Operation和同一事务参与者共享一个本地SQLite/WAL control DB。
- Repository Service保持独立内网进程和durable root，使用既有internal bearer。
- Backend不挂载Repository volume、不运行Dolt、不接触Repository server path或CLI。
- V1不引入HA、外部DB、broker、sidecar、worker membership或分布式事务。
- 同机Backend模块和worker属于一个受控信任域；外部HTTP输入、artifact内容、scope和路径仍不可信。

Backend `/readyz` 至少检查settings、control DB migration/integrity、artifact root和JobDefinition
registry；worker有独立health gate。部署只在Backend、worker和Repository Service都healthy后
开放流量。shutdown先关闭HTTP admission，再drain worker。暂时没有worker不需要membership状态。

## 4. Scope, provisioning and identity

IdentityContext保留：

```text
actor_id
gateway_device_external_key
business_project_id
permissions
```

外部control plane拥有device/project/Repository mapping和provisioning。V1一个gateway device
同时最多有一个active business project；该pair解析到唯一Repository。Provisioning创建
Repository及其initial empty commit，并在同一业务scope登记explicit-empty BaselineNode/Head。
Upload不得创建或猜测Repository/Baseline。

同一`(owner_actor_id, gateway_device_external_key, business_project_id)`最多一个OPEN
Workspace。历史Workspace、UploadRevision、PreviewResult、Submission和BaselineNode冻结创建时
的scope与Repository identity；mapping变化不改写历史。

`CreateOrGetWorkspace`是mutation通则的唯一例外：它没有可供caller预先读取的Workspace version，
也不要求caller-generated idempotency key；其幂等identity就是当前session解析出的exact
`(owner_actor_id, gateway_device_external_key, business_project_id)`。并发创建由数据库OPEN
唯一约束裁决；一个事务创建并返回`201`，其余冲突事务重新读取同一OPEN Workspace并返回`200`，
不得产生第二个Workspace。

其余mutation必须携带caller-generated idempotency key和expected optimistic version。same key/
same fingerprint返回原结果；same key/different fingerprint返回conflict。相同bytes使用新key是
新的用户动作，可以创建新UploadRevision，但ArtifactStore可以按content复用bytes。

## 5. Repository main and business Baseline

P5明确维护两种不可互换的身份：

```text
Repository main
  latest successful technical import head

Business BaselineHead
  latest formally archived BaselineNode/commit
```

Preview只读取业务BaselineHead。5B AcceptSubmit在T1冻结
`business_baseline_commit_id`，同时resolve并冻结当前Repository `main`为
`repository_expected_commit_id`；前者绑定业务比较，后者只用于Repository import parent/CAS。

Repository所有成功import沿技术`main`形成永久链。Review不移动ref。Archive也不移动技术
`main`，而是把现有合格Submission CommitId直接绑定为下一BaselineNode。业务History的
`based_on_baseline_node_id`与Repository物理parent是两种不同边。

## 6. Slice baseline

### 6.1 5A Upload and Preview

Upload与Preview是独立command和identity；前端可以把它们顺序呈现为一次用户动作。

Upload同步执行bounded streaming、size/raw SHA、archive/path/link安全、required-file和role
closure admission，然后创建immutable UploadRevision。Upload不解析SQL、不materialize
Snapshot、不比较，也不创建Operation。

首版输入模式只有：

| Mode | Uploaded roles | Preview before side |
| --- | --- | --- |
| `FULL` | `INITIAL + MODIFIED` | uploaded INITIAL |
| `MODIFIED_ONLY` | `MODIFIED` | current business Baseline reconstruction |

两种mode都必须从frozen business Baseline exact commit物化Baseline Snapshot。FULL形成
Baseline/uploaded INITIAL/uploaded MODIFIED三侧并生成`baseline_to_initial`与
`initial_to_modified`；MODIFIED_ONLY把Baseline Snapshot直接复用为effective INITIAL，再与
uploaded MODIFIED生成`initial_to_modified`。

删除用户可见`INITIALIZE_BASELINE`；5A要求已存在BaselineHead。

Preview接受后返回`202 + operation_id`，并冻结exact Workspace/UploadRevision generation、
source/input digest、BaselineNode/commit、ruleset/contract versions和required artifact policy。
JobDefinition固定为：

```text
materialize_inputs
  -> assemble_preview
  -> publish_preview
```

table/capability内部工作不升级为持久workflow step。必需source/table/default pair/bundle closure
失败使整个Preview失败；可选table/XML/ordered/risk增强可以以bounded diagnostics降级，但成功
结果仍只有READY，不增加`READY_WITH_WARNINGS`。

新Upload采用latest-generation-wins。旧QUEUED Preview进入`SUPERSEDED`；旧RUNNING Preview
收到cooperative cancellation，且无论迟到结果如何都不能发布current preview。发布事务同时
校验Workspace generation和BaselineHead CAS；发布前drift产生`SUPERSEDED`且不创建
PreviewResult。发布后Baseline drift不改写immutable PreviewResult，只在读取时派生stale，
Submit拒绝该结果。系统不自动重算。

### 6.2 5B Submit

AcceptSubmit校验current generation、Preview binding、current business Baseline、权限、幂等和
Workspace占用；canonical business digest等于base时在Attempt前返回`NO_CANONICAL_CHANGE`。
T1只原子创建SubmitAttempt和Operation，不创建outbox。

Repository policy由5B内部固定：`target_ref=main`、`verification_policy=STRUCTURAL`、
`unknown_type_policy=REJECT`、mutation policy=`REBUILD_ALWAYS`。HTTP caller不能选择。
Repository effect和T3遵守evidence-first recovery；业务worker不推断commit/ref事实。

### 6.3 5C Review

Review只使用`PENDING | APPROVED | REJECTED | RETURNED_FOR_REVISION | WITHDRAWN`和immutable
events，不建设start-review中间态。Review不创建、移动、回退或清理Repository ref。所有成功
Submission commit永久保留；rejected/returned/withdrawn重新开放Workspace并进入History。

### 6.4 5D Archive

CandidateProjection只包含Review=`APPROVED`、基于current BaselineHead且未被既有ArchiveResult
关闭的Submission。PreviewArchivePlan是纯读结果。StartArchive要求idempotency key、expected
Head version、candidate-set digest、唯一selection、confirmations/anomaly resolutions并确认无
active SubmitAttempt；它与AcceptSubmit在同一Head scope内通过SQLite事务串行验收。

成功StartArchive在一个本地事务中创建ArchivePlan、ArchiveResult、BaselineNode，推进
BaselineHead，把未选approved sibling分类为`CLOSED_NOT_ARCHIVED`并释放对应Workspace。
Archive不创建Operation/ArchiveExecution，不调用Repository写接口，不重物化或重复commit。
已关闭sibling若要重新采用，必须从current Baseline重新Preview/Submit。

### 6.5 5E History Compare

HistoryTreeProjection由Backend从initial Baseline、Submission、Review facts、ArchivePlan/Result、
BaselineNode/Head和validation issue组合。它包含所有成功Submission commit，包括rejected、
returned、withdrawn和closed-not-archived；未来migration commit必须登记为`SYSTEM_MIGRATION`。
未发布private candidate、失败import临时commit和operation marker不属于业务History。

History Compare绑定两个或三个授权业务节点的exact CommitId，执行只读Repository access、
comparison/risk/surface/bundle和只读Operation，不修改Workspace/Submission/Archive/Baseline。

## 7. Authorization boundary

- Workspace create/read和Upload要求exact actor/device/project scope；Upload另需
  `upload_submit_workspace`。
- Preview接受沿用Workspace exact scope；Operation/result/bundle每次读取都重新检查当前session、
  scope与permission。
- Review/Archive/complete History使用独立project/device权限，可以覆盖多个actor Workspace。
- Session expiry不取消已经接受的Preview；gateway disabled拒绝新工作，但已接受的纯计算可以完成。
- Worker不持续重新授权；它只执行已接受、冻结且可恢复的job。结果读取不能依赖接受时权限。
- Repository internal bearer不是终端用户authority，Backend负责所有业务授权与RepositoryId映射。

具体permission字符串和route命名由对应Slice HTTP contract冻结，不进入domain或Repository wire。

## 8. Persistence and transaction boundary

各domain拥有独立repository port和record mapping，但通过同一SQLite Unit of Work组合需要原子提交
的事实。禁止把HTTP body、capability object、Python closure或Repository client放入domain
record。

5A关键事务为：Workspace create/get；UploadRevision + generation/current-input publication；
Preview Operation acceptance；PreviewResult + current-preview pointer + terminal Operation publication。
Artifact bytes必须先以immutable/server-owned path写入并回读校验，再由短事务发布ref；stale CAS
留下的未引用derived artifact由bounded TTL cleanup处理。

5B保留跨Repository的T1/T2/T3。5C是短事务。5D是单个本地archive事务。当前没有真实
integration-event consumer，因此任何Slice都不创建outbox table或dispatcher。

## 9. Artifact retention

- UploadRevision metadata永久保留；大bytes按业务引用和TTL处理。
- current Preview与active SubmitAttempt需要的SnapshotTableArtifact被pin。
- AcceptSubmit T1把pin responsibility从Preview原子转给Attempt；Attempt终态释放full-row pin。
- 成功Submission使用的SourcePackageArtifact长期保留，作为raw/provenance/replay authority。
- superseded、失败或从未提交的大bytes使用保守固定TTL做best-effort cleanup。
- 不建设generic refcount/GC状态机；protected、active或manual-recovery artifact不得自动清理。
- rejected/withdrawn commit由Repository永久history保存；业务metadata和source retention不因Review
  结果被改写。

## 10. Recovery and administration

Preview是pure compute：可从immutable refs/checkpoint重算，取消只在cooperative boundary生效。
5B外部effect只能复用原request/artifact/idempotency/Repository operation identity进行reconcile。

部署内部admin HTTP复用现有internal bearer，仅允许：

```text
RESUME_RECONCILE
RETRY_FROM_CHECKPOINT
ABORT_CONFIRMED_FAILURE
```

请求必须带Operation/Step expected versions和reason；不允许任意record编辑、force-success、force
移动Repository ref或blind replay。

## 11. Verification and gates

每个Slice验证Contract语义屏障而非穷举内部步骤。5A至少覆盖：

- Workspace uniqueness、scope、permission、idempotency和optimistic conflict；
- streaming size/hash、archive traversal/link/root escape、required role/file closure；
- FULL与MODIFIED_ONLY pair/bundle结果和既有capability golden一致；
- generation supersede、running cooperative cancellation和迟到publication fencing；
- Baseline drift before/after publication；required failure与optional degradation；
- artifact pin/TTL/protected边界、worker restart/takeover和READY closure；
- Backend/worker/Repository health coordination及HTTP DTO/OpenAPI tests。

阶段性验证按仓库testing conventions只运行focused范围；5A最终gate运行Backend相关unit/
integration/serial、五包ruff/mypy及权威`./vnext/scripts/run-tests.sh`。触碰Dockerfile、Compose、
entrypoint、settings/readiness、mount或最终Slice gate时，重建current-HEAD镜像并运行容器门禁。

P5 整体退出另须完成 §2A 的边界修复、风险处置及 Phase 6 性能输入；单个 Slice 的历史 exit
不替代阶段收口。5C 后续及 5D/5E 在原有 handoff 中简述增量遵守情况。

## 12. Deferred and reopen conditions

延后到各Slice详细设计：exact HTTP paths/DTO field names、permission字符串、History cursor/page
shape、固定TTL数值、UI节点渲染和production-path容量记录。Legacy persistence/Dolt cutover、
online ruleset migration、external event consumer、HA和外部DB保持独立未来决策。

出现以下任一情况必须停止对应设计/实现并reopen owning contract：

- 一个device需要同时映射多个active business project；
- 5A需要在Upload中解析SQL、初始化Baseline或执行Repository写入；
- Preview无法使用固定三步JobDefinition或需要持久per-table workflow；
- Archive必须合并多个candidate、移动Repository ref或产生新commit；
- rejected/withdrawn history需要删除、rewrite或脱离scope授权读取；
- 出现真实integration-event consumer、multi-host writer、HA、broker或外部transaction participant；
- business Baseline和Repository `main`无法保持独立身份。

## 13. Current next action

[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md) 已声明
`p5_5b_slice_exit: pass`。P5-5C design 已 accepted；S1 implementation 已授权并交付，当前处于
S1 remediation / independent countersign（见 [S1 handoff](p5-5c-s1-handoff.md) 与
[remediation handoff](p5-5c-s1-remediation-handoff.md)）。P5-5D/P5-5E implementation 与
production deployment 仍未授权。
