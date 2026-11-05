# Phase 6 基准输入准备工具：证据复核 1

- 结论：**工具代码与本次定向证据通过，无阻塞项；可协调合入，并在后续确有需要时采用。** [代码复审 1](p6-baseline-input-preparation-code-rereview-1.md) 的 F1/F2 已闭合，本次最终 focused/静态证据补齐。当前 CT108 原运行不切换，不为采用工具重生成已通过输入；本报告不是新 W4 输入接受或基准终审结论。
- 日期：2026-11-05；审核会话：`p6-backend-review`（DC73）。
- 代码：`249c09d0824c5d9716f02f7deb1bb8c154ea4c98`；handoff：`9deb8915321b50b738624ae116e6e01a183acbc9`，见 [实施 handoff](p6-baseline-input-preparation-handoff.md)（该文件目前在工具分支，引用以此提交为准）。
- 方法：在 `/home/dev/gdds-p6-input-evidence-review-9deb8915` clean detached worktree 只读审核；05 先做 BatchMode SSH 连接检查，随后仅核对已有文件、Git 身份与释放状态，不获取占用、不运行测试、生成器或 Compose。未访问 CT108。真实数据只输出计数与摘要；核对程序通过 stdin 执行，没有落盘临时脚本。

## 1. 候选绑定与 F1/F2

程序核对 handoff HEAD、detached、clean；handoff 与代码候选的 `vnext/` tree 均为 `25fe7febbb9aa284c00a980a31b5c102748cafc8`。handoff 提交只新增交付文档，`git diff --check` 通过。05 保留测试 worktree `/home/dev/gdds-p6-input-preflight-05` 当前 HEAD、tree 与代码候选程序比较一致，status 为空，legacy 链接存在。

F1/F2 的代码结论沿用 `4aade4745792dee202b7c99ba6276ce2b61c4ccf`：固定两个 Process，通过 Pipe/sentinel 观察无结果直接退出，finally 收束；输出在写入前按 resolve 后路径拒绝落入 reuse 根。最终 focused 明确包含这两个修正所在测试文件，以及同次已完成分段复用、1/2 路字节一致和真实有界 generate→新根 validate 完整成功路径。

## 2. 05 最终 focused 与静态

节点 `gw-dms-test-05`，运行 `2026-11-05T02:59:04Z–02:59:20Z`。程序提取日志中的两个完整 HEAD，均与 `249c09d0824c5d9716f02f7deb1bb8c154ea4c98` 相同；外置脚本启动时拒绝 dirty，结束 status 没有输出，最终 `validation_exit=0`。

- focused 的三个文件为 `test_p6_input_preparation.py`、`test_p6_baseline_inputs.py`、`test_p6_s1b_synthetic_load.py`：**54 passed，6.73 s**。
- 五包各一次 Ruff 成功及 mypy 成功，source files 依次为 34、15、26、499、200；程序核对成功标记分别为五次，没有将中途静态失败的旧运行算作本次通过。
- 已核对验证脚本实际使用受控 uv 入口、locked/no-sync 路径，设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、外置 TMPDIR/Cargo target、Cargo PATH，清除指定 Rust 覆盖变量与大小写 HTTP/HTTPS/ALL proxy。backend sync 强制重装 Rust 扩展并绑定当前 Rust tree。日志未出现缓存缺失或代理下载；按 handoff 使用节点已有本地缓存，没有本次新增依赖制品。

日志 SHA256 为 `b51975f57a756ff6f9fd7041961957f8bca6288207dd52fe5e277cb98cae2739`；验证脚本 SHA256 为 `f7c07f6d5dce94e670e9ec1043892347e32ee9f8653d37ad12d0b45d106118b4`；传入 05 的 reviewfix bundle SHA256 为 `e4fc35a2574dbc38390a791285f48d117244974f5bf1868221ada4b916d65291`，均重新读取实际字节比较通过。此为工具 focused/静态证据，不是权威 runner、容器门禁或按包 carried。

## 3. 真实来源预检及适用范围

真实来源运行仍绑定 **`e08cabdb234e0ba77331660fc2d096dad97bd12e`**。05 日志起止 HEAD 相同，脚本启动拒绝 dirty、结束 status 无输出；`2026-11-05T02:52:43Z–02:57:25Z`，Bash time 为 **282.472 秒**，`preflight_exit=0`。脚本只调用 `--phase preflight`，外层预算为 600 秒、超时 TERM 后 10 秒 KILL；本次未触发超时。脚本使用 offline 环境并清除代理。

程序比较 stdout JSON 的 preflight 与保存的 `preflight.json` 完全相等，结论为 `PREFLIGHT_COMPLETE`，没有最终 `input-summary.json`。按原包实际字节重算 SHA，并只读抽取其中唯一 SQL 流重算大小/SHA，与预检记录一致；预检 implementation 的每项摘要/源码树均与本地 e08 Git 对象程序比较一致。

| 输入 | 原 SQL bytes | DDL 数 | 样本行数 | 样本 SQL bytes | 扫描 s | smoke s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| t4 v1 | 79,446,967 | 319 | 7,741 | 1,535,626 | 19.873 | 114.865 |
| t4 v2 | 79,269,322 | 319 | 7,741 | 1,533,737 | 19.864 | 114.982 |

