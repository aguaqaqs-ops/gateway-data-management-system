# P6→P7 文档与检索整理协调记录

日期：2026-11-10。状态：**A_SCOPE_GO 已核收；B 入口与三项归档实施候选，待 B 原审/静态验证；C 未执行**。

本记录是单份协调入口。授权与禁动表依[任务提示词](p6-p7-documentation-cleanup-prompt.md)和[执行方案](p6-p7-documentation-cleanup-execution-plan.md)；不形成新的产品规则或 S1a 授权。

## 1. 固定输入与现场边界

| 项目 | 已核事实 |
| --- | --- |
| 实现 main 基线 / 归档来源 S | `5ddd73b962e2432f961a46f6743395a53a388435`；位于 `/home/dev/gdds-s5-design-main`；A 最近核对 clean |
| 本任务输入提交 I | `2204f039a51046563b51fe82a3f978c2e981f259`；基于 S 只纳入本任务方案与提示词；本任务工作区 `/home/dev/gdds-p6-p7-doc-cleanup` |
| P6 exit | 附注 tag `p6-exit` → `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`；tag 原文限定六包、本地容器和 fresh t4 最小链；不签 FE、P7 或 production |
| S1a 初读 | `a46cea2c048b2dfb57c5c3ab062974ae6815a4df`，四个 dirty 文档；未写入该工作区 |
| S1a 最新只读快照 | `24394b98a6e6f9bea89c404b44cf0dde691a8044`，工作区 `/home/dev/gdds-p7-s1a-a`、分支 `p7-s1a-a`，clean；与前快照相比五个文档更新，已重核候选引用 |
| S1a 状态 | A 入口与 Contract 目标候选，修复原审 finding 中；不能称 DESIGN_GO、产品通过或 S1a exit。本任务不等待其 exit，也不替其合入 |

S1a 相对 S 的只读禁动集合为：`docs/backend-vnext/artifacts.md`；`contracts/{comparison-bundle,comparison,risk,snapshot-table-access}.md`；formal `contracts/{business-lifecycle-and-state,canonical-storage-and-repository-boundary,operation-lifecycle-and-integrity,repository-service,storage-mutation-and-change-set}.md`；以及 `p7-{design,execution-plan,processing-groups-and-test-extraction-design,s0-owner-decisions,s1a-execution-plan,s1a-implementation-prompt,s1a-storage-resource-design,s1a-a-entry-and-contract,s1a-a-verification}.md`。前两组路径相对 `docs/backend-vnext/`，最后一组相对本目录；共 19 个文件，后续新增同属 S1a。

**适用输入不能被导航改写。** S1a 固定提交的 `p7-s1a-a-entry-and-contract.md` §1 明确：本轮用户给定旧节点分工/DC68 优先于其本地 main 已写的 DC91 节点池/新版 DC68；06 focused、04 权威、05 默认真实调试，不继承 P6 的 06 完整旅程专项许可，也不默许三轮恢复。本任务的当前索引应同时指出仓库通用规则入口和这一 S1a 特定授权边界，不能宣称通用规则替代它。本任务本身依 cleanup 提示词仅做开发主机文档静态核查，不运行产品或连接测试节点。

其余禁动：`vnext/**`、`frontend/**`、`legacy/**`、锁/部署/fixture/golden、AGENTS、testing-conventions、政策/ADR/Contract、`architecture-and-refactoring-plan.md`、`implementation-stages.md`、FE 文档、其他会话文件与外置证据/资源。入口可引用 owner，不能复制其规则成为第二权威。

## 2. A 提议的精确归档集合

以下三文件在 S 和 I 中字节一致，均为 tracked、来源已在 main 历史可达。**A 阶段仅提议且未删除；[A 原审](p6-p7-documentation-cleanup-a-review.md)已给 A_SCOPE_GO，B 按下列精确集合删除并登记 manifest，待 B/C 验收。** 不将文件年代、零逐字命中或体积单独作为删除依据。三文件合计 9,139 字节；不是数量指标。

完整来源提交统一为 `5ddd73b962e2432f961a46f6743395a53a388435`，下表原路径统一前缀 `docs/backend-vnext/refactoring/formal/plans/`。

