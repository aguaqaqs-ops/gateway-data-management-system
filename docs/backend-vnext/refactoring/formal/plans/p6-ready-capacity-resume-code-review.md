# Phase 6 READY 容量限定恢复接线审核

- **最新结论：`cd9b75ce887d737327d0ee6611017b475040f856` 工具代码及 05 focused/五包静态证据通过，无剩余阻塞项，可推进最终 H 的新镜像与 04 门禁；不是 CT108 恢复放行。** 追加复审及证据见第 4 节。
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

## 4. cd9b75 复审与 05 证据补核（2026-11-05）

本节关闭第 3 节的 05 待补事项。候选为 `cd9b75ce887d737327d0ee6611017b475040f856`，审核在 `/home/dev/gdds-p6-capacity-evidence-cd9b75ce` clean detached worktree 进行，完整 HEAD、detached 和清洁状态均程序核对。

相对已静态审核的 413832，仅两项变化：CLI 默认参数期望补上 `capacity_fix_resume=False`；组装目标产品 provenance 时对 Optional run_status 加 None 分支，消除 mypy 错误。公开 run_journey 路径仍传递实际状态字典，正常来源记录不改变；身份、产品差异、输入、镜像和快照拒绝条件均未放宽。产品文件与已审容量提交字节相同，差异范围及 whitespace 检查通过。

05 节点原始验证日志 `/home/dev/gdds-p6-logs/baseline/ct05-capacity-resume-cd9b75-validation-20261105.log`，SHA256 独立重算为 `9d14de877898ff43d5e815fe37028ed77a5755ec211fe885947b19c16df67e00`，匹配交付。日志时间 16:09:51Z–16:10:29Z、hostname 为 gw-dms-test-05，起止 HEAD 均为 cd9b75，159 passed in 1.83s、五包 Ruff/mypy 均通过、exit 0。扩展 expected/installed build-input 均为 `58436908aee9dd449f4d3e0542a6a8c1920b6d5e`，与候选 Rust tree 程序比较相等。

实际测试 worktree 为 `/home/dev/gdds-p6-baseline-capacity-resume-972c12-05`，目录名不代表当前提交；已只读核对其当前 HEAD 为 cd9b75 且 clean。原日志 `worktree=` 字段误接 PATH 行，pytest rootdir/toolchain 行和补充记录明确实际路径，不修改原日志。

收束记录 `ct05-capacity-resume-cd9b75-postflight-20261105b.log` 位于同目录，重算 SHA256 为 `65c1b6359fc0bf6e2d1ab34c5f22fbe6ea7c933f2f43471374580ff827c7c3f6`，记录 16:15:13Z PASS。记录包含 worktree/venv Python/uv wrapper 的绝对路径、prepare、扩展重装及身份检查、focused 和五包静态的受控命令；`UV_OFFLINE=1`、`GATEWAY_DEV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、PATH 前缀 `/home/dev/.cargo/bin` 与外置 TMPDIR。五个 uv.lock 的工作树 SHA 与 HEAD 均 MATCH，Cargo target 清理、工作区 clean、节点锁 FREE。审核时也只读确认该节点标记不存在；未获取标记或干预其他工作。

此前失败日志保留，均独立重算 SHA，不作成功证据：

| 同目录日志 | 失败及修正 | SHA256 |
| --- | --- | --- |
| ct05-capacity-resume-413832-validation.log | 初始扩展不可导入，测试尚未启动 | `4c9bbe55c6ca77b00dfc49a9e7a41cdb88458b87335a66ac052715a63ee58712` |
| ct05-capacity-resume-413832-validation-retry-20261105a.log | 扩展 build-input 为空；按当前 Rust tree 重装后身份通过 | `15d12658f567ac3c03ebf41cc6444e7e10e8d12efc52ed2c2394b423fb5793e6` |
| ct05-capacity-resume-413832-validation-retry-20261105b.log | 158 passed/1 failed：CLI 期望未包含新增默认参数；972c12 修正 | `ee1b169a48826c3f20fd5b084170b37c2a8653e0b4488e42e4786fd2c32e47a9` |
| ct05-capacity-resume-972c12-validation-20261105.log | maturin 启用临时 Rust 安装路径并尝试下载，网络不可达，构建失败；后续固定本地 PATH/toolchain。此轮不称为成功离线验证 | `5ac8dc716b9c77b7384c1f5f411b886e73f5d931f80e5c907d4dabf997cb552d` |
| ct05-capacity-resume-972c12-validation-retry-20261105b.log | 159 passed，mypy 报 Optional run_status.get；cd9b75 修正 | `66c17dc82c4c7feda010d306215df424a9b9311e69f2fc5fdd1d75bd4a1cefb1` |
| ct05-capacity-resume-cd9b75-postflight-20261105.log | 补充记录误用节点未安装的 rg，保留失败记录后用 Python 重做；未重跑测试 | `e5c7a2cb5b25d703a0c50569d63a9c2121ca337c8783e64bbdb6ebc7eb0ba53e` |

上述为独立调试/环境准备失败，未被合并包装为一次成功 runner，也未用于宣称 CT108 产品恢复成功。依 DC80 主动修正后，最终完整 focused/静态结果独立绑定 cd9b75；不要求再重复这些已通过检查。实施 handoff 应保留失败、修正和最终证据关系。

工具代码验收通过后，原实施者可继续固定最终 H、准备新镜像和 04 backend 权威包/容器门禁，生成并提交精确目标身份记录。实际镜像及恢复条件尚未审核，本次不作恢复 GO。审核只修改本报告，无推送；自身 detached worktree 用后清理。
