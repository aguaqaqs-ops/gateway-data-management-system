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
- 旧系统只作为行为、fixture 和人工体验 oracle，不继承其模块、DTO、路径和 cache 结构，也不作为新设计的性能 benchmark 对比基线。

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
- Archive subject 来源：approved Submission 或显式 discard；Candidate 从 approved Submission 事实派生。
- Archive confirmation：include approved Submission 或 discard Workspace。
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

`SubmitAttempt` 与 `ArchiveExecution` 使用相同的最小 external-effect 状态形状，但保持为独立业务对象，不建立通用 `ExternalEffectExecution` aggregate 或继承层次：

```text
PREPARED
  -> EFFECT_PENDING
      -> FINALIZED

PREPARED       -> ABORTED
EFFECT_PENDING -> ABORTED
```

状态含义：

- `PREPARED`：Submit 已被接受、Workspace 已被占用，但尚未跨越 Repository 调用边界。
- `EFFECT_PENDING`：Repository 请求可能尚未发送、正在执行、结果未知，或者已经成功但 readback/业务 Finalize 尚未完成。
- `FINALIZED`：Submission 已创建，Workspace 占用已从 Attempt 原子切换到 Submission。
- `ABORTED`：已证明本次 Repository 副作用不存在，并保证原请求不会再继续执行。

不增加 `EFFECT_APPLIED / RECONCILING / ATTENTION_REQUIRED` 状态。Repository operation journal/evidence 证明 effect，稳定 attention/failure code 表达人工关注，Operation Runtime 仍只拥有 queue、worker lease 和 step retry。

`SubmitAttempt` 至少固化：

```text
contract_version
submit_attempt_id
operation_id
workspace_id
source_baseline_node_id
source_baseline_commit
input_revision_id
preview_id
source_artifact_ref
source_artifact_digest
submit_idempotency_key
submit_request_digest
repository_idempotency_key
repository_request_digest optional
repository_operation_id optional
repository_after_commit optional
readback_manifest_digest optional
state
attention_code optional
failure_code optional
submission_id optional
created_at / updated_at / finalized_at / aborted_at
version
```

Attempt 保存的是 acceptance 时的不可变输入/baseline 绑定和最小 recovery evidence，不复制完整 Preview payload、Repository catalog 或 Operation step 状态。`Submission.submit_attempt_id` 必须唯一；重复 Finalize 先返回已有 Submission，再修正 Workspace/Operation 投影。

#### Submit 事务边界

Submit 不与独立 Repository Service 使用分布式事务，使用三个业务边界：

```text
T1 AcceptSubmit
  lock Workspace/BaselineHead
  validate revision + preview + baseline binding
  validate idempotency and repository occupancy
  insert PREPARED SubmitAttempt + Operation + outbox
  set Workspace.active_submit_attempt_id

T2 BeforeRepositoryCall
  reload and validate Attempt
  persist repository idempotency key/request digest
  PREPARED -> EFFECT_PENDING
  call Repository SubmitImport

T3 FinalizeSubmit
  validate matching Repository success evidence
  validate readback manifest
  insert Submission with unique submit_attempt_id
  swap active_submit_attempt_id -> active_submission_id
  EFFECT_PENDING -> FINALIZED
  insert SubmissionCreated outbox
```

T1 和 T3 各自在一个业务数据库事务中完成。T2 必须在发起 Repository 请求前持久化幂等键和 request digest；否则 worker 在调用边界崩溃后无法安全判断重发或对账。第一版只要 Attempt 尚未 `FINALIZED/ABORTED`，就继续占用对应 `repository:{repository_id}` serialization key；完整性故障可能阻塞整个 Repository，但避免引入隔离 commit、过期 Attempt 和旧 Baseline 恢复等额外状态机。

`ABORTED` 必须通过一个短事务设置终态、CAS 清除 `active_submit_attempt_id`、释放 serialization key 并写审计/outbox。输入引用按 recovery 处理：

- `NEW_USER_INPUT`（例如明确的 `SUBMIT_IMPORT_REJECTED`）同时清除 Workspace current input/preview，历史 revision、preview、attempt 和 artifact 仍保留，用户通过新上传重新开始。
- 已证明无副作用的技术性运维终止可以保留 current input/preview，允许重新发起 Submit。
- `effect=UNKNOWN/APPLIED` 时禁止 `ABORTED`；Operation 为 `FAILED_FINAL` 也不是解除占用的证据。

#### Submit reconciliation 决策

Submit reconciler 使用 Repository evidence，而不是 Python exception 或 Operation 终态作出决定：

| 观察事实 | Effect | Attempt/占用 | 动作 |
| --- | --- | --- | --- |
| durable source artifact 缺失 | `NONE` | `PREPARED`，保持占用并 attention | 修复 artifact 后继续原 Operation，或证明不会执行后审计 ABORT。 |
| Repository 明确暂时不可用 | `NOT_APPLIED` | `EFFECT_PENDING`，保持占用 | 同一 Operation、同一 Repository 幂等键重试。 |
| Repository 明确拒绝输入 | `NOT_APPLIED` | 进入 `ABORTED` | 清除 current input/preview，要求新 UploadRevision。 |
| Repository operation 仍在运行 | 未决 | `EFFECT_PENDING`，保持占用 | 等待或 worker takeover，不重发。 |
| journal 明确证明未应用 | `NOT_APPLIED` | `EFFECT_PENDING`，保持占用 | 原 Operation 安全重发；确认原请求不会执行后也可 ABORT。 |
| journal 证明已应用 | `APPLIED` | `EFFECT_PENDING`，保持占用 | 跳过 import，继续 readback 和 Finalize。 |
| 只能看到 commit、没有匹配 journal | `UNKNOWN` | `EFFECT_PENDING`，保持占用并 attention | 不凭 commit 猜测本次成功，由 Repository Service 修复 evidence。 |
| readback 不一致 | `APPLIED` | `EFFECT_PENDING`，保持占用并 attention | 修复/重做 readback，不创建 Submission。 |
| Repository 已成功但 T3 崩溃 | `APPLIED` | `EFFECT_PENDING`，保持占用 | 重做 Finalize，最多创建一个 Submission。 |
| Submission 已存在 | `APPLIED` | 修正为 `FINALIZED` | 修复 Workspace pointer 和 Operation ready result。 |

只有 evidence 明确证明无副作用且原 Repository operation 不会再执行时，才能释放 Attempt。`effect=UNKNOWN` 只能对账同一 Operation，不能将重试次数耗尽解释为 `NOT_APPLIED`。

#### Effect reconciliation 与 readback

已确认“副作用对账”和“内容完整性校验”是两个不同步骤：

| 步骤 | 回答的问题 | 数据读取范围 |
| --- | --- | --- |
| Effect reconciliation | 本次 Repository 写入是否发生、对应哪个 commit。 | 读取 operation journal、operation ref 和 commit/ref 元数据，不读取全部业务行。 |
| Readback verification | 已写入 commit 的业务内容是否符合 Submit 输入和 contract。 | Repository 内部流式扫描本次 commit 的业务表/受保护表，业务服务只接收 manifest/digest。 |

Repository operation journal 不是可丢失的事后日志，至少绑定：

```text
repository_operation_id
operation_kind
idempotency_key
request_digest
repository_id
expected/base commit
source_artifact_digest
effect state
result commit optional
verification state
readback manifest digest optional
created_at / completed_at
```

Repository Service 必须先持久化 operation intent，再执行写入，并使用确定性的 operation/staging ref 或等价 durable marker 关闭“commit 成功、journal 尚未确认时进程崩溃”的窗口：

```text
PREPARED journal
  -> deterministic operation/staging ref
  -> import and commit
  -> APPLIED evidence(result commit)
  -> streamed readback
  -> VERIFIED evidence(manifest digest)
```

这些是 Repository Service 内部 operation phase，不提升为业务 `SubmitAttempt` 状态。Repository Service 重启后负责恢复自己的 journal；业务服务调用 `GetOperation` 获得 `RUNNING / NOT_APPLIED / APPLIED / UNKNOWN` 及结构化 evidence，不遍历 Dolt history 猜测。

Readback 使用通用、版本化的 snapshot manifest，不把 Preview/Submission 业务语义放入 Repository wire contract：

```text
SnapshotManifest
  contract_version
  commit_hash
  catalog_digest
  tables[]:
    table_name
    schema_digest
    row_count
    content_digest
    ordering_digest optional
  protected_summary_digest
  business_content_digest
```

业务 application 将该 manifest 与 Preview/Submit 固化的 expected digests 比较。`repository_commit_hash`、`catalog_digest`、`business_content_digest` 和 `protected_summary_digest` 分属不同语义域，不能用 Dolt commit hash 直接替代 Preview/content digest。Repository Service 可以提供通用 `ComputeSnapshotManifest(commit, contract_version)` 能力，但不能理解 Candidate、Submission 或 Archive。

第一版 readback 采用以下正确性优先策略：

- 不扫描 Repository 历史或其他 Baseline/Submission commit，只处理本次提交 commit 中的业务表和必要受保护表。
- 在 Repository Service 内按稳定表顺序和流式 batch 计算，不将全部行装入内存或通过网络返回给 Python application。
- 正常 Submit 对本次提交的数据执行一次 post-commit 逻辑扫描；导入输入流上顺手计算的 digest 不能单独证明最终 commit 可读且一致。
- journal 保存 verification/checkpoint 和最终 manifest digest；业务 T3 崩溃后复用 `VERIFIED` evidence，不重复扫描。
- mismatch 先由 per-table schema/row count/content digest 定位，只有损坏、缺失 evidence、运维修复和抽样审计才展开逐行深度核对。
- 将扫描耗时、峰值内存和每表吞吐纳入 Phase 0 性能基线；只有 benchmark 证明是瓶颈后，才讨论增量表扫描、Dolt root hash 辅助或 Rust digest kernel。

Archive 对账只验证 CAS journal、request digest、before/after commit 和 main ref 结果；目标 commit 已在 Submit 时完成内容验证，正常 Archive reconciliation 不重新扫描全部业务表。

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

#### Repository 级写入串行原则

已确认把现有业务流程的串行前提提升为正式架构不变量：

```text
one BaselineScope <-> one business Repository
at most one mutating command/flow per Repository
concurrent reads are allowed only on immutable commits
no out-of-band Repository writer
```

这里的串行同时约束同一 Repository 的不同 Flow 实例，不只是单个 Flow 内的 step 顺序。不同 Workspace 的 SubmitFinalize、Review/Confirmation、Archive 和受审计 Repository repair 不并行修改同一 Repository 对应的业务作用域。

第一版不建立独立业务 `BaselineScopeWriteLease` aggregate，使用现有执行边界实现简单排他：

```text
asynchronous write Operation
  serialization_key = "repository:{repository_id}"

short synchronous mutation
  lock BaselineHead row
  or acquire the same repository-keyed database advisory lock

Repository Service write
  repository-local writer lease
```

规则：

- Operation Runtime 对同一 `serialization_key` 最多 claim 一个 active 写 Operation；worker takeover 复用原 Operation/Execution 和幂等键。
- 短命令只在数据库事务期间持锁；不能从用户打开页面一直锁到人工审核或归档，避免浏览器退出、断网或人工等待造成长期占用。
- SubmitFinalize、Archive 和 repair 等长写由 Operation 的持久 claim/lease 持有排他资格，不另建一套业务 lease 状态机。
- 普通读不获取写锁，但必须从 BaselineHead/Node、Submission 或 ArchiveResult 解析 immutable commit；不能直接读取可能领先于业务 Finalize 的 Repository `main` ref。
- Repository Service 仍独立实施 writer lease、幂等 operation journal 和 ref CAS；业务串行假设不能替代跨进程完整性保护。
- 不实现同一 Repository 上不同 Workspace ref 写入并行、写 Flow 抢占、公平队列、优先级或细粒度 Candidate/Workspace 锁。

即使写 Flow 串行，仍必须保留 expected commit/CAS、idempotency key、BaselineHead 条件更新、transactional outbox、ArchiveExecution 和 reconciliation，因为它们处理 worker crash、重复消息、Repository 已成功但业务 Finalize 未完成、运维漂移以及锁被绕过等故障，而不是正常业务并发。

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

#### ArchiveCandidateProjection

已确认删除持久化、可变的 `ArchiveCandidate` entity、Candidate store 和 Candidate 状态机。Candidate 是 Archive Policy 从 Submission domain 的稳定只读 facts 派生的 projection：

```text
ArchiveCandidateProjection
  contract_version
  baseline_node_id
  workspace_id
  submission_id
  review_state: APPROVED
  review_version
  input_roles
  repository_id
  initial_commit optional
  modified_commit optional
  initial_facts_digest optional
  modified_facts_digest optional
  available_roles[]
  required_anomaly_digests_by_role
  candidate_policy_version
  candidate_digest
```

Ownership 与持久化边界：

- Submission domain 拥有 `SubmissionArchiveFactsSnapshot`；Archive domain/policy 拥有 CandidateProjection、role eligibility 和 candidate digest 语义。
- CandidateProjection module-public、非持久、非 Repository wire contract；第一版由 Python domain policy 计算，不属于 Rust data capability。
- 可以建立非权威 read cache，但 PreviewArchivePlan/StartArchive 必须从同一权威业务快照重新计算。
- Confirmation 和 ArchivePlan 保存最小 Candidate subject/selection snapshot 供长期审计，不需要为此恢复可变 Candidate 表。

第一版唯一 Candidate 来源是：

```text
APPROVED_SUBMISSION
```

不再保留 `REJECTED_SUBMISSION / WITHDRAWN_SUBMISSION / WORKSPACE_PREVIEW / WORKSPACE_INITIAL_ONLY` source kind enum：

- REJECTED、WITHDRAWN、RETURNED 会重新开放 Workspace，不产生 Candidate。
- Preview 未经 Submit/Finalize/Review，不能进入正式 Archive。
- Initial-only 必须先形成 approved Submission，再提供 `INITIAL_HISTORY` role；discard 由 ArchiveConfirmation 表达，不是 Candidate。

一个 approved Submission 对应一个 CandidateProjection。role 不属于 Candidate 自身的可变状态，而属于 `ArchivePlanSelectionItem`：

```text
MAINLINE
  selected_commit = candidate.modified_commit

INITIAL_HISTORY
  selected_commit = candidate.initial_commit
```

role 规则：

- `MAINLINE` 要求当前 BaselineNode 下仍为 APPROVED、review version 匹配，并存在经过 Submit Finalize/readback 的 modified commit。
- Approved initial-only Submission 可以只提供 `INITIAL_HISTORY`。
- Initial+modified Submission 只有在 root abnormal initial policy 要求保留时才提供异常型 `INITIAL_HISTORY`；peer-chain downstream 不独立提供该 role。
- 异常型 role 必须绑定 exact required anomaly digests，并在 Start 时具有匹配 Resolution；initial-only 的正常 history role 不伪造 anomaly。
- `MANUAL_ACCEPT_ABNORMAL_MODIFIED` 可以解除 MAINLINE 的异常阻断，但不会自动产生 INITIAL_HISTORY role。
- 同一个 Submission 可以同时以 `(submission_id, MAINLINE)` 和 `(submission_id, INITIAL_HISTORY)` 进入 Plan，因为二者绑定不同 commit；Plan 对 `(submission_id, role)` 保证唯一。

Candidate 使用 Submission ID 作为稳定业务身份，digest 负责版本保护，不分配随机 `candidate_id`：

```text
CandidateRef
  submission_id
  expected_candidate_digest
```

`candidate_digest` 使用 canonical serialization，至少覆盖：

```text
candidate semantic contract version
baseline_node_id
workspace_id
submission_id
review state/version
input roles
repository_id
initial/modified commit
initial/modified facts digest
available roles
required anomaly digests by role
candidate semantic policy version
```

展示文本、时间戳、actor、provider implementation version、Confirmation/Resolution ID、mutable repository ref、选择状态和归档结果不进入 digest。只有语义 policy version 进入 digest，纯实现升级不得使 Confirmation 无意义失效。

关系收敛为：

```text
SubmissionArchiveFactsSnapshot
  -> ArchiveCandidateProjection
  -> ArchiveSubject(candidate_digest)
  -> ArchiveConfirmation(candidate_digest)
  -> ArchivePlanSelectionItem(role, candidate_digest, selected_commit)
  -> ArchiveResult / ArchiveResultHistoryEntry
```

CandidateProjection 的最小业务快照应嵌入 Confirmation/Plan，以便历史审计解释用户确认和最终选择；digest 负责完整性，snapshot 负责可读性。

归档准备流程改为纯计算链：

```text
load current Head and Submission facts
  -> derive CandidateProjection/ArchiveSubject/AnomalyOccurrence
  -> apply Confirmation/Resolution
  -> validate requested selection refs
  -> build PreviewArchivePlan
```

因此第一版删除：

```text
Candidate upsert API/store
mutable Candidate selection endpoint
selected_for_archive
candidate_set_hash/version
NOT_ARCHIVED/ARCHIVED_AS_*/CLOSED_NOT_ARCHIVED Candidate status
Candidate status propagation
selection-time Candidate tag
```

删除 selection-time Candidate tag 的前提是 approved Submission commit 在当前 Baseline 周期由 Submission retention 可靠保留；StartArchive 后由 ArchiveExecution 接管选中 commit/artifact 的 retention，Finalize 后由 BaselineNode/ArchiveResult 接管。Repository GC 不得删除仍被这些业务 owner 引用的 commit。

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
  confirmation_set_digest
  anomaly_set_digest
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
  required_anomaly_digests
```

Plan 必须恰好包含一个 `MAINLINE`，可以包含零到多个 `INITIAL_HISTORY`。所有 selection item 必须属于同一 source BaselineNode。`plan_digest` 使用 canonical serialization，覆盖 selection 和所有业务事实/policy version，但排除 plan ID、created_at、actor 和展示文本；items 按 `role + submission_id` 排序。Preview 和 Start 必须复用同一 digest 实现。

`subject_set_digest` 覆盖当前 BaselineNode 下需要归档决策的 Workspace、Submission、review version 和 CandidateProjection digest；因此不再单独保存重复的 `review_set_digest`。新增 Workspace、退回后新 Submission、review/candidate facts 或 discard 变化必须使旧 preview plan 失效。

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

#### ArchiveConfirmation

Archive Policy 先为每个需要处理的 Workspace 派生当前 `ArchiveSubject`；它是只读 projection，不是持久 entity：

```text
ArchiveSubject
  baseline_node_id
  workspace_id
  workspace_version
  subject_kind
  submission_id optional
  review_version optional
  repository_commit optional
  candidate_digest optional
  subject_policy_version
  subject_digest
