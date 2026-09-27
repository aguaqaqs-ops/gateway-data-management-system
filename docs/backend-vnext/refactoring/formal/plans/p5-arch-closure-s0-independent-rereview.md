# P5 架构收口 S0 r2 独立复审报告

- 日期：2026-09-26。
- 身份：未参与 r1 起草、S0 审核或 r2 修订的独立复审者。
- 结论：**定向修订**。阻塞项为 **RR-F1、RR-F2**。
- 本报告只评审文档；不接受 ADR、不改 Contract 版本或阶段状态，不构成实现授权。
- 依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §4、§6、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)、
  [AGENTS](../../../../../AGENTS.md)、[测试约定](../../../testing-conventions.md)。

## 1. 结论与对象

总体模型与主要执行路径成立，无需整体返工。r2 实质关闭了规范域切换、规则选择、规范投影复用、删表、
INITIAL、类型处置与阶段拆分的大部分缺口。不能直接通过的原因是：

1. 设计和 ADR 0020 明文把 same-key 重放排在 scope 与权限之前，且误标为既有行为。
2. 新规范 schema digest 与 accepted Canonical Storage §4 中 manifest 的同名摘要定义不一致，
   文档未区分两种身份，也未提供该条款的修订候选。接受时无法确定应保留还是替换哪一个摘要。

这两项均可定向修复，不需要改变 DC1–DC22。RR-F3–RR-F5 为非阻塞补充，建议在同一文档修订中处理。
本报告没有需要 owner 重新裁决的业务事项。

```yaml
reviewed_branch: p5-arch-closure-docs
reviewed_worktree: /home/dev/gdds-p5-arch-closure-docs
reviewed_docs_commit: 5858eaaa08e8a32948d3ab08f827224baef30ddd
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
initial_worktree_status: clean
r1_commit: 3e5d5807e5
review_inputs: [8d89ca3c86, 89668aaf56]
owner_decisions_commit: 3f3b1de192
vnext_diff_2172369803_to_5858eaaa08: empty
main_workspace_changes: none
implementation_changes: none
```

开始时依次记录 HEAD、检查两个固定 commit 间的 vnext diff、阅读 r1→r2 diff stat。
后者共 12 个文档，1,984 行增加、423 行删除；不包含源码变化。
所有下述文档章节及行号均指复审 commit；所有源码行号均指代码基线。
报告提交产生的新 HEAD 不替代被复审 commit。

被复审文件及输入：

- [修订处置表](p5-arch-closure-s0-revision-disposition.md)；只作导航，未采用其自评结论。
- [原审核报告](p5-arch-closure-s0-independent-docs-review.md)，包括 §6、§7 的更新关闭标准。
- [Owner 决议](p5-arch-closure-s0-owner-decisions.md)，尤其 DC10–DC22。
- [Entry Brief](p5-arch-closure-s0-entry-brief.md)、[详细设计](p5-arch-closure-design.md)（含附录 A、B）、
  [执行计划](p5-arch-closure-execution-plan.md)。
- ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
  [0019](../adr/0019-commit-canonical-metadata-authority.md)、
  [0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [0021](../adr/0021-flow-neutral-comparison-entry.md)。
- [P5](p5-business-vertical-slices-design.md) §2A.4.1 及 [formal README](../README.md) 索引。

上游另外核对了 [Business Lifecycle](../contracts/business-lifecycle-and-state.md)、
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[Ruleset Activation](../contracts/ruleset-activation-and-migration.md)、
[Operation Lifecycle](../contracts/operation-lifecycle-and-integrity.md)、
[Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md)、
[ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)、
[Architecture](../architecture/architecture-and-refactoring-plan.md) §7、§10、§13、
P5 §2A.2、§2A.4、§6.1 以及 [5D 设计](p5-5d-archive-design.md) §6。

## 2. 核查、实验与局限

### 2.1 实际执行

源码只读核查覆盖 Preview 物化与比较、Submit 受理/指纹/保护转移/prepare/finalize、History 受理及
incident 消费者、snapshot 编码与摘要、storage schema/DML/package 分工、Repository replay 与 STRUCTURAL。
对主工作区仅只读使用 venv 和 legacy 行为 oracle；没有读取或引用主线后续源码作为基线。

临时脚本、Dolt HOME、数据库和静态检查缓存全部放在审核者的仓库外临时目录，未入库。
Python 核查按任务指定的 backend venv 与 worktree PYTHONPATH 执行，禁用 bytecode 写入。
Repository 校验探针额外把本 worktree 的 repository_service/src 加入模块搜索路径。

| 核查 | 本轮结果 | 证据强度 |
| --- | --- | --- |
| import_rules 模块 | 54 条违例、8 个运行时环、16 个不可达模块，与冻结基线逐条相符 | 实际运行；不是 S1 修复后的结果 |
| 规则集统计 | 52 条；SKIP 8、SNAPSHOT_ONLY 1、BROWSE_ONLY 13、ORDERED_DIFF 9、STANDARD_DIFF 21；13 条 ignored 中 4 条 dropped，9 条与结构列重叠 | 实际运行 registry |
| manifest schema digest 列序探针 | 相同列定义仅反转列序，现行 storage `compute_schema_digest` 不相等 | 实际运行，支持 RR-F2 |
| Dolt 2.1.11 删表 replay | 用户删表、sibling 新增表、sibling 删除表、删除全部表，最终表集合分别符合目标 | 实际 CLI 运行 |
| STRUCTURAL 核心比较 | 上述四组从真实 Dolt 获取表名、列类型/可空性/主键、行数，再调用现行 `_compare_manifest_structural`，均通过 | 实际运行校验函数；没有经过 HTTP import operation |
| 设计 §12 测试文件 | 所列 25 个不同测试文件中，18 个存在；7 个不存在的均在执行计划相应阶段标为新增 | 路径核查；不是测试已实现的证明 |
| 五包静态检查 | 五包 ruff 全通过；五包 mypy 最终分别通过 34、15、26、198、459 个文件 | 只读检查代码基线，非实现验收 |

Dolt HOME 在首次 init 前预置 `versioncheck.disabled=true`、`metrics.disabled=true`。
删表探针构造简单 INT 主键表，按 `parent − target` 生成 DROP，再对目标表 DROP/CREATE/INSERT；
最后以实际 catalog 核对目标 manifest。sibling 两种情况验证的是技术 parent 与目标集合的差异，
没有模拟 control DB 中完整的 sibling 生命周期。首次空 catalog 输出解析缺少 `rows` 的处理错误发生在
临时探针，修正后四组重跑通过；不是产品缺陷。

静态检查未使用会同步依赖的入口，未改锁文件。使用只读 venv 中的工具、`ruff --no-cache` 和仓库外
mypy cache。首次共用 backend 环境并把五包全部放进 MYPYPATH，导致 Repository 缺少 mysql/httpx2 依赖、
Backend 出现因强制类型解析产生的 redundant-cast/unused-ignore。改用 Repository 自有只读 venv，
Backend 使用临时 venv overlay（第三方包只读链接，editable 路径指向本 worktree），保持正常包可见性后通过。
未修改源码、检查配置、依赖或忽略错误码。

### 2.2 局限

- 没有运行全量测试、业务端到端或容器门禁，没有构建镜像。
- 没有重新完成原审核的全部 E1–E9 实验；本轮独立核查源码，并对删表与摘要冲突做了上述定向实验。
  原报告的 Dolt JSON 精度、SET 顺序、TEXT 主键实验仍是历史证据，不冒充本轮复现。
- 未读取真实业务 dump，未完成 DC22 普查或运行验收；F7 保留到指定时点。
- 本轮不证明 CAS、response loss、artifact cleanup 并发或完整 HTTP Arrow 往返已通过；这些仍由既定实施 owner 验收。
- 没有审核 2172369803 之后主线的 P5-5E 变化，由 S1 kickoff 复核。

### 2.3 镜像决策

```text
Current HEAD: 5858eaaa08e8a32948d3ab08f827224baef30ddd（复审对象；报告另作 docs-only 提交）
Container rebuild required: no
Reason: docs-only 独立复审；未修改 image/deployment/container runtime boundary；未宣称阶段退出
Last verified image revision: none（本轮）
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 本轮无；实施阶段按执行计划 §6，S5 fresh 最终门禁
Required execution point: 相应实施阶段最终候选；本轮不执行
```

## 3. 原 findings 独立关闭判定

“已关闭”表示达到本轮文档关闭标准，不表示相关实现或测试已经交付。F7、F8 按原报告标注的后续时点判断。
源码证据编号见 §4；表内 D=详细设计、EP=执行计划、EB=Entry Brief，均为上列链接中的 r2。

| ID | 独立判定 | 关闭标准核对与剩余事项 |
| --- | --- | --- |
| F1 | 已关闭 | 以原报告 §7.2 为准。D §4.1、§4.5、§4.7–§4.9（148–151、254–257、280–316 行）明确运行期规则、三节点一致、存储差异 alignment、旧 Preview 陈旧拒绝、恢复稳定失败和 Submit 冻结。附录 B.2 给出 Ruleset §1 的恢复例外；§12（567、570–572 行）分别指定三个核心场景及恢复 owner。DC10 已消除规则全序与历史取回需求；回滚和三节点行为实际仍有定义，见 §5.1。原代码接缝见 C1、C3。RR-F3 是措辞传播建议，不重开规则选择。 |
| F2 | 已关闭 | D §4.1–§4.2（135–198 行）给出 descriptor、键可空性、伪 gid、SET、JSON 条件处置及词表；§12 第 561 行与 EP S2a 指定真实 Repository/HTTP Arrow/Dolt 同一性 owner。已知差异不再作为未知停止项，§14 只保留修正失败的停止条件。代码 C4、C5。摘要与 manifest 的上游衔接另由 F4/F11、RR-F2 处理。 |
| F3 | 已关闭 | D §4.3、§4.6、§4.8、§10（202–206、268–274、287–302、531 行）明确 adapter/port、schema+DML+打包、只发布 manifest、MODIFIED 闭包、T1 字段/指纹/保护、冻结 parent 删表与 checkpoint 复用。§12 第 574–575 行和 EP S2b 覆盖三种删表情形。C3、C6 与本轮 replay 探针支持不改 Repository 的可实施性。same-key 的权限顺序是 RR-F1，不能因闭包冻结已补而忽略。 |
| F4 | 部分关闭 | 原报告列出的 XML、Comparison Projection、incident 范围、Taxonomy hidden 行都有附录 A/B 候选、§11 owner 和 EB §5/EP S0 接受时点。Business Lifecycle/Canonical Storage 版本均正确。但 RR-F2 所涉 Canonical Storage §4 尚无候选或明确的双摘要区分，故附录整体不能直接接受。 |
| F5 | 已关闭 | D §4.4（210–221 行）、附录 B.1、ADR 0018 Decision 4 和 EP S2a 一致：9 条 ordered 规则去掉 ignored 中的 no，保留结构/位置语义，校验包括结构列，明确 ruleset digest 改变。代码 C2 的 registry 与 storage view 证实修正针对真实冲突。 |
| F6 | 已关闭 | D §8 第 489 行、ADR 0018 Decision 6、EP S3 第 163–169 行明确 VARCHAR(64)、来源表名长度校验及真实 Dolt 导入；TEXT 停止条件已撤销。代码 C7；legacy 列定义也为 VARCHAR(64)。 |
| F7 | 部分关闭 | 文档部分到位：D §4.2、§12–§14，EP S1 kickoff 第 64–74 行及 S2b 第 157–158 行明确失败清单、整体 FAILED、普查、DC12/DC15 条件执行和 4 份 dump 链路。C5 证实类型限制真实存在。普查和链路证据尚无，不能写成完全关闭；不阻塞 S0，普查在 S1 kickoff、完整关闭在 S2b 语义验收前。 |
| F8 | 部分关闭 | DC16 已进入 D §4.4（237–250 行）、附录 A.2、ADR 0018 Decision 5；§12 第 566 行指定角色 owner，EP S2a 第 120 行规定冻结时点。文档部分到位；具体事实形态及 Preview/Review 可见性在 S2a 冻结，尚未执行，不能完全关闭。C8 与 legacy oracle 支持该项有必要。 |
| F9 | 已关闭 | D §5.1、§6、§7.2、附录 A.1 与 ADR 0019/0021 一致：INITIAL 必须零用户表，读取 catalog 后断言，非空稳定失败；EP S2b 明确改 compose seed 并验收。与 Business Lifecycle §1A.2、5D §6 不冲突，见 §5.5。现状 C9。 |
| F10 | 已关闭 | 按原关闭标准：EP S1 第 81–94 行的三条残余、零环及不可达分组可逐条映射 baseline；A2 移入 Application；codec 合并移至 S2a；原报告明确列出的生产/测试路径和 DC9 DTO/OpenAPI/探针均已补齐。C10。进一步扫描发现 S2b 一个必改消费者漏列，记为非阻塞 RR-F4；不宣称整张路径预算已穷尽。 |
| F11 | 部分关闭 | D §4.1、§4.5、§5.3、§12 第 563 行已定义 schema+内容+行数、排除列序并指定共享参数表；提前退出不再只看旧 compare_schema_digest。C4、C5 支持修复必要性。但同名 manifest schema digest 的关系未定义（RR-F2），规范身份尚未与上游闭合。 |
| N1 | 部分关闭 | 输入边界已作为实施必达写入 D §7.6（448–452 行）、ADR 0020 Decision 5、§12 第 579 行和 EP S4 第 182–183 行：数量、重复 action、枚举、digest、理由与错误码齐全。评估集、FULL 混合模式和舍弃旧 projection/allowance 也已补。判定顺序新增 RR-F1 回退，须修正。 |
| N2 | 已关闭 | D §3、§6 第 398 行、§7.4 第 434 行与 ADR 0020/0021 给出 surface 自有类型、Application 映射及双侧 table_artifacts，不新增 surface→identity 边。C8 显示现有接缝确需修改。 |
| N3 | 已关闭 | D §5.1 第 325–327 行明确 Repository+commit 键、该 Repository 的业务记录、冻结 scope、manifest digest；ADR 0019 Required Verification 明确验收。C3 的长期 manifest 保护可复用。设计与验收均已写入；§12 尚应指定唯一测试文件，见非阻塞 RR-F5。 |
| N4 | 已关闭 | D §4.4 第 247–248 行明定排除列变化为表 UNCHANGED 加内容变化事实，允许提交；新增/删除记录保留全部列。与规范存储身份和行级比较语义可以并存，见 §5.4；F8 的展示验收不能省略。 |
| N5 | 已关闭 | D §2.1 R3/R4 更正为预检与逐 batch 转换；§4.3 使用 facade 的 publish_snapshot_table_artifact。C1、C3、C4 与源码吻合。 |
| N6 | 已关闭 | EP S2a/S2b 分别审核；D §1、§10、§12 明确前向 migration、旧行空值按不可用、S2b 前重建开发/测试数据、按表归属的 migration owner。无兼容层，符合 DC6/DC21。 |

## 4. 源码事实复核索引

以下路径均在 worktree 中存在。C 编号用于减少关闭表重复，不表示新增 findings。

| 编号 | 核查事实与代码定位（@2172369803） |
| --- | --- |
| C1 | R1/R2/R5/R6：`vnext/backend/src/gateway_backend/application/preview_jobs.py:964` 走 SQL parse/materialize；同文件 1335、1340、1348 行固定 SAME_PROJECT 并调用 bind_pair_input，未传 table_policies；`vnext/backend/src/gateway_backend/application/history/compare_jobs.py:890` 只从规则派生 ordered/ignored policy。对照设计 §2，支持原始/规范域不一致、角色未接线及 XML 未接入。 |
| C2 | E-g/F5：`vnext/backend/src/gateway_backend/capabilities/table_rules/registry.py:198` 的 ordered 规则同时有 ignored no 与 structural no；`vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py:33` 根据 dropped_columns 处理列。设计 §4.4 的修正不应把 no 从存储删除。 |
| C3 | R3/E-f/T1：`vnext/backend/src/gateway_backend/http/orchestration/submit_acceptance.py:238` 预检计算基线 digest，147 行按 artifact id 选表；`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:396` 构造冻结 Attempt；`vnext/backend/src/gateway_backend/application/submission/contracts.py:329` 与 366 行分别从新请求事实和既有 Attempt 构造指纹；`vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py:251` 把 manifest 转给长期 owner。 |
| C4 | R4/E-c/E-d/E-e：`vnext/backend/src/gateway_backend/infrastructure/repository_read/http_arrow.py:142` 从行重建 hidden summary，301 行逐 batch/列 to_pylist；`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/repository_ref.py:262` 再读表；`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/scalar_encoding.py:60` 和 156 行为 SET 的字符串型解码接缝；`vnext/repository_service/src/gateway_repository_service/arrow_mapping.py:367` 输出 list<string>；`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/_digest.py:98` 对列序敏感，114、156 行分别是缺完整 schema 的比较/状态摘要。 |
| C5 | E-a/E-d/F2/F11：`vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:414` 起检查无键/重复键等，500 行限制类型，513 行起固定 gid 为 INT UNSIGNED；`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:950` 的提前退出只用旧 compare_schema_digest、行数与内容；`vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py:80` 的 schema digest 保留传入列序。 |
| C6 | E-f/E-i：`vnext/backend/src/gateway_backend/application/submit_jobs.py:450` 优先复用 prepare checkpoint，1350 行起重新取运行期规则，2151 行起按摘要找表；`vnext/backend/src/gateway_backend/repository_import_artifact.py:130` 起组合投影/schema/DML/发布；`vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py:34` 只 DROP/CREATE 包内表；`vnext/backend/src/gateway_backend/capabilities/mutation_planning/import_replay.py:68` DML 接收 repository_base_digest。Repository `vnext/repository_service/src/gateway_repository_service/providers.py:400` 委托 replay；`vnext/repository_service/src/gateway_repository_service/candidate_a/dolt_cli.py:452` 直接执行 SQL；`vnext/repository_service/src/gateway_repository_service/versioned_import/verification.py:263` 起核对完整表集合、主键、列和行数。 |
| C7 | E-b/F6：`vnext/backend/src/gateway_backend/capabilities/snapshot_materialization/compose.py:88` 声明 source_table TEXT；主工作区 `legacy/backend_vnext/capabilities/composite_signal/materializer.py:81` 声明 VARCHAR(64)。本轮只读对照，未重跑 TEXT/JSON Dolt 探针。 |
| C8 | N2/F8：`vnext/backend/src/gateway_backend/capabilities/surface_assembly/contracts.py:20` 导入 comparison IdentityStatus；`vnext/backend/src/gateway_backend/capabilities/surface_assembly/_assembly.py:118` changed_table_count 排除 UNCHANGED；主工作区 `legacy/backend_vnext/capabilities/comparison/planner.py:333` 为 BROWSE_ONLY 路由。新内容变化事实必须有独立展示，不能假定现行 changed_count 自动反映它。 |
| C9 | E-h/F9：`vnext/backend/src/gateway_backend/infrastructure/control_db/sqlite_mapping.py:80` 接受供给的 commit 身份；`vnext/backend/tests/support/compose_gate_harness.py:1202` 默认 import_baseline=True；同文件 1218 行先导入再登记基线。 |
| C10 | S1 基线：`vnext/backend/tests/architecture_baseline.py:18`、`vnext/backend/tests/support/import_rules.py:86`。逐条核对 54/8/16 与设计 §9/EP S1，见 §6。 |

设计 §2 E-e 的概括略过了一个区别：空表增列会漏过旧 raw_state_digest，但原审核 E8 中 comparison 已显示
SCHEMA_CHANGED；不能把所有 schema 类别概括成“两个环节都不可见”。P5 §2A.4.1 第 238 行仍保留
“带显式键、忽略列或 SKIP 规则的表系统性降级”的过宽表述，设计 R1 已更精确。这些事实摘要应随修订校正，
不改变 F11 修复方向，也不是新的业务阻塞。

## 5. 关键闭合性与上游候选

### 5.1 运行期规则集

DC10 把选择函数定义为“本次 operation 捕获的当前激活规则”，不是在几个 digest 中选最大值。
因此全序及历史规则文档取回两个机制确实不需要。回滚后新操作按回滚后的运行期规则；三节点 History
整份结果使用一个规则集，D §4.7/§4.9 已明定。后两项是行为已定义，不是场景消失。
旧 commit provenance 不触发 mismatch；存储身份变化进入 alignment/fallback。

附录 B.2 是 Ruleset §1 一般继续执行条款的特定恢复例外：同一进程继续用捕获值，激活后恢复的纯计算
任务在值不同时失败。Submit 则依靠 T1 冻结的产物，不需要持久化旧规则。因此不构成要求重新裁决 DC10
的冲突。§5 的回滚一般句宜显式交叉引用该例外，且 B.2 的外部 effect 句宜明确 T1，见 RR-F3。
STORAGE_BREAKING 的 migration 仍是未来工作，当前方案没有授权绕过 MIGRATION_REQUIRED。

### 5.2 T1、回放、保护与 evidence-first

新增闭包的 consumer 明确：在 FULL 三侧/原始与规范表并存时，让 T1 和 prepare 选择同一个 MODIFIED
规范状态；manifest 则用于 commit 元数据及 Repository 结果绑定。不需要新增独立状态机。

设计已规定 ref/digest 进入 Attempt 和指纹，源包、闭包、表 artifact、manifest 的保护按闭包转移；
§10 还明确保护闭包 artifact 本身。既有新受理与重放的双指纹路径（C3）允许新字段在首次受理取自
PreviewResult、重放取自 Attempt，不重新获取当前 Preview 或重读 Repository。身份确认的请求部分
进入指纹，actor/time 是服务端事实，不能在重放时重新取时钟参与比较。实施应沿用这一既有模式，
不能把“先重放”解释成跳过授权（RR-F1）。

prepare 对冻结 parent 的只读 catalog 访问位于外部写 effect 前；包 checkpoint 成立后只复用同一包，
恢复不重新选择 parent。effect 后依据原请求和 Repository evidence 继续 reconcile/finalize，不能
因激活或重新上传而换包。§4.8 的不变声明、现行 checkpoint-first 路径和 §12 的 prepare/保护 owner
已提供文档级闭合；本轮不宣称恢复实测通过。

### 5.3 removed_tables 与 sibling

设冻结技术 parent 表集合为 P，上传规范集合为 U：DROP(P−U)，对 U 全量 DROP/CREATE 并写入目标行，
完成后恰为 U。现行 Repository replay 不把 SQL 的 DROP 目标限制为 manifest.tables，STRUCTURAL
核对的是最终 catalog，因此无需给已删除表增加 manifest entry，也不需要改 Repository API。

业务基线等于 main 的用户删表、sibling 增表、sibling 删表分别对应 U 缩小、P 多表、P 少表。
现有 SQL 执行及 STRUCTURAL 核心比较支持三者，本轮实验还覆盖 U 为空。CAS 继续绑定冻结 parent：
读取 catalog 后 main 再推进，应由原 expected-commit CAS 拒绝，而非重新生成包适配新 main。

Preview 比较业务基线，不能展示其后才出现在 main 的 sibling 增表；下一次完整状态提交删除这种表，
是 DC18 明确选择的行为。既有 sibling commit 不被改写，且新 commit 等于用户上传 U，没有发现未被
认识的新增数据损失。不可把 Preview 的业务基线当成 removed_tables 的 parent。

### 5.4 规范状态与 compare-excluded

Business Lifecycle §3 的比较对象仍是业务基线与上传状态，不是 main；附录 A.3 对此正确。
Canonical Storage §9 关于只修改 DROP_FROM_STORAGE 列不产生 effect 的要求仍成立：这些列不进入
规范表，schema/内容/行数均不变。新 schema 身份覆盖长度、类型、可空性、有序键，排除普通列序，
符合 DC13；与 manifest 同名摘要的衔接必须补 RR-F2。

只改 compare-excluded 列时，表的值比较状态 UNCHANGED 与规范内容已变是不同事实，可以共存：
无 MODIFIED 记录/行级风险，但展示表级内容变化，规范状态摘要不同，允许提交。
这不是逻辑矛盾，也不应要求 owner 改 DC4/DC16。实施不能沿用现有 surface changed_count 过滤后
让该事实消失；F8 的唯一角色 owner 应证明 Preview/Review 的可见结果，而非只断言底层 flag。

### 5.5 INITIAL、seed 与 incident

INITIAL 零用户表不要求 Repository main 永远为空。Business Lifecycle §1A.2 与 5D §6 把 scope
归属和 seed/迁移原子性放在 control DB，把 initial commit 真实性交给 provisioning；后续物化做
零表断言补充后者，不应在 schema migration 中增加 Repository 网络调用。
已经有 Submission 的 Repository 仍可引用其真实空 initial commit；种子业务数据经 Submit 进入，
不是禁止已有业务历史。DC6 规定的开发/测试重建与 S2b harness 调整足以处理本项目现状。
真实部署若使用非空 initial，应触发 DC17/DC6 重开条件，不能静默清空或伪造 initial。

附录 B.3 保留与 Backend 期望值矛盾的读回以及 CAS/结果歧义的 durable incident，同时把 catalog
行数与流实际行数不一致降为依赖异常。它没有放松 Operation Lifecycle §3“已经完成的 Dolt commit
不得由新上传替代”，也没有删除 Operation integrity 的 startup/DB 检查。属于范围收窄，非权威事实降级。

### 5.6 附录 A、B 可并入性

| 候选 | 对照结论 |
| --- | --- |
| A / Business Lifecycle | 当前 Semantic version 为 3.0.0，候选目标 3.1.0 正确；§1A.2 provisioning 定位句存在（89 行），§2 可选增强句存在（144–145 行）；§3–§6 插入位置存在。新增 INITIAL、XML required、身份、完整状态和摘要条款与正文方向一致。 |
| B.1 / Canonical Storage | 当前 3.0.0→3.1.0 正确；§2 替换原句存在（37 行），ignored 结构列段存在（50–52 行）；§7、§9 的 alignment/no-change 方向成立。缺 §4 摘要处置，见 RR-F2，因此本附录当前不能直接整体并入。 |
| B.2 / Ruleset | §1 捕获 snapshot 原句存在（20 行）；新增特定恢复例外可实施。§5 的一般句与 T1 措辞宜同步澄清，见 RR-F3。 |
| B.3 / ADR 0016、Operation Lifecycle | ADR Decision 的原句存在（28–29 行）；Contract §4 原句存在（60 行），§3 readback 条目存在（53 行）。保留历史 ADR、加范围澄清标注可行，不应机械删除全部 integrity 字样。 |
| B.4 / Taxonomy | §5 三个删除行及两个更新行均存在（397、400、401、422、423 行），owner/consumer 调整可执行。§4.4/§4.6 仍有同一旧 capability 的有效定义，见 RR-F3。 |
| B.5 / P5 | §2A.2 保留流程词汇句、§6.1 可选 XML 句、§2A.4 包根 adapter 行都存在。需保留候选/接受边界，不能把旧条款在 S0 前仍存在当作传播失败。 |
| B.6 / Architecture | §7.1 图、§7.2 第 2 项、§10 两个占位目录、§13 完成标准均存在。替换方向与目标 DAG 一致。 |

引文不是全部逐字节一致：A.2 的 XML 原句跨行且含 Markdown code span，B.1 的 ignored 段是带省略号的
定位摘句，B.3 的 ADR 原句也跨行。核查时保留原词、忽略排版换行/code-span 包裹后可定位；没有发现
不存在的插入位置或把另一版本文字误作原文。它们应作为编辑指令使用，不应作为字节精确替换脚本。
附录 A/B 是候选补充而非完整补丁，owner 并入时还须把旧断言与新增限定合并成一个有效规则。

## 6. 执行计划、路径和测试 owner

S1 的结构工作与语义变更已经分开：上传 admission 移入 Application，HTTP 保留流与 DTO；codec
合并移至 S2a，因此 S1 不必改变 checkpoint 载荷来达标。54 条 import 违例按原组逐条映射后，
预期只剩 http_arrow 的 private 与 capability-surface 两条、repository_import_artifact 的包根一条。
8 个环均有解除动作；16 个不可达模块中，删除 6 项（cache、两个 projection 占位、comparison provider、
snapshot cache、synthetic_w2），保留 4 个 composite/XML、3 个 external_target_sync，及改名后的
3 个 canonical-row-hash 模块。改名条目须在同 diff 解释。这里是计划的可兑现性判断，不是修复后运行证据。

S2a 尚有 R1 的中间状态可以接受：EP 第 114 行明确记录且阶段间不发布；S2a 的通过仅证明能力构件及
同一性，不证明 Preview 规范域语义。S2b 门槛要求这些构件已通过，S2b 才验收规范域链路。
不得把 S2a 中原始上传侧喂给新 comparison 的临时结果当作最终 golden 业务标准。

S2a/S2b 预算覆盖了原报告 F10 的全部指定漏项；扩展扫描得到 RR-F4。DC9 扫描还命中
History projection/queries 的 `HistoryIntegrityFailure`，它们表示历史事实/游标一致性，不是 hidden-summary
incident，不应因名称含 integrity 删除。S1 迁出 HTTP 用例后的路径要按实际落点更新，不能机械按旧文件名清理。

§12 新增测试文件为：test_canonical_snapshot_identity.py、test_canonical_state_identity.py、
test_comparison_canonical_domain.py、test_table_rules_comparison_view.py、test_comparison_rule_roles.py、
test_project_identity.py、test_comparison_replacement.py；执行计划 §3 均标为新增。
规范状态 identity 与 Submit no-change 的 owner 分别负责算法与业务受理，职责不重复；
Preview/History 恢复、HTTP 422 与事务 409、capability composite 与 Preview 接入属于不同边界。
N3 的唯一文件尚待指定（RR-F5），不能凭 ADR 的验证句声称所有不变量都已落到测试文件。

计划引用 AGENTS 并要求纯逻辑不用 Dolt、同构用例共享参数表；真实 Dolt 同一性和删表 owner 显式标为
integration。未新增按轮次命名测试或全故障点矩阵。涉及固定 Event/join/stream 时间预算时仍必须按
AGENTS 标 serial；计划没有给予豁免，也未要求对 backend 加 xdist。代码未实现，不能预判将来 marker
已经正确。

镜像规则符合 AGENTS：S1 进程组合、S2a migration/阶段退出、S2b harness/DTO、S3/S4 compose 旅程均在
阶段末重建，S5 fresh 最终候选；kickoff 只读普查不重建合理。停止条件绑定可复现的同一性、类型、
业务规则或部署变化，没有把已知 TEXT 主键问题继续悬置。S1“行为不变”仍须以其阶段证据兑现。

新增机制的 consumer 与理由均明确：RepositoryParentCatalogPort 服务 prepare 的完整状态删除，避免误用业务
基线；CommitCanonicalMetadataPort 服务 Preview/History 的 commit provenance，复用已长期保护的 manifest；
规范闭包替换已确认不可靠的选表启发式；身份确认服务误传识别、Review 审计和 Archive 处置。没有引入
独立 helper、历史规则库、恢复 sidecar 或新的跨进程安全域，规模符合比例化政策。输入数量/理由上限、
现有 archive/path 边界、冻结 Repository 与 CAS/事务仍须保留；DROP 表名继续使用 renderer 的标识符
引用规则，不能拼接 caller SQL。基础授权的例外不能由比例化推导，见 RR-F1。

## 7. 新 findings

### RR-F1：same-key 重放顺序把授权放到了返回结果之后

- **类别：已证实缺陷（文档）；阻塞：是。** 不声称当前代码已有越权漏洞。
- **位置：** D §7.6 第 460–472 行；ADR 0020 Decision 5 第 40 行；EP S4 第 182–183 行按该顺序验收。
- **依据：** D 写“same-key 重放（E，先于全部业务校验）”为第 1 项，scope 与权限为第 2 项。
  实际 `vnext/backend/src/gateway_backend/application/submission/accept.py:74` 先 permission/resolve，
  `vnext/backend/src/gateway_backend/application/submission/accept.py:150` 先 exact scope 和 Repository
  匹配才查 prior；`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:122`
  同样先 permission/resolve。比例化政策 §3 保留当前业务授权，Business Lifecycle §1A.3 第 116–117 行
  要求每次访问仍校验当前权限和业务引用。
- **触发场景：** 已成功受理后权限被撤销，或另一 scope 的请求持有旧 workspace/idempotency key；
  实现者照 r2 顺序先返回 prior result，后面的授权分支不会执行。
- **影响：** 把幂等性误当成授权豁免，可能泄露既有业务结果及操作身份。当前代码有屏障，风险来自计划删除/后移屏障。
- **最小修正：** 认证、当前权限及 exact scope/Repository 绑定先于重放结果返回；same-key 重放只先于
  可漂移的 workspace version、baseline/current-preview、no-change、身份确认和占用等新受理校验。
  不要求重放重新物化或重跑业务流程，也不应重新用当前事实计算冻结字段。
- **关闭标准：** 设计、ADR、计划一致写出该顺序，移除错误 E 标记；现有 Submit 事务/HTTP owner 明确
  验收“合法同 scope 重放绕过陈旧业务前置，但撤权或跨 scope 重放拒绝”。无需新权限机制或 owner 决议。

### RR-F2：规范 schema digest 与 manifest 同名摘要未建立明确关系

- **类别：已证实缺陷（定义/上游候选缺口）；阻塞：是。** 未声称两种摘要不能并存。
- **位置：** D §4.1 第 148–165 行、§5.1 第 322 行、附录 B.1 第 635–646 行；ADR 0018 Decision 1、
  ADR 0019 Decision 5；Canonical Storage §4 第 105–108 行。
- **依据：** 新定义是含表名、按列名排序定义、有序主键的 JCS 摘要，由 snapshot_materialization 拥有；
  accepted manifest 每表 schema digest 保持 DDL 列序，由 Storage Projection 拥有。
  `vnext/backend/src/gateway_backend/capabilities/storage_projection/_digest.py:80` 保留输入 columns 顺序；
  `vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py:243` 的输出在 284 行写入
  manifest.canonical_schema_digest。定向探针确认只换列序就改变现行 manifest 摘要。
  附录 B.1 只改 §2，并称列策略、键、canonical bytes 不变，未说明新旧同名值及 binding 的来源。
- **触发场景：** S2a 实现新摘要，S2b 从长期 manifest 读取 commit 存储身份；或者上传与已存 commit
  仅列序不同。不同实现者可能直接复用 manifest 字段、重新计算语义摘要，或直接覆盖旧字段。
- **影响：** 不能唯一决定 canonical_binding/提前退出/no-change 应消费哪种摘要；直接覆盖可能违反
  accepted manifest §4，直接复用旧值又违反 DC13。属于语义定义缺口，不是未实现测试本身。
- **最小修正：** 推荐保留 package/manifest 的物理 DDL 顺序摘要，给新列序无关摘要明确不同名称和
  使用位置，声明两个值不能互换，说明 commit 侧如何由实际 descriptor 得到语义值；同步附录中的 owner
  与关系说明。也可统一改 manifest 语义，但那必须提供 Canonical Storage §4 的替换候选及相应版本/摘要
  影响，不能仅在 §2 后追加描述。本报告不代替 owner 选择统一方案。
- **关闭标准：** 文档可无歧义回答“两个字段是否相同、各自由谁产生/消费、列序变化各自是否变、
  canonical_binding 使用哪个”；附录可直接落实该答案。既定 schema identity owner 覆盖列序互换及
  两生产路径的结果，manifest/package 的 STRUCTURAL 物理列序验证仍保留。

### RR-F3：候选传播的两个非阻塞澄清

- **类别：非阻塞建议；阻塞：否。** 当前特定条款足以解释恢复例外，不据此重开 F1。
- **位置：** D 附录 B.2 第 650–652 行、B.4；Ruleset §5 第 67–69 行；Taxonomy §4.4/§4.6。
- **依据与触发：** 只把 B.2 追加到 §1，读 §5 的人仍会看到“已捕获旧 snapshot 的 operation 继续使用
  原规则”；B.2 只提跨 effect 后冻结，而 D §4.8/DC11 从 T1 就冻结。仅删除 Taxonomy §5 的行后，
  §4.4 第 194 行 DAG 和 §4.6 第 266 行仍把 Comparison Projection 当有效 owner。
- **影响：** 接受后的导航可能继续引导实现者使用旧规则/不存在的 capability；没有发现新的执行机制需求。
- **最小修正与关闭标准：** §5 明确适用 §1 的纯计算恢复例外；B.2 写清 Submit 从 T1（含 effect 前）
  只消费冻结产物；Taxonomy 有效 DAG/artifact owner 加同一替代或取代标注。保留历史决策正文的地方用
  明确 superseded 标记，不要求全文改写历史。

### RR-F4：S2b 预算漏列 History 受理的 incident 调用方

- **类别：已证实缺陷；阻塞：否。** 设计删除意图已明确，可按普通路径预算修正，不扩大语义范围。
- **位置：** EP §3 S2b 第 296 行只列 history 的 compare_jobs/contracts/errors/ports；D §5.5 第 359 行。
- **依据：** `vnext/backend/src/gateway_backend/application/history/compare.py:137` 调用
  has_pending_integrity_for_commit，141 行抛 HistoryIntegrityUnresolved；该文件在 S2a 预算内，但
  S2a 没有删除 incident，S2b 删除 port 后它仍必须改。HTTP 旧编排也有 DTO 映射，S1 迁移后需按真实落点清理。
- **触发与影响：** S2b 只按列出的路径删除 port/error，受理调用方残留，类型检查或受理路径失败。
- **最小修正与关闭标准：** 把 application/history/compare.py 加入 S2b 必改，注明 S1 迁移后 DTO 映射
  的实际 owner；对被删符号做调用方扫描，区分仍应保留的 HistoryIntegrityFailure。

### RR-F5：N3 验收已有条款，但唯一测试 owner 未落文件

- **类别：非阻塞建议；阻塞：否。** 不把缺少新测试实现当作文档阻塞。
- **位置：** D §5.1、§12；ADR 0019 Required Verification；EP S2b 新 sqlite_commit_metadata adapter。
- **依据与触发：** §12 没有 CommitCanonicalMetadataPort 的 scope/Repository/digest 独立条目；
  Repository 单遍物化 owner 不能自动证明 control DB 元数据解析的跨 scope 屏障。
- **影响：** N3 实施必达可能只存在于 ADR 验证清单，或被多个流程复制证明。
- **最小修正与关闭标准：** 在 §12 指定一个 adapter/use-case 测试 owner（现有文件或明确新增均可），
  验收相同 commit 字符串跨 Repository 不串读、冻结 scope 不符拒绝、manifest digest 不符拒绝。
  调用链其他层保留接线 smoke，不复制矩阵；在 S2b 开工前落定。

## 8. 后续前置与 owner 事项

本轮结论不是通过；RR-F1/RR-F2 应先修订并复核。修订完成后仍保留原实施前置：

1. owner 单独提交接受 ADR 和上游候选；实现授权另行给出。5E slice exit pass 后才能合入并启动 S1。
2. S1 kickoff 对 exit 后源码复核漂移、运行架构基线并完成真实 dump 普查，按已决定的 DC12/DC15 条件落定类型处理。
3. S2a 真实 Repository/Dolt/HTTP Arrow 同一性通过；F8 事实形态冻结且用户可见；S2b 验收规范域、
   冻结闭包、same-key/CAS/恢复、删表三种情形、INITIAL 及 DC9 清理；F7 在 S2b 语义验收前关闭。
4. S3 经真实 Dolt 导入 composite，并证明 XML 变化与失败语义；S4 完成身份确认与 Archive 处置旅程。
5. 各阶段保留镜像决策与当前候选证据；S5 全量、五包静态、fresh 容器门禁及真实数据链路后，再交 P5 整体 exit。

无新增必须由 owner 重新裁决的业务问题。RR-F2 推荐区分物理 manifest 摘要与语义摘要，按既定 owner
职责修订即可；如果选择改变 manifest 既有语义，应在 S0 接受前由 Storage Projection/Contract owner
确认其候选及版本影响，本报告不自行决定。DC12/DC15/DC22 的确认时点仍按原决议，不提前替 owner 选择。

## 9. 报告交付检查

本报告的全部相对链接及其目标已检查；报告未使用片段锚点。全部反引号 vnext 路径在 worktree 存在，
legacy 路径在主工作区存在，带行号引用均未超出文件长度。上述检查只证明路径/引用可解析，不代替内容核查。
提交只包含本报告；不推送、不合并，不操作主工作区，不修改被复审文件或其他仓库文件。