| 分类 / 原文件名 | source_blob | SHA256 | 原件角色、现行 owner / 保留承接 |
| --- | --- | --- | --- |
| ARCHIVE `p4-r2-s6-remediation-appendix.md` | `c7c86675bac60f47aa7b941ee94af2b710fa655b` | `59225f95fd8570cd7372cd97029cbdc2a027c8a93fd7c0ce0e599d3b8e3307ca` | S6 两 finding 的修复处置，非 R2 最终交接；operation runtime owner。两项完整闭合与重开边界已在保留的 `p4-r2-s6-independent-review.md` §8 和 R2 S7 最终 handoff 承接 |
| ARCHIVE `p4-r2-s6-remediation-handoff.md` | `68bd0d8fd671559ec279850369483b99241c012a` | `bd981887494b378ed7d5c39b590dae3866408873010632e01cae5287d19a1473` | finding-scoped 中间交接，next 为独立 rerun，原文不授权 S7/R3。保留 R2 S7 最终 handoff 的精确 source/tree、491/1319/24/2 结果、两 finding 处置及原独审；当前语义仍由 operation Contract 拥有 |
| ARCHIVE `p5-5b-s6-remediation-round4-handoff.md` | `d0188559e72084b940103a3c0b5e9e5e44516535` | `d91611f5ed79e170fa6d522dff7e47fb271422991519905c7d6c6f8fc9612784` | P5 Delivery 中间修复轮，原文仍阻塞 S7。RR12 pre-drain 在保留的 round5 handoff、`p5-5b-s6-independent-review-5.md`（Round 6）和 S8 最终交接中承接；不归档最终退出或只剩此处的规则 |

B 若经核准，逐文件写 manifest 的完整原路径/source_commit/source_blob/SHA256/reason/current_owner_or_successor/dependency_disposition，再从当前树移除；不改原件、不新建 archive 复制树、不新 tag。恢复只输出到本人临时目录，例如：

```bash
git show 5ddd73b962e2432f961a46f6743395a53a388435:docs/backend-vnext/refactoring/formal/plans/p4-r2-s6-remediation-appendix.md > /本人临时目录/p4-r2-s6-remediation-appendix.md
```

### 三类消费者核对

| 类别 | 检查与处置 |
| --- | --- |
| 当前导航、S1a、Contract/ADR/决议/有效 handoff | 对三候选全名与去扩展名 stem 的 tracked 文本检索均无候选外逐字入站命中；读三份原文及承接报告，确认没有独留有效决议。不能据此推断全仓历史零引用 |
| 实际代码/测试/runner/闭包/构建 | 只读扫描 `vnext/`、`frontend/` 的 docs 路径、Markdown读取及 glob 调用点；已识别 P2 methodology、legacy oracle、P5 census 等真实读取。部署 runbook glob 仅覆盖 `vnext/deploy/**` 与 RS README，不覆盖候选。未发现运行时按 `formal/plans/*.md` 扫描三候选的路径；Docker context 为 `vnext/`，候选位于 context 外。任一新增动态消费者疑点即将该项转 DEFER，不改产品来归档 |
| 历史/保留材料与归档内部 | 三候选互无逐字引用；R2 最终 handoff 保留 Git input commit（历史对象引用仍有效，不等同于当前树文件依赖）。P5 plan/S6 原审含 `p5-5b-s6-*.md` 的**历史 allowed-path glob**，且 round5 有 carried-from-round4 叙述；这些历史范围/轮次描述保留原文，不能说完全无历史引用。它们不要求当前树保留每份中间 handoff，归档清单提供精确恢复入口。三候选均无活跃 Markdown 入站链接，因此无需改冻结原审 |

### S1a 传递依赖

以最新 clean S1a 的 19 变更文档为种子，只读建立 tracked docs + AGENTS 的文件名引用保守传递图；包含 Markdown、code span、裸文件名，basename 重名会过量保留。结果可达 655 文件，三候选均不可达。该图是保守筛选，不能证明任意动态引用不存在；另有上述源码调用点核对。

直接保留链包括 `p7-s1a-{implementation-prompt,execution-plan}.md` → `p6-s6-implementation-prompt.md` §3、`p6-s6-coordination.md`，以及 P7/S1a 设计 → artifacts、business/storage/runtime/RS owning Contract、ADR0012、比例化政策、S0 决议与实际 FE review 输入。新增 `24394b98a6` 五文档改动未新增候选依赖。B/C 前再次检查 S1a 增量，仅复核受影响候选；未知用途先保留。

## 3. 保留与延期

