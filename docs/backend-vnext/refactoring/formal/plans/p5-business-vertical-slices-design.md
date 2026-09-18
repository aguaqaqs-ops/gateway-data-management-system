# P5 Business Vertical Slices Design Baseline

状态：**ACCEPTED DESIGN BASELINE — 5A/5B SLICE EXIT PASS**

日期：2026-09-06

状态更新：2026-09-18（P5-5B independent slice exit acceptance）

Owner：Backend vNext Business Applications and Interfaces

上游：[P4-R6-S0 Entry Brief](p4-r6-s0-entry-brief.md)、
[Business Lifecycle and State](../contracts/business-lifecycle-and-state.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)、
[Implementation Stages](implementation-stages.md)

5B 入口：[P5-5B-S0 Entry Brief](p5-5b-s0-entry-brief.md)

5B exit：[P5-5B-S8 Independent Slice Exit Acceptance](p5-5b-s8-independent-acceptance.md)

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
p5_5c_authorized: no
p5_implementation_authorized: no
```

P5-5B 的历史 implementation 与 real Repository effect authority 已在 S1–S8 执行链中消费并关闭；
独立 acceptance 已声明 `p5_5b_slice_exit: pass`。P5-5A slice exit 与 container gate 亦已 pass
（证据见 [P5-5A S6 Handoff](p5-5a-s6-handoff.md)）。当前不授权新的 P5-5B 实现、P5-5C、
production deployment 或 contract/wire/trust boundary 变更。

## 2. Objective and staged depth

P5按`5A Upload/Preview -> 5B Submit -> 5C Review -> 5D Archive -> 5E History Compare`
交付正式业务纵切。总体基线只冻结跨Slice identity、owner、事务、权限和Repository边界。
**5A** slice exit pass，作为 historical input / slice evidence，不再作为默认详细设计入口。
**5B** slice exit pass；S0 entry、详细设计与执行记录转为 historical input。**5C–5E** 仍待
新的明确授权后再写详细设计，不从 5B exit 自动推导 DTO、实现步骤或 production authority。

P5第一屏交付的是可用业务API和前端loader所需bundle，不建设营销或兼容适配层。新vNext HTTP
DTO独立版本化，不承诺旧`/api/*` wire兼容；legacy只用于发现需要保留的业务语义和fixture。

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
`p5_5b_slice_exit: pass`。下一阶段若为 P5-5C，必须另行取得 entry/design/implementation 明确授权；
当前 `p5_5c_authorized: no`，production deployment 亦未授权。
