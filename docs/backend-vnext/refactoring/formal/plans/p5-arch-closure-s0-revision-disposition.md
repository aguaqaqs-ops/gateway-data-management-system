# P5 架构收口 S0 修订处置表

- 状态：r2、r3 各经两份独立复审（r2：均为定向修订；r3：通过与定向修订）；**r4 修订者自查完成，待核对 r4 差异**（r3 见 §8，r4 见 §9）。本表不是复审结论。
- 日期：2026-09-26（r2、r3）；2026-09-27（r4）
- 修订者：S0 独立审核者，应 repository owner 要求执行 r2–r4 修订。修订者与审核者为同一人，因此复审须由既未参与起草、
  也未参与相应修订的 reviewer 承担。
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
revision: r4                              # §1–§7 为 r2 的历史记录，§8 为 r3，§9 为 r4
revised_at: 2026-09-26
r1_commit: 3e5d5807e5
r2_commit: 5858eaaa08
r2_rereview_commits: [34ff1827cf, ca6502d8a4]
r3_commit: ffba1138ef
r3_rereview_commits: [783acefe94, 46a4e03ae5]
review_report_commit: 89668aaf56
owner_decisions_commits: [3f3b1de192, f984381ab3]
code_inspection_base: 2172369803
vnext_changed: no
accepted_contract_bodies_changed: no      # 上游修订只以候选文本给出（设计附录 A、B）
adr_status_changed: no                    # 0018–0021 保持 Proposed
implementation_authorized: no
diff_check_of_r4: pending
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

## 8. r3 处置（两份 r2 复审与 DC23–DC27）

本节记录 r3 的处置。§1–§7 是 r2 的历史记录，保持原样。

### 8.1 输入与修订边界

- 输入：
  - [r2 独立复审（第一份）](p5-arch-closure-s0-independent-rereview.md) @ `34ff1827cf`，以下编号前缀 RV1；
  - [r2 独立复审（第二份）](p5-arch-closure-s0-independent-rereview-2.md) @ `ca6502d8a4`，以下编号前缀 RV2；
  - [S0 Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) §7 的 DC23–DC27 @ `f984381ab3`：由第二份复审者记录，owner 确认后单独提交。
- 两份复审的结论均为定向修订。阻塞项的判定有差异（RV1 列 2 项，RV2 列 6 项），r3 对两份报告的全部阻塞项与非阻塞建议一并处置，
  不因另一份报告判为非阻塞而跳过。
- 只改文档：源码、测试、配置与已接受的 Contract 正文未改动；ADR 保持 Proposed。复审报告与决议记录不改写。
- r3 修订者与 r2 修订者是同一人。r3 的复审须由未参与 r3 修订的 reviewer 承担，可只核对 r3 差异（`f984381ab3` 之后）。

### 8.2 阻塞项处置

