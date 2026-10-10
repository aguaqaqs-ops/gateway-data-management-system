# P5 架构收口详细设计

状态：**ACCEPTED — S0 文档（r4）由 repository owner 于 2026-09-27 接受；ADR 0018–0021 为 Accepted；实现未授权**

日期：2026-09-27（r4 与接受）；r2、r3 为 2026-09-26；r1 为 2026-09-25

Owner：Backend vNext Architecture（收口牵头）；各项语义归属见 §11

入口：[Entry Brief](p5-arch-closure-s0-entry-brief.md) → 本文 → [执行计划](p5-arch-closure-execution-plan.md)

审核与决议：[S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)、
r2 独立复审（[第一份](p5-arch-closure-s0-independent-rereview.md)、[第二份](p5-arch-closure-s0-independent-rereview-2.md)）、
r3 独立复审（[第一份](p5-arch-closure-s0-independent-rereview-r3.md)、[第二份](p5-arch-closure-s0-independent-rereview-r3-2.md)）、
[r4 独立核对](p5-arch-closure-s0-independent-rereview-r4.md)、[S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)、[修订处置表](p5-arch-closure-s0-revision-disposition.md)

上游：[P5 §2A / §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-guardrails)、
[Architecture](../architecture/architecture-and-refactoring-plan.md)、
[Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)、
[Business Lifecycle 3.0.0](../contracts/business-lifecycle-and-state.md)、
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[Ruleset Activation](../contracts/ruleset-activation-and-migration.md)、
[P3-R4 设计](p3-r4-storage-projection-design.md)、[P3-R5 设计](p3-r5-comparison-design.md)、
[5E 设计](p5-5e-history-compare-design.md)；本轮提案 ADR
[0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
[0019](../adr/0019-commit-canonical-metadata-authority.md)、
[0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
[0021](../adr/0021-flow-neutral-comparison-entry.md)。

标记：**E** = 已实现事实（源码 @ `2172369803`）；**D** = 已接受设计；**P** = 本设计提案。

## 1. 目标、决定与非目标

目标：在 P5 整体 exit 前完成 §2A 收口：

1. 关闭 §2A.4 与 §2A.4.1 已确认问题，使 `tests/architecture_baseline.py` 清空，或剩余条目逐条
   具备 owner、理由和后续阶段；
2. 纠正核对确认的语义缺陷（§2），使 Preview、Submit、History 在同一规范业务状态上得出一致结论；
3. 交付 §2A.3 要求的代表性链路测量与 Phase 6 候选。

Repository owner 决定（DC1–DC9 为 2026-09-25，DC10–DC27 为 2026-09-26，详见
[决议记录](p5-arch-closure-s0-owner-decisions.md)）。本文据此设计，不再重开：

| ID | 决定 | ADR |
| --- | --- | --- |
| DC1 | 所有比较在规范域进行；表规则的比较语义由 table_rules 的 `ComparisonRuleView` 提供；删除 `comparison_projection` 占位。Preview 只展示规范业务状态的差异，被规则丢弃的列和 SKIP 表不参与、不显示（细化：DC13、DC14、DC16） | 0018 |
| DC2 | 以 Backend 持有的 `CanonicalizationManifest` 作为 commit 规范元数据权威；不在 Dolt 写隐藏表；不做读回校验；删除 hidden summary 重建并收缩 5E integrity incident 机制（细化：DC10、DC11、DC19） | 0019 |
| DC3 | 项目身份沿用旧设计三段式语义；“无法判定”的继续确认在 Submit 受理时收集，不设 Preview 暂停门；两个确认动作分开校验；“不同项目”不可改判 | 0020 |
| DC4 | composite_signal / `logics.xml` 接入 P5 业务物化；`composite_signal_point` 保留 `formula_ast_json`、`point_name` 但只以 `formula_digest` 比较（细化：DC20） | 0018 |
| DC5 | 撤销 §2A.2 对 R5 流程词汇的保留约定；comparison 只接收两侧规范快照、规则集、执行模式和选项 | 0021 |
| DC6 | 新项目无历史数据：可以直接改变 contract、checkpoint/payload、canonical bytes 与 digest；不建设兼容层或双读路径 | — |
| DC7 | before 侧为初始基线的 pair，身份评估为 `NOT_APPLICABLE`，首次提交不需要身份确认（DC17 后恒成立） | 0020 |
| DC8 | `logics.xml` 存在但解析失败或违反 composite 业务不变量时 Preview FAILED | — |
| DC9 | 删除以 hidden summary 为生产者的 5E History compare integrity incident 机制；ADR 0016 的 Operation integrity 不受影响（细化：DC19） | 0019 |
| DC10 | 比较语义统一使用运行期（当前激活）规则集；存储身份不同按 Canonical Storage §7 对齐（对齐方式与来源标记见 §4.5） | 0018、0019 |
| DC11 | 规则激活前完成的 Preview 在激活后受理时拒绝；已受理的 Preview/History 在激活后恢复时稳定失败；Submit 在 T1 后只用冻结产物（细化：DC23、DC24） | 0019 |
| DC12 | JSON 列：真实数据中有则以 LONGTEXT 无损存储，无则 fail-closed；不采用有损的统一表示（条件决议；细化：DC27） | 0018 |
| DC13 | 列序不属于规范业务状态 | 0018、0019 |
| DC14 | 规范投影失败时 Preview 整体 FAILED，一次列出全部失败的表与列 | 0018 |
| DC15 | 真实数据普查发现词表外类型时，在 S2a 内扩充存储类型词表（条件决议） | 0018 |
| DC16 | SNAPSHOT_ONLY/BROWSE_ONLY 表内容变化产出可见的表级事实 | 0018 |
| DC17 | 初始基线恒为空，不支持预置数据的初始库 | 0019、0021 |
| DC18 | 上传代表完整规范状态；删表以冻结的 expected parent 为依据 | 0018 |
| DC19 | Repository 读取不一致按依赖异常处理，不建持久 incident（细化：DC25） | 0019 |
| DC20 | composite `source_table` 为 `VARCHAR(64)`，由派生表 schema owner 修复 | 0018 |
| DC21 | S2 拆分为 S2a、S2b，分别独立审核 | — |
| DC22 | 真实数据：4 份代表性 dump（含同一项目前后两个版本，均带 `logics.xml`） | — |
| DC23 | Ruleset Activation §5 末句随附录 B.2 一并修订：带外部 effect 的 operation 按冻结产物继续，纯计算 operation 按 §1 稳定失败 | 0019 |
| DC24 | Preview 在受理时冻结运行期规则集 digest，每步执行前比较，不同即稳定失败 | 0019 |
| DC25 | manifest artifact 的 digest 与 Submission 记录不符时按稳定失败处理，附诊断、日志与指标，不属于 incident 范围 | 0019 |
| DC26 | canonical row hash 的 Rust 绑定放置由 Backend Architecture 在 r3 选定（结果见 §9 A6 行） | — |
| DC27 | DC12 触发时，在 S2a handoff 中按 Canonical Storage §8 写明 storage projection version 的处理（条件决议） | 0018 |

非目标：

- Phase 6 Rust 实现；新的 Repository effect、API 或 wire 变化；HA、外部 DB；legacy 数据迁移；性能通过阈值；
- 在线 ruleset 迁移与 STORAGE_BREAKING migration operation；规则集全序与历史规则集持久化（DC10）；
- 部分 Preview（DC14）；预置数据的初始库（DC17）；Repository 读取不一致的持久 incident（DC19）；
- 生产环境其他协议族与软件版本的覆盖（DC22，列为重开条件）；
- 5E slice 范围内的任何改动（5E slice exit 之前不改动其候选树）。

兼容性（DC6）：control DB 通过新增前向 migration 修改 schema，不做数据回填。新增列允许旧行为空，旧行在新判定中按
“不可用”处理，例如缺少规范状态摘要的 PreviewResult 在受理时按 derived-stale 拒绝。开发与测试环境的 control DB
与 Repository 数据在 S2b 前重建。所有 golden 与 digest 随语义变化一次性更新。

## 2. 当前事实与问题映射

### 2.1 r1 确认的语义缺陷

| ID | 事实（E） | 影响 | 归属 |
| --- | --- | --- | --- |
| R1 | Preview 上传侧是原始 SQL 快照（DDL 主键、全部列），基线侧读自 Repository，是规范形态（显式键为主键、存储丢弃列已删除、无 SKIP 表）。用 capability 公开入口实验：`com_cfg` 两侧内容相同，FULL `baseline_to_initial` 与 MODIFIED_ONLY 主 pair 均为 `DEGRADED`（`CURRENT_ONLY_COLUMNS`、`EFFECTIVE_KEY_CHANGED`）；独立审核已复现 | 基线非空后，以下表在 Preview 中降级或误报：显式键与 DDL 主键不同的表；4 张存储丢弃列的表（com_cfg、composite_signal_point、net_cfg、scdmod_para）；8 张 SKIP 表（在上传侧表现为新增表）；9 张 ordered 表（键、伪 gid 与 `no` 位置语义不一致） | W1 |
| R2 | 表规则的比较语义未生效：`BROWSE_ONLY`、`SNAPSHOT_ONLY`、`UPDATE_ONLY` 在任何链路都没有使用；History 在 `B/application/history/compare_jobs.py::_project_table_policy` 只投影 ordered 与忽略列；Preview/Submit 不传 `table_policies` | 与 R4 设计 §4.3 规定的比较含义不一致；同一对 commit 在 Preview 与 History 中的结果可以不同 | W1 |
| R3 | `NO_CANONICAL_CHANGE` 比较 Preview bundle digest 与 `compute_baseline_canonical_bundle_digest`（基线自比流水线的 bundle digest）；该流水线在 AcceptSubmit 预检中执行（`B/http/orchestration/submit_acceptance.py`），写事务复用预检结果 | 受 R1 影响基本不会命中；AcceptSubmit 同步请求承担整条比较流水线的成本 | W2 |
| R4 | `B/infrastructure/repository_read/http_arrow.py::_hidden_summary_from_streaming_tables` 从行重建 hidden summary，版本字段取运行时常量；`B/capabilities/snapshot_materialization/repository_ref.py` 随后再读一遍全表做交叉校验；读取按 record batch 逐列 `to_pylist()` 转成 Python 行；全仓无 hidden summary 写入方 | 违反 P3-R3“不从 catalog/rows 重建”；每次物化全表读两遍；无法得知 commit 的规则版本 | W2 |
| R5 | 上传包中的 `/comps/logic/logics.xml` 被暂存（`optional_xml_document_ref`）但从不解析；Preview/Submit 走纯 SQL 物化，`composite_logic_source_digest` 恒为空 | `logics.xml` 的修改被静默丢弃，不进入规范业务状态 | W5 |
| R6 | Preview 以 `_PreviewIdentityAssessment` 固定 `SAME_PROJECT`；独立 identity capability 不存在；comparison 的 `DATASET_REPLACEMENT` 只返回无 facts 的 `CHANGED`；risk 无任何处理 | 跨项目误传无法识别；identity gate 等分支无生产者 | W4 |

### 2.2 独立审核补充确认的事实

| ID | 事实（E，审核实验或源码核查） | 处置 |
| --- | --- | --- |
| E-a | storage_projection 只支持 STRING 族（含 JSON、ENUM、SET）、INT、BIGINT、INT UNSIGNED；其余类型与降级描述符（无 PK、重复键）返回 `UNSUPPORTED_TABLE` 或 `BINDING_INVALID`（ADR 0017） | §4.2（DC14、DC15） |
| E-b | Dolt 2.1.11 拒绝 `TEXT` 主键与前缀主键，拒绝显式可空的主键列；JSON 往返有损（大整数精度、重复键、数值写法） | §4.2、§8（DC12、DC20） |
| E-c | Repository Service 把 SET 映射为 Arrow `list<string>`；Backend 把它编码为 `StringScalar("['x', 'y']")`，与 SQL 侧 `SqlSetValue` 的摘要不同 | §5.2 |
| E-d | 规范 descriptor 若沿用原始 DDL 类型，伪 gid（`UnsignedIntegerScalar`）编码失败；`fast_row_digest` 对列序敏感 | §4.1 |
| E-e | `raw_state_digest` 不含 schema；comparison 提前退出只看 `compare_schema_digest`（表名、排序后的列名与键名）、行数与 `raw_content_digest`。因此类型、长度、可空性、键序的变化在两处都不可见；空表增列不改变 `raw_state_digest`，但比较显示 SCHEMA_CHANGED；有数据表的列序变化改变 `raw_state_digest`，但比较显示 UNCHANGED | §4.1、§4.5、§5.3 |
| E-f | import 在冻结的 expected parent（T1 时的 main）上重放；replay 只对包内表 DROP/CREATE；STRUCTURAL 校验要求表集合完全一致；T1 与 prepare 以 artifact id 前缀与摘要启发式挑选导入表 | §4.8（DC18） |
| E-g | 9 条 ordered 规则 `ignored_columns=("no",)` 同时是结构列，违反 Canonical Storage §2；52 条规则中只有 4 条真正丢弃列 | §4.4 |
| E-h | compose harness 默认把含表的 commit 作为 INITIAL 节点；供给 mapping 不校验 commit 为空 | §5.1（DC17） |
| E-i | import 包 = storage_projection 的 schema SQL + mutation_planning 的 DML（需要 `repository_base_digest`）；mutation_planning 依赖 storage_projection；`publish_canonicalization` 要求 replay SQL | §4.3、§4.8 |

### 2.3 既有清单映射

§2A.4 各行与 §2A.4.1 各项、以及 `tests/architecture_baseline.py` 的分组（`A<n>`/`N-*`），在 §9 映射到
具体修复与阶段。不能由 import 规则判定的问题（语义缺陷、编排复制、用例放置、UoW 枢纽）由本文及执行
计划的测试 owner 跟踪。

## 3. 目标结构

```text
table_access ─┐
composite_signal ─> snapshot_materialization（原始快照、Repository 规范快照、规范 schema/状态摘要、artifact）
table_rules ───────> storage_projection（规范投影：规范快照 + CanonicalizationManifest；import schema 渲染与打包）
storage_projection ─> mutation_planning（import DML）
table_rules（ComparisonRuleView） ─┐
snapshot_materialization ──────────┴─> comparison（规范对规范；DETAILED | DATASET_REPLACEMENT）
snapshot_materialization ─> project_identity（新）
comparison ─> risk_evaluation ─> surface_assembly ─> bundle_assembly
```

- 删除 `comparison_projection`、`business_projection` 占位与架构测试中对应的 owner、DAG 边；surface_assembly 的上游改为 comparison 与 risk_evaluation。
- 新增 `project_identity`，上游仅 `snapshot_materialization`。surface_assembly 不依赖 project_identity：身份标注使用 surface 自有的中性类型，由 Application 映射。
- `comparison` 上游改为 `table_rules` 与 `snapshot_materialization`。
- Submit import 包由 infrastructure 中的 publication adapter 组装，实现既有 `SubmitImportPublicationPort`，由组合根接线（符合 P5 §2A.2）。
- capability 公共面统一为包 facade（`__init__`）与 `contracts`；`contracts` 必须是 owner 内叶子，不得 lazy import 本 owner 的执行实现（关闭 A7）。架构测试的 capability DAG 规则同步放行上游 facade。
- Application 负责流程拓扑（FULL/MODIFIED_ONLY、pair 列表、History 视图）、执行模式选择、确认与事务；capability 不再出现流程词汇（DC5）。

## 4. W1 规范域比较与比较规则视图（ADR 0018）

### 4.1 规范快照与规范身份

规范快照（P）是在运行期规则集下、形态与 storage projection 输出一致的 `SnapshotTableSet`。它的 descriptor 等于 import schema：

| 项 | 规范定义 |
| --- | --- |
| 表集合 | storage projection 输出的存储表，不含 SKIP/OMIT 表 |
| 列集合 | retained columns（规范列名） |
| 列类型 | storage codec 的 SQL 类型，按 ADR 0017 与 Repository `normalize_sql_type` 的同一规范拼写 |
| 可空性 | 键列一律 NOT NULL；其余列沿用规范投影结果 |
| 主键与比较键 | 规范键，保持顺序 |
| ordered 表 | `gid INT UNSIGNED NOT NULL`（已分配伪 gid）；`no INT NOT NULL` 为结构列（Canonical Storage §3；E 中投影沿用源列的可空性，需修正）；ordered metadata 为 `CANONICAL_PSEUDO_GID` |
| 物理列序 | retained columns 的顺序（即 import DDL 顺序），不属于规范身份（DC13） |
| 单元格 | 按 codec 规范化：gid 为无符号整数，SET 为按标签顺序的 `SqlSetValue`，ENUM 为字符串，JSON 按 DC12 |

`canonical_binding`（P）分为两部分：

- 存储身份：`storage_projection_version` 与逐表存储规则事实。存储规则事实只含完全来自规则的字段：canonical key policy、`EXPLICIT` 策略下的显式键、ordered policy、structural 列与 dropped 列（含理由），均已记录在 manifest 的每表条目中（E：`CanonicalizationManifestTable`）。比较据此标记 schema 差异的来源（§4.5）。
  - 不计入：retained 列（源表的列减去 dropped 列）与 `DDL_PRIMARY_KEY` 策略下取自源表主键的 canonical key。二者虽也写入 manifest，但随源 schema 变化，属于 schema 而不是规则。
  - 存储身份也不用 schema 摘要表示，因为规范 schema 还取决于源 schema。
- 规则集 provenance：`ruleset_id`、`ruleset_version`、`ruleset_digest`。只用于记录，以及 AcceptSubmit 的陈旧判定（§5.3），不决定比较语义（DC10）。

规范快照有两个生产者：storage_projection 从原始快照投影（Preview 上传侧）；snapshot_materialization.repository_ref
从 Repository commit 读取（Preview 基线侧与 History 节点）。

业务 schema 摘要与规范状态摘要由 snapshot_materialization 契约拥有（P）：

- **business schema digest**（业务 schema 摘要，每表）：JCS{表名；按列名排序的列定义（列名、规范类型、可空性）；有序主键}。不含物理列序（DC13）。
- **canonical state digest**（规范状态摘要，每个快照）：JCS{按表名排序的每表（表名、business schema digest、行数、`raw_content_digest`）}。不含 `fast_row_digest`；`fast_row_digest` 只作快照内部诊断。
- `raw_content_digest` 沿用 E：按列名排序编码的行摘要多重集，与列序无关。

manifest 中的 `CanonicalizationManifestTable.canonical_schema_digest`（E，Canonical Storage §4）与 business schema digest 不是同一个值，也不可互换：

| | manifest `canonical_schema_digest`（E） | business schema digest（P） |
| --- | --- | --- |
| owner | Storage Projection | Snapshot Materialization |
| 列序 | 保持 DDL 列序，列序变化即改变 | 按列名排序，列序变化不改变 |
| 用途 | manifest 发布时的自洽核对、mutation planning 判断表 schema 是否变化，并计入 manifest digest；语义不变。Repository STRUCTURAL 不使用它：STRUCTURAL 比较的是包内 `manifest.json` 的列、主键与行数 | 规范状态摘要、比较提前退出、schema 事实 |
| commit 侧来源 | 长期保护的 manifest | 由 Repository 读取得到的 descriptor 计算，不从 manifest 取 |

两者都不进入 `canonical_binding`；manifest 字段也不进入规范状态摘要。

**规范快照同一性不变量**（P）：同一规范内容无论由哪个生产者得到，都满足：

1. descriptor 级相等：表集合相等；每表的列名集合、规范类型、可空性、有序主键相等；
2. 每表 business schema digest、行数与 `raw_content_digest` 相等，快照 canonical state digest 相等。

分歧在以下位置修正：

- 读取侧解码与投影侧编码不一致（如 SET）：在 snapshot_materialization 的编码 owner（`scalar_encoding`）修正；
- 存储会改写的信息（如 JSON 文本、可空主键、不能作主键的类型）：在 storage_projection 选择规范存储表示时解决（§4.2）；
- 不得在比较侧特判。

### 4.2 存储类型词表、存储约束与投影失败

当前词表（E，ADR 0017）与规范处置（P）：

| 源类型 | 规范存储与编码 | 同一性要点 |
| --- | --- | --- |
| CHAR、VARCHAR、TEXT 族 | STRING | Dolt 保留 CHAR 尾随空格（审核 E3） |
| ENUM | STRING，值须为声明的标签 | 两侧一致（审核 E2） |
| SET | 按标签顺序的 `SqlSetValue` | Repository 读取必须把 Arrow `list<string>` 解码为 `SqlSetValue`（§5.2） |
| JSON | DC12：真实数据中有则以 LONGTEXT 存原文，无则 fail-closed；触发时在 S2a handoff 中按 Canonical Storage §8 写明 storage projection version 的处理（DC27） | 不采用统一 JSON 表示，因为 Dolt 的规范化有损 |
| INT、BIGINT | SIGNED_INTEGER 32/64 | — |
| INT UNSIGNED | UNSIGNED_INTEGER 32（ordered gid 固定使用） | 规范 descriptor 取 codec 类型（审核 E2） |
| 其余类型 | 当前 fail-closed（`UNSUPPORTED_TABLE`）；DC15：普查发现存储表中有这些类型时，在 S2a 扩充 | 扩充须同时覆盖同一性、renderer 与真实 Dolt 往返 |

存储约束在投影阶段（即 Preview）检查（P），与 Dolt 行为一致：

- 规范键列不得是 TEXT、BLOB、JSON 等不能作主键的类型；键列在 import DDL 中一律 NOT NULL；
- ENUM/SET 标签合法；ordered 表的 gid/no 规则沿用 Canonical Storage §3；
- 无键、重复键、缺键按 Canonical Storage §3 fail closed。

投影失败的结果形态（DC14）：

- Preview 整体 FAILED，不做部分 Preview；
- typed 诊断一次列出全部失败的表与列。投影在单表失败后继续收集，现有实现遇到第一个失败即停止，需要调整；
- FULL 模式下 INITIAL 侧的投影失败同样使 Preview FAILED，诊断标明失败所在侧；
- 与 Business Lifecycle §2 的 required table 语义一致。

### 4.3 storage_projection 规范投影与 import 渲染入口

- `project_canonical_table_set(raw_table_set, ruleset) -> CanonicalProjectionResult`（P）：输出规范表（符合 §4.1 的 descriptor 与 reader）、`CanonicalizationManifest` 与全部诊断。复用 E 中的 `materialize_canonical_source_rows` 与 `derive_storage_rule_view`，不复制规则。
- `publish_canonicalization_manifest(manifest, store) -> ArtifactRef`（P）：只发布 manifest。E 的 `publish_canonicalization` 要求 replay SQL，Preview 阶段拿不到。
- 规范表由 Application 经 snapshot_materialization facade 的 `publish_snapshot_table_artifact` 持久化为 `SnapshotTableArtifact`。
- `render_import_schema_sql(import_input, removed_tables) -> bytes`（P，扩展 E 的 `render_repository_import_schema_replay_sql`）：对包内表 DROP/CREATE，对 `removed_tables` 只 DROP。表名一律经 renderer 的标识符引用规则输出，不拼接调用方提供的 SQL。
- import DML 仍由 mutation_planning 生成（E：`render_import_mutation_dml`，输入改为规范表行，不再二次投影原始快照）；打包沿用 E 的 `pack_repository_import_entries`。这三步在 Submit 的 publication adapter 中组合（§4.8）。

### 4.4 table_rules 比较规则视图与列处置

`TableRuleRecord` 增加 `compare_excluded_columns`（P）：保留在存储中，但不参与值比较。`ignored_columns` 维持 R4 与
Canonical Storage §2 的语义（`DROP_FROM_STORAGE`）。

规则集校验（P）：

- `ignored_columns` 与 `compare_excluded_columns` 不相交；
- 两者都不得包含规范键、ordered 身份列或结构列（Canonical Storage §2）。

现有规则调整（P）。ruleset digest 随之变化，DC6 下无兼容负担：

- 9 条 IEC104 ordered 规则去掉 `ignored_columns` 中的 `no`。`no` 作为结构列与 ordered 位置列，由 ordered 策略处理，不进入普通值比较（Canonical Storage §3）。
- `composite_signal_point` 的忽略列改为 `dev_addr`、`device_gid`、`point_payload_json`；`formula_ast_json`、`point_name` 移入 `compare_excluded_columns`，值比较只用 `formula_digest`（DC4）。

`ComparisonRuleView`（P，与 E 中的 `StorageRuleView` 对称）逐表给出：

```text
canonical_table
comparison_role: STANDARD | ORDERED | BROWSE_ONLY | SNAPSHOT_ONLY
artifact_scope: ALL_CHANGES | UPDATE_ONLY        # ordered 表固定为 ordered 语义
compare_excluded_columns: canonical tuple
ordered: position_column, stable_key_candidates, row_identity_key, blank_row_policy   # 仅 ORDERED
comparison_rule_digest
```

`ComparisonRuleSet`（P）由运行期规则集派生（DC10）。未匹配的表按 resolver 既有回退规则处理（E：`STANDARD_RAW_PK_FALLBACK`）。
ordered 参数从规则投影；IEC104 的 `gid/no` 默认值只在 table_rules 注册表中出现，不再出现在 comparison 契约默认值或 Application 中。

角色语义沿用 [R4 设计 §4.3](p3-r4-storage-projection-design.md)，并按 DC16 补充表级内容变化事实：

| 规则角色 | 规范快照 | 比较语义 |
| --- | --- | --- |
| SKIP | 不含该表 | 不比较 |
| SNAPSHOT_ONLY | 含该表 | 不产出记录；行数、`raw_content_digest` 或 business schema digest 不同时产出表级“内容已变化”事实 |
| BROWSE_ONLY | 含该表 | 表级存在性与两侧行数事实；行数、`raw_content_digest` 或 business schema digest 不同时产出表级“内容已变化”事实；不产出记录，不参与行级风险 |
| STANDARD_DIFF | 含该表 | 普通比较，`UPDATE_ONLY` 按表收窄产物 |
| ORDERED_DIFF | 含该表 | ordered 比较 |

schema 事实（§4.5）适用于所有存储角色：SNAPSHOT_ONLY/BROWSE_ONLY 表只改 schema 时，同时产出 schema 事实与表级内容事实。
表级内容事实使 pair 摘要与 surface 的变化计数显示为有变化；E 中 surface 的变化计数只统计非 UNCHANGED 的表，需要调整，
不能让该事实被过滤掉。

compare-excluded 列：值比较与 `MODIFIED` 判定都不使用这些列；新增和删除行的记录照常携带全部列。只有排除列变化时，
表状态保持 UNCHANGED，并产出与 DC16 同形的表级“内容已变化”事实。由于存储内容确实变了，§5.3 的判定会允许提交。

`SNAPSHOT_ONLY` 与 `BROWSE_ONLY` 的其余事实形态，以及修改行记录是否展示排除列的两侧值，在 S2a 按 legacy 行为 oracle 核对后冻结；`version_manager` 等表的浏览仍通过快照 artifact 提供。

### 4.5 comparison 消费方式

- 公共输入见 §6。comparison 按运行期 `ComparisonRuleView` 逐表决定角色、产物范围、排除列与 ordered 参数；`ComparisonTablePolicy` 降为 comparison 内部的派生类型，不再是调用方输入，也不再由 Application 编解码。
- 不再校验两侧的规则集 digest（删除 r1 的 `RULESET_BINDING_MISMATCH`，DC10）。
- vNext 比较不使用 native diff，始终按列名与有效键对齐，有效键取自运行期 `ComparisonRuleView`。因此无论两侧的 storage projection version 或 ruleset digest 是否相同，都满足 Canonical Storage §7 的 alignment 要求。
- schema 差异的来源按 Canonical Storage §7 标记，只依据两侧逐表存储规则事实（§4.1，规则侧字段）逐项归因：
  - 由规则事实的差异可以解释的差异，归 `STORAGE_PROJECTION_POLICY`：dropped 集合变化导致的列增删、key policy 或显式键变化导致的键变化、ordered policy 与 structural 列变化导致的 gid/no 变化，以及这些变化派生的差异（例如显式键变化使新旧键列的可空性随之改变，§4.2）；
  - 其余差异归 `SOURCE_SCHEMA`：源表增删列、类型、长度、可空性，以及 `DDL_PRIMARY_KEY` 策略下主键的变化；
  - 两类都有时为 `BOTH`；只有列序不同不产生 schema 差异（DC13）。
  - 两侧的规则事实总是可得：commit 侧取自 manifest，上传侧取自本次投影，INITIAL 没有表；无 manifest 的 commit 按 §5.1 不得进入比较。
- 无法安全对齐时（例如有效键变化且无法 fallback），该表为 DEGRADED，并给出原因诊断；pair 不因此失败。
- 提前退出条件改为：business schema digest、行数与 `raw_content_digest` 都相等。
- 两侧内容相同但 schema 不同时，产出明确的 schema 事实（类型、可空性、主键顺序的变化，或空表的列增删），不得显示为 UNCHANGED。列序不产生事实（DC13）。

### 4.6 Preview

受理（DC24）：Preview 受理时把运行期规则集 digest 冻结进 job payload，替代 E 中冻结的 `ruleset_version` 常量。每一步执行前比较
运行期 digest 与冻结值，不同即稳定失败（`PREVIEW_RULESET_VERSION_MISMATCH`），尚未开始 materialize 的 Preview 同样适用。

`materialize_inputs`：

1. 上传侧：staging → 业务物化（SQL 与可选的 `logics.xml`，§8）→ 原始 artifact → 规范投影（§4.3）→ 规范 artifact 与 manifest artifact；
2. 基线侧：从 BaselineHead 的 exact commit 读取规范快照（§5.2）；INITIAL 节点按 §5.1 处理；
3. 项目身份评估（§7.2）；
4. checkpoint 记录原始与规范 artifact ref、manifest ref、投影所用的规则集 digest（即受理时冻结的值）与身份评估结果。

`assemble_preview` 只比较规范快照。`publish_preview` 在 PreviewResult 中持久化（P）：

- MODIFIED 侧的规范表集合闭包：一个 JCS 闭包 artifact 的 ref 与 digest，逐表列出 `SnapshotTableArtifact` manifest ref；
- MODIFIED 侧 manifest 的 ref 与 digest；
- 上传 MODIFIED 侧与基线侧的 canonical state digest（§5.3）；
- 投影所用的规则集 digest（即受理时冻结的值，用于 §5.3 的陈旧判定）；
- 身份结论（§7.5）。

三步 JobDefinition 不变。Preview 不再展示被规则丢弃的列与 SKIP 表（DC1）；原始 SourcePackage 仍完整保留。

### 4.7 History

- 比较语义使用运行期规则集（DC10）；commit 规范元数据只提供存储身份与 provenance。
- accept 冻结运行期规则集 digest，替代 5E 的逐表 `table_policies` checkpoint 与 `table_ruleset_version`。恢复时运行期规则集 digest 与冻结值不同，则稳定失败，由用户重跑（DC11，沿用 E 的 `HISTORY_RULESET_VERSION_MISMATCH`）。
- 三节点比较的整份结果使用同一个运行期规则集。
- 受理指纹包含冻结的规则集 digest（E 中为版本常量）。激活后以同一幂等键重放返回 `409 IDEMPOTENCY_CONFLICT`，用户需以新的幂等键重跑；错误说明写明这一点。
- 删除 `_project_table_policy`、`_policy_to_checkpoint_dict`、`_table_policies_from_checkpoint`。

### 4.8 Submit

T1（AcceptSubmit）：

- Attempt 冻结 PreviewResult 中 MODIFIED 侧的规范表集合闭包与 manifest（ref 与 digest）。`canonicalization_manifest_ref/digest` 在 T1 即确定（E 中在 prepare 才生成）；这些字段进入请求 fingerprint。
- 保护责任按闭包精确转移：闭包中的规范表 artifact、manifest、source package 与 ready closure。删除 E 中按 artifact id 前缀过滤（`is_submit_snapshot_table_binding_candidate`）和按摘要挑选（`_snapshot_bindings_from_operation`）的启发式。
- 转移范围比 E 窄：E 在 T1 把 Preview 持有的全部 artifact 转给 Attempt；本设计只转移上述 Attempt 需要的 artifact。其余 Preview artifact 在 T1 随 `current-preview` 与 `preview-operation` 的保护一并解除（Canonical Storage §5：历史 Preview 引用不再 pin），此后按 P5 §9 的固定 TTL 做 best-effort 清理。T1 之后 submit job 只把 ready closure ref 作为绑定值核对，不读取其余 artifact。
- 受理的校验顺序与错误见 §5.3 与 §7.6。

prepare（P）：

- 读取冻结的规范表集合闭包与 manifest，不再重新投影原始快照。
- 经 Application 端口 `RepositoryParentCatalogPort` 读取冻结 expected parent（`repository_expected_commit_id`）的表目录。该端口由 infrastructure 实现，调用既有的 versioned catalog 读取接口。parent 中有、规范快照中没有的表进入 `removed_tables`（DC18：上传代表完整规范状态，包括用户删除的表和未归档 sibling Submission 在 main 上新增的表）。
- publication adapter 组合 `render_import_schema_sql`（含 `removed_tables`）、mutation_planning 的 DML 与打包，写出包 artifact；结果进入 prepare checkpoint，重试时复用同一个包；expected commit CAS 不变。
- 包根 `repository_import_artifact.py` 中的 `SubmitImportPublicationAdapter` 迁入 infrastructure（例如 `infrastructure/repository_write/import_publication.py`），实现既有 `SubmitImportPublicationPort`，由组合根接线（关闭 A6 中该项，符合 P5 §2A.2）。
- T1 冻结规范产物之后（含 PREPARED 与 prepare），Submit 不依赖运行期规则集；规则激活后恢复的 Attempt 按冻结产物继续执行（DC11、DC23）。

Preview 以业务基线比较：被删除的表显示 `DELETED_TABLE`，并按既有表删除风险规则提示。Repository wire、verification
policy 与 T1/T2/T3 的 evidence-first 恢复语义不变。

### 4.9 规则激活语义

本节集中定义规则集激活对各流程的影响（DC10、DC11），并与 Ruleset Activation §1、§5 及 Canonical Storage §7、§9 对照。
STORAGE_BREAKING 的 migration operation 属于未来工作（Ruleset Activation §4），本收口只规定比较侧的行为。

| 场景 | ADDITIVE / COMPARISON_BEHAVIORAL / RISK_ONLY | STORAGE_BREAKING |
| --- | --- | --- |
| 旧 commit 作为 Preview 基线或 History 节点 | 按运行期规则比较；存储规则事实一致，正常比较 | 受影响表按列名与有效键对齐，schema 差异来源标记为 `STORAGE_PROJECTION_POLICY`，不安全时表级 DEGRADED（Canonical Storage §7）；其余表正常比较 |
| 激活前完成、激活后受理的 Preview | AcceptSubmit 按 derived-stale 拒绝（`PREVIEW_DERIVED_STALE`），用户重跑 Preview | 同左 |
| 激活时尚未完成的 Preview/History operation 恢复（含受理后尚未开始执行、排队或已 checkpoint 的） | 稳定失败（`PREVIEW_RULESET_VERSION_MISMATCH`、`HISTORY_RULESET_VERSION_MISMATCH`），用户重跑；不静默改用运行期规则 | 同左 |
| 已受理的 Submit（T1 冻结规范产物之后，含 PREPARED） | 按冻结产物继续 | 按冻结产物继续；激活前置（例如不得存在未终结的 SubmitAttempt）由未来 migration 设计规定 |

激活须经 graceful drain 与重启（Ruleset Activation §2）。drain 期间 checkpoint 后交由 durable runtime 接管的 Preview/History，
以及排队尚未执行的，都会在重启后稳定失败；runbook 需写明这一用户影响。

Ruleset Activation §1、§5 的修订候选见附录 B.2（DC23）；Canonical Storage §7、§9 与本节一致，无需修订。

## 5. W2 commit 规范元数据与单遍读取（ADR 0019）

### 5.1 commit 规范元数据权威

- Submission commit：`Submission.canonicalization_manifest_ref/digest`。E 已持久化，finalize 时由 `canonicalization-manifest` owner 长期保护；manifest 含 `storage_projection_version`、规则集 id/version/digest、逐表存储规则事实与摘要。
- INITIAL BaselineNode（DC17）：恒为空提交，即零表规范状态，`canonical_binding` 取运行期规则集。物化时读取一次 catalog，断言没有用户表；不满足则稳定失败（`INITIAL_BASELINE_NOT_EMPTY`），用于防止误供给。不支持预置数据的初始库。误供给要到首个 Preview（或涉及 INITIAL 节点的 History）才暴露；INITIAL 节点不可修改，恢复方式是按 Business Lifecycle §1A.1 把 scope 改绑到新的 Repository，运维说明需写明。
- `CommitCanonicalMetadataPort`（P，由 control DB adapter 实现）：
  - 以 `(repository_id, commit_id)` 为键，只经该 Repository 的 Submission 与 BaselineNode 记录解析，并限定在 operation 冻结的 scope 内（实施必达）；
  - 返回取自 manifest 的存储身份与规则集 provenance（§4.1），或 INITIAL 标记；
  - 无法解析时稳定失败（`COMMIT_CANONICAL_METADATA_MISSING`）；
  - 读取 manifest artifact 时，digest 与 Submission 记录不符：稳定失败（`COMMIT_CANONICAL_METADATA_DIGEST_MISMATCH`），附诊断、结构化日志与指标，不创建持久 incident（DC25）；
  - 解码历史 manifest 时，`contract_version`、`storage_projection_version` 与 `ruleset_version` 只作 provenance，接受任何已发布的值；新写入的 manifest 仍按当前常量校验（读取与写入分开校验）。E 中 manifest 构造时把这三个版本固定为当前常量，需要调整。
- 未来的 `SYSTEM_MIGRATION` commit 必须同时登记 manifest，否则不得进入 Preview 或 History 比较（重开条件）。

### 5.2 Repository 规范快照单遍读取

- `RepositoryRefMaterializationRequest` 增加 `canonical_binding`，由 Application 按 §5.1 提供。
- provider 协议删除 `read_hidden_summary`；删除 `HiddenFinalSummary` 与 `HIDDEN_SUMMARY_*` 诊断码。
- 物化对每张表只读一次：同一遍内计算 descriptor 与摘要并写入 artifact；descriptor 由 catalog 构造（列名、规范类型、可空性、有序主键）。catalog 行数与实际读取行数不一致时返回普通 FAILED（`REPOSITORY_ROW_COUNT_MISMATCH`，DC19）。
- `snapshot_id` 由 `(repository_id, commit_id)` 确定性派生。
- 标量解码（必改）：SET 列按 catalog 中的标签，把 Arrow `list<string>` 解码为按标签顺序的 `SqlSetValue`；其余类型按 §4.2 的词表解码，与投影侧编码一致。
- HTTP Arrow adapter 只负责传输，按 record batch 交付，不计算摘要，不导入 capability 私有模块（关闭 A2 中 `http_arrow` 的两条）。Python 行对象只在 snapshot_materialization 中转换一次；Arrow 原生摘要计算作为 Phase 6 候选（§13）。

### 5.3 规范状态摘要与无规范变化判定

- 规范状态摘要 = 规范快照的 canonical state digest（§4.1），覆盖业务 schema、行数与内容，不含列序（DC13）。
- Preview 同时计算上传 MODIFIED 侧与基线侧的规范状态摘要，二者都持久化进 PreviewResult。
- AcceptSubmit 的陈旧判定（P）：Baseline 漂移（E）；或 PreviewResult 缺少规范状态摘要；或其投影所用规则集 digest 与运行期不同（DC11）。任一成立都返回 `PREVIEW_DERIVED_STALE`。
- 通过陈旧判定后，两侧规范状态摘要相等即 `NO_CANONICAL_CHANGE`，不再物化基线。只有列序不同的上传属于无规范变化，不产生 commit。
- `Submission.canonical_business_digest` 改为 MODIFIED 侧的规范状态摘要，取代 E 中由 Preview bundle digest 派生的值。
- 删除 `BaselineCanonicalDigestPort`、`compute_baseline_canonical_bundle_digest`、`http/runtime.py`（S1 后迁入 `bootstrap/composition.py`）中的 `HttpBaselineCanonicalDigestPort`，以及 `http/dependencies.py` 中的 `FailClosedBaselineCanonicalDigestPort`。

### 5.4 History 的规则集语义

History 受理与执行使用运行期规则集（DC10）。节点 commit 规范元数据中的规则集只作 provenance；比较按 §4.5 对齐，
并按两侧存储规则事实标记 schema 差异的来源。不再以 commit 元数据中的规则集判定失败；operation 内“受理时冻结”与
“执行时运行期”不一致时，按 DC11 稳定失败（§4.7）。

### 5.5 收缩 5E integrity incident

hidden summary 删除后，5E-S2 以 `HIDDEN_SUMMARY_*` 为生产者的 class (c) integrity incident 不再有生产者（DC9，取代
[5E 设计 §6.6](p5-5e-history-compare-design.md) 的相应部分）。删除范围（P）：

- History compare integrity 记录与受理阻断（`has_pending_integrity_for_commit` 等端口方法）；
- `POST /v1/history-compares/{operation_id}/integrity-ack` 路由与 `http/orchestration/history_integrity.py`，以及 `http/wiring.py` 的 `PRODUCTION_OPENAPI_PATHS` 中的对应路径；
- Operation 读取 DTO 中的 `integrity_incident` 字段（`http/routes/operations.py`、`http/schemas/operation.py`），以及 History DTO 中的对应字段；
- `application/history/compare_jobs.py` 中的 integrity 判定、二次物化与发布函数；`application/history/{contracts,errors}.py` 中的对应类型与错误（如 `HistoryIntegrityUnresolved`）；
- `application/history/compare.py` 中的受理阻断（`has_pending_integrity_for_commit` → `HistoryIntegrityUnresolved`）；
- `http/orchestration/history_compare.py`（或 S1 后承接其 DTO 映射的 HTTP 模块）中的 integrity DTO 读取与错误映射；
- 只为 incident 映射存在的 `MaterializationDiagnostic.expected_digest_ref/observed_digest_ref`；
- 以新 migration 删除 `history_compare_integrity_records` 表及其索引；
- 对应测试与测试支撑：
  - `test_history_compare_integrity.py`；
  - `test_history_compare_jobs.py`、`test_history_compare_transactions.py`、`test_history_http.py`、`test_operation_http.py`、`test_artifact_staging_conformance.py` 中的 integrity 用例；
  - `tests/support/repository_ref_materialization.py` 与 `tests/support/history_compare_job_harness.py` 中的 hidden summary 篡改钩子。

不在删除范围内：`application/history/errors.py` 的 `HistoryIntegrityFailure`。History projection/queries 用它表示历史事实与分页游标的
一致性，与 hidden summary incident 无关。删除时对被删符号做调用方扫描，按此区分。

读取不一致（DC19）：

- Repository 读取不一致（如 `REPOSITORY_ROW_COUNT_MISMATCH`）按依赖异常处理：普通 FAILED，附诊断、日志与指标，不创建持久 incident。
- ADR 0016 与 Operation Lifecycle §4 的 incident 范围限定为：Repository 返回值与 Backend 持有的期望值相矛盾，以及 CAS/结果歧义。Backend artifact store 的读回校验失败（如 manifest digest 不符）按稳定失败处理，不建 incident（DC25）。修订候选见附录 B.3。
- ADR 0016 的 Operation integrity（`operations/store.py` 的 `scan_active_integrity`、worker startup 扫描、control DB 完整性检查）不受影响。
- 该删除只在 5E slice exit 之后进行。

## 6. W3 comparison 公共面去流程化（ADR 0021）

公共输入（P）：

```text
ComparisonRequest(
  pair_id,                      # 调用方给出的不透明 id
  before: CanonicalSnapshotInput,
  current: CanonicalSnapshotInput,
  rule_set: ComparisonRuleSet,  # 运行期规则集（DC10）
  mode: DETAILED | DATASET_REPLACEMENT,
  options, contract_versions)
plan_comparison(request) -> ComparisonPlan | FailedResult
compare_plan(plan) -> DetailedFactsResult | DatasetReplacementResult | FailedResult | CancelledResult
publish_records_closure / open / restore / rewrite       # 记录闭包 API 保持
```

- 删除 comparison 契约中的 `PairViewKind`、`PairRole`、`InputCompleteness`、`IdentityApplicability`、`IdentityStatus`（移入 project_identity）、`ContinuationAction`、`BaselineReconstruction*`、`TrustedFlowApplicabilityBinding`、`UnverifiableContinuationBinding`、`IdentityGateBlockedResult`、`InitialSnapshotResult`，以及 `ProjectIdentityAssessment` 协议（移入 project_identity）。`domain/workspace` 中同名的上传模式枚举 `InputCompleteness` 属于 Workspace 领域，保留不变。
- 删除生产入口不可达的 `PythonReferenceBatchProvider`/`RustArrowBatchProvider` 公共导出（S1，随 A9 删除 `capabilities/comparison/provider.py`）；Phase 6 需要时由 owner 按实际热点重新设计（§2A.3“不预建 provider framework”）。
- 初始基线（恒为空，DC17）作为零表 `before` 传入，不再需要单侧视图。
- FULL 与 MODIFIED_ONLY 的 pair 拓扑、pair 标签与 History 视图全部由 Application 决定。
- surface 的身份标注改由 Application 在 `SurfaceAssemblyInput` 中提供，类型是 surface_assembly 自有的中性标注（状态与 assessment ref），不导入 project_identity。
- 本条撤销 §2A.2 中“R5 已接受的 pair/view/applicability 词汇保留”的约定（ADR 0021 接受后同步修订 §2A.2）。

## 7. W4 项目身份与数据替换（ADR 0020）

### 7.1 project_identity capability

- 规则 `version-manager-overlap/v1` 沿用旧设计：读取两侧规范快照的 `version_manager` 表，排除 `no` 列，其余列按规范名排序后规范化，比较完整条目。
  - 有交集为 `SAME_PROJECT`；双方都有可比条目但无交集为 `DIFFERENT_PROJECT`；
  - 缺表、空表、没有非 `no` 列、列集合不一致或读取失败为 `UNVERIFIABLE`；
  - 字符串不 trim、不折叠大小写，`NULL` 与空字符串不同。
- 输出 `ProjectIdentityAssessment`（schema/rule version、status、两侧快照摘要、计数、条目集合摘要、assessment digest），不包含原始行。
- 流程中立：不感知 Preview、pair 或确认。

### 7.2 适用范围（Application）

| 上传模式 | pair | 适用性 |
| --- | --- | --- |
| FULL | baseline → initial | before 为初始基线时 `NOT_APPLICABLE`，否则评估 |
| FULL | initial → modified | 评估 |
| MODIFIED_ONLY | baseline → modified | before 为初始基线时 `NOT_APPLICABLE`，否则评估 |

对初始基线评估必然得到 `UNVERIFIABLE`，这会让每个项目的首次提交都成为异常节点，因此显式规定为 `NOT_APPLICABLE`（DC7）。
DC17 保证初始基线恒为空，所以该规则不会漏检已有数据。History compare 不做身份评估（沿用 D）。

### 7.3 模式选择与 Preview 结果

- `DIFFERENT_PROJECT` → `DATASET_REPLACEMENT`；其余 → `DETAILED`。
- `UNVERIFIABLE` 额外附诊断 `PROJECT_IDENTITY_UNVERIFIABLE`。
- Preview 始终完成并 READY，不设暂停门（DC3）。
- 已判定为 `DIFFERENT_PROJECT` 的 pair，不因后续局部失败回退为详细比较（沿用旧设计）。

### 7.4 能力补齐

- comparison 的 `DATASET_REPLACEMENT` 按旧设计产出表级事实：双方都存在记为 `REPLACED`（deleted = before 行数，inserted = current 行数）；只一侧存在记为 `DELETED_TABLE`/`ADDED_TABLE`。不调用详细比较、records writer 或行级风险。
- risk 对替换 pair 产出比较级 `HIGH`，原因码 `PROJECT_IDENTITY_MISMATCH`、`DATASET_REPLACEMENT`；不产出表级或行级标注。
- surface 的替换展示与 replacement summary 已实现（E），需补测试。bundle 对替换 pair 的同名表导出两侧快照：Application 必须向 surface 传入两侧的 `table_artifacts`（E 中没有调用方传入），bundle 据此导出。

### 7.5 持久事实（A 类）

- `PreviewResult`：`identity_assessment_set_digest`，以及逐 pair 的 `(pair_id, applicability, status, mode, assessment_ref)`。
  `identity_assessment_set_digest` = JCS{schema: `project-identity-assessment-set/v1`；pairs: 按 pair 顺序排列的
  (pair_id, applicability, status, assessment_digest 或 null)}，包含 NOT_APPLICABLE 的 pair。
- `SubmitAttempt` / `Submission`：身份确认记录 `(action, assessment_set_digest, reason, actor_id, confirmed_at)`。actor 与时间只取自 session 与服务端时钟；Submission 在 finalize 时从 Attempt 复制，之后不可变。
- Archive：身份异常处置事件（§7.7）。

### 7.6 Submit 受理

`AcceptSubmitCommand` 增加 `identity_confirmations`（P），每项为 `{action, assessment_set_digest, reason}`。

输入边界（实施必达）：由 HTTP DTO 校验，违反时返回 `422 REQUEST_VALIDATION_FAILED`：

- 最多 2 项，每个 action 至多出现一次；action 只能是 `ACCEPT_DATASET_REPLACEMENT` 或 `ACCEPT_UNVERIFIABLE_DETAILED_RESULT`；
- `assessment_set_digest` 必须是合法的 digest 格式；
- `reason`：HTTP DTO 沿用 `BoundedDiagnosticReason`（1–4096 UTF-8 字节）；Submission 领域再按 Review 理由的标量规则校验，但允许多行（DC28）：放行 LF（U+000A）、CR（U+000D）与 TAB（U+0009），其余 C0/C1 控制字符、代理码点与非字符码点仍拒绝，并至少含一个非空白字符（E：`domain/submission/review.py` 的 `validate_review_reason` 现行拒绝全部控制字符）。S4 把这组规则提取为 Submission 领域的共享理由校验，由调用方显式选择是否放行上述三个字符：身份确认理由放行，Review 理由不放行，Review 行为不变；不从 Archive Application 导入校验函数。理由按原文持久化，不做换行规范化。

业务校验在 T1 写事务内，与 preview、baseline、占用校验一起执行，不产生额外的外部调用：

- Preview 含 `DIFFERENT_PROJECT` pair 时必须包含 `ACCEPT_DATASET_REPLACEMENT`；含 `UNVERIFIABLE` pair 时必须包含 `ACCEPT_UNVERIFIABLE_DETAILED_RESULT`。两者分别校验，不能互相替代；
- 缺少所需的确认 → `409 PROJECT_IDENTITY_CONFIRMATION_REQUIRED`；
- 提供了 Preview 不需要的确认，或 `assessment_set_digest` 与 current PreviewResult 不符 → `409 PROJECT_IDENTITY_CONFIRMATION_MISMATCH`。

判定顺序（P）：

1. 认证、当前权限与 exact scope，包括 workspace 的精确 scope 与 Repository 映射（E）；
2. same-key 重放（E）：只越过其后可漂移的新受理校验，不重新计算冻结字段；
3. workspace、revision、preview 绑定与 CAS；
4. baseline 绑定；
5. 陈旧判定（§5.3）；
6. `NO_CANONICAL_CHANGE`；
7. 身份确认；
8. 占用与 ready closure。

确认的请求内容（action、assessment_set_digest、reason）进入请求指纹；actor 与时间是服务端事实，不进入指纹，重放时也不重新取值。
same key 且 same fingerprint 的重放返回原结果；same key 但 fingerprint 不同返回 `409 IDEMPOTENCY_CONFLICT`（E）。

### 7.7 Review、Archive 与 History

- Review 读取面展示身份异常与确认记录（只读）。
- Archive 新增 `ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION`：
  - `PreviewArchivePlan` 对所选 Submission，若它带身份确认记录，则派生该异常；
  - subject digest 绑定 `submission_id`、candidate digest、preview bundle digest 与 assessment set digest；
  - 处置动作为 `ACKNOWLEDGE_IDENTITY_EXCEPTION`，reason 必填；
  - StartArchive 要求最新处置为肯定，沿用 `/v1/archive-anomaly-resolutions` 与 `anomaly_resolution_refs`。
- 既有 `ArchiveAnomalyResolutionEvent` 的 `sibling_submission_id`/`sibling_candidate_digest` 泛化为 `target_submission_id`/`target_candidate_digest`（DC6，无兼容）。
- History 节点派生 `identity_exception` 标记（只读投影，不新增持久事实）。

## 8. W5 composite_signal 接入

- Preview 上传侧改用 `materialize_business_snapshot`（E，P3-R3 已实现并测试）：SQL 加 `logics.xml`；缺失时按 D 使用稳定的 EMPTY 来源；XML 摘要或 EMPTY 标记进入快照身份（`snapshot_digest`）。规范状态摘要只覆盖派生表的内容，这与规范存储一致。
- `logics.xml` 存在但解析失败或违反 composite 业务不变量时，Preview FAILED 并附明确诊断（DC8，沿用 P3-R3）。这修订了 P5 §6.1 与 Business Lifecycle §2 中“XML 增强可降级”对 `logics.xml` 的适用，候选文本见附录 A 第 2 项与附录 B.5。
- 派生表键列类型（DC20）：`composite_signal_point.source_table` 由 `TEXT` 改为 `VARCHAR(64)`（MySQL 标识符长度上限，与 legacy 派生表一致），由派生表 schema owner（snapshot_materialization compose / composite_signal contract）修改，并校验来源表名的长度。storage_projection 在投影阶段拒绝不能作主键的键列类型（§4.2），因此不需要额外的键列类型改写机制。
- `composite_signal_point` 经规范投影进入存储、比较和风险，规则按 §4.4 变更。

## 9. W6 边界与结构修复

| 基线分组 / 问题 | 目标 | 阶段 |
| --- | --- | --- |
| A1 wire DTO 进入业务 port | `application/submission/ports.py` 只返回业务结果；Repository wire 编解码移入 `infrastructure/repository_write`；保持请求证据字节、实际发送与恢复语义一致 | S1 |
| A2 私有模块导入 | HTTP 上传受理移入 Application（例如 `application/workspace/upload_admission.py`），经 `source_package_staging` 公开的受限成员枚举入口实现；HTTP 只保留 DTO 映射与流式读取（HTTP 区不得导入 capability）。`http_arrow` 两条随 §5.2 关闭 | S1 / S2b |
| A3 事务→job 反向调用 | checkpoint 保护释放下沉到 submission 用例内的下层模块 | S1 |
| A5 nominal ref 倒挂 | Submission 领域持有自身的包引用值对象；`artifacts` 不导入 domain；转换函数移至 `application/submission` | S1 |
| A6 包根模块 | 删除重复的 `canonicalization_manifest.py`/`canonicalization_cells.py`；import 包媒体类型只由 storage_projection 契约定义，adapter 测试断言与 wire 常量一致；`repository_import_artifact.py` 的 adapter 按 §4.8 迁入 infrastructure；`compute.py`、`canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash`；import 规则精确放行 `capability:canonical_row_hash → ext:compute`（DC26 选定：ADR 0001 与 Contract Taxonomy §4.4 允许 capability facade 直接调用 PyO3 production provider；该 capability 只有 Rust 一个 production provider，不存在需要由 composition 选择的 provider，也就不按 P5 §2A.3 预建 provider 端口；放行只针对该 owner，不是整层或按文件名的豁免；`capabilities/canonical_row_hash/contracts.py` 仍保持叶子，不导入 compute，只 import contract 不加载 Rust 扩展），放行在同一 diff 中说明，`tests/support/import_rules.py` 与 `test_architecture.py` 的规则形态参数表同步修改；三个模块仍不可达，登记 Phase 6 延期（改名后的不可达条目在同一 diff 中给出理由）；`synthetic_w2.py` 移至 `tests/support` | S1 / S2b |
| A7 contracts 跳板 | 公共面改为 facade + contracts，contracts 为叶子；DAG 测试放行上游 facade | S1 |
| A8 绕过 facade | Application 只从 facade 或 contracts 导入 | S1 |
| A9 / N-dead 不可达代码 | 删除 `cache/comparison_core.py`、`capabilities/comparison/provider.py`、`capabilities/snapshot_materialization/cache.py`、两个占位 capability；`external_target_sync` 登记延期（真实外部目标出现时重开）；composite 与 XML 模块（含 `snapshot_materialization._catalog`）在 S3 变为可达；synthetic job 与 external effect 桩移出生产包和 worker 装配 | S1 / S3 / S5 |
| N-http-composition | 抽出 `bootstrap/composition.py`，由 HTTP 与 worker 共用；job registry 由 Application 构建，worker 不再导入 `http.runtime` | S1 |
| N-http-bypass | `http/history_reader.py` 移至 `infrastructure/control_db`；`http/dependencies.py` 的只读 store 改为经 bootstrap 注入的 adapter；设置常量由组合根注入；HTTP 不导入 capability 与 wire 类型 | S1 |
| N-infra-usecase | adapter 只依赖 Application 的 ports/contracts/errors；`compare_bindings` 编解码与 abort 码移入对应 contracts | S1 |
| N-operations-private | `operations.contracts` 提供公开校验函数 | S1 |
| Preview/History 受理用例在 HTTP | 移入 `application/workspace/preview.py` 与 `application/history/compare.py`；HTTP 只保留 DTO 映射与准入 | S1 |
| job 模块复制 | S1 抽出 Application 内共享的 step plumbing 与 pair 流水线骨架，不改 checkpoint 载荷；Snapshot/Summary 编解码并入 snapshot_materialization contracts 放在 S2a（两份 `_summary_payload` 已分叉，合并会改变 checkpoint 载荷） | S1 / S2a |
| UoW 枢纽 | 按 owner 拆分：共享的最小控制事务协议由 Application 平台模块持有，workspace、submission、archive、history 各自声明所需 port；组合在 bootstrap/infrastructure 完成 | S1 |
| 运行时环（N-cycles） | 各自在 owner 内解除 | S1 |

S1 只做结构修复、不改行为：golden、业务 digest、checkpoint 载荷、HTTP DTO 与 compose 旅程结果保持不变，作为后续语义变更的回归基准。
模块改名导致的基线条目替换，须在同一 diff 中给出理由。

**S1 修订登记（2026-10-10）**：`tests/architecture_baseline.py` 的起始基线为 3 条 import 违例、0 个运行时环、14 个不可达模块，条内注释标明关闭阶段。此前 10 项来自包级 facade 可达性扩展；按实际导入的 wrapper 符号展开后，4 个仅由不可达 `compose.py` 调用的 composite 模块应计入不可达项。Owner 批准将测量基线由 10 更正为 14，理由、工具语义与 S3 归属见 [S0 owner decisions](p5-arch-closure-s0-owner-decisions.md) §10；这只更正测量，不放宽后续只减不增要求。
`external_target_sync` 三模块按上表 A9 登记外部目标延期（决议见 [S0 owner decisions](p5-arch-closure-s0-owner-decisions.md) §9）。
迁入 `capabilities/canonical_row_hash/` 后的 `compute` / IPC / `contracts` 无生产消费者，登记 **Phase 6** 延期（DC26 选项 3）。

## 10. 持久化、HTTP 与部署影响

- control DB 新增前向 migration，不做数据回填；新增列允许旧行为空（DC6）：
  - PreviewResult：MODIFIED 侧规范表集合闭包 ref/digest、manifest ref/digest、两侧规范状态摘要、投影规则集 digest、身份结论；
  - SubmitAttempt：规范表集合闭包与 manifest 在 T1 冻结；身份确认记录。Submission：身份确认记录（finalize 时复制）；
  - History compare acceptance：冻结运行期规则集 digest（替代 `table_ruleset_version`）；
  - archive 事件字段 `sibling_*` 改名为 `target_*`，并增加 subject kind；
  - 删除 `history_compare_integrity_records` 表与索引。
- HTTP：
  - Preview 结果读取增加身份结论、规范变化标记与表级“内容已变化”事实；
  - Submit 受理请求增加 `identity_confirmations`（§7.6 的 422 与两个 409）；陈旧判定沿用 `PREVIEW_DERIVED_STALE`；
  - Archive 异常处置接受新的 subject kind；
  - 删除 integrity-ack 路由、`PRODUCTION_OPENAPI_PATHS` 中的对应路径，以及 Operation/History DTO 的 `integrity_incident` 字段；
  - OpenAPI 测试随之更新；
  - 新增 operation 失败码：`PREVIEW_RULESET_VERSION_MISMATCH`、`INITIAL_BASELINE_NOT_EMPTY`、`COMMIT_CANONICAL_METADATA_MISSING`、`COMMIT_CANONICAL_METADATA_DIGEST_MISMATCH`、`REPOSITORY_ROW_COUNT_MISMATCH`。
- Repository 访问：prepare 新增一次对冻结 expected parent 的只读 catalog 读取（既有接口，无 wire 变化）。
- artifact 保留：规范表 artifact、规范表集合闭包与 manifest，与原始 `SnapshotTableArtifact` 同等 pin，并在 T1 按闭包转移给 Attempt（P5 §9 规则不变）；其余 Preview artifact 不转给 Attempt，在 T1 解除保护，按 P5 §9 的固定 TTL 做 best-effort 清理（§4.8，Canonical Storage §5）；finalize 后 manifest 由 `canonicalization-manifest` owner 长期保护（E）。
- 镜像与 Compose：
  - Dockerfile、依赖、entrypoint 与 Compose 均不变；
  - compose harness 在 S2b 改为不预导入基线数据（DC17）；
  - 各语义阶段的 compose 旅程需要更新并重跑，按执行计划 §6 在阶段末重建 current HEAD 镜像；
  - 真实数据旅程从主机侧经公开 HTTP 接口运行，不把数据目录挂载进容器（DC22）。

## 11. 语义 owner 与需修订的文档

| 语义 | Owner | 需修订 |
| --- | --- | --- |
| 规范快照、规范 schema/状态摘要、Repository 单遍物化、标量解码 | Snapshot Materialization | P3-R3 设计 hidden summary 条款（由 ADR 0019 取代） |
| 规范投影、manifest、import schema 渲染与打包、存储类型词表与存储约束 | Storage Projection | Canonical Storage §2、§4（附录 B.1）；Contract Taxonomy §4.4、§4.6、§5、§13（附录 B.4） |
| import DML | Mutation Planning | — |
| Submit import 包组装与发布 | Submission Application（port）+ infrastructure adapter | P5 §2A.4 “包根 … Submit adapter”一项的处置（附录 B.5） |
| `ComparisonRuleView`、列处置 | Table Rules | P3-R4 设计 §4.2 只加“由 ADR 0018 取代（列处置）”标注，不改写正文；新规则由 ADR 0018 与 Canonical Storage §2（附录 B.1）承载 |
| comparison 输入、替换模式、Canonical Storage §7 对齐 | Comparison | P3-R5 设计 identity gate 与流程词汇相关条款；P5 §2A.2（附录 B.5） |
| 规则激活语义 | Table Rules / Risk Rules Policy + 各 Application | Ruleset Activation §1、§5（附录 B.2） |
| 项目身份评估 | Project Identity（新） | Contract Taxonomy（附录 B.4） |
| Preview/Submit/Archive 身份确认与持久事实 | 对应 Application | Business Lifecycle 3.1.0（附录 A） |
| History integrity 收缩、读取不一致处置 | History Application | 5E 设计 §6.6 标注取代；ADR 0016 / Operation Lifecycle §4（附录 B.3） |
| 目标 DAG | Backend Architecture | Architecture §7.1/§7.2/§9.1/§10/§13（附录 B.6）；`tests/test_architecture.py` owner 集合与 DAG |

接受时点：附录 A、附录 B 的候选文本已于 2026-09-27 随 S0 文档接受并入（Entry Brief §5）；P3 与 5E 的设计文档同时加了
“由 ADR 00xx 取代”的标注，不改写历史正文。

## 12. 测试归属

| 不变量 | 唯一 owner（P） |
| --- | --- |
| 规范快照同一性（descriptor 级与 schema/内容摘要；两条生产路径；真实 Dolt 往返） | `test_canonical_snapshot_identity.py`（integration：经 `tests/support/submit_job_harness.py` 启动的真实 Repository Service 导入规范快照，再经 HTTP Arrow 读回；覆盖 NULL、ENUM、SET、CHAR、JSON（按 DC12）、INT/BIGINT/INT UNSIGNED、伪 gid；S3 起加入 `composite_signal_point`） |
| 标量编码与 SET 解码规则 | `test_snapshot_materialization_contracts.py`（unit，共享参数表） |
| 规范状态身份覆盖业务 schema、排除列序；提前退出与 schema 事实 | `test_canonical_state_identity.py`（unit，共享参数表：空表增列、类型、长度、可空性、键序、列序；列序互换时同一行断言 business schema digest 不变、manifest `canonical_schema_digest` 改变；manifest 摘要的发布自洽核对与 mutation planning 用法仍由既有 storage_projection 与 mutation_planning 测试证明） |
| 同内容的原始上传与规范基线 → 全表 UNCHANGED | `test_comparison_canonical_domain.py` |
| `ComparisonRuleView` 派生与列处置校验（含 ordered `no`） | `test_table_rules_comparison_view.py`（共享参数表） |
| 角色语义（BROWSE_ONLY/SNAPSHOT_ONLY/UPDATE_ONLY/ordered；表级内容变化事实，含各存储角色只改 schema 的情形；compare-excluded） | `test_comparison_rule_roles.py` |
| 表级内容已变化事实在 Preview/Review 的变化计数中可见 | `test_surface_assembly.py` |
| 按列名与有效键对齐，并按两侧规则侧存储事实标记 schema 差异来源（Canonical Storage §7） | `test_comparison_planning.py`（共享参数表：同一规则下源表增列、改 DDL 主键 → `SOURCE_SCHEMA`；规则改变 dropped 列或显式键 → `STORAGE_PROJECTION_POLICY`，含显式键变化派生的键列可空性变化；两者同时发生 → `BOTH`；只有列序不同 → 无 schema 事实） |
| 投影失败形态与存储约束（一次列出全部失败；不可作键的类型；键列 NOT NULL） | `test_storage_projection_core.py` |
| Repository 单遍物化与行数不一致失败 | `test_repository_ref_materialization_protocol.py` |
| ADDITIVE 激活后旧基线仍可 Preview | `test_preview_job_materialize.py` |
| 激活前完成的 Preview 在激活后受理被拒 | `test_submit_transactions.py` |
| Preview/History 在激活后恢复时稳定失败（Preview 含受理后、materialize 前发生激活的情形） | `test_preview_job_worker.py`、`test_history_compare_jobs.py`（各自入口） |
| `NO_CANONICAL_CHANGE` 由规范状态摘要判定 | `test_submit_transactions.py`（收敛现有 5 个文件中的相关断言） |
| T1 按闭包冻结与保护转移；删除启发式 | `test_submit_artifact_protection.py` |
| prepare 按 expected parent 删表（用户删表；业务基线 ≠ main 时 sibling 新增表与删除表），经真实 Repository 的回放与 STRUCTURAL 校验 | `test_submit_prepare_removed_tables.py`（integration，新增模块；`test_submit_job_prepare.py` 为模块级 unit，不放 integration 用例） |
| prepare 包 checkpoint 复用 | `test_submit_job_prepare.py`（unit） |
| `CommitCanonicalMetadataPort` 的键与 scope、manifest digest 校验、历史版本 manifest 的解码 | `test_commit_canonical_metadata.py`（unit，新增；共享参数表：其他 Repository 的同名 commit、未登记的 commit、冻结 scope 之外的 Submission、INITIAL 标记、manifest digest 不符、历史版本的 manifest） |
| INITIAL 恒为空的断言 | `test_preview_job_materialize.py` |
| 身份规则 v1 | `test_project_identity.py` |
| 替换事实、比较级风险 | `test_comparison_replacement.py`、`test_risk_contracts.py` |
| 身份确认的输入边界与业务校验 | `test_submit_transactions.py`（业务校验与判定顺序）、`test_submit_http.py`（422 输入边界与 409 错误码映射的参数表） |
| Submission 共享理由校验（多行放行与 Review 单行两种模式） | `test_review_domain.py`（共享参数表：LF/CR/TAB 在身份确认模式下通过、在 Review 模式下拒绝；其他控制字符、代理码点、非字符码点、纯空白与超长在两种模式下都拒绝） |
| 授权与 exact scope 先于 same-key 重放；重放越过可漂移的业务前置 | `test_submit_transactions.py`（既有 T1 重放用例：scope 映射失效时拒绝、只有 head 漂移时返回原结果；S4 补充撤权后重放被拒） |
| Archive 身份异常处置 | `test_archive_transactions.py` |
| composite 业务物化、键列类型与规则 | `test_snapshot_materialization_business.py`（capability）、`test_preview_job_materialize.py`（Preview 接入）、`test_storage_projection_core.py`（规则） |
| control DB migration | `test_workspace_control_db_migrations.py`、`test_submit_control_db_migrations.py`、`test_archive_control_db_migrations.py`（按表归属） |
| import 边界 | `test_architecture.py` + `tests/architecture_baseline.py` |
| 端到端 | 既有 compose 旅程扩展：重复提交同内容得到 `NO_CANONICAL_CHANGE`；规则表在非空基线上的 Preview；用户删表与 sibling 新增表后提交；仅改 `logics.xml`；跨项目上传→确认→审核→处置→归档，另加 `UNVERIFIABLE` 与 FULL 混合模式 |
| 真实数据 | 4 份代表性 dump 的 Preview → Submit → History 链路（主机侧脚本，结果写入 handoff，不进入普通 CI；DC22） |

同构错误使用模块级参数表；纯规则与解析测试不引入 Dolt（AGENTS）。

## 13. 性能输入（§2A.3、§2A.5 第 3 项）

S5 选择 FULL 上传（非空基线）→ Submit → History compare 这条链路，使用 DC22 的大数据档与同一项目的前后版本记录端到端耗时，
并拆分为 Repository I/O（含 prepare 读取 expected parent catalog 时附带的每表行数统计）、Arrow→Python 转换、规范投影、摘要计算、比较、artifact 读写几部分，形成 Phase 6 候选
（预期包括 Arrow 原生行摘要与 canonical row hash Rust 路径）。遵守
[Performance Measurement Guidance](../contracts/performance-measurement-and-baseline.md)：不设通过阈值，不建设新的 benchmark 平台；
dataset ID、SHA-256 与 raw samples 按[决议记录 §4](p5-arch-closure-s0-owner-decisions.md#4-真实数据存放建议)记录。

## 14. 停止条件与开放项

出现以下情况时，停止对应阶段并回到 owner 处理：

1. 真实 Dolt 同一性测试对 §4.2 词表内的类型失败，且无法在编码 owner 或存储表示的选择中修正，只能在比较侧特判；
2. S1 kickoff 普查发现的词表外类型无法无损往返 Dolt，DC15 的扩充无法满足同一性；
3. legacy oracle 显示 BROWSE_ONLY/SNAPSHOT_ONLY 的比较形态与 R4 §4.3 冲突；
4. 需要 Preview 暂停确认或改判“不同项目”（重开 ADR 0020），或需要在比较中使用非运行期规则（重开 DC10）；
5. 出现需要兼容旧数据的真实部署（重开 DC6），或需要预置数据的初始库（重开 DC17）；
6. 身份确认需要 Review 阶段的独立交互（本设计只做只读展示）；
7. 生产环境出现新的协议族或软件版本（DC22 的重开条件：重跑普查与相关验收）。

r1 的停止条件“Dolt 拒绝 `TEXT` 主键”已由 DC20 决定，不再是停止条件。

## 附录 A：Business Lifecycle 3.1.0 补充候选

以下候选文本已于 2026-09-27 并入 [Business Lifecycle](../contracts/business-lifecycle-and-state.md)，版本升至 3.1.0；保留于此作为并入依据，现行规则以 Contract 正文为准。

附录 A、B 都是编辑指令：引文用于定位，原文跨行或含 code span 处以原词为准；并入时把被修订的旧断言与新增限定合并为一条有效规则，不保留互相矛盾的两句。

1. §1A.2：在第一段末句（“…不得靠 Archive 创建 commit 或猜测 main 来补归属。”）之后另起一段：
   - 初始 BaselineNode 引用的 commit 必须是没有用户表的空提交，即零表规范状态；物化时断言，不满足即稳定失败。不支持预置数据的初始库，种子数据一律经 Submit 进入（DC17）。
2. §2：
   - PreviewResult 的不可变绑定增加：MODIFIED 侧规范表集合闭包与 CanonicalizationManifest 引用；上传 MODIFIED 侧与基线侧的规范状态摘要；投影所用规则集 digest；身份评估集摘要与逐 pair 的身份结论和执行模式。
   - 比较在规范域进行，比较语义使用运行期规则集：被规则丢弃的列与 SKIP 表不属于比较对象；只存不比的表以表级事实呈现内容变化；列序不属于规范业务状态。
   - 规范投影失败（不支持的类型、键或表）使整个 Preview 失败，并一次列出全部失败项。
   - “可选table/XML/ordered/risk增强失败可发布READY及bounded diagnostics” 中的 XML 不包括 `/comps/logic/logics.xml`，并增加：`/comps/logic/logics.xml` 存在时是必需输入，解析失败或违反 composite 业务不变量使 Preview 失败；缺失时使用稳定的 EMPTY 来源。其他可选增强的降级规则不变。
3. §3：
   - “canonical business digest” 定义为规范状态摘要，由列序无关的业务 schema、行数与内容组成；业务 schema 不是 CanonicalizationManifest 中按 DDL 列序计算的每表 schema digest。`NO_CANONICAL_CHANGE` 指 PreviewResult 中两侧的规范状态摘要相等。
   - Preview 的基线漂移，或其投影所用规则集与运行期不同，都使 PreviewResult derived-stale，AcceptSubmit 拒绝。
   - Preview 含 `DIFFERENT_PROJECT` 或 `UNVERIFIABLE` pair 时，AcceptSubmit 必须携带对应的、彼此独立的身份确认；确认记录随 Attempt 冻结，并复制到 Submission，不可变。
   - Attempt 在 T1 冻结 PreviewResult 的规范表集合与 CanonicalizationManifest。Submit 写入的内容就是上传的完整规范状态，expected parent 中多出的表在新 commit 中删除。
4. §4：Review 只读展示身份确认记录。
5. §5：AnomalyResolution 增加身份异常 subject；带身份确认记录的 Submission 被选为归档对象时，必须有带理由的肯定处置。
6. §6：History 比较使用运行期规则集；节点的 commit 规范元数据提供存储身份与 provenance。比较始终按列名与有效键对齐（Canonical Storage §7），schema 差异的来源只依据两侧规则侧的存储事实标记。

## 附录 B：其他上游修订候选

以下候选已于 2026-09-27 并入对应文档；保留于此作为并入依据，现行规则以各文档正文为准。

### B.1 Canonical Storage and Repository Boundary §2、§4（3.0.0 → 3.1.0）

- §2 把 “Comparison projection 在比较时负责跨版本 alignment、selected value columns、ordered semantics 和 records。二者来自相同 table-rules source，但具有不同 contract、DTO、version 和 cache identity” 改为：

  > 比较在规范域进行：两侧都是规范快照（storage projection 输出或 Repository commit 读取）。比较语义由 table_rules 的 `ComparisonRuleView` 提供、由 comparison 消费，使用运行期规则集。`StorageRuleView` 与 `ComparisonRuleView` 来自同一 table-rules source，各有独立的 digest。比较不使用 native diff，始终按列名与有效键对齐（§7）。

- §2 在 “被标记为 ignored 的列不得同时作为 effective key、ordered identity 或其他 required structural column…” 一段之后增加：

  > `compare_excluded_columns` 表示保留在存储中（`PERSIST_BUSINESS`）、但不参与值比较的列，不得与 `ignored_columns`、有效键、ordered identity 或结构列重叠。ordered 表的位置列（如 `no`）是 `RETAIN_FOR_STRUCTURE` 列，由 ordered 语义处理，不得列入 `ignored_columns`。

- §4 在 “每表 schema digest 的 canonical payload 必须包含…Arrow 物理类型不进入 schema digest。” 一段之后增加：

  > 该每表 schema digest 保持 DDL 列序，用于 manifest 发布时的自洽核对与 mutation planning 的 schema 变化判断，并计入 manifest digest；Repository STRUCTURAL 比较的是包内 `manifest.json` 的列、主键与行数，不使用它。比较、规范状态摘要与 `NO_CANONICAL_CHANGE` 使用 Snapshot Materialization 拥有、与列序无关的 business schema digest（ADR 0018），二者不可互换。

- 版本：
  - Semantic version 由 `3.0.0` 升至 `3.1.0`；
  - CanonicalizationManifest 的 `contract_version` 记录其遵循的本 Contract 版本：S2a 起新写入的 manifest 记录 `3.1.0`，读取时按 ADR 0019 接受历史版本；manifest 载荷结构与 `canonicalization_manifest_digest` 算法不变；
  - storage projection version 不变。若 S1 kickoff 普查触发 DC12（JSON 改以 LONGTEXT 存储），按 §8 在 S2a handoff 中写明是否提升（DC27）。
- §7、§9 与 DC10 一致，不修改。

### B.2 Ruleset Activation and Migration §1、§5

- §1 在 “已运行 operation 在启动时捕获 ruleset snapshot，运行期间不受后续 activation 影响。” 之后增加：

  > 激活须经 §2 的 drain 与重启，同一进程生命周期内的运行期 ruleset 就是启动时捕获的 ruleset。跨越激活的只有恢复的 operation，上一句在恢复场景下按以下规则理解：纯计算 operation（Preview、History compare）在受理时冻结 ruleset digest，恢复时运行期 ruleset 与冻结值不同则稳定失败，由用户重跑，不得静默改用新规则；Submit 在 T1 冻结规范产物之后（含 PREPARED）只使用冻结产物，不依赖运行期 ruleset。

- §1 第二段 “Table ruleset snapshot 可以作为 protected hidden metadata table 随正式 canonical commit 原子保存…” 末尾增加：“当前不采用：commit 的 ruleset provenance 由 Backend 持有的 CanonicalizationManifest 记录（ADR 0019）。”

- §5 末句 “已捕获旧 snapshot 的 operation 继续使用原规则。” 改为：

  > 已捕获旧 snapshot 的 operation 按 §1 处理：带外部 effect 的 operation 按冻结产物继续；纯计算 operation 在恢复时，若运行期 ruleset 与冻结值不同则稳定失败，由用户重跑，相同则照常继续。本节“不增加 mismatch 分支”指 commit 记录的历史 ruleset 与运行期不同，不构成失败理由；operation 冻结值与运行期不同时的恢复失败按 §1 处理，不属于此类。

### B.3 ADR 0016 与 Operation Lifecycle and Repository Integrity §3、§4

- [ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md) 的 “Repository/content readback mismatch、CAS ambiguity 等权威事实问题创建 durable `RepositoryIntegrityIncident`” 不改写正文；在状态行下增加 “incident 适用范围由 ADR 0019 澄清” 的标注。
- [Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md) §4 在字段清单代码块之后、“incident 通过 stable operation/user code…”一段之前增加一段：

  > 权威事实问题指：Repository 返回值与 Backend 持有的期望值相矛盾（例如 T3 回显的 manifest digest、expected parent 或 commit），或 CAS/结果歧义。以下情形不创建 incident，按普通稳定失败处理，附诊断、结构化日志与指标：未与 Backend 期望值比较的 Repository 读取不一致（如 catalog 行数与读取行数不一致）；Backend artifact store 的读回校验失败（如 manifest artifact 的 digest 与 Submission 记录不符）。

- §3 的 “repository content/readback mismatch：先处理 integrity incident” 按 §4 的上述范围理解，不另行修改。

### B.4 Contract Taxonomy and Ownership §4.4、§4.6、§5、§13

- §4.4 “允许的主依赖方向” 代码块替换为：

  ```text
  table_access/table_rules -> snapshot
  snapshot + table_rules（StorageRuleView） -> storage_projection -> RepositoryImportArtifact
  storage_projection -> mutation_planning（import DML）
  snapshot + table_rules（ComparisonRuleView） -> comparison -> risk -> surface -> bundle
  snapshot -> project_identity
  ```

- §4.6 artifact 内容 owner 表删除 “Comparison projection table | Comparison Projection capability” 一行。
- §5：
  - 删除 “Comparison `ProjectionSchema`、projection digest | Comparison Projection capability” 行；
  - 删除 “Hidden SnapshotSummary table schema/content” 与 “Hidden table 的普通版本化存储” 两行；
  - 新增 “`ComparisonRuleView`、比较列处置 | Table Rules capability | Comparison”；
  - 新增 “`ProjectIdentityAssessment` | Project Identity capability | Workspace Application、Surface（经 Application 映射）”；
  - “Storage column policy/key/ordered identity、`CanonicalizationManifest`” 行的主要消费者增加 “Preview、History（commit 规范元数据）”；
  - “`SnapshotTableArtifact` full-row facts/schema” 行的主要消费者 “Storage/Comparison Projection” 改为 “Storage Projection、Comparison”；
  - Cache 两行保留：S1 删除的 `cache/comparison_core.py` 是不可达实现，不改变缓存的归属约定。
- §13 第 9 项是 Phase 1A 的历史决策，不改写，末尾加标注：“comparison projection 部分由 ADR 0018 取代：比较使用 table_rules 的 `ComparisonRuleView`，不再有 comparison projection artifact 或 owner。”

### B.5 P5 设计

- §2A.2 “流程编排归 Application” 一条中，把 “R5 已接受的 pair/view/applicability 词汇保留；5D/5E 若需要增加流程分支，先判断是否可在 Application 映射为已有模式，不能只因新增流程就扩大 comparison 的业务分支。” 替换为：

  > comparison 公共面按 ADR 0021 只接收两侧规范快照、规则集、执行模式与选项，不含 pair/view/applicability 等流程词汇；新增流程分支先在 Application 映射为已有执行模式，不能只因新增流程就扩大 comparison 的业务分支。

  其后的 “确需改变语义时由原 contract owner 决定。” 保留。
- §6.1：“可选table/XML/ordered/risk增强可以以bounded diagnostics降级” 中的 XML 不再包括 `/comps/logic/logics.xml`（DC8）。
- §2A.4 “包根 … Submit adapter” 一行的处置列替换为：

  > 按职责拆分归位：adapter 迁入 infrastructure，实现 `SubmitImportPublicationPort`；import 包媒体类型只由 storage_projection 契约定义；canonical bytes、manifest/package 版本与 digest 如因 ADR 0018、0019 改变，一次性更新，不保留兼容（DC6）；删除无消费者入口，避免只搬目录或让 capability 反向依赖 Application。

### B.6 Architecture and Refactoring Plan

- §7.1 主依赖链代码块替换为：

  ```text
  table_access + parser
      -> snapshot_materialization -> SnapshotTableArtifact（原始快照与 Repository 规范快照）
                                        |
  table_rules --------------------------+-> storage_projection（规范投影、manifest、import schema）
                                        |      -> mutation_planning（import DML）
                                        |      -> RepositoryImportArtifact
                                        |      -> Repository Client
                                        |
                                        +-> comparison（ComparisonRuleView + 规范快照）
                                        |      -> risk_evaluation
                                        |      -> surface_assembly
                                        |      -> bundle_assembly
                                        |      -> upload_preview_bundle
                                        |
                                        +-> project_identity（只依赖 snapshot_materialization）
  ```

- §7.2 第 2 项替换为：

  > 2. `table_rules` 的 `ComparisonRuleView`
  >    - 逐表给出比较角色、产物范围、compare-excluded 列与 ordered 参数；
  >    - 与 storage projection 的 `StorageRuleView` 来自同一 table-rules 语义源，各有独立 digest，不共享未区分职责的 DTO；
  >    - 跨版本 schema alignment 与有效比较键由 comparison 按运行期规则执行（ADR 0018）。

- §9.1 “ruleset、storage/comparison projection、CanonicalizationManifest、SnapshotSummary、Comparison 和 Risk 语义” 改为 “ruleset、storage projection 与比较规则视图、CanonicalizationManifest、SnapshotSummary、Comparison 和 Risk 语义”。
- §10 建议目标目录：删除 `comparison_projection/` 与 `business_projection/`，增加 `project_identity/`。
- §13 “storage/comparison projection 分离” 改为 “storage 与 comparison 规则视图分离”。

P3-R3（hidden summary 条款）、P3-R4 §4.2（`compare_excluded_columns` 与 ordered `no`）、P3-R5（identity gate 与流程词汇）与
5E §6.6 在同一时点加“由 ADR 0018/0019/0021 取代”的标注，不改写历史正文。