两份均为每表不超过 60 行、155 个空表、22 个 keyless 表、144 个 ordered 表，10%/100% 的 SQL materialization/canonical 均 COMPLETE、诊断 0。观察到的特殊点行数为 **0**；不能称为真实特殊点值已覆盖，该边界由 focused fixture 承担。扫描、smoke 与额外读取/解析成本不能简单相加当作完整墙钟。

原包 SHA256：v1 `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675`；v2 `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611`。其中 SQL SHA256：v1 `b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8`；v2 `65358db2cfba310f145446698d6d20b580ba3b805d520bd3ff9ae33a12ad01af`。

代码复审已程序比较 e08→249 的 11 个预检/生成依赖文件或树对象不变，入口抽取和 `_generate_pair` AST 不变；本次 handoff 与 249 同树。因此接受这次 e08 运行作为未变预检范围的真实来源调试证据，无需重复，不能改称在 249 实跑。它不证明全量输入正确、XML/composite 完整性、大输入双进程峰值或加速比；完整原包验收、确定性及 READY 条件保留。

## 4. 失败记录、SHA 与停止规则

首次真实来源 wrapper 于 `02:52:08Z` 返回 127；stderr 明确为 `/usr/bin/time: No such file or directory`，stdout JSON 为空。失败发生在该 wrapper 调用生成器之前；日志及 stderr 均保留。修正脚本使用 Bash time，不安装依赖，以新日志名重做一次并成功。这符合 DC68 的命令错误修正范围，无需新增停止或恢复授权；不将失败记录抹去，也不将该次启动尝试改称成功预检。由于同一原输出路径随后被“已有根即拒绝”的工具成功使用，记录与未建立生成根的说明相符。

此前 c755/9fac 的 focused 失败、a421/335 的静态失败均有原日志；程序核对分别为 `2 failed/40 passed`、`1 failed/44 passed`、`50 passed 后静态失败`、`50 passed 后静态失败`，各次 `validation_exit=1`。它们属于收敛中的 focused 调试，未冒称权威 runner 证据；最终候选已完整通过所需验证。

以下 15 个 05 文件均按 handoff 给出的预期 SHA，程序重算并比较为 MATCH。路径均相对于 `/home/dev/gdds-test-tmp/`；表内补列核心真实来源和释放记录，其他完整 SHA 见 handoff 第 05 验证/调试记录节。

| 文件或组 | 核对结果 |
| --- | --- |
| 最终 validation.log、validate.sh、reviewfix.bundle | 三项 MATCH，完整 SHA 见本报告 §2 |
| c755、9fac、a421、335a 的 validation.log | 四项 MATCH，失败摘要与 handoff 一致 |
| actual-e08c.log、actual-e08c-stderr.log | 分别 `1dcb68314b9872b17e49139ac9927ae72d7d12a93bb292e4849973476a28f29a`、`3aa90856764d1a87d247275a055619f945b32816e16bb9df670d04cffbb00a8b` |
| actual-e08c-retry.log | `3bbdce9d15aa13b104ef6960c04c2a65d80bf43b02d81b29a70e20605160a8cd` |
| actual-e08c-retry-output.json | `ae53a7172ec111668d39e39b76c93904f4ea4dd2ef65c9c8f45d8b08c5a88f96` |
| actual-e08c-retry-stderr.log | `b0ba787a109f650b1e1b0b5c558eaaa8b65774df7bf1b0e6aa5b9fda912c066b` |
| actual-e08c/preflight.json | `7444633020868a0ff121951be2fcbcb0802575a63b67e793305e80597254baaa` |
| actual.sh（修正后） | `bea23aa892d129d7f20bf2c9cb2081a330e5da63d007e5bc3d9462c951a3d59f` |
| postflight.log | `d3229dde052861a48b1ebecead260086e66dba3d1ac00800465d0ee2ff906480` |

表内 `actual*`、`postflight.log` 的完整文件名前缀均为 `p6-input-preflight-`。另重算 CT201 两份 checkout 操作错误说明日志 SHA，与 handoff 一致；它们是事后说明，不能替代原始命令日志或作为候选通过证据，本结论依据最终 clean/固定 HEAD 的实际运行。没有发现需放宽 DC68 或基准停止规则的事项。

## 5. 节点、镜像及后续

postflight 记录 `2026-11-05T03:00:22Z`、249 HEAD、无运行容器行及无 8000 监听行，脚本检查 clean 和本任务 owner 后释放标记，`postflight_exit=0`。本次只读核对时，节点占用标记不存在，本任务外置 Cargo target 不存在，测试 worktree 仍 clean；保留的 worktree、日志和预检输出属于已声明证据，不在本轮删除。

本工具仅修改 host benchmarks 与对应测试，不触发本次冻结产品镜像重建；没有新 image revision/source-tree、容器门禁或 carried 声明。将来合入基准最终候选时仍按原最终 runner/镜像闭包流程处理。

DC79 的工具代码/定向证据条件现已满足。后续由相关实施者协调合入及实际需要时使用，历史无 receipt 的已接受根不会自动获得复用能力；当前生成成功则优先完成既定验收，不为展示工具再生成。首次大输入双进程仍需核对当时节点资源预算，不能由本次样本证据推定峰值。

本轮仅按显式路径提交审核报告，不合入工具、不推送、不打 tag、不办理阶段 exit；不改设计/DC 正文。审核 worktree 在确认 clean、HEAD 不变后清理。