```

`subject_digest` 表达用户实际确认的 Workspace/Submission 事实版本。Confirmation 采用 append-only 记录，不再按 `baseline + workspace` 覆盖写：

```text
ArchiveConfirmation
  contract_version
  confirmation_id
  baseline_node_id
  workspace_id
  confirmation_sequence
  decision: INCLUDE_SUBMISSION | DISCARD_WORKSPACE
  subject_digest
  submission_id optional
  review_version optional
  candidate_digest optional
  reason optional/required for discard
  confirmed_by_actor_id
  confirmed_at
  confirmation_digest
```

已确认规则：

- 同一 Workspace 的当前决定取最大 `confirmation_sequence`，不依赖客户端时间或简单 latest timestamp。
- `INCLUDE_SUBMISSION` 必须绑定 Submission、review version 和 candidate digest。
- `DISCARD_WORKSPACE` 必须填写 reason，并绑定当前 workspace version/subject digest。
- 写命令携带 `expected_subject_digest`，锁 BaselineHead，并在没有 active ArchiveExecution 时追加新记录。
- Confirmation 没有 `VALID/INVALID` 状态；只有 baseline node 仍为 Head current、该记录是 Workspace 最新确认且 subject digest 仍匹配时，才计入当前 confirmation set。
- exact current confirmation ID 与 `confirmation_digest` 按 workspace 排序进入 `confirmation_set_digest`；语义相同的重新确认也会使旧 PreviewArchivePlan 失效，从而绑定准确审计记录。
- 同一 Repository 写命令已经串行，`confirmation_sequence` 足以恢复历史顺序，不再保存重复的 `supersedes_confirmation_id`。

失效/复用规则：

- APPROVED 后退回、新 Submission 或重新上传会改变 subject/workspace version，旧确认保留审计但不再有效。
- include/discard 改变通过追加更大 sequence 的新记录取代旧记录，不修改历史行。
- BaselineHead 推进后，旧节点全部 Confirmation 自然历史化，不写 `invalidated_at`。
- StartArchive 成功后禁止追加或替换 Confirmation。
- ArchiveExecution 在 CAS 前 `ABORTED` 且 subject 未变化时，原 Confirmation 可以复用。

#### AnomalyOccurrence 与 AnomalyResolution

Anomaly 先由 policy 从原始事实派生精确 occurrence；Resolution 不能只绑定全局 reason code：

```text
AnomalyOccurrence
  baseline_node_id
  anomaly_code
  root_submission_id
  affected_submission_ids
  relevant_facts_digest
  anomaly_policy_version
  anomaly_digest
```

`anomaly_digest` 至少覆盖 baseline node/commit、root 与 affected submission IDs、initial/modified commit、相关 summary/time facts digest、peer/root chain、anomaly code 和 policy version；展示 message 不进入 digest。同名 anomaly 在事实变化后必须产生不同 digest。

人工处置使用不可变记录：

```text
AnomalyResolution
  contract_version
  resolution_id
  resolution_group_id optional
  baseline_node_id
  anomaly_digest
  anomaly_code
  root_submission_id
  resolution_type
  reason
  resolved_by_actor_id
  resolved_at
  resolution_digest
```

第一版保留三种明确人工决定：

```text
MANUAL_ACCEPT_EXTERNAL_CHANGE
MANUAL_ACCEPT_INCOMPLETE_SUMMARY
MANUAL_ACCEPT_ABNORMAL_MODIFIED
```

一条 Resolution 只覆盖一个精确 `anomaly_digest`。一次 UI 操作接受多个异常时，在同一事务创建多条记录并使用 `resolution_group_id` 关联。`RESOLVED_BY_PEER` 和 `SUPERSEDED_BY_LATER_SUBMISSION` 是图计算解释，不作为人工 Resolution 持久化。

已确认只有以下范围中的 anomaly 阻断 StartArchive：

```text
selected mainline
selected initial histories
peer/root dependency closure required by those selections
```

已明确 `DISCARD_WORKSPACE` 且不属于 selection/dependency closure 的 anomaly 保留为 diagnostics，但不要求人工 Resolution，也不阻断整个 BaselineNode 的归档。

Plan 使用三个独立集合 digest：

```text
confirmation_set_digest
  = hash(sorted exact current confirmation IDs + confirmation digests)

anomaly_set_digest
  = hash(sorted required AnomalyOccurrence digests)

resolution_set_digest
  = hash(sorted anomaly digest + exact resolution ID/digest)
```

`plan_digest` 同时绑定 source baseline/commit、selection、subject set 以及上述三个 digest 和 archive policy version。Occurrence 消失、facts/policy/chain 变化或 Resolution 被新 occurrence 替代都会使旧 plan 失效；历史 Resolution 不物理删除，也不会自动覆盖新的同名 anomaly。

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
      -> FINALIZED

PREPARED       -> ABORTED
EFFECT_PENDING -> ABORTED
```

`PREPARED / EFFECT_PENDING` 都是 active/frozen；`FINALIZED / ABORTED` 是终态并释放 execution freeze。`EFFECT_PENDING` 同时覆盖 Repository 请求未发送、执行中、结果未知，以及 CAS 已成功但业务 Finalize 尚未完成。Repository journal 是 effect confirmation 的权威证据，不再持久化重复的 `EFFECT_CONFIRMED` 生命周期状态。

只有取得匹配 repository idempotency key、request digest、before/after commit 的成功 operation evidence，才能直接执行 Finalize 并进入 `FINALIZED`。只有证明 Repository 副作用未发生且不会再执行，才能进入 `ABORTED`；timeout、网络异常或 Operation failure 不足以解除冻结。

不增加单独 `RECONCILIATION_REQUIRED` 状态；reconciliation 是 `EFFECT_PENDING` 下的处理方式。需要人工关注时使用稳定 attention code，例如：

```text
REPOSITORY_OUTCOME_UNKNOWN
MAIN_REF_DRIFT
REPOSITORY_OPERATION_MISSING
FINALIZATION_RETRY_REQUIRED
```

Operation 只拥有 `QUEUED/RUNNING/READY/FAILED_*`、worker lease、step retry、repository serialization key 和 diagnostics。Archive write Operation 使用 `serialization_key=repository:{repository_id}`，与同 Repository 的 SubmitFinalize/repair 写 Operation 排他。Operation 失败不等于 ArchiveExecution 已终止；即使 Operation 显示 `FAILED_FINAL`，只要 Execution 仍 active，就不得允许退回或新的 StartArchive。Operation `READY` 要求 Execution 已 `FINALIZED` 且 ArchiveResult 可读。

#### Archive 事务与 reconciliation

业务侧与 Repository Service 不使用分布式事务：

```text
T1 StartArchive
  lock Head
  validate/recompute plan
  insert Plan + PREPARED Execution
  insert outbox with repository serialization key

T2 Before Repository Call
  PREPARED -> EFFECT_PENDING
  persist repository request digest

External Repository Service
  CompareAndSetRef(main, expected commit, target commit, idempotency key)

T3 Confirm And Finalize
  validate repository operation evidence
  insert target BaselineNode
  insert ArchiveResult/history entries
  CAS BaselineHead source -> target
  EFFECT_PENDING -> FINALIZED
  insert MainlineAdvanced outbox
```

T3 的业务事实必须在同一个业务数据库事务中提交。CAS 已成功但 Finalize 需要恢复时，Execution 保持 `EFFECT_PENDING`，保存 repository evidence/attention code，并由 reconciler 重做同一个 Finalize；不需要额外中间状态。后置 transfer、cache 和统计失败不能回滚 ArchiveResult 或 BaselineHead。

Reconciler 按以下证据顺序处理：

1. ArchiveResult 已存在时修正 Execution 为 `FINALIZED`。
2. Repository journal 存在匹配 request digest 的成功记录时执行 Finalize。
3. Repository operation 仍在运行时保持 `EFFECT_PENDING`。
4. operation 不存在且 main 仍为 source 时，使用同一幂等键安全重发。
5. main 为 target 但没有匹配 journal 时不能猜测本次成功，进入人工关注。
6. main 为其他 commit 时记录 `MAIN_REF_DRIFT` 并保持冻结。
7. 只有 journal 证明请求最终无副作用且 main 仍为 source 时，才允许 `ABORTED`。

不提供正常业务上的 Baseline/Batch invalidate。Repository 漂移通过 Execution attention 与受审计运维修复处理，不修改或作废不可变 BaselineNode。

#### Failure 与 reason taxonomy

已确认不为 Submit、Review、Archive 各自建立互不兼容的失败状态枚举，也不建立覆盖全系统的巨大 ErrorCode enum。第一版使用少量共享分类维度，并由对应 use case owner 定义稳定 code。

必须区分四类语义：

```text
Command Rejection
  request is not accepted
  no Operation is created
  no business side effect

Execution Failure
  request was accepted
  durable Operation failed during execution

Effect Uncertainty
  external side effect may have happened
  reconcile before retry/unlock/final failure

Business Outcome
  APPROVED / REJECTED / WITHDRAWN / RETURNED_FOR_REVISION
  not a failure
```

统一失败描述：

```text
FailureDescriptor
  code
  category
  phase
  recovery
  effect
  message
  details
  diagnostic_refs optional
```

共享分类维度：

```text
category:
  INVALID_REQUEST
  NOT_FOUND
  FORBIDDEN
  STATE_CONFLICT
  DEPENDENCY_FAILURE
  INTEGRITY_FAILURE
  INTERNAL_FAILURE

recovery:
  NO_RETRY
  RETRY_COMMAND
  RETRY_SAME_OPERATION
  RECONCILE_SAME_OPERATION
  NEW_USER_INPUT
  OPERATOR_INTERVENTION

effect:
  NONE
  NOT_APPLIED
  UNKNOWN
  APPLIED
```

`retryable: bool` 只可作为 wire compatibility/read-model 字段从 recovery 派生，不是权威语义。`RETRY_COMMAND`、`RETRY_SAME_OPERATION` 和 `RECONCILE_SAME_OPERATION` 不能合并为一个布尔值。

`phase` 由用例 owner 版本化，不建立全局 enum：

```text
Submit:   ACCEPT / LOAD_SOURCE / IMPORT / READBACK / FINALIZE
Review:   VALIDATE_TRANSITION / APPLY_TRANSITION
Archive:  START / MAIN_REF_CAS / FINALIZE
```

Owner 边界：

| 内容 | Owner |
| --- | --- |
| category/recovery/effect 原语 | Shared Kernel |
| 具体 code、phase、details schema | 对应 Application Use Case |
| Operation failure persistence | Operation Runtime |
| Repository error code/effect evidence | Repository Service wire contract |
| Repository error 到业务 code 的映射 | RemoteRepositoryAdapter/Application |
| HTTP status 与 ErrorEnvelope | HTTP Interface |

Domain/Application 不抛裸 `ValueError/KeyError` 让 HTTP 猜测稳定语义；message 是面向人类的非稳定文本，程序逻辑只依赖 code 与结构化字段。外部 exception、host path、SQL、凭据和 stack trace 不进入公开 details。

##### Submit reasons

Submit acceptance 的第一版同步拒绝码：

| Code | Category | Recovery | Effect |
| --- | --- | --- | --- |
| `WORKSPACE_NOT_FOUND` | `NOT_FOUND` | `NO_RETRY` | `NONE` |
| `SUBMIT_WORKSPACE_NOT_OPEN` | `STATE_CONFLICT` | `NEW_USER_INPUT` | `NONE` |
| `SUBMIT_INPUT_STALE` | `STATE_CONFLICT` | `NEW_USER_INPUT` | `NONE` |
| `SUBMIT_SOURCE_MISMATCH` | `INVALID_REQUEST` | `NEW_USER_INPUT` | `NONE` |
| `SUBMIT_ACTIVE_SUBMISSION_EXISTS` | `STATE_CONFLICT` | `NO_RETRY` | `NONE` |
| `BASELINE_SCOPE_WRITE_BUSY` | `STATE_CONFLICT` | `RETRY_COMMAND` | `NONE` |
| `IDEMPOTENCY_KEY_REUSED` | `STATE_CONFLICT` | `NO_RETRY` | `NONE` |

同一 idempotency key + 相同 request digest，或 Workspace 已有同一 SubmitAttempt 时，返回原 Operation/Attempt，不作为失败。`SUBMIT_INPUT_STALE` 统一覆盖 input revision、preview 和 binding 不再匹配，details 指明具体 expected/actual 字段；source bytes/digest 不一致使用独立 `SUBMIT_SOURCE_MISMATCH`。

Submit finalize 的第一版执行码：

| Code | Phase | Recovery | Effect |
| --- | --- | --- | --- |
| `SUBMIT_SOURCE_ARTIFACT_UNAVAILABLE` | `LOAD_SOURCE` | `OPERATOR_INTERVENTION` | `NONE` |
| `REPOSITORY_TEMPORARILY_UNAVAILABLE` | `IMPORT` | `RETRY_SAME_OPERATION` | `NOT_APPLIED` |
| `SUBMIT_REPOSITORY_OUTCOME_UNKNOWN` | `IMPORT` | `RECONCILE_SAME_OPERATION` | `UNKNOWN` |
| `SUBMIT_IMPORT_REJECTED` | `IMPORT` | `NEW_USER_INPUT` | `NOT_APPLIED` |
| `SUBMIT_READBACK_INTEGRITY_FAILED` | `READBACK` | `OPERATOR_INTERVENTION` | `APPLIED` |
| `SUBMIT_FINALIZE_INTERNAL_FAILURE` | `FINALIZE` | descriptor 明确指定 | descriptor 明确指定 |

已经接受的 durable source artifact 缺失属于系统完整性问题，不让用户通过重复上传静默覆盖原 Attempt。Readback mismatch 时 Repository commit 可能已经产生，不能简单将 Attempt 标为 final failure 并释放 Workspace；必须保留占用和 effect evidence，交给 repair/reconciliation。

##### Review reasons

Review 是同步短事务，第一版稳定拒绝码收敛为：

```text
SUBMISSION_NOT_FOUND
REVIEW_VERSION_STALE
REVIEW_TRANSITION_NOT_ALLOWED
REVIEW_REASON_REQUIRED
BASELINE_SCOPE_WRITE_BUSY
IDEMPOTENCY_KEY_REUSED
```

`REVIEW_TRANSITION_NOT_ALLOWED` 的 details 至少返回 `current_state / requested_action / allowed_actions`，不为每条状态边创建独立 code。APPROVED、REJECTED、WITHDRAWN 和 RETURNED_FOR_REVISION 是正常 Business Outcome。

Review 后如需释放 Repository 临时 ref，作为独立、可重试 cleanup Operation 处理；cleanup 失败不回滚已经成立的 Review 事实，也不把 Review Outcome 改成 failed。

##### Archive reasons

StartArchive 的同步拒绝码：

```text
BASELINE_NOT_CURRENT
ARCHIVE_PLAN_STALE
ARCHIVE_SELECTION_INVALID
ARCHIVE_NOT_READY
ARCHIVE_IN_PROGRESS
BASELINE_SCOPE_WRITE_BUSY
IDEMPOTENCY_KEY_REUSED
```

`ARCHIVE_NOT_READY` 携带 typed blockers，不将每种 eligibility 原因扩散为顶层 ErrorCode：

```text
CONFIRMATION_MISSING
CONFIRMATION_STALE
MAINLINE_SELECTION_MISSING
CANDIDATE_STALE
CANDIDATE_NOT_ELIGIBLE
ANOMALY_RESOLUTION_MISSING
DEPENDENCY_CLOSURE_INVALID
```

`TIME_ABNORMAL_* / UNRESOLVED_INITIAL_STATE / SUMMARY_FACT_MISSING` 等仍属于 AnomalyOccurrence code，不与 Command rejection code 混用。

Archive 执行期使用精确 failure/attention code，不使用笼统 `ARCHIVE_EXECUTE_FAILED`：

| Code | Recovery | Effect |
| --- | --- | --- |
| `REPOSITORY_TEMPORARILY_UNAVAILABLE` | `RETRY_SAME_OPERATION` | `NOT_APPLIED` |
| `REPOSITORY_OUTCOME_UNKNOWN` | `RECONCILE_SAME_OPERATION` | `UNKNOWN` |
| `MAIN_REF_DRIFT` | `OPERATOR_INTERVENTION` | 根据 journal evidence 为 `NOT_APPLIED/UNKNOWN` |
| `ARCHIVE_FINALIZATION_RETRY_REQUIRED` | `RECONCILE_SAME_OPERATION` | `APPLIED` |
| `ARCHIVE_RESULT_INTEGRITY_FAILED` | `OPERATOR_INTERVENTION` | `APPLIED` |

同一个 code 不能替代 effect evidence；例如 `MAIN_REF_DRIFT` 必须通过 Repository journal 说明本次请求已明确未应用，还是结果仍未知。`effect=UNKNOWN` 时 ArchiveExecution 保持 `EFFECT_PENDING`，不能进入 `ABORTED`、释放 repository serialization slot 或重放外部写。

##### Operation 与 HTTP 映射

Operation 状态映射：

```text
recovery = RETRY_SAME_OPERATION
  -> FAILED_RETRYABLE

recovery = RECONCILE_SAME_OPERATION
  -> retry handler must reconcile first; never replay blindly

recovery = NEW_USER_INPUT / OPERATOR_INTERVENTION / NO_RETRY
  -> FAILED_FINAL
```

Operation `FAILED_FINAL` 不证明 SubmitAttempt/ArchiveExecution 可以解除业务占用；业务对象仍根据 effect evidence 决定是否终止。同步 Command rejection 不创建 Operation。

HTTP 默认映射：

```text
INVALID_REQUEST      -> 422
FORBIDDEN            -> 403
NOT_FOUND            -> 404
STATE_CONFLICT       -> 409
DEPENDENCY_FAILURE   -> 503 only before request acceptance
INTEGRITY_FAILURE    -> 500 before request acceptance
INTERNAL_FAILURE     -> 500
```

