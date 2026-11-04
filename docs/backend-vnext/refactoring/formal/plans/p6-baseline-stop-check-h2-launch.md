# Phase 6 重建对照基准：H2 三节点 launcher 停止复核

- 结论：**启动命令错误，尚未触及被测产品；第二次失败后停止正确。** 建议修正命令与过时 runbook 示例，owner 放行后重新启动 H2 三节点。不是产品缺陷，不需要修改 Contract 或新 DC；本报告不代替 DC68 第 3 项要求的 owner 放行。
- 日期：2026-11-04；审核会话：`p6-backend-review`（DC73）。
- 对象：`p6-baseline` handoff `d4f1cbae54` 的“2026-11-04 W4 KEY_EMPTY 修正与 H2 三节点预检停止”；工具 `e0768fbeae`，产品 `p6-s1c-exit`，project `p6bwh2threenode20261104a`。
- 方法：clean detached worktree `/home/dev/gdds-p6-baseline-stop-review-d4f1cbae` 只读审核；ct108 仅读取既有日志、占用标记与容器列表，未取占用、未启动测量或测试、未写被测 worktree。

## 1. 证据与失败位置

证据根：ct108 `/home/dev/gdds-p6-logs/baseline/scenarios/ct108-independent-2x-20261104a/`。审核以程序重算以下八项 SHA256，与 handoff 全部相符；副本及 `hash-audit.json` 保存在 CT201 `/home/dev/gdds-p6-logs/baseline/h2-launch-review/`。

| 文件 | 结果 / SHA256 |
| --- | --- |
| `launcher-h2-three-node.log` | 00:21:04Z，exit 1；`cf5cdd8349c230199512c4e57461cb044167666bbff0157dff1a425a2ddfdfb8` |
| `launcher-h2-three-node-attempt2.log` | 00:22:53Z，exit 2；`4fc19473f3b2c69f01de93d3d0de51d0e84b099891d93fdd7171c2099a60c8e7` |
| `h2-three-node-postflight.log` | 无 project 容器、旅程/Dolt 进程、8000 监听，无 launch/resources 文件；`13540b4ff1f5b8dc6a650a31c9081d23deb9d341741556fefc97a5b53a4e8d48` |
| `cleanup-postflight.log` | 清理后无测量进程，00:31:22Z 释放占用；`75cea7b31f7497bb67f22109bbd8a1ef6a1425cd6d6da35a39089502cb2e6b9b` |
| `accepted-2x-input-check.log` | MATCH；`b75ec3fbcf9b972aa04d861c06b3ffc8556d6a7f57ddff444c7a756b3bc2bc7e` |
| `image-identity-h2-three-node-attempt2.log` | 两镜像 config digest 与全部 15 个 DiffID 比较通过；`0b590aa90a0f0aa0634c0a6443fdf8b137bdbc0b57fb06438a4dd077c861d9c9` |
| `product-tree-identity-corrected.log` | 六个产品 tree 与 S1c 一致，审核程序再次对 Git object 比较通过；`de02815fdc56a07a8a0ba7e808c4416b9f76be3329c428e3e9a15cdc62aaf217` |
| `h2-three-node-input-manifest-preflight-attempt2.log` | MATCH；`51a4e54739d339c5b9c7343ef16dfc2335c8c9ea61e025787052122b85c439fb` |

两次 launcher 起止 HEAD 都为 `e0768fbeae16755adcf2d5cc5532f1ab28492303`。

1. 第一次直接执行 `benchmarks/p6_baseline_resources.py`，导入 `benchmarks.p6_baseline_input_manifest` 时 `ModuleNotFoundError`，未进入 main。
2. 第二次改为模块调用，进入 `_launch_metadata` 后报 `formal journey must use this worktree's backend .venv Python`。该函数要求 child command 的首项为仓库根下 `vnext/backend/.venv/bin/python`（或相对仓库根可正确解析到它的路径）。拒绝发生在资源采样与 `subprocess.Popen` 之前。
3. 源码允许此处创建/调整日志父目录权限，不能笼统称绝对无文件系统操作；没有产品、卷、Dolt/control DB 或测试运行的证据。没有可续跑 checkpoint，也没有可接受的计时结果。

