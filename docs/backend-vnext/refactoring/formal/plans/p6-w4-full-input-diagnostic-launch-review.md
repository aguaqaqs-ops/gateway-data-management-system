# Phase 6 四路完整输入诊断：启动条件核对

- 结论：**启动条件核对通过，可按 owner 原授权执行本文固定 wrapper 一次，无需再次等待确认。** 不由审核方启动，不改变当前 CT108 任务；触及既定停止条件即收束、保留记录，不自动重试。本报告不是全尺寸结果、输入接受或正式四路工具验收结论。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 材料候选：`99b44fe0b219df57bf3842005692546936c2ba73`，工具分支上的[启动材料](p6-w4-full-size-four-process-diagnostic.md)，引用以提交为准。设计为 `0a239dca540c353314b254601a214b431fc33fe1` 的 §5.4，见[范围审核](p6-w4-full-input-diagnostic-scope-review.md)。实际执行代码固定 `249c09d0824c5d9716f02f7deb1bb8c154ea4c98`。
- 方法：在 `/home/dev/gdds-p6-full4-launch-review-99b44fe0` clean detached worktree 只读审核；程序核对完整 HEAD、detached、clean、docs-only 和父提交代码树不变，diff check 通过。05 先 BatchMode SSH 确认，随后只读固定脚本、既有微型结果和冻结来源，不取占用、不重跑测试或启动全量；未访问 CT108。真实数据仅输出大小、计数与摘要，核对程序经 stdin 执行。

## 1. 固定执行对象

05 worktree `/home/dev/gdds-p6-input-preflight-05` 经程序核对仍为 clean 的完整 249 HEAD。节点标记 owner 为 `p6-input-full4-diagnostic`，用途为“计时测量：full W4 4-way generation diagnostic”，本次审核没有修改该标记。输出根 `/home/dev/gdds-test-tmp/p6-w4-full-20261105a` 尚不存在。

启动应执行已审外置 wrapper **`/home/dev/gdds-test-tmp/p6-w4-full-run.sh`**，SHA256 **`343250abe0400f461510fbec2e20e1763da14fb5cf592ba54046ead90db60322`**，将完整 stdout/stderr 保存到材料指定的外置主日志。不能只取其内部 Python 命令而省略启动检查。

wrapper 核对固定 HEAD、clean、自有占用、harness SHA 与新根，记录五锁前后并比较，执行受控 offline lock-check；固定绝对解释器运行外置 harness。环境设置 UV/Cargo offline、Cargo PATH、外置 TMPDIR/PYTHONPATH，并清除代理与 Rust 覆盖变量。没有同步依赖、下载、改锁或源码步骤。

固定 harness **`p6_w4_full_diagnostic.py`** SHA256 **`62cf908f9dae3e853634c43a57b057ca9e9c07328c37ef16eedda8cc00b1dcce`**。入口只运行一次四 worker trial，不重新生成 2×，不运行 Preview/census 或旅程，不发布 receipt/INPUTS_READY。内部预算 14,370 秒、外层 timeout 14,400 秒并保留最多 10 秒强制清理余量；最终结果仍需另行核对。

## 2. 冻结来源与完整模板

程序重算 CT201 transfer.log SHA 为 `676d424e722b7e83c5f5e98247df182347dd34f00f24d47b046391f3cf4f97ad`。记录来源为历史 `input/1ed24d38f0`，`04:24:40Z–04:24:41Z`，来源前后与目标摘要一致；再读取 CT201 实际 summary/包，比较这些记录全部 MATCH。审核没有自行回读 CT108 的计时节点。

05 三个冻结文件的实际摘要、大小与 accepted summary 程序比较通过；文件 mode 0400，来源目录 mode 0700：

| 文件 | bytes | SHA256 |
| --- | ---: | --- |
| input-summary.json | 246,987 | `c31c18f6d17147b3edbfb0e0655c5edd8db99245318acd05f433e2b12e1b3227` |
| rd-t4-d-v1.tar.gz | 10,652,436 | `74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c` |
| t4-2x-v1.sql | 153,875,448 | `a4b45a455d386845a49eca4b53e6fd3d18aacf51f4630606b41eedf6f3429b7e` |

