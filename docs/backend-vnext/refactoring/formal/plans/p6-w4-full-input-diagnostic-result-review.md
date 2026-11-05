# Phase 6 四路完整输入诊断：结果与清理复核

- 结论：**本次诊断结果、停止阈值记录、清理及解释范围通过，无阻塞项。** 固定完整输入的四单元生成/封包在约 47 分 55 秒完成，采样父进程加全部后代 RSS 峰值约 31.971 GiB，同档独立重复字节一致。没有 full2 同条件对照，不给出加速比；输出仍为诊断制品，不接受为正式输入。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 报告候选：`eb72d0eb7cfbc4df13621ab33e3f2dd70b301d51`，见工具分支上的[完整输入诊断报告](p6-w4-full-size-four-process-diagnostic.md)，引用以提交为准。实际代码仍为 `249c09d0824c5d9716f02f7deb1bb8c154ea4c98`；启动依据为 `5d4345310c` 的[启动核对](p6-w4-full-input-diagnostic-launch-review.md)。
- 方法：在 `/home/dev/gdds-p6-full4-result-review-eb72d0eb` clean detached worktree 只读审核；程序核对完整 HEAD、detached、clean、docs-only 及与启动材料代码树不变，diff check 通过。先读 CT201 证据副本，再经 BatchMode SSH 确认 05 占用已释放，仅读取节点原始文件重算；未重跑测试/诊断，未取占用、未访问 CT108。真实数据只输出计数与摘要，核对程序经 stdin 执行。

## 1. 运行绑定与范围

主日志记录 `gw-dms-test-05`、`2026-11-05T04:36:50Z–05:24:47Z`，起止完整 HEAD 均经程序比较为 249，`full_diagnostic_exit=0`、`FULL_SIZE_GENERATION_DIAGNOSTIC_COMPLETE`。启动 wrapper 的 clean 检查和结束 status 无变更输出；目前保留 worktree 也仍为 clean 的相同 HEAD。

重新读取 harness SHA `62cf908f9dae3e853634c43a57b057ca9e9c07328c37ef16eedda8cc00b1dcce`、wrapper SHA `343250abe0400f461510fbec2e20e1763da14fb5cf592ba54046ead90db60322`，与启动审核一致；来源三文件当前 SHA 与 provenance、启动/结束日志均匹配。五锁 before/after/postflight 三份清单的 SHA 都为 `16c8ab14e5714fcc4e8470beea91feda7c56405ef42c36d66ef83336e8d3f238`，每个锁的内容摘要与本地 249 Git 对象比较相同。

运行只包含一次四 worker trial，四份分别为 10%/100% 的首次和独立重复，使用完整模板；没有重建 2×、运行 Preview/census/产品旅程。输出根没有 input-summary、generation receipt 或 failure.json，不能因诊断 summary 成功就转为 INPUTS_READY。

报告披露的一次 `rg` 不存在的状态查询属于只读查询说明，未作为生成失败或重试证据使用；实际生成日志记录的固定 wrapper 成功运行与本次结果相符，不因此追加重跑。

## 2. 制品、完整包与确定性

程序逐项重算输出清单中的 **17 个文件**，包括四份 SQL/完整包、逐单元 JSON、source-package-members、provenance、summary、trial result 和 RSS samples，全部与清单匹配。summary/provenance 公共字段相等，summary 的唯一 trial 与 result.json 相同；每单元 JSON 与汇总相同。

另用标准库只读流式读取完整来源包及四个输出包，不调用生成器或产品物化器：

- 来源包内唯一 SQL 的 SHA 与冻结 SQL 一致；来源成员记录与保存的 source-package-members.json 一致。
- 四个输出包的非 SQL 成员顺序、名称、类型、记录的权限/所有者/时间/link/pax metadata 与内容摘要均与原包相等，每包一个非 SQL 成员；不比较随 SQL 长度变化的物理 tar offsets。
- 每个输出包内 SQL 的大小/SHA 与对应实际生成文件一致；同档首次/重复的 SQL 与完整包实际摘要一致。

| 档位 | SQL bytes | 包 bytes | SQL SHA256 | 完整包 SHA256 |
| --- | ---: | ---: | --- | --- |
| 10% | 153,530,296 | 10,486,420 | `91cfaa9a09a4179ec17aeafa1cdb7dc33892ea90194511078265afe9886e41f6` | `4cb82a16d7c7801a1d4ecf11828cf8e94a92ed95bd6f89293a75653164bbd27c` |
| 100% | 150,737,542 | 9,173,579 | `aedde09698d6eaa48b18ce9ad6d3502dcc51b33c7dfa81d84da23903f3e67bb9` | `c6f7c5e74f48715d2e33e9efe32a5679e913caccd8f93398f3ad4d1322eb4ec6` |

