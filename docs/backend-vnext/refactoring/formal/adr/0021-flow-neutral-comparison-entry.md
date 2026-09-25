# ADR 0021: Flow-Neutral Comparison Entry

状态：Proposed（repository owner 决定 2026-09-25；待 P5 架构收口 S0 独立文档审核）

日期：2026-09-25

决策 owner：Backend vNext Comparison / Backend Architecture

关联阶段：P5 架构收口 S2；撤销 P5 §2A.2 中“R5 已接受的 pair/view/applicability 词汇保留”

## Context

- Contract Taxonomy §4.4 要求 capability contract 与流程无关，但 comparison 公共面导出了 99 个名字，其中包括：
  - 上传模式：`InputCompleteness.FULL/MODIFIED_ONLY`；
  - 业务 pair 角色：`PairRole.BASELINE_TO_INITIAL` 等；
  - 流程视图：`PairViewKind.HISTORY/ARCHIVE_REPLAY`；
  - 受信流程绑定、身份门控与继续确认；
  - 生产中不可达的 provider 类。
- `bind_pair_input` 以这些词汇编码业务规则，例如 MODIFIED_ONLY 必须重建基线、History 必须携带受信绑定；`ARCHIVE_REPLAY` 在全仓没有消费者。
- 这些词汇在 P3-R5 被接受，§2A.2 只是冻结其扩张；本项目没有兼容负担。

## Decision

1. **comparison 的公共输入只有**：不透明 `pair_id`、两侧规范快照、`ComparisonRuleSet`、执行模式（`DETAILED | DATASET_REPLACEMENT`）、选项与契约版本。
2. **删除公共面上的流程词汇**，包括 `PairViewKind`、`PairRole`、`InputCompleteness`、`IdentityApplicability`、`ContinuationAction`、基线重建结果、受信流程绑定、继续确认绑定、`IdentityGateBlockedResult`、`InitialSnapshotResult`。
   - `IdentityStatus` 与评估协议移入 `project_identity`；
   - 删除 provider 类的公共导出。
3. **Application 拥有流程拓扑**：FULL 与 MODIFIED_ONLY 的 pair 列表与标签、History 视图、执行模式选择。
   - 初始空基线以零表 `before` 传入；
   - surface 的身份标注由 Application 提供。
4. **公共面按真实消费者收窄**，只保留请求、结果、facts、记录闭包 API 与入口函数。
5. 接受后同步修订 P5 §2A.2 与 P3-R5 设计的相关条款。

## Alternatives

- **保留词汇、继续冻结**：放弃。流程语义会继续留在 capability 中，新流程只能再扩词汇，或在 Application 里做映射绕开。

## Consequences

- comparison 契约、规划与测试需要重写入口部分；比较算法、记录与摘要语义不变（规范域变化由 ADR 0018 处理）。
- Preview 与 History 通过 Application 内共享的 pair 流水线调用同一入口。

## Required Verification

- 架构测试：comparison 公共面不含上述名字。
- 各上传模式的 pair 拓扑由 Application 测试覆盖。
- 比较 golden 在同一规范输入下保持不变。

## Reopen conditions

- 出现必须由 comparison 本身区分流程才能正确计算的真实需求；此时先证明无法在 Application 中映射为现有执行模式。
