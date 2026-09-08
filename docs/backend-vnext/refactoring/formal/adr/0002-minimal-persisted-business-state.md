# ADR 0002: Minimal Persisted Business State

状态：Accepted

日期：2026-07-19

决策 owner：Backend vNext Domain Architecture

关联阶段：Phase 5

2026-09-06 amendment：Archive不再持久化`ArchiveExecution`。`StartArchive`是本地幂等短
事务，直接把既有合格Submission commit绑定为新BaselineNode，并原子创建ArchivePlan/
ArchiveResult、CAS推进BaselineHead、分类未选sibling和释放Workspace占用。Repository
`main`与业务BaselineHead分离；Review不移动或清理Repository ref。

## Context

Legacy 和早期草案把执行阶段、read-model label、审核过程、archive candidate/batch 与成功结果重复持久化。多个模块必须同步推进同一含义，失败恢复时容易出现状态漂移。本次是不兼容重构，可以根据稳定业务事实重新划分 aggregate，而不继承旧 persistence shape。

## Decision

持久化最小业务事实，其他含义由 owning application 派生。Workspace 只持久化 `OPEN/CLOSED` 与 current/active refs；UploadRevision 和 PreviewResult 是不可变绑定；Submit 在 Repository VERIFIED 前只创建 SubmitAttempt，不创建 Submission；Review 不包含单独 start action 或中间审核状态；Baseline 使用 immutable BaselineNode + BaselineHead；Candidate、PreviewArchivePlan与HistoryTree是只读 projection；StartArchive 成功时才冻结 ArchivePlan；ArchiveResult 是归档结果权威。

不建设baseline batch aggregate；Candidate entity不落库；不建设ArchiveExecution、archive
dry-run状态和复制的archive状态。完整History从immutable业务事实派生，不给Repository
commit写入业务状态。精确对象、状态与owner由
[Business Lifecycle and State Contract](../contracts/business-lifecycle-and-state.md)唯一规定。

## Alternatives

- 保留 legacy 状态机并通过 adapter 映射：拒绝，因为会永久维护两套含义。
- 建立统一 lifecycle aggregate：拒绝，因为 Workspace、Submit、Review、Baseline 和 Archive 具有不同 owner 与事务边界。
- 为查询便利持久化所有 projection：拒绝；只有性能证据和一致性策略充分时才可引入可重建 read model。

## Consequences

业务状态更少、owner 更清晰，重放和恢复只需维护权威事实。查询层需要显式构造 projection；持久 schema 与 legacy 不兼容，迁移必须单独决策。旧接口若暴露已删除状态，只能在 interface read model 中派生，不得反向污染 domain。

## Required Verification

- Domain 状态机、projection derivation 和 persistence schema tests。
- Submit VERIFIED 前不存在 Submission，Finalize 重放只产生一个 Submission。
- Review、Archive 与 Baseline journey 不出现已删除状态/对象。
- Workspace占用、BaselineHead CAS、ArchiveResult和sibling disposition在重复请求与事务失败
  下保持一致；Archive不产生Repository effect或重复commit。
