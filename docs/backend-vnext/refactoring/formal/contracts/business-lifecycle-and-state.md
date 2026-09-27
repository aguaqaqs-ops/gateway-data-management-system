# Business Lifecycle and State Contract

状态：正式设计（Accepted）；`3.0.0` 固定业务 scope 归属补充已复审接受；`3.1.0` P5 架构收口补充于 2026-09-27 接受

阶段：Phase 0 结论；Phase 5 实现

Contract ID：`gateway-vnext.business-lifecycle-and-state`

Owner：各子领域 owner（见下表；本文不建立共同 aggregate）

Semantic version：`3.1.0`（Accepted 2026-09-27；前版 `3.0.0`）

2026-09-06 amendment：P5 设计收口后，Repository `main` 与业务 `BaselineHead` 明确分离；
Archive 直接把既有合格 Submission commit 提升为业务 Baseline，不移动 Repository ref、
不重新导入，也不再使用 external-effect execution 四态。Review 不创建或清理临时 ref。

2026-09-27 amendment（`3.1.0`）：随 [ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)–
[ADR 0021](../adr/0021-flow-neutral-comparison-entry.md) 接受，比较在规范域进行并使用运行期规则集；PreviewResult
绑定规范表集合与规范状态摘要；初始 BaselineNode 恒为空；Submit 写入上传的完整规范状态；项目身份异常以确认与
Archive 处置记录（§1A.2、§2–§6）。实现由 [P5 架构收口](../plans/p5-arch-closure-design.md) S1–S5 交付；交付前现行
源码仍按 `3.0.0` 行为运行，不将本补充表述为已实现。

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

<a id="repository-scope-ownership-amendment"></a>

## 1A. Repository 固定业务 scope 归属（Accepted）

状态：**ACCEPTED — 2026-09-20 独立复审通过**。接受依据见 [5D 文档审核记录](../plans/p5-5d-s0-independent-docs-acceptance.md)。

日期：2026-09-20。

Owner：Business Lifecycle Contract（跨领域身份/一致性）；Baseline Domain（初始归属事实）；
Provisioning Application / control-plane adapter（mapping 验证）。不建立新的共同 aggregate。

```yaml
amendment_kind: repository_fixed_business_scope
accepted_base_version: 2.0.0
accepted_contract_version: 3.0.0
content_agreed_by_repository_owner: yes
amendment_status: accepted
independent_amendment_review: pass
amendment_accepted: yes
p5_5d_s1_contract_precondition: satisfied
implementation_authorized: no
```

补充依据：原 §1 的 scope→Repository 正向映射与 Repository 唯一 BaselineHead，尚未排除
两个 scope 共用 Repository。Archive 按授权 scope 收集候选却推进共享 Head 时，可能遗漏另一
scope 的 approved sibling 和 Workspace release。V1 采用以下固定归属规则消除此歧义。
此处只收窄 Backend 业务映射，不改变 Repository Service 的通用 wire 或令其识别业务 scope。
本节及 §9A 随本次复审接受进入 `3.0.0`；相关 5D 设计同步接受。实现与迁移验收仍待后续阶段。

### 1A.1 Identity and cardinality

- 业务 scope 定义为 exact `(gateway_device_external_key, business_project_id)`；actor 不属于
  Repository 归属键。同 scope 多 actor 的 Workspace/Submission 合法，仍按各用例权限授权。
- 一个 Repository 从首次业务登记起，在整个业务历史中只属于一个固定 scope；不同 scope
  不得同时共享，也不得先后接管同一 Repository。即使两组 mapping 的 Head/node/commit 相同，
  也不能视为同一业务 scope。
- 保留一个 device 同时最多一个 active project mapping、一个当前 scope 解析到唯一 Repository
  的既有规则。同 scope 可改为绑定新的 Repository；新 Repository 必须未绑定过其他 scope，
  或已具有该 exact scope 的合法归属。旧 Repository 的归属与全部历史事实保持原样。
- 禁用、移除 mapping，或把 scope 的 mapping 改指新 Repository，都不释放旧 Repository 的
  固定归属。不得借删除/重建 mapping 绕过规则；禁止重写历史对象的 device/project/Repository。

### 1A.2 Authority and validation

固定归属由 Backend 初始 BaselineNode 的 immutable Repository/device/project identity 表达，
其业务事实不随 mapping 消失；不另建 owner registry、租约、tombstone 或归属状态机。初始
Baseline 登记与首次 mapping 建立在同一个 control DB 事务中完成；一个 Repository 只有一个
initial BaselineNode。Repository provisioning/initial commit 的真实性仍由既有 owner 负责，
不得靠 Archive 创建 commit 或猜测 main 来补归属。

