# Phase 0 Baseline and Oracle Discussion Notes

状态：Draft

阶段：Phase 0 - Baseline and Oracle

用途：记录 Phase 0 讨论过程中已确认的阶段性结论、待讨论问题和候选清单。本文不是正式 contract；Phase 0 结束后，应将最终结论重新整理到 `refactoring/formal/`，再将本文标记为 `Resolved` 或归档。

## 1. 讨论主题

```text
0A  Oracle 权威与兼容范围
0B  业务旅程和状态机清单
0C  Fixture 数据集设计
0D  Golden contract/digest/artifact
0E  性能和资源基线
0F  旧数据迁移与 intentional changes
0G  第一版简化范围
```

## 2. 0A 已确认结论

### 2.1 Oracle 权威顺序

已确认以下权威顺序：

```text
已确认的业务规则
  > 正式重构 contract / ADR
  > 当前目标业务文档
  > 现有 backend_vnext 可观测行为
  > 更早的旧系统实现和输出
```

解释：

- 旧代码只能证明当前实现做了什么，不能单独证明业务上必须这样做。
- 正式重构 contract/ADR 一旦与已确认业务规则冲突，应先修正文档，不能以文档优先级覆盖业务事实。
- 当前目标业务文档用于补充尚未进入正式重构 contract 的语义。
- 旧系统只作为行为、fixture、性能和人工体验 oracle，不继承其模块、DTO、路径和 cache 结构。

### 2.2 现有行为分类

已确认将现有行为划分为五类：

| 分类 | 处理方式 |
| --- | --- |
| 已确认业务规则与不变量 | 新实现必须保持。 |
| 已接受的正式 contract | 必须保持；变更需要正式 contract 更新或 ADR。 |
| 旧实现内部结构和技术字段 | 默认不兼容，不进入新设计。 |
| 已知旧 bug | 新实现修复，并记录 intentional change。 |
| 尚无法判断的行为 | 建立 fixture 和对照证据，讨论后再决定。 |

### 2.3 新旧差异分类

所有新旧结果差异必须归类为：

```text
MATCH
OLD_BUG
NEW_BUG
INTENTIONAL_CHANGE
UNRESOLVED
```

规则：

- `MATCH`：正式语义和关键结果一致；不要求 host path、内部 DTO 或 cache layout 一致。
- `OLD_BUG`：旧实现违反已确认规则，新实现结果作为目标，但必须保留证据。
- `NEW_BUG`：新实现违反已确认规则或正式 contract，阻塞对应 Slice/Phase 退出。
- `INTENTIONAL_CHANGE`：经过明确决策的语义变化，必须记录影响、迁移和验收更新。
- `UNRESOLVED`：证据不足；不能进入正式 contract，也不能作为切流通过项。

### 2.4 Oracle 使用约束

- 不直接以旧 payload 全字段相等作为通过标准，先区分 core fact、derived projection、adapter-only 和 removed 字段。
- 不以旧文件路径、临时 ID、时间戳、日志文本或输出顺序作为 oracle，除非对应 contract 明确要求稳定。
- Digest 对照必须先确认双方使用同一 semantic contract、scalar encoding、排序和版本。
- 性能结果不能决定业务正确性；只有 validation passed 的结果进入性能比较。
- 人工判断必须转化为 fixture、规则说明或 intentional change 记录，不能长期只存在于口头结论。

### 2.5 已确认：简化也是 Phase 0 目标

Phase 0 不只建立旧行为 baseline，还必须主动审查哪些现有状态、功能和优化不应进入重构第一版。

简化原则：

```text
能由稳定事实推导的，不重复持久化
能由 Operation 表达的，不进入 Domain 状态
没有真实调用方的，不提前发布 contract
没有 benchmark 依据的优化，不进入第一版
同一业务事实只保留一个 owner
```

现有范围统一分类为：

```text
KEEP       保持业务能力和正式语义
SIMPLIFY   保持能力，但减少状态、步骤、传输或重复事实
DEFER      第一版不实现，记录重新进入条件
REMOVE     不进入新架构，也不提供兼容出口
```

每项简化必须记录：