异步 Operation 已接受后，polling endpoint 返回 `200 + OperationEnvelope`，通过 Operation status 和 FailureDescriptor 表达失败，不把后台失败重新映射成 HTTP 500。HTTP Interface 可以调整安全所需的 message/details，但不能改变 application code、recovery 或 effect 语义。

#### History Compare

History Compare 第一版默认是只读 Operation + artifact closure，不建立额外复杂业务状态机。只有长期保存、分享或审计某次比较成为真实需求时，才引入持久 `HistoryComparisonResult`。

#### Phase 0 异常 fixture/golden 覆盖

异常测试不按 Python exception、HTTP 错误或 legacy 分支逐条复制，按外部可观察语义分成三条测试轨道：

| 轨道 | 语义 | 主要断言 |
| --- | --- | --- |
| Data semantics | capability 正常完成，但产生 anomaly、degraded 或 blocker。 | payload、digest、artifact、AnomalyOccurrence/typed blocker。 |
| Command rejection | 命令未被接受。 | FailureDescriptor、没有 Operation、没有业务/Repository mutation。 |
| Execution/recovery | Operation 已接受，在 durable step 或外部 effect 边界失败。 | Attempt/Execution/Operation 状态、Repository evidence、占用和恢复终局。 |

例如 `TIME_ABNORMAL_INITIAL` 是数据语义异常，`ARCHIVE_PLAN_STALE` 是 command rejection，`REPOSITORY_OUTCOME_UNKNOWN` 是 execution/recovery；三者不能混成一个通用 `expected_error.json`。

异常进入 Phase 0 golden 的门槛是它会改变以下任一正式可观察事实：

- Workspace、Review、SubmitAttempt、Submission、ArchiveExecution、BaselineHead 或 ArchiveResult。
- `FailureDescriptor.code/category/phase/recovery/effect`。
- Repository commit/ref/journal、业务占用或 serialization key 是否释放。
- Snapshot/Comparison/Anomaly/Plan/artifact schema/digest。
- retry、worker takeover、reconciliation 或进程重启后的结果。
- legacy 与新设计容易发生语义分歧的边界。

普通字段缺失、简单 404、HTTP adapter 映射、内部 helper exception、日志文本/stack trace 以及无业务可观察差异的实现细节使用 unit/contract test，不建立完整 journey golden。

P0 最小异常范围：

| 旅程 | 必须固定的异常语义 |
| --- | --- |
| Upload | 非法包在形成有效 revision 前失败且不创建 UploadRevision；相同 bytes 的新上传动作允许创建新 revision/generation，但复用 content artifact。 |
| Preview | 计算失败保留有效 UploadRevision 且不发布 PreviewResult；新上传后旧 Preview 不能覆盖 current preview。 |
| Submit Accept | stale revision/preview、source mismatch、active attempt 和 idempotency 冲突不创建新 Operation/Attempt。 |
| Submit Execute | 明确未应用、outcome unknown、成功 journal 后恢复、readback mismatch、Finalize crash。 |
| Review | stale version、非法 transition、reason 缺失；StartArchive 前可退回，StartArchive 后拒绝退回。 |
| Archive Start | plan/candidate/confirmation stale、resolution missing、已有 active Execution；typed blocker 使用参数化 contract fixtures。 |
| Archive Execute | 明确未应用、unknown、CAS 成功后 Finalize crash、main drift、重复消息和后置 task 失败。 |
| Baseline/History | Head/Repository drift、artifact/summary 缺失或损坏；History Compare 失败不修改业务状态。 |

Data semantics 还必须覆盖 Python/Rust 共同语义边界：损坏/截断 SQL、编码/转义、空表、无 key、schema change、NULL、ordered duplicate/gap/reorder degraded、生成时间缺失、initial/modified 时间异常、unresolved root、peer chain 解释和 pending/missing summary。它们固定 canonical scalar/order、manifest/artifact 和 digest，不固定 Polars/Rust 内部实现步骤。

Submit recovery 至少建立以下场景：

```text
SUB-01 stale Preview: reject without Attempt
SUB-02 same idempotent request: return original Attempt
SUB-03 repository unavailable: retry same Operation then succeed
SUB-04 import rejected: ABORT and require new input
SUB-05 timeout + success journal: reconcile then Finalize
SUB-06 timeout + no-effect evidence: replay original repository key
SUB-07 commit visible without journal: remain frozen/attention
SUB-08 readback mismatch: no Submission and no unlock
SUB-09 Finalize crash: recover exactly one Submission
```

Archive recovery 使用前述 reconciler 证据顺序做表驱动 golden：Result 已存在、成功 journal、operation running、main=source 可安全重发、main=target 但 journal 缺失、main drift，以及明确 no-effect 后 ABORT。每一行都必须验证重复 reconcile 的幂等性。

每个 execution/recovery fixture 使用稳定语义注入点，而不是绑定实现代码行：

```text
before_repository_effect
after_repository_request_sent
after_repository_effect_confirmed
before_readback_verified
after_readback_verified
before_business_finalize
after_business_finalize_before_outbox_delivery
```

场景至少描述并在失败后、恢复后分别断言：

```text
scenario_id
initial_facts
command_or_event
fault_injection_point
expected_failure(code/category/phase/recovery/effect)
expected_operation_attempt_execution_state
expected_business_facts_created/absent/unchanged
expected_repository_before/after/journal
expected_workspace_and_serialization_occupancy
expected_retry_or_reconciliation_action
expected_final_result/events/artifacts
legacy_classification: MATCH | OLD_BUG | INTENTIONAL_CHANGE | UNRESOLVED
```

Golden 分成 semantic、artifact 和 recovery 三类，不保存完整数据库 dump。固定时钟/ID和canonical serialization，移除 host path、trace ID、随机时间戳、日志文本及不属于 contract 的输出顺序。legacy 输出不能无条件作为异常答案；删除 Batch/Candidate/IN_REVIEW、批准后退回和新 effect recovery 都应按已确认规则标记 intentional change，而不是要求机械 MATCH。

#### 简化决策汇总

| 项目 | 第一版决策 |
| --- | --- |
| Workspace 阶段状态 | `SIMPLIFY`：只持久化 OPEN/CLOSED 与事实引用，其余派生。 |
| Upload mode | `SIMPLIFY`：从 source roles 派生。 |
| Preview binding | `SIMPLIFY`：收敛为 immutable PreviewResult。 |
| Submit package | `SIMPLIFY`：复用 Upload artifact，不重复上传。 |
| Submission 创建 | `SIMPLIFY`：Finalize 成功后创建。 |
| SubmitAttempt 状态 | `SIMPLIFY`：四个单向状态；EFFECT_PENDING 覆盖 effect 未决/已应用待 readback/Finalize。 |
| Submit retry/cancel | `REMOVE`：无公共入口；同一 Attempt/Operation 通过内部重试、takeover 和 reconciliation 恢复。 |
| Submit readback | `KEEP`：Repository 内流式验证本次 commit，业务侧只比较 versioned manifest/digest。 |
| Precommit warmup/provisional promotion | `DEFER`：Phase 7 由 benchmark 决定。 |
| Repository import providers | `SIMPLIFY`：第一版一个 production provider。 |
| Operation DAG | `DEFER`：第一版顺序 step。 |
| Repository 写并发 | `SIMPLIFY`：同 Repository 最多一个修改命令/Flow；Operation 使用 repository serialization key。 |
| 业务 WriteLease aggregate | `REMOVE`：短写锁 Head/DB，长写复用 Operation claim/lease。 |
| 并发读 | `KEEP`：只读取业务已发布的 immutable commit，不直接读取 Repository main。 |
| Baseline Batch | `REMOVE`：以不可变 BaselineNode + 最小 BaselineHead 取代。 |
| Batch/Baseline invalidate | `REMOVE`：不提供正常业务作废功能。 |
| Archive 状态复制 | `SIMPLIFY`：ArchiveResult 为权威。 |
| Submission Review | `SIMPLIFY`：删除 START_REVIEW/IN_REVIEW，使用审核事件和当前投影。 |
| Approved 后退回 | `KEEP`：归档 Start 前允许 RETURNED_FOR_REVISION，并重新开放 Workspace。 |
| Archive Dry-run | `SIMPLIFY`：纯读 PreviewArchivePlan，不持久化、不冻结。 |
| Archive selection | `SIMPLIFY`：由 Preview/Start 请求携带，Start 时固化进 ArchivePlan。 |
| Archive Candidate | `SIMPLIFY`：approved Submission 派生只读 CandidateProjection，不持久化 entity/status/selection。 |
| Candidate source kind | `REMOVE`：唯一来源为 APPROVED_SUBMISSION；initial-only 也先经过 Submit/Review。 |
| Candidate role | `SIMPLIFY`：MAINLINE/INITIAL_HISTORY 属于 PlanSelectionItem，不是 Candidate 可变状态。 |
| Candidate tag | `REMOVE`：由 Submission/Execution/Result retention 保证 commit 存活。 |
| Archive Confirmation | `SIMPLIFY`：append-only 决定绑定 subject digest，不维护有效/失效状态。 |
| Confirmation supersedes link | `REMOVE`：按单调 confirmation_sequence 恢复顺序。 |
| Discard Confirmation | `KEEP`：绑定 workspace subject version，reason 必填。 |
| Anomaly Resolution | `SIMPLIFY`：一条只覆盖一个 anomaly digest；peer/supersede 为派生解释。 |
| Anomaly 阻断范围 | `SIMPLIFY`：只阻断 selection dependency closure。 |
| Archive Execution 状态 | `SIMPLIFY`：四个单向状态；EFFECT_PENDING 覆盖 effect 未决/已应用待 Finalize。 |
| Archive cancel/retry | `REMOVE`：无公共入口，使用同一 Execution 自动恢复。 |
| Failure taxonomy | `SIMPLIFY`：共享 category/recovery/effect，具体 code/phase 由 use case owner 定义。 |
| Retryable boolean | `SIMPLIFY`：只作为 recovery 的派生 read-model/wire 字段。 |
| Archive readiness errors | `SIMPLIFY`：一个 ARCHIVE_NOT_READY + typed blockers。 |
| Review cleanup failure | `SIMPLIFY`：ref cleanup 独立重试，不回滚 Review Outcome。 |
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

### SubmitAttempt

已确认 SubmitAttempt 使用与 ArchiveExecution 同形但独立拥有的四态模型：

```text
PREPARED
EFFECT_PENDING
FINALIZED
ABORTED
```

Attempt 拥有精确输入/baseline binding、Repository effect certainty、Workspace 占用和业务 Finalize 幂等；Operation 拥有 queue/lease/step retry。Repository journal 是 effect authority，readback manifest 是内容完整性 evidence。只有 `FINALIZED/ABORTED` 释放 Attempt 的 serialization 占用；`UNKNOWN/APPLIED` 和单独的 Operation terminal status 都不能解锁。

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

### Archive Confirmation/Anomaly

Confirmation 与 AnomalyResolution 都是不可变审计记录，不维护 `VALID/INVALID/RESOLVED/STALE` 生命周期状态。当前有效性由 `BaselineHead + ArchiveSubject/AnomalyOccurrence digest + latest confirmation sequence` 派生。Plan 绑定 exact confirmation/anomaly/resolution record set；旧记录仅作为历史事实保留。

### Archive Candidate/Execution

当前实现 Candidate 状态：

```text
NOT_ARCHIVED
ARCHIVED_AS_MAINLINE
ARCHIVED_AS_HISTORY
CLOSED_NOT_ARCHIVED
```

目标设计不持久化 Candidate 和上述状态。CandidateProjection 只从当前 approved Submission facts 派生；唯一稳定引用为 `submission_id + expected_candidate_digest`，role/selected commit 固化在 PlanSelectionItem，结果从 ArchiveResult/HistoryEntry 派生。

已确认 Execution 状态：

```text
PREPARED
EFFECT_PENDING
FINALIZED
ABORTED
```

已确认 mainline CAS、业务 Finalize 和后置 transfer 是正交事实；不再以 `SUCCEEDED_TRANSFER_FAILED` 作为单一权威业务结果。Repository成功证据属于journal/evidence，Execution在业务Finalize前保持 `EFFECT_PENDING`。

### Failure/Reason

Command rejection、Operation execution failure、external effect uncertainty 和 Business Outcome 已明确分离。共享原语只拥有 category/recovery/effect；Submit、Review、Archive use case 各自拥有稳定 code、phase 和 details schema。`effect=UNKNOWN` 只能对同一 SubmitAttempt/ArchiveExecution 做 reconciliation，不能按普通 final failure 释放占用。

### Exception Fixture/Golden

已确认异常覆盖分为 data semantics、command rejection 和 execution/recovery 三条轨道。P0 golden 只固定会改变业务事实、stable failure semantics、Repository evidence、digest/artifact 或恢复终局的异常；普通 adapter/helper 错误留在 unit/contract tests。Recovery fixture 以稳定 effect 注入点和 evidence decision table 驱动，不绑定 Python/Rust 代码行，也不保存完整数据库快照。

## 5. 0C/0D Fixture manifest、目录与命名（阶段性确认）

### 5.1 语言无关的 fixture 根目录

已确认 Phase 0 正式 fixture 使用跨实现共享的仓库级根目录：

```text
vnext/fixtures/
```

规则：

- Backend、Repository Service 和 Rust 实现共同读取这里的语言无关场景，不把正式 oracle 归属于某一种实现语言。
- 各组件自己的测试目录只保留不构成跨实现 contract/oracle 的私有小型测试数据。
- 不继承 legacy 的测试目录或内部 fixture 组织方式；legacy 只用于提取输入、行为证据和差异分类。
- 当前 `testing-fixtures.md` 中以旧 backend 测试目录为根的约定需要在 Phase 0 收口后重新整理，而不是作为新目录的兼容约束。

### 5.2 目录第一分类维度

已确认正式 scenario 按执行语义组织：

```text
vnext/fixtures/
  scenarios/
    data/
    command/
    recovery/
```

三类目录分别对应 0B 已确认的测试轨道：

| 目录 | 场景语义 |
| --- | --- |
| `data/` | capability 正常完成，但产生正常结果、anomaly、degraded 或 blocker。 |
| `command/` | 命令未被接受，不创建 Operation，也不产生业务或 Repository 副作用。 |
| `recovery/` | 请求已被接受，在 durable step 或外部 effect 边界失败并恢复或对账。 |

`semantic / artifact / recovery` 是 golden/断言输出类型，不建立与 scenario 轨道竞争的第二套顶层目录分类。一个场景可以同时拥有 semantic 和 artifact golden；recovery 场景还可以拥有 recovery timeline/终局断言。

原 `minimal / regression` 不再作为正式目录第一维度：

- 手写最小样本与脱敏裁剪样本通过 manifest provenance 区分。
- 原始业务数据不属于正式 manifest，也不进入可提交 scenario；只允许存在于 gitignored staging 位置或仓库外 dataset root。
- benchmark dataset 继续位于仓库外，不与 correctness fixture 混合。

### 5.3 Manifest 权威粒度

已确认每个 scenario 目录包含一份权威 `scenario.yaml`：

```text
vnext/fixtures/scenarios/data/ordered-records/duplicate-gid-degraded/
  scenario.yaml
  input/
  expected/
```

规则：

- 不维护人工编辑的全局巨型 manifest，避免全局清单与场景内容形成两个事实来源。
- manifest 格式由版本化 schema 校验。
- 如 runner、CI 或文档需要全局 catalog，应从各场景 manifest 生成；生成物不是权威编辑入口。
- 一个 scenario 目录是可独立发现、校验和执行的最小资产单元。

### 5.4 版本维度

已确认分离以下版本和完整性概念：

```yaml
manifest_schema_version: 1
scenario_id: data.ordered-records.duplicate-gid-degraded
contracts:
  scalar: 1
  ordered_records: 1
fixture_content_digest: ...
```

规则：

- `manifest_schema_version` 只表示 `scenario.yaml` 的格式版本。
- 各 owner 的 semantic/artifact/policy contract 独立版本化，不由一个全局 fixture version 代替。
- `fixture_content_digest` 标识场景受控内容，用于检测未声明的输入或 golden 漂移。
- 不在目录或 `scenario_id` 中预先加入 `v1`，也不建立泛化的 `scenario_version`。
- contract 语义变化时更新对应 contract version 和 golden；只有滚动升级或兼容窗口明确要求新旧 contract 同时验证时，才在同一稳定场景身份下保留多版本 expected 数据。

### 5.5 Scenario identity 与 naming

已确认 `scenario_id` 使用稳定的小写点分命名空间，物理路径使用对应的小写 kebab-case 段：

```text
data.ordered-records.duplicate-gid-degraded
command.submit.stale-preview
recovery.submit.timeout-with-success-journal
```

命名规则：

- 第一段固定为 `data / command / recovery`，并与物理目录一致。
- 后续段表达 owner/capability 或 journey，再表达触发条件或业务边界。
- 不使用 `SUB-01` 等序号作为稳定身份；序号只能作为报告或讨论文档中的展示别名。
- 不绑定 Python exception、实现函数、内部 step、代码行或 legacy 方法名。
- 当 recovery 的 evidence 分支决定不同终局时，名称明确表达分支，例如 `timeout-with-success-journal`。
- `scenario_id` 发布后不因目录整理、实现替换或纯文案修改而变化；若场景所表达的业务语义实质改变，应创建新 scenario，而不是静默复用旧 identity。

### 5.6 Subject 与 runner 分派

已确认 manifest 只声明稳定的业务 subject，不引用实现入口：

```yaml
subject:
  kind: capability
  name: ordered-records
```

规则：

- `subject.kind` 第一版收敛为 `capability | journey`；`subject.name` 表达对应 capability 或业务旅程 owner。
- scenario 轨道由 `scenario_id` 第一段和物理目录共同确定，不在 manifest 中维护另一份可漂移的 track 字段。
- runner 使用 `scenario track + subject` 查找已注册的 harness。
- manifest 不保存 Python module/function、Rust binary、Repository Service 实现类或 legacy entrypoint。
- 实现重构、provider 替换和跨语言 differential runner 不改变 scenario identity 或 manifest 的业务 subject。

### 5.7 Manifest 最小字段

