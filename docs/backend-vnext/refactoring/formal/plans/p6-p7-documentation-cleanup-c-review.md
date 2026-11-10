# P6→P7 文档整理 C 独立验收

日期：2026-11-10。结论：**C_GO**，绑定下列固定 C；实际本地 merge 及收尾元数据 H 也已独立核收，见 §7。未关闭 finding 为零。本报告只覆盖文档整理，不签产品、S1a、FE、SDK 或 production。

## 1. 固定对象与独立范围

| 对象 | 固定值 |
| --- | --- |
| 来源 S / 输入 I | `5ddd73b962e2432f961a46f6743395a53a388435` / `2204f039a51046563b51fe82a3f978c2e981f259` |
| B 实施 / A–B 收录点 | `1d84b7a0669a4bf7da5f833304436447bbc38e2a` / `bb4dd10e5dc3e8ab0565066ca4749859dd288433` |
| main 带入基线 M | `00ca325c2ed6d705abfa39e9528ef148e6029cfc` |
| 工作分支同步 IM | `2b99722bd837f901da7058001cf204b53a4b5fe9`；不是 cleanup 合入 main |
| 固定 C | `5de3d2eb53b21f659313c86c55af175728c15a6f` |
| 原审 detached | `/home/dev/gdds-reviews/p6-p7-doc-cleanup-c-5de3d2eb53`，起止 clean、HEAD 未变 |
| 后续 main 现场 | `6536502a115956a9a29a43c63c256ccf50f3a2d4`，clean；增量见 §3 |

完整读取 cleanup prompt、execution-plan、coordination、A/B 原审；另读适用 AGENTS/testing-conventions、比例化政策、三层原/新入口、P3→P4 handoff/manifest、三归档原文及其最终承接。独立核 A–B 全区间、C 导航修订、owning Contract 和实际源码消费者。仓库内只写本报告；未 import 产品、运行产品测试/lint/编译/Compose/真实旅程、执行 S1a 验证脚本或连接测试节点。

差异分拆独立成立：`S..bb4dd10e5d` 恰十三条任务路径；`bb4dd10e5d..IM` 恰五十一条已在 main 的路径，分为三十一 FE、二十 S1a；`IM..C` 恰六文档，即四导航、coordination、handoff。`M..C` 恰十四条获准任务路径；三 README 修改、index 新增、三删除及七份任务记录/manifest 新增，没有其他路径。产品/测试/依赖/部署、AGENTS/testing、政策/ADR、Contract、S1a、FE、总纲与实施阶段规划的本任务净差异均为空；`M:vnext=C:vnext=49c1de43be31b5bc5ac75f528e8ef0c77f39bcb3`。

任务区间 `S..bb4dd10e5d`、`IM..C`、`M..C` 的 `diff --check` 均 exit 0。main 带入区间及 `S..M` 均有同一既有 FE 诊断：`docs/frontend-vnext/fe3c-evidence-04.md:436: new blank line at EOF.`，exit 2；不称全 `S..C` 无 whitespace 问题，也不越权修 FE。

## 2. 全部归档原件与语义核收

[TSV manifest](p6-p7-documentation-cleanup-manifest.tsv) 严格解析为三行 ARCHIVE，与实际删除集合一致。逐项从完整 S 读取原字节并核 blob、SHA256、长度，与 I/A 起点原字节相等；恢复副本只写原审本人外置目录。S 对 C、M 及后续实际 main 均可达；最终合入后仍复核。

| 原文件名 | 原字节 | 保留承接与独立判断 |
| --- | ---: | --- |
| `p4-r2-s6-remediation-appendix.md` | 3,524 | 两 finding 中间修复；R2 S6 独审 §8 完整保留 F1/F2 闭合、限制与重开条件，R2 最终 handoff 保留 source/结果/阶段边界 |
| `p4-r2-s6-remediation-handoff.md` | 3,125 | 原下一步仍为独立 rerun；R2 最终 handoff 保留同一 validated source、491/1319/24/2 和正式退出，原独审不动 |
| `p5-5b-s6-remediation-round4-handoff.md` | 2,490 | RR12 中间候选；round5 handoff、S6 最终独审与 S8 handoff 保留 pre-drain 闭合、容器 skip/defer 和最终退出，不把中间结果改为最终通过 |

三份共 **9,139 字节**。候选名/stem 在 S、固定 S1a、M 的候选外无逐字入站；C 命中仅为本任务恢复/审核元数据，没有活跃 Markdown 目标指向删除路径。历史 P5 allowed-path glob、carried-from-round4 和 R2 Git 对象引用保持原文。归档准入来自原文/承接及消费者核对，不来自零命中或年代。

