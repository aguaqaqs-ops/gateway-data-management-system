# P6→P7 文档整理 A 独立审核

日期：2026-11-10。结论：**A_SCOPE_GO**。核准下述精确归档及可写范围；A-N1 修订与 A-V1 补充处置均由原审核收，未关闭 finding 为零。A 静态验证回执已核；A-V1 的原文件身份缺失限制继续保留。B 尚未归档，C/本地合入尚未验收。

## 1. 固定对象与审核方式

| 对象 | 固定值 |
| --- | --- |
| main / 来源 S | `5ddd73b962e2432f961a46f6743395a53a388435` |
| 任务输入 I | `2204f039a51046563b51fe82a3f978c2e981f259` |
| 初审候选 | `4a43fe0b53c02bd4b24c1e0cd15ca4c280e22508` |
| 复审核准候选 A | `322fa28b2c5dbc1c18008b2d7a43db8533c34f04` |
| S1a 只读来源 | `24394b98a6e6f9bea89c404b44cf0dde691a8044`，19 个相对 S 的文档变更；03:23:49Z 仍 clean |
| 核查结束时的 main | `320ed655c9b8f77ca29d84ce4c29f07eb852d316`，clean；S..该提交仅新增 FE3c evidence-check-1，无本任务路径/候选依赖重叠。B/C 合入前仍须重核届时增量 |
| 原审 worktree | `/home/dev/gdds-reviews/p6-p7-doc-cleanup-a-4a43fe0b53`、`/home/dev/gdds-reviews/p6-p7-doc-cleanup-a-322fa28b2c`，均为 clean detached 候选 |

完整读取本任务提示词、执行方案、实际 AGENTS/testing-conventions、比例化政策、三层 README、P3→P4 cleanup handoff/manifest，以及三份候选原件和承接其结论的原审/最终交接。产品源码仅作调用点静态阅读；未 import 产品、运行测试/lint/编译/Compose/真实旅程或连接测试节点。

S..A 差异恰为本任务 prompt、execution-plan、coordination 三文档新增；`git diff --check` 通过，产品、Contract、测试输入、AGENTS、testing-conventions、S1a/FE 及部署文件均无本任务差异。I 两份输入与原工作区相应未提交原件逐字一致。S 是 main 和 A 的祖先，原归档来源保持可达。

## 2. 独立核准的范围

拟移除文件均在 `docs/backend-vnext/refactoring/formal/plans/`。以下三项判为 **ARCHIVE**，合计 9,139 字节；不因零命中或文件年代单独准入。

| 原文件名 | 独立判断与必须保留的承接 |
| --- | --- |
| `p4-r2-s6-remediation-appendix.md` | 两 finding 的中间修复处置；完整闭合、限制和重开条件已由 `p4-r2-s6-independent-review.md` §8 与最终 `p4-r2-durable-store-atomic-transition-handoff.md` 承接。两者保留。 |
| `p4-r2-s6-remediation-handoff.md` | 下一步仍为独立 rerun 的中间交接；最终 R2 handoff 保留同一 validated source、原结果、限制与退出边界，原 S6 独审亦保留。 |
| `p5-5b-s6-remediation-round4-handoff.md` | RR12 的中间修复轮；round5 handoff、S6 最终 `p5-5b-s6-independent-review-5.md` 与 S8 最终 handoff 保留原闭合及容器 skip/defer，不将中间候选改写为最终通过。 |