| 分类 | 路径 / 集合 | 理由与后续 owner |
| --- | --- | --- |
| KEEP_CURRENT | AGENTS、testing-conventions、现行政策/ADR/Contract、P7/S1a 上述 19 文档和后续记录 | 实际规则/owning Contract/活跃工作；本任务只链接，不改变路径或正文；各原 owner |
| KEEP_CURRENT | `p2-r1-runtime-provider-feasibility.md` | `test_input_closure.py:110` 纳入 RS 闭包；`test_p2_r1_audit_corrective.py:123` 实读 methodology 字节。RS owner；本轮不改 consumer |
| KEEP_CURRENT | `legacy/` 与 P3 parser/source/table-rules handoff | `tests/support/table_rules_legacy_oracle.py` 动态加载 legacy 模块；多份 capability contracts 的 Authority docstring 仍指 P3 handoff。Backend/capability owner |
| KEEP_CURRENT | `p5-arch-closure-s1-census.json` | `real_dump_journey.py:1110`、`s4_submit_measurement_driver.py:411` 与 `test_table_access_sql_census.py` 实读；真实数据/SQL census owner |
| KEEP_EVIDENCE | `p6-s4-c-review.md` | `vnext/fixtures/vectors/mutation/sql-replay/v1/batch-boundaries.json` 的 independent_review 字段固定引用；mutation/fixture owner |
| KEEP_EVIDENCE | P6 全部原始成功/失败记录、`p6-s6-{report,iii-execution,coordination,implementation-prompt}.md`、Owner 决议 | exit/失败与当前 S1a 模型来源；不把旧失败改写成通过；Backend/P6 各 owner |
| KEEP_EVIDENCE | R2 S6 独审与最终 `p4-r2-durable-store-atomic-transition-handoff.md`；`p5-5b-s6-remediation-round5-handoff.md`、`p5-5b-s6-independent-review-5.md`、S8 最终交接 | 完整承接三候选的历史闭合/限制；round5 含 skipped 容器和后续工作等证据，后续归档评估延期；原 owner；历史阶段的授权不能当当前权限 |
| KEEP_EVIDENCE | `p5-5b-s3-independent-review-8.md` | 虽逐字入站零命中，明确是 Final Stage Sign-off；不因零命中归档最终签署 |
| DEFER | 其他未逐文件核清的长 review/过程记录 | 本轮小集合已足够，未逐条追清所有后续 owner 前保留。P5 Delivery / 各原 owner |
| DEFER | S1a 各目标补充、实现阶段总规划和 FE review 的 stale/同步问题 | 并行归属，不属 cleanup 可写范围；S1a / FE / 总规划 owner |

## 4. 可写集合交接

A 实施者只写本记录；A 原审只写 `p6-p7-documentation-cleanup-a-review.md`；验证原件在本人 worktree 外。是否核准由原审报告给出，实施者不自签 GO。

B 的精确普通导航白名单是 `docs/backend-vnext/README.md`、`docs/backend-vnext/refactoring/README.md`、`docs/backend-vnext/refactoring/formal/README.md`，以及新 `docs/backend-vnext/refactoring/formal/plans/current-context-index.md`。三份 README 都存在默认阶段漂移，修当前入口并压缩历史默认导航；保留现行 owner 链接，不改历史记录语义。未发现需要扩大白名单的普通导航页。

B 可删除的候选严格限 §2 三条且须先被 A 核准。本任务文件限已有方案/提示词、本记录、一份 `p6-p7-documentation-cleanup-manifest.tsv`、A/B/C 三份原审报告与最终 `p6-p7-documentation-cleanup-handoff.md`。后续如只修本任务导航/清单，原审连续复核；其他普通导航需先登记白名单，不抢改 S1a 或历史原审。

## 5. 固定检索问题与 A 基线

统计用 Git tracked blob 字节，排除磁盘 untracked，不含路径/权限空间。S 是产品/文档基线，I 额外包含两份任务输入；B/C 必须分别报告整理的毛移除与本任务新增记录，不能以记录增长掩盖或夸大收益。

| 固定 revision | docs 文件 / 字节 | formal/plans 文件 / 字节 | M24 命中文件 / 行 / 输出字节 |
| --- | --- | --- | --- |
| S `5ddd73b962` | 701 / 15,379,368 | 517 / 10,962,626 | 72 / 343 / 205,846 |
| I `2204f039a5` | 703 / 15,406,793 | 519 / 10,990,051 | 73 / 344 / 206,085 |

文件/字节口径：`git ls-tree -rl <rev> docs`，按路径前缀求文件数与 blob size 总和。M24 口径：`git grep -n M24 <rev> -- docs/backend-vnext/refactoring/formal/plans/`，**逐行去掉最前 `<rev>:` 后**保留 `path:line:text`、原字节与末尾换行。此口径故意不沿用交接观察的另一种终端字节数；B/C 按本口径重复。本轮三个候选均不含 M24，不预期此历史查询出现大幅下降；当前入口可用性是主验收目标，不宣称 Codex 时延/正确率/token 实测。