| 编号 | 问题 | 处置 | 改动位置 |
| --- | --- | --- | --- |
| RV1-F1、RV2-F1 | 受理判定顺序把 same-key 重放放在权限与 scope 之前，与现行实现相反 | 改为：认证、当前权限与 exact scope（含 workspace 的精确 scope 与 Repository 映射）→ same-key 重放 → 其余受理校验；重放只越过其后可漂移的校验，不越过授权；确认的请求内容进入指纹，actor 与时间不进入。测试 owner：`test_submit_transactions.py` 的既有 T1 重放用例，S4 补撤权后重放被拒 | 设计 §7.6、§12；ADR 0020 Context、Decision 5、Required Verification；执行计划 S4 |
| RV1-F2（RV2-N2 同源） | 新的列序无关 schema 摘要与 manifest 中保持 DDL 列序的同名摘要关系未定义；以 schema 摘要表示存储身份不可行 | 新摘要改名 business schema digest，由 Snapshot Materialization 拥有；manifest `canonical_schema_digest` 语义不变，两者不可互换，设计给出对照表，两者都不进入 `canonical_binding`。存储身份改用 manifest 每表已记录的存储规则事实。比较始终按列名与有效键对齐，schema 差异来源按规则事实标记 `SOURCE_SCHEMA`/`STORAGE_PROJECTION_POLICY`/`BOTH`。附录 B.1 为 Canonical Storage §4 增加区分说明 | 设计 §4.1、§4.5、§4.9、§5.1、§5.3、§5.4、§12、附录 A 第 3、6 项、附录 B.1；ADR 0018 Context、Decision 1、3、Alternatives、Required Verification；ADR 0019 Decision 1、5、6；执行计划 S2a |
| RV2-F2（RV1-F3 前半同源） | 附录 B.2 未覆盖 Ruleset §5 末句；Submit 的边界用词不一致；Preview 捕获规则集的时点未定义 | DC23：B.2 同时修订 Ruleset §1 与 §5 末句，写明 §1 首句在恢复场景下的含义，澄清 §5“不增加 mismatch 分支”的范围。Submit 边界统一为“T1 冻结规范产物之后（含 PREPARED）”。DC24：Preview 受理时把规则集 digest 冻结进 job payload，每步执行前比较，不同即 `PREVIEW_RULESET_VERSION_MISMATCH` | 设计 §1、§4.6、§4.8、§4.9、§12、附录 B.2；ADR 0019 Decision 6、Consequences、Required Verification；执行计划 S2a 第 6 项与验收 |
| RV2-F3（RV1-F5 同源） | N3 的键与 scope 没有唯一测试 owner 与阶段验收；manifest digest 不符的处置未定义 | 新增唯一 owner `test_commit_canonical_metadata.py`（unit，共享参数表），列入 S2b 验收与测试预算。DC25：digest 不符按 `COMMIT_CANONICAL_METADATA_DIGEST_MISMATCH` 稳定失败，附诊断、日志与指标，不建 incident；附录 B.3 按 DC25 写明 incident 范围 | 设计 §5.1、§5.5、§10、§12、附录 B.3；ADR 0019 Decision 1、7、Alternatives、Required Verification；执行计划 S2b |
| RV2-F4 | `compute.py` 迁入 capability 后新增 layer 违例，S1 验收无法机械兑现 | DC26 由 Backend Architecture 选定选项 1：import 规则精确放行 `capability:canonical_row_hash → ext:compute`。依据是 ADR 0001 与 Contract Taxonomy §4.4：capability facade 可直接调用 PyO3 production provider；该 capability 只有一个 production provider，不存在需由 composition 选择的 provider，不按 P5 §2A.3 预建 provider 端口。放行只针对该 owner。`import_rules.py`、`IMPORT_RULE_SHAPES` 与 `test_architecture.py` 的旧路径列入 S1 | 设计 §1、§9 A6 行；执行计划 S1 验收与 §3 S1 |
| RV2-F5（RV1-F4 同源） | S2a/S2b 路径预算遗漏被删机制的使用方 | S2a 增补：两个 compose 模块、`compose_gate_harness.py`（History oracle）、`test_architecture.py`（comparison 上游）、`http_workspace_harness.py`、`http_shutdown_harness.py`、`application/workspace/preview.py`、`http/orchestration/history_compare.py`（或 S1 后的承接模块）、`test_preview_job_worker.py`、`test_preview_application.py`。S2b 增补：`application/history/compare.py`、`http/orchestration/history_compare.py`（或 S1 后的承接模块）、两个新测试文件与 4 个条件测试文件。设计写明保留 `HistoryIntegrityFailure` | 执行计划 S2a、S2b 内容与 §3；设计 §5.5 |
| RV2-F6 第 1–4 点（RV1-F3 后半同源） | 附录 A、B 不能按字面并入 | B.4 增补 Contract Taxonomy §4.4 依赖图替换、§4.6 删行、§13 第 9 项取代标注。附录 A 第 1 项与 B.3 改为整句、整段后的插入点。B.5、B.6 给出替换文本：P5 §2A.2 的替换句与保留的后半句；Architecture §7.1 新依赖图、§7.2 第 2 项、§9.1。设计 §11、ADR 0018 与附录 B 对 P3-R4 §4.2 统一为只加取代标注。附录 A 开头说明引文是编辑指令 | 设计附录 A、附录 B、§11；ADR 0018 Consequences；Entry Brief §5；执行计划 S0 |

### 8.3 非阻塞项与附带意见

