# P5 架构收口 S0 r3 独立复审报告

- 日期：2026-09-26。
- 结论：**通过（文档审核）**；无阻塞项。保留 §6 的实施前置条件与一个非阻塞诊断精度问题。
- 身份：第一份 r2 独立复审的复审者；未参与 r3 起草、修订或 DC23–DC27 决议。此次是对修订结果的复核，不声称首次接触本设计。
- 本报告不接受 ADR、不修改 Contract 版本、不改变阶段状态，也不代替实施验收。

## 1. 对象、依据与边界

```yaml
reviewed_branch: p5-arch-closure-docs
reviewed_worktree: /home/dev/gdds-p5-arch-closure-docs
reviewed_docs_commit: ffba1138ef0b8e7f3646c1fd883086b803ece63d
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
owner_decisions_update: f984381ab3
initial_worktree_status: clean
vnext_diff_code_base_to_reviewed_commit: empty
main_workspace_changes: none
implementation_changes: none
```

本次首先固定 HEAD、确认代码基线到该 commit 的 vnext diff 为空，并阅读 r3 改动。
r3 修订提交涉及 9 个文档，427 行增加、180 行删除；决议与第二份复审作为另行提交的输入核查。
报告提交后产生的 HEAD 不替代上述被复审 commit。下文 D、EP 的章节/行号均指该 commit；源码行号均指代码基线。

被复审文件：

- D：[详细设计](p5-arch-closure-design.md)，含附录 A、B；EP：[执行计划](p5-arch-closure-execution-plan.md)。
- [Entry Brief](p5-arch-closure-s0-entry-brief.md)、[处置表](p5-arch-closure-s0-revision-disposition.md) §8、[P5](p5-business-vertical-slices-design.md) §2A.4.1、[README](../README.md)。
- ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、[0019](../adr/0019-commit-canonical-metadata-authority.md)、[0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)，以及未修改的 [0021](../adr/0021-flow-neutral-comparison-entry.md)。

复核输入：[原审核报告](p5-arch-closure-s0-independent-docs-review.md) F1–F11、N1–N6、§6、§7；
[第一份 r2 复审](p5-arch-closure-s0-independent-rereview.md)（下称 RV1）；
[第二份 r2 复审](p5-arch-closure-s0-independent-rereview-2.md)（下称 RV2）；
[Owner 决议](p5-arch-closure-s0-owner-decisions.md) DC1–DC27。
处置表仅作导航，未把自评状态当作审核结论；未以 memory 作为证据。

上游核查：[Business Lifecycle](../contracts/business-lifecycle-and-state.md)、
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[Ruleset Activation](../contracts/ruleset-activation-and-migration.md)、
[Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md)、
[Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)、
[ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)、
[Architecture](../architecture/architecture-and-refactoring-plan.md)、[5D 设计](p5-5d-archive-design.md)。
判断尺度为[纵切指南](../guides/slice-design-execution-and-review-guide.md) §4、§6、
[比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)、
[AGENTS](../../../../../AGENTS.md) 与[测试约定](../../../testing-conventions.md)。

## 2. 两份 r2 复审的关闭情况

本表的“已关闭”表示文档关闭标准满足，并非拟新增实现已通过测试。
RV1/RV2 的 F 编号均指各报告中的 RR-F；本报告 §5 的 RR-F1 是新的独立编号。

