# P5 架构收口 S0 文档 r4 核对报告

- 状态：独立核对报告（docs-only）。本报告不接受 ADR、不修改 Contract 版本、不改变任何阶段状态，也不构成实现授权。
- 日期：2026-09-27
- 核对者：[r2 第二份复审](p5-arch-closure-s0-independent-rereview-2.md)与 [r3 第二份复审](p5-arch-closure-s0-independent-rereview-r3-2.md)
  的复审者，也是 DC23–DC27 的记录人；未参与 r1 起草、S0 审核或 r2–r4 修订。按[修订处置表](p5-arch-closure-s0-revision-disposition.md)
  §9.1，r4 可由未参与 r4 修订的 reviewer 只核对差异。
- 核对依据：[纵切指南](../guides/slice-design-execution-and-review-guide.md) §3–§6、`AGENTS.md`、
  [testing-conventions](../../../testing-conventions.md)、
  [比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)；关闭标准以两份 r3 复审报告
  （[第一份](p5-arch-closure-s0-independent-rereview-r3.md)、[第二份](p5-arch-closure-s0-independent-rereview-r3-2.md)）为准；
  DC1–DC27 以 [Owner 决议记录](p5-arch-closure-s0-owner-decisions.md) 为准，不重新裁决。处置表 §9 的自评只作线索。
- 结论：**通过**（文档核对）。无阻塞项；保留 §6 的实施前置条件、两项非阻塞建议与一项需 owner 知悉的事项。

## 1. 结论与理由

**通过。** r4 关闭了两份 r3 复审的全部 findings，没有引入新的阻塞问题：

- **存储规则事实**只含规则侧字段：key policy、`EXPLICIT` 策略下的显式键、ordered policy、structural 列与 dropped 列，明确排除
  retained 列与 `DDL_PRIMARY_KEY` 下取自源表的主键。§4.5 改为逐项归因，并给出与之对应的 `test_comparison_planning.py` 参数表。
  按这一定义重算 r3 复审的两个探针：同一规则下源表增列、回退规则表改主键，规则侧字段都不变，因此归为 `SOURCE_SCHEMA`。
- **manifest `canonical_schema_digest` 的消费方**在设计 §4.1、ADR 0018 与附录 B.1 中与源码一致：发布时的自洽核对、mutation
  planning 的 schema 变化判断、manifest digest。附录 B.1 并入后与 Canonical Storage §4 原文（92–94 行）及 §6.1 的包结构一致。
- **T1 保护转移**的表述与 Canonical Storage §5 和现行代码一致；**附录 B.4** 的依赖图与 B.6 同向；**身份确认理由**的校验归
  Submission 领域，不再从 Archive Application 导入。
- 两处顺带修改（附录 B.2 §5 写明“冻结值与运行期不同才失败”；DC26 下 `canonical_row_hash/contracts.py` 保持叶子）都准确，且与
  其他章节一致。

剩余两项非阻塞建议都是来源归因与测试说明的精度问题，可在 S2a 冻结对齐用例前处理（§5）。另有一项需要 owner 知悉：身份确认
理由沿用 Review 规则后，不能包含换行与制表符（§7）。

## 2. 核对对象

```yaml
docs_branch: p5-arch-closure-docs
docs_worktree: /home/dev/gdds-p5-arch-closure-docs
checked_commit: 2f38b301a607926d6df64cdd7d4991c2ea34c48f   # r4；核对开始时的 HEAD，核对期间未变
diff_base: 46a4e03ae5        # r3 第二份复审报告；ffba1138ef 之后只新增了两份 r3 复审报告
code_inspection_base: 217236980350d523101936af5464fbbd9ad66f88
vnext_diff_check: "git diff --stat 2172369803 2f38b301a6 -- vnext" 输出为空
r4_diff: "git diff --stat 46a4e03ae5 2f38b301a6" 为 9 个文件，+136 / -62
main_workspace_usage: 未使用（本轮只读 worktree 源码）
```

