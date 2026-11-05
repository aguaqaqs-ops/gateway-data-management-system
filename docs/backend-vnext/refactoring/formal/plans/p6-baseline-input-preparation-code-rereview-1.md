# Phase 6 基准输入准备工具：代码定向复审 1

- 结论：**代码复审通过，F1/F2 闭合，无新增代码阻塞项；实施证据待复核，尚不启用新工具。** 最终 focused/静态日志及 handoff 尚待交付，不能以本报告替代工具证据接受结论。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 修正候选：`249c09d0824c5d9716f02f7deb1bb8c154ea4c98`；相对已审 `e08cabdb234e0ba77331660fc2d096dad97bd12e`，仅改 `p6_baseline_inputs.py` 与 `test_p6_input_preparation.py`。
- 依据：[代码审核 1](p6-baseline-input-preparation-code-review-1.md)（`1a5202e08f`）、[工具 kickoff](p6-baseline-input-preparation-kickoff.md)（最新设计 `b184b25eeed77a7d1377594b109ded06bc2be6ee`）、DC66/DC73/DC79 与 AGENTS。
- 方法：在 `/home/dev/gdds-p6-input-tool-rereview-249c09d0` clean detached worktree 只读审核。程序核对完整 HEAD、detached、clean、祖先关系、改动路径及源码对象/AST；未访问 05 或 CT108，未获取占用、运行测试或读取在跑的证据。

## 1. 修正核对

| 项目 | 复审核对 |
| --- | --- |
| F1：子进程直接退出 | `p6_baseline_inputs.py:240–313` 改为固定两个 spawn Process，各自使用独立单向 Pipe。父进程同时等待结果连接与 process sentinel；子进程退出且没有结果时，经 poll/EOF 分支报 `InputPreparationError`，不再由 Pool 补充 worker 后等待丢失任务。普通异常回传后也进入同一个 finally；失败时 terminate 存活子进程，然后 join/close 全部本次进程和 reader。正常完成同样 join/close。不增加重试、替代 worker 或任意运行时长阈值。 |
| F1 定向用例 | 新增 serial 用例让真实 10% 段在同一个失败根完成 receipt 后，100% 子进程直接 `os._exit(19)`；以有界测试等待验证父调用结束、没有新增存活子进程、不发布 summary、不产生失败段 receipt，再从本次失败根复用已完成的 10% 段。原普通异常、1/2 路输出字节一致与 worker 数量边界用例保留。这是源码覆盖核对，运行结果待最终日志。 |
| F2：来源根不变 | `prepare_inputs` 在任何 mkdir/复制/预检前，对输出和 reuse root 分别 resolve，并用包含关系拒绝输出落入来源根。覆盖原报告中的直接嵌套和 symlink 别名；复用来源同路径也被拒绝。两个公开入口用例断言错误发生于写入前、来源文件内容不变且没有 retry 目录。没有引入同 euid 对抗性模型。 |
| 完整成功路径 | 新用例通过真实有界 SQL 生成参考包和 accepted summary；调用公开 `prepare_inputs(..., phase="generate")` 后确认没有最终 summary，再以新根 validate 复用三段，执行真实完整 Preview/census 路径后发布 summary。断言四项 Preview COMPLETE、pair 关系、重复封包通过、census 摘要及三种 journey root；没有 mock 掉验收函数。其运行结果同样待日志复核。 |
| 设计澄清 | `b184b25eee` 已明确预检只消费 SQL bytes，不覆盖封包/staging；封包由独立回归和完整生成验收承担。与实际实现及首次报告建议相符，首次报告的设计澄清项闭合；完整原包 business/canonical 验收未削减。 |

本轮没有改变生成算法、receipt 身份/复用规则、完整验收或 READY 条件。停止规则、默认单进程、最多两路及当前 CT108 固定运行版本不变。

## 2. 真实来源预检的适用范围

程序比较 `e08cabdb23..249c09d082`，以下 11 个文件/树对象全部相同：

- 六个 benchmark 模块：`p6_input_preflight.py`、`p6_input_stages.py`、`p6_s1b_synthetic_load.py`、`p6_w4_synthetic.py`、`p6_w4_input_stage.py`、`real_dump_census.py`。
- `vnext/backend/src`、`vnext/shared_kernel/src`、两个包的 `uv.lock` 与 backend `.python-version`。

`p6_baseline_inputs.py` 的 AST 变化限 `_generate_w4_stages`、新增 `_w4_stage_child` 和 `prepare_inputs` 的来源路径检查；`_read_package_sql`、`_generate_pair`、`_validate_generated_preview_materialization`、`main` 均未变。因此，对于原合法外置根、原参数下的 `--phase preflight`，F1/F2 修正不改变 SQL 预检算法及相关依赖，无需仅为本次修正重复真实来源调试。

这只是证据适用范围核对。此前转述的 e08 真实来源预检 exit 0、耗时 282.472 秒、日志 SHA `3bbdce9d15aa13b104ef6960c04c2a65d80bf43b02d81b29a70e20605160a8cd` 与 JSON SHA `ae53a7172ec111668d39e39b76c93904f4ea4dd2ef65c9c8f45d8b08c5a88f96` 尚未由审核方读取重算；不能在最终 handoff 改称该运行发生于 249。原包装命令 exit 127 及重做记录也需一并核对。

## 3. 静态核对、镜像与待交付

候选 `vnext/` tree 为 `25fe7febbb9aa284c00a980a31b5c102748cafc8`；`git diff --check e08cabdb23..249c09d082` 通过。无产品源码、golden 或依赖变化。本轮不触发冻结产品镜像重建，没有新 image revision/source-tree、容器门禁或 carried 结论。

后续交付最终候选 focused/五包 Ruff/mypy、独立 handoff、已有真实来源预检及命令失败/修正日志；审核按起止 HEAD、exit、SHA、预检输入身份与上述未变范围做证据复核。无需为这次复审重跑全部产品 runner、大输入生成或未受影响的基准场景。当前 CT108 原任务继续，不等待或切换本工具。

仅按显式路径提交本报告，不推送、不改设计正文、不打 tag 或办理 exit；审核 worktree 在确认 clean、HEAD 不变后清理。