## 2. 命令与文档问题

`p6_baseline_resources.run_sampled` 把 `--worktree` 作为仓库根，并在其中启动 child。当前 runbook “Evidence journeys and step-scoped resume” 仍把 WORKTREE 写成 `vnext/backend`，child 使用 `uv-consume.sh`，且两段示例缺少 sampler 必填的 `--expected-input-manifest`。这些示例与当前 launcher 检查不一致，照抄会再次失败。

建议实施方按 DC66 第 5 项修正该 runbook 的 fresh/resume 示例：sampler 从 backend 目录以模块方式运行；`--worktree` 指向仓库根；child 首项使用该 worktree 的 backend `.venv/bin/python` 绝对路径，随后给 `real_dump_journey.py` 绝对路径；sampler 与 child 引用同一期望输入清单。保留已有场景、census、evidence、镜像、离线与不经代理设置。不要删掉解释器或输入身份检查来使错误命令通过。

此次无须产品代码修复。若实施方另改 benchmarks 工具或测试，按 DC66 第 5 项完成 05 focused 与五包静态检查并记录提交；审核方不代写工具或 runbook。

## 3. 处置建议与边界

1. **owner 放行前保持停止**。本项是启动测量的步骤，不能因内部拒绝发生在 Popen 前就把连续两次启动失败改称无限次只读预检。DC68 第 3 项已触发；实施方没有继续 W4/H3，处置正确。
2. 建议 owner 允许实施方按 §2 修正后重启 H2 三节点，使用新的运行日志/证据路径，保留两次失败记录。启动前只读核对命令展开后的仓库根、child 解释器、清单、输入与镜像身份；正常取得测量占用后运行。不得启动产品来冒充只读预检。
3. H2/H3 不依赖无效 W4 输入。W4 的重新生成与验收仍按 KEY_EMPTY 停止复核 §4，不因本次 launcher 修正改变输入或验收范围。已通过的其他场景无需重测。
4. 最新剩余估计 19–35 小时，低于 48 小时；恢复时更新估计，超过阈值仍停交 owner。本次不审核 W4 生成修正的最终正确性，相关提交与完整测量留待基准终审。
5. 本轮只有审核文档，不触发镜像重建；最后核验的产品镜像仍为 S1c V′，不是当前 main。基准 exit、S2a exit 均未办理，无推送。若要放宽“第二次失败后须 owner 放行”的规则，**交设计会话**，本报告不作规则修订。


## 4. 设计处置转交后的定向核对（2026-11-04）

结论：失败位置与无产品运行/无残留的历史证据已核对通过；**修正后的完整启动命令尚未提交，恢复前的定向审核尚未完成**。

本次收到 owner 转交的设计建议后，检查 `p6-baseline` 仍停在 `d4f1cbae54`，工作区 clean，相对该提交无新增变更。现有 runbook 仍为 §2 所述版本，不能把设计建议当作已经落实的命令修正。失败证据沿用 §1 的已核结果，不重复读取真实数据或启动场景。

实施方下一步仅固定现有 runbook/启动脚本中的完整调用：明确 sampler 工作目录、仓库根、解释器绝对路径、journey 路径、同一期望输入清单、census、project、evidence 与既有场景参数；解释器保留 `.venv/bin/python` 的路径身份，不经 realpath/readlink 解析成系统 Python。只读核对参数不得启动 sampler 的正式运行。若修改工具代码，按 DC66 第 5 项完成 05 focused 与五包静态检查。

提交后交本会话只审该命令修正及必要验证；通过后给 owner 一次性恢复授权 prompt。恢复范围仍为 H2 三节点从头、H3 使用已接受 2× 输入、W4 新目录生成并通过既定全表生产投影/身份/确定性验收后运行 W4/S4/H1、FULL、STRESS。旧 W4 输入保持作废，已完成场景不因本次启动错误自动重跑。无需重建基准、修改产品或放宽 DC68。本节不是恢复授权。