- 被保留的业务事实和用户结果。
- 被删除的状态、接口、provider 或优化。
- 失败恢复、审计和数据保留是否仍完整。
- 是否属于 intentional change。
- 后续重新引入的触发条件（如有）。

## 3. 0B 业务旅程分层（部分确认）

以下是根据现有文档和代码提取的旅程清单。Upload/Preview 边界已形成阶段性结论，其余部分仍待确认。

### 3.1 一级：端到端主旅程候选

```text
initialize BaselineNode/BaselineHead
  -> create/select workspace
  -> Workspace Source Upload
  -> Upload Preview
  -> accept submit
  -> finalize repository commit
  -> review
  -> StartArchive/promote mainline
  -> create successor BaselineNode/advance BaselineHead
  -> history compare
```

主旅程用于端到端验收，但不意味着所有节点属于同一个 aggregate 或事务。

已确认 `Workspace Source Upload` 是显式业务旅程节点；它处于 Workspace change lifecycle 范围内，但不能因上层名称而在 baseline、fixture 和状态讨论中被省略。`Upload Preview` 是消费已接受输入 revision 的独立用例，即使第一版 HTTP API 将二者同步组合。

### 3.2 二级：业务分支候选

- Initial-only、modified-only 和 initial+modified upload 模式。
- Preview 后重新上传、generation supersede 和过期 submit。
- Submit acceptance 拒绝、finalize 最终失败和安全重试。
- Review 的 approve、reject、withdraw 和 approved 后 return。
- Reject/withdraw 后 Workspace 重新开放和 mutable ref release。
- Archive candidate 来源：approved、rejected、withdrawn、preview、initial-only。
- Archive confirmation：candidate 或 discarded。
- Anomaly resolution、override、只读 plan preview 和正式 archive start。
- Archive CAS conflict、archive frozen 和 transfer failure。
- History compare 的 2-node、3-node/dual-pair 和缺失/损坏 summary。

### 3.3 三级：执行机制候选

以下默认不作为独立业务旅程，而作为主旅程的执行/优化场景：

- Precommit warmup。
- Provisional/canonical cache completion 和 promotion。
- Operation retry、cancel、lease timeout 和 worker takeover。
- Capability 内部表级并行。
- Repository Service import operation 和 writer lease。
- Artifact cleanup、cache eviction 和 GC。

若其中某项产生用户可见业务状态或不可逆事实，需要重新提升为业务分支讨论。

### 3.4 已确认：Upload 与 Preview 边界

#### 三类独立身份

已确认后端概念上区分：

```text
SourcePackageArtifact
  immutable content identity and bytes

WorkspaceUploadRevision
  workspace input selection/generation

PreviewOperation
  one compute attempt over one revision
```

规则：

- Source artifact 以内容 digest 标识，可以被多个 revision 复用。
- UploadRevision 表达用户为 Workspace 选择的一版输入，不等同于 Repository commit 或 Submission。
- PreviewOperation 表达一次解析、Snapshot、Comparison、Risk、Surface/Bundle 计算尝试。
- Preview 失败不把已经校验并接受的 UploadRevision 标记为失败。
- Upload 接收、解压或格式校验在形成有效 revision 前失败时，不产生正式 UploadRevision。

#### Upload 与 Preview 用例

概念上保持两个用例：

```text
UploadWorkspaceSource
  -> receive/stage bytes
  -> validate SourcePackage
  -> persist/reuse source artifact
  -> create WorkspaceUploadRevision
  -> advance upload generation

BuildUploadPreview
  -> consume WorkspaceUploadRevision
  -> materialize/compare/evaluate/assemble
  -> publish PreviewInputBinding
```

第一版接口可以组合调用二者，但 contract、identity、失败和重试语义保持分离。

#### 后端恢复与前端交互

已确认采用：

```text
backend recoverability
  + minimal frontend interaction
```

- 后端保留 revision、checkpoint、`retry_of`、自动重试和 worker takeover 能力。
- Operation Runtime 优先自动处理 retryable failure 和 lease takeover。
- 后端可以内部复用同一 UploadRevision 重启 PreviewOperation，用于自动恢复、运维、故障注入或系统修复后重算。
- 第一版前端不提供单独的“重试预览”入口。
- 第一版不为尚不存在的调用方发布公共 `RetryPreview` API。
- 自动恢复耗尽后，用户可以沿用“重新上传”作为重新开始流程的操作。

