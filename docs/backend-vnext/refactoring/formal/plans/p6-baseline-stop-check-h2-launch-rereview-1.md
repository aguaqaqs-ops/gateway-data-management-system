# Phase 6 重建对照基准：H2 启动命令定向复核 1

- 结论：**通过，无阻塞项；可交 owner 一次性授权恢复原范围测量。** 本报告只接受启动命令修正，不是恢复授权，也不是基准终审。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 对象：`p6-baseline@0fba15d1d86433debf5079808b1ddab36eb9ca36`；相对 `d4f1cbae54` 仅修改 measurement runbook 与 baseline handoff。
- 依据：[H2 停止复核](p6-baseline-stop-check-h2-launch.md) §2、§4，owner 转交的设计处置建议；DC66 第 5 项、DC68。
- 方法：clean detached worktree `/home/dev/gdds-p6-h2-command-review-0fba15d1` 只读审核。未运行产品、pytest、sampler、journey、Compose 或测量；ct108 只读查询既有 identity helper 与指定 worktree 的 HEAD/status，未取占用、未写节点。

## 1. 定向核对

| 项 | 结果 |
| --- | --- |
| 改动范围 | 程序比较文件清单，仅 `vnext/backend/benchmarks/p6_s1b_measurement_runbook.md` 与 `p6-baseline-handoff.md`；没有工具实现、产品、锁或 Contract 改动 |
| Bash 语法 | 独立重做 `git diff --check`；提取 runbook 12 个 Bash fenced blocks，仅执行 `bash -n`，12/12 通过，不执行命令内容 |
| 工作目录与解释器 | sampler 在 backend 目录以模块启动，`--worktree` 为仓库根；sampler/child 使用同一个绝对 `.venv/bin/python`，没有 realpath/readlink 解引用；child journey 脚本为绝对路径。与 `_launch_metadata` 的词法路径检查及 child `cwd=worktree` 一致 |
| journey 导入 | `real_dump_journey.py` 在导入 benchmarks/tests 前显式加入 backend 路径；从仓库根执行其绝对脚本不会重现首次 sampler 的模块导入失败 |
| manifest 双绑定 | H2 sampler 与 journey 各传一次同一 `EXPECTED_INPUT_MANIFEST`；程序比较 root/census/manifest 三个路径与上轮已接受预检记录，3/3 一致 |
| H2 参数 | t4、默认 full、synthetic census、fresh、cold、three-node、MODIFIED_ONLY 与既有清单 scenario 一致；没有 full-v2、cross-project、resume 或 keep-stack 的冲突参数 |
| checkpoint | AST 读取 `JOURNEY_STEP_IDS`，25 项不重复且均受支持、均非首步；是既有 H2 参数的固定，不新增审核 checkpoint |
| 镜像与缓存 | 保留 project-specific V′ retag、完整身份 checker、PREBUILT、既有 composite cache、offline 与无代理设置；只读核对 helper 接收“期望 JSON + 两个 image tag”并在不符时非零退出，与示例相符 |
| 运行后核对 | 保留同一 manifest 对该次 `state.json` 的 `compare-state`；保存比较退出码与 SHA，MATCH / NOT_UPLOADED / MISMATCH 分开处理；无 state 时按正文记录启动拒绝，不伪造比较 |
| fresh/resume | 两段通用示例同步纠正根目录、解释器与清单绑定；不构成新增场景或续跑授权 |

指定 ct108 worktree 当前仍为 `e0768fbeae16755adcf2d5cc5532f1ab28492303`，status clean。runbook 的命令文档提交与实际工具 HEAD 分开记录是合理的：本提交没有工具源码变化，不要求仅为文档切换被测 worktree。后续若使用新 worktree，所有路径须一致替换并重新核对身份。

历史失败位置、无产品启动与当次无残留的证据沿用停止复核 §1；此次不重审已处置的 W4 问题、不重跑既有场景。节点当前 clean 不代替恢复前的占用与残留检查。handoff 保留停止状态，没有把文档提交或静态验证写作测量放行。

## 2. 验证范围与镜像判定

本轮只有文档/命令静态核对，不需要 05 focused 或五包静态检查；没有执行工具实现，不宣称动态启动成功。若之后修改工具代码，仍按 DC66 第 5 项执行验证。Bash 示例是受既有停止规则约束的操作步骤；启动失败后应单独完成日志保留与只读后处理，不因为 shell 的 `set -e` 结束而漏记退出状态。

不触发镜像重建。最后接受的产品镜像身份仍为 S1c V′，见停止复核 §1，不能解释为当前 main 或本次文档 HEAD 的产品门禁。此次没有重新导出或比较镜像，也没有启动测量。

## 3. 供 owner 授权转交的恢复 prompt

以下文字仅在 owner 明确授权转交后生效；实施方不得仅凭本审核报告自行解除 DC68 停止。

> 授权 `p6-baseline-measure` 依据本定向复核，通过本次 DC68 停止点并恢复既有基准任务。使用 `0fba15d1d86433debf5079808b1ddab36eb9ca36` 中固定的 runbook 命令，不临时更换调用方式或削弱检查。
>
> 恢复前确认 ct108 空闲并取得占用，使用 clean 已提交 worktree；核对展开后的仓库根、backend 目录、字面的 `.venv/bin/python` 绝对路径、输入/census/清单与 V′ config digest、全部 DiffID。保持离线、不经代理，日志在 worktree 外记录 hostname、起止 HEAD/时间、退出码及 SHA256，真实数据只输出计数与摘要。
>
> H2 三节点从场景开头运行，使用新的 project 与证据路径，保留两次失败记录；按固定命令保留 25 个 checkpoint、timing 与 stop-on-manual-recovery。运行后执行同一清单的 compare-state，包含失败但有 state 的情形；无 state 时记录原因，不伪造核对结果。
>
> H3 使用已接受的 2× 输入。W4 在新目录重新生成，按既有 KEY_EMPTY 处置完成全表生产投影、输入身份、确定性及其他已批准验收后，运行 W4/S4/H1、W4-FULL、W4-STRESS。旧 W4 输入保持作废；不因生成器测试通过恢复有效，不重跑未受影响的已完成场景。
>
> 继续原授权剩余正确性旁证、DC63/V5b、正式 JSON/SHA、comparator replay 与 04 最终 runner；不扩大场景。更新剩余估计，超过 48 小时或触发 DC66/DC68/runner 的既有停止条件即停并报告。工具修正按 DC66 第 5 项；产品、Contract 或授权变化交 owner，不自行扩大范围。完成后提交 handoff 交基准终审。本授权不含推送、tag 或阶段 exit。