| 原项 | 独立判定 | 依据与理由 |
| --- | --- | --- |
| RV1-F1 / RV2-F1 | 已关闭 | D §7.6 第 501–511 行明确认证、当前权限、exact scope/Repository 映射先于重放；只有其后可漂移的新受理校验被越过。ADR 0020、D §12、EP S4 同步；补撤权及跨 scope 重放拒绝验收。与 C1 一致。 |
| RV1-F2 / RV2-N2 | 已关闭 | D §4.1 第 154–182 行区分 manifest canonical_schema_digest 与 business schema digest，说明 owner、来源、列序与用途，二者不可互换且均不进入存储规则绑定。附录 B.1 补 Canonical Storage §4，ADR 0018/0019 与 EP S2a 同步。C2 支持保持 manifest 物理摘要不变。存储规则事实的诊断归因精度另见 §5，不重新混淆两种摘要。 |
| RV1-F3 / RV2-F2 | 已关闭 | D §4.6、§4.8、§4.9、附录 B.2 同时覆盖 Ruleset §1、§5；Submit 边界统一为 T1 后，含 PREPARED（DC23）。Preview 受理时把 digest 冻结进 job payload，每步先校验，涵盖尚未 materialize 的排队任务（DC24）；EP S2a 与 ADR 0019 验收同步。 |
| RV1-F4 / RV2-F5 | 已关闭 | D §5.5 与 EP §3 S2a/S2b 已补 History compare 受理与 HTTP 映射、两个 compose 测试、History oracle harness、workspace/shutdown harness、受理模块与相关测试。保留 HistoryIntegrityFailure，按消费者扫描删除旧机制；不是按 integrity 字样一概删除。C5 是必改接缝。 |
| RV1-F5 / RV2-F3 | 已关闭 | D §5.1、§12 和 EP S2b 新增唯一 test_commit_canonical_metadata.py owner，覆盖 Repository+commit、冻结 scope、缺失、INITIAL、digest 不符与历史版本。DC25 明确 artifact digest 不符稳定失败、日志/指标、无 incident；附录 B.3 与 ADR 0019 同步。 |
| RV2-F4 | 已关闭 | D §9 A6、EP S1 及预算写明仅 canonical_row_hash → ext:compute 放行、同步规则形态参数表、迁移与放行同 diff。DC26 的选项已由设计选定并给出单 production provider 的依据。临时规则探针显示可精确放行，其他 capability 仍拒绝；不是增加整层豁免。C6。 |
| RV2-F6 | 已关闭 | 附录 A.1/B.3 插入点移至完整段落/代码块之后；B.4 补 Taxonomy §4.4、§4.6、§13；B.5/B.6 有可用替换正文；P3-R4 统一为取代标注。B.1 指定新 manifest contract_version=3.1.0、历史读取及 DC27 的版本轴处理时点。见 §4。 |
| RV2-N1 | 已关闭 | D §4.4 将 business schema 变化纳入只存不比的事实，schema 事实适用于所有存储角色；内容事实计入 pair 摘要/surface 计数。D §12 与 EP S2a 分别指定角色事实及显示 owner。C7 证实现行计数必须修正。 |
| RV2-N3 | 已关闭 | D §5.1 第 361 行将历史读取与当前写入校验拆开；EP S2a 调整 manifest 解码，S2b 的 metadata owner 覆盖历史版本，不能继续用当前常量拒绝旧 manifest。C3。 |
| RV2-N4 | 已关闭 | D §12、EP S2b 新增 integration 模块 test_submit_prepare_removed_tables.py；原 test_submit_job_prepare.py 只承担 unit checkpoint 复用，避免模块级 unit 标记污染真实 Dolt 测试。C4。 |
| RV2-N5 | 已关闭 | D §4.1 ordered no 为 INT NOT NULL；§5.3 精确描述原 digest 来源；§7.6 理由复用 Archive 1–4096 UTF-8 字节校验，持久原文；§4.9 写清排队/checkpoint 任务的激活影响。ADR 0019/0020 与 EP 同步。处置表 §3 的旧长度是 r2 历史记录，§8.3 已明确覆盖。 |

## 3. 原 F1–F11、N1–N6 重判