#### 重新上传语义

重新上传是新的用户意图，不根据文件 digest 推断为 operation retry：

```text
same idempotency key
  -> same request replay
  -> return existing revision/operation

new user action / new idempotency key
  -> new UploadRevision
  -> new upload generation
  -> new PreviewOperation
```

即使 source digest 相同，新的用户上传动作也可以创建新 revision/generation；ArtifactStore 应复用相同 SourcePackageArtifact bytes，避免服务端重复存储。旧 PreviewOperation 在发布前必须检查 expected generation/revision，发现新上传后只能 supersede，不能覆盖最新 Preview。

#### 第一版不做

- 不增加前端 Retry/Replace 两个并列操作。
- 不让用户选择 retry policy 或查看内部 step。
- 不根据相同 digest 自动猜测用户是 retry 还是 replace。
- 不无限保留失败 Preview 对应的 revision；具体 TTL/retention 在 artifact/Workspace lifecycle 讨论中决定。
- 不将 `UPLOADING`、`PARSING`、`COMPARING` 等 operation 状态加入 Workspace 业务状态。

#### 后续触发公共 Retry 能力的条件

出现以下真实需求后，再讨论公共 Retry API/前端入口：

- 文件较大，重复传输成本显著。
- Preview 失败导致较多重复上传或支持事件。
- 用户需要在服务修复/provider 切换后自行重算。
- 前端已经具备稳定 operation polling 和失败动作模型。

是否发布公共 retry contract 是后续产品/API 决策，不影响后端保持 UploadRevision 与 PreviewOperation 分离。

### 3.5 已确认：第一版模型与功能简化

#### Workspace 状态

Workspace 只持久化最小生命周期：

```text
OPEN
CLOSED
```

并保存稳定关系：

```text
current_input_revision_id optional
current_preview_id optional
active_submission_id optional
closed_at optional
```

`EMPTY / INPUT_READY / PREVIEW_READY / SUBMITTED / CLOSED` 作为 read-model label 从上述事实推导，不作为多个模块共同推进的 Domain 状态。Upload、Preview 和 Submit 的 operation 状态不得进入 Workspace enum。

#### Input roles 与 upload mode

`WorkspaceInputRevision` 使用 source roles 表达输入：

```text
sources:
  - role: INITIAL
    artifact_ref: ...
  - role: MODIFIED
    artifact_ref: ...
```

Initial-only、modified-only 和 initial+modified 由 role 集合推导，不持久化一套独立 upload mode 状态机。

#### PreviewResult 与 Submit

`PreviewInputBinding` 收敛为不可变 `PreviewResult`，至少绑定：

```text
preview_id
workspace_id
input_revision_id
input/source digest
snapshot/comparison digests
ruleset/contract versions
bundle/artifact closure refs
created_at
```

Submit 使用 `expected_input_revision_id + expected_preview_id` 做一致性校验，并直接复用 Preview 对应的 immutable SourcePackageArtifact，不要求用户再次上传完整 package。Workspace source artifact 在 submit 成功时从 workspace retention 提升为 submission durable，优先只修改 retention metadata，不复制内容。

#### SubmitAttempt 与 Submission

Submit acceptance 只创建 `SubmitAttempt`/Operation。Repository import、commit 和 readback validation 成功后才创建正式 `Submission`；失败的 attempt 不产生半完成 Submission。Finalize 完成前，调用方使用 operation/attempt ID；是否另设业务受理号后续按真实审计需求决定。

#### Workspace 占用与重新开放

Workspace 使用两个显式关系区分执行期占用和业务期占用：

```text
active_submit_attempt_id optional
active_submission_id optional
```

已确认规则：

