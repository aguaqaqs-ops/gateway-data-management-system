# ADR 0018: Canonical-Domain Comparison and Comparison Rule View

状态：Proposed（repository owner 决定 2026-09-25；2026-09-26 按 S0 独立审核与 DC10–DC22 修订；待独立复审）

日期：2026-09-25；修订 2026-09-26

决策 owner：Backend vNext Architecture / Table Rules / Storage Projection / Comparison

关联阶段：P5 架构收口 S2a、S2b、S3

详细设计：[P5 架构收口详细设计](../plans/p5-arch-closure-design.md) §4、§8；依据
[S0 独立审核报告](../plans/p5-arch-closure-s0-independent-docs-review.md) 与
[S0 Owner 决议记录](../plans/p5-arch-closure-s0-owner-decisions.md)

## Context

- 总纲 §7.2 规划了独立的 `comparison_projection` capability，但它一直只是占位；表规则到比较语义的映射没有 owner。
- History 在 Application 中自行投影 ordered 与忽略列（`_project_table_policy`），Preview 与 Submit 完全不传。
- Preview 的上传侧是原始 SQL 快照，基线侧是 Repository 中的规范形态。实验表明内容相同的 `com_cfg` 在两种上传模式下都被判为 `DEGRADED`。
- R4 设计 §4.3 定义的 SKIP、SNAPSHOT_ONLY、BROWSE_ONLY、UPDATE_ONLY 比较语义在任何链路都没有生效。
- 同一规则的第二份“表形态”实现已经造成过漂移（ADR 0017）。
- S0 独立审核补充确认：
  - r1 要求两侧规则集 digest 相等，与 Ruleset Activation §3、§5 冲突，任何规则变更都会使 Preview 与 Submit 死锁；
  - 规范快照同一性定义不足：SET 解码、JSON 往返、可空主键、伪 gid 的类型与列序都会造成分歧；规范状态摘要与比较提前退出看不到 schema 变化；
  - 9 条 ordered 规则把结构列 `no` 放入 `ignored_columns`，违反 Canonical Storage §2；
  - Dolt 2.1.11 拒绝 `TEXT` 主键与显式可空的主键列；
  - storage_projection 只支持有限的类型词表，真实数据覆盖未知；
  - import 包由 schema SQL 与 mutation_planning 的 DML 组成，T1 与 prepare 以启发式挑选导入表；replay 只 DROP/CREATE 包内表，删表不成立。

## Decision

1. **比较只在规范域进行。** 规范快照的 descriptor 等于 import schema：
   - 只含 retained columns；列类型取 storage codec 的规范 SQL 类型；键列一律 NOT NULL；规范键为主键；不含 SKIP/OMIT 表；ordered 表为 `gid INT UNSIGNED NOT NULL` 且已分配伪 gid；
   - 物理列序不属于规范身份（DC13）；
   - 规范快照由 storage_projection（从原始快照）或 Repository 读取（从 commit）产生；两者对同一内容必须 descriptor 级相等，每表 canonical schema digest、行数与 `raw_content_digest` 相等；
   - 分歧在编码 owner 或存储表示的选择中修正，不在比较侧特判。
2. **storage_projection 是规范形态的唯一实现。**
   - `project_canonical_table_set` 输出规范表集、`CanonicalizationManifest` 与全部诊断；投影失败时 Preview 整体 FAILED，并一次列出全部失败的表与列（DC14）；
   - `publish_canonicalization_manifest` 只发布 manifest；
   - `render_import_schema_sql(import_input, removed_tables)` 渲染 import schema；import DML 仍由 mutation_planning 生成，打包沿用 `pack_repository_import_entries`；三者在 Submit 的 infrastructure publication adapter 中组合，adapter 实现既有 `SubmitImportPublicationPort`；
   - Submit 复用 Preview 的规范投影：Attempt 在 T1 冻结 PreviewResult 的规范表集合闭包与 manifest，prepare 不再二次投影原始快照；
   - 上传代表完整规范状态：冻结 expected parent 中有、规范状态中没有的表在新 commit 中删除（DC18）。
3. **table_rules 提供 `ComparisonRuleView`**，与 `StorageRuleView` 对称，逐表给出比较角色、产物范围、不参与比较的列与 ordered 参数。
   - comparison 以运行期（当前激活）规则集派生的 `ComparisonRuleSet` 为必填输入（DC10），不校验两侧的规则集 digest；
   - 某侧的存储身份与运行期规则推导的存储视图不同时，按 Canonical Storage §7 做 alignment/fallback，无法安全对齐时该表为 DEGRADED；
   - `ComparisonTablePolicy` 降为 comparison 内部类型。
