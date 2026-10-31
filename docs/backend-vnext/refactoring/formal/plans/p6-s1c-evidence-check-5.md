# Phase 6 S1c 取证复核 5（DC69 取证）

状态：**证据实质通过。** DC69 第 2 项要求的四部分（V' 镜像预构建与身份核对、04 六包 runner、05 t1、ct108 2× t4 三节点完整旅程及两项只读对照）均已完成，结论与 handoff 一致。进入终审前还差两件事（第 5 节）：

1. owner 对 05 t1 超出 DC68 一次重做的情况作出决定（已追认，见第 5 节）；
2. 实施者补一节 handoff 记录（只改文档）。

## 1. 对象

- 代码候选 V'=`ebd1b60a3f`；handoff H=`5eca3b728a`（`0d032ff13b` 之后追加 `96c450872a` 与 `5eca3b728a`，只改 `p6-s1c-handoff.md`），分支 `p6-s1c-impl`，clean，未推送。
- 取证合并提交 `b96fe8e4cc`：第一父 V'，第二父工具提交 `fb534592`。审核者在 ct108 核对：相对 V' 只改 `vnext/backend/benchmarks/` 与对应测试（17 个文件）。`git diff V'..b96fe8e4cc` 与上一轮 `git diff 3008d578cf..47832ee94d` 的 SHA256 同为 `75036f1d…`，工具差异逐字节相同。

## 2. 核对

审核者在开发节点与三台测试节点逐项核对了 SHA256、hostname、起止 HEAD 与结论。

| 项 | 结果 |
|---|---|
| 镜像 | 开发节点 V' clean worktree 构建，归档 `5c691d1d…`，config digest `sha256:6d0aab7e…`。开发节点、04、05、ct108 的 backend 与 worker 镜像 15 个 RootFS DiffID 逐项相同（审核者在四台机器上读取比较）。三节点身份日志 `57d9ef53…`、`3bd8a13d…`、`f33912d7…` 与 handoff 一致 |
| 04 RS / client e2e 预构建 | 04 本机用 lock 匹配的预置依赖镜像离线重建，label 指向 V'。RS 日志 `15cc5319…` 一致 |
| 04 runner | `gw-dms-test-04`，起止 HEAD 均为 V'，14:50:44Z–15:11:16Z，exit 0，未设置 `GATEWAY_TEST_PACKAGES`，六包全部通过；`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`，`GATEWAY_DOCKER_BUILD_NETWORK` 与代理变量均未设置。日志 `a77654a1…` 一致。postflight（`342bc423…`，存于开发节点）：worktree clean、无容器、8000 无监听、无 Dolt/pytest/uv 进程。04 当前无容器、无本轮卷 |
| 04 首次 runner | exit 1，唯一失败是 `test_build_script_defaults_docker_build_network_to_host`，原因是 runner 环境继承了 `GATEWAY_DOCKER_BUILD_NETWORK=none`（日志 `0012957e…` 第 4741 行）。这个测试对环境不隔离，已由 backend 镜像任务 E3（`9600b33927`）在 main 上修正；V' 早于该修正，因此仍受环境影响。runner 开始测试之后才失败，不属于 DC68 自动重做范围，实施者正确停止；重跑经 owner 在实施会话中授权，本复核记录该授权 |
| 05 t1 | `gw-dms-test-05`，HEAD `b96fe8e4cc`，预构建镜像、离线、无代理。18 个步骤 `step_succeeded`，无失败事件，History 比对成功。日志 `67b01d59…`、状态 `2c06de99…`、清理 `b44f5d94…` 一致。卷已清理，05 无容器 |
| ct108 三节点 2× t4 | `gw-dms-test`，HEAD `b96fe8e4cc`，cold History、`--three-node-history`、五个 checkpoint，15:36:30Z–20:59:36Z，exit 0，`failure_step=null`，`step_checks` 26/26 PASS（含 v3-submit、v3-repository-read、History）。日志 `376a51af…`、状态 `072a2f5a…` 一致。镜像元数据中的 config digest 与 DiffID 与预构建一致 |
| (a) v1 对 1030b | 审核者用对照 JSON（`bb713612…`）中保存的逐表哈希复算：v1 与 1030b 631/631 相同；三份哈希又与 1030b 原始哈希文件（`79e541d6…`，09:28 生成，本轮未改）相同。canonical state 均为 `sha256:1f53df33…` |
| (b) v3 对 v1 | 631/631 相同。DC69 修复后，回退型 Submit 产出与 v1 逐表一致的 Repository 状态 |
| 只读与保留 | 对照只在卷副本上进行，不执行 add/commit；临时副本与哈希容器已清理（`51bfc890…`）。ct108 现有卷：本轮 `s1c-vprime-ebd1_*`、`fb534`、`20e634`、1030b，共十二个，无容器 |

S1c 自身的行为（2× t4 Submit 无人工干预完成，`await_import_result` 每次只领取一次）在本轮 v1、v2、v3 三次 Submit 中都出现了。DC69 修复在真实数据的回退场景中得到证明。

