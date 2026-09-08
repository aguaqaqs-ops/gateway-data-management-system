# Business Lifecycle and State Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 5 实现

Contract ID：`gateway-vnext.business-lifecycle-and-state`

Owner：各子领域 owner（见下表；本文不建立共同 aggregate）

Semantic version：`2.0.0`

2026-09-06 amendment：P5 设计收口后，Repository `main` 与业务 `BaselineHead` 明确分离；
Archive 直接把既有合格 Submission commit 提升为业务 Baseline，不移动 Repository ref、
不重新导入，也不再使用 external-effect execution 四态。Review 不创建或清理临时 ref。

## 1. 目的与所有权

本文固定 vNext 第一版必须持久化的最小业务事实、派生 projection 和跨领域事务边界。每个子 contract 只有一个 owner：

| 子 contract | 唯一 owner | 持久化 |
| --- | --- | --- |
| Workspace | Workspace Domain | 必须 |
| UploadRevision | Workspace Domain | 必须 |
| PreviewResult | Workspace Application | 必须 |
| SubmitAttempt | Submission Application | 必须 |
| Submission、ReviewEvent/ReviewProjection | Submission Domain | 必须 |
| BaselineNode、BaselineHead | Baseline Domain | 必须 |
| ArchivePlan | Archive Application | 必须；仅保存成功 StartArchive 的冻结输入 |
| ArchiveResult | Archive Domain | 必须 |
| CandidateProjection、PreviewArchivePlan | Archive Application read model | 否；按请求派生 |
| HistoryTreeProjection | History Application read model | 否；按请求派生 |

Application owner 负责命令验收、事务和跨 aggregate 协调；Domain owner 负责对象状态与不变量。Operation Runtime 只拥有执行状态，Repository Service 只拥有通用 repository effect，不取得业务对象所有权。

业务一致性根为`RepositoryId`。V1中一个gateway device同时最多有一个active
business-project mapping；外部control plane把
`(gateway_device_external_key, business_project_id)`解析为唯一Repository。`BaselineHead`
按Repository唯一。历史对象冻结创建时的actor/device/project/Repository身份；后续mapping
变化不得改写历史。

## 2. Workspace 输入与预览

Workspace 只持久化 `OPEN | CLOSED` 以及必要关系：当前 input revision、当前 preview、active SubmitAttempt/Submission 和关闭时间。`EMPTY`、`INPUT_READY`、`PREVIEW_READY`、`SUBMITTED` 等只可作为 read-model label，不能成为需要多模块同步推进的状态。

同一`(owner_actor_id, gateway_device_external_key, business_project_id)`最多存在一个OPEN
Workspace。Upload和Preview都要求幂等键与expected Workspace version。

`UploadRevision` 表达一次用户输入选择及generation，引用按`INITIAL | MODIFIED` role标识的
immutable `SourcePackageArtifact`。`FULL`要求INITIAL和MODIFIED；`MODIFIED_ONLY`只接收
MODIFIED，并在Preview时从当前业务Baseline重建before侧。相同bytes的新用户动作可以创建新
revision；artifact bytes按内容复用。Upload只执行bounded streaming、size/hash、archive/path
safety、required-file和role closure admission；不得解析SQL、materialize snapshot或比较。
格式校验在接受前失败不得创建revision。

`PreviewResult` 是对 exact Workspace、UploadRevision、source/input digest、业务Baseline、
ruleset/contract version、Snapshot/Comparison digest 和 artifact closure 的不可变绑定。
Preview接受时冻结这些身份，并创建固定三步Operation：
`materialize_inputs -> assemble_preview -> publish_preview`。Preview失败不使已接受revision
失败；旧generation不得覆盖current preview。新Upload采用latest-generation-wins：旧QUEUED
Preview进入`SUPERSEDED`，旧RUNNING Preview收到cooperative cancellation。

必需source/table/default pair/bundle closure缺失使整个Preview失败；可选table/XML/ordered/risk
增强失败可发布READY及bounded diagnostics，不增加`READY_WITH_WARNINGS`。发布前Workspace
generation或BaselineHead CAS漂移时进入`SUPERSEDED`，不创建PreviewResult或current pointer；
发布后的Baseline漂移保留immutable结果，但使其derived-stale，后续Submit必须拒绝。