- Submit acceptance 原子设置 `active_submit_attempt_id`；该 attempt 有效期间禁止重新上传和重复 Submit，不支持新上传 supersede 正在执行的 Repository 写入。
- Retryable failure、worker takeover 和 Repository reconciliation 期间保持 attempt 占用。
- 明确 final failure 且确认没有未决 Repository 写入后清除 attempt；结果不确定时保持占用直到 reconciliation。
- Finalize 成功时原子创建 Submission，并将 `active_submit_attempt_id` 替换为 `active_submission_id`。
- APPROVED Submission 保持 Workspace 占用，直到对应 ArchiveResult 推进 BaselineHead。
- REJECTED、WITHDRAWN 或 `RETURNED_FOR_REVISION` 清除 active submission、current input 和 current preview，但保留历史 revision、preview、submission、artifact 和 repository commit 供审计。
- Workspace 重新开放后通过新 UploadRevision 重新开始；相同 source bytes 可以复用 content artifact。
- Workspace CLOSED 后不 reopen；需要继续修改时创建新的 Workspace。

Submit acceptance 和 finalize 的 Workspace/attempt/submission 变更必须由同库事务或 outbox 保证，不能依赖“先创建 Operation、保存 Workspace 失败后再尽力删除”的补偿模式。

#### Submission Review 与批准后退回

已确认删除 `START_REVIEW / IN_REVIEW`。审核状态简化为：

```text
PENDING
APPROVED
REJECTED
RETURNED_FOR_REVISION
WITHDRAWN
```

允许转换：

```text
PENDING -> APPROVED
PENDING -> REJECTED
PENDING -> WITHDRAWN
APPROVED -> RETURNED_FOR_REVISION
```

`REJECTED` 与 `RETURNED_FOR_REVISION` 保持不同语义：前者表示首次审核不通过，后者表示已批准但在归档执行冻结前被审核人退回修改。退回必须记录 reason。

审核变化使用不可变事件保存审计历史：

```text
SubmissionReviewEvent
  event_id
  submission_id
  action: APPROVE | REJECT | WITHDRAW | RETURN_FOR_REVISION
  actor_id
  reason optional/required by action
  occurred_at
  previous_state
  resulting_state
```

Submission 可以保存受乐观锁保护的 `current_review_state + review_version` 作为当前投影，但事件是审核历史事实。Application 内部使用明确命令 `ApproveSubmission / RejectSubmission / WithdrawSubmission / ReturnApprovedSubmission`，不以任意 action string 作为内部稳定 contract。

退回后旧 Submission 保持不可变并失去 archive eligibility；后续上传、Preview 和 Submit 创建新的 Submission，不修改旧 Submission 的 source/commit。

绑定旧 Submission/candidate 的 archive confirmation 保留为历史审计记录，但不再计入当前 confirmation set；新 Submission 进入候选集合后必须重新确认。退回通过 review/candidate/confirmation digest 变化使已预览的 ArchivePlan 自动失效，不依赖物理删除旧 confirmation。

#### 第一版删除/推迟的优化

第一版不实现：

```text
Precommit Warmup flow
shadow repository import
provisional comparison cache promotion/rekey
multiple formal repository import providers
generic Operation DAG
frontend Retry Preview action/public retry API
stateful Archive Dry-run
mutable persisted ArchiveSelection before execution
public Archive cancel/retry API
```

说明：

- Preview 走正常计算；Submit 走一次正式 Repository import/readback。
- Repository import 第一版只有一个经过验证的 production provider；其他 provider 只作为 benchmark/spike，不进入正式 contract。
- Operation 第一版只支持固定顺序 step；需要独立恢复的并行任务必须由 benchmark 和业务进度需求证明。
- Cache、warmup、并行和 provider 扩展在正确性路径稳定后，按 Phase 7 的 benchmark 门禁重新进入。
- Archive 只提供纯读 plan preview 和正式 start；不为 Dry-run 建立 freeze/cancel/timeout 状态机。
- Archive 接受后使用同一 ArchiveExecution 自动重试、worker takeover 和 reconciliation，不向前端暴露 cancel/retry 竞争语义。

#### BaselineNode 与 BaselineHead

已确认删除独立 `BaselineBatch` 聚合、Batch open/close/invalidate 命令和 Batch 状态。不能删除的是本轮提交的作用域身份；原 `batch_id` 语义替换为 `base_baseline_node_id`。