4. **列处置拆分。**
   - `TableRuleRecord` 新增 `compare_excluded_columns`，表示保留在存储中但不参与值比较；`ignored_columns` 维持 `DROP_FROM_STORAGE`；
   - 两者不相交，也不得包含规范键、ordered 身份列或结构列；
   - 9 条 ordered 规则去掉 `ignored_columns` 中的 `no`，`no` 作为结构列由 ordered 语义处理；
   - `composite_signal_point` 保留 `formula_ast_json`、`point_name` 为 compare-excluded，只以 `formula_digest` 比较（DC4）。
5. **只存不比的变化可见。** SNAPSHOT_ONLY/BROWSE_ONLY 表的行数或内容不同，以及只有 compare-excluded 列变化时，产出表级“内容已变化”事实，不产出记录，不参与行级风险（DC16）。
6. **存储类型词表与约束。**
   - 词表：STRING 族（CHAR/VARCHAR/TEXT、ENUM、SET、JSON）、INT、BIGINT、INT UNSIGNED；其余类型 fail-closed；
   - S1 kickoff 普查发现存储表中有词表外类型时，在 S2a 扩充，扩充须覆盖同一性、renderer 与真实 Dolt 往返（DC15）；
   - JSON：真实数据中有则以 LONGTEXT 存原文，无则 fail-closed；不采用有损的统一表示（DC12）；
   - storage_projection 在投影阶段拒绝不能作主键的键列类型；`composite_signal_point.source_table` 由派生表 schema owner 改为 `VARCHAR(64)`（DC20）。
7. **删除 `comparison_projection` 与 `business_projection` 占位**，capability DAG 相应调整。
8. **Preview 只展示规范业务状态的差异。** 被规则丢弃的列与 SKIP 表不参与比较、不显示；原始 SourcePackage 仍完整保留。

## Alternatives

- **按总纲原设计实现独立的比较投影，对原始侧与规范侧各投影一次**：放弃。同一规则会产生两份“表形态”实现，原始侧也没有伪 gid。
- **把 History 的投影函数提成 Application 共享模块**：放弃。无法解决域不一致，规则语义仍停留在 Application。
- **要求两侧规则集 digest 相等（r1）**：放弃。与 Ruleset Activation §3、§5 冲突，非破坏性激活后 Preview 与 Submit 死锁。
- **使用两侧中较新的规则集**：由运行期规则集取代。没有回滚时二者等价；运行期规则不需要规则集全序，也不需要持久化历史规则集，并与 Ruleset Activation §5 一致。
- **两侧统一 JSON 规范表示**：放弃。Dolt 的 JSON 规范化有损（大整数精度、重复键、数值写法）。
- **在比较侧特判编码差异**：放弃。会让同一性依赖比较实现，Submit 与 History 仍会看到分歧。

## Consequences

- Preview 所见即 Submit 所写；存储不支持的类型在 Preview 即失败，并一次列出全部失败项。
- Preview 每个上传侧多一次规范投影，Submit 相应少一次；prepare 多一次对 expected parent 的只读 catalog 读取。
- 规则调整使 ruleset digest 变化；DC6 下无兼容负担，所有比较相关 golden 一次性更新。
- 上游文档修订以候选文本随 S0 接受：Canonical Storage §2 升至 3.1.0、Contract Taxonomy §5、Architecture §7.1/§7.2/§10/§13、R4 设计 §4.2（详细设计附录 B）。
- `tests/test_architecture.py` 的 owner 集合与 DAG 需要同步。

## Required Verification

- 规范快照同一性（integration）：规范快照经真实 Repository Service 导入 Dolt，再经 HTTP Arrow 读回，descriptor 与摘要相等；覆盖 NULL、ENUM、SET、CHAR、JSON（按 DC12）、INT/BIGINT/INT UNSIGNED、伪 gid，S3 起加入 `composite_signal_point`。
- 规范状态身份（共享参数表）：空表增列、类型、长度、可空性、键序的变化都不被判为无变化，并在 Preview 中可见；只有列序不同时判为无变化。
- 内容相同的原始上传与规范基线比较结果为全表 UNCHANGED。
- 各规则角色的比较语义与 legacy oracle 一致；DC16 的表级事实。
- 存储身份不同时按 Canonical Storage §7 对齐。
- 投影失败形态与存储约束。
- prepare 删表的三种情形（integration）。
- compose：在非空基线上重复上传同一内容，得到 `NO_CANONICAL_CHANGE`。

## Reopen conditions

- 需要在 Preview 中展示被规则丢弃的列。
- 规范快照同一性只能在比较侧特判才能满足。
- 需要在比较中使用非运行期规则集（重开 DC10）。
- 生产环境出现新的协议族或软件版本：重跑类型普查与相关验收（DC22）。
- 已决定 fail-closed 的 JSON 或其他类型出现在存储表中（DC12、DC15）。