Upload与Preview是两个用例；接口可以组合调用，但identity、失败和重试语义不能合并。Upload
同步完成且不创建Operation；只有Preview执行状态属于Operation，不进入Workspace。

## 3. SubmitAttempt 与 Submission

`AcceptSubmit` 必须校验 expected revision、preview、业务baseline、idempotency 和占用。T1同时
冻结`business_baseline_commit_id`与当时Repository技术`main`的
`repository_expected_commit_id`；二者不得混用。若Preview的canonical business digest与当前
业务base相同，以`NO_CANONICAL_CHANGE`在创建Attempt前拒绝；不得创建Operation、Repository
request、Submission或BaselineNode。

验收成功只创建 `SubmitAttempt` 与 Operation。Attempt 固化 source/baseline/preview、artifact、request/idempotency、Repository operation/evidence、终局和 Submission 引用。状态仅为：

```text
PREPARED -> EFFECT_PENDING -> FINALIZED
PREPARED -----------------> ABORTED
EFFECT_PENDING -----------> ABORTED
```

- `PREPARED`：业务已验收并占用 Workspace，尚未跨越可能产生 effect 的边界。
- `EFFECT_PENDING`：请求可能未发送、执行中、结果未知，或已应用但尚未完成 readback/业务 finalize。
- `FINALIZED`：Repository result已完成Submit owner为该use case请求的verification，且
  恰好一个Submission已创建。
- `ABORTED`：Repository stable outcome已经证明未发布，且原请求不再继续。

只有matching SUCCEEDED result，且`requested_verification_policy ==
completed_verification_policy`，artifact ID、CanonicalizationManifest digest、expected
parent、target ref和unknown type policy均与T1 checkpoint一致后才可创建
`Submission`。Repository verification不替代business-owned digest/binding validation；
具体use case选择NONE、STRUCTURAL或FULL_SCAN在Phase 3/5 consumer设计时确定，不能由
Repository擅自升级或降级。失败Attempt不产生半完成Submission。
`Submission.submit_attempt_id`唯一。Finalize重放先返回既有Submission，再修正
Workspace/Operation派生投影。

`FINALIZED` 将 Workspace 占用从 Attempt 原子切换到 Submission；`ABORTED` 释放 Attempt 占用。Operation 的 terminal status、effect `UNKNOWN` 或已应用但未 finalize 都不能单独释放占用。

## 4. Review

Review 当前投影仅为：

```text
PENDING | APPROVED | REJECTED | RETURNED_FOR_REVISION | WITHDRAWN
```

Review 使用不可变审核事件和当前 projection；不建设单独的“开始审核”命令或中间审核状态。Approve、reject、withdraw、return 是直接的短事务。Reject/withdraw/return 重新开放 Workspace 并清除当前输入、预览和占用；approved Submission 保持占用，直到对应 ArchiveResult 推进 BaselineHead。归档开始后不得 return。

Review状态与Archive disposition正交。Review不创建、移动、回退或清理Repository ref。
`REJECTED | RETURNED_FOR_REVISION | WITHDRAWN`对应的成功Submission commit永久保留并进入
HistoryTreeProjection；知道CommitId不绕过当前scope与permission检查。

## 5. Baseline 与 Archive

`BaselineNode` 是immutable业务mainline version，引用一个既有immutable Repository CommitId；
`BaselineHead`只保存当前node pointer和并发版本。Repository `main`只是最新成功技术import头，
不得被解释为业务Baseline。当前/历史身份由Head派生。第一版不建设baseline batch aggregate/
lifecycle、invalidate或重复的ready/archive状态。

`CandidateProjection`只从Review=`APPROVED`、冻结business baseline等于当前BaselineHead、且
未被既有ArchiveResult关闭的Submission派生，不持久化candidate entity、selection、status或
tag。稳定引用为`submission_id + expected_candidate_digest`。旧baseline的approved sibling
仍保留Review事实和History节点，但不再是普通candidate。

`PreviewArchivePlan`是纯读计算，不冻结输入、不创建业务状态。`StartArchive`要求幂等键与
expected BaselineHead version，并在短本地事务中重新校验Head、无active SubmitAttempt、
candidate-set digest、confirmation、anomaly resolution与唯一selection。AcceptSubmit和
StartArchive在同一Repository/BaselineHead scope内通过control DB事务串行验收。
Confirmation和AnomalyResolution是append-only审计事实；有效性由当前subject digest和
sequence派生。

