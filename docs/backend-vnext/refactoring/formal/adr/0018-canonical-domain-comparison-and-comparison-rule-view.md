# ADR 0018: Canonical-Domain Comparison and Comparison Rule View

状态：Proposed（repository owner 决定 2026-09-25；待 P5 架构收口 S0 独立文档审核）

日期：2026-09-25

决策 owner：Backend vNext Architecture / Table Rules / Storage Projection / Comparison

关联阶段：P5 架构收口 S2、S3

## Context

- 总纲 §7.2 规划了独立的 `comparison_projection` capability，但它一直只是占位；表规则到比较语义的映射没有 owner。
- History 在 Application 中自行投影 ordered 与忽略列（`_project_table_policy`），Preview 与 Submit 完全不传。
- Preview 的上传侧是原始 SQL 快照，基线侧是 Repository 中的规范形态。实验表明内容相同的 `com_cfg` 在两种上传模式下都被判为 `DEGRADED`。
- R4 设计 §4.3 定义的 SKIP、SNAPSHOT_ONLY、BROWSE_ONLY、UPDATE_ONLY 比较语义在任何链路都没有生效。
- 同一规则的第二份“表形态”实现已经造成过漂移（ADR 0017）。

## Decision

1. **比较只在规范域进行。** 规范快照的形态与 storage projection 输出一致：只含保留列，以规范键为主键，不含 SKIP 表，ordered 表已分配伪 gid。
   - 规范快照由 storage_projection（从原始快照）或 Repository 读取（从 commit）产生；
   - 两者对同一内容的描述符摘要与状态摘要必须相等。
2. **storage_projection 是规范形态的唯一实现。**
   - 新增公开入口，输出规范表集与 `CanonicalizationManifest`；
   - 新增公开入口，从规范表集渲染 import 包；
   - Submit 复用 Preview 的规范投影，不再二次投影原始快照。
3. **table_rules 提供 `ComparisonRuleView`**，与 `StorageRuleView` 对称，逐表给出比较角色、产物范围、不参与比较的列与 ordered 参数。
   - comparison 以规则集为必填输入，并校验两侧规范快照的规则集 digest 与之相等；
   - `ComparisonTablePolicy` 降为 comparison 内部类型。
4. **列处置拆分。** `TableRuleRecord` 新增 `compare_excluded_columns`，表示保留在存储中但不参与值比较；`ignored_columns` 维持 `DROP_FROM_STORAGE`。
   - `composite_signal_point` 保留 `formula_ast_json`、`point_name`，只以 `formula_digest` 比较。
5. **删除 `comparison_projection` 与 `business_projection` 占位**，capability DAG 相应调整。
6. **Preview 只展示规范业务状态的差异。** 被规则丢弃的列与 SKIP 表不参与比较、不显示；原始 SourcePackage 仍完整保留。

## Alternatives

- **按总纲原设计实现独立的比较投影，对原始侧与规范侧各投影一次**：放弃。同一规则会产生两份“表形态”实现，原始侧也没有伪 gid。
- **把 History 的投影函数提成 Application 共享模块**：放弃。无法解决域不一致，规则语义仍停留在 Application。

## Consequences

- Preview 所见即 Submit 所写；存储不支持的类型在 Preview 即失败。
- Preview 每个上传侧多一次规范投影，Submit 相应少一次。
- 总纲 §7、Contract Taxonomy ownership matrix 与 R4 设计 §4.2 需要修订。
- `tests/test_architecture.py` 的 owner 集合与 DAG 需要同步。
- 所有比较相关 golden 需要一次性更新（无兼容负担）。

## Required Verification

- 规范快照同一性：SQL 投影与 Repository 读取对同一内容的摘要相等。
- 内容相同的原始上传与规范基线比较结果为全表 UNCHANGED。
- 各规则角色的比较语义与 legacy oracle 一致。
- compose：在非空基线上重复上传同一内容，得到 `NO_CANONICAL_CHANGE`。

## Reopen conditions

- 需要在 Preview 中展示被规则丢弃的列。
- 规范快照同一性无法由编码 owner 修正。
- 出现需要跨规则集比较的真实场景（按 Ruleset Activation and Migration 处理）。