`BaselineNode` 是不可变主线版本节点：

```text
BaselineNode
  baseline_node_id
  baseline_scope_id
  repository_id
  commit_hash
  parent_baseline_node_id optional
  generation
  created_at
```

已确认规则：

- `baseline_scope_id` 第一版对应一个 Gateway Device 及其唯一 Repository mainline。
- node ID 使用 UUID/ULID，不使用 commit hash；未来即使需要相同 commit 的后继代次也不会发生身份冲突。
- 同一 scope 只有一个 root；非 root 节点必须绑定同 scope、同 repository 的 parent，第一版保持线性历史。
- genesis 节点必须绑定 Repository Service 创建的真实初始 commit，不再使用 `vnext-empty-main:*` 一类伪 commit。
- 第一版不支持“无内容变化但强制推进代次”；没有成功 mainline CAS 就不创建后继节点。
- Node 不持久化 `OPEN/CLOSED/INVALIDATED/current` 或 archive gate；是否为当前节点由 Head 派生。
- BaselineNode 只表示 mainline；initial history 作为 ArchiveResult 的不可变子记录，不能成为 Head。

`BaselineHead` 是每个 scope 唯一的最小可变指针：

```text
BaselineHead
  baseline_scope_id
  current_baseline_node_id
  updated_at
```

Head 不复制 commit、generation 或状态。`current_baseline_node_id` 本身作为 CAS token：

```text
UPDATE baseline_head
SET current_baseline_node_id = :target
WHERE baseline_scope_id = :scope
  AND current_baseline_node_id = :expected_source
```

更新行数必须为一；否则只能返回已有幂等结果或进入一致性故障处理，不能覆盖推进。

#### ArchiveResult 权威事实

以不可变 `ArchiveResult` 作为归档成功的权威事实，至少记录：

```text
archive_result_id
archive_execution_id
archive_plan_id
archive_plan_digest
baseline_scope_id
source_baseline_node_id
target_baseline_node_id
repository_id
main_ref
old_main_commit
new_main_commit
repository_operation_id
repository_request_digest
selected_mainline_submission_id
requested_by_actor_id
mainline_advanced_at
recorded_at
```

initial history 作为 Result 聚合内的不可变子记录：

```text
ArchiveResultHistoryEntry
  history_node_id
  archive_result_id
  source_workspace_id
  source_submission_id
  commit_hash
  resolution_id optional
```

约束：

- 只有确认 Repository main CAS 成功后才能创建 Result；失败只属于 ArchiveExecution。
- 一个 source BaselineNode、target BaselineNode 和 ArchiveExecution 各自最多关联一个 Result。
- old/new commit 必须分别等于 source/target BaselineNode 的 commit。
- Result 不包含 transfer/post-processing 状态；CAS 成功与后置 transfer 失败是正交事实。
- Submission、Candidate 和 Workspace 的归档展示结果从 ArchiveResult/HistoryEntry 派生，不批量复制同一状态。
- Node 不反向强制引用 Result；Result 单向引用 target node，避免循环外键。
- `mainline_advanced_at` 是 Repository CAS 实际时间，`recorded_at` 是业务数据库完成 Finalize 的时间。
- Confirmation、anomaly resolution 和 override 暂不删除，待业务规则/fixture 审查后决定是否简化。

#### ArchivePlan

Archive preview 与启动采用两个操作：

```text
PreviewArchivePlan   pure read, no lock
StartArchive         validate, persist plan/execution, freeze
```

`PreviewArchivePlan` 根据当前 confirmations、approved submissions、candidate selection 和 main commit 计算 proposed plan 与 `plan_digest`：

- 不持久化 ArchivePlan。
- 不冻结 Review/Candidate/Workspace。
- 允许反复调用。
- APPROVED Submission 在此阶段仍可被 `ReturnApprovedSubmission` 退回。
- Candidate selection 由 preview/start 请求携带，不在执行前维护一份 mutable persisted selection。

Start 时持久化的 `ArchivePlan` 不可变且没有生命周期状态：