四单元均记录 638 表、873,428 原始输入行；10%/100% 的生成后行数分别为 872,725/863,476。这些是工具计数，不与冻结来源的 873,863 canonical 行强行等同；本轮不补做业务/canonical 验收，也不依据数量差异改变输入接受口径。

## 3. 时间与资源复算

trial 墙钟 **2,875.263897 秒**，harness 总墙钟 **2,875.850894 秒**，外层命令 **2,876.477 秒**。报告已正确区分单元字段、trial 和 harness：单元字段不包括模板成员预读及其后完整包文件 SHA/结果发送，不能把各边界当作完全相同的指标。

四 child 生命周期 CPU 总和为 11,412.745932 秒，除以 trial 墙钟约 **3.969**，支持约四个 CPU 同时工作的描述；它是并行 CPU 使用比，不是 full2/full4 加速比。CPU 为脚本自身记录，审核核对结果层级与算术，不宣称另有独立 CPU 测量。

对 **14,264 次**资源样本逐项验证父进程加后代求和，并重新求最大/最小值，与报告及 summary 完全一致：

| 指标 | 实际 bytes | 换算 GiB | 既定边界 |
| --- | ---: | ---: | --- |
| 父进程 + 全部后代 RSS 采样峰值 | 34,328,506,368 | 31.970913 | 达到 52 即停 |
| 四 worker 聚合 RSS 采样峰值 | 34,201,255,936 | 31.852402 | 辅助指标，不代替上一行 |
| 最小 MemAvailable | 33,166,419,968 | 30.888636 | 低于 8 即停 |
| 最小磁盘余量 | 228,295,626,752 | 212.616871 | 低于 10 即停 |

时间也低于内部 14,370 秒和外层 14,400 秒预算。全部已有采样未触限，日志无资源/截止失败；这不证明采样间不存在更短峰值。RSS 相加可能重复计算共享页，本次约 32 GiB 不能作为其他输入、节点或未来运行的硬上界。

## 4. 证据与收束

CT201 `/home/dev/gdds-p6-logs/full4-diagnostic-20261105/` 的主日志、summary、result、provenance、输出清单与 postflight 六项副本 SHA，分别与候选报告和 05 实际文件程序比较一致：

| 记录 | SHA256 |
| --- | --- |
| 主日志 | `d0ad8488f1457cb4197b603abca3a211ee0ecdd6f0947912794b8361132bad2d` |
| summary | `423f8937ae1378701d6e571931a0ad506e028e3c8199bdd3d3cc355443588d08` |
| trial result | `afeebf2d4f6eb19afe564ed1d8b53fda02df68690b82a4781b0bbb9121232ae0` |
| provenance | `8e8ec1c579b29181d2332b9ac7a847e23062427886d8dfe3d096740a0d1fa0de` |
| 输出清单 | `e2c26fb18482ab68dc70e0ab06ef170360e8d63d09198b79cb1116437ce30920` |
| postflight | `45ef330182138c29b531b6f7d2b67bdbff80335d1690c8ee3a0b07c0aa26dd26` |

节点上的 RSS samples SHA 另重算为 `47eee72bd57aed089d05f3e4884ab2a45cc9391da52c5c236431bb6bd945f28e`，与报告及输出清单相同。

postflight 记录 `05:25:29Z–05:25:30Z`：自有 timeout、父进程、tracker 与四 worker 已退出，五锁和来源不变、worktree clean，确认 owner 后释放标记。本次从资源样本汇总得到的五个后代 PID（四 worker 加 tracker）及已记录父 PID 均已不在 `/proc`，节点 busy marker 不存在；未删除任何现有证据或实施 worktree。

## 5. 解释与后续

可以据此表述：在本次 05、冻结 153,875,448-byte SQL 和完整 SourcePackage 模板上，一次四单元诊断约 48 分钟完成，同档独立重复确定性和模板保留通过，采样聚合内存约 32 GiB，未触及设置的资源/时间停止边界。

不能据此计算全尺寸加速比、承诺整条输入准备流程提速，或将输出自动变成已接受正式输入。正式四路 CLI/default 及分段 receipt 调度若后续实施，仍按另行确定的实现范围处理；本次不改变既有 1/2 路工具审核结论，不影响 CT108 当前任务或基准 exit 顺序。

固定源码、依赖及工作区未变，本轮不触发镜像重建或新增全 runner/五包静态；没有新 image revision/source-tree、产品/容器验收声明。仅按显式路径提交本报告，不合入诊断分支、不推送、不打 tag、不改设计正文；审核 worktree 核对 clean、HEAD 不变后清理。