三项的 S 原字节、blob、SHA256 和 A 当前字节已逐项独立比较，均与[协调记录 §2](p6-p7-documentation-cleanup-coordination.md#2-a-提议的精确归档集合)一致；长度分别为 3,524、3,125、2,490 字节。B 删除前须以清单逐行登记完整来源和恢复元数据，按 `git show <完整来源提交>:<原路径>` 读取；本审核不声称 A 已删除或 B 已完成恢复验收。

核准的普通导航写入仅为 `docs/backend-vnext/README.md`、`docs/backend-vnext/refactoring/README.md`、`docs/backend-vnext/refactoring/formal/README.md` 与新 `docs/backend-vnext/refactoring/formal/plans/current-context-index.md`。用途是修正当前入口、文档角色和受本次归档影响的导航；不重写产品规则、历史报告或 S1a 状态。没有依据增加其他普通导航白名单。

本任务记录可写范围限协调记录 §4 明列的方案/提示词、单份协调记录/manifest、A/B/C 原审报告与最终 handoff。三项以外的历史材料均继续保留或 DEFER；新增候选/普通导航必须先补消费者依据并交适用原审，不能按本结论扩大删除集合。S1a、共享规则、Contract/ADR、总纲/实施阶段规划、FE、产品与外置证据/资源继续禁动。

## 3. 消费者与语义依据

已分别核当前导航/Contract/决议/S1a、真实代码/闭包/构建消费者，以及历史引用。S 与固定 S1a 中三候选全名/stem 的候选外逐字入站为零；本任务元数据中的恢复文字不算活跃文件依赖。保留报告中的 `p5-5b-s6-*.md` 为历史 allowed-path 范围，round5 的 carried-from-round4 为历史轮次描述，R2 Git input commit 仍可达；未将这些说成“全历史零引用”。无需改冻结原审以消除新断链。

独立用 S1a Git 对象重建按文件名引用的保守传递图：19 seeds、655 reached，与实施快照逐项一致，三候选均不可达。该图包含 basename 重名带来的过量保留，不替代动态消费者判断。另读源码读取/glob 调用点，部署 runbook glob 只在 `vnext/deploy/**`/RS README，Docker context 为 `vnext/`；未发现三候选的动态读取路径。

以下真实消费者和依据必须保留：P2 feasibility 文档被 `test_input_closure.py` 列入并由 methodology 测试实读；legacy oracle 动态加载 legacy 模块；两份 benchmark 与 SQL census 测试读取 P5 census；fixture `batch-boundaries.json` 固定引用 `p6-s4-c-review.md`；capability Authority docstring 仍指 P3 handoff。P6 原始成功/失败、有效 Owner 决议、阶段最终原审/handoff 与 S1a 的 P6-S6 模型来源亦保留。零逐字入站的 P5 最终 sign-off 未被误归档。

S1a 的目标 Contract 尚待实现，不可作为当前已生效行为。本任务当前入口须区分 main 的通用规则入口与 S1a 本轮用户旧节点/DC68 输入限定，保留其固定来源，不以导航覆盖授权。S1a 继续推进时，B/C 只复核受影响的候选；未知用途先保留，不等待或接管其 exit。

## 4. 固定静态核查稿与证据

以下稿已发协调者及 A 验证者，固定 C=A；其 S/I、三原件身份及外置查询 spec 不得因失败改预期：

1. 在验证者自己的 clean detached C 记录身份/UTC/HEAD，核 S..C 仅三任务文档新增及 `git diff --check`。
2. 逐个读取三项 S 原件，核 source/blob/SHA256/长度、C 字节相同，以及 S 对 main/C 的可达性；不删除或恢复覆盖活跃路径。
3. 重算 S/I 的 docs、plans blob 数/字节与 M24；五查询使用 `five-query-spec-and-baseline.json` 固定 regex/path 数组，去首 revision 后保留原字节/换行，核 I 的 exit/文件/行/字节/SHA 及原输出，再记 C 同口径结果。
4. 核三 README 相对链接路径基线、三新增文档的链接/锚点和候选入站引用；区分历史 glob、Git 对象与活跃路径依赖，不借机扩大修订。
5. 只读核上述 P2/legacy/P5 census/fixture 的实际调用点仍存在；不执行消费者，也不由验证角色判断可删范围。
6. 记录 main/S1a 现场身份；S1a 偏离固定来源时保留增量交原审，不自行重定范围。输出放 worktree 外，记录起止候选、exit 与 SHA256。

原审已独立重算 `statistics.json` 的 S/I 全部值，以及五项 I 查询的计数、SHA256 和原输出字节，全部一致。三 README 链接路径基线没有缺失；该基线不宣称全部既有锚点有效，B/C 须核修改页全部新/保留锚点。M24 三候选均不含命中，不预期由删除它们获得明显下降；文件/字节统计不是模型性能实测。

A 验证回执为 `/home/dev/gdds-p6-p7-documentation-cleanup-evidence/A-candidate-check.txt`，SHA256 `4d1b43a5979e9fbc529cea83c888365dea6cfa486a5ff62d272b7282a35ecd98`，原审已读取相关原始命令/修正/结束记录并重算日志摘要。记录 `heavy-dev-01`、03:25:08Z 起与 03:35:00Z 最终复核、起止 C、clean detached、逐命令 exit；三原件/固定查询/链接路径与消费者检查符合上述稿，三 README 221 个相对链接路径无缺失，C 新增四个相对链接有效且无 fragment。S1a 仍为固定 clean 来源，main 增量已单列。实施盘点资料目录为 `/home/dev/gdds-test-tmp/docs-cleanup-a-impl-20261110/`，完整索引见协调记录 §6。

验证者第 3 项误将两份规范化 M24 重算文本写回上述实施输入目录的 `M24-5ddd73b962.txt`、`M24-2204f039a5.txt`，写前未保存 SHA/mtime，因而不能证明原文本或元数据未变。不得补造写前身份、回写“恢复”或称原件未变；仅这两份派生输出受影响，固定 S/I/C、statistics JSON、五查询 spec 及其 q1–q5 原输出未受该覆盖影响。原审在覆盖前已独立重算 Git 统计，但未核两份实施 M24 文本的原 SHA。出错的是未持久化的 inline Python，具体误写语句和路径已在回执保留，不能声称另有原脚本文件。验证者随后只向本人目录重算；原审逐字比较新副本与固定 Git 规范化输出，均相等，补充动作已核收。其可复算性不追认被覆盖文件的原始身份。

| 新重算副本（同在 `/home/dev/gdds-p6-p7-documentation-cleanup-evidence/`） | 字节 / SHA256 |
| --- | --- |
| `M24-5ddd73b962.txt` | 205,846 / `68d42767ce3aa1a3cf989dbdcbadf267b730576f39c8bbc3fb46146ad0908fe9` |
| `M24-2204f039a5.txt` | 206,085 / `23490f90ea92da74707b91332d6cf0d7095431d7ac00ca2dbe4017a79e95bd5f` |

回执还保留第 2 项早期 S/I 记录标签误用、匹配误收恢复示例的两项只读 logger 错误。其后按 revision 独立记录并只匹配 `| ARCHIVE` 行，重做三候选检查，原件/身份/唯一表行均相符；原审已复核修正，不把原 false 或模糊标签改写为通过。没有扩大核查范围、改候选/预期或运行产品。

## 5. Finding 与限制

| ID | 处置 |
| --- | --- |
| A-N1，普通分类一致性 | 4a43fe0b53 中 round5 handoff 同列 KEEP_EVIDENCE 与 DEFER；322fa28b2c 仅修两行，将其唯一化为 KEEP_EVIDENCE 并保留后续归档评估延期。原审在新 detached 候选确认，**closed**。 |
| A-V1，验证派生输出误写 | 两份 M24 文本的写前身份未知；覆盖事实和来源限制保留，固定 Git 新副本及日志 SHA 已由原审核收，**补充处置 closed**，不伪称原件未变。候选/产品与归档集合不受影响。 |

当前审核 HEAD 为 A。无需容器重建：仅文档盘点，Docker context/产品输入未改；本轮最后验证的 image revision/source-tree 未检查，current container gate 为 `not-applicable`，无 carried 或产品通过声明，无需为本任务安排产品门禁。P6 tag/历史证据只作保留来源，不因此签署 P7、FE、SDK 或 production；本报告也不证明资源已释放、本地合入或 S1a 已验收。
