# P5 架构收口 S0 r2 修订处置表

- 状态：**修订者自查完成；待独立复审**。本表不是复审结论。
- 日期：2026-09-26
- 修订者：S0 独立审核者，应 repository owner 要求执行本次修订。修订者与审核者为同一人，因此复审须由既未参与起草、
  也未参与修订的 reviewer 承担。
- 输入：
  - [S0 独立审核报告](p5-arch-closure-s0-independent-docs-review.md)（F1–F11、N1–N6；含 2026-09-26 复核补充）；
  - [S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md)（DC10–DC22）；
  - r1 文档 @ `3e5d5807e5`。
- 被修订文档：[Entry Brief](p5-arch-closure-s0-entry-brief.md)、[详细设计](p5-arch-closure-design.md)、
  [执行计划](p5-arch-closure-execution-plan.md)、ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、[0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)、[P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925)、
  [formal README](../README.md)。

```yaml
record_kind: p5_arch_closure_s0_revision_disposition
revision: r2
revised_at: 2026-09-26
r1_commit: 3e5d5807e5
review_report_commit: 89668aaf56
owner_decisions_commit: 3f3b1de192
code_inspection_base: 2172369803
vnext_changed: no
accepted_contract_bodies_changed: no      # 上游修订只以候选文本给出（设计附录 A、B）
adr_status_changed: no                    # 0018–0021 保持 Proposed
implementation_authorized: no
independent_rereview: pending
```

## 1. 修订边界

- 只改文档。源码、测试、配置与已接受的 Contract 正文未改动；ADR 保持 Proposed。
- 审核报告与决议记录是历史记录，本次不改写。它们引用的设计章节号是 r1 的编号，对照见 §5。
- r2 没有重跑审核实验。E 级事实沿用审核在 `2172369803` 上的核查；r2 只补做了源码路径、标识符与测试文件存在性检查（§6）。

## 2. Findings 处置

“状态”一栏是修订者的自评，由复审确认。“待验证”指文档已给出定义与验收，需在所列阶段以测试或数据证明。

