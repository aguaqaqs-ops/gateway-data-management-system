# Business Lifecycle and State Contract

状态：正式设计（Accepted）

阶段：Phase 0 结论；Phase 5 实现

Contract ID：`gateway-vnext.business-lifecycle-and-state`

Owner：各子领域 owner（见下表；本文不建立共同 aggregate）

Semantic version：`1.0.0`

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
| ArchivePlan、ArchiveExecution | Archive Application | 必须 |
| ArchiveResult | Archive Domain | 必须 |
| CandidateProjection、PreviewArchivePlan | Archive Application read model | 否；按请求派生 |

Application owner 负责命令验收、事务和跨 aggregate 协调；Domain owner 负责对象状态与不变量。Operation Runtime 只拥有执行状态，Repository Service 只拥有通用 repository effect，不取得业务对象所有权。

## 2. Workspace 输入与预览

Workspace 只持久化 `OPEN | CLOSED` 以及必要关系：当前 input revision、当前 preview、active SubmitAttempt/Submission 和关闭时间。`EMPTY`、`INPUT_READY`、`PREVIEW_READY`、`SUBMITTED` 等只可作为 read-model label，不能成为需要多模块同步推进的状态。

`UploadRevision` 表达一次用户输入选择及 generation，引用按 `INITIAL | MODIFIED` role 标识的 immutable `SourcePackageArtifact`。相同 bytes 的新用户动作可以创建新 revision；artifact bytes 按内容复用。格式校验在接受前失败不得创建 revision。

`PreviewResult` 是对 exact Workspace、UploadRevision、source/input digest、baseline、ruleset/contract version、Snapshot/Comparison digest 和 artifact closure 的不可变绑定。Preview 失败不使已接受 revision 失败；旧 generation 的计算不得覆盖 current preview。

Upload 与 Preview 是两个用例；接口可以组合调用，但 identity、失败和重试语义不能合并。Upload/Preview 的执行状态属于 Operation，不进入 Workspace。

## 3. SubmitAttempt 与 Submission

`AcceptSubmit` 必须校验 expected revision、preview、baseline、idempotency 和占用。若 Preview 的 canonical business digest 与当前 base 相同，以 `NO_CANONICAL_CHANGE` 在创建 Attempt 前拒绝；不得创建 Operation、Repository request、Submission 或 BaselineNode。

验收成功只创建 `SubmitAttempt` 与 Operation。Attempt 固化 source/baseline/preview、artifact、request/idempotency、Repository operation/evidence、终局和 Submission 引用。状态仅为：

```text
PREPARED -> EFFECT_PENDING -> FINALIZED
PREPARED -----------------> ABORTED
EFFECT_PENDING -----------> ABORTED
```

- `PREPARED`：业务已验收并占用 Workspace，尚未跨越可能产生 effect 的边界。
- `EFFECT_PENDING`：请求可能未发送、执行中、结果未知，或已应用但尚未完成 readback/业务 finalize。
- `FINALIZED`：Repository evidence 已 VERIFIED，且恰好一个 Submission 已创建。
- `ABORTED`：已经证明 effect 不存在，并保证原请求不再继续。

只有 VERIFIED Repository evidence 后才可创建 `Submission`；失败 Attempt 不产生半完成 Submission。`Submission.submit_attempt_id` 唯一。Finalize 重放先返回既有 Submission，再修正 Workspace/Operation 派生投影。

`FINALIZED` 将 Workspace 占用从 Attempt 原子切换到 Submission；`ABORTED` 释放 Attempt 占用。Operation 的 terminal status、effect `UNKNOWN` 或已应用但未 finalize 都不能单独释放占用。

## 4. Review

Review 当前投影仅为：

```text
PENDING | APPROVED | REJECTED | RETURNED_FOR_REVISION | WITHDRAWN
```

Review 使用不可变审核事件和当前 projection；不建设单独的“开始审核”命令或中间审核状态。Approve、reject、withdraw、return 是直接的短事务。Reject/withdraw/return 重新开放 Workspace 并清除当前输入、预览和占用；approved Submission 保持占用，直到对应 ArchiveResult 推进 BaselineHead。归档开始后不得 return。

Review 状态与 archive 结果正交。Repository 临时 ref cleanup 是独立、可重试的后置 operation；失败不回滚已经成立的 Review 事实。

## 5. Baseline 与 Archive

`BaselineNode` 是 immutable mainline version；`BaselineHead` 只保存当前 node pointer 和并发版本。当前/历史身份由 Head 派生。第一版不建设 baseline batch aggregate/lifecycle、invalidate 或重复的 ready/archive 状态。

`CandidateProjection` 只从当前 approved Submission 等事实派生，不持久化 candidate entity、selection、status 或 tag。稳定引用为 `submission_id + expected_candidate_digest`。

`PreviewArchivePlan` 是纯读计算，不冻结输入、不创建业务状态。`StartArchive` 重新校验 Head、candidate、confirmation、anomaly resolution 与 selection，并冻结 immutable `ArchivePlan`。Confirmation 和 AnomalyResolution 是 append-only 审计事实；有效性由当前 subject digest 和 sequence 派生。

`ArchiveExecution` 使用与 SubmitAttempt 同形但独立拥有的四态：`PREPARED | EFFECT_PENDING | FINALIZED | ABORTED`。不得抽取通用业务 aggregate。`ArchiveResult` 是成功后的归档权威，记录 mainline/history/closed-not-archived 结果；不得把相同状态复制到 Submission、Candidate 或 BaselineNode。

成功的 ArchiveResult 和 BaselineHead advance 在业务事务中保持一致；没有成功 mainline CAS 就不创建后继 BaselineNode。Repository evidence、业务 finalize、outbox delivery 和后置 artifact transfer 是正交事实。

## 6. Persisted 与 Derived 边界

明确禁止持久化：

- Workspace 计算阶段状态和 upload mode。
- 半完成 Submission。
- 中间审核状态或 archive 状态副本。
- Baseline batch aggregate。
- Candidate entity/status/selection/tag。
- Archive dry-run 状态。
- 可从 immutable facts、events、Head 或 ArchiveResult 唯一推导的重复字段。

需要查询时由 owning application 建 projection；projection 不是新的业务事实来源。

## 7. 版本与兼容性

本 contract 是不兼容重构基线，不承诺读取 legacy persistence record。旧 Dolt repository 的迁移/兼容由独立 cutover gate 决定。任何新增持久状态必须证明无法从现有权威事实可靠派生，并由对应 domain owner 提升 semantic version。

## 8. 验收标准

- 每个对象、状态和 projection 能定位到上表唯一 owner。
- Upload、Preview、Submit、Review、Archive 的 generation、idempotency 和并发测试通过。
- Submit 仅在 VERIFIED 后创建一个 Submission；`NO_CANONICAL_CHANGE` 无任何写 effect。
- Review 测试中不存在单独 start action 或中间审核状态。
- Archive 只在 Start 时冻结，Candidate/PreviewArchivePlan 不落库。
- BaselineHead CAS、ArchiveResult 和 Workspace 占用在失败/重放后保持一致。
- 持久 schema 中不存在 baseline batch、Candidate 状态或重复 archive 状态。

## 9. 关联文档

- [External Effect and Recovery](external-effect-and-recovery.md)
- [Canonical Storage and Repository Boundary](canonical-storage-and-repository-boundary.md)
- [ADR 0002](../adr/0002-minimal-persisted-business-state.md)
- [Architecture and Refactoring Plan](../architecture/architecture-and-refactoring-plan.md)
- [Implementation Stages](../plans/implementation-stages.md)