```text
ArchivePlan
  contract_version
  archive_plan_id
  baseline_scope_id
  source_baseline_node_id
  expected_main_commit
  selection_items[]
  subject_set_digest
  review_set_digest
  confirmation_set_digest
  resolution_set_digest
  archive_policy_version
  plan_digest
  created_at

ArchivePlanSelectionItem
  role: MAINLINE | INITIAL_HISTORY
  workspace_id
  submission_id
  review_version
  selected_commit
  candidate_digest
```

Plan 必须恰好包含一个 `MAINLINE`，可以包含零到多个 `INITIAL_HISTORY`。所有 selection item 必须属于同一 source BaselineNode。`plan_digest` 使用 canonical serialization，覆盖 selection 和所有业务事实/policy version，但排除 plan ID、created_at、actor 和展示文本；items 按 `role + submission_id` 排序。Preview 和 Start 必须复用同一 digest 实现。

`subject_set_digest` 覆盖当前 BaselineNode 下需要归档决策的 Workspace/Submission 集合；新增 Workspace、退回后新 Submission 或 discard 变化必须使旧 preview plan 失效。

`StartArchive` 接收 selection、`expected_plan_digest`、`expected_source_baseline_node_id` 和 idempotency key，并在业务数据库事务中：

```text
lock BaselineHead
  -> verify current node == expected source node
  -> recompute current plan
  -> compare expected_plan_digest
  -> validate review/candidate/confirmation/resolution facts
  -> verify no active ArchiveExecution
  -> persist immutable ArchivePlan
  -> persist PREPARED ArchiveExecution
  -> persist operation/outbox
```

`StartArchive` 是批准后退回的截止边界。退回发生在 Preview 与 Start 之间时，会改变 review version、candidate/confirmation set 和 plan digest；旧 Start 请求返回 `ARCHIVE_PLAN_STALE`。Start 成功后退回返回 `ARCHIVE_IN_PROGRESS`。

所有会改变 archive facts 的命令必须在短事务中锁同一 BaselineHead 并检查 active ArchiveExecution；不需要在 BaselineNode、Submission 或 Candidate 上复制 freeze 状态。

#### ArchiveExecution

`ArchiveExecution` 不复制 Operation 的 queue/lease/step 状态，只拥有外部 mainline 副作用确定性、业务冻结、幂等和 reconciliation：

```text
ArchiveExecution
  contract_version
  archive_execution_id
  archive_plan_id
  operation_id
  baseline_scope_id
  source_baseline_node_id
  planned_target_baseline_node_id
  planned_archive_result_id
  requested_by_actor_id
  start_idempotency_key
  start_request_digest
  repository_idempotency_key
  repository_request_digest
  repository_operation_id optional
  state
  attention_code optional
  failure_code optional
  repository_before_commit optional
  repository_after_commit optional
  repository_applied_at optional
  created_at
  updated_at
  finalized_at optional
  aborted_at optional
  version
```

Start 和 Repository 分别使用独立幂等键。重复 start key + 相同 request digest 返回原 Execution；相同 key + 不同 digest 返回 `IDEMPOTENCY_KEY_REUSED`。Repository key 由 Execution ID 确定性生成，worker retry/takeover 不创建新的业务 Execution。

Execution 状态收敛为：

```text
PREPARED
  -> EFFECT_PENDING
      -> EFFECT_CONFIRMED
          -> FINALIZED

PREPARED       -> ABORTED
EFFECT_PENDING -> ABORTED
```

`PREPARED / EFFECT_PENDING / EFFECT_CONFIRMED` 都是 active/frozen；`FINALIZED / ABORTED` 是终态并释放 execution freeze。只有取得匹配 repository idempotency key、request digest、before/after commit 的成功 operation evidence，才能进入 `EFFECT_CONFIRMED`。只有证明 Repository 副作用未发生且不会再执行，才能进入 `ABORTED`；timeout、网络异常或 Operation failure 不足以解除冻结。

不增加单独 `RECONCILIATION_REQUIRED` 状态；reconciliation 是 `EFFECT_PENDING` 下的处理方式。需要人工关注时使用稳定 attention code，例如：

