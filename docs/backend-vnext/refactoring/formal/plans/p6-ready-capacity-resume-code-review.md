# Phase 6 READY 容量限定恢复接线审核

- **结论：修订后的实现范围与静态逻辑通过，未见剩余阻塞 Finding；05 focused/五包静态证据待补，尚不是完整代码验收或恢复放行。**
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 初版：`a1f7c27d0df15dc1e8441ca64d65e4ec2007a754`；复审：`41383218046bcd6a398ee1a7feeb6a60cc57e83d`。
- 工具改动基线：`8132f1bfa6c657d2baa75ea5c51c1f86bc23c5ff`，为已审产品容量修正在 baseline 上的提交。
- 依据：DC80、容量 kickoff、[产品审核](p6-ready-closure-capacity-code-review.md)、[停止复核](p6-baseline-stop-check-w4-ready-closure.md)。方法为 clean detached worktree 只读审核，程序核对 HEAD、detached、clean 和差异；CT108 只读核对原 run/state 元数据，未取占用、未执行工具/测试/旅程。

## 1. 实现范围与身份

工具两提交相对基线只改 `real_dump_journey.py`、对应测试和 runbook；产品文件与已审容量提交字节一致。相对原失败运行的产品变化仍恰为单处 `4_096 → 32_768`，其余差异限已列明的 benchmark、测试和文档。最初消息提供的完整 a1f7 SHA 不存在；审核以仓库分支和实施 worktree 程序解析的完整提交为准，实施者已更正，无身份歧义。

| 项目 | 静态结论 |
| --- | --- |
| 源证据 | 固定原项目、HEAD、run/state/log 摘要、v2-preview 起点、输入 manifest 与路径。审核直接读原 run/state，程序比较固定 SHA、V′ config digest、每镜像 15 层及请求 checkpoint 清单均匹配。固定 run/state 摘要同时绑定完整来源 DiffID 数组。 |
| 产品变化 | 要求已审产品提交在当前 ancestry，实际 vnext tree 等于目标身份记录，限制允许的差异路径；产品源码必须为原文件精确一次常量替换，当前产品文件及测试文件必须与已审目标相同。不是任意产品变化放行开关。 |
| 镜像变化 | V′ 来源与 H 目标各自验证 config digest 和全部 DiffID，忽略跨节点本机 image ID。目标必须匹配固定机读记录且不能仍为来源镜像。工具不声称二者相等。最终 H 的构建来源及门禁仍须另做证据审核。 |
| 恢复入口 | 专用 flag 限定 t4/full、原 W4 10% 输入、指定新项目和外置目录、v2-preview、cold Preview/healthy History、计时、手工恢复即停及后续 checkpoint 集合；拒绝 final-state、三节点、FULL-v2、debug 等混用。未启用 flag 时原同产品/同镜像限制保留。 |
| 快照保护 | 复用原来源 loader、失败前步骤 PASS 判定、checkpoint state 与 run 的公共字段比较、三卷快照摘要和新卷复制后摘要；不改原证据，不把失败末态作来源。新预检身份失败在卷复制/Compose 前拒绝，完整输入预检仍保留。 |
| 分段来源 | 复用原 step_checks 的 source_head/source_log；续跑步骤绑定当前 H。新 run/state/parent_source 补充本次源/目标关系和身份文件摘要，不伪造全程在 H 上执行。 |

目标身份 JSON 是本次固定来源到固定目标的机读绑定，生成入口要求 clean worktree、预置 H 镜像并从 Docker 程序取得身份；不存在可接受任意项目/产品的通用批准机制。JSON 目前尚未生成，不能把入口存在视为目标镜像已通过。按 runbook 在 04 验证后生成、只提交该文档路径，最终 HEAD 的按包/镜像沿用仍遵循 AGENTS，不能因 vnext tree 相等自动跳过闭包规则。

## 2. 修订与测试审查

初版静态发现两项测试 fixture 缺陷，已直接反馈并在 413832 修正，没有削弱生产校验：

1. “目标仍为来源镜像”测试同时提供了绑定另一目标的 approval，先触发目标不符，无法到达预期分支；修订让该用例的 approval 同样绑定来源，正确触发来源镜像拒绝。
2. source evidence fixture 使用合成 config digest，却未同步测试内固定的 V′ config 值，成功分支将被生产检查拒绝；修订在 fixture 内局部绑定相应常量，生产来源值不变。

测试静态覆盖目标 config/DiffID 判定、固定批准文件形状与项目、非专用调用在 Compose 前拒绝、真实 Git 仓库上的允许产品变化和额外产品变更拒绝、源/输入/起点/state 镜像不符，以及 CLI 接线。原快照与 step provenance 测试继续保留。本轮未执行这些测试，不以静态覆盖代替运行结果。

比例化检查：新增逻辑主要是固定本次身份、复用入口分支与分段来源记录，没有新增业务恢复状态机。原 AST 归一化签名与精确字符串替换、目标/当前文件字节比较完全重复；建议删除，413832 已采纳。保留精确字节比较足以约束本次单常量修正，不要求为行数重写工具或扩建通用框架。

## 3. 待补证据与后续

待实施者提交固定候选的 05 focused 与五包静态日志、起止 HEAD/exit、SHA 和收束记录后完成证据补核。若代码再变，仅复审差异；不要求重审容量产品或重跑原失败 Preview。

本轮未构建新镜像，没有实际恢复候选的 image revision/source-tree 或容器结果可宣称。完整代码验收后仍须最终 H 的 04 backend/容器门禁、固定目标机读身份、镜像传输校验、源快照与输入及步骤来源复核，才能按 DC80 执行恢复。未推送、未改产品或设计正文，未作恢复 GO。