| ID | 处置 | 主要改动位置 | 状态 |
| --- | --- | --- | --- |
| F1 规则集绑定冲突 | 采用 DC10：比较语义使用运行期规则集，删除 `RULESET_BINDING_MISMATCH`；存储身份不同按 Canonical Storage §7 对齐。采用 DC11：激活前完成的 Preview 在受理时按 derived-stale 拒绝；已受理的 Preview/History 恢复时稳定失败；Submit 在 T1 后只用冻结产物。新增“激活类别 × 场景”对照表。运行期规则不需要规则集全序与历史规则集持久化，因此审核 §7.2 的“全序、可取回、回滚、三节点”四项定义不再需要单独规定：回滚后同样按运行期规则比较，三节点 History 整份结果使用同一运行期规则集 | 设计 §1（DC10、DC11）、§4.1（`canonical_binding` 拆为存储身份与 provenance）、§4.5、§4.7、§4.9、§5.3、§5.4、§12；附录 A 第 3、6 项；附录 B.2；ADR 0018 Decision 3 与 Alternatives；ADR 0019 Decision 5、6；执行计划 S2a 第 6 项、S2b | 文档已处置；S2a/S2b 待验证（§12 的三个测试 owner） |
| F2 规范快照同一性 | 规范 descriptor 定义为 import schema（retained columns、codec 规范类型、键列 NOT NULL、伪 gid 为 `INT UNSIGNED`）；列序不属于身份（DC13）；给出类型词表与各类型的同一性要点；SET 解码列为必改；JSON 按 DC12；可空键列在投影阶段处理；修正位置限定为编码 owner 或存储表示；新增真实 Dolt 往返的 integration owner | 设计 §2.2（E-a–E-d）、§4.1、§4.2、§5.2、§12；ADR 0018 Decision 1、6 与 Required Verification；执行计划 S2a（integration owner 为 S2b 门槛） | 文档已处置；S2a 待验证 |
| F3 Submit 复用规范投影 | import schema 渲染归 storage_projection（`render_import_schema_sql(import_input, removed_tables)`），DML 仍归 mutation_planning，打包沿用 `pack_repository_import_entries`，三者在 infrastructure publication adapter 中组合并实现既有 `SubmitImportPublicationPort`；新增只发布 manifest 的入口；PreviewResult 持久化规范表集合闭包与 manifest，Attempt 在 T1 冻结并纳入指纹；按闭包转移保护，删除两处启发式；prepare 经 `RepositoryParentCatalogPort` 读取冻结 expected parent，得出 `removed_tables`（DC18）；包进入 checkpoint，CAS 不变；撤回 Preview blocker 备选 | 设计 §3、§4.3、§4.6、§4.8、§9 A6 行、§10、§12；附录 A 第 3 项；附录 B.5；ADR 0018 Decision 2；执行计划 S2b | 文档已处置；S2b 待验证（删表三种情形的 integration） |
| F4 上游 Contract 修订 | 附录 A 修订（新增 §1A.2 的 INITIAL 条款；§2 的 `logics.xml` 条款引用原文；§3 的规范状态摘要与陈旧判定；§6 的运行期规则集）。新增附录 B：Canonical Storage §2（3.1.0）、Ruleset Activation §1、ADR 0016 与 Operation Lifecycle §3/§4、Contract Taxonomy §5、P5 §2A.2/§6.1/§2A.4、Architecture §7.1/§7.2/§10/§13；P3-R3/R4/R5 与 5E §6.6 加取代标注。接受时点定为 S0 复审通过（不再排在实现之后） | 设计附录 A、附录 B、§11；Entry Brief §5；执行计划 S0；ADR 0019 关联阶段与 Decision 7 | 文档已处置；候选文本能否直接并入由复审确认 |
| F5 列处置与 ordered `no` | 9 条 ordered 规则去掉 `ignored_columns` 中的 `no`（`no` 为 `RETAIN_FOR_STRUCTURE`，由 ordered 语义处理）；校验规则：`ignored_columns` 与 `compare_excluded_columns` 不相交，且都不含键、ordered 身份列与结构列。实施时一并删除 table_rules 校验中对 ordered `no` 的例外分支 | 设计 §2.2（E-g）、§4.4；附录 B.1；ADR 0018 Decision 4；Entry Brief §2 规则集一行 | 文档已处置；S2a 待验证 |
| F6 composite `TEXT` 主键 | 采用 DC20：`source_table` 改为 `VARCHAR(64)`，由派生表 schema owner 修改并校验长度；storage_projection 在投影阶段拒绝不可作键的类型；删除该停止条件；S3 以真实 Dolt 导入验证 | 设计 §4.2、§8、§14；ADR 0018 Decision 6；执行计划 S3；Entry Brief §2 | 文档已处置；S3 待验证 |
| F7 Preview 提前失败范围 | 列出类型词表与失败类别；投影失败形态按 DC14（整体 FAILED、一次列出全部、INITIAL 侧同样处理）；S1 kickoff 做真实数据普查并按结果落定 DC12、DC15；S2b 验收要求 4 份 dump 完成 Preview → Submit → History（在 S2 语义验收前关闭 F7） | 设计 §4.2、§12、§13；执行计划 S1 kickoff 第 4、5 项、S2b 验收；ADR 0018 Decision 6 | 文档已处置；普查（S1 kickoff）与真实数据运行（S2b）待完成 |
| F8 只存不比的表不可见 | 采用 DC16：SNAPSHOT_ONLY/BROWSE_ONLY 表内容变化产出表级“内容已变化”事实，不含记录、不参与行级风险；只有 compare-excluded 列变化时同样处理；事实形态在 S2a 按 legacy oracle 核对后冻结 | 设计 §4.4、§12；附录 A 第 2 项；ADR 0018 Decision 5；执行计划 S2a 验收 | 文档已处置；S2a 冻结 |
| F9 初始基线语义 | 采用 DC17：初始基线恒为空提交；物化时断言 catalog 无用户表（`INITIAL_BASELINE_NOT_EMPTY`）；DC7 的 `NOT_APPLICABLE` 因此不会漏检；comparison 以零表 `before` 传入；compose harness 在 S2b 改为不预导入 | 设计 §5.1、§6、§7.2、§10、§12；附录 A 第 1 项；ADR 0019 Decision 2；ADR 0020 Decision 2；ADR 0021 Decision 3；执行计划 S2b 第 7 项与 compose 验收 | 文档已处置；S2b 待验证 |
| F10 执行计划 | A2 改为把上传受理移入 Application；S1 验收更正为可由 `import_rules` 核对（`http_arrow` 两条、A6 `repository_import_artifact`、改名后的 canonical row hash 条目需同 diff 理由、composite 在 S3、`external_target_sync` 延期、运行时环为空）；Snapshot/Summary 编解码合并移到 S2a；S2 拆分，路径预算逐阶段列出，不用整层通配；补齐审核列出的生产与测试路径；DC9 删除清单补全（DTO 字段、OpenAPI 路径、诊断字段、篡改钩子） | 设计 §5.5、§9；执行计划 §2（S1、S2a、S2b）、§3、§4、§6 | 文档已处置；各阶段 handoff 按预算核对 |
| F11 schema 盲区 | 定义 canonical schema digest（按列名排序的列名、规范类型、可空性，加有序主键）与 canonical state digest（每表 schema digest、行数、`raw_content_digest`，不含 `fast_row_digest`）；列序按 DC13 排除；提前退出要求 schema digest 相等，内容相同但 schema 不同时产出 schema 事实；`NO_CANONICAL_CHANGE` 改用规范状态摘要；History 的同类现有缺陷随同一比较修复关闭 | 设计 §2.2（E-e）、§4.1、§4.5、§5.3、§12；附录 A 第 3 项；ADR 0018 Decision 1 与 Required Verification；ADR 0019 Decision 5 | 文档已处置；S2a 待验证（共享参数表） |