| 原项 | 独立判定 | r3 依据、源码接缝与实施时点 |
| --- | --- | --- |
| F1 | 已关闭 | 采用原审核 §7.2 标准。D §4.5、§4.7–§4.9、附录 B.2、ADR 0019 与 EP S2a 定义运行期规则、激活/恢复/回滚、三节点一致及 T1 冻结。规则选择不需要 digest 全序或历史规则取回；回滚及三节点行为已定义，并非这些场景消失。C8。 |
| F2 | 已关闭 | D §4.1–§4.2、§5.2、§12 和 EP S2a 给出 descriptor、类型词表、键可空性、SET、伪 gid、DC12/DC15 条件及真实 Repository/Arrow 往返 owner。C2/C9；实际同一性仍为 S2b 前门槛。 |
| F3 | 已关闭 | D §4.3、§4.6、§4.8、§10 明确 MODIFIED 规范闭包、manifest、schema/DML/打包分工、T1 指纹与保护、expected parent 删表、checkpoint 复用。EP S2b 与 §12 有对应验收。C4/C10。 |
| F4 | 已关闭 | 附录 A、B 修订面和接受时点完整；双摘要、Ruleset §5、Taxonomy DAG/artifact owner 等 r2 缺口均补齐。D §11、Entry Brief §5、EP S0 一致，版本为两个 3.0.0→3.1.0。 |
| F5 | 已关闭 | D §4.4、附录 B.1、ADR 0018 与 EP S2a 明确 9 条 ordered 规则去除 ignored no，保留结构列并收紧重叠校验。C9；没有误删位置列。 |
| F6 | 已关闭 | D §8、ADR 0018 与 EP S3 明确 VARCHAR(64)、来源表名长度校验、真实 Dolt 导入；TEXT 键已不是待决定停止条件。C9。 |
| F7 | 部分关闭 | 文档部分到位：D §4.2、§12–§14，EP S1 kickoff/S2b 给出整体失败、完整失败清单、真实数据普查与四份 dump 链路。普查/链路未执行；S1 kickoff 及 S2b 语义验收前分别完成，不阻塞 S0。C9。 |
| F8 | 部分关闭 | D §4.4、§12、附录 A.2 与 EP S2a 定义表级事实、schema 交叉、变化计数、compare-excluded；oracle 核对与事实形态冻结仍在 S2a，不能把文档到位当作已验收。C7。 |
| F9 | 已关闭 | D §5.1、§6、§7.2、附录 A.1、ADR 0019/0021 与 EP S2b 一致：INITIAL 零用户表、物化时断言、非空稳定失败、harness 改为空 seed，并说明误供给须改绑新 Repository。C11。 |
| F10 | 已关闭 | EP S1 残余三条、零运行时环及不可达分组可映射基线；DC26 补迁移后 Rust 导入规则；S2 拆分及消费者预算已补。D §9 保持 S1 行为约束，codec 合并在 S2a；不宣称预算免于 kickoff 的调用方复核。C5/C6。 |
| F11 | 已关闭 | D §4.1、§4.5、§5.3、§12 与附录 B.1 定义 business schema/规范状态摘要、列序无关、提前退出与 schema 事实，已与 manifest 摘要分开。C2/C9；共享参数表在 S2a 验证。 |
| N1 | 已关闭 | D §7.5–§7.6、§12、ADR 0020、EP S4 完整约束数量、唯一 action、枚举、digest、理由、422/409、独立确认、指纹及授权先于重放；FULL 混合模式与双路径 assessment 有验收。输入边界仍是实施必达。C1。 |
| N2 | 已关闭 | D §3、§6、§7.4 和 ADR 0020/0021：surface 自有中性类型，由 Application 映射，替换 bundle 获得两侧 table_artifacts。C7。 |
| N3 | 已关闭 | D §5.1、§12、ADR 0019、EP S2b 覆盖键、scope、长期 manifest 及 digest 校验，新增唯一测试 owner；是实施必达。C3/C10。 |
| N4 | 已关闭 | D §4.4 的表 UNCHANGED 表示比较值不变，内容事实表示规范内容变化；规范状态摘要仍变化，允许提交，无行级差异/risk。新增/删除记录携带全部列，修改记录的具体形态随 F8 冻结。C7。 |
| N5 | 已关闭 | D §2 的 R3/R4 精确为预检/逐 batch 转换，E-e 区分空表增列与旧 digest 漏检，P5 R1 摘要同步；D §4.3 使用公开发布入口。C8/C9。 |
| N6 | 已关闭 | D §1、§10、§12 与 EP S2a/S2b 分离能力层和域切换、前向 migration、旧行缺值拒绝、测试 owner 按表归属。DC6/DC21 未被兼容层绕过。 |

源码证据索引（本轮只读抽查；未修改源码）：

