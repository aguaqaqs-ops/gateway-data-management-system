# P5 架构收口 G11 独立审核记录

- 结论：**通过**。G11 经两位审核方各自审核，均为通过。
- 日期：首审 2026-10-16；第二审 2026-10-17。
- 审核对象：
  - p5-g11 @ H `dcff8c0685f7d42211279dac4d6f47f01e04773b`；
  - 门禁提交 V `3223152f26d1edecba4f674da95f9e9576c0741e`；
  - kickoff base `676110a74b68f68ea89866e25fa7cffdaae8bf73`；
  - 审核区间 `676110a74b..dcff8c0685`。
- tag：`p5-g11-exit` 由首审方创建，为附注 tag，tag object `5ed848f58b1eb4ec1858f6f95a1737828d00ef18`，指向 H，作为 S3 的区间起点。

  按惯例，tag 应打在审核报告的提交上。这次打在 H 上，审核记录合入后才补交（即本文件）。owner 决定不移动 tag。
- 合入：`fa902aa200`（`--no-ff`）。
- 依据：
  - 治理修订计划 G11 及其“kickoff 补充”；
  - AGENTS.md「跑测试」「写测试」「镜像身份等价」；
  - 执行计划 §8.9（DC30）；
  - handoff `plans/p5-arch-closure-g11-handoff.md`。

## 1. 首审（2026-10-16）

首审要求 handoff 修正两处，两处均已修正：

- kickoff base 上含 serial 标记的 backend 测试文件数：handoff 原写 27，首审独立计数为 26，handoff 改为 26（`1c2ed5923f`）。
- 有效基线之前有两次没有形成证据的尝试，初版 handoff 没有披露。修正后的 handoff（`dcff8c0685`）补充了：
  - 12:19:16Z：exit 2，没有收集任何用例；
  - 12:19:25Z：repository_service `.venv` 缺失，7 个用例失败，2,840 passed，exit 1。

首审接受 12:48:15Z 那次 clean 的有效基线作为唯一基线证据，结论为通过，并创建了 `p5-g11-exit`。

## 2. 第二审（2026-10-17）

第二审在只读 detached worktree 中独立核对，没有采信首审结论，结论为通过，没有阻塞项。

### 2.1 核对结果

- **runner：** backend 改为两遍，其余三个小包单进程，repository_service 原有两遍保留。
  - 并行遍：`-m "(not serial) or parallel_safe" -n ${TEST_WORKERS}`；
  - serial 遍：`-m "serial and not parallel_safe" -n 0`。
  
  设置 `GATEWAY_TEST_BASETEMP` 时，backend 的 7 个 Compose 文件改在真实文件系统上运行，之后 `--basetemp` 恢复。
- **依赖：** lock 只增加 `pytest-xdist==3.8.0` 及其传递依赖 `execnet==2.1.2`，均为 canonical PyPI。
- **分类：** 以下计数均独立复核，与 handoff 一致：
  - kickoff base 上含 serial 标记的文件 26 个；
  - V 上 `serial and not parallel_safe` 34 项，分布在 18 个文件；
  - `parallel_safe` 0 项；
  - `-m unit` 2,668 项。

  另外核对了：
  - 7 个 Compose 文件全部留在 serial；
  - 并行批次中剩下的 `wait(timeout` 都是注入的假 wait；
  - 收集期探针显示，依赖真实 Dolt 而没有 integration 标记的用例为 0。
- **两次 V runner：** 起止 HEAD 都是 V，前后 status 都是 clean，exit 都是 0。
  - 计数：shared_kernel 242、repository_contracts 152、repository_client 154、backend 2,813 + 34、RS 1,684 + 1 skipped / 205。
  - provenance 两个文件的 SHA-256 与 handoff 一致。
- **carried：** 在 H 上重算的 RS 身份为 build-input `adc5d87fea`、source-tree `sha256:5b34d0c5…`，与运行中用到的两个 RS 镜像的 label 都一致。backend/worker 两次重建得到的 ID 与第二次运行的 provenance 相同。
- **静态检查与 `import_rules`：** 五包 ruff/mypy 均 exit 0；`import_rules` 为 0 / 0 / 14。
- **基线多跑的偏差：** 两次失败都是依赖环境没有就绪，日志都保留了，handoff 没有挑选结果。DC30 限制的是完整 runner 的次数，多出来的是只跑 backend 的调试测量。披露充分，不影响验收。

