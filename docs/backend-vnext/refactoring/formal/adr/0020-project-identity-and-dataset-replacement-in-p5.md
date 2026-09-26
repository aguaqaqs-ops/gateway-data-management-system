# ADR 0020: Project Identity and Dataset Replacement in P5

状态：Proposed（repository owner 决定 2026-09-25；2026-09-26 按 S0 独立审核、两份 r2 独立复审与 DC10–DC27 修订；待独立复审）

日期：2026-09-25；修订 2026-09-26

决策 owner：Backend vNext Project Identity / Workspace, Submission and Archive Applications

关联阶段：P5 架构收口 S4；落实 P3-R5 identity gate 的业务意图

详细设计：[P5 架构收口详细设计](../plans/p5-arch-closure-design.md) §7；依据
[S0 独立审核报告](../plans/p5-arch-closure-s0-independent-docs-review.md)、r2 独立复审
（[第一份](../plans/p5-arch-closure-s0-independent-rereview.md)、[第二份](../plans/p5-arch-closure-s0-independent-rereview-2.md)）与
[S0 Owner 决议记录](../plans/p5-arch-closure-s0-owner-decisions.md)

## Context

- 旧设计以 `version-manager-overlap/v1` 判定上传数据是否属于当前项目：
  - 不同项目进入数据替换视图；
  - 无法判定时要求继续确认；
  - 提交与归档各需一次带审计的确认。
- P5 中身份评估 capability 不存在，Preview 固定产出 `SAME_PROJECT`，comparison、risk、surface、bundle 中的相关分支都没有生产者。
- 该判据不能达到 100% 可靠，因此不能用来阻断流程；它只应改变展示方式，并要求人工确认。
- 旧设计要求 Preview 在“无法判定”时先暂停等待确认，这需要改变 P5 固定的三步 Preview JobDefinition。
- S0 独立审核补充：确认的输入边界、错误码与判定顺序需要写明；surface 当前从 comparison 导入 `IdentityStatus`；没有调用方向 surface 传入两侧 `table_artifacts`。
- r2 复审补充：r2 把 same-key 重放排在权限与 scope 之前，与现行实现相反（现行实现先校验权限与 exact scope，再查幂等记录），会绕过授权；理由的计量单位与 Archive 不一致。

## Decision

1. **新增流程中立的 `project_identity` capability**，实现 `version-manager-overlap/v1`，输入两侧规范快照，输出不含原始行的评估结果。
2. **Application 决定适用性。**
   - before 侧为初始基线时，结果为 `NOT_APPLICABLE`；初始基线恒为空（DC17），因此不会漏检已有数据；
   - FULL 的两个 pair 分别评估；
   - History compare 不评估。
3. **判定为不同项目时，使用 comparison 的 `DATASET_REPLACEMENT` 模式**（表级替换事实，不做实体配对），risk 产出比较级 `HIGH`。
   - 该判定不可由用户改为同一项目；需要行级差异时，经 History compare 查看该提交的 commit；
   - Application 向 surface 传入两侧 `table_artifacts`，bundle 据此导出同名表的两侧快照。
4. **Preview 始终完成**，不设暂停门；无法判定时附诊断。
5. **AcceptSubmit 按 Preview 结论要求确认**：`ACCEPT_DATASET_REPLACEMENT` 与 `ACCEPT_UNVERIFIABLE_DETAILED_RESULT` 两个独立动作，绑定评估集摘要，理由必填。
   - 输入边界：最多 2 项，每个 action 至多一次，action 须为上述枚举，摘要格式合法，理由与 Archive 理由使用同一校验（1–4096 UTF-8 字节，按原文持久化）；违反时返回 `422 REQUEST_VALIDATION_FAILED`；
   - 缺少所需确认返回 `409 PROJECT_IDENTITY_CONFIRMATION_REQUIRED`；提供了不需要的确认，或摘要与 current PreviewResult 不符，返回 `409 PROJECT_IDENTITY_CONFIRMATION_MISMATCH`；
   - 判定顺序：认证、当前权限与 exact scope（含 workspace 的精确 scope 与 Repository 映射）→ same-key 重放 → workspace、revision、preview 绑定与 CAS → baseline 绑定 → 陈旧判定 → `NO_CANONICAL_CHANGE` → 身份确认 → 占用与 ready closure。same-key 重放只越过其后可漂移的受理校验，不越过授权与 scope 校验；
   - 评估集摘要 = JCS{schema `project-identity-assessment-set/v1`；按 pair 顺序的 (pair_id, applicability, status, assessment_digest 或 null)}，包含 `NOT_APPLICABLE` 的 pair；
   - 确认的请求内容进入请求指纹（actor 与时间是服务端事实，不进入指纹），随 Attempt 冻结，并复制到 Submission。
6. **Archive 新增身份异常 subject**。选中带身份确认记录的 Submission 时，需要带理由的肯定处置；复用既有异常处置事件机制。
7. **Review 与 History 只读展示身份异常。** surface 的身份标注使用 surface 自有的中性类型，由 Application 映射，不新增 surface → project_identity 依赖。
8. **不采用** P3-R5 §5.1 的 continuation 与 server-side policy allowance（没有 Preview 暂停门，也就没有需要授权的继续计算），也不采用旧设计替换视图中的 side-local 业务 projection；替换展示沿用 surface 已实现的表级替换视图。

## Alternatives

- **完整沿用旧设计，含 Preview 暂停门**：放弃。需要新增 Preview 等待状态或重跑机制，并触发 P5 §12 的重开条件；它相对本决定的增益只是推迟详细结果的展示时机。
- **以校验门直接拒绝“不同项目”**：放弃。判据误判时会阻断正常归档。
- **不做检测**：放弃。误传只能靠审核人从差异中发现。

## Consequences

- 新增 A 类持久事实：PreviewResult 身份结论、身份确认记录、Archive 身份异常事件。
- HTTP 受理 DTO 增加 `identity_confirmations`，新增两个 409 错误码，输入边界沿用 `422 REQUEST_VALIDATION_FAILED`。
- Business Lifecycle 升至 3.1.0（与 ADR 0019 一并，详细设计附录 A）。
- 工作量约与 P5-5C 相当。

## Required Verification

- 身份规则判定类别（合成夹具），以及投影侧与 Repository 侧对同一内容得出相同 assessment。
- 初始空基线为 `NOT_APPLICABLE`。
- 替换事实、比较级风险与双侧导出。
- 确认的输入边界（共享参数表）、缺失、多余、摘要不符、判定顺序与重放；撤权或 scope 不符时重放被拒，只有可漂移的业务前置变化时重放返回原结果。
- Archive 处置与 StartArchive 校验。
- compose 跨项目旅程、“无法判定”旅程与 FULL 混合模式旅程。

## Reopen conditions

- 需要在 Preview 阶段暂停确认。
- 需要改判“不同项目”。
- Review 阶段需要独立的身份确认交互。
- 出现比 `version_manager` 更可靠的判据。