## 3. 非阻塞建议处置

| ID | 处置 | 主要改动位置 |
| --- | --- | --- |
| N1 | 输入边界（最多 2 项、action 唯一且在枚举内、digest 格式、理由去空白后 1–1000 字符 → 422 `REQUEST_VALIDATION_FAILED`）；缺失 → 409 `…_REQUIRED`；多余或摘要不符 → 409 `…_MISMATCH`；判定顺序；`assessment_set_digest` 的组成（按 pair 顺序，含 `NOT_APPLICABLE`）；“投影侧与 Repository 侧生成相同 assessment”；FULL 混合模式旅程；不采用 side-local 业务 projection 与 R5 §5.1 的 server-side policy allowance | 设计 §7.5、§7.6、§12；ADR 0020 Decision 5、8；执行计划 S4 |
| N2 | surface 使用自有的中性身份标注类型，由 Application 映射，不新增 surface → project_identity 边；Application 向 surface 传入两侧 `table_artifacts` | 设计 §3、§6、§7.4；ADR 0020 Decision 3、7；ADR 0021 Decision 3 |
| N3 | `CommitCanonicalMetadataPort` 以 `(repository_id, commit_id)` 为键，只经该 Repository 的记录并在冻结 scope 内解析；规则集身份取自受长期保护的 manifest artifact，读取时校验 digest | 设计 §5.1；ADR 0019 Decision 1 |
| N4 | 只有 compare-excluded 列变化时表状态为 UNCHANGED，并产出表级“内容已变化”事实；新增与删除行的记录携带全部列 | 设计 §4.4 |
| N5 | R3 改为“AcceptSubmit 预检中执行，写事务复用预检结果”；R4 改为“按 record batch 逐列 `to_pylist()`”；规范表发布改用 facade 导出的 `publish_snapshot_table_artifact` | 设计 §2.1、§4.3 |
| N6 | S2 拆分为 S2a、S2b（DC21）；migration 测试 owner 按表归属；前向 migration 的新增列允许旧行为空，旧行按“不可用”处理，开发与测试环境在 S2b 前重建 | 设计 §1 兼容性、§10、§12；执行计划 §1、§2 |

## 4. Owner 决议落点