| 编号 | 问题 | 处置 | 改动位置 |
| --- | --- | --- | --- |
| RV2-F6 第 5 点、DC27 | B.1 未说明 manifest `contract_version`；DC12 触发时的版本轴 | B.1 写明：S2a 起新写入的 manifest 记录 `3.1.0`，读取接受历史版本，载荷与 digest 算法不变；DC12 触发时在 S2a handoff 中按 Canonical Storage §8 写明 storage projection version 的处理 | 设计 §4.2、附录 B.1；ADR 0018 Decision 6；执行计划 S2a 第 3 项 |
| RV2-N1 | 只存不比的表与 schema 事实的交叉 | 角色表的触发条件加入 business schema digest；schema 事实适用于所有存储角色；内容事实计入 pair 摘要与 surface 变化计数；owner：`test_comparison_rule_roles.py`（含只改 schema）、`test_surface_assembly.py`（可见） | 设计 §4.4、§12；ADR 0018 Decision 5、Required Verification；执行计划 S2a |
| RV2-N3 | 历史 manifest 的解码被当前版本常量锁定 | 读取与写入分开校验：历史版本只作 provenance；`test_commit_canonical_metadata.py` 覆盖 | 设计 §5.1、附录 B.1；ADR 0019 Decision 1；执行计划 S2a 第 3 项 |
| RV2-N4 | 删表 integration owner 位于模块级 unit 文件 | 新增 integration 模块 `test_submit_prepare_removed_tables.py`；`test_submit_job_prepare.py` 保留 unit 的包 checkpoint 复用 | 设计 §12；执行计划 S2b |
| RV2-N5 | 表述精度与小缺口 | ADR 0019 Decision 5 改为“取代 E 中由 Preview bundle digest 派生的值”；ordered `no` 定为 `INT NOT NULL`（现行投影需修正）；身份确认理由与 Archive 同一校验（1–4096 UTF-8 字节，按原文持久化）；激活的用户影响面写入 §4.9，并要求 runbook 说明 | 设计 §4.1、§4.9、§5.3、§7.6；ADR 0019 Decision 5；ADR 0020 Decision 5；执行计划 S2a、S4 |
| RV1 §4 | 设计 E-e 概括过宽；P5 §2A.4.1 的 R1 表述过宽 | E-e 区分空表增列（比较显示 SCHEMA_CHANGED）；P5 §2A.4.1 的 R1 行改为与设计 R1 一致 | 设计 §2.2；P5 §2A.4.1 |
| RV1 §6 | `HistoryIntegrityFailure` 不在删除范围；DROP 表名须经标识符引用 | 设计 §5.5 写明保留并要求按调用方扫描区分；§4.3 写明 renderer 的标识符引用规则 | 设计 §4.3、§5.5 |
| RV2 §6 | 保护转移范围变窄；History 同 key 重放返回 409；INITIAL 误供给的恢复；S2a compose 预期；worker 集成测试注入；catalog 行数开销；Architecture §9.1 | 依次写入设计 §4.8、§4.7、§5.1；执行计划 S2a 验收、S1 验收；设计 §13；附录 B.6 | 同左 |

### 8.4 DC23–DC27 落点

| 决议 | 落点 |
| --- | --- |
| DC23 Ruleset §5 随 B.2 修订 | 附录 B.2（§1、§5）；设计 §4.9 末段；ADR 0019 Consequences |
| DC24 Preview 受理时冻结规则集 digest | 设计 §4.6、§4.9、§12；ADR 0019 Decision 6；执行计划 S2a 第 6 项与验收；失败码 `PREVIEW_RULESET_VERSION_MISMATCH`（设计 §10） |
| DC25 manifest digest 不符按稳定失败处理 | 设计 §5.1、§5.5、§10；附录 B.3；ADR 0019 Decision 1、7；`test_commit_canonical_metadata.py` |
| DC26 canonical row hash 的 Rust 绑定放置 | 设计 §9 A6 行（选项 1）；执行计划 S1 验收与 §3 S1 |
| DC27 DC12 触发时的版本轴 | 设计 §4.2 JSON 行、附录 B.1；ADR 0018 Decision 6；执行计划 S2a 第 3 项 |

### 8.5 修订者新发现并处理的问题

- P5 §2A.4“包根 … Submit adapter”一行要求“保持 canonical bytes、manifest/package 版本和 digest 兼容”，与 DC6 冲突。附录 B.5 给出
  替换后的处置列：这些值如因 ADR 0018、0019 改变，一次性更新，不保留兼容。
- Ruleset Activation §1 允许把 ruleset snapshot 作为 hidden metadata table 随 commit 保存，与 DC2 的方向不一致（原文是“可以”，不构成
  冲突）。附录 B.2 为该句加“当前不采用”的说明。
