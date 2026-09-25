# ADR 0020: Project Identity and Dataset Replacement in P5

状态：Proposed（repository owner 决定 2026-09-25；待 P5 架构收口 S0 独立文档审核）

日期：2026-09-25

决策 owner：Backend vNext Project Identity / Workspace, Submission and Archive Applications

关联阶段：P5 架构收口 S4；落实 P3-R5 identity gate 的业务意图

## Context

- 旧设计以 `version-manager-overlap/v1` 判定上传数据是否属于当前项目：
  - 不同项目进入数据替换视图；
  - 无法判定时要求继续确认；
  - 提交与归档各需一次带审计的确认。
- P5 中身份评估 capability 不存在，Preview 固定产出 `SAME_PROJECT`，comparison、risk、surface、bundle 中的相关分支都没有生产者。
- 该判据不能达到 100% 可靠，因此不能用来阻断流程；它只应改变展示方式，并要求人工确认。
- 旧设计要求 Preview 在“无法判定”时先暂停等待确认，这需要改变 P5 固定的三步 Preview JobDefinition。

## Decision

1. **新增流程中立的 `project_identity` capability**，实现 `version-manager-overlap/v1`，输入两侧规范快照，输出不含原始行的评估结果。
2. **Application 决定适用性。**
   - before 侧为供给时的初始空基线时，结果为 `NOT_APPLICABLE`；
   - FULL 的两个 pair 分别评估；
   - History compare 不评估。
3. **判定为不同项目时，使用 comparison 的 `DATASET_REPLACEMENT` 模式**（表级替换事实，不做实体配对），risk 产出比较级 `HIGH`。
   - 该判定不可由用户改为同一项目；需要行级差异时，经 History compare 查看该提交的 commit。
4. **Preview 始终完成**，不设暂停门；无法判定时附诊断。
5. **AcceptSubmit 按 Preview 结论要求确认**：`ACCEPT_DATASET_REPLACEMENT` 与 `ACCEPT_UNVERIFIABLE_DETAILED_RESULT` 两个独立动作，绑定评估集摘要，理由必填。
   - 确认进入请求指纹，随 Attempt 冻结，并复制到 Submission。
6. **Archive 新增身份异常 subject**。选中带身份确认记录的 Submission 时，需要带理由的肯定处置；复用既有异常处置事件机制。
7. **Review 与 History 只读展示身份异常。**

## Alternatives

- **完整沿用旧设计，含 Preview 暂停门**：放弃。需要新增 Preview 等待状态或重跑机制，并触发 P5 §12 的重开条件；它相对本决定的增益只是推迟详细结果的展示时机。
- **以校验门直接拒绝“不同项目”**：放弃。判据误判时会阻断正常归档。
- **不做检测**：放弃。误传只能靠审核人从差异中发现。

## Consequences

- 新增 A 类持久事实：PreviewResult 身份结论、身份确认记录、Archive 身份异常事件。
- HTTP 受理 DTO 增加 `identity_confirmations`，并新增两个 409 错误码。
- Business Lifecycle 升至 3.1.0（与 ADR 0019 一并）。
- 工作量约与 P5-5C 相当。

## Required Verification

- 身份规则判定类别（合成夹具）。
- 初始空基线为 `NOT_APPLICABLE`。
- 替换事实与比较级风险。
- 确认缺失、多余、摘要不符、理由长度与重放。
- Archive 处置与 StartArchive 校验。
- compose 跨项目旅程与“无法判定”旅程。

## Reopen conditions

- 需要在 Preview 阶段暂停确认。
- 需要改判“不同项目”。
- Review 阶段需要独立的身份确认交互。
- 出现比 `version_manager` 更可靠的判据。