### 2.2 目标达成情况

G11 的验收条款都满足了，但缩短门禁的效果很小：

| 指标 | 改动前 | 改动后 |
| --- | --- | --- |
| backend 批次 | 1,717 s（单遍） | 约 1,577 s（两遍合计），减少约 8% |
| 完整 runner | S2b V 约 2,000 s | 1,945–1,958 s，减少约 2% |

原因是改动前 backend 耗时中有 91.7% 是 7 个 Compose 旅程文件，共 11 个用例，它们必须单进程运行。

G11 计划当初的前提是“backend 的大部分耗时来自普通用例”，这个判断有误，责任在审核方，不在实施方。handoff 已经按要求如实报告了耗时构成。后续处理登记为 G11b。

### 2.3 Findings 与观察（均不阻塞）

- **R2-F1（既有缺陷，登记到 G11b）：backend 的 Compose 旅程没有把 RS 镜像绑定到当前提交。**
  - `compose_gate_harness.ensure_repository_service_image()` 只在 `gateway-repository-service:local` 不存在时才构建，不比对身份 label。
  - 第一次运行就是这样使用了 S2b 留下的 RS 镜像 `196148be…`（`org.opencontainers.image.revision` 为 `753c5768a5`）。第一次运行中 RS 的 serial 批次重建了镜像，第二次运行才使用 V 的 `df34df3e…`。
  - 本次两个镜像的 build-input 和 source-tree 都与 V 相同，结论不受影响。但只要改了 RS 源码、又没有预先构建镜像，backend 的 Compose 旅程就会对着旧镜像运行，provenance 记录的也会是旧 ID。
  - handoff 只报告了第二次运行的 provenance。
- **R2-O1：carried 的 backend/worker 重建是在 HEAD=V 时做的。** 名为 `g11-carried-final-H-identity.log` 的日志，记录的是更早的 H `e2e95fa926`。V→H 只改了 `docs/`，而所有镜像的构建上下文都是 `vnext/`，结论不受影响。AGENTS.md 第 3 条没有写明重建时应检出哪个提交，补充说明登记到 G11b。
- **R2-O2：** 有 3 个并发用例移入了并行批次，它们隐含依赖 SQLite `busy_timeout`（5 s），handoff 写的是“没有固定 timeout”。余量很大，两次运行都通过了，风险低；一旦出现不稳定，改回 serial。
- **R2-O3：** conftest 改动后，只标 serial 的用例也会自动获得 `unit`，`test_http_admission_shutdown_process.py` 里 3 个涉及子进程和信号的用例因此成了 `unit`，与 marker 表中“子进程属于 integration”的定义不一致。这与 repository_service 的现有行为相同，runner 也不按 `unit` 筛选。建议之后把这 3 个用例标为 integration。
- **R2-O4：** 并行调试和无 dolt unit 调试的日志中，head 写的是 kickoff base，实际运行的是还没提交的 V 改动。这些是调试日志，不作为证据。

### P5 exit 后的当前处置

本节保留上面的 G11 审核观察作为历史记录；当前状态以 [P5 exit review](p5-exit-review.md) §6.2 和 §7 EXIT-F4 为准。

- **R2-O1 / G11b-O1：** 已由后续 G12/DC34 的镜像身份规则覆盖；按当前同 worktree manifest 规则判定 carried。
- **R2-O2：** 三项 SQLite `busy_timeout` 并发用例仍有条件重开项；出现不稳定时由 Backend 测试 owner 移回 serial。
- **R2-O3：** 已关闭；相关子进程测试现标为 integration/serial，P5 exit 的 unit 收集核对为 0 selected。
- **R2-O4：** 无效调试尝试继续只作非证据，不是待修代码项。
- **G11b-O2：** 仍是历史门禁耗时归因的测量限制；仅在后续门禁性能分析时考虑，不作为产品容量证据。
- **G11b-O3：** Compose 旅程继续串行；并发优化需 owner 另立授权步骤，未列为阶段退出前置。