```text
REPOSITORY_OUTCOME_UNKNOWN
MAIN_REF_DRIFT
REPOSITORY_OPERATION_MISSING
FINALIZATION_RETRY_REQUIRED
```

Operation 只拥有 `QUEUED/RUNNING/READY/FAILED_*`、worker lease、step retry 和 diagnostics。Operation 失败不等于 ArchiveExecution 已终止；即使 Operation 显示 `FAILED_FINAL`，只要 Execution 仍 active，就不得允许退回或新的 StartArchive。Operation `READY` 要求 Execution 已 `FINALIZED` 且 ArchiveResult 可读。

#### Archive 事务与 reconciliation

业务侧与 Repository Service 不使用分布式事务：

```text
T1 StartArchive
  lock Head
  validate/recompute plan
  insert Plan + PREPARED Execution + outbox

T2 Before Repository Call
  PREPARED -> EFFECT_PENDING
  persist repository request digest

External Repository Service
  CompareAndSetRef(main, expected commit, target commit, idempotency key)

T3 Confirm And Finalize
  validate repository operation evidence
  EFFECT_PENDING -> EFFECT_CONFIRMED
  insert target BaselineNode
  insert ArchiveResult/history entries
  CAS BaselineHead source -> target
  EFFECT_CONFIRMED -> FINALIZED
  insert MainlineAdvanced outbox
```

T3 的业务事实必须在同一个业务数据库事务中提交。正常路径可以在同一事务内完成 CONFIRMED 到 FINALIZED；中间状态用于 CAS 已成功但 Finalize 需要恢复的情况。后置 transfer、cache 和统计失败不能回滚 ArchiveResult 或 BaselineHead。

Reconciler 按以下证据顺序处理：

1. ArchiveResult 已存在时修正 Execution 为 `FINALIZED`。
2. Repository journal 存在匹配 request digest 的成功记录时执行 Finalize。
3. Repository operation 仍在运行时保持 `EFFECT_PENDING`。
4. operation 不存在且 main 仍为 source 时，使用同一幂等键安全重发。
5. main 为 target 但没有匹配 journal 时不能猜测本次成功，进入人工关注。
6. main 为其他 commit 时记录 `MAIN_REF_DRIFT` 并保持冻结。
7. 只有 journal 证明请求最终无副作用且 main 仍为 source 时，才允许 `ABORTED`。

不提供正常业务上的 Baseline/Batch invalidate。Repository 漂移通过 Execution attention 与受审计运维修复处理，不修改或作废不可变 BaselineNode。

#### History Compare

History Compare 第一版默认是只读 Operation + artifact closure，不建立额外复杂业务状态机。只有长期保存、分享或审计某次比较成为真实需求时，才引入持久 `HistoryComparisonResult`。

#### 简化决策汇总

| 项目 | 第一版决策 |
| --- | --- |
| Workspace 阶段状态 | `SIMPLIFY`：只持久化 OPEN/CLOSED 与事实引用，其余派生。 |
| Upload mode | `SIMPLIFY`：从 source roles 派生。 |
| Preview binding | `SIMPLIFY`：收敛为 immutable PreviewResult。 |
| Submit package | `SIMPLIFY`：复用 Upload artifact，不重复上传。 |
| Submission 创建 | `SIMPLIFY`：Finalize 成功后创建。 |
| Precommit warmup/provisional promotion | `DEFER`：Phase 7 由 benchmark 决定。 |
| Repository import providers | `SIMPLIFY`：第一版一个 production provider。 |
| Operation DAG | `DEFER`：第一版顺序 step。 |
| Baseline Batch | `REMOVE`：以不可变 BaselineNode + 最小 BaselineHead 取代。 |
| Batch/Baseline invalidate | `REMOVE`：不提供正常业务作废功能。 |
| Archive 状态复制 | `SIMPLIFY`：ArchiveResult 为权威。 |
| Submission Review | `SIMPLIFY`：删除 START_REVIEW/IN_REVIEW，使用审核事件和当前投影。 |
| Approved 后退回 | `KEEP`：归档 Start 前允许 RETURNED_FOR_REVISION，并重新开放 Workspace。 |
| Archive Dry-run | `SIMPLIFY`：纯读 PreviewArchivePlan，不持久化、不冻结。 |
| Archive selection | `SIMPLIFY`：由 Preview/Start 请求携带，Start 时固化进 ArchivePlan。 |
| Archive Execution 状态 | `SIMPLIFY`：五个单向状态，不建立独立 reconciliation 状态。 |
| Archive cancel/retry | `REMOVE`：无公共入口，使用同一 Execution 自动恢复。 |
| 无变化代次推进 | `REMOVE`：第一版没有成功 mainline CAS 就不创建后继 BaselineNode。 |
| History Compare 状态机 | `SIMPLIFY`：默认 operation/artifact。 |