StartArchive成功时在同一业务事务中冻结immutable `ArchivePlan`，直接把所选Submission的既有
CommitId绑定到新`BaselineNode`，并创建`ArchiveResult`、CAS推进`BaselineHead`、分类未选
approved sibling为`CLOSED_NOT_ARCHIVED`并释放相关Workspace占用。Archive不重新物化、不调用
Repository import、不移动Repository `main`、不创建第二个commit，也不创建Operation或
`ArchiveExecution`。失败的校验不创建Plan/Result；same key/same fingerprint返回既有成功结果，
same key/different fingerprint冲突。

成功的ArchiveResult、BaselineNode、BaselineHead advance、sibling disposition和Workspace
release在业务事务中保持一致；没有成功业务Head CAS就不创建任何前缀。若以后仍需采用
`CLOSED_NOT_ARCHIVED`内容，必须针对当前Baseline重新Preview/Submit。后置artifact transfer或
notification若出现真实consumer，只能作为归档成功后的独立可重试动作，不改变已成立业务事实。

## 6. History

`HistoryTreeProjection`由Backend从initial Baseline、Submission、ReviewEvent/Projection、
BaselineNode/Head、ArchivePlan/Result和校验问题按请求组合，不是Dolt内部log的镜像。业务父边为
`based_on_baseline_node_id`；Repository parent commit只可作为技术诊断字段，不能替代业务边。

History包含所有成功Submission commit及其PENDING/APPROVED/REJECTED/
RETURNED_FOR_REVISION/WITHDRAWN review事实、ARCHIVED_BASELINE/CLOSED_NOT_ARCHIVED archive
disposition和archive eligibility issue。未来ruleset migration创建commit时必须登记为
`SYSTEM_MIGRATION`业务历史节点。未发布private candidate、失败import临时commit和operation
marker不属于业务History。每次结果、bundle和commit内容读取均重新检查当前session、scope和
permission；完整项目历史需要device/project audit权限。

## 7. Persisted 与 Derived 边界

明确禁止持久化：

- Workspace级可变计算阶段或派生upload-mode状态；UploadRevision冻结的
  `input_completeness`不是Workspace状态。
- 半完成 Submission。
- 中间审核状态、ArchiveExecution或archive状态副本。
- Baseline batch aggregate。
- Candidate entity/status/selection/tag。
- Archive dry-run 状态。
- 可从 immutable facts、events、Head 或 ArchiveResult 唯一推导的重复字段。

需要查询时由 owning application 建 projection；projection 不是新的业务事实来源。

## 8. 版本与兼容性

本 contract 是不兼容重构基线，不承诺读取 legacy persistence record。旧 Dolt repository 的迁移/兼容由独立 cutover gate 决定。任何新增持久状态必须证明无法从现有权威事实可靠派生，并由对应 domain owner 提升 semantic version。

## 9. 验收标准

- 每个对象、状态和 projection 能定位到上表唯一 owner。
- Upload、Preview、Submit、Review、Archive 的 generation、idempotency 和并发测试通过。
- Submit仅在requested/completed policy与全部T1 binding匹配后创建一个Submission；
  `NO_CANONICAL_CHANGE`无任何写effect。
- Review 测试中不存在单独 start action 或中间审核状态。
- Archive 只在 Start 时冻结，Candidate/PreviewArchivePlan 不落库。
- Archive直接引用所选既有commit；Repository `main`不移动且不产生重复commit。
- BaselineHead CAS、ArchiveResult、sibling disposition和Workspace占用在失败/重放后保持一致。
- 旧baseline sibling不能覆盖新baseline；再次采用必须从当前baseline重新Preview/Submit。
- rejected/withdrawn/returned/closed-not-archived节点可从授权History读取并按exact commit比较。
- 持久schema中不存在baseline batch、Candidate状态、ArchiveExecution或重复archive状态。

## 10. 关联文档

- [External Effect and Recovery](external-effect-and-recovery.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [ADR 0002](../adr/0002-minimal-persisted-business-state.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Repository Service](repository-service.md)