| 决议 | 落点 |
| --- | --- |
| DC10 运行期规则集 | 设计 §1、§4.1、§4.4、§4.5、§4.7、§4.9、§5.4、§6；ADR 0018 Decision 3；ADR 0019 Decision 6；ADR 0021 Decision 1 |
| DC11 激活前后的 operation | 设计 §4.7、§4.8、§4.9、§5.3；附录 A 第 3 项；附录 B.2；ADR 0019 Decision 5、6 |
| DC12 JSON（条件） | 设计 §4.2；执行计划 S1 kickoff 第 5 项、S2a 第 3 项；ADR 0018 Decision 6 |
| DC13 列序 | 设计 §4.1、§4.5、§5.3；附录 A 第 2、3 项；ADR 0018 Decision 1；ADR 0019 Decision 5 |
| DC14 投影失败形态 | 设计 §4.2；附录 A 第 2 项；ADR 0018 Decision 2 |
| DC15 类型词表扩充（条件） | 设计 §4.2、§14 第 2 项；执行计划 S1 kickoff 第 5 项、S2a 第 3 项；ADR 0018 Decision 6。决议记录写作“S2 内”，拆分后落在 S2a |
| DC16 只存不比的可见性 | 设计 §4.4；附录 A 第 2 项；ADR 0018 Decision 5 |
| DC17 初始基线为空 | 设计 §5.1、§6、§7.2；附录 A 第 1 项；ADR 0019 Decision 2；ADR 0020 Decision 2；ADR 0021 Decision 3 |
| DC18 完整规范状态与删表 | 设计 §4.8；附录 A 第 3 项；ADR 0018 Decision 2 |
| DC19 读取不一致 | 设计 §5.2、§5.5；附录 B.3；ADR 0019 Decision 3、7 |
| DC20 composite 键列类型 | 设计 §4.2、§8；ADR 0018 Decision 6；执行计划 S3 |
| DC21 S2 拆分 | 执行计划 §1、§2、§3、§6 |
| DC22 真实数据 | 设计 §12、§13、§14 第 7 项；执行计划 S1 kickoff 第 4 项、S2b/S3/S4/S5 验收；Entry Brief §3 |

审核报告 §6 的实施前置条件落点：第 1 项 → 执行计划 S1 kickoff；第 2 项 → Entry Brief §5 与执行计划 S0；第 3 项 → 执行计划
S1 kickoff 第 4、5 项；第 4 项 → 执行计划 S2a、S2b 验收；第 5 项 → 执行计划 S3 验收；第 6 项 → 执行计划 §6；第 7 项 → 决议记录
已对 D1–D15 全部作出决议。审核报告 §7.8 的推进顺序 → 执行计划 §1 与 S5。

## 5. 设计章节号对照（r1 → r2）

审核报告与决议记录引用的是 r1 章节号。

| r1 | r2 |
| --- | --- |
| §2.1 本轮新确认的语义缺陷 | §2.1（R1、R3、R4 的表述按审核更正） |
| — | §2.2 独立审核补充确认的事实（新增） |
| §2.2 既有清单映射 | §2.3 |
| §4.1 规范快照 | §4.1 规范快照与规范身份 |
| — | §4.2 存储类型词表、存储约束与投影失败（新增） |
| §4.2 storage_projection 规范快照输出 | §4.3 |
| §4.3 table_rules 比较规则视图与列处置 | §4.4 |
| §4.4 comparison 消费方式 | §4.5 |
| §4.5 Preview | §4.6 |
| §4.6 History | §4.7 |
| §4.7 Submit | §4.8 |
| — | §4.9 规则激活语义（新增） |
| §5.3 无规范变化判定 | §5.3 规范状态摘要与无规范变化判定 |
| §5.4 History 规则集校验 | §5.4 History 的规则集语义 |
| 附录 A 第 1–5 项 | 附录 A 第 2–6 项（新增第 1 项：§1A.2） |
| — | 附录 B（新增） |

执行计划：S2 拆为 S2a、S2b；新增 S1 kickoff 普查；§3 路径预算改为逐阶段列表。

## 6. 修订者自查

- `git diff --stat 2172369803 HEAD -- vnext` 为空。
- 被修订文档与本表的全部相对链接与锚点可解析。
- 反引号中的源码路径：现存路径在 worktree 中存在；不存在的只有执行计划标注为“新增”或“迁移后”的文件，以及设计中的提案名。
- 反引号中的标识符：E 级名称都能在源码中找到；找不到的都是本设计提案的新名称（P）。
- 设计 §12 与执行计划引用的测试文件：除标注为新增的 8 个文件外均存在。

以上是修订者自查，不替代独立复审。

## 7. 复审输入与关注点

- 复审对象：本分支包含 r2 的固定 commit（由复审者记录）；代码事实基线 `2172369803`。
- 建议顺序：本表 → Entry Brief → 设计 → 执行计划 → ADR 0018–0021 → 附录 A、B 对照上游原文。
- 重点关注：
  - 本表中每一项是否真正关闭，改动是否传播到所有相关位置；
  - 修订者即原审核者，复审宜独立重判 F1–F11 的关闭标准，不以本表的自评为准；
  - 执行计划 §3 中的新增文件名是建议名，复审可判断 owner 与边界是否合适；
  - S2a 结束时 R1 仍存在的中间状态是否可接受；
  - 附录 B 的候选文本是否准确引用上游原文、能否直接并入。