已确认每份 `scenario.yaml` 的最小权威字段为：

```yaml
manifest_schema_version: 1
scenario_id: data.ordered-records.duplicate-gid-degraded
subject: ...
provenance: ...
contracts: ...
inputs: ...
stimulus: ...
expectations: ...
input_digest: ...
fixture_content_digest: ...
```

可选的人类说明和筛选字段为：

```yaml
title: ...
tags: ...
legacy_oracle: ...
notes: ...
```

`legacy_oracle` 只在场景确实执行旧新对照时填写 `MATCH / OLD_BUG / INTENTIONAL_CHANGE / UNRESOLVED`。纯新 contract 或 legacy 没有可比较行为的场景不伪造 legacy 分类；一旦产生实际旧新差异，仍必须遵守 0A 的差异分类规则。

### 5.8 场景 closure 与输入资产复用

已确认不建立 scenario 组合框架：

- 禁止 scenario 继承、模板展开和 scenario-to-scenario 引用。
- 小型手写输入直接放在 scenario 自己的 `input/`。
- 只有确有跨场景复用价值的较大输入才进入 `vnext/fixtures/assets/`，并通过内容 digest 引用。
- scenario closure 包含 manifest 直接引用的本地文件和共享资产；发现、校验或执行一个 scenario 不需要加载另一个 scenario。
- 第一版不建立通用 fixture dependency graph、参数化继承 DSL 或动态输入生成插件。

这允许适度复用不可变 bytes，但不继承 legacy 中以 helper、builder 或隐式目录约定拼装测试输入的内部结构。

### 5.9 Input digest 与 fixture content digest

已确认使用两个职责不同的 digest：

```yaml
input_digest: ...
fixture_content_digest: ...
```

- `input_digest` 覆盖 schema 校验并规范化后的 stimulus，以及全部输入文件/共享输入资产的 closure，用于证明相同场景输入可重复生成。
- `fixture_content_digest` 覆盖规范化 manifest（计算时排除两个 digest 字段）和全部 input、expected、artifact closure，用于检测任何未声明的 fixture/golden 漂移。
- digest 遍历按规范化相对路径排序；绝对路径、host path、mtime、目录枚举顺序和 YAML 排版不得影响结果。
- Manifest、JSON、JSONL 等声明为结构化 contract 的内容，schema 校验后按 owner 声明的 canonical representation 参与 digest；SQL、压缩包、Parquet 和其他 raw/binary asset 按原始 bytes 参与 digest。
- 结构化文件的 YAML/JSON 缩进、object key 排版或注释不改变 digest；owner 声明为有序的 JSONL/array 仍保留顺序语义。CI 可以另行要求统一 formatter，但 formatter 不是 digest contract。
- 修改 expected 的 canonical content 而没有修改 input 时，`input_digest` 保持不变，`fixture_content_digest` 必须变化；纯排版变化不改变二者。
- 两个 digest 都是校验产物，不能替代各业务 owner 自己的 semantic、artifact 或 repository content digest。

### 5.10 Declarative manifest 边界

已确认采用受控的 YAML 与外部文件混合模式：

- `scenario.yaml` 内联 subject、contract versions、stimulus 和 fault injection；所有 golden expectation 一律通过 `path` 引用外部文件，不在 manifest 中内联 expected payload。
- SQL、source package、expected payload、Parquet 和完整 artifact 放在 `input/`、`expected/` 等外部文件，并由 manifest 显式引用。
- manifest 禁止任意脚本、可执行表达式、环境变量替换、YAML 自定义 tag 和实现语言对象反序列化。
- YAML 只是人类编辑格式；schema 校验、runner 输入和 digest 使用解析后的规范化数据模型，不依赖 YAML 注释、锚点写法、key 排版或原始文本格式。
- 允许的 stimulus/fault/expectation envelope 必须由版本化 manifest schema 明确定义，expected payload 必须由对应 owner contract 定义；不能通过透传任意字典把实现内部参数暴露为 fixture contract。

### 5.11 Subject、identity 与物理路径一致性

已确认 `scenario_id` 第二段、`subject.name` 和物理 subject 目录必须完全一致：

```yaml
scenario_id: data.ordered-records.duplicate-gid-degraded
subject:
  kind: capability
  name: ordered-records
```

```text
scenarios/data/ordered-records/duplicate-gid-degraded/
```

因此此前讨论中的临时示例 `data.ordered.*` 在任何 fixture 发布前统一修正为 `data.ordered-records.*`，不保留 owner alias 或另一份映射表。对于 journey，同样要求例如 `command.submit.*` 和 `subject.name: submit` 一致。

### 5.12 完整目录层级

已确认目标目录为：

```text
vnext/fixtures/
  README.md
  schemas/
    scenario-manifest-v1.schema.json
  assets/
    sha256/
      <digest>/
        <logical-name>
  vectors/
    shared-kernel/
      canonical-encoding/
        v1/
          vector-set.json
          jcs.jsonl
          scalar.jsonl
          digest.jsonl
          invalid.jsonl
  scenarios/
    data/
      <subject>/
        <scenario>/
          scenario.yaml
          input/       optional
          expected/    optional
    command/
      <subject>/
        <scenario>/
          scenario.yaml
          input/       optional
          expected/    optional
    recovery/
      <subject>/
        <scenario>/
          scenario.yaml
          input/       optional
          expected/    optional
```

只在首个真实 schema、asset、vector、track、subject 或 scenario 出现时创建对应目录，不预建空目录树。`schemas/` 中的 `v1` 表示 manifest schema 自身的版本；`vectors/` 中的 `v1` 表示被验证的真实 contract version。两者都不违反 scenario identity/path 不携带泛化版本号的规则。

### 5.13 Expected 与 contract version 的显式绑定

已确认 expected 文件的语义和版本由 manifest 显式声明，不通过目录位置猜测：

```yaml
expectations:
  - expectation_id: ordered-records
    kind: semantic
    contract:
      owner: ordered-comparison
      name: ordered-records
      version: 1
    path: expected/ordered-records.v1.json
```

规则：

- `expectations[]` 是 golden 的唯一公共 envelope；`manifest_schema_version` 负责版本化该 envelope。
- 每项必须具有场景内唯一的 lower-kebab-case `expectation_id`、`kind`、完整 owner/name/version 和相对 `path`。
- `expectations[].kind` 第一版限定为 `semantic | artifact | recovery`。
- `kind` 只用于分类、发现和 runner 校验路由，不拥有或替代 expected payload schema。
- 一个 scenario 可以声明多个 expectation，也允许存在多个同 kind expectation；禁止把不相关 owner 的输出塞入一个大型 `expected.json`。
- referenced expected 文件只保存 owner contract payload，不再重复嵌套 fixture `kind/contract/version` wrapper，避免双份 envelope 漂移。
- 第一版不支持 inline golden、`path | inline` union 或从文件内容反向推断 contract。
- 兼容窗口需要同时验证多个 contract version 时，在同一场景 manifest 中声明多项 expectation。
- `expected/` 默认保持扁平，不再重复建立 `semantic/artifact/recovery` 子目录；文件名中的版本只用于可读性，不是权威版本来源。
- 多文件 artifact 使用 `expected/<expectation-id>.v<version>/`，其 expectation `path` 指向目录内的 `manifest.json`；该 manifest 显式声明完整 closure。
- 不建立全局 `expected/v1/`、`expected/v2/` 目录约定。

建议的局部布局为：

```text
expected/
  comparison-facts.v1.json
  comparison-records.v1/
    manifest.json
    records.jsonl
  submit-recovery.v1.json
```

### 5.14 Provenance 与脱敏边界

已确认手写样本使用最小 provenance：

```yaml
provenance:
  kind: handcrafted
```

裁剪回归样本使用：

```yaml
provenance:
  kind: sanitized-regression
  case_ref: non-sensitive-reference
  sanitization:
    status: reviewed
    summary: ...
```

规则：

- sanitized regression 必须记录非敏感 case reference、脱敏审核状态和裁剪/替换摘要。
- manifest 和已提交资产禁止包含原始业务路径、客户/设备真实标识、凭据或其它可反查源数据的信息。
- 不强制保存原始敏感输入 digest；若 digest 本身可能用于识别来源，也不得提交。
- 原始数据与脱敏过程的受限审计证据如需长期保存，应由仓库外的安全流程拥有，不扩张公开 fixture manifest 的职责。

### 5.15 校验、CI 与 golden 更新门禁

已确认以下情况必须使 fixture schema/contract 校验或 CI 失败：

- manifest schema version 不受支持。
- `scenario_id`、物理路径或 `subject` 不一致。
- 存在重复 scenario ID。
- 声明的 contract/version 没有 owner 或不可解析。
- 文件引用缺失、越出 `vnext/fixtures/` 或经过 symlink。
- scenario 目录存在 manifest 未声明的 input/expected 文件。
- `input_digest` 或 `fixture_content_digest` 不匹配。
- sanitized regression 缺少脱敏确认。
- 普通测试运行尝试自动改写 manifest、expected 或 digest。

Golden 更新只能通过后续显式设计的 bless/generate 操作完成，更新结果必须形成可审查 diff。Phase 0 当前只固定这个安全边界，不提前设计 CLI、通用插件系统或自动接受新输出的工作流。

### 5.16 Canonical normalization 的 owner 与执行顺序

已确认 canonical normalization 分成两层，不建设 fixture runner 私有的万能清洗器：

```text
Shared Kernel
  stable scalar/identifier primitives
  canonical serialization

owner observation contract
  stable fields
  collection identity/order/duplicate semantics
  owner-specific canonical payload
```

Shared Kernel 只拥有跨语言稳定原语。semantic、artifact 或 recovery owner 拥有对应 observation contract 的字段选择、集合解释和排序规则。第一版不增加独立 `normalization_profile` 版本轴；normalization 改变正式可观察含义时升级 owner contract，共享 scalar/serialization 改变时升级 Shared Kernel contract 并说明受影响 digest 的 compatibility。

Golden runner 的固定顺序为：

```text
resolve contract owner/name/version
  -> validate expected schema
  -> validate actual schema
  -> canonicalize both with that contract
  -> exact compare
  -> independently recompute and verify declared digests
```

默认 fail-closed：未知 contract/version、未知字段、缺失必需字段、非法 scalar 和 normalization failure 都直接失败；不隐式转换类型，不降级为字符串比较。Golden 默认执行完整 observation contract equality，不提供 `$any`、regex、dynamic ignore list、任意 subset、数值范围、`oneOf accepted outputs` 或递归“排序后再试”的 matcher。

不稳定值必须在正式 observation contract 中排除，或通过 fixture 固定 clock、ID source 和稳定 external evidence。范围/类型边界、局部字段和参数化校验留给 unit/contract tests，不能扩张 public golden envelope。

### 5.17 Shared scalar 与 collection 默认语义

已确认第一版默认规则：

- Canonical structured output 使用 UTF-8 和 LF；object key 按 Shared Kernel canonical serialization 排序。
- `null`、boolean、integer、decimal、string、date/time、binary 和 digest 保持 contract 声明的类型区别；decimal 不经 binary float 中转，NaN/Infinity 不允许进入正式 golden。
- Application/operation timestamp 使用 UTC instant；SQL `DATE/DATETIME/TIMESTAMP/TIME` 按 5.26 的 civil/instant/duration 边界分别解释，不能笼统地全部转换为 UTC。
- 普通业务字符串保留原始 code points，不做全局 Unicode 改写；只有 `CanonicalIdentifier` 使用其明确声明的 identifier normalization。
- Array 默认保序。只有 owner contract 明确声明 identity 和 canonical order 后，集合才可解释为 set、multiset 或 keyed collection；multiset 必须保留重复次数，公共 runner 不自动去重。
- 不属于 contract 的 host path、trace/correlation ID、worker/lease ID、随机时间戳、日志/stack 文本和 provider/build metadata 不进入 golden observation。

Shared Kernel 的 decimal、timestamp、binary、typed row scalar 等逐字节编码由 5.23–5.28 的 `canonical_encoding_version` contract 和跨语言 vectors 固定，不能回退为复用 legacy helper 实现。

### 5.18 Semantic golden

Semantic golden 直接绑定 capability/domain owner 的公开 canonical payload：

- 不创建通用数据库 dump、ORM snapshot 或 test-only 万能业务 DTO。
- 跨多个 owner 的 journey 优先拆成多项 expectation；只有必须表达原子关系时，才由 journey owner 定义组合 observation contract。
- 公开 facts、summary、diagnostics 和 digest 如果属于同一 contract，应共同精确验证；runner 必须从 canonical payload 独立重算声明的 digest，不能只比较预填 digest 字符串。
- “事实不存在”由 owner contract 的明确 `null/absent/empty` 语义表示，不使用 matcher 或字段缺省猜测。

### 5.19 Artifact golden

Artifact contract 继续保持“Artifacts 拥有通用 envelope，内容 producer 拥有 content schema”的 owner 边界。Artifact golden 使用稳定 manifest view 加 owner content：

- 固定 artifact kind/contract version、按 `logical_ref` canonical ordering 的 closure，以及 owner 定义的 schema、稳定 metadata、diagnostics 和 canonical content。
- 只有 content contract 明确声明为 byte-canonical 的格式，才把物理 bytes、blob/content digest 和 size 作为跨 provider golden。
- Parquet、压缩包等可能包含 writer-dependent metadata 的 logical-canonical 格式，比较解码后的 owner content/schema/order 和 owner logical digest；物理 digest 仍用于该次 artifact bytes 的完整性验证，但不作为跨 provider oracle。
- `created_at`、location、host path、object key、writer/build metadata 和临时文件名不进入稳定 artifact observation。
- `expected/<expectation-id>.v<version>/manifest.json` 是多文件 expected artifact closure 的唯一入口；closure 之外的额外文件使校验失败。

### 5.20 Recovery golden

Recovery golden 由 Submit、Archive 等 journey owner 定义组合 observation contract，以命名 checkpoint 保存精确状态快照：

```json
{
  "checkpoints": [
    {"name": "after-failure", "facts": {}},
    {"name": "after-recovery", "facts": {}}
  ]
}
```

规则：

- fault injection 位于 manifest stimulus，使用已确认的稳定 effect boundary；expected recovery 文件不绑定 Python/Rust 代码行。
- Checkpoint 名称、顺序和 typed facts 由 journey contract 版本化并精确比较。
- Attempt/Execution/Operation 状态、Repository journal/evidence、业务占用、恢复动作、最终业务 facts、event/artifact refs 和 exactly-once 结果通过 typed facts 表达。
- 重复 retry/reconcile 的幂等性由 stimulus 明确执行相应次数，再观察命名 checkpoint；不引入 `$eventually`、条件表达式、脚本或通用 invariant DSL。
- 不保存完整数据库 dump 或原始事件日志。wall-clock、内部 retry 次数、lease token 和并发事件交错默认不固定；只有 owner contract 明确承诺的顺序/次数才能进入 golden。

### 5.21 Failure 与 diagnostic 的稳定投影

- `FailureDescriptor` 精确固定 `code/category/phase/recovery/effect` 和 use-case owner versioned typed details。
- `Diagnostic` 固定 code、severity、稳定 subject/location 和 typed parameters；人类 message、翻译文本、stack trace 和日志文本不是 golden contract。
- Diagnostic collection 的 order、identity 和 duplicate semantics 由 owner 声明；公共 runner 不自动排序、聚合或去重。
- HTTP adapter 的安全 message/details 投影由 interface contract test 验证，不反向改变 application failure golden。

### 5.22 Golden 演进与跨实现一致性

- 修正错误 golden 但不改变 contract 语义时，保持 contract version，更新 expected 与 `fixture_content_digest`，并记录变更理由及适用的 oracle 差异分类。
- 字段、类型、collection semantics、normalization 或可观察含义变化时，升级 owner contract version。
- 同一 scenario 只有在明确兼容窗口中才同时保留多版本 expectation；各版本必须分别通过，不能表达为任一版本通过即可。
- 场景业务含义不变时保持 `scenario_id`；stimulus 条件或预期业务边界实质变化时创建新 scenario。
- Python、Rust 和 Repository provider 共用同一 golden；禁止 `.python.json`、`.rust.json` 等实现专属 oracle。Provider 私有 metadata 和性能观测留在各实现私有测试或 benchmark 中。

### 5.23 Canonical encoding contract 边界与版本

已确认新设计使用统一的：

```text
canonical_encoding_version
```

它替代含义过窄的 `scalar_encoding_version`，同时固定三个明确层次：

```text
canonical JSON for DTO/manifest/digest payload
typed table scalar encoding
row/collection digest framing
```

三个层次在规范中分别描述，但第一版只发布一个 bundle version，不允许调用方自由组合 JSON/scalar/frame 版本。任一层的规范 bytes 发生变化都升级 `canonical_encoding_version`，避免形成未经验证的版本矩阵。Hash algorithm 继续由 `DigestRef` 的 `sha256:` prefix 明示，不隐含在 field name 中。

Python Backend、Rust compute core 和 Repository Service 必须对同一 version 具有完全相同的解释。Legacy 的 Python `json.dumps(sort_keys=True)`、`str.lower()` 和“转换失败则保留原字符串”只作为风险证据，不进入新 contract。

### 5.24 Canonical JSON

JSON-compatible DTO、manifest、golden structured content 和 semantic digest payload 采用 RFC 8785 JSON Canonicalization Scheme（JCS），不自定义 `sort_keys + separators` 方言：

- 输入必须满足 I-JSON：UTF-8、object member name 唯一、合法 Unicode、有限 IEEE-754 binary64 number。
- Object property 按 JCS 的 UTF-16 code-unit 规则递归排序；array element order 不改变。
- 不输出 token 间 whitespace；string escaping 和 number serialization 完全采用 JCS。
- String code points 原样保存，不执行 Unicode normalization。
- 普通 JSON integer 只允许精确互操作范围 `[-(2^53)+1, (2^53)-1]`；`uint64`、高精度 decimal、binary 和 table temporal 使用 schema-declared string/typed scalar，不能冒充 JSON number。
- NaN、Infinity、duplicate key、lone surrogate、Unicode noncharacter 和 schema-unknown field fail-closed。
- 仓库中的 JSON 可以按 formatter 生成 pretty form；进入 digest 或 equality 前必须先 schema-validate 并转换为 JCS bytes。

