# P6→P7 文档与检索整理交接

日期：2026-11-10。状态：**C 实施候选，A_SCOPE_GO 与 B_GO 已核收；C 独审/独立静态验证、cleanup 合入 main 及合入后核收尚待完成**。本文不自签 GO，不作为产品、S1a exit 或容器通过声明。

## 1. 固定对象与实际交付

| 对象 | 固定身份 / 状态 |
| --- | --- |
| 来源 S | `5ddd73b962e2432f961a46f6743395a53a388435`；三归档原件的统一来源 |
| 任务输入 I | `2204f039a51046563b51fe82a3f978c2e981f259`；仅方案/提示词 |
| A 核准记录 | `497fedfce56f1c183e6f638f7b7ec949fa44d859`；[A 原审](p6-p7-documentation-cleanup-a-review.md) A_SCOPE_GO |
| B 实施 / 核收 | `1d84b7a0669a4bf7da5f833304436447bbc38e2a`；[B 原审](p6-p7-documentation-cleanup-b-review.md) B_GO，报告收录于 `bb4dd10e5dc3e8ab0565066ca4749859dd288433` |
| 最新 main M | `00ca325c2ed6d705abfa39e9528ef148e6029cfc`，2026-11-10 04:06Z 核 clean；已合入 S1a A |
| C 同步起点 | `2b99722bd837f901da7058001cf204b53a4b5fe9`；协调者将 M 无冲突合入 cleanup 工作分支，cleanup 尚未合 main |
| C 固定审核候选 / 结论 | 待协调者提交后固定、待 C 原审及验证者实际核收 |
| 最终 cleanup 合入 / 增量核收 | 待完成，不能用本任务分支同步提交代替 |

当前入口为 [Current Context Index](current-context-index.md)，由 [backend README](../../../README.md)、[refactoring README](../../README.md) 和 [formal README](../README.md) 导入。入口指向 owning Contract、实际源码、P6 固定退出与 S1a A 已合入设计；不复制规则、不把待实现目标写成源码现状。归档共三份已关闭中间记录，原件不改写，未创建第二套 archive 树、产品 exit tag 或全局忽略规则。

本任务与并行变化分别核：`S..bb4dd10e5d` 为 A–B 整理；`S..M` 是他人 31 FE 和 20 S1a 路径；`M..C候选` 是本任务对最新 main 的净差异。B 已核的本任务范围为三 README、新 index、三删除及 cleanup 元数据；C 只在该导航白名单最小同步 S1a 最新状态并写本任务交接/协调。产品、测试、依赖、部署、AGENTS/testing-conventions、政策/ADR、Contract、S1a 和 FE 的本任务净差异应为零；C 固定核查与最终 merge 仍须实际复核这一条件。

## 2. 归档清单与恢复

[TSV manifest](p6-p7-documentation-cleanup-manifest.tsv)逐行给 action、完整原路径/source_commit/blob/SHA256/字节、理由、owner/保留承接和依赖处置。以下原路径均在 `docs/backend-vnext/refactoring/formal/plans/`，统一 source_commit 为完整 S。

