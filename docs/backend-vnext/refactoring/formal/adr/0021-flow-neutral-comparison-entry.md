# ADR 0021: Flow-Neutral Comparison Entry

状态：Accepted（repository owner 于 2026-09-27 按 P5 架构收口 Entry Brief §5 接受；此前为 Proposed：2026-09-25 决定，2026-09-26 按 S0 独立审核与 DC10–DC22 修订）

日期：2026-09-25；修订 2026-09-26；接受 2026-09-27

决策 owner：Backend vNext Comparison / Backend Architecture

关联阶段：P5 架构收口 S1（provider 删除）、S2a；撤销 P5 §2A.2 中“R5 已接受的 pair/view/applicability 词汇保留”

详细设计：[P5 架构收口详细设计](../plans/p5-arch-closure-design.md) §6；依据
[S0 独立审核报告](../plans/p5-arch-closure-s0-independent-docs-review.md) 与
[S0 Owner 决议记录](../plans/p5-arch-closure-s0-owner-decisions.md)

## Context

- Contract Taxonomy §4.4 要求 capability contract 与流程无关，但 comparison 公共面导出了 99 个名字，其中包括：
  - 上传模式：`InputCompleteness.FULL/MODIFIED_ONLY`；
  - 业务 pair 角色：`PairRole.BASELINE_TO_INITIAL` 等；
  - 流程视图：`PairViewKind.HISTORY/ARCHIVE_REPLAY`；
  - 受信流程绑定、身份门控与继续确认；
  - 生产中不可达的 provider 类。
- `bind_pair_input` 以这些词汇编码业务规则，例如 MODIFIED_ONLY 必须重建基线、History 必须携带受信绑定；`ARCHIVE_REPLAY` 在全仓没有消费者。
- 这些词汇在 P3-R5 被接受，§2A.2 只是冻结其扩张；本项目没有兼容负担。
- S0 独立审核确认：待删除的流程词汇在 comparison 之外没有消费者，唯一例外是 surface 从 comparison 导入 `IdentityStatus`。

## Decision

1. **comparison 的公共输入只有**：不透明 `pair_id`、两侧规范快照、`ComparisonRuleSet`（由运行期规则集派生，DC10）、执行模式（`DETAILED | DATASET_REPLACEMENT`）、选项与契约版本。
2. **删除公共面上的流程词汇**，包括 `PairViewKind`、`PairRole`、`InputCompleteness`、`IdentityApplicability`、`ContinuationAction`、基线重建结果、受信流程绑定、继续确认绑定、`IdentityGateBlockedResult`、`InitialSnapshotResult`。
   - `IdentityStatus` 与评估协议移入 `project_identity`；
   - 删除 provider 类的公共导出；
   - `domain/workspace` 中同名的上传模式枚举属于 Workspace 领域，不受影响。
3. **Application 拥有流程拓扑**：FULL 与 MODIFIED_ONLY 的 pair 列表与标签、History 视图、执行模式选择。
   - 初始基线恒为空（DC17），以零表 `before` 传入，不需要单侧视图；
   - surface 的身份标注由 Application 以 surface 自有的中性类型提供。
4. **公共面按真实消费者收窄**，只保留请求、结果、facts、记录闭包 API 与入口函数。
5. P5 §2A.2 与 P3-R5 设计的相关条款已于 2026-09-27 随本 ADR 接受同步修订（详细设计附录 B.5；P3-R5 加“由本 ADR 取代”标注）。

## Alternatives

- **保留词汇、继续冻结**：放弃。流程语义会继续留在 capability 中，新流程只能再扩词汇，或在 Application 里做映射绕开。

## Consequences

- comparison 契约、规划与测试需要重写入口部分；比较算法与记录语义不变（规范域、规则角色与 schema 事实的变化由 ADR 0018 处理）。
- Preview 与 History 通过 Application 内共享的 pair 流水线调用同一入口。

## Required Verification

- 架构测试：comparison 公共面不含上述名字；surface 不导入 comparison 或 project_identity 的身份类型。
- 各上传模式的 pair 拓扑由 Application 测试覆盖，包括以零表 `before` 表示的初始基线。
- 比较 golden 在同一规范输入与同一规则集下保持不变。

## Reopen conditions

- 出现必须由 comparison 本身区分流程才能正确计算的真实需求；此时先证明无法在 Application 中映射为现有执行模式。