- 执行计划 S2a 预算补上 `http/orchestration/history_compare.py`（或 S1 后的承接模块）：复核被删符号的使用方时发现它仍向 History 受理
  传入 `table_ruleset_version`。

### 8.6 修订者自查

- `git diff --stat 2172369803 HEAD -- vnext` 为空。
- 被修订文档与本表的全部相对链接与锚点可解析。
- 对 S2a、S2b 删除的符号逐个 grep 使用方：均落在对应阶段的预算内（`cache/` 及其测试在 S1 删除）。按文件名匹配命中的
  `table_ruleset_version` 其余用途属于快照物化请求字段，不在删除范围。
- 反引号中的源码路径：现存路径在 worktree 中存在；不存在的只有标注为“新增”或“迁移后”的文件，以及提案中的新名称。
- 设计 §12 与执行计划引用的测试文件：除标注为新增的文件外均存在。

以上是修订者自查，不替代独立复审。

### 8.7 r3 复审输入与关注点

- 复审对象：本分支包含 r3 的固定 commit（由复审者记录）；可只核对 `f984381ab3` 之后的差异；代码事实基线 `2172369803`。
- 重点关注：
  - 8.2、8.3 中每一项是否真正关闭，改动是否传播到所有相关位置；
  - business schema digest 与 manifest `canonical_schema_digest` 的区分，以及存储身份改用存储规则事实后 §4.5 的自洽性；
  - DC26 选定的精确放行是否符合 P5 §2A.2、§2A.3 与 ADR 0001；
  - 附录 B.2–B.6 的替换文本能否按字面并入，并入后上游文档中不再有与 ADR 0018–0021 冲突的现行表述；
  - 身份确认理由改为与 Archive 同一校验后，是否与 Archive 身份异常处置的理由规则一致。

## 9. r4 处置（两份 r3 复审）

本节记录 r4 的处置。§8 是 r3 的历史记录，保持原样。

### 9.1 输入与修订边界

- 输入：
  - [r3 独立复审（第一份）](p5-arch-closure-s0-independent-rereview-r3.md) @ `783acefe94`，结论为通过，含一项非阻塞 finding，以下编号前缀 RW1；
  - [r3 独立复审（第二份）](p5-arch-closure-s0-independent-rereview-r3-2.md) @ `46a4e03ae5`，结论为定向修订，两项阻塞、三项非阻塞，以下编号前缀 RW2。
- 两份报告结论不一致，但指向同一组问题：RW1-F1 与 RW2-F1 相同，RW1 判为非阻塞，RW2 判为阻塞。按 owner 指示，r4 修复两份报告的
  全部 findings，不再区分阻塞与否。
- 两份报告都认为不需要新的 owner 决议。r4 只修正定义与措辞，不改变 DC1–DC27。
- 只改文档：源码、测试、配置与已接受的 Contract 正文未改动；ADR 保持 Proposed；复审报告与决议记录不改写。
- r4 修订者与 r2、r3 修订者是同一人。r4 的核对须由未参与 r4 修订的 reviewer 承担，可只核对 `46a4e03ae5` 之后的差异。

### 9.2 处置

