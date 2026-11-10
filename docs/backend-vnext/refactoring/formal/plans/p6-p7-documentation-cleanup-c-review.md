# P6→P7 文档整理 C 独立验收

日期：2026-11-10。结论：**C_GO**，绑定下列固定 C；归档、入口、整体区间与独立静态回执已核收，候选未关闭 finding 为零。最终 main 合入尚待实际核收。本报告只覆盖文档整理，不签产品、S1a、FE、SDK 或 production。

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

最终 main 合入、后续 handoff/coordination 元数据和实际结果增量尚未执行核收，后续由本原审继续，不因分支候选通过而省略。

Current HEAD 为固定 C。Container rebuild required：no；仅 docs 导航/历史归档/元数据，`vnext` context 与容器边界没有本任务变化。Last verified image revision/source-tree 未检查；current container gate=`not-applicable`；carried=none。本任务不需要产品门禁，不推导资源已释放、S1a/FE 产品通过或新的 exit tag。