独立重读实际读取/动态调用点：P2 feasibility 仍被 closure 明列并由 methodology 测试实读；legacy oracle 仍用 importlib 加载；两个 benchmark 与 SQL census 测试仍读取 P5 census；fixture JSON 仍固定引用 P6-S4 review；六处 P3 Authority docstring 继续保留。部署 runbook glob 只覆盖 `vnext/deploy/**` 与 RS README，Docker context 为 `vnext/`，没有覆盖三归档候选的动态消费者。未执行这些消费者。P6 原始成功/失败、有效决议、阶段最终原审/handoff 和 S1a 的 P6-S6 模型来源没有移除；其他未知材料继续保留/DEFER。

三 README 的完整压缩差异没有移走唯一有效规则：过时阶段默认顺序被 current index 取代，历史最终入口仍可追溯；精确语义仍由保留的总纲、taxonomy、政策和 owning Contract 拥有。index 不成为第二份规则汇编。

## 3. 权威入口及最新并行增量

P6 tag 原文与新入口一致：六包、本地容器、fresh t4 最小链；保留失败/UNKNOWN/取消项及维护限制，不签 FE/P7/SDK/production。S1a A_GO 原审签署 `/home/dev/gdds-p7-s1a-reviews/a/355c54a0-a-go.md` 已完整只读并独立重算 SHA256 `3d22ae5e4b11143e505bfb7de3cc4b06c7f226a2cee6009639580f7a2f9ddfbb`，绑定 `355c54a0022fde8237f788c0007e375801ff5288`；M 确实合入它。该签署只核 A 文档/设计入口，本整理不连接 06 重验其原件或接管其结论。

C 四导航已准确改为已合 main 的 S1a A，九份 P7/A 文档使用存在的相对链接，仍区分 Contract“目标补充（待实现）”和实际源码。AGENTS/testing 的通用 DC91/DC68 入口与 S1a A 入口 §1 的旧节点/DC68 特定用户输入分别说明；cleanup 的开发主机静态/角色授权来自自身 prompt。未覆盖原 owner 的授权或改写 S1a 历史候选自述。

`24394b98a6..355c54a0` 三路径增量已逐字读核：两个 A 文档的工具故障/明确恢复说明和纯文档验证脚本，没有改变归档依赖、目标生效边界或 §1 特定输入。main 后来推进到 `6536502a`，相对 M 仅新增 `docs/frontend-vnext/reviews/fe4-kickoff-review.md`；无归档名/stem 入站、无本任务共享路径，`vnext` tree 不变。

S1a B 保持隔离并有活跃 dirty 产品/fixture 与三新增本包文档/脚本。已只读留身份和三份文件字节快照，读取其文档及脚本相关调用点：依赖 S1a A/设计/自身验证，无三归档消费者；dirty/untracked 路径与本任务十四路径无交集。该快照不是 B 候选或验收依据，不写入、不复制到 cleanup、不测试、不替其合入。后续若再出现共享路径或新依赖，最终合入前只重核受影响项。

验证末尾 B 已提交 `df0116245fdb15d074d12eddf959972a0240ffb6`，仍有活跃 dirty。已再次独立核 `M..df011624` 的 124 路径及后续 dirty：docs 仅其三 B 文件，全部变化与 cleanup 十四路径无交集；提交全相关树无三归档全名/stem 命中。三文档的后续增量为其自身 B_NO_GO/SCRIPT_NO_GO finding 修复、离线依赖/daemon 预检与 focused 选择器，不新增归档消费者。验证者与原审分别保留各自时点的活跃状态，不伪称它们同时固定或签 B 通过。最新原审快照 `s1a-b-df011624-late/metadata.json` SHA256 为 `6dcc2f33de4bb605d24bb0bfb7c1148e8fec03384e7583708735d72f934d4bb4`。

## 4. 固定静态稿、统计与原审输出

已在固定 C 完整阅读后向唯一验证者发六项稿：新 detached 身份与四区间拆分/净禁动差异；三项完整恢复；四导航及全部任务 Markdown 链接/fragment；S/I/B/M/C 同口径统计与五固定查询；P6/S1a/真实消费者语义；main/S1a 现场增量和最终 merge 后续。固定 query spec SHA256 为 `17ff3acc740505ab0e922729457416a97fdeeb008649c8db5b5343b13255a69f`，只替换 revision，A/B 原件目录只读。