五个固定问题使用 `git grep -n -E <regex> <rev> -- <固定 paths...>`，同样去掉 revision 前缀。完整 regex/path 数组与原输出放在 §6 的 `five-query-spec-and-baseline.json` 和 `q1`–`q5` 文件；其路径数组**已预先包含尚不存在的 current index/manifest**，B/C 不改预期或缩窄范围，只替换 revision。下面是 I 的对照：

| 问题 / ID | 入口范围与最低正确结果 | I 文件 / 行 / 输出字节 |
| --- | --- | --- |
| 当前阶段与下一入口？`q1-stage` | 三层 README + current index；I 仍称 P5 默认、P6 待 kickoff，需改为 P6 已退出、S1a 实际候选状态和固定分支来源 | 2 / 8 / 1,484 |
| 多 root、发布/保护/清理听谁？`q2-contract` | artifacts + business/storage/runtime Contract + current index；Contract 仍是 owner；S1a 固定设计目标待实现，不能把其目标当已生效源码 | 4 / 43 / 10,723 |
| 当前节点、失败与角色出处？`q3-authorization` | AGENTS/testing + P6-S6 prompt + cleanup prompt + index；既有通用 DC91/DC68 与 S1a 特定旧输入分别注明适用范围；本任务角色授权来自 cleanup prompt | 4 / 41 / 14,106 |
| 旧退出/结论如何追溯？`q4-history` | P6 report/III/coordination、R2 最终 handoff、manifest、index；P6 tag 对象与 R2 固定来源都可读，B manifest 提供原路径/blob/SHA恢复，失败结论保持原文 | 2 / 3 / 410 |
| 哪些老材料不能删？`q5-consumers` | P2 closure/audit调用点、legacy oracle、P5 census 两 benchmark/测试、fixture JSON、index；最低找到这些实际消费者与保留理由 | 7 / 30 / 3,489 |

S1a 尚未合入 main 的九个 P7/本包文件用 `git show 24394b98a6e6f9bea89c404b44cf0dde691a8044:docs/backend-vnext/refactoring/formal/plans/<文件名>` 读固定字节；current index 不能放指向本任务树不存在文件的相对链接，也不能拷贝另一套文件。Q2/Q3 还应沿此固定来源人工核目标/授权语义，grep 数字不代替语义验收。

链接基线：三层 README 的 inline 相对 Markdown 链接**路径**检查无缺失；尚未证明全部锚点均有效。B/C 对修改页的新/保留锚点完整核对，既有无关失效记基线，不借机改 owner 正文或历史原审。三候选没有活跃入站 Markdown 链接；归档清单/本记录使用恢复元数据，不制造指向删后路径的相对链接。

## 6. 原始输出与待核收

A 实施原件目录：`/home/dev/gdds-test-tmp/docs-cleanup-a-impl-20261110/`。该目录仅文档静态输出，未 import 产品、未测试/lint/编译/Compose、未连接节点。主要原件：`candidate-audit.json`（全路径/source/blob/SHA/字节与逐字入站结果）、`statistics.json`、两份 `M24-*.txt`、`five-query-spec-and-baseline.json`、`q1-stage.txt` 至 `q5-consumers.txt`、`product-doc-consumers.txt`、`s1a-readonly-snapshot.json`（19 seeds/655 可达路径及 clean HEAD）、`navigation-path-baseline.json`。交原审/验证者逐项读取，不以本记录替代核验。

一次初筛 rg 错把仓库不存在的 `scripts`、根 `pyproject.toml`、`.github` 当搜索根，工具 stdout/stderr 记录 exit 2；未触及被测对象、无写入副作用。已改为实际 `vnext/ frontend/` 重做并保存 `product-doc-consumers.txt`；不把首次失败称通过，原始来源仅为会话工具输出，没有补造独立实时日志。该操作是文档静态盘点，不是产品门禁或 DC68 测试恢复声明。

| 工作包 | 实施 | 独审 / 验证 | 合入 |
| --- | --- | --- | --- |
| A | 盘点与精确范围已固定；A 未删除文件 | A 原审 A_SCOPE_GO，A 静态回执已核，A-N1/A-V1 补充处置 closed；原件身份限制见原审 | 已在本任务分支固定；未合 main |
| B | 三 README/current index 已修；manifest 三行；删除三原件共 9,139 字节 | 实施静态自检完成；待协调者固定 clean 候选后原审与独立验证 | 未提交/未合入 |
| C | 未开始 | 未开始 | 未合入 |

