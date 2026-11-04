# Phase 6 重建对照基准：H3 provenance 定向复审 1

- 结论：**通过，F1 关闭，无阻塞项；可按原授权恢复 H3 缓存准备及正式 H3。** 本结论接受工具修正与恢复流程，不评价尚未产生的 prime/H3 运行结果，也不是基准终审。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 对象：`p6-baseline@322b7b53158b0ecf1b6680b04dc0406e7b8f3b34`；代码提交 `a5e935e1748bdd97281a4919ec91e9c60e108ac1`，runbook `76e95950f8`，handoff `322b7b5315`。定向范围 `95b1d4b1c4..322b7b5315`，此前已补核的 `9bf9b02701` 文档差异不重复审核。
- 依据：[初审及 handoff 补核](p6-baseline-h3-provenance-review-1.md)（`379c50dc2f`、`460e9b7ad1`），DC66 第 5 项、DC68、DC73；既有两阶段恢复边界不变。
- 方法：clean detached worktree `/home/dev/gdds-p6-h3-rereview-322b7b53` 只读审核；完整 HEAD、detached、clean 与文件差异均由程序比较。节点只读读取指定日志及 HEAD/status、检查输出路径是否存在；未取占用、未写节点、未运行测试或产品。

## 1. F1 关闭核对

| 项目 | 结果 |
| --- | --- |
| 复制来源仍严格绑定 | `compare_target()` 保留 source final digest、source→target 卷名映射及 `parent.copied_volume_digests` 精确判等；`real_dump_journey` 复制前后校验未改。未排除 mtime、文件或其他摘要字段。 |
| checkpoint 独立核验 | 仅去掉 checkpoint 与启动前 copied digest 的跨时点判等。仍要求 history 前、completed_through=v2-approve、恰好三卷；底层 `_resume_checkpoint_state()` 校验 run/state 记录、快照卷集合与 retained volumes、路径及已完成步骤；`_verify_checkpoint_snapshot()` 重算每个实物快照并核对完整摘要。 |
| 状态与语义屏障 | checkpoint steps、目标 history 前 state、来源去掉 history 后的 state 仍相等；输入 manifest、parent run/state/log SHA、比较 commits/rules、镜像、缓存完整性与原 TTL 的检查未变。 |
| 正例 | final-state fixture 在 service_state 目录创建并删除探针，保留目录 mtime 变化；比较结果 MATCH，且显式断言 checkpoint digest 与刚复制卷 digest 不同，直接覆盖初审误拒绝路径。 |
| 负例 | 分别破坏 `copied_volume_digests` 与 checkpoint 实物文件，仍被对应校验拒绝。原来源、恢复模式、输入等拒绝用例保留。 |

这是 DC66 第 5 项工具修正，没有修改产品、计时器、输入、Contract、golden 或已认可的恢复语义；不要求重测已完成的 H2。

## 2. runbook、handoff 与验证证据

runbook 只把最初 source preflight 输出改为 `/home/dev/gdds-p6-logs/baseline/scenarios/h3-source-check-cacheprep-20261104c.{json,log}`；保留两项 `test ! -e`。本次只读检查两路径均尚不存在，旧 `h3-source-check-verified.*` 与 `h3-source-check-f1-verified.*` 不被覆盖。17 个 Bash blocks 独立执行 `bash -n` 全通过，`git diff --check` 通过。其余启动解释器、manifest 双绑定、新 project、离线/无代理、V′ 身份及停止规则沿用初审已核对的命令。

程序比较 `a5e935e174..322b7b5315` 仅有 runbook 与 handoff，已验证的代码/测试未再改变。ct108 指定 worktree 当前仍为 `a5e935e1748bdd97281a4919ec91e9c60e108ac1`、status 空；实际运行记录应继续准确区分工具 HEAD 与文档提交，不把文档候选写成未经执行的测试 HEAD。

本轮从节点读取实际字节并重算 SHA256：