原审在 C 独立核四导航 **121** 个相对链接；四导航加 coordination/handoff 六修改页为 **143 / 14 fragment**；再含其余四任务 Markdown 共 **147 / 15 fragment**，全部有效。index 为 65 行。没有新增活跃断链；该检查不扩大为全仓旧链接治理。

| revision | docs 文件 / blob 字节 | plans 文件 / blob 字节 | M24 文件 / 行 / 规范化字节 |
| --- | --- | --- | --- |
| S | 701 / 15,379,368 | 517 / 10,962,626 | 72 / 343 / 205,846 |
| I | 703 / 15,406,793 | 519 / 10,990,051 | 73 / 344 / 206,085 |
| B | 704 / 15,413,368 | 520 / 11,022,705 | 75 / 354 / 210,802 |
| M | 716 / 15,747,642 | 527 / 11,184,914 | 74 / 347 / 207,073 |
| C | 721 / 15,807,784 | 532 / 11,270,999 | 79 / 364 / 214,384 |

| 固定问题 | C 文件 / 行 / 字节 | 语义核收 |
| --- | --- | --- |
| 当前阶段 | 4 / 27 / 10,025 | P6 exit，S1a A_GO/main 与 B 活跃边界 |
| root/发布/保护/清理 | 5 / 59 / 18,926 | 唯一 owning Contract，目标待实现 |
| 节点/失败/角色 | 5 / 44 / 15,679 | 通用规则、S1a 特定输入、本任务授权分别可达 |
| 历史恢复 | 4 / 9 / 3,782 | 固定来源、原路径/blob/SHA 和保留原结论 |
| 必须保留的消费者 | 8 / 34 / 4,531 | P2、legacy、census、fixture 等实际依据 |

S/I 基线、I spec 原输出、B 报告数值均独立复算一致。C 对 M 的 docs 净量 **+60,142 字节**：毛归档 −9,139；三 README 36,907→10,964，压缩 25,943；新 index +9,000；七份任务记录/manifest +86,224。他人 main 相对 S 另 +368,274；不能把 `S..C` 总量归 cleanup。上述仅固定 C，尚不含本报告及后续收尾元数据；不称文件/grep 字节是模型时延、正确率、token 或全量检索收益实测。

原审目录为 `/home/dev/gdds-test-tmp/docs-cleanup-c-review-20261110-Wc7UNF/`。固定 C 的 `candidate-audit-v2/audit.json` SHA256 `13bc0bfe0e48dafcb5b5a412cacb1f4d89608ae9236103edbc7f977c385ae671`；`static-audit-v2.py` SHA256 `dacdc31d99c40f21316851157e7f8690e41b5535b65df55deb693019fa5e95ed`。输出含全部恢复副本、逐命令 stdout/stderr/原 exit、统计/查询与链接；04:11:17Z–04:11:18Z，`heavy-dev-01`，exit 0。后续 main/B 快照见 `latest-parallel-input/metadata.json`，SHA256 `be4ca5721d16081432372519a1c0b2c948156e5f574aabe28ec0c5f318cf9f19`。

## 5. 证据限制与失败保留

A/B 原审的限制继续成立，关键 receipt/spec 摘要已独立重算相符。A 的两份旧 M24 派生文本写前 SHA/metadata 未保存，新的固定 Git 输出可复算不追认被覆盖文件的原始身份；A 的标签/表行 logger 初错仍保留。B 的本人 README basename 覆盖、stats dict 比较失败、Authority 窄 grep 和旧 identity 结束段格式限制，以及实施者无命中 grep 的错误 exit 预期均保留；不补造旧副本身份、精确时刻或实时总日志，也不把修正说成产品 DC68 恢复。

C 又只读核明 A 的 `navigation-path-baseline.json` 当前仅为三字节 `[]`；无法从该文件重放 A 所报的 221 条路径计数，也不推断其写前身份。C 从 S/I 固定 Git 另核三 README 的 227 个链接路径无缺失，并已完整核固定 C 的全部新/保留链接及锚点。验证者自己的只读摘要 key 错误和末端文件名碰撞拒写均保留于 `operator-events.txt`；后者未覆盖原件，改用唯一文件名完成。