A 原范围结论与静态回执见 A 原审；B 下一动作是由协调者固定 clean 候选并交新 B 原审/验证者。三文件归档集合如需收紧，直接保留/延期即可，不扩大为产品变更或重跑测试。当前 HEAD 与镜像记录：A 输入为 I，仅文档盘点；不触发容器重建，无新的 image revision/source-tree 验证声明，无 carried/产品通过声明，必要产品镜像验证归其实际 owner。

## 7. B 实施候选与静态交接

B 固定起点 `497fedfce56f1c183e6f638f7b7ec949fa44d859`。2026-11-10 03:39Z 只读核 main 为 `16ffe728290e1179d9450ea160a0e6ca49473ec6`、clean；S..该点为 31 个 FE 文档/前端路径，未重叠本轮导航或三候选，`vnext` tree 仍为 `49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。S1a 仍为 `24394b98a6e6f9bea89c404b44cf0dde691a8044`、clean，无相对 A 最新快照增量；未写其工作区。后续 main/S1a 变化由 B/C 固定候选及合入前再核，不将本快照当永久许可。

实施顺序为先修三层 README 和 [Current Context Index](current-context-index.md)，再写 [TSV manifest](p6-p7-documentation-cleanup-manifest.tsv)，核来源与当前原字节相等后逐项移除三文件。三 README 压缩旧默认导航，保留现行 owner 与历史最终入口；未改 owning Contract、旧审核原文或退出结论。current index 只链接当前 owner，同时说明 S1a 分支目标“待实现”、九份尚未合入文件的完整固定读取方式、通用规则与其特定旧节点/DC68 输入的适用范围。本轮没有新增其他归档项或普通导航路径。

三行清单均给完整来源 `5ddd73b962e2432f961a46f6743395a53a388435`、原路径、blob、SHA256、字节、理由、owner/承接与依赖处置。删除前已核 source 是当时 main 与本任务 HEAD 的祖先；`git show <source_commit>:<original_path>` 的恢复副本仅写本人临时目录，三项 blob/SHA/长度与 A 表及实际原字节相等。最终 main 可达性仍由 C/合入核收，不预记完成。毛移除为三文件 9,139 字节；导航压缩与本任务新增 index/清单/审核/记录应分列，不用净量冒充毛收益。

最后只读核对 main 全名/stem 入站时，首次 inline Python 错将 `git grep` 无命中的 exit 1 断言为 0，脚本以 AssertionError/exit 1 停止；此前均为只读 Git 命令，无产品执行或写入副作用。原失败仅保留于会话工具 stdout/stderr，没有补造独立实时日志。随后先单独确认 grep 的真实无命中/exit 1，再固定 `final-check.py` 以 expected_exit=1 记录并完成核对；修正的是 logger 预期，不改变归档范围/内容或产品断言。修正后原输出在 `final-static-commands.json`，含现场身份及四份 `git show` 固定 S1a 原字节；该静态操作不声明 DC68 产品恢复。

B 实施原件在 `/home/dev/gdds-test-tmp/docs-cleanup-b-impl-20261110/`：`archive-before-delete.json` 及三原件副本记录删除前身份；`implement.py`、`archive.py`、`check.py` 是本人实施/静态核查脚本；`navigation-links.json` 与 `checks-working.json` 是工作树自检输出；`q*-working.txt` 和 `M24-working.txt` 仅为未提交工作树的同路径/regex 预检，**不充作固定 B revision 的最终统计**。协调者固定 B 后，由验证者按 A 的 `five-query-spec-and-baseline.json` 原数组仅替换 revision 重算，原实施输入目录与 A-V1 涉及旧文件不写入。

实施静态自检：四份导航共 111 个相对链接（含 fragment）路径/锚点有效；清单恰三项，与实际删除一致且全可恢复；`git diff --check` 和精确白名单核对通过。P2 closure/methodology、legacy oracle、P5 census、fixture review 及 S1a/P6 有效依赖均保留；五问题的最终语义与固定统计仍待 B 原审/验证者核收。仅文档静态操作，未 import 产品、运行产品测试/lint/编译/Compose 或连接测试节点。

当前 HEAD 仍为 B 起点，尚未提交；容器重建 `not-applicable`，理由为文档导航/元数据且不在 `vnext/` Docker context。最后验证的 image revision/source-tree 未检查，无当前产品、容器、carried、S1a 或资源释放声明。B 实施者不自签 GO，不代写 B 原审。