| 文件 | SHA256 / 结果 |
| --- | --- |
| 05 `/home/dev/gdds-p6-logs/baseline/h3-review-fix-a5e935e174-ct05/validation.log` | `8d36525dbc14281faceecf4bb81e4ff28887dd7759507f5f26f953751e2edb5f`；hostname gw-dms-test-05，12:33:42Z–12:33:46Z，起止 HEAD 均为 a5e935e174 完整 SHA，165 passed，五包 ruff/mypy 全部 exit 0，overall exit 0，结束 status 空。 |
| 同目录 `preflight.log` / `postflight-release.log` | `0fe9bebfe34bb7300db8b9820f73a6f91f88a6c50833081b59b1117fa35d869e` / `b85279f2a28539d58768b5ee84d362a72c5f3f47b5122a0138c6ea54ef2bf5d8`；与 handoff 一致。 |
| ct108 `/home/dev/gdds-p6-logs/baseline/scenarios/h3-source-check-f1-verified.json` / `.log` | `d309f95b2d741af6f1b77f85e1ab8443105602c4b0a8cd6783b68fc3af354a43` / `679e712db8697666751c3d3c602ae0e593249c55ccd8c6d6aee5b75679bf626a`；RESULT=MATCH，purpose=cache-preparation，原/目标 manifest SHA 一致、3 卷。 |
| ct108 `/home/dev/gdds-p6-logs/baseline/h3-review-fix-a5e935e174-ct108/source-check-execution.log` | `fe3a319768066e3194207736a08c282731e30df748b33db9c0ecd915738882d2`；hostname gw-dms-test，12:35:01Z–12:35:03Z，start HEAD 为 a5e935e174 完整 SHA，exit 0。报告内容不变由输入与 source 检查未变解释，不能据相同报告 SHA 冒称旧执行用了新代码。 |
| 同目录 `postflight-readonly.log` | `c54f0bf5b457dd09baf8b9dba5ea62aba1b8dc62e1ed0ee962a056a0cc4db758`；记录候选 HEAD、clean、node_lock=ABSENT 与 source MATCH。 |

这些是修订验证及来源预检；本会话未独立重跑大体积 source 快照遍历，也没有 prime/H3 的运行结果可供接受。

非阻塞记录勘误：handoff 将初审报告 SHA `b94303ab1c5c4f48c04ecfd6098d79d659ce10f15d16a39f7ff28bde76e5ed60` 绑定到 `379c50dc2f`。从 Git blob 程序重算，该 SHA 实际属于补核后的 `460e9b7ad1`；`379c50dc2f` 对应 SHA 为 `db1d7a457fa98f5856db91f23fbb2e5a5cb3984a46e7552d92f9cd31fffacf8f`。下次 handoff 更新时纠正引用提交或摘要即可；这是审核文档引用错配，不是被测输入或镜像身份不符，不阻塞本轮恢复。

## 3. 恢复边界与镜像判定

可按原授权和固定 runbook 继续：先确认 ct108 空闲、取得测量占用并做来源 preflight 和 V′ 完整镜像身份比较；用新的 project/证据目录执行 cold checkpoint→prime。prime 成功、来源关系和健康缓存/TTL 校验通过后，再复制成功最终三卷执行正式 H3，完成同一 manifest 的目标比较及 `compare-target`。准备、复制和 checkpoint 不计入 History operation timing。保留全部旧失败与审核证据，不重跑未受影响的已完成场景。

本轮不触发产品镜像重建，冻结产品仍为 `p6-s1c-exit` 的 S1c V′；最后接受的 backend/worker config digest 为 `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1`，全部 15 个 DiffID 仍须启动前程序比较。工具 HEAD 不作为新产品 image revision；本报告不宣称当前候选容器门禁或 carried。

新失败继续适用 DC66/DC68、缓存/身份与 runner 停止规则；预计剩余超过 48 小时仍停交 owner。H3 结果须后续证据复核，基准终审与最终 04 runner 尚未完成；S2a exit 仍等基准 exit。未推送、未办理 tag/合入/阶段 exit。