### 5.25 Typed scalar frame 与数值 payload

Typed table scalar 的 canonical frame 为：

```text
tag:u8 || payload_length:minimal-ULEB128 || payload
```

- ULEB128 必须是最短表示，允许的 payload length 最大为 `2^63-1`；实现必须支持 streaming，并可在入口根据业务/resource policy 设置更低限额。
- Unknown/reserved tag、truncated payload、length overflow 和非最短 ULEB128 直接失败。
- 这些 bytes 只作为 digest preimage，不成为 public wire/storage format，生产 API 不公开通用 decoder。跨语言 conformance test 必须提供 frame validator 以验证 unknown tag、truncation、length overflow 和 non-minimal ULEB128；正式数据交换继续使用 JCS、Arrow、Parquet 或 owner artifact contract。

第一版 tag registry：

| Tag | Kind | Payload |
| --- | --- | --- |
| `0x00` | null | length `0`。 |
| `0x01` | boolean | length `1`，false=`00`，true=`01`。 |
| `0x10` | signed-int | 8-byte big-endian two's-complement。 |
| `0x11` | unsigned-int | 8-byte big-endian unsigned integer。 |
| `0x12` | decimal | Canonical ASCII decimal。 |
| `0x13` | float32 | 4-byte IEEE-754 big-endian bits。 |
| `0x14` | float64 | 8-byte IEEE-754 big-endian bits。 |
| `0x20` | string | Valid canonical UTF-8 bytes。 |
| `0x21` | binary | Raw bytes。 |
| `0x30` | date | Canonical ASCII civil date。 |
| `0x31` | datetime | Canonical ASCII civil datetime。 |
| `0x32` | timestamp | Canonical ASCII UTC instant。 |
| `0x33` | time | Canonical ASCII MySQL duration。 |
| `0x7f` | source-literal-anomaly | JCS anomaly envelope。 |

其余 tag 在 v1 中保留；实现不能自行占用。

数值规则：

- Column canonical schema 校验 `tinyint/smallint/mediumint/int/bigint` 的 width 和 signedness；scalar payload 统一使用 8 bytes，不重复写 column width。
- Integer lexical `+`、前导零和 `-0` 规范为唯一数值 bytes；超出 column range 失败。
- Decimal 禁止 `+` 和 exponent，移除多余整数前导零与小数尾零，补足小于 1 的整数 `0`，`-0` 规范为 `0`。例如 `1.00 -> 1`、`.10 -> 0.1`、`-0.000 -> 0`。
- Decimal precision/scale 属于 schema digest，不进入 value payload；只有 scale 的扩大且值未变化时不制造 content diff。
- Float 按声明宽度 round-to-nearest, ties-to-even；`FLOAT` 必须先舍入为 binary32。`-0` 规范为 `+0`，正常 subnormal bits 保留，NaN/Infinity 失败。

### 5.26 Text、binary、temporal、anomaly 与 identifier

#### Text 与 binary

- String payload 原样保存 UTF-8 bytes，不 trim、不 case-fold、不做 NFC/NFKC。
- Surrogate、Unicode noncharacter 和非法 UTF-8 不进入正常 string；禁止使用 replacement character 静默修复。
- Binary payload 保存 raw bytes；`BIT(n)` 使用 binary tag，位宽由 schema 验证，leading zero bits 不能丢失。

#### Temporal

Canonical payload：

```text
date       YYYY-MM-DD
datetime   YYYY-MM-DDTHH:MM:SS[.fraction]
timestamp  YYYY-MM-DDTHH:MM:SS[.fraction]Z
time       [-]HH:MM:SS[.fraction]
```

规则：

- `DATE` 是无时区 civil date；`DATETIME` 是无时区 civil datetime，不能擅自转 UTC。
- `TIMESTAMP` 是 UTC instant。Shared Kernel encoder 只接受已经解析完成的 UTC value，不读取机器时区或 timezone database。
- SQL parser/Repository adapter 必须绑定显式 source/session timezone；DST ambiguous/nonexistent local time 产生 stable anomaly，不能猜测。Named-zone/tzdb policy 由 parser contract 版本化。
- `TIME` 是 MySQL duration，可为负或超过 24 小时。Hours 0–99 使用两位、100–838 使用三位；负零规范为正零。
- Fraction 最多 6 位并移除尾零；全零时省略。Schema 的 fractional precision 仍由 schema digest 保存。
- Zero/incomplete date、非法 leap second 和越界值不能使用正常 temporal tag，只能进入 owner-declared anomaly 或 hard failure。
- Application/operation timestamp 不使用 table scalar tag；其 public contract 使用 RFC 3339 UTC instant，并由 JCS serialization 固定。

#### SourceLiteralAnomaly

Normalizer 不允许“转换失败就变成普通 string”，只能返回 valid typed scalar、owner-declared `SourceLiteralAnomaly` 或 hard failure。Anomaly payload 为 JCS object：

```json
{
  "declared_type": "datetime",
  "raw_base64url": "...",
  "raw_encoding": "utf-8",
  "reason": "ZERO_DATE"
}
```

`raw_base64url` 使用 RFC 4648 URL-safe alphabet 且不带 padding，覆盖 parser 完成 SQL unquote/unescape 后、type coercion 前的 logical literal bytes；原始 SQL token/quoting 仍由 SourcePackageArtifact 保存。`raw_encoding`、reason code 和允许继续进入 storage projection 的条件由 parser/use-case owner 版本化，Shared Kernel 只拥有 envelope。

#### CanonicalIdentifier

- SQL parser 负责 identifier unquote 和 escaped quote；Shared Kernel 不 trim、不猜 quote。
- 只将 ASCII `A-Z` 映射为 `a-z`；非 ASCII code point 原样保留，不执行 Unicode case-fold/normalization。
- 空 identifier、非法 Unicode 和 canonical 后重名失败。
- Binary row 中字段按 canonical identifier 的 UTF-8 bytes unsigned lexicographic order 排序；这与 JCS object key 的 UTF-16 ordering 是两个独立 contract，不能混用。
- Display identifier 是 source/schema fact，不进入 canonical identity，除非 owner contract 明确将其作为业务值。

### 5.27 Semantic digest、row 与 collection framing

Canonical semantic digest 使用 domain separation：

```text
preimage = ASCII("gateway-vnext:<digest-kind>:v1\0") || canonical_payload
digest   = SHA256(preimage)
wire     = "sha256:" || lowercase_hex(digest)
```

`digest-kind` 是 lower-kebab-case registry value，例如 `canonical-json`、`row`、`raw-content`、`business-content`、`collection-item`、`sequence`、`multiset`、`set`、`keyed-collection` 和 `snapshot`。组合 digest 使用 child digest 的 raw 32 bytes，不使用其 hex/wire text。

Raw file/blob integrity digest 仍为直接 `SHA256(raw bytes)`，不增加 semantic prefix。`raw-content` 与 `business-content` 属于不同 domain：即使 canonical payload 相同也产生不同 digest，不能互相替代或通过值相等暗示 authority 相同。

Unordered row/table framing：

```text
row_frame =
  ULEB128(field_count)
  + for field in canonical_identifier_utf8_order:
      ULEB128(name_length) + name_utf8 + scalar_frame

row_hash = SHA256(domain("row") + row_frame)

unordered_table_frame =
  ULEB128(row_count)
  + lexicographically_sorted(raw_row_hash_bytes...)

raw_content_digest =
  SHA256(domain("raw-content") + unordered_table_frame)
```

Field order 和 input row order 不影响 unordered content digest；duplicate canonical column name 失败；duplicate rows 以重复的 32-byte row hash 保留；空表和零字段 row 都有唯一 frame。Ordered table 的 `no`/sequence 语义由 ordered owner digest 表达，不污染 raw unordered content digest。

Shared Kernel collection frame：

```text
framed_item = ULEB128(item_length) + item_bytes
item_hash   = SHA256(domain("collection-item") + framed_item)

sequence_frame =
  ULEB128(item_count) + framed_item... in declared order

multiset_or_set_frame =
  ULEB128(item_count) + sorted(raw_item_hash_bytes...)

keyed_collection_frame =
  ULEB128(entry_count)
  + entries sorted by canonical key bytes:
      ULEB128(key_length) + key_bytes
      + ULEB128(value_length) + value_bytes
```

- `sequence` 保留输入顺序，并使用 `sequence` domain。
- `multiset` 使用 `multiset` domain，保留重复 item hash。
- `set` 使用 `set` domain，发现重复 item hash 时失败。
- `keyed-collection` 使用 `keyed-collection` domain，重复 canonical key 失败。

Owner 必须声明使用哪一种 collection semantics；公共 serializer 不根据容器语言类型猜测。

### 5.28 Cross-language normative vectors

Contract vectors 独立于业务 scenario：

```text
vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/
  vector-set.json
  jcs.jsonl
  scalar.jsonl
  digest.jsonl
  invalid.jsonl
```

`v1` 是被验证的真实 contract version，因此允许与未来版本并存。`vector-set.json` 声明 schema version、owner、contract/version、文件 closure 和 content digest，不保存 Python/Rust/Repository 实现入口；计算 closure digest 时排除 manifest 自身的 digest 字段，避免自引用。

每个 vector 使用稳定 `case_id`，声明 operation、typed input 或 `input_utf8_hex`，以及 expected `canonical_bytes_hex`/DigestRef；invalid case 只固定 stable error code，不固定 exception class/message/stack。

最低覆盖：

- RFC 8785 JCS number/string/property-order cases、I-JSON invalid cases和 non-BMP key ordering。
- Signed/unsigned extrema、column range overflow、decimal 等价 lexical forms。
- Float normal/subnormal/negative-zero/boundary rounding 和 NaN/Infinity rejection。
- Unicode、control escaping、binary、BIT leading zeros、invalid UTF-8。
- Date/datetime/timestamp/time extrema、fraction trimming、timezone binding、zero/incomplete temporal 和 anomaly envelope。
- Empty/zero-field row、field permutation、row permutation、duplicate row/key、sequence/set/multiset/keyed collection。
- Non-minimal/overflow ULEB128、unknown tag、truncation 和 malformed length。
- Semantic domain separation、child raw digest composition 和 raw blob digest distinction。

Backend Python、Rust compute core 和 Repository Service 分别直接消费同一 vector set，并逐字节比较 output 与 stable error code；只比较最终 digest 不算通过。Property/fuzz tests 只能补充，不能替代 normative static vectors。

普通 CI 不得自动生成/bless vector。Generator 只能形成 candidate diff，关键 bytes 必须人工审查并至少由 Python/Rust 两个独立实现验证。v1 发布后，修改既有 case 的 bytes、digest 或 success/error classification 必须发布 v2；只增加能由既有规范唯一推导的新 case 可以继续使用 v1。

### 5.29 Intentional change、延后事项与验收基线

本轮是对 legacy 和现有草案的显式 incompatible correction：

- Legacy `canonical_json_bytes` 不是跨语言 byte contract；legacy scalar conversion 失败后保留 string、合并 `DATETIME/TIMESTAMP` 和 Unicode runtime lowercasing 均不继承。
- 当前正式/目标文档广泛使用 `scalar_encoding_version`；Phase 0 formal 收口时统一重写为 `canonical_encoding_version`，不能只修改字段名而遗漏 JCS、frame 和 digest compatibility。
- 现有文档中“没有额外 normalization 时 business digest 可以直接等于 raw digest”的表述与 domain separation 冲突；formal 整理时必须改为不同 semantic domain 分别计算，不能复用 DigestRef。
- 上一轮 temporary 中“时间统一 UTC”的笼统表述已修正；只有 instant 使用 UTC，SQL civil/duration values 不转换。

以下不再阻塞本 contract：

- 具体 canonical SQL type registry 和 type alias 清单，由 parser/schema contract 细化。
- `SourceLiteralAnomaly.reason` 完整枚举及哪些 owner policy 允许继续 storage projection。
- 部署的 source/session timezone 配置值和 named-zone/tzdb distribution；parser contract 必须显式版本化，Shared Kernel 不加载。
- 实现级 resource limit、streaming buffer 和 SIMD/Rust 优化；它们不能改变规范 bytes。

Phase 0 退出前至少满足：vector schema/closure 可校验；Python、Rust、Repository 三方通过全部 valid/invalid vectors；同一 logical input 产生相同 bytes 和 digest；任何 byte contract 变化都由 version 变化和 digest compatibility 说明显式表达。

### 5.30 Oracle runner 的权责与 harness registry

已确认使用一个语言无关 fixture orchestrator，加 owner harness registry：

```text
load and validate scenario closure
  -> resolve harness(track, subject)
  -> provision isolated execution profile
  -> arm fault when declared
  -> invoke stable production entrypoint
  -> collect owner observations
  -> canonicalize and exact-compare golden
  -> emit conformance result/evidence
```

Runner core 只拥有 fixture discovery/schema/closure、profile lifecycle、fault/checkpoint control、canonical comparison 和 test result；不解释 Submit、Archive、Comparison 或 Repository 业务语义。

- `data` harness 调用 capability public contract。
- `command/recovery` harness 调用 application use case、正式 worker/queue/reconciler 和 Repository client/service contract。
- Registry key 使用已确认的 `scenario track + subject`；manifest 不记录 module/function/class 或 executable path。
- Owner harness 负责把稳定 subject 映射到 public entrypoint 和 typed observer，不允许 runner 直接调用私有 step handler。
- Runner 不是第二套 workflow engine，不支持 manifest script、任意 callback、动态 DAG 或透传实现语言对象。
- Test result/evidence 不是生产 Operation、artifact 或业务事实，不能反向进入正式状态机。

### 5.31 Execution profiles 与 required matrix

同一 scenario/golden 可以在多个 execution profile 下验证；profile 由 versioned runner/CI suite config 选择，不进入 `scenario_id`、manifest expectation 或 expected payload：

| Profile | 作用 |
| --- | --- |
| `reference` | Deterministic in-process adapters、fake clock/scheduler；快速跑完整决策表。 |
| `integration` | Real persistence、Repository Service 和 Dolt；验证真实 service/journal/readback 边界。 |
| `process-crash` | 独立 worker/service process 的非优雅终止、lease expiry、restart/takeover。 |
| `provider-matrix` | Python/Rust 等 capability provider 对同一输入、bytes、facts/digest 的一致性。 |

最低 required matrix：

| Track | Reference | Integration | Process-crash | Provider matrix |
| --- | --- | --- | --- | --- |
| Data semantics | 全量 | source→Repository→readback 关键子集 | 不要求 | Python/Rust 共有 capability 全量 |
| Command rejection | 全量 | 涉及真实事务/唯一约束的子集 | 不要求 | 不要求 |
| Recovery | 全量 evidence decision table | 每种 Repository outcome/evidence 分支至少一个 | 每个 durable boundary/关键 journey 至少一个 | 不要求 |

Process-crash 至少覆盖：request 已发送但 client 无 evidence、Repository effect 已提交但 application 无 evidence、readback verified 后 business finalize 前，以及 business finalize/outbox record 原子提交后 delivery 前。

Profile/provider 不支持声明的 contract、boundary 或 action 时返回 `UNSUPPORTED`，不能伪装为 pass。Required matrix 中任一 cell 未运行或非 `PASSED` 都使 suite 失败；不得用临时 CLI 参数静默降低 required coverage。

### 5.32 Runner result contract

每个 `(scenario_id, profile, provider)` 形成唯一 execution result，状态第一版限定为：

```text
PASSED
ASSERTION_FAILED
HARNESS_ERROR
UNSUPPORTED
```

- `ASSERTION_FAILED`：schema-valid actual observation 与 golden 不相等，或 owner digest/invariant 重算不一致。
- `HARNESS_ERROR`：环境、fault control、barrier/observer、schema/contract resolution、cleanup 等测试基础设施失败，无法形成可信业务结论。
- `UNSUPPORTED`：该 profile/provider 不实现已声明能力；它只是明确缺口，不是成功。
- Normative scenario 不允许 `xfail`、模糊 pass、自动 retry 后覆盖第一次失败或从 legacy classification 推导 expected failure。
- 未被 suite 选择的 scenario 不产生伪造 `SKIPPED` result；suite report 另行记录 selection coverage。

Result 至少记录：scenario/profile/provider、fixture digest、contract versions、status、expected/actual observation digest 和脱敏 diagnostic/evidence refs。Timing/resource 可以作为非 golden 测量字段存在，但不能改变 correctness status。

### 5.33 Fault plan、legality matrix 与 effect authority

第一版每个 scenario 只允许一个 primary fault：

```yaml
fault:
  contract:
    owner: repository-faults
    version: 1
  target: repository_client
  boundary: after_repository_request_sent
  action: drop_response
  occurrence: 1
```

Fault envelope 只包含 versioned `owner/target/boundary/action/occurrence` 及必要 typed parameters；禁止 exception class、函数/代码行、SQL/shell/path 和任意脚本。重复 recovery 由 recovery stimulus 拥有，不通过声明多个 primary faults 模拟。

每个 fault owner 发布 target/boundary/action legality matrix。非法组合在 arm 阶段返回 `HARNESS_ERROR`，不能开始 stimulus。第一版稳定 boundary 继续使用：

```text
before_repository_effect
after_repository_request_sent
after_repository_effect_confirmed
before_readback_verified
after_readback_verified
before_business_finalize
after_business_finalize_before_outbox_delivery
```

`after_business_finalize_before_outbox_delivery` 的前置事实必须是 business finalize 与 outbox record 已在同一本地事务原子提交，只是 outbox 尚未投递。不得注入“业务已提交但 outbox record 缺失”的非法事务缝隙。

Fault action 只决定测试组件如何行为，例如 `reject_before_accept`、`drop_response`、`transport_timeout`、`crash_worker`、`corrupt_readback` 或 integrity-corruption case。Fault receipt 只能证明测试动作发生；Repository effect 是否存在仍由 operation journal、CAS/ref、readback 和已确认 evidence decision table 裁决。

### 5.34 Fault arm/consume protocol 与安全边界

执行 stimulus 前必须完成：

```text
submit fault plan
  -> validate profile support and legality
  -> return armed receipt + plan digest
  -> execute stimulus
  -> trigger boundary/action
  -> persist consumed receipt
  -> verify exact occurrence count
  -> disarm during teardown
```