C 原审也保留自身事件：初筛 rg 误猜三个不存在源码路径，exit 2，原始来源仅会话工具 stdout/stderr，后用 `rg --files` 和真实路径修正；首次静态脚本将 main 带入区间也要求 `diff --check` exit 0，遇 §1 既有 FE 空行诊断后 exit 1 停止。原脚本、逐命令输出和 traceback 均留存；v2 仅把已知 main 基线与任务区间分开，任务预期不变，未改 FE 或隐藏原失败。首次脚本 SHA256 `6134f9383ba58824d9962968542602feb19176746e33cbc4fd0b4af4a8a827a1`，traceback SHA256 `b5c0cafd779dcd774ac56417b83fdba48725d39abff328b6e829802083bb8772`。末尾首次索引只读核对误用双空格解析实际 TSV，ValueError 来源仅会话输出、未写文件；改按 SHA/size/path 三列后逐项通过。全部静态操作无产品/外置原件写入副作用。

## 6. 独立验证及最终合入

独立验证目录为 `/home/dev/gdds-p6-p7-documentation-cleanup-c-verify-20261110/`。验证者在自己的 clean detached C，`heavy-dev-01`，04:19:27Z 起、04:34:18Z 结束留完整身份；候选起止一致。原审交叉核其首段一百命令的二百个原始 stdout/stderr SHA/长度；五 revision blob 统计、五份 M24、二十五份固定查询及三恢复原件与原审独立输出逐字相符。随后五十五命令的一百一十个 raw 输出、十篇固定文档快照、全部 147 链接/15 fragment、消费者与语义输出也逐项核收；没有补称另有未保存的实时总日志。

原回执 `candidate-verification-receipt.txt`（SHA256 `9f0a7d749d1987a156bd5d8c69e0aa4276b40cd51a7c13a9df0dfbef4f0f84e3`）将 P6 peeled commit 误称 tag object，原审提出 **C-V1**。验证者保留原件后新增 `candidate-verification-receipt-r1-final.txt`，SHA256 **`544b4238a4ae28fb463bdd2c4b70456e79ffbef513b15f3db79cd31b9b077921`**；原审逐字比对仅改身份区分并增修订说明，已核附注对象 `e4791d4e8d7cbd09e172bf4e74e4f3e5545ca176` 与 target `b0fc25e881cb4ce39b1cc847bad92b4ccb06b809`，**C-V1 closed**。中间 r1 漏说明草稿及生成事件也保留，不覆盖或补造旧原件。

最终候选证据索引 `evidence-sha256-r1-final.txt` SHA256 **`0add13d7e25fef9c3843a55bcfac85c0932290ae19fb94bf2d7d97ad3261eb2c`**，原审重算其全部 464 项 SHA/长度相符；此前 v2 的 447 项也全部重算。链接 JSON SHA256 为 `0e483cb045f0a41e63d199bec356cf15a90471742ad7bf028f5f8e1878418064`。所有回执限制见 §5；没有改变 C、归档集合、spec 或原断言。

实际 main 合入及 handoff/coordination 元数据增量已继续完成核收，见 §7；没有以候选 C_GO 代替实际 merge 检查。

Current HEAD 为固定 C。Container rebuild required：no；仅 docs 导航/历史归档/元数据，`vnext` context 与容器边界没有本任务变化。Last verified image revision/source-tree 未检查；current container gate=`not-applicable`；carried=none。本任务不需要产品门禁，不推导资源已释放、S1a/FE 产品通过或新的 exit tag。

## 7. 实际 main 合入及收尾元数据核收

实际 merge **F=`6a8fff14f3fcd865d4797c53d8ef5ae794ebac66`**，父提交依次为 N=`6536502a115956a9a29a43c63c256ccf50f3a2d4` 与 T=`895a7ed08d07823d2e80b4589e32d4ae692f809a`。原审新建 clean detached `/home/dev/gdds-reviews/p6-p7-doc-cleanup-final-6a8fff14f3`，逐项核：`C..T` 仅新增本报告的候选签署版（14,169 字节）；`T..F` 仅新增 FE4 review 且字节等 N；`N..F` 恰十五条本任务路径，较 C 仅多本报告。其余任务字节/删除状态与 C 一致；C/N/F 的 `vnext` tree 相同，没有本任务产品、Contract、共享规则、S1a 或 FE 净变化。上述三个净区间 `diff --check` 均为 0；全 S..F 仍保留已知 FE3c EOF 空行 baseline，不作全区间通过声明。

F 上三归档原件再次逐项恢复并核 source/blob/SHA/长度，S 是 F 和实际 main 祖先；manifest、保留承接与附注 tag 身份未变。固定五查询的 F 规范化输出逐字等 C。既有 147 链接及其目标字节未变，本报告候选版新增一条有效 manifest 链接，F 合计 **148 / 15 fragment**。原审 `final-merge-6a8fff14/final-merge-audit.json` SHA256 为 `c51fc55f4aa23a4878fc1a9dcf013224c597285e4fdcdb99a5a56e5b89314291`。