| 编号 | @2172369803 的位置及事实 |
| --- | --- |
| C1 | `vnext/backend/src/gateway_backend/application/submission/accept.py:74` 权限检查、150 行 scope；`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:122` 事务内受理；`vnext/backend/src/gateway_backend/application/archive/contracts.py:58` 理由校验。 |
| C2 | `vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py:80` manifest schema 保留列序；`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:279` 将实际 retained 等字段写入 manifest；`vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py:33` 由源 descriptor 推导 retained/key。 |
| C3 | `vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py:290` manifest 构造约束当前版本；`vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py:251` manifest 长期保护。 |
| C4 | `vnext/backend/src/gateway_backend/application/submit_jobs.py:450` prepare checkpoint 优先；`vnext/backend/tests/test_submit_job_prepare.py:62` 模块级 unit；`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263` 完整 catalog STRUCTURAL；`vnext/repository_service/src/gateway_repository_service/candidate_a/dolt_cli.py:452` 执行 replay SQL。 |
| C5 | `vnext/backend/src/gateway_backend/application/history/compare.py:137` pending incident 阻断；`vnext/backend/src/gateway_backend/http/orchestration/history_compare.py:1` 受理映射；`vnext/backend/tests/test_history_compose_e2e.py:15`、`vnext/backend/tests/test_ordered_compare_compose.py:13` 旧 policy helper；`vnext/backend/tests/support/compose_gate_harness.py:849` History oracle。 |
| C6 | `vnext/backend/src/gateway_backend/compute.py:5` Rust import；`vnext/backend/tests/support/import_rules.py:46` ext:compute 分类、316 行 capability 共用 allow-list；`vnext/backend/tests/architecture_baseline.py:18` 冻结基线。 |
| C7 | `vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py:118` 旧 changed count 过滤 UNCHANGED；`vnext/backend/src/gateway_backend/capabilities/surface_assembly/contracts.py:20` 旧 identity 类型依赖。 |
| C8 | `vnext/backend/src/gateway_backend/application/preview_jobs.py:964` SQL 物化、1227 行旧规则校验、1335 行固定身份；`vnext/backend/src/gateway_backend/application/history/compare_jobs.py:890` 旧 policy 派生。 |
| C9 | `vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:414` 键检查、500 行类型边界；`vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:198` ordered no；`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py:88` TEXT；`vnext/backend/src/gateway_backend/infrastructure/repository_read/http_arrow.py:301` batch 转换；`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:950` 旧提前退出。 |
| C10 | `vnext/backend/src/gateway_backend/application/submission/contracts.py:329` 新受理指纹、366 行重放指纹；`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:321` 保护转移；`vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py:34` 包内表 DROP/CREATE。 |
| C11 | `vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py:80` initial 身份登记；`vnext/backend/tests/support/compose_gate_harness.py:1202` 现行预导入 seed。 |

## 4. 闭合性、传播与执行可行性

**运行期规则。** DC10 与进程启动捕获 snapshot 自洽，激活必须 drain/restart；恢复边界由 DC23/24 和 B.2 明确。
历史 commit 的不同 digest 不失败，operation 的冻结 digest 与运行期不同才失败。History 激活后同 key 的指纹改变，返回 409，
用户用新 key 重跑；三节点仍使用一份运行期规则。B.2 §5 候选中“纯计算 operation 在恢复时稳定失败”必须连同 §1 的
“冻结值不同”条件理解，不能实现成所有普通恢复均失败；§4.9 标题/场景和 S2a 每步校验已排除后一种解释。

**T1 与写入。** 规范闭包/manifest 为 FULL 多侧 artifact 提供精确 consumer；T1 冻结并纳入指纹，重放从 Attempt 取值。
保护只转移 Attempt 后续所需闭包、表、manifest、source/ready 绑定，其余仍按 Preview 生命周期保护，D §4.8 已明示。
prepare 从冻结 expected parent 获取 catalog，计算 parent−target，DROP 后目标全量 replay，最终表集合正好等于 manifest；
Repository 的既有 SQL replay/STRUCTURAL 支持这一点。包 checkpoint 后复用，CAS/evidence-first 不变；业务基线与 main 不同的
sibling 情形不偷换 parent，也不改变 DC18 已选择的完整状态提交语义。无需修改 Repository wire。

**状态与权威。** 规范摘要仍比较上传与业务基线，满足 Canonical Storage §9 和 Business Lifecycle §3；丢弃列不进入摘要，
compare-excluded 列仍进入摘要与表内容事实，故“UNCHANGED + 可提交”自洽。INITIAL 是被引用的初始 commit，不是要求 main
永远为空；5D 的迁移/seed 登记身份与物化断言分工不冲突。B.3 只按 DC19/DC25 收窄 incident，保留 Repository 返回与 Backend
期望冲突、CAS/结果歧义和 ADR 0016 Operation integrity；没有把已完成 commit 当作可用重新上传替代的临时数据。