Fault 未 arm、未触发、位置/次数不符或残留未 disarm 均为 `HARNESS_ERROR`。Receipt 包含 run-scoped fault ID、plan digest、target/boundary/action、trigger count 和 test evidence ref，但不进入业务 golden，也不能替代 Repository journal。

Fault provider 只由 test composition root 注入：

- Production factory 不注册 provider，不暴露 control route；非 test environment 请求启用时服务拒绝启动。
- Real Repository Service profile 使用 test-only adapter/control side channel，只允许固定 versioned fault contract。
- Side channel 只绑定隔离网络、loopback 或 Unix socket，并使用 run-scoped token。
- 禁止 arbitrary SQL/command/path/exception；token 和 fault config 不进入 log、artifact 或 golden。
- Process-crash profile 必须真正终止目标 process；reference profile 的 lease-loss simulation 不能冒充已验证真实 process crash，只能共享同一业务 golden。

### 5.35 Recovery execution protocol 与 checkpoint shape

Recovery runner 的固定阶段：

```text
seed initial facts
  -> validate seed
  -> arm primary fault
  -> execute stimulus through production entrypoint
  -> reach durable failure/quiescence barrier
  -> collect after-failure
  -> drive production recovery mechanism
  -> reach durable completion barrier
  -> collect after-recovery
  -> canonicalize/compare/recompute digests
```

Recovery golden 第一版只允许两个 checkpoint：

```text
after-failure
after-recovery
```

Seed validation 是 harness evidence，不重复成为 golden checkpoint。`repetitions > 1` 时，在全部重复 recovery actions 完成后采集唯一 `after-recovery`；exactly-once 由最终 facts 和 action receipts 证明。需要第三个正式业务阶段时优先拆分新 scenario，不扩张成任意 timeline DSL。

Checkpoint facts 由 journey recovery contract 按 authority 分组：

```json
{
  "name": "after-failure",
  "facts": {
    "business": {},
    "operation": {},
    "repository": {},
    "artifacts": {},
    "events": {}
  }
}
```

外层 journey contract 固定子块 schema/version，payload 不重复 owner metadata。Observer 只读取 typed read model、Operation store port、Repository journal/query contract 和 artifact manifest/digest；不读取原始 DB dump、Repository 服务端文件树或日志作为业务 golden，也不通过观察动作推进状态。

### 5.36 Stable-read barrier 与生产恢复驱动

跨 Application/Repository observation 不建设测试专用分布式事务，采用 stable-read protocol：

```text
hold new runnable work
  -> settle or terminate in-flight worker/effect
  -> read application anchor versions
  -> read business/operation facts in one DB snapshot
  -> query Repository journal/evidence
  -> validate artifact manifests/digests
  -> reread application/repository anchors
  -> accept only when anchors are unchanged
```

Anchor 变化时在 profile deadline 内重新采集；无法稳定是 `HARNESS_ERROR`。Barrier 只控制 test scheduling，不补 journal、不 finalize、不 reconcile、不篡改业务事实。Reference 使用 deterministic `run_until_idle/hold`，integration 使用 bounded polling 和 read-only authority queries，不使用固定 sleep。

Runner 只允许以下固定 test controls 驱动正式机制：

```text
advance_fake_clock
stop_or_start_worker
deliver_durable_message
run_scheduled_reconciler
release_dispatch_hold
```

Manifest recovery stimulus 由 owner versioned trigger 表达，例如 `automatic_retry`、`lease_takeover`、`process_restart`、`duplicate_delivery`、`scheduled_reconcile` 和 repetitions；不保存任意 action list。禁止直接修改 Operation/Attempt/Execution、伪造 journal、调用私有 handler 或手工标记成功。

### 5.37 Logical time、deadline、isolation 与 teardown

Scenario logical time 与 runner wall-clock deadline 必须分离：

- Logical clock 拥有业务 timestamp、retry schedule、lease expiry 和 reconciliation 语义；reference profile 使用 injectable wall/monotonic test clock。
- Runner deadline 只约束 environment startup、fault arm、effect settle、observation stabilization 和 recovery completion，由 profile config 拥有，不进入 fixture/golden。
- Runner deadline 超时是 `HARNESS_ERROR`。业务预期 timeout 必须由 fault action 产生正式 FailureDescriptor，不能依赖 runner 等待超时。
- Integration/process-crash 可以用 test config 缩短 lease/poll interval，但 actual duration 不进入 golden。

每次 execution 使用独立 DB namespace、artifact root、repository ID/ref、queue/worker scope。Business ID、clock 和随机源由 scenario seed 固定；environment run ID 只防止并发碰撞，不进入 golden。`data/command` 可以并行；第一版 recovery 在共享外部服务上串行，只有 profile 证明完整隔离后才放开。

Correctness failure 不自动重试。CI 无论成功失败都 teardown；cleanup、lease、process 或 fault-plan 泄漏使 result 成为 `HARNESS_ERROR`。本地可以显式保留隔离环境，但不能改变 result。

### 5.38 RunEvidenceBundle

每次失败生成 test-only、content-digested `RunEvidenceBundle`：

```text
scenario/fixture digest
git revision
profile/provider/component versions
deterministic seed and logical clock start
fault arm/consume receipts
actual checkpoint payloads
expected/actual canonical diff
Repository journal/query evidence
sanitized diagnostic/log references
teardown result
```

Evidence bundle 不是业务 artifact、golden 或 production contract；不得包含 credential、host path、原始敏感数据、完整数据库或 Repository 文件树。CI 先尽力采集 evidence 再 teardown。Evidence 采集失败不能覆盖原始 `ASSERTION_FAILED`，而是附加 secondary harness failure。Reproduction 只依赖 `scenario_id + profile + provider + fixture digest + git revision`，不依赖临时目录。

### 5.39 Intentional conflict、延后事项与退出条件

现有 `operations.md` 草案允许 lease timeout 后保守地“重做整个 RUNNING step”；该规则对纯内部/幂等计算可以成立，但与 Repository external effect recovery 冲突。Phase 0 formal 整理时必须改为：一旦请求可能被接受，takeover 先按 journal/readback evidence reconcile，只有明确 no-effect 才以原 idempotency key replay。

原注入点 `after_business_finalize_before_outbox_publish` 已更名为 `after_business_finalize_before_outbox_delivery`，明确 business finalize 与 outbox record 原子提交，publish/delivery 是后续可恢复 effect。

以下实施细节不阻塞本架构：runner CLI/报告展示格式、具体 profile deadline 数值、完整 fault action/error code registry、test side-channel transport 和 evidence bundle 的物理归档位置。它们必须遵守本节 result/security/authority 约束。

0C/0D 本部分退出前至少满足：

- Manifest fault/recovery schema 能在执行前拒绝非法组合。
- Reference profile 可跑完整 recovery decision table，无固定 sleep。
- Real integration 能证明 fault 确实 arm/consume，并从 Repository authority 观察 no-effect/unknown/applied 分支。
- Process-crash 覆盖四个关键 durable boundary，replacement worker 通过生产机制恢复。
- Required matrix 无 silent skip/xfail；`ASSERTION_FAILED/HARNESS_ERROR/UNSUPPORTED` 均不能算 pass。
- 两个 checkpoint 可稳定采集、canonical compare，observer 不修改状态。
- 每个失败可形成脱敏 reproduction evidence；每个执行可完全 teardown，无 fault/lease/process 泄漏。

### 5.40 “测试材料”术语与边界

为避免与正式 SourcePackageArtifact、SnapshotTableArtifact 等生产 Artifact 混淆，本文使用“测试材料”作为本轮数据样本的中文统称。`fixture asset` 只保留为物理目录/技术名称，不把测试文件提升为业务 Artifact。

与本轮样本数据有关的测试材料分为三种治理类别：

| 类别 | 内容与位置 | Correctness authority |
| --- | --- | --- |
| Scenario package | Git 内的 `scenario.yaml + input/ + expected/` closure。 | 是；以 owner contract 和 golden 表达正式预期。 |
| Shared fixture asset | Git 内 `vnext/fixtures/assets/sha256/<digest>/` 的不可变共享输入 bytes。 | 单独不是；由显式引用它的 scenario 赋予语义。 |
| External benchmark dataset | Git 外的大型或敏感 workload 与受控 dataset manifest。 | 否；只测量新架构性能、容量和资源使用。 |

Manifest schema、Shared Kernel normative vectors 也是仓库内规范性测试内容，但已有独立 contract/version 治理，不纳入上述“样本数据三分法”。Runner/harness 代码、临时数据库/Dolt repository、日志、RunEvidenceBundle、benchmark report 和生产 Artifact 也不属于该分类。

### 5.41 Scenario-local material 与 shared input asset

Scenario package 是可独立发现、审查、校验和执行的 correctness 最小单元：

- Manifest、scenario-local input、expected/golden 和 artifact closure 共同进入已确认的 `fixture_content_digest`。
- Handcrafted 与 sanitized regression 使用完全相同的 schema、canonical comparison 和通过标准，只由 `provenance.kind` 区分来源。
- `minimal/regression` 不重新成为目录、测试等级或 CI status；已提交 scenario 都是 normative correctness 测试材料。
- 场景很小且只被少量使用时，优先将 input 复制到各自 scenario，保持 closure 直观；不为消除少量 bytes 建共享抽象。

Shared fixture asset 只在同一份较大不可变输入确有跨场景复用价值时使用：

- 只保存输入材料，不保存 stimulus、expectation、golden 或业务判定。
- Scenario 必须按 content digest 显式引用；禁止按文件名、搜索路径或另一个 scenario 间接发现。
- 修改任一 byte 必须产生新 digest/新路径，不能原地覆盖。
- 单独执行 scenario 只解析自己的 manifest closure 和直接引用的 shared assets，不加载其它 scenario。
- 不共享 expected/golden；即使输入相同，各 capability/journey owner 仍分别拥有 observation contract 和 expected payload。

### 5.42 Git 提交大小与可审查性门禁

第一版采用以下默认 admission budget：

- 一个 scenario 的 scenario-local closure 总计不超过 `1 MiB`。
- 一个 content-addressed shared asset 不超过 `5 MiB`。
- 同时校验物理 bytes 和安全展开后的 bytes；归档成员、嵌套和展开路径必须受控，不能用高压缩比绕过大小门禁。
- 除非压缩/归档格式本身就是被测输入 contract，否则提交可直接审查的明文 SQL/JSON/JSONL 等文件。
- 第一版不使用 Git LFS。无法合理裁剪到门禁内的大型输入进入仓库外 dataset，不以 LFS 模糊 correctness fixture 与 benchmark corpus 的边界。

大小门禁是 repository/test governance，不是业务 contract。极少数确有 correctness 必要性的例外必须记录理由、安全审查和 owner approval；不能由 contributor 临时提高本地参数绕过 CI。总仓库 fixture budget、归档成员数量等实施数值可以由 versioned CI policy 细化，但不得弱化上述默认边界。

### 5.43 Sanitized regression 的准入、审核与退出

只有同时满足以下条件的真实问题样本才进入 Git：

1. 来自已发生缺陷或真实数据组合，并捕获 handcrafted scenario 尚未表达的跨表、DDL、ordering、recovery 或 lifecycle interaction。
2. 已裁剪为稳定复现该语义的最小 closure；无关表、行、列、注释、文件和 metadata 已删除。
3. 客户、设备、项目、路径、凭据及其它真实标识已替换为不可反查的 synthetic values。
4. 自动敏感信息扫描通过，并由人工完成脱敏和最小化审核。
5. `case_ref`、sanitization summary 和 review status 本身均为非敏感信息。

Sanitized regression 不提交原始业务输入、原始路径、原始敏感 content digest 或受限工单内容。原始来源与脱敏过程的受限审计证据由仓库外安全流程拥有；legacy output 不能未经 contract 审核直接成为 golden。

一旦进入 Git，regression scenario 不因原 bug 已修复而删除。只有更小的 normative scenario 已完整覆盖同一 contract boundary 时才允许退役，并在审查记录中指向 replacement scenario；删除不能静默降低 required coverage。

### 5.44 External benchmark dataset identity

仓库外 dataset 只评价新架构自身，不承担 correctness oracle。正式、可进入 baseline/report 的 benchmark dataset 必须包含 versioned `dataset.yaml`；旧约定中的 optional manifest 只允许本地探索，所产结果标记为 non-reportable/non-normative。

第一版 dataset identity 至少包含：

```text
dataset_contract_version
dataset_id
dataset_revision
source_sql_file
private_content_digest
workload_shape
sensitivity_class
validation_profile
```

规则：

- `dataset_id + dataset_revision + private_content_digest` 唯一确定不可变输入；同一 revision 的 bytes 不允许漂移，输入变化必须发布新 revision。
- `small/medium/large` 只是由安全 aggregate statistics 派生的 `size_class`/展示标签，不是稳定 dataset identity；不继承 `business_small` 等旧 runner 名称作为新 contract。
- `private_content_digest` 保存在受限 dataset package 和内部运行证据中；若其本身可能帮助识别敏感来源，不写入 Git、公开 report 或普通 CI log。
- 公开/共享 report 只输出安全的 dataset ID/revision、规模摘要、validation profile 和脱敏环境 fingerprint；不得包含原始路径、客户标签或 row payload。
- Benchmark runner 只消费显式 provision/mount 的 dataset root，不联网下载、猜测 host path 或内置凭据。
- Dataset manifest 描述 source 和 workload identity，不透传 provider 私有参数；benchmark suite/profile config 拥有运行矩阵。

### 5.45 Correctness CI、benchmark lane 与语义回流

已确认分离以下执行 lane：

| Lane | 输入 | 门禁语义 |
| --- | --- | --- |
| PR correctness | Git 内全部 scenario/schema/vector closure。 | 全量 discovery/schema/path/digest/provenance 校验，并执行 required reference correctness suite。 |
| Merge/scheduled conformance | 同一 Git fixture；按 versioned suite config 选择 integration/process-crash/provider profiles。 | Required cell 非 `PASSED` 即失败，不改变 scenario 的 normative 身份。 |
| External benchmark | 显式 provision 的仓库外 immutable dataset revision。 | 先 validation，后计量；只建立新架构自身性能/容量基线。 |

外部 dataset 不得成为普通 PR correctness 的隐式依赖。已配置为 required 的 benchmark job 找不到或不能验证 dataset 时，结果为 `HARNESS_ERROR`，并使用稳定 diagnostic code `DATASET_UNAVAILABLE`/`DATASET_IDENTITY_MISMATCH`；不能报告 `PASSED` 或把结果纳入统计。

只有 validation passed 的运行才能进入时间、吞吐、峰值内存和存储结果。每个可比较结果必须绑定 git revision、dataset ID/revision/private identity、contract/policy/storage projection version、component/provider version 和脱敏 environment fingerprint。Phase 0 不运行或维护 legacy-vs-vNext 性能门禁。

External benchmark 暴露新语义时采用单向回流：

```text
external dataset finding
  -> minimize and sanitize
  -> review business/contract meaning
  -> add sanitized-regression scenario
  -> review explicit golden diff
```

Benchmark actual output 不能直接 bless golden；无法安全裁剪的输入只能保留为受限 investigation evidence，不能形成普通 correctness CI 的隐藏 oracle。

### 5.46 Intentional conflict、延后事项与退出条件

现有 `testing-fixtures.md` 使用旧 backend test root，并以 `minimal/regression/external` 作为物理目录；这与 5.1–5.2、5.40–5.45 的仓库级 scenario/provenance 设计冲突。Phase 0 formal 整理时必须重写，而不是保留兼容目录。其 `dataset.yaml optional` 也必须收窄为：只有非正式本地探索可省略，正式 baseline/report 不可省略。

现有 benchmark runbook 中 `business_small/medium/large`、provider 列表、host path 和当前 runner output layout 只说明已有实验环境，不进入新 dataset identity 或 public benchmark contract。Legacy 和旧 benchmark runner 只能帮助识别 workload/容量，不继承其内部分类、cache/provider 布局或性能比较口径。

以下实施细节不阻塞本架构：size-policy 文件的物理位置、敏感信息扫描器选型、人工 approval 的代码承载方式、外部 dataset registry/storage 服务，以及安全报告发布渠道。它们必须遵守本节 storage、identity、privacy 和 authority 边界。

0C/0D 本部分退出前至少满足：

- 单个 scenario 可离线解析完整 closure；普通 PR 不需要外部 dataset、网络或 legacy 文件。
- CI 能阻止 oversize/unsafe archive、未声明文件、shared asset digest 漂移和未审核 sanitized regression。
- Handcrafted 与 regression 使用相同 exact golden contract，不存在 regression-only 宽松 matcher/xfail。
- Reportable benchmark 可拒绝缺失或 identity 漂移的 dataset，并只在 validation passed 后计量。
- 外部数据发现的 correctness 语义只能通过已审核 sanitized regression 进入 Git/golden。
- 公开报告和普通 evidence 不泄漏 private dataset digest、原始路径、真实标签或 row payload。

## 6. 新重构原则：Raw Source Artifact 与 Canonical Dolt Repository（阶段性确认）

### 6.1 原则与权威边界

已确认本次不兼容重构不再要求 Dolt repository 单独具备“完全复原原始 SQL 数据库”的能力。新的原则是：

> 不可变 SourcePackageArtifact 保存原始上传事实；Dolt 保存由版本化 storage projection 生成的 canonical business state。系统保证必要原始数据的完整性，但不要求 Dolt 中保留所有原始物理列和原始 DDL。

权威关系为：

```text
Immutable SourcePackageArtifact
  raw uploaded bytes / source provenance / replay authority
        |
        v
parse + table rules + versioned storage projection
        |
        v
Canonical RepositoryImportArtifact
        |
        v
Dolt canonical business tables
        |
        v
SnapshotManifest canonical readback
```

规则：

- Submit 成功后，原始 SourcePackageArtifact 仍按已确认设计从 workspace retention 提升为 submission durable；新原则不删除原始上传 bytes。
- Dolt commit 是已接受 canonical business state 的历史权威，不是原始 SQL bytes、原始列布局或原始 `CREATE TABLE` 的唯一副本。
- 从 Dolt 导出的业务表默认是 canonical schema；若调用方需要原始上传包，应读取 SourcePackageArtifact，不能假设可以从 Dolt 逆向还原。
- Source digest、storage projection digest、canonical business content digest、Repository commit hash 分属不同语义域，不能互相替代。
- legacy 只用于提取原始行为、表规则和 fixture，不继承其 projection table、SQL patch 或 Dolt 内部结构，也不参与新设计的性能 benchmark 对比。

