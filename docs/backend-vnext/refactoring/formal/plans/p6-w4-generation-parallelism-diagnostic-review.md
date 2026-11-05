# Phase 6 W4 两路与四路诊断：定向核对

- 结论：**诊断记录、计算与解释范围通过，无阻塞项。** 本有界样本的四单元工作在四路下平均墙钟缩短 49.62%，同时 worker RSS 采样峰值约翻倍；支持“值得继续评估四单元调度”的结论，不构成正式四路实现/启用、默认值调整或全量性能验收。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 报告候选：`ebaf523aeeaea073e301a94e66243f3308c08aac`，`p6-w4-parallel-diagnostic` 分支的 [诊断报告](p6-w4-generation-parallelism-diagnostic.md)；该文档尚未合入 main，引用以提交为准。
- 设计边界：`c4f36ef2846c4ac1b26861dea21cc324018607c5` 的 [kickoff §5.3](p6-baseline-input-preparation-kickoff.md#53-四路可行性诊断)。实际调用的工具代码仍为已接受的 `249c09d0824c5d9716f02f7deb1bb8c154ea4c98`。
- 方法：在 `/home/dev/gdds-p6-parallel-review-ebaf523a` clean detached worktree 审核，程序比较完整 HEAD、detached、clean 和 docs-only 改动。05 先 BatchMode SSH 确认连接，随后只读已有脚本、日志、JSON 和制品，未取占用、未重跑或执行诊断脚本，未访问 CT108。真实数据只输出计数与摘要，核对程序经 stdin 执行，未留下临时脚本。

## 1. 范围与身份

报告提交只新增一个文档，与其父提交的 `vnext/` tree 相同；`git diff --check` 通过。报告分支的代码树不是诊断所调用的工具树，两者没有混用：实际日志起止 HEAD 均经程序比较为 249，05 保留测试 worktree 当前仍为相同 HEAD 且 clean。

脚本实际只读调用 `_make_w4` 与 `repack_source_package`。每轮四单元分别为 10% 首次/独立重复、100% 首次/独立重复；两路每个进程顺序执行同档两份，四路每进程执行一份。四轮按 2、4、4、2 执行，均使用新子目录，没有用复制替代重复生成，没有嵌套池、Preview、census、Dolt 或正式旅程。模板仅含一个 `sql/dbcfg.sql` 成员，解包后摘要与来源 SQL 相同，不包含 XML/business 关系。

来源 SQL 大小 3,026,734 bytes，SHA256 `c4d6ca618fbbea3f7f5c40b58926a9d9795108d9463be88b4f48d19142019ac9`；模板 SHA256 `14bfc7dd188b1824c3744e32e20ff067ebf3a7f3b365192ce9cba7c2f57221bb`。均读取实际字节重算相符。每单元记录 638 张表、15,482 行输入；本次核对不重新验证样本的完整业务语义。

脚本内部预算 570 秒，外层硬 timeout 600 秒；harness 总墙钟 278.545996 秒，外层 279.177 秒，exit 0、DIAGNOSTIC_COMPLETE。没有触发预算退出。脚本的异常/超时路径终止并回收本次进程，成功运行的回收另由 postflight 核对；本轮不声称额外执行过超时故障注入。

## 2. 原始制品与计算复核

程序逐项重算 16 个单元的 SQL/package 大小与 SHA，共 **32 个文件**；核对每单元 JSON、四份 result.json 与 summary 对应内容一致。同档首次/重复、跨轮及跨模式的实际字节摘要全部相同；两个 rate 不要求彼此相同。各轮 PID 数分别为 2、4、4、2，共 12 个 worker。

读取四份 `rss-samples.json`，分别含 1835、930、925、1849 次记录；按每个采样时刻求 worker RSS 之和，再取最大值，结果与 summary 完全一致。parent+worker 峰值也逐轮重算一致。这不是各进程高水位相加，仍有 RSS 重复计算共享页、约 50 ms 采样可能漏短峰的限制。

| 次序 | worker 数 | 墙钟 s | 已记录子进程 CPU 总和 s | 重算 worker RSS 峰值 MiB |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2 | 92.231410 | 182.329400 | 432.816 |
| 2 | 4 | 46.809863 | 183.845321 | 861.305 |
| 3 | 4 | 46.477214 | 183.297329 | 863.555 |
| 4 | 2 | 92.951901 | 182.588070 | 433.242 |

从原始数值重算：两路平均墙钟 92.591655 秒，四路 46.643539 秒；`1 − 四路/两路 = 49.624469%`，同工作量吞吐比 `两路/四路 = 1.985091`。平均子进程 CPU 总和分别为 182.458735、183.571325 秒，未随墙钟缩短而减少。CPU 数值来自脚本记录的 getrusage，自身运行及导入在其中；审核核对其跨层一致性与算术，不宣称另有独立 CPU 采样器。

最大单进程 RSS 高水位约 217.484 MiB；两路和四路的同时 worker RSS 最大采样值分别为 433.242、863.555 MiB。含父进程的对应最大采样值为 533.961、964.273 MiB。报告的舍入值与这些结果一致。

## 3. 环境、失败记录及释放

provenance 与 summary 的公共字段程序比较完全一致。记录节点为 05，affinity 64、可见 `cpu.max=max 100000`、`memory.max=max`、MemTotal 64 GiB；这些是当时该节点可见资源，不是 CT108 的性能或全层级资源保证。实际使用 retained backend `.venv/bin/python` 3.14.6；shell 显式设置 offline、TMPDIR、PYTHONPATH，清除代理，先受控 lock-check，再用既有绝对解释器调用外置脚本，无环境同步或下载步骤。

首次 `uv-consume run` 因外置脚本路径被拒绝，exit 2，未进入 harness；失败日志保留。已有授权明确要求外置诊断脚本，修正为 lock-check 后显式解释器调用一次，未修改或削弱 wrapper。不得表述成 wrapper 执行了诊断；报告已正确区分。这次命令纠正和成功重做符合本诊断范围及 DC68，不要求重跑。

报告明确缺少专门的执行前五锁 SHA 行。程序分别把运行中、运行后记录的五锁 SHA 与本地 249 的五个 Git 文件内容摘要比较，全部相同；起始 clean 和 lock-check 提供其实际记录的前提，但不能将运行中补录改称执行前采集。对本次不变源码的有界诊断，该已披露缺项不阻塞结果解释。

postflight 于 `2026-11-05T03:27:10Z` 记录的 12 个 worker PID 集合与单元结果一致，remaining 为空；来源未变、worktree clean，释放自己的占用。核对时节点 busy marker 不存在、保留测试 worktree 仍为 clean 的 249。已保留诊断制品不在本轮删除。

## 4. SHA 核对及结论边界

报告表内七个文件及首次失败日志，共八项 SHA 均重新读取字节后与报告程序比较为 MATCH。核心绑定为：

- 外置脚本：`2046e5c7e156571b06a65ea61aa078632ea0ac57cd3d9f3d2c096d2e2aec24ac`；修正后 shell：`6eed586a099a608c5af24b0f9b50c58dfc7836e0396a937595c96caeee1df1e5`。
- 成功日志：`52aef15dd3764c6430b326717a76ae68a0800a921c61cd161a47e62b40b4eae3`；summary：`cf2fb29bcc40db06bc35cf0c1e27961da1462b62e4a1fb8d0c8365ca8c0ff215`。
- provenance：`c6f09924805f5d0b396221b74512ca34ac9a48b669c3698d426c163e7e109567`；运行中环境：`5f32546ec6740592139a4140ed9871813f4a091ce892b61e8e5f574b1b18af62`。
- postflight：`627c63d677e6fabefd2b1b6533f6a0d883ccbfdb5a45039c6c23937aaee197ab`；首次失败：`3bc7261e76fb12cc52afa1a11f4324bc91988e3688aa11b7df40221a3da29e4f`。

接受报告对本样本独立生成/重复封包单元有明显收益的解释。每模式仅两轮，没有置信区间或尾延迟结论；SQL-only 模板未测完整原包/XML 封包成本，未测全量内存、CT108 或整个输入准备流程。现有正式工具只有两个 rate 任务，单纯把并发参数上限改成 4 不能获得本实验四个独立单元的调度收益。是否正式拆分及采用四路交后续设计/实施处理，不由本次诊断自动生效。

已接受 1/2 路工具结论保持不变；本轮没有修改 CLI/默认值、输入接受条件或当前 CT108 运行，也不新增真实输入/基准门禁结论。不触发冻结产品镜像重建，没有新的 image revision/source-tree 或容器证据声明。

本轮仅按显式路径提交审核报告，不合入诊断分支、不推送、不打 tag 或办理 exit；不改设计正文。审核 worktree 在确认 clean、HEAD 不变后清理。