**附录可并入。** 对照上游核对定位词及完整上下文：A.1 的首段末句存在；A.2 的 XML 原词存在；B.1 的 §2 与 §4 摘要段存在；
B.2 的 §1 与 §5 两句存在；B.3 的字段块和其后 incident 段存在；B.4 的 DAG、artifact/owner 行及历史 §13 第 9 项存在；
B.5 的流程句、XML 句、包根行和 B.6 的图/§7.2/§9.1/目录/§13 均可定位。
引文中的省略号是定位片段，不是完整原文；跨行和 code span 依 D 附录前言保留原词，不能机械把省略号写入 Contract。
Business Lifecycle 与 Canonical Storage 均为 3.0.0→3.1.0，新 manifest 从 S2a 写 3.1.0，历史 decoder 已有实施预算。
接受时可以按这些编辑指令并入，无需重新决定规则选择或 incident 范围；本轮没有执行并入。

传播检查覆盖设计正文/附录、EP、ADR 0018–0021、Entry Brief、P5 §2A.4.1 和 README。
两侧 digest 必须相等、RULESET_BINDING_MISMATCH、TEXT 停止条件、未拆分 S2 等仍出现在历史描述/否定句时，不是有效要求；
处置表 §2/§3 保存 r2 记录，§8 明确 r3 覆盖。不把这些历史文字误报为回退。

**S1 与路径预算。** 基线 54 个唯一违例、8 个运行时环、16 个不可达模块与既有冻结项一致。
S1 指定的三条残余、composite/XML 四模块、external_target_sync 三模块和迁移后的 canonical row hash 三模块都有去向。
精确放行 Rust import 后没有发现必然新增的 layer 违例；S1 必须保留 golden/digest/checkpoint/HTTP/旅程结果，
synthetic worker 仅改测试侧装配，codec 合并留在 S2a。预算补齐 RV2 指出的调用方；kickoff 按 S1 实际迁移路径更新后续预算，
特别是 job payload 的冻结字段传递，不应因文件改名漏掉序列化边界。
S2a 保留 R1 是受控中间状态，非空基线 Preview 可能变化，EP 明确记录、不发布，S2b 通过同一性门槛后修复。

**比例化与测试。** ParentCatalogPort 服务 prepare 删表；MetadataPort 服务 Repository 节点 provenance/scope；闭包服务精确冻结；
身份确认服务跨项目误提交/异常归档，均有当前 consumer，不需要 broker、sidecar 或历史规则仓库。
输入上限、路径/标识符引用、跨 scope、事务/CAS、重放授权没有因比例化取消。
D §12 共 28 个不同测试文件，19 个已存在、9 个在 EP 相应阶段明确新增；按能力事实、Application 接入与 HTTP 映射区分 owner，
未发现同一不变量要求两个权威 owner。N3 已有单一文件，NO_CANONICAL_CHANGE 的重复断言明确收敛。
纯规则/解析用共享参数表和 unit；真实 Dolt 往返/删表单列 integration；EP 测试规则保留时序 serial，遵循 AGENTS。
阶段末/最终候选镜像规则及停止条件可执行，DC12/DC15/DC27 的条件判断不得由测试侧静默改语义。

## 5. 新 finding

### RR-F1：实际存储字段集合不等同于存储规则变化

- 类别：**已证实缺陷（诊断归因定义）**；**非阻塞**。
- 位置：D §4.1 第 156 行、§4.5 第 278 行、§4.9 激活表第一行；ADR 0018 的 schema 来源说明；EP S2a 对齐验收。
- 依据：C2 的 view.py 33–44 行根据源 descriptor 推导 retained_columns 和 DDL_PRIMARY_KEY 的 key。
  本轮临时探针对完全相同 net_cfg 规则，只在源表增加 extra 列，retained 从 (board, link_no) 变为
  (board, link_no, extra)。没有规则变化，manifest 的“存储规则事实”仍会变化。
- 触发场景：同一规则下源增列/删列，或 DDL key 改变。按 §4.5 字面分支会把源 schema 变化标为 STORAGE_PROJECTION_POLICY；
  “事实相同而 schema 不同”和“两者兼有”的关系也不足以唯一决定 BOTH。
- 影响：可能误导用户对 schema 变化来源的解释。当前设计始终按列名/有效键 alignment，未发现该标签控制写入、CAS、规则激活或
  NO_CANONICAL_CHANGE 的证据，因此不阻塞 S0，不要求推翻 DC10 或新增历史规则持久化。