### 6.2 Storage projection 不等同于临时 comparison projection

已确认在 Repository import 前应用版本化 storage projection：

```text
parsed full-row facts
  -> resolve frozen table rules
  -> build canonical storage schema
  -> validate storage eligibility
  -> stream canonical rows
  -> build RepositoryImportArtifact
  -> Repository Service generic import/readback
```

Storage projection 决定 Dolt 长期保存的列、物理主键和结构事实；comparison projection 仍负责跨版本 schema alignment、selected value columns、ordered 语义和 records。两者必须来自同一 table-rules 语义源，但不能因为都叫 projection 就共用未区分职责的 DTO 或 cache。

第一版列策略至少区分：

```text
PERSIST_BUSINESS
  canonical business value/identity column

RETAIN_FOR_STRUCTURE
  不参与普通内容 modified 判定，但恢复结构语义需要

DROP_FROM_STORAGE
  已确认不影响业务身份、业务值、顺序、审计解释或恢复的波动列
```

只有 `DROP_FROM_STORAGE` 列会在写入 Dolt 前删除。删除理由、规则版本和 source/canonical schema digest 必须进入 CanonicalizationManifest。

### 6.3 普通表的 canonical key 与行完整性

已确认正常业务表经过规则修改 schema 后应具有可用、稳定的 effective key。第一版采用 fail-closed 设计，不为无效普通表建设通用 surrogate-key 或自动 keyless fallback。

Canonical keyed table 写入前必须验证：

- effective key 字段存在，并且没有被 `DROP_FROM_STORAGE`。
- key tuple 不含 NULL 或业务空值，并在整张 canonical table 内唯一。
- storage projection 前后 row count 相同。
- 不通过 deduplicate、last-write-wins、覆盖或丢弃行来满足主键约束。
- 所有未明确删除的列按 canonical scalar contract 完整保留。

验证失败时：

```text
Preview
  -> data semantics degraded/blocker with typed reason

Submit
  -> reject before Repository write effect
  -> no Dolt commit
  -> durable SourcePackageArtifact remains available
```

真正允许 keyless/multiset storage 的表必须由 ruleset 显式分类，不能作为 canonical key validation failure 的隐式退路。重复 key、缺失 key 和 projection 后 row count 变化必须进入 Phase 0 fixture/golden。

### 6.4 Ordered 表保留 `no` 作为结构事实

已确认第一版不为 ordered table 建立独立 numeric-position table 或 predecessor-edge table，也不依赖 Dolt 的隐式行顺序。

Ordered canonical table 采用：

```text
gid  canonical primary key
no   retained ordering/position fact
business value columns
```

其中：

- `no` 属于 `RETAIN_FOR_STRUCTURE`，不能按普通 volatile/ignored column 从 Dolt 删除。
- `no` 不参与普通 row-content value digest 或普通 content modified 判定，但进入 ordering validation、ordered sequence、ordering digest 和 ordered provider。
- History Compare/ordered read 必须显式按 `no` 恢复顺序；SQL/Dolt 未带 `ORDER BY` 的读取顺序不是 contract。
- ordered semantic 仍由 ordered provider 计算，不能直接继承 Dolt native raw diff counts，尤其是 pseudo blank、position shift、move 和 interval。
- 数字序号大范围漂移可能使 Dolt 产生较多 modified rows；基于该事件约千分之一的业务频率，第一版接受这项罕见存储噪声，以换取单表读取、readback 和完整性校验的显著简化。

独立 position/edge storage 延后，只有真实历史证明 `no` 漂移显著贡献 Repository 容量，并且 benchmark 证明节省收益覆盖双表 join/遍历、readback 和校验成本时，才重新进入。

### 6.5 Ordered `gid` 重建与 pseudo blank 范围

已核实原始 SQL 中 ordered `gid` 类型为 `INT(11) UNSIGNED`。`(11)` 不改变 32-bit unsigned 整数范围；canonical table 继续使用 `INT UNSIGNED`，不为 pseudo blank 扩大到 BIGINT 或新增技术主键列。

已确认 canonical identity domain：

```text
source gid = 0 / NULL / empty
  blank input, canonicalizer must allocate pseudo gid

canonical real gid
  1 .. 3_999_999_999

canonical pseudo gid
  4_000_000_000 .. 4_294_967_295

canonical gid = 0
  forbidden
```

Pseudo 区间共提供 `294,967,296` 个值；真实业务 gid 从小到大使用且 pseudo blank 很少，第一版将 `4_000_000_000` 提升为正式 storage contract 边界，而不是只依赖经验上“通常不会冲突”。

Pseudo gid 分配规则：

```text
validate and sort rows by no
pre-scan every real gid
first blank  -> 4_000_000_000
second blank -> 4_000_000_001
...
```

必须满足：

- 原始真实 gid 必须位于 `1..3_999_999_999` 且唯一；原始值进入 pseudo 保留区间时输出 blocker，不能自动解释为 pseudo。
- 只有原始 `0 / NULL / empty` 才能生成 pseudo gid。
- `no` 必须为正数、唯一、连续；分配顺序只依赖规范化后的 `no`。
- 分配不得使用 UUID、auto increment、Dolt 插入顺序、Python object identity 或随机值。
- 相同 source、ruleset 和 policy version 必须生成相同 canonical gid、schema 和 digest。
- pseudo blank 的正式业务语义仍是 `PSEUDO_BLANK`；高位 synthetic gid 只用于 canonical physical identity，不得作为真实业务 gid 展示。
- ordered provider 仍按 stable-row interval 和 blank signature 解释 pseudo blank；Dolt 对 synthetic gid 的 native add/delete/modified 不是 ordered 业务 oracle。

Canonical DDL 目标形状为：

```sql
gid INT UNSIGNED NOT NULL,
no INT NOT NULL,
PRIMARY KEY (gid)
```

具体 display width、secondary index 和 DDL 文本由后续 storage schema contract 决定，不进入当前业务语义基线。

### 6.6 CanonicalizationManifest 与 readback

已确认每次 Repository import 必须生成版本化 CanonicalizationManifest，并与 source artifact、import request 和 Repository readback evidence 绑定。至少记录：

```text
contract_version
source_artifact_digest
storage_projection_version
ruleset_id/version/digest
tables[]:
  table_name
  source_schema_digest
  canonical_schema_digest
  source_row_count
  canonical_row_count
  retained_columns
  structural_columns
  dropped_columns_with_reason
  canonical_primary_key
  canonical_content_digest
  ordering_digest optional
  ordered_identity_policy_version optional
  real_gid_min/max optional
  pseudo_gid_start/max/count optional
manifest_digest
```

Repository readback 验证 canonical commit，而不是要求 Dolt 与原始 SQL schema 全字段相等：

- per-table canonical schema digest、row count、content digest 和 ordering digest 与 import expectation 一致。
- 普通表没有 dedup/overwrite/row loss。
- ordered 表真实 gid 未修改，pseudo gid 位于保留区间，`gid=0` 不存在，主键唯一，`no` sequence 合法。
- Repository journal 保存匹配的 canonicalization/readback manifest digest；业务 Finalize 只接受 VERIFIED evidence。
- 原始 bytes、原始 DDL 或已删除列的审计需要回到 durable SourcePackageArtifact 和 source-side diagnostics。

### 6.7 Storage projection/ruleset 升级的简化策略

已确认项目生命周期内 storage projection 的物理列或主键规则升级属于极罕见场景。第一版复用现有 schema-change alignment，不建立 repository history migration/rebaseline 状态机。

每个 commit 必须记录 `storage_projection_version + ruleset_digest`。比较策略：

```text
same storage projection version
  -> normal canonical/native route when eligible

different storage projection version
  -> schema-change alignment
  -> disable unsafe native data diff
  -> compare shared compatible columns/effective key through streaming fallback
  -> table-level degraded when safe alignment is impossible
```

规则：

- 不回写旧 commit，不为罕见规则变化迁移整个 Repository 历史。
- 主键集合发生变化时不能假设 Dolt native data diff 完整；必须 fallback 或 degraded。
- 新规则开始保留旧 commit 已删除的列时，不能从 Dolt 猜测历史值；必要时从 durable SourcePackageArtifact 显式重算，普通路径可以给出明确 degraded。
- schema change 必须标记来源，避免把 storage policy 升级误报为用户业务 DDL 风险：

```text
SOURCE_SCHEMA
STORAGE_PROJECTION_POLICY
BOTH
```

- 这种受控降级是已接受的简化，不允许静默输出看似精确但使用了不兼容 row identity 的 diff。

### 6.8 Ownership 与 Repository Service 边界

Table rules/storage projection capability 拥有 canonical schema、列策略、业务 key、ordered identity policy 和 CanonicalizationManifest 语义。Repository Service 继续保持通用：

- 不理解 ignored/structural columns、pseudo blank、Workspace、Submission 或 ordered business semantics。
- 只导入业务侧提供的 canonical RepositoryImportArtifact。
- 只执行通用 commit/ref/operation journal、catalog、stream rows 和 versioned snapshot manifest readback。
- Repository Service 可以校验 SQL schema、主键、row count 和内容 digest，但不能自行选择要删除的业务列或生成业务 pseudo gid。

因此新原则不会把旧 projection 内部结构搬进 Repository Service，也不会破坏独立通用 Repository Service 的正式目标。

### 6.9 Intentional change 与文档影响

本原则属于显式 `INTENTIONAL_CHANGE`：

- 旧行为以 Dolt 中原始/full-row schema 为主，并在比较时临时构建 projection table。
- 新行为在 import 前一次生成 canonical storage form，Dolt 不再保证原始 schema/DDL 的完整复原。
- 旧 `docs/backend-vnext/adr/0001-snapshot-table-and-dolt-import-boundary.md` 中“原始 CREATE TABLE 保留用于 Dolt import”的结论与本原则冲突；该旧文档只作为变更证据，Phase 0 结束后必须重新整理到 formal contract/ADR，不能直接改名、移动或静默沿用。
- `refactoring/formal/plans/implementation-stages.md` 当前仍把旧实现性能列为 oracle；该表述与本轮决定冲突，Phase 0 收口整理 formal 时必须删除。当前 temporary 先记录新决定，不直接修改 formal baseline。
- `SnapshotTableArtifact` 是否继续保存 full-row raw table facts，与 Dolt 是否保存 canonical table 是两个边界；后续正式文档必须避免把 raw snapshot、storage projection 和 comparison projection 合并为一个权威对象。
- 新旧 Dolt commit 的兼容/迁移策略仍由 0F 决定；在决定前不得直接把 legacy raw commit 与新 canonical commit 当作同版本 repository state 比较。

### 6.10 性能假设、验证证据与 fixture 范围

已确认以下是待 benchmark 的设计假设，而不是已经成立的验收结论：

- 删除真正 unstable/ignored columns 可以减少无业务变化时的 Dolt diff、chunk 增量和 Repository 容量。
- import 前一次 canonicalization 可以减少 history/重复 comparison 构建 projection table 的 CPU、内存和临时 IO。
- storage projection 本身会增加 Submit materialization 成本，必须与后续 diff/readback 节省一起评估。

性能基线和门禁只评价新架构自身：

- 不运行或维护“legacy implementation vs new implementation”的性能对比作为 Phase 0/切流门禁。
- 不以旧实现耗时、吞吐、内存或磁盘占用作为新实现必须达到的相对基准，也不要求证明相对 speedup。
- 第一条正确、串行、validation-passed 的新路径建立自身 baseline；后续优化与同一 workload、dataset、contract version 下的新架构已接受基线比较。
- 性能验收由新系统的真实 workload、容量预算、用户可接受延迟、资源上限和回归阈值拥有；具体绝对目标在 0E 收口。
- legacy 可以帮助识别真实业务旅程和数据规模，但旧 runner、旧 cache/provider 布局和旧测量口径不进入新 benchmark contract。

本轮使用 Dolt `2.1.11` 做了一个方向性小实验：1 万 ordered rows、128-byte payload、中间插入导致后 5000 行序号漂移。结果为：

| Storage shape | Baseline bytes | Insert growth bytes | Dolt row diff |
| --- | ---: | ---: | --- |
| 原表保留 `no` | 273,038 | 140,653 | 1 added + 5000 modified |
| 独立 numeric position table | 305,676 | 52,517 | 1 added + 5000 modified |
| predecessor edge table | 308,079 | 17,974 | 1 added + 1 modified |

该实验只证明取舍方向：拆表可以隔离罕见序号漂移，但增加基线占用和每次读取/校验复杂度。结合约千分之一的漂移频率，第一版选择原表保留 `no`；正式结论仍需真实 dataset、多代次历史、GC 后磁盘、readback 和 History Compare benchmark。

Phase 0 fixture/golden 至少需要覆盖：

- ignored-only raw change 产生相同 canonical content/digest，Preview 暴露 `NO_CANONICAL_CHANGE`，Submit 在创建 Attempt/Operation 前拒绝且没有 Repository effect。
- dropped column 不影响 canonical schema 之外的 row count 和 retained values。
- duplicate/missing effective key 阻止 Submit，不发生 Repository effect。
- ordered real gid 保持原值并成为主键。
- ordered `0 / NULL / empty` gid 确定性映射到 `4_000_000_000+`。
- 原始真实 gid `>=4_000_000_000` 返回 reserved-range blocker。
- pseudo blank insert/delete、重复 materialization 和 readback digest 稳定。
- `no`-only position shift 不产生普通 content modified，但产生正确 ordered semantics/ordering digest。
- storage projection version change 进入 schema alignment/fallback，不错误使用 native data diff。
- SourcePackageArtifact 可独立恢复原始上传 bytes，Dolt export 明确为 canonical schema。

### 6.11 Measurement contract 与 numeric baseline 的交付时序

当前 vNext 尚未具备完整、正确的 `storage projection -> Dolt import -> post-commit canonical readback` 路径，因此 Phase 0 当前交付的是 `BenchmarkMeasurementContract v1`、workload/dataset identity、result schema 和 capture gate，不使用 legacy 数字或方向性实验伪造新架构 numeric baseline。

首份 accepted numeric baseline 在以下路径首次可运行后立即捕获：

```text
frozen Preview-bound table facts
  -> storage projection
  -> CanonicalizationManifest
  -> RepositoryImportArtifact
  -> Repository Service import/commit
  -> full post-commit readback
  -> VERIFIED evidence
```

它必须先于 parallelism、cache、incremental readback、production provider 切换或专用 Rust 性能优化。Baseline record lifecycle 与 execution result 四态相互独立：缺少 required evidence/gate 为 `INCOMPLETE`，完整且等待 owner review 为 `CANDIDATE`，审核通过为 `ACCEPTED`，被新记录显式取代后为 `SUPERSEDED`。只有 `ACCEPTED` 才是正式 numeric baseline。具体用户延迟、容量预算、资源上限和相对 regression threshold 由 0E 在真实部署 profile 上确认。

因此正式阶段计划中的“Phase 0 Performance baseline report”必须整理为“measurement contract + baseline capture gate”；真实数字由首条 validation-passed vNext 纵切产生。旧实现和旧 runner 只帮助识别 workload/规模，不提供性能目标或相对 speedup 门禁。

### 6.12 Accepted baseline 的容器与环境权威

正式端到端 numeric baseline 只接受容器化 Repository Service deployment profile：

```text
Backend/worker container
  -> Repository public client/wire contract
  -> Repository Service container
       owns Dolt binary/process lifecycle
       owns registry/journal/repository/staging storage
```

第一版不把 Dolt SQL Server 拆成另一个独立容器。Repository Service 是 Dolt lifecycle、journal、recovery 和路径的唯一 owner；业务容器不安装 Dolt、不挂载 Repository volume，也不接触服务端路径。

首份 baseline 前的最小容器门禁：

- Repository Service 真正运行稳定 public contract，不是打印 settings 后退出的 bootstrap。
- Repository Service image、base image、Dolt version/binary digest 固定。
- Dolt repository、registry、operation journal 使用独立 persistent volume；temporary staging 可独立清理和计量。
- 支持 readiness/liveness、graceful stop、non-graceful restart recovery 和 run-scoped fresh repository。
- Container CPU/memory limits、volume driver/filesystem、host CPU/disk class、kernel/runtime 进入 `environment_profile_id`。
- 同一 baseline machine 一次只执行一个正式 benchmark suite。

Host-local、pytest embedded 或直接 Dolt CLI 结果可以作为 component/diagnostic evidence，但不能与 deployment baseline 混为同一 series。只有相同 environment profile 的结果可以做性能回归判断；具体 quota 数值在 0E 固定，但 profile 一旦用于 accepted baseline 就不可静默漂移。

### 6.13 `NO_CANONICAL_CHANGE` 与 Submit artifact 边界

原始 SourcePackageArtifact bytes 可以不同，但当 Preview 绑定的 canonical business digest 与当前 base 完全相同时：

```text
Preview
  -> expose NO_CANONICAL_CHANGE

AcceptSubmit T1
  -> revalidate revision/preview/base binding
  -> reject NO_CANONICAL_CHANGE
  -> no SubmitAttempt
  -> no Operation
  -> no Repository request/commit
  -> no Submission/BaselineNode
```

该 SourcePackageArtifact 继续按 Workspace retention 管理，不提升为 submission durable。第一版不建立“成功但复用旧 commit”的 no-op Submission，不让无业务变化输入进入 review/archive 历史。

Preview 负责 parse/materialize immutable full-row table facts、canonical business digests 和正式 PreviewResult，但不为每个未提交 Preview 预建完整 Dolt-specific RepositoryImportArtifact。Submit T2 从 exact Preview-bound SnapshotTableArtifact/table facts 开始：

```text
frozen table facts + frozen ruleset/policy
  -> storage projection
  -> CanonicalizationManifest
  -> RepositoryImportArtifact
  -> persist artifact/checkpoint digest on the Attempt
  -> call Repository Service
```

Submit 不重新解析原始 SQL。RepositoryImportArtifact 对同一 Attempt 只构建一次；retry、worker takeover 和 reconciliation 复用完全相同的 immutable artifact ref/digest。一旦 Repository 请求可能被接受，禁止重新构建另一份“逻辑等价”artifact 再盲目发起请求。