## 3. handoff 未记录的尝试

审核者在节点日志目录中发现以下失败尝试，handoff 都没有记录，其中 ct108 一节写有“无未解释偏差”：

| 节点 | 尝试 | 失败原因 | 日志 SHA256 | DC68 判断 |
|---|---|---|---|---|
| ct108 | 旅程首次启动 15:34:59Z | 工具参数校验：未设置 `GATEWAY_P6_RUN_LOG` | journey `4e2565f2…`、launch `3e8ee734…` | 被测对象未运行，重做一次成功，符合 |
| ct108 | 只读对照首次 21:03:58Z | 审核脚本解析 `dolt log` 时没有去掉 ANSI 颜色，在 checkout 核验阶段失败，尚未读取任何表哈希；只涉及副本 | `6528aa3d…`、诊断 `447ac1f7…` | 外部比对脚本缺陷，无副作用，重做一次成功，符合 |
| ct108 | 首次临时清理 | 哈希容器未全部删除即报错；第二次清理成功 | `50771b7a…` | 清理操作，无影响 |
| 05 | 环境同步首次 15:19:00Z | 命令重复传 `--locked`，uv 拒绝 | `548906ea…` | 重做一次成功（`2dffeda9…`，handoff 引用的是这次），符合 |
| 05 | t1 首次 15:20:08Z | 工具参数校验：`--project-name` 只能与 `--keep-stack` 同用 | `996f4702…` | 被测对象未运行 |
| 05 | t1 第二次 15:20:43Z | 工具启动前检查：未传项目名，按默认名寻找预构建镜像，报缺失 | `59a7e2e9…` | 被测对象仍未运行，但这是重做后再次失败 |

前五项都在 DC68 范围内，只是缺少记录。05 t1 是同一步骤连续两次操作错误，第三次（`-final`）才通过。DC68 写的是“重做再次失败……停止交 owner”，实施者没有停下来交 owner，这是程序偏差。两次失败都在工具的启动前检查阶段，没有启动栈、没有写卷，通过的那次是完整的独立运行。

## 4. 记录错误

- handoff 列出的 15 个 DiffID 中，第 3 个写成 `…606d47ba4b53…`，实际为 `…606d47db4a53…`。四台机器上的镜像与 state 文件均为后者，属于抄写错误，镜像本身一致。
- client e2e 预构建日志 SHA256 写成 `4684544b…e48015a6f111…`，实际为 `4684544b17d2252103bd7948201e480d2d6d24179af90a21f84513c22611a028`。中段混入了 RS 日志的哈希片段。
- 两份 04 postflight 日志存于开发节点 `/home/dev/gdds-p6-logs/s1c/`，不在 04；handoff 没有写明所在主机。
- 05 t1 最终日志没有结束时间与 exit code，handoff 已如实披露，可以接受：状态文件与日志都表明全部步骤成功，前两次尝试的 wrapper 都写了 `EXIT_CODE`，只有最终这次缺失。

## 5. 进入终审前

1. **owner 决定 05 t1（建议：追认）。** 两次失败都是传参错误，在工具的启动前检查阶段被拦下，被测对象没有运行，没有副作用，原因各不相同。最终运行完整独立，日志与状态完整。重跑 t1 约需 10 分钟，但不会增加证明力。建议 owner 追认这次超出一次重做的情况，并记入 handoff。若 owner 要求按 DC68 字面处理，就在 05 原 worktree 再跑一次 t1。
   - **owner 决定（2026-10-31）：按建议追认。** 05 t1 的 `-final` 运行（日志 `67b01d59…`、状态 `2c06de99…`）作为 DC69 取证证据，不重跑。这次追认只针对本次情况，不修改 DC68 的一次重做规则。
2. **实施者补一节 handoff（只改文档，追加提交，不改写已有提交）：**
   - 第 3 节六项尝试的时间、原因、修正与日志 SHA256；05 t1 写明 owner 的决定。
   - 更正第 4 节两处抄写错误，写明 postflight 所在主机。
   - 04 首次 runner 写明重跑经 owner 授权。
   - ct108 `/home/dev/gdds-test-tmp/s1c-dc69-ct108-cargo-target` 是本轮环境同步留下的构建缓存，列入 exit 清理。
3. 补记提交后，在本会话终审。最终 HEAD 只在 V' 之上增加文档提交，04 runner 的六个包与容器门禁按闭包比较沿用，来源为本次 V' runner。

## 6. 结论

| 项 | 判定 |
|---|---|
| V' 镜像身份 | 通过（config digest 与 15 个 DiffID 四机一致） |
| 04 六包 runner | 通过（V'，exit 0） |
| 05 t1 | 通过（owner 已追认第二次重做） |
| ct108 三节点 2× t4 | 通过（26/26，exit 0） |
| v1 对 1030b、v3 对 v1 | 631/631 一致 |
| handoff 记录 | 需补记（第 3、4 节） |
| S1c exit | 第 5 节两项完成后进入终审 |
