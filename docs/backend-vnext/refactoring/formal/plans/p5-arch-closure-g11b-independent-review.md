# P5 架构收口 G11b 独立审核记录

- 结论：**通过**。G11b 经两位审核方各自审核，均为通过。
- 日期：2026-10-17。
- 审核对象：
  - p5-g11b @ H `944982eb910dab9cbfc117a976dea6721cdd6ca2`；
  - 门禁提交 V `d4c991f77c08d5e21ebfd5ca98155c420c971b6d`；
  - kickoff base `460cfc77763fa23850dca2f58d5a59d25f36820c`；
  - 审核区间 `460cfc7776..944982eb91`。
- tag：`p5-g11b-exit` 由首审方创建，为附注 tag，tag object `6859f7e6e629d1ef3fbc0030ed7aa31847557251`，指向 H。它取代 `p5-g11-exit` 作为 S3 的区间起点。与 G11 相同，tag 打在 H 上，没有打在审核报告的提交上（即本文件）。
- 合入：`e8b5322b3c`（`--no-ff`）。
- 依据：
  - 治理修订计划 G11b；
  - `plans/p5-arch-closure-g11-independent-review.md` §2.2–§2.3；
  - AGENTS.md「镜像身份等价」「Docker / Compose 验证」；
  - 执行计划 §8.2、§8.9（DC30）；
  - handoff `plans/p5-arch-closure-g11b-handoff.md`。

## 1. 首审

首审经过三轮，过程在 handoff「审核与过程偏差」一节有完整记录：

- 第一轮（H1 `d786dcf4bd`）结论为阻塞：方案报告没有评估同一文件内的共栈候选。首审方在审核完成前曾短暂创建 `p5-g11b-exit`，发现阻塞项后删除。该 tag 不构成阶段退出证据。
- 第二轮（H2）和第三轮（H3）都是定向修订，只改 handoff：补审核提示词，补执行计划 §8.2 要求的 `import_rules` 前后对照和停止条件状态。
- 最终 H 通过，首审方重新创建了 `p5-g11b-exit`。每一轮 H 都重新做了 carried，最终以 `g11b-carried-final-h4.log` 为准。

## 2. 第二审

第二审在只读 detached worktree 中独立核对，没有采信首审结论，结论为通过，没有阻塞项。

### 2.1 核对结果

- **区间：** V 之后的三个提交只改 handoff；每个提交都带 trailer。
- **R2-F1 修复：**
  - `ensure_repository_service_image()` 通过当前解释器调用 RS 已有的 `build_context_digest.py identity`，没有另写 identity 算法。
  - 比对 `gateway.p2r1.build-input-revision` 和 `gateway.p2r1.source-tree-sha256`：一致时复用；不一致或缺失时重建，重建后再核对一次。
  - 无法计算 identity 时（包括 dirty worktree），在 inspect 之前失败关闭。这与 RS 的 `require_clean_worktree()` 行为一致。
  - 指定 `GATEWAY_REPOSITORY_SERVICE_IMAGE` 时行为相同，构建脚本也用这个变量作为输出 tag。
  - provenance 增加 `repository_service_image`（image ref、ID 和两个 label）；写入前再核对一次 identity。
  - 参数表测试 `test_repository_service_image_is_bound_to_current_build_identity` 独立运行 3 passed。
- **门禁：**
  - `g11b-authoritative-run-1.log` 起止 HEAD 都是 V，前后都 clean，`runner_exit=0`，01:12:40Z–01:45:12Z（32:32）。
  - 计数：shared_kernel 242、repository_contracts 152、repository_client 154、backend 2,816 + 34、RS 1,684 + 1 skipped / 205。backend 比 G11 多出的 3 项就是新增参数表的 3 个案例。
  - 在 V 和 H 上独立重算 RS identity：build-input `adc5d87fea073545fde6416d123c3d7845e715ff`、source-tree `sha256:5b34d0c5…`，与 provenance（SHA-256 `8ac1f08c…`）中的 label 相等。
- **carried：**
  - `g11b-carried-final-h4.log` 记录：在 H 上重算的 identity 与本地 RS 镜像 label 一致；
  - 用 V 的 project `ordered-bisect-b-554228-baseline` 连续构建两次，backend `b752628c…`、worker `e1759450…` 都与 provenance 相同；
  - exit 0，起止 HEAD 都是 H，起止都 clean。
- **静态检查：** 五个包的 ruff/mypy 独立运行均通过；`import_rules` 为 0 / 0 / 14。
- **测量：**
  - 用原始事件 `g11b-compose-timing-events.jsonl` 重算 11 个用例各阶段的耗时，各列合计与 handoff 表相符。
  - 唯一的人工修正是 container ready 行：插件重复包了一次就绪等待，多算了 4.03 s。handoff 已说明这一点，单用例重跑测得 10.30 s，可以印证。
  - 计时代码没有进入提交，补丁和日志都在 worktree 外。
- **方案报告：** 两路并发的 LPT 结果（节省 169.87 s；含 control case 时节省 289.01 s）以及阶段退出方案的 727.95 s 均已复算。固定等待的来源与代码一致：`_WORKER_FIXED_BUDGETS`、healthcheck 5 s / 12 次 / 30 s。

### 2.2 观察（均不阻塞）

- **G11b-O1：门禁没有走真正的重建路径。** 运行前本地 RS 镜像的身份已经与 V 相同，harness 按 identity 复用。重建分支只由参数表测试覆盖；判定逻辑都在被测函数中，这样的覆盖已经足够。
- **G11b-O2：没有测 operation 在服务端的耗时。** 约 1,160 s 花在轮询 operation 终态上，例如 upload/import 旅程有 26 次轮询，共 52 s。handoff 认为这段时间主要是异步执行时间，这是推断，没有测过。
  - “缩短轮询间隔省不到 60 s”这个结论成立；但 backend、worker、RS 内部有没有空等，目前不清楚。
  - 如果以后还要缩短门禁，下一步应在一次调试运行中读取 control DB 里各 operation 的时间戳，这不需要改代码。按 DC31，这不属于 P5 的范围。
- **G11b-O3：推荐方案。** 审核方认同 handoff 的推荐，维持现状，完整门禁约 32.5 分钟。两路并发预计节省约 3 分钟，但要改 compose 端口、gate 锁和 `BACKEND_URL`，属于强制重建项，由 owner 决定是否另立一步实施。它不阻塞 S3。