随后固定 **H=`3ef86af38264cb29db0031944615bea6337e701e`**，直接父提交为 F；原审新建 clean detached `/home/dev/gdds-reviews/p6-p7-doc-cleanup-handoff-3ef86af382`。完整读取 `F..H`，恰 handoff/coordination 两页，只补候选 C_GO、实际 merge、现有统计/原件/限制及当时 pending 状态；无规则或归档范围变化，其他树字节与 F 相同，`diff --check` 为 0。H 的全部十一任务/导航文档 **152 相对链接 / 15 fragment** 有效，固定五查询所用路径 F..H 无变化。两页引用的报告 SHA `a7d8b8b20deddaeb0737713778bcfe352c9ff512488ba31ca3511c8b7714ff76` 已从 T 的报告原字节重算，仅标识候选签署版，不标识本次追加后的文件。原审 `handoff-3ef86af3/metadata-audit.json` SHA256 为 `2df22788a3975a0768d4e61f11a07e701efd60f296ab835d24ddd2d1280b2813`。

唯一验证者按原审另发的固定 merge/H 增量稿，在新目录 `/home/dev/gdds-p6-p7-documentation-cleanup-c-merge-evidence-20261110/` 留独立原件。原审核其 97 核心命令的 194 raw 文件、三原件 r2 的 24 raw 文件、47 链接命令的 94 raw 文件 SHA/长度相符；F/H 的 148/152 链接逐条集合与原审独立结果一致，二十二文档快照逐字等各固定 Git 对象。结束快照 04:55:47Z 为 `heavy-dev-01`、F detached clean、main H clean、S1a A clean；未执行产品或连接节点。

最终回执 **`final-merge-verification-receipt-r1.txt`** SHA256 为 **`3225575424c7aa88ee6f1600b2241aa02963cf1c99d5387f6b03a6933d3911ba`**；最终索引 **`merge-evidence-sha256-index-r1.tsv`** SHA256 为 **`943a64c4f1544edf45e7d8df365d15bf21542c7de0ebe7babcfd44d98a9bfbe0`**，原审重算全部 **422 项** SHA/长度相符。原 418 项索引也已全核，原件保留。

最终验证者的首轮归档预期 SHA 手抄错误导致第三项摘要 false；r1 三逐项结果正确但顶层摘要仍误抄，均原样保留。r2 直接从已核固定 C manifest 读取预期，三原件再恢复全部一致，原审核收；没有修改来源 SHA 或被核对象。原最终回执又把继承 FE3c 的 34,116 字节/SHA 标签写作 FE4；保留原回执后 r1 仅改该标签并增说明，原审逐字复核关闭。真实 FE4 review 为 35,648 字节/SHA256 `985ece6b46ec2cd43ff1eb42d912147208388d652c54ce4a682eeb0a01a4f26e`；继承 FE3c SHA `5f880f9a26b356eaeed4429f91b036699b96c56e2ee36249b39b0f2a462e4994` 保持。原审最终索引只读辅助命令也曾误将 header 当路径、宽 glob 误收生成脚本，均在写文件前停止，原始来源仅会话输出；改按明确 TSV 文件/header 后 418/422 项重算通过，不补造原日志。

验证期间 S1a B 推进至 clean `bba9d6ae9a1e36509f2d51934ec565b2dbc990fd`。原审另核 `df011624..bba9d6ae` 十八路径：docs 为其三 B 文件和新增 saved-image helper，均不与 cleanup 十五路径相交；全相关树无三归档全名/stem 命中。读增量与 helper 后确认仅补其依赖来源/镜像 tar 身份验证，不读取归档材料、不改变本任务范围；不签其 B 结论。快照 `s1a-b-bba9d6ae/metadata.json` SHA256 为 `5bf1b649be43e2db767cf674bbf0d64d43564daf99b40dff811dedbb686144c1`。

**本地合入 F 与元数据 H 的最终静态验收通过，未关闭 finding 为零。** 协调者后续只需提交本报告追加并将 handoff/coordination 的 pending/写稿时点状态收口；该最终最小差异继续由原审只读核收，不改导航、manifest、归档集合或产品。H 为此处实际核收的精确 HEAD；容器决定仍为 no rebuild / `not-applicable` / carried none，无 push、部署、产品 exit tag、资源清理或产品/S1a/FE 通过声明。