| 原文件名 | 字节 | 保留承接 / owner |
| --- | ---: | --- |
| `p4-r2-s6-remediation-appendix.md` | 3,524 | [R2 S6 独审 §8](p4-r2-s6-independent-review.md#8-independent-remediation-rerun)与 [R2 最终 handoff](p4-r2-durable-store-atomic-transition-handoff.md)；operation runtime owner |
| `p4-r2-s6-remediation-handoff.md` | 3,125 | 同上，保留 validated source、原结果、限制与后续阶段边界；operation runtime owner |
| `p5-5b-s6-remediation-round4-handoff.md` | 2,490 | [round5 handoff](p5-5b-s6-remediation-round5-handoff.md)、[S6 最终独审](p5-5b-s6-independent-review-5.md)、[S8 handoff](p5-5b-s8-handoff.md)；P5 Delivery owner |

三项合计 **9,139 字节**。依据是完整闭合/限制已有保留承接，三类消费者核对无活跃依赖，S1a 保守传递依赖与实际调用点均已核；不能以年代或零逐字入站单独推导可删。保留历史 allowed-path glob、round5 的 carried-from-round4 与 R2 Git 输入对象，不声称历史零引用。

恢复只输出到本人临时目录，并按 manifest 比对 SHA256；不要覆盖活跃树，例如：

```bash
git show 5ddd73b962e2432f961a46f6743395a53a388435:docs/backend-vnext/refactoring/formal/plans/p4-r2-s6-remediation-appendix.md > /本人临时目录/p4-r2-s6-remediation-appendix.md
```

另外两项按清单完整路径读取；原相对链接按来源提交解释。B 原审/验证及 C 实施准备已逐一读取全部来源核 blob/SHA/长度；C 最终独审/验证仍须在固定候选独立复核。S 对 M 和 C 同步起点均可达，最终合入结果还须复核来源可达性。纠正误归档时核无同名并行新文件后正常新增恢复提交，不重写已引用提交/tag。

## 3. 静态核查与检索口径

本任务按[执行方案](p6-p7-documentation-cleanup-execution-plan.md)仅在开发主机做文档/Git 静态核查，不 import 产品、不跑产品 runner/pytest、lint/mypy、编译、Compose、benchmark 或真实旅程，不连接/占用测试节点。S1a 自身 06 文档核收原件由其原审负责，本任务仅读取其签署。

B 已核：manifest 恰三行与删除集合一致、全部原件恢复成立、四导航 111 个相对链接（含 10 个 fragment）以及协调记录五链接全部有效；`git diff --check S..B` 与精确白名单通过。C 新增链接/最终整体差异、固定统计及最新并行输入待独审核收，不能把工作树自检称作最终固定候选验证。

| 同口径 revision | docs 文件 / blob 字节 | plans 文件 / blob 字节 | M24 文件 / 行 / 规范化字节 |
| --- | --- | --- | --- |
| S | 701 / 15,379,368 | 517 / 10,962,626 | 72 / 343 / 205,846 |
| I | 703 / 15,406,793 | 519 / 10,990,051 | 73 / 344 / 206,085 |
| B | 704 / 15,413,368 | 520 / 11,022,705 | 75 / 354 / 210,802 |

B 毛归档 −9,139 字节；三 README 压缩 26,079 字节；新 index +8,697，四份任务输入/记录及 manifest 合计 +60,521，相对 S 的 docs 净量 +34,000 字节。B 报告及后续 C/handoff、他人 main 增量均不在该 B 数中；不能冒称最终净收益。固定五问题分别是当前阶段、存储/保护 owner、节点/失败/角色来源、历史恢复、P2/legacy 等实际消费者；I/B 各项文件/行/字节及语义核收见 B 原审 §3。C 仍按 A 固定 spec 的原 regex/path 数组只替换 revision，新增 main 变化与 cleanup 净量分列。文件/命中/字节不是模型时延、正确率、token 或全量搜索收益实测。

## 4. 审核与外置原件索引

| 来源 | 位置 / 身份 |
| --- | --- |
| A 实施 / spec | `/home/dev/gdds-test-tmp/docs-cleanup-a-impl-20261110/`；`five-query-spec-and-baseline.json` SHA256 `17ff3acc740505ab0e922729457416a97fdeeb008649c8db5b5343b13255a69f` |
| A 静态回执 | `/home/dev/gdds-p6-p7-documentation-cleanup-evidence/A-candidate-check.txt`；SHA256 `4d1b43a5979e9fbc529cea83c888365dea6cfa486a5ff62d272b7282a35ecd98` |
| B 实施 | `/home/dev/gdds-test-tmp/docs-cleanup-b-impl-20261110/`；工作树预检不充固定候选统计 |
| B 独审原件 | `/home/dev/gdds-test-tmp/docs-cleanup-b-review-20261110-1d84b7a066/`；`review-static.json` SHA256 `c4b0d0f449fce9184cb9f5e938e3fdff50613a1539db41cd202b958a3d559e48` |
| B 静态回执 | `/home/dev/gdds-p7-doc-cleanup-b-verify-20261110/verification-receipt.txt`；SHA256 `440d6d885beacc6267115c3ad004d817222c718c995dd2f543c94e5fbd2a38ce` |
| C 实施准备 | `/home/dev/gdds-test-tmp/docs-cleanup-c-impl-20261110/static-preparation.json`；SHA256 `8e25e0dce8143f7a00fd0be49fe65694d61de9b7f9cf018e961a970a6c2d3eb2`；同目录三恢复副本 |
| C 工作树自检 | 同 C 实施目录 `working-check.py` / `working-check.json`；JSON SHA256 `823846cf30b6ab679a011af3e1ba723f9207893515d336e8259e865a11d6802c`；四导航 121、六修改页 143 链接/14 fragment 有效，六路径白名单/净禁动差异/`diff --check` 通过；不代固定候选核查 |
| C 原审 / 独立回执 | 待固定候选后实际补记，不预造路径/摘要或 GO |

上述 A/B 状态及限制由仓库内原审报告承接，原件目录只读。A-V1 的两份派生 M24 文本曾被验证误写，写前身份未知；新固定 Git 副本可复算不追认旧身份。B 验证自有 README basename 覆盖、统计 dict 比较错误、窄 grep、旧结束段格式，以及 B 实施无命中 grep logger 预期错误，均按 B 原审/协调记录保留原失败和修正，不补造旧 SHA/实时日志，不改预期掩盖失败，也不称产品 DC68 恢复。C 实施准备为会话 inline Python 静态输出，无另存脚本或实时总日志声明。

## 5. 保留、延期与 S1a 并行边界

必须保留的实际消费者包括 P2 feasibility 的 RS 闭包/methodology、legacy 动态 oracle/P3 Authority、P5 census 的两 benchmark/测试、fixture JSON 指向 P6-S4 C review，以及 P6 全部成功/失败、有效决议、最终原审/handoff 和 S1a 的 P6-S6 模型来源。具体调用点和分类见[协调记录 §3](p6-p7-documentation-cleanup-coordination.md#3-保留与延期)。其他未经逐文件核清的长过程记录继续 DEFER，由各原 owner 后续定向评估；总纲/实施阶段规划、FE stale 同步和 S1a 目标语义均由原 owner 负责，不是本轮“清空”指标。

S1a A 原审签署 `/home/dev/gdds-p7-s1a-reviews/a/355c54a0-a-go.md` 的 SHA256 为 `3d22ae5e4b11143e505bfb7de3cc4b06c7f226a2cee6009639580f7a2f9ddfbb`，绑定 `355c54a0`，只核 A 文档/设计入口，已由 M 合入。四导航相应更新为现有链接，保留目标待实现及 [A 入口 §1](p7-s1a-a-entry-and-contract.md#1-实际入口和来源) 的特定旧节点/DC68输入。B 工作区 `/home/dev/gdds-p7-s1a-b` 现场有未提交产品改动，不属 cleanup；本任务不触碰、测试、替它合入或从 A_GO 推导 B–G/S1a 退出。

C 实施准备再核 M/355c54a0 三候选全名/stem均无逐字入站；与 B 固定 S1a 输入相比的三文档增量是其静态工具故障/恢复说明与脚本，不引入归档消费者。已读语义仍由前包核准结论及 C 原审独立复核承接，文本零命中不替代消费者判断。main/S1a 再推进时仅重核受影响归档/链接，未知用途先保留，发现共享路径冲突停受影响项。

## 6. 最终核收待办与容器决定

协调者固定 clean C 后，C 原审须核完整 A–B、20 S1a/31 FE 的独立来源、全部三原件、四导航及新增任务记录的链接/fragment、精确净差异、五问题/统计和未知项边界；再给唯一验证者固定稿。输出只写本人外置目录，不覆盖 A/B 原件，不执行产品或 S1a 文档验证脚本。

C_GO 后由协调者串行核最新 main 及并行写入、完成 cleanup 本地合入，并请原审核实际合入增量、来源可达性和最终链接/状态；最后补实际候选/报告/回执/SHA、合入提交和静态核收。本候选尚未发生这些事实，不以分支同步或 B_GO 预先填“已完成”。

Current HEAD 为 C 同步起点 `2b99722bd837f901da7058001cf204b53a4b5fe9`，本页待提交；container rebuild required=no，仅 docs 导航/归档元数据且不在 `vnext/` Docker context，无产品/部署/容器边界变化。Last verified image revision/source-tree 未检查；current container gate=`not-applicable`；carried=none；本任务无需产品门禁。不 push、不部署、不清理他人 worktree/镜像/缓存/日志/卷，不创建 P6/P7 exit tag，不声明资源已释放。