| 编号 | 问题 | 处置 | 改动位置 |
| --- | --- | --- | --- |
| RW2-F1、RW1-F1 | 用于标记 schema 差异来源的“存储规则事实”混入了随源 schema 变化的 retained 列与 `DDL_PRIMARY_KEY` 键，同一规则下源表增列或改主键会被标成规则变更 | 存储规则事实限定为规则侧字段：key policy、`EXPLICIT` 显式键、ordered policy、structural 列与 dropped 列（含理由），均已在 manifest 中；retained 列与 DDL 主键不计入。§4.5 改为逐项归因：规则事实差异可解释的归 `STORAGE_PROJECTION_POLICY`，其余归 `SOURCE_SCHEMA`，两类都有为 `BOTH`；写明两侧规则事实总是可得。`test_comparison_planning.py` 增加参数表：同规则下源表增列、改 DDL 主键 → `SOURCE_SCHEMA`；规则改变 dropped 列或显式键 → `STORAGE_PROJECTION_POLICY`；同时发生 → `BOTH`；只有列序不同 → 无 schema 事实 | 设计 §4.1、§4.5、§12、附录 A 第 6 项；ADR 0018 Context、Decision 3、Alternatives、Required Verification；ADR 0019 Decision 1；执行计划 S2a 第 4 项与验收 |
| RW2-F2 | manifest `canonical_schema_digest` 被写成服务 Repository STRUCTURAL；Repository 从不读取它 | 改为：用于 manifest 发布时的自洽核对与 mutation planning 的 schema 变化判断，并计入 manifest digest；Repository STRUCTURAL 比较包内 `manifest.json` 的列、主键与行数，不使用它。附录 B.1 的 §4 增补按同一表述改写，并入后与 Canonical Storage §4 原文一致 | 设计 §4.1 对照表、§12、附录 B.1；ADR 0018 Alternatives |
| RW2-N1 | §4.8 写“其余 Preview artifact 继续由 PreviewResult 持有”，与 Canonical Storage §5 冲突 | 改为：其余 Preview artifact 在 T1 随 `current-preview` 与 `preview-operation` 的保护一并解除，此后按 P5 §9 的固定 TTL 做 best-effort 清理；与现行 T1 的做法一致 | 设计 §4.8、§10 |
| RW2-N2 | 附录 B.4 的 Taxonomy §4.4 替换图与 B.6 的依赖方向不一致 | 替换图改为 `table_access/table_rules -> snapshot`；`snapshot + table_rules（StorageRuleView） -> storage_projection -> RepositoryImportArtifact`；`storage_projection -> mutation_planning`；`snapshot + table_rules（ComparisonRuleView） -> comparison -> risk -> surface -> bundle`；`snapshot -> project_identity` | 设计附录 B.4 |
| RW2-N3 | 身份确认理由复用 Archive Application 的校验函数，未写明共享校验的 owner | HTTP DTO 沿用 `BoundedDiagnosticReason`（1–4096 UTF-8 字节）；Submission 领域按 Review 理由的同一规则再校验（不含控制字符、代理码点与非字符码点，至少一个非空白字符）；S4 把该规则从 `domain/submission/review.py` 提取为 Submission 领域的共享校验，Review 行为不变；不从 Archive 导入 | 设计 §7.6；ADR 0020 Context、Decision 5；执行计划 S4 验收与 §3 S4 |
| RW1 §4 附带意见 | 附录 B.2 §5 候选中的“纯计算 operation 在恢复时稳定失败”须连同 §1 的“冻结值不同”条件理解 | 候选句写明条件：运行期 ruleset 与冻结值不同则稳定失败，相同则照常继续 | 设计附录 B.2 |
| RW2 §6 附带意见 | DC26 放行后，`canonical_row_hash` 的 `contracts.py` 仍须保持叶子 | 设计 §9 A6 行写明 `contracts.py` 不导入 compute，只 import contract 不加载 Rust 扩展 | 设计 §9 |

身份确认理由的规则比 r3 收紧：r3 与 Archive 一致，只限字节数；r4 与同属 Submission 领域的 Review 一致，另外拒绝控制字符与纯空白。
字节上限不变，违反时同样返回 `422 REQUEST_VALIDATION_FAILED`。

### 9.3 修订者自查

- `git diff --stat 2172369803 HEAD -- vnext` 为空。
- 被修订文档与本表的全部相对链接与锚点可解析。
- 新写入的源码事实已核对：`view.py` 中 retained 列与 `DDL_PRIMARY_KEY` 键取自源 descriptor，dropped/structural/key policy/ordered
  policy 来自规则；`canonical_schema_digest` 的消费方只有 `mutation_planning/_planner.py`、`storage_projection/publish.py`、manifest
  digest 与 durable manifest 编解码，Repository Service 中没有引用；现行 T1 在转移后清除 `current-preview` 与 `preview-operation`
  的保护；`BoundedDiagnosticReason` 与 `validate_review_reason` 的规则如 9.2 所述。

以上是修订者自查，不替代独立复审。

### 9.4 r4 核对的输入

- 核对对象：本分支包含 r4 的固定 commit（由核对者记录）；可只核对 `46a4e03ae5` 之后的差异；代码事实基线 `2172369803`。
- 关注点：9.2 各项是否关闭且传播到所有相关位置；§4.5 的来源归因能否直接写成 `test_comparison_planning.py` 的参数表；附录 B.1 的
  §4 增补并入后是否与 Canonical Storage §4 原文一致。