### 6.14 非重叠阶段、计时层级与 full readback

Measurement contract 使用以下非重叠阶段：

```text
storage_projection
  frozen table facts/ruleset
  -> canonical schema/rows validated
  -> CanonicalizationManifest and RepositoryImportArtifact ready

repository_prepare
  request accepted
  -> journal PREPARED
  -> deterministic staging/ref ready

dolt_apply
  import canonical tables
  -> working set complete

commit
  working set complete
  -> durable commit + APPLIED evidence

post_commit_readback
  open committed ref
  -> stream required canonical/protected tables
  -> SnapshotManifest matched

verification_persist
  matched manifest
  -> journal VERIFIED
```

同时保留三个观察层级：

| 层级 | 边界 | 用途 |
| --- | --- | --- |
| Component | 单个 projection/Repository 阶段。 | 定位 owner 与热点。 |
| Effect | Submit T2 开始到 VERIFIED evidence 可用。 | 衡量完整外部写 effect。 |
| Journey | AcceptSubmit T1 开始到 FinalizeSubmit T3 commit。 | 衡量 queue/dispatch/RPC/业务事务后的用户旅程。 |

`canonical_repository_write_total` 从 storage projection 开始到 VERIFIED；`repository_effect_total` 从 Repository request accepted 到 VERIFIED。各层实际独立计量，不通过 component durations 相加制造重复 total。

所有 duration 使用 monotonic clock。Client wall、service-local spans、queue/RPC/process startup 分开记录，不能用跨进程日志 timestamp 相减。正常 Submit readback 必须从 committed ref 全量、流式读取本次 commit 的必要业务/受保护表；不能复用 import input stream、内存 row objects 或旧 VERIFIED evidence。Recovery 复用 VERIFIED evidence 是独立 recovery profile，不混入 normal readback scan baseline。

### 6.15 Benchmark profiles 与 workload matrix

第一版使用四类互不拼接的 profile：

| Profile | 固定输入 | 每次重建 | 目的 |
| --- | --- | --- | --- |
| `projection-build` | 同一 immutable SnapshotTableArtifact。 | CanonicalizationManifest、RepositoryImportArtifact；fresh output。 | 单独测 storage projection。 |
| `repository-effect` | 同一 prebuilt content-digested RepositoryImportArtifact。 | Fresh repository、import、commit、full readback。 | 隔离 Repository Service。 |
| `canonical-write-e2e` | 同一 SnapshotTableArtifact。 | Projection、artifact、import、commit、readback。 | 完整 canonical write。 |
| `history-sequence` | 固定 immutable revision chain。 | 每代次 artifact 和正式 Repository history。 | 多代次增长。 |

Profile 之间的数字不能相加。`repository-effect` 不得重建 projection；`projection-build` 不得命中前次 artifact；`canonical-write-e2e` 必须真正重跑完整路径；每个 cold sample 使用 fresh repository 和 run-scoped operation identity。

正式 workload 分别报告，不建立缺乏业务依据的加权综合分数：

| Workload | 作用 |
| --- | --- |
| `initial-load` | Empty repository 的首次 canonical import。 |
| `canonical-no-change` | Raw unstable/ignored-only change；只测 projection/no-change detection。 |
| `sparse-business-change` | 少量 retained values 的常规变化。 |
| `row-churn` | 业务行 insert/delete。 |
| `compatible-schema-change` | Retained canonical schema 的正常演进。 |
| `normal-history-30` | 30 个确定性业务代次，建立常规增长斜率。 |
| `retention-stress-100` | 100 代次 scheduled capacity stress，不进入普通 PR。 |
| `ordered-position-shift` | 罕见 `no` 大范围漂移，独立诊断。 |
| `storage-projection-upgrade` | 极罕见规则升级/alignment，独立诊断。 |

Accepted baseline 必须覆盖 representative typical dataset 的 initial/sparse/row-churn/schema/history-30，以及 upper-bound representative dataset 的 initial/change/readback。`canonical-no-change`、history-100、ordered shift 和 projection upgrade 单独报告，不能通过人工权重改变正常路径结论。

真实 immutable revision chain 优先；缺少特定 change shape 时使用固定 generator version、seed 和完整 result digest 的确定性变换。Benchmark 运行时不得随机生成未固定的输入。

### 6.16 Multi-generation retention lifecycle 与 GC checkpoint

每个标准代次必须模拟正式可达历史：

```text
canonicalize
  -> submit candidate commit
  -> full readback VERIFIED
  -> mainline CAS/archive-equivalent production mechanism
  -> remove transient operation/staging refs
  -> quiescence
  -> record storage
  -> next generation
```

规则：

- 保留 mainline 可达的完整正式历史和仍被业务 retention owner 引用的 commit。
- 清除 transient staging、operation ref 和实验失败残留，不能把测试垃圾算作长期增长。
- 不通过“每代次重新创建 repository”模拟历史，也不能过度删除正式 commit 得到虚假低增长。
- 记录每次 commit 后增量、累计大小和 working-storage high-water。
- 30/100 代次序列结束并达到 quiescence 后才执行固定 maintenance/GC checkpoint；GC 不进入单次 Submit latency。
- GC 前后都记录 physical size、reclaimed bytes、duration 和保留 commit/ref closure。

具体 Dolt maintenance 命令/参数和生产周期延后，但同一 baseline series 必须固定 Dolt version 与 maintenance policy。

### 6.17 时间、吞吐、内存与存储指标

Required time/throughput：

```text
each exclusive phase duration
effect/journey total duration
canonical rows per second
canonical encoded bytes per second
tables per second
readback rows/bytes per second
GC/maintenance duration separately
```

不能只报告 rows/s；宽表、窄表和 table fixed overhead 必须通过 canonical bytes/s 与 tables/s 一并解释。

Memory authority：

- 各 Backend/worker、Repository Service/Dolt container 分别记录 cgroup peak。
- 按同一 monotonic timeline 同步采样 run-scoped containers；`pipeline_memory_peak` 是同一时刻各 container actual usage 之和的最大值。
- 禁止把不同时间出现的各 container independent peak 直接相加。
- Linux 优先使用 cgroup memory authority；fallback process-tree RSS sampler 必须记录 method/interval，不同方法不可直接比较。
- Host page cache、container runtime 和 benchmark runner 单独报告；CPU time、read/write bytes 同样提供 component 和 pipeline 视图。

Storage authority 至少分四类：

| Owner | Required measurements |
| --- | --- |
| SourcePackageArtifact store | Raw bytes、content-digest dedup growth。 |
| Canonical Dolt repository | Apparent/allocated bytes、每代增量、累计增长、pre/post-GC bytes。 |
| Repository metadata | Registry、operation journal、manifest/evidence bytes。 |
| Temporary working storage | Import artifact/staging/transient high-water，cleanup 后不计 durable total。 |

“删除不稳定列减少存储”首先是 Dolt physical-growth 假设；只测 Dolt 时不能宣称系统总存储下降。系统容量预算使用各 owner 总和，但必须保留分项。SourcePackageArtifact durable retention 和去重成本不能隐藏在 Repository 指标之外。

### 6.18 Repetition、统计与 result eligibility

单代次 profile 使用一次 warm-up 加至少 5 次有效 measured run；cold profile 每次创建 fresh repository。报告全部原始样本、median、MAD、min/max；少于 20 个样本不报告伪精确 P95，需要 P95 时至少执行 20 次。Multi-generation profile 至少执行 3 条完整 fresh-repository sequence，逐代保存指标。

不静默删除 outlier；只能标记并解释。失败 sample 和原始 evidence 必须保留，自动 retry 不能覆盖第一次结果。Correctness/validation 未通过的运行不进入任何 performance aggregate。

Benchmark 复用 Oracle runner 四态：

```text
PASSED
ASSERTION_FAILED
HARNESS_ERROR
UNSUPPORTED
```

- `PASSED`：正式路径、full readback validation、required metrics 和 cleanup 全部完成。
- `ASSERTION_FAILED`：valid dataset 暴露 schema/digest mismatch、row loss、非法终局或其它 correctness failure。
- `HARNESS_ERROR`：dataset/environment/measurement/cleanup 不能形成可信结论；稳定 diagnostic 包括 `DATASET_UNAVAILABLE`、`DATASET_IDENTITY_MISMATCH` 等。
- `UNSUPPORTED`：明确的 profile/environment capability 缺口，不是 pass。

`Cold` 第一版表示 fresh repository、fresh service/process 且不复用 application artifact/cache；不要求清除宿主 OS page cache。真正 system-cold 需要独立受控 machine profile，不能与普通 container-cold 混为同一 series。

### 6.19 Measurement version、baseline series 与 record

独立的 `measurement_contract_version` 拥有 stage boundary、metric unit/denominator、required metrics、sample eligibility、aggregation、cold/warm、GC checkpoint 和 result schema。上述任一语义发生不兼容变化必须升级版本；只增加 optional diagnostic 字段可以保持版本。

以下变化不一定升级 measurement contract，但必须建立新的 baseline series，不能判定为同线代码 regression：

- Dataset revision/change chain。
- Storage projection/ruleset/canonical encoding/readback contract。
- Dolt、Repository Service image或 production provider。
- CPU/memory/filesystem/volume driver/environment profile。

Accepted baseline 使用不可变、machine-readable `BenchmarkBaselineRecord`：

```text
baseline_id/status/supersedes_baseline_id
measurement contract digest
git revision
safe dataset id/revision
environment/image/component digests
validation status
all measured samples
median/MAD/min/max
external evidence digest/ref
known limitations
```

权威 JSON 可以生成 Markdown report；report 不是第二事实来源。Accepted record 不原地覆盖，新 record 显式 supersede。Git 内 record 不包含 private dataset digest、host path、raw row 或敏感 log；完整 evidence、logs、repositories 位于 Git 外并 content-digested。

### 6.20 Production entrypoints 与 run validity

Benchmark 不建设第二条执行路径：

```text
projection-build       -> table_projection public capability
repository-effect      -> Repository Service public client/wire contract
canonical-write-e2e    -> production Submit worker/job definition
history-sequence       -> production import/readback/CAS/cleanup mechanisms
```

禁止调用私有 step、绕过 journal/commit/readback/validation、直接修改服务端目录、使用 benchmark-only import fast path、伪造 VERIFIED evidence，或为计时改变 production batch/order/digest 语义。生产组件通过 typed diagnostic spans/counters 暴露阶段；runner 只观察，不重新实现。

正式 run preflight/validity 至少要求：

- 同一 machine 无并发正式 benchmark，同 Repository 只有一个 writer。
- Container topology、quota、volume/filesystem 与 environment profile 一致。
- Disk headroom 达到 profile 安全水位。
- 无未声明 background GC、backup 或其它 Repository maintenance。
- 服务 health/quiescence 后才开始计时。
- Container restart、OOM、异常 throttling、disk exhaustion 或 required metric gap 使结果成为 `HARNESS_ERROR`。
- Ambient load、CPU throttling、memory/disk pressure 进入 environment diagnostics。

### 6.21 First accepted baseline capture gate

首份 accepted numeric baseline 必须同时满足：

1. Storage projection、RepositoryImportArtifact、SnapshotManifest 和 measurement contract 已版本化。
2. Normative fixture/vector、Repository conformance 和 full readback tests 全部通过。
3. 最小 Repository Service container 已满足 health、persistent volume、restart recovery 和固定 image/Dolt identity。
4. External dataset identity/validation 通过。
5. 四类 benchmark profile 都只走 production public entrypoint。
6. Required 单代次 profile 至少 5 个有效 measured samples。
7. Required history profile 至少 3 条完整 fresh-repository sequence。
8. 所有进入 aggregate 的结果均为 `PASSED`。
9. Baseline record、samples、environment fingerprint 和 external evidence digest 完整。
10. Storage projection owner、Repository owner 和 environment profile owner 共同审核接受。

Capture gate 前的实现不能声明 accepted performance baseline；capture gate 后任何优化只能在 correctness 继续通过且同 baseline series 可比时声称收益。

### 6.22 Intentional conflict、延后事项与本轮收敛

现有 formal implementation stages 把 Phase 0 写成直接记录 parse/materialize/projection/Dolt 等新路径性能；在完整 vNext path 尚不存在且 legacy benchmark 已被排除后，该顺序不可执行。Formal 整理时必须采用 6.11 的 measurement-contract-now/capture-after-walking-slice 模型。

现有 `capabilities/repository-import.md` 和 benchmark runbook 中的 `business_small/medium/large` identity、provider ranking/matrix、host path、旧 Snapshot materialization 阶段及已有数值只作为历史实验依据，不自动进入新的 dataset、profile、stage 或 accepted baseline contract。第一版 production route 只有一个；替代 provider 只是 spike，直到后续 benchmark/ADR 明确提升。

以下事项延后，不阻塞本轮架构：具体 CPU/memory quota、绝对 latency/capacity budget、relative regression threshold、Dolt GC 命令与周期、RSS sampler/interval、baseline record 物理目录/报告样式，以及 Kubernetes、HA、autoscaling 和完整 backup retention。它们分别由 0E、实现 policy 或后续生产硬化拥有。

三轮访谈后，本子题不存在剩余架构级阻塞。Phase 0 measurement contract 的退出条件是：上述 stage/profile/workload/result/storage/capture gate 可形成版本化 schema/runner contract；真实 numeric baseline 明确等待首条正确 containerized production path，而不是等待 legacy 对比或提前实现优化。

## 7. Phase 0 讨论收敛状态与 formal 整理

0B 的主要业务状态、失败语义和异常 golden 范围，0C/0D 的 versioned fixture manifest、目录层级、scenario naming、golden 公共 envelope、canonical normalization、Shared Kernel 逐字节 encoding 与跨语言 vectors、Oracle runner、Repository fault injection、恢复 checkpoint execution protocol、测试材料治理与外部 benchmark dataset 边界，Raw Source Artifact + Canonical Dolt Repository 重构原则，以及新架构自身 performance measurement/capture contract 已形成阶段性结论。

当前没有会改变 Phase 0 核心架构的待讨论阻塞项。下一步应按 ownership 将本文重新整理到 formal contract/ADR/implementation stages；不能直接移动、改名本文或把整份 temporary notes 作为一个大型正式 contract。Numeric baseline、绝对性能/容量预算和 regression threshold 按 6.11/6.21 延后到可执行纵切与 0E，不阻塞当前 discussion closure。

## 8. Formalization 状态与逐节映射

状态：**已 formalized（2026-07-19）**

本文继续原位保存为讨论证据，不移动、不改名、不删除。自该日期起，normative 语义由下表中的唯一 formal owner 持有；本文不再作为第二份正式规范。其他 formal 文档只链接 owner contract，ADR 只记录决策理由。

| Temporary 主题 | 唯一 normative owner | Formal 落点 |
| --- | --- | --- |
| 2.1–2.5 legacy oracle 权威、差异分类、不兼容变更 | Conformance Harness | [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md)、[ADR 0006](../../formal/adr/0006-language-neutral-fixture-oracle.md) |
| 3.1–3.5 业务旅程、Upload/Preview、最小持久业务事实 | 对应 Domain/Application 子 owner | [Business Lifecycle and State](../../formal/contracts/business-lifecycle-and-state.md)、[ADR 0002](../../formal/adr/0002-minimal-persisted-business-state.md) |
| 3.5/4 中 Submit/Archive execution、T1/T2/T3、FailureDescriptor 与恢复终局 | 对应 Application；Repository evidence 由 Repository Service | [External Effect and Recovery](../../formal/contracts/external-effect-and-recovery.md)、[ADR 0003](../../formal/adr/0003-external-effect-reconciliation.md) |
| 4 中 Workspace、Review、Baseline、Candidate/Plan/Result 状态对象 | 对应 Domain/Application 子 owner | [Business Lifecycle and State](../../formal/contracts/business-lifecycle-and-state.md) |
| 4 中异常 fixture/golden 分轨与 recovery scenario | Conformance Harness；expected content 由绑定 semantic owner | [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md) |
| 5.1–5.15 manifest、目录、scenario naming、golden envelope、provenance | Conformance Harness | [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md)、[ADR 0006](../../formal/adr/0006-language-neutral-fixture-oracle.md) |
| 5.16–5.29 JCS、scalar、identifier、temporal、digest、row/collection framing、vectors | Shared Kernel | [Shared Canonical Encoding](../../formal/contracts/shared-canonical-encoding.md)、[ADR 0005](../../formal/adr/0005-shared-canonical-encoding.md) |
| 5.30–5.46 runner/harness、profile、fault/recovery、evidence、材料与 external dataset | Conformance Harness | [Fixture Oracle and Conformance](../../formal/contracts/fixture-oracle-and-conformance.md) |
| 6.1–6.10 raw source authority、storage/comparison projection、key、ordered no/gid、manifests、artifact retention、upgrade | Table Rules/Storage Projection；generic effect 由 Repository Service | [Canonical Storage and Repository Boundary](../../formal/contracts/canonical-storage-and-repository-boundary.md)、[ADR 0004](../../formal/adr/0004-raw-source-artifact-and-canonical-dolt-storage.md) |
| 6.11–6.22 measurement、container authority、profiles/workloads、retention/GC、metrics、baseline lifecycle/capture gate | Performance Measurement | [Performance Measurement and Baseline](../../formal/contracts/performance-measurement-and-baseline.md)、[ADR 0007](../../formal/adr/0007-vnext-performance-baseline-authority.md) |
| 跨模块 contract 类型、public/persisted/wire、版本轴 | 各 semantic owner；taxonomy 负责分类治理 | [Contract Taxonomy and Ownership](../../formal/contracts/contract-taxonomy-and-ownership.md) |
| 分阶段交付顺序与 cutover gate | Backend vNext Architecture | [Implementation Stages](../../formal/plans/implementation-stages.md)、[Architecture and Refactoring Plan](../../formal/architecture/architecture-and-refactoring-plan.md) |

本轮 formalization 明确保留的延后项：旧 Dolt repository migration/compatibility、Repository transport/物理 journal 技术、绝对性能与容量预算、regression threshold、Dolt maintenance policy 和生产 HA。它们没有被本文或 formal contract 擅自决定。