- 最小修正方向：由 comparison owner 在 S2a 明确区分配置的 policy 与源 descriptor 派生的 effective fields；不要以 retained/key
  的变化本身证明 policy 改变。给出来源判定表，说明 available provenance 不足时如何解释，避免凭缺失信息断言因果。
  不要求增加额外状态机；若需要改变 Contract 的标签语义，先交 owning Contract owner 确认。
- 关闭标准：test_comparison_planning.py 的共享参数表覆盖同规则源增列/删列、只改 policy、两者同时改、仅列序改变；来源标签与
  实际原因一致，且不改变列序无关状态和统一 alignment。D/ADR/EP 同步该判定，最迟 S2a 语义冻结时完成。
- 事实/推测区分：字段依赖源 schema 和字面分支误分类已证实；没有声称未来实现已经误写业务数据。

## 6. 保留前置条件与 owner 事项

通过仍保留以下实施条件：

1. 由 owner 按 Entry Brief §5 接受 ADR/上游候选并完成取代标注；5E slice exit 后再进入实施，S1 kickoff 复核主线相对代码基线的变化。
2. S1 kickoff 完成 DC22 真实数据普查，落定 DC12/DC15；若 JSON→LONGTEXT 触发，按 DC27 在 S2a handoff 记录版本轴判断。
3. S2a 完成真实 Dolt/HTTP Arrow 同一性门槛、F8 oracle/事实冻结、规则恢复和 schema/内容验收；处理 §5 的来源标签精度。
4. S2b 完成 F7 四份 dump 链路、metadata scope/digest/历史版本、删表 replay/STRUCTURAL、T1 保护/指纹/重放/CAS 与 INITIAL 验收。
5. S3 composite 真实导入；S4 输入边界、身份/归档/FULL 混合模式；各阶段及 S5 最终候选执行规定镜像与容器门禁。

没有需要 owner 新作出的业务决议。本报告不重新裁决 DC1–DC27；DC27 及设计停止条件中的确认仍在其原定时点进行。

## 7. 实际核查、局限与镜像记录

本轮实验均在仓库外临时目录，Python 使用指定只读 venv 和 worktree PYTHONPATH，并禁止 bytecode 写入：

- 规则事实探针：相同规则下源增列改变 retained_columns，支持 RR-F1。
- 架构扫描：54 个唯一违例、8 个运行时环、16 个不可达模块；原始违例实例为 56，按与 baseline 相同的 key 去重后为 54。
- DC26 临时内存规则探针：canonical_row_hash → gateway_compute 从 layer 违例变为允许，comparison → gateway_compute 仍拒绝。
  仅证明精确放行可实现，没有模拟整个 S1 迁移。
- 测试 owner 路径核查：28 个文件，19 个存在、9 个在计划中新增。
- 提交前五包 ruff、mypy 最终均通过；mypy 分别检查 34、15、26、198、459 个文件。
  使用只读环境、仓库外 mypy cache、ruff --no-cache，未同步依赖或改锁。Backend 首次经临时 venv 的 python -m ruff 调用
  报 621 项（与正常 CLI 结果不同，未单独归因）；改用只读 venv 的原 ruff CLI 在同一 worktree 执行通过，未改代码或配置。
- 报告内相对链接、反引号内完整源码路径及所引用行号做机械校验；没有新增 legacy 路径引用。

本轮没有执行全量测试、真实 dump、Dolt、完整业务 e2e 或容器门禁。RV1 的真实 Dolt 删表/STRUCTURAL 探针是同一代码基线的
历史证据，本轮只重新核对源码，未冒充重新运行。未读取主线后续源码、未修改主工作区；只读使用其 venv。
不宣称拟新增 snapshot identity、metadata、恢复/CAS 或 cleanup 验收已完成；这些仍由实施阶段交付。

```text
Current HEAD: ffba1138ef0b8e7f3646c1fd883086b803ece63d（固定复审对象；报告另作 docs-only 提交）
Container rebuild required: no
Reason: docs-only，vnext 与代码基线无差异，未触及 image/deployment/container-only runtime boundary
Last verified image revision: none（本轮未核验）
Last verified source-tree/image id: none（本轮未核验）
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 本轮无容器声明；实施按执行计划 §6 的相应门禁与 S5 最终门禁
Required execution point: 相应实施阶段最终候选及 S5 fresh 构建；本轮不执行
```