初始 BaselineNode 引用的 commit 必须是没有用户表的空提交，即零表规范状态；物化时断言，不满足即
稳定失败。不支持预置数据的初始库，种子数据一律经 Submit 进入。

migration、首次 seed、批量 seed 和 mapping update 必须遵循同一业务验收规则：

1. 以 Repository 聚合输入、现存 mapping（包含 disabled）及已有初始归属；同时核对历史
   Workspace/Submission 等冻结 scope。一个 Repository 只能得到一个 exact scope。
2. 已有固定归属时只接受同 scope；没有归属事实但历史已存在时，只有在 migration 明确验证
   全部既有事实一致后，才能按其原身份接入初始 Baseline。不能选任一 mapping、采用最新记录、
   自动拆分 Repository，或把两个 scope 静默合并。
3. 任一跨 scope、无法解释的历史或初始归属冲突使整个 migration / seed 批次 / mapping update
   事务拒绝，无部分写入；失败不改既有 mapping、Head、历史或 schema migration 版本。
4. 同 scope 的重复 seed、禁用/启用、重启沿用合法身份，不覆盖已推进的业务 Head。读取当前
   scope 和验收 Archive 时仍核对固定归属；遗留矛盾明确失败，不能只在 candidate 查询中过滤。

具体 DDL、唯一索引和 INITIAL Node 接入由
[5D Design §6](../plans/p5-5d-archive-design.md#6-persistence-migration-and-initial-baseline) 细化；
本 Contract 只规定身份、原子拒绝和历史不变的语义。现有源码尚未实现此补充，不将文档确认
表述为已存在的 migration/seed 保障。

### 1A.3 Archive, authorization and reopen

在固定归属成立时，一个 Repository 的业务候选全集即其唯一 scope 的候选全集；拥有该 scope
Archive 权限的 actor 可覆盖其中其他 actor 的 Workspace。StartArchive 仍须按 §5 原子验收完整
候选集合、分类全部未选 approved sibling 并释放相关占用；不能通过扩大当前 actor 的权限跨
scope 收集数据来补救非法共享。

scope 改绑新 Repository 不隐式授予对旧 Repository 的历史读取权限，也不重写历史 scope；
每次访问仍遵守各用例当前权限及业务引用校验。本补充不新增历史授权 API。

若未来需要 Repository 跨 scope 共享或转交，必须先重开本 Contract，由相应 owner 定义候选
全集、权限范围、历史访问、sibling 处置、迁移及并发规则后再实现。撤掉唯一约束、将 mapping
设为 disabled 或由普通 Archive 命令“接管”都不是 V1 合法操作。

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
ruleset/contract version、Snapshot/Comparison digest、artifact closure，以及 MODIFIED 侧规范表集合
闭包与 CanonicalizationManifest 引用、上传 MODIFIED 侧与基线侧的规范状态摘要、投影所用规则集
digest、身份评估集摘要与逐 pair 的身份结论和执行模式的不可变绑定。
Preview接受时冻结这些身份，并创建固定三步Operation：
`materialize_inputs -> assemble_preview -> publish_preview`。Preview失败不使已接受revision
失败；旧generation不得覆盖current preview。新Upload采用latest-generation-wins：旧QUEUED
Preview进入`SUPERSEDED`，旧RUNNING Preview收到cooperative cancellation。

比较在规范域进行，比较语义使用运行期规则集：被规则丢弃的列与 SKIP 表不属于比较对象；只存不比的
表以表级事实呈现内容变化；列序不属于规范业务状态。规范投影失败（不支持的类型、键或表）使整个
Preview 失败，并一次列出全部失败项。

必需source/table/default pair/bundle closure缺失使整个Preview失败。`/comps/logic/logics.xml`
存在时是必需输入，解析失败或违反composite业务不变量使整个Preview失败；缺失时使用稳定的EMPTY来源。
其余可选table/XML/ordered/risk增强失败可发布READY及bounded diagnostics，不增加
`READY_WITH_WARNINGS`。发布前Workspace generation或BaselineHead CAS漂移时进入`SUPERSEDED`，
不创建PreviewResult或current pointer；发布后的Baseline漂移保留immutable结果，但使其
derived-stale，后续Submit必须拒绝；投影所用规则集与运行期不同亦然（§3）。

Upload与Preview是两个用例；接口可以组合调用，但identity、失败和重试语义不能合并。Upload
同步完成且不创建Operation；只有Preview执行状态属于Operation，不进入Workspace。

## 3. SubmitAttempt 与 Submission

`AcceptSubmit` 必须校验 expected revision、preview、业务baseline、idempotency 和占用。T1同时
冻结`business_baseline_commit_id`与当时Repository技术`main`的
`repository_expected_commit_id`；二者不得混用。若Preview的canonical business digest与当前
业务base相同，以`NO_CANONICAL_CHANGE`在创建Attempt前拒绝；不得创建Operation、Repository
request、Submission或BaselineNode。

canonical business digest 指规范状态摘要，由列序无关的业务 schema、行数与内容组成；业务 schema 不是
CanonicalizationManifest 中按 DDL 列序计算的每表 schema digest。`NO_CANONICAL_CHANGE` 指 PreviewResult
中上传 MODIFIED 侧与基线侧的规范状态摘要相等。Preview 的基线漂移，或其投影所用规则集与运行期不同，
都使 PreviewResult derived-stale，AcceptSubmit 拒绝。

Preview 含 `DIFFERENT_PROJECT` 或 `UNVERIFIABLE` pair 时，AcceptSubmit 必须携带对应的、彼此独立的
身份确认；确认记录随 Attempt 冻结，并复制到 Submission，不可变。

Attempt 在 T1 冻结 PreviewResult 的规范表集合与 CanonicalizationManifest。Submit 写入的内容就是上传的
完整规范状态，expected parent 中多出的表在新 commit 中删除。

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
Review 只读展示 Submission 的身份确认记录。
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
sequence派生。AnomalyResolution 包括身份异常 subject：带身份确认记录的 Submission 被选为归档
对象时，必须有带理由的肯定处置。

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

History 比较使用运行期规则集；节点的 commit 规范元数据提供存储身份与 provenance。比较始终按列名与
有效键对齐（[Canonical Storage](canonical-storage-and-repository-boundary.md) §7），schema 差异的来源
只依据两侧规则侧的存储事实标记。

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

§1A 的 `3.0.0` 收窄此前未禁止的跨 scope 共享/转交，可能拒绝既有配置，按不兼容
业务映射约束处理；不将其标成 `2.0.0` 已有规则。正式版本推进见
[独立复审接受记录](../plans/p5-5d-s0-independent-docs-acceptance.md)；不自动升级 SQLite schema、Repository wire、其他 Contract 或授权 production migration。

`3.1.0`（2026-09-27）按 [P5 架构收口 Entry Brief](../plans/p5-arch-closure-s0-entry-brief.md) §5 接受。新增的
持久事实（PreviewResult 的规范绑定与身份结论、Attempt 冻结的规范表集合与 manifest、身份确认记录、Archive
身份异常事件）都有明确 consumer；control DB 以前向 migration 增加，不做兼容回填。实现随收口 S1–S5 交付，
验收 owner 见[收口设计](../plans/p5-arch-closure-design.md) §12；交付前现行源码仍按 `3.0.0` 行为运行。

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

## 9A. 固定归属补充验收（Accepted）

以下是 §1A 的实施验收要求，当前未执行或宣称通过：

- migration 拒绝两个不同 scope 指向同 Repository，包括 identical Head 与 disabled mapping；
  既有历史 scope 冲突也必须拒绝，失败后原数据和 migration version 完整保留。
- 首次/批量 seed、mapping update 拒绝共享和跨 scope 转交，批次不能部分写入；原 mapping
  移走后仍通过 immutable initial identity 拒绝另一个 scope 接管。
- 同 scope 多 actor、合法重复 seed、禁用/启用、改绑新 Repository 正常；旧归属/历史不改写，
  重启不回退 Head，不隐式扩展旧 Repository 访问权限。
- Archive 遇归属矛盾 fail closed；合法 scope 的完整 candidate/sibling/release 继续满足 §5，
  无 Repository 写入、第二个 commit 或新增归属工作流。

唯一测试 owner 沿用 [5D Design §9](../plans/p5-5d-archive-design.md#9-verification-ownership)：
`test_archive_control_db_migrations.py` 拥有 migration/seed/update 归属矩阵，
`test_archive_queries.py` 拥有候选完整性拒绝，`test_archive_transactions.py` 拥有原子归档效果，
`test_archive_http.py` 拥有外部权限边界；不建立另一套 Contract 验证框架或重复矩阵。

本补充已复审接受，解除 5D S1 的这项 Contract 前置，但不是 S1 实现授权或 5D slice acceptance。
当前评审入口及其余三项 finding 的关闭依据见
[5D Entry Brief](../plans/p5-5d-s0-entry-brief.md)。

## 10. 关联文档

- [External Effect and Recovery](external-effect-and-recovery.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [ADR 0002](../adr/0002-minimal-persisted-business-state.md)
- [ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)–[ADR 0021](../adr/0021-flow-neutral-comparison-entry.md)
  与 [P5 架构收口设计](../plans/p5-arch-closure-design.md)（`3.1.0`）
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
- [Repository Service](repository-service.md)