## 4. 0B 状态对象（部分确认）

### Workspace

当前实现状态：

```text
EMPTY
INITIAL_READY
PREVIEW_READY
SUBMITTED
CLOSED
```

已确认简化为持久 `OPEN/CLOSED` 生命周期与事实引用；上述其余名称仅可作为 read-model label。SubmitAttempt/APPROVED Submission 占用 Workspace；REJECTED、WITHDRAWN、RETURNED_FOR_REVISION 清除当前输入/预览和占用并重新开放；对应 ArchiveResult 推进 BaselineHead 后关闭旧 Workspace，CLOSED 不 reopen。

### Submission Review

当前实现状态：

```text
PENDING_REVIEW
IN_REVIEW
APPROVED
REJECTED
WITHDRAWN
```

Submission archive 结果当前单独建模：

```text
NOT_ARCHIVED
ARCHIVED_AS_MAINLINE
ARCHIVED_AS_HISTORY
CLOSED_NOT_ARCHIVED
```

已确认删除 `IN_REVIEW`，目标审核状态为 `PENDING / APPROVED / REJECTED / RETURNED_FOR_REVISION / WITHDRAWN`。Review 与 Archive 结果保持正交；Review 使用不可变事件和当前投影，ArchiveResult 为归档权威。REJECTED/WITHDRAWN/RETURNED 均重新开放 Workspace；APPROVED 保持占用直到对应 ArchiveResult 推进 BaselineHead。

### Baseline Node/Head

已确认删除 BaselineBatch 及其状态机。目标对象为：

```text
BaselineNode   immutable mainline version
BaselineHead   current node pointer
```

当前/历史语义从 Head 指针派生：

```text
node_id == head.current_baseline_node_id   CURRENT
node_id != head.current_baseline_node_id   HISTORICAL
```

`READY_FOR_ARCHIVE` 从 subjects/reviews/confirmations/resolutions 派生；Operation 表达执行进度；ArchiveExecution active 状态表达冻结；ArchiveResult 表达成功。不在 Node 或 Head 上复制这些状态。

### Archive Candidate/Execution

Candidate 结果候选：

```text
NOT_ARCHIVED
ARCHIVED_AS_MAINLINE
ARCHIVED_AS_HISTORY
CLOSED_NOT_ARCHIVED
```

已确认 Execution 状态：

```text
PREPARED
EFFECT_PENDING
EFFECT_CONFIRMED
FINALIZED
ABORTED
```

已确认 mainline CAS、业务 Finalize 和后置 transfer 是正交事实；不再以 `SUCCEEDED_TRANSFER_FAILED` 作为单一权威业务结果。Candidate 展示状态优先从 ArchiveResult 派生，具体 confirmation/anomaly/candidate lifecycle 仍待讨论。

## 5. 后续待讨论

0B 建议依次确认：

1. Confirmation 和 AnomalyResolution 如何绑定 BaselineNode、subject version 和 Plan digest。
2. Confirmation 在 RETURNED、新 Submission、discard 和旧 Workspace 历史化后的失效/重建规则。
3. Archive Candidate 是否需要持久 entity，还是优先作为 policy projection/selection item。
4. Submit、Review、Archive 的拒绝、可重试失败和最终失败 reason taxonomy。
5. 哪些异常分支必须进入 Phase 0 fixture/golden 覆盖。

0B 收口前，不把当前 enum 名称直接提升为重构后的正式 domain contract。