审核只读流式检查包内唯一 SQL 的大小/SHA 与抽取文件一致，完整模板另有一个非 SQL 成员；未将包路径解压到磁盘。summary 的 638 表、873,863 canonical 行只作冻结记录，不替代本轮生成器的实际原始行计数。

harness 在生成前重验固定 summary/package 摘要、SQL 的 accepted 大小/SHA，并验证模板内 SQL 身份；输出必须是来源目录外的新根。每个 worker 生成并封包后，逐项比较非 SQL 成员的顺序、名称、类型、记录的 metadata 和内容 SHA，另核对包内 SQL 大小/SHA。四单元结束才比较同档首次/重复的 SQL/package 摘要；来源三文件结束再重验，不一致即失败。完整模板核验已进入实际成功路径。

## 3. 资源、停止与微型验证

初始要求 MemAvailable 至少 60 GiB，磁盘至少 `10 GiB + 8 × (SQL bytes + package bytes)`，本来源约 **11.226 GiB**。本次只读复核时约 63.086 GiB 可用内存、214.452 GiB 磁盘余量，满足初始条件；实际启动仍由 harness 重新检查，不能用该观测替代启动时状态。

循环约每 200 ms 汇总父进程及全部本次后代（含 multiprocessing tracker）的 RSS，另采集 MemAvailable、磁盘余量。RSS ≥52 GiB、可用内存 <8 GiB、磁盘 <10 GiB 任一触发即抛出资源停止；截止、普通异常或无结果进程退出也进入收束。finally 终止未完成 worker、限时 join，仍存活则 kill/join，关闭连接并保存采样；运行失败记录 failure.json，成功只发布诊断 summary。没有自动重试或换节点。

固定最终 smoke 脚本 SHA 为 `9d984d77d1375b6354152a5ba9e5a9a4cbe961e8944a4ce27a77635ef81816bf`；最终 prelaunch wrapper 为 `c3874fa2f27e4c752f86ded30beb776c821f121b859e27e5d6773d580116f912`。最终日志 SHA **`3ad4010d9a5c909d61a8ebb0cea95965446ac5ae8e9fc7bf7b9adf379bab0dc1`**，运行 `04:28:34Z–04:28:35Z`，起止完整 HEAD 均为 249，前后五锁 SHA 与本地 249 Git 内容逐项比较一致，exit 0。

审核核对脚本和已有输出：

- 60 行 fixture 的真实四单元生成/完整封包约 0.664 秒，同档重复一致；重新计算八个 SQL/package 文件 SHA，与结果 JSON 一致。非 SQL 成员保留及包内 SQL 检查实际成功。
- 三个阈值分别以边界输入测试；将 RSS limit 设为 0 走实际 trial 的资源停止路径，独立过期 deadline 走截止路径。两条路径均检查无 active worker；已有 stop 目录保存 rss-samples，没有成功 result。没有声称对真实节点施加了 52 GiB 内存压力或实际耗尽磁盘。
- 脚本静态与 offline lock-check 已成功；最终日志绑定上述最终 harness SHA。首次 prelaunch 日志也已重算 MATCH，但最终结论以新增完整成员核验后的复验为准。

以上六个脚本/日志摘要均与材料程序比较为 MATCH。监控是尽力机制，RSS 共享页可能重复、采样可能漏短峰；审核通过不等于承诺不会 OOM 或一定在四小时内完成。

## 4. 执行与后续边界

材料与 §5.4 一致，启动前核对条件现已满足。实施者可按原授权在现有自有计时占用下执行固定 wrapper 一次；不得改脚本/参数后仍引用本次固定摘要。资源/截止失败保留记录并收束，不自动重试；正常完成后保存源/输出身份、每任务 CPU/墙钟、聚合资源、进程清理和占用释放记录，另交结果复核。

这次只测 full4，无同条件 full2，对结果不能计算全输入加速比，也不能以 CT108 的完整生成/验收耗时作分母。当前 CT108 运行、已接受 CLI/default 和正式输入验收口径均不变。不触发冻结产品镜像重建，没有新 image revision/source-tree 或容器/基准验收声明。

本轮只提交范围与启动审核文档；不启动、不合入工具、不推送、不打 tag、不改设计正文。两个审核 worktree 在确认 clean、HEAD 不变后清理；05 的实施占用与制品不由审核方删除。