被核对的 r4 差异：[详细设计](p5-arch-closure-design.md)（含附录 A、B）、[执行计划](p5-arch-closure-execution-plan.md)、
[Entry Brief](p5-arch-closure-s0-entry-brief.md)、ADR [0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、
[0019](../adr/0019-commit-canonical-metadata-authority.md)、[0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
[P5 §2A.4.1](p5-business-vertical-slices-design.md#p5-architecture-review-20260925)、[formal README](../README.md)、
[修订处置表](p5-arch-closure-s0-revision-disposition.md) §9。ADR 0021 与决议记录在 r4 中未改动。

行号约定：以 `vnext/` 开头的路径相对仓库根目录，行号以 `2172369803` 为准；文档行号以 `2f38b301a6` 为准。沿用处置表 §9 的编号：
RW1- 指 r3 第一份复审，RW2- 指 r3 第二份复审（其 RR3- 编号）。

## 3. 核查与局限

### 3.1 核查

| # | 核查 | 结果 |
| --- | --- | --- |
| R4E1 | 基线：HEAD、`vnext/` 差异、r4 差异统计、并行提交 | 与 §2 一致；核对期间分支上没有其他提交 |
| R4E2 | 存储规则事实：以 `vnext/backend/src/gateway_backend/capabilities/storage_projection/view.py:33-46`、`78-86` 核对 r4 的字段划分，并以 r3 复审 R3E4 的两个探针结果重算 | 规则侧字段（dropped、structural、key policy、ordered policy、`EXPLICIT` 显式键）都来自规则记录；retained 与 DDL 主键来自源 descriptor。两个探针在规则侧字段上均无差异，按 §4.5 归为 `SOURCE_SCHEMA` |
| R4E3 | manifest 摘要消费方与既有测试 | 消费方与 r3 复审 R3E5 一致。既有测试覆盖 ENUM 标签顺序、可空性、drop/restore 对该摘要的影响（`vnext/backend/tests/test_storage_projection_integrity.py:527-574`、`579-608`）与 mutation planning 的 schema 变化用例（`vnext/backend/tests/test_mutation_planning.py:289`），但没有列序互换的断言（RR4-N2） |
| R4E4 | Review 理由规则 | `vnext/backend/src/gateway_backend/domain/submission/review.py:290-304`、`326-343`：拒绝 C0 控制字符（含 `\t`、`\n`、`\r`）、DEL 与 C1、代理码点、非字符码点，要求 1–4096 UTF-8 字节且至少一个非空白字符；`InvalidReviewReason` 映射为 `422 REQUEST_VALIDATION_FAILED`（`vnext/backend/src/gateway_backend/http/errors.py:339-344`）。与 r4 的描述一致 |
| R4E5 | T1 保护转移 | 现行 T1 在转移后清除 `current-preview` 与 `preview-operation` 的保护（`vnext/backend/src/gateway_backend/application/submission/accept_transaction.py:321-335`），与 r4 §4.8 一致 |
| R4E6 | 路径预算回归：r3 复审 R3E3 的普查脚本对 r4 执行计划重跑 | S2a、S2b 删除的符号，使用方仍全部落在对应阶段预算内 |
| R4E7 | 链接与锚点：r4 改动的 9 个文件 | 0 个问题；r4 新引用的源码路径均存在 |

### 3.2 局限

- 只核对 r4 差异，并对 r1–r3 的关闭依据做回归抽查，没有重新完成之前各轮的全部核查。
- 没有运行新的 Python 或 Dolt 实验；R4E2 的探针结果沿用 r3 复审在同一代码基线上的实测，本轮按新定义重新判读。
- 没有真实 dump，没有构建镜像，没有跑全量测试。

### 3.3 镜像决策记录（testing-conventions“每轮评审记录”）

```text
Current HEAD: 2f38b301a6（被核对文档）；本报告提交后为只含本报告的新提交
Container rebuild required: no
Reason: docs-only 独立核对；未触碰 image/deployment/container 边界；只读核查 worktree 源码
Last verified image revision: none（本轮）
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: 无；各阶段门禁按执行计划 §6
Required execution point: 不适用
```

## 4. 两份 r3 复审的关闭情况

| 编号 | 判定 | 依据（r4 行号） | 说明 |
| --- | --- | --- | --- |
| RW2-F1、RW1-F1 | 已关闭 | 设计 §4.1（157–159）、§4.5（281–286）、§12（615）、附录 A 第 6 项（682）；ADR 0018 Context、Decision 3（50）、Alternatives（75）、Required Verification（91）；ADR 0019 Decision 1（38）；执行计划 S2a 第 4 项与验收 | 字段划分与源码一致（R4E2）；各处传播一致；参数表覆盖源表增列与改 DDL 主键、规则改 dropped 列或显式键、两者同时发生、只有列序不同。RW1-F1 的关闭标准（来源标签与实际原因一致、D/ADR/EP 同步）同时满足。派生差异的归属见 RR4-N1 |
| RW2-F2 | 已关闭 | 设计 §4.1 对照表（177）、§12（610）、附录 B.1（700）；ADR 0018 Alternatives（74） | 三处的消费方表述与源码一致；B.1 并入后与 Canonical Storage §4 第 92–94 行、§6.1 不矛盾。§12 的测试说明见 RR4-N2 |
| RW2-N1 | 已关闭 | 设计 §4.8（326）、§10（578） | 与 Canonical Storage §5 第 128 行及现行 T1 一致（R4E5） |
| RW2-N2 | 已关闭 | 附录 B.4（732–740） | 与 B.6 及设计 §3 同向；`table_rules -> snapshot` 与现行 capability DAG 中 snapshot_materialization 的上游一致（`vnext/backend/tests/test_architecture.py:65-67`） |
| RW2-N3 | 已关闭 | 设计 §7.6（498）；ADR 0020 Decision 5（42）；执行计划 S4 验收（199）与 §3 S4（369） | 校验归 Submission 领域，HTTP 层沿用 `BoundedDiagnosticReason`，领域层沿用 Review 规则并在 S4 提取为共享校验；不从 Archive 导入。规则比 r3 严格，见 §7 |
| RW1 §4 附带意见（B.2 §5 的条件） | 已关闭 | 附录 B.2（718） | “运行期 ruleset 与冻结值不同则稳定失败，相同则照常继续”，与 §1 候选句一致 |
| RW2 §6 附带意见（DC26 下 contracts 叶子） | 已关闭 | 设计 §9 A6 行（546） | 与 P5 §2A.2“只 import contract 不应加载重型执行依赖”一致 |

回归抽查：r3 复审确认已关闭的各项（受理判定顺序、Ruleset §1/§5 候选、`CommitCanonicalMetadataPort` 的 owner 与 DC25、DC26 的
S1 验收、路径预算、附录插入点）在 r4 中未被改动或削弱；DC1–DC27 未被改变。

## 5. 新 findings（均为非阻塞）

| ID | 类别 | 阻塞 | 标题 |
| --- | --- | --- | --- |
| RR4-N1 | 非阻塞建议 | 否（S2a 冻结对齐用例前） | 规则变化派生的可空性差异，按字面清单会被归为 `SOURCE_SCHEMA` |
| RR4-N2 | 非阻塞建议 | 否（S2a） | §12 称既有测试证明 manifest 摘要保持 DDL 列序，实际没有列序互换的断言 |

### RR4-N1 规则变化派生的可空性差异，按字面清单会被归为 `SOURCE_SCHEMA`

- **位置**：设计 §4.5（282–284 行）、§12（615 行）。
- **依据**：
  - 设计 §4.2 规定键列在 import DDL 中一律 NOT NULL，其余列沿用投影结果。所以当规则把显式键由 `(a)` 改为 `(b)` 时，除了主键变化，
    还会出现两项可空性变化：`b` 变为 NOT NULL，`a` 恢复为源列的可空性。
  - §4.5 第一条把“可以由规则事实的差异解释的差异”归为 `STORAGE_PROJECTION_POLICY`，但列举时只写了“键变化”。第二条把“可空性”
    列在 `SOURCE_SCHEMA` 下。按字面实现，这类规则变更会被标为 `BOTH`。
- **影响**：只影响来源标签，不影响对齐、比较结果或写入。
- **建议**：§4.5 第一条补一句：“规则事实变化派生的差异（例如显式键变化使新旧键列的可空性随之改变）同样归
  `STORAGE_PROJECTION_POLICY`”；`test_comparison_planning.py` 的参数表加这一行。

### RR4-N2 §12 称既有测试证明 manifest 摘要保持 DDL 列序，实际没有列序互换的断言

- **位置**：设计 §12（610 行）。
- **依据**：r4 写道，manifest `canonical_schema_digest`“保持 DDL 列序、发布自洽核对与 mutation planning 用法仍由既有
  storage_projection 与 mutation_planning 测试证明”。既有测试覆盖了 ENUM 标签顺序、可空性、drop/restore 与 mutation planning
  的 schema 变化用例，但没有“只交换列序时该摘要改变”的断言（R4E3）。
- **影响**：两个摘要的区别（列序是否计入）是本轮设计的核心说明之一，却只有 business schema digest 一侧有测试证明。
- **建议**：在 `test_canonical_state_identity.py` 的列序互换行同时断言 manifest 摘要改变而 business schema digest 不变，并相应
  改写 §12 的说法。

## 6. 保留的实施前置条件

通过不代表实施验收。以下条件继续有效：

1. owner 按 Entry Brief §5 以单独的 docs 提交接受 ADR 0018–0021 与附录 A、B 的候选，并完成取代标注。实现授权另行给出，最早在
   P5-5E slice exit 之后；本分支在 5E slice exit 后合入主线，S1 kickoff 复核主线相对代码基线的变化。
2. S1 kickoff 用 4 份真实 dump 完成普查，按 DC12、DC15 落定类型处置；若 DC12 触发，按 DC27 在 S2a handoff 中写明版本轴。
3. S2a：真实 Dolt 同一性 owner 通过（S2b 的门槛）；F8 的事实形态与 legacy oracle 核对后冻结；RR4-N1、RR4-N2 在冻结对齐与
   状态身份用例前处理。
4. S2b：F7 的真实数据链路、`CommitCanonicalMetadataPort` 的键与 scope、删表三种情形的真实 Repository 验证、T1 冻结与保护、
   INITIAL 断言通过。
5. S3 经真实 Dolt 导入 composite；S4 完成身份确认、Archive 处置与 FULL 混合模式旅程；各阶段记录镜像决策，S5 fresh 构建最终候选。

## 7. 需要 owner 知悉或确认的事项

| # | 事项 | 说明与建议 | 确认时点 |
| --- | --- | --- | --- |
| O6 | 身份确认理由不能包含换行与制表符 | r4 让身份确认理由沿用 Review 规则。该规则拒绝全部 C0 控制字符，其中包括 `\n`、`\r`、`\t`（R4E4），所以理由只能是单行文本；而 Archive 的身份异常处置理由按 Archive 规则只限字节数，可以多行。若身份确认需要多行说明，应在 S4 提取共享校验时明确放行换行，并确认 Review 是否同样放行；若单行即可，维持 r4 即可。这是用户可见的输入规则，不影响本轮通过 | S4 开工前 |

除此之外，没有需要 owner 新作出的决议。

## 8. 链接与路径检查

提交前用脚本检查了本报告：

- 全部相对链接与锚点都能解析；
- 反引号中以 `vnext/` 开头的路径在 worktree 中都存在，带行号的引用不超出文件长度；
- 只写文件名的测试文件中，`test_comparison_planning.py` 已存在，`test_canonical_state_identity.py` 是执行计划标为新增的文件。
