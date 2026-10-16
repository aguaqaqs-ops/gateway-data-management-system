# P5 架构收口 S2b 独立审核（第 1 次复审）

- 结论：**通过**
- 日期：2026-10-16
- 审核对象：p5-s2b @ `b9424eafe716b64f7654b53a3093a3b3efae06c6`（H），门禁提交 V `753c5768a533885b5e0af0865cfe28c62df3ce27`；
  base main merge-base `cae9a0f82be3415cc362e46b98da954edcf1d807`。main 在 merge-base 之后只有审核方文档提交（62cc7c3e0f、1925dcedc2、5a1a391ea8、92db9df18e、a889acc242）。
- 上次审核：`plans/p5-arch-closure-s2b-independent-review.md`（`e94008889c`，需修订，阻塞项 S2b-F1）。
- 范围：`e94008889c..b9424eafe7`，共 5 个提交：
  - fix `d450f946bf`（S2b-F1）；
  - fix `4049986e4c`（S2b-F2、S2b-F4）；
  - test `753c5768a5`（Compose oracle 补传取消回调）= V；
  - docs `43722bb575`、`b9424eafe7`（handoff，S2b-F3）。
- 生产代码只改了 `vnext/backend/src/gateway_backend/` 下 4 个文件：`operations/recovery.py`、`application/preview_jobs.py`、`application/pair_pipeline.py`、`application/history/compare_jobs.py`。
- 依据：
  - 第一轮报告 §6；
  - 执行计划 §2/§3 S2b、§8.9；
  - owner 决议 DC30、DC31；
  - AGENTS.md「权威入口的运行前提」与「镜像身份等价」；
  - handoff §8.4–§8.10。
- 审核在只读 detached worktree `/home/dev/gdds-review-s2b` 中进行。carried 重建在 V 的 worktree `/home/dev/gdds-p5-s2b` 中完成，只执行 identity 计算和 `docker compose build`，没有写任何被跟踪的文件。

## 1. 结论摘要

第一轮的 4 项 Finding 都已关闭，修订没有引入新的阻塞问题。

- **门禁：** V 上的权威 runner `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh` exit 0，起止 HEAD 都是 V，起止 status 都是 clean。
- **carried：** V→H 只改 handoff。我在 V 的 worktree 中独立重做了 carried 判定，RS identity 与 label 一致，backend/worker image ID 与 V 的 provenance 完全相同。
- **真实数据：** 按 owner 确认，沿用 `b0175cf583` 的 t1–t4 取证。修订改动的是 worker 启动恢复和组装阶段的取消终态，真实数据旅程不经过这两条路径，复用成立。

下面 §3 记录 3 项观察，均不阻塞 S2b 合入。

**S2b 可以打 `p5-s2b-exit` 并合入 `main`。**

## 2. 原 Finding 关闭情况

### S2b-F1（阻塞）：已关闭

- **生产代码：** `recovery.py` 的 `StartupRecovery.recover_pair` 不再查询 capability。只要租约未过期，任何 capability 都返回 `RETRYABLE_BLOCK`；事务内复查发现租约未过期时，也改为返回 `RETRYABLE_BLOCK`（原来返回 `READY`）。租约过期后仍按原 R5 处置表执行：
  - `PURE_RECOMPUTE` → `RETRY_WAIT`，诊断 `R5.RETRY_SCHEDULED`；
  - `EXTERNAL_EFFECT` → `RETRY_WAIT`，诊断 `R5.RECONCILE_STARTED`；
  - `NON_RETRYABLE` → `MANUAL_RECOVERY_REQUIRED`，startup 返回 `FATAL_BLOCK`。

  R5 处置表、operation/step 状态集和正常领取循环都没有改，DC31 的停止条件未触发。
- **启动循环有界性：** `worker_runtime.py` 的 startup 循环对 `RETRYABLE_BLOCK` 按退避重试，每轮都重新调用 `startup()` 读取租约。因此旧租约在 30 s 内过期后，下一轮会进入 R5 处置，不会永久阻塞。
- **测试：** `test_operation_takeover.py` 删除了固化旧行为的 `test_live_external_effect_lease_keeps_existing_startup_behavior`，新增两组参数化测试：
  - `STARTUP_LEASE_DISPOSITION_CASES`：3 种 capability × 有效/过期租约，共 6 行，断言 startup 处置、step 与 operation 状态、租约字段和诊断码；
  - `test_transaction_recheck_blocks_a_lease_that_became_live`：外层时钟判定已过期、事务内时钟判定仍有效的竞态，覆盖 3 种 capability。

### S2b-F2：已关闭

- **生产代码：** 下面两处组装循环在检测到取消时，先通过 `on_cancel` 发布 `_make_cancelled_terminal_builder()` 终态，再抛出 `PairPipelineCancelled`，由 handler 捕获并返回 `PUBLISHED`：
  - Preview 的组装循环（`_assemble_preview`）；
  - History 的组装循环（`_assemble_comparison`）。

  `pair_pipeline._run_comparison_risk_surface` 的取消检查也走同一路径，Preview 和 History 共用它。两处 `_run_pair_pipeline` 包装都先放行 `PairPipelineCancelled`，因此它不会被改写为 `PreviewJobError` / `HistoryCompareJobError`。
- **测试：** 新增 3 个用例，分别覆盖 Preview 组装循环、Preview pair pipeline 内部、History 组装循环，都断言 acknowledgment 为 `PUBLISHED`、operation 为 `CANCELLED`。History 的 pair pipeline 内部取消没有单独用例，但它与 Preview 共用 `_run_comparison_risk_surface` 和同一个 `on_cancel` 接线，可以接受。
- **配套修复：** V `753c5768a5` 给 Compose oracle 脚本补传了无副作用的 `on_cancel`。这是新增必填参数带来的配套修改，调试阶段一次 runner 失败（日志 `s2b-revision-gate-4049986e4c.log`）正是这个原因，handoff 如实记录了。

### S2b-F3：已关闭

逐项核对 handoff：

- §4 与 §8.7 已更正：projection version 1→2 由 `26560b2595`（S2a-F1）引入，DC29 没有再改它，golden 变化来源已逐项说明。
- §1 新增预算外生产路径登记表，覆盖第一轮报告列出的 risk engine、bundle assembly、artifact store、materialize/artifact、mutation planner/renderer、`_ordered.py`、comparison、surface 八类，每项都写了提交和理由。
- §1、§8.3 已更正 V 的说明：拦截点从 `commit_exists` 移到 `catalog_at`，原因是 `09c3e8c217` 引入的 Catalog 缓存。
- §8.4 已把两项 integration 测试归入 backend 批次。
- 重复的 `8.1` 小节已删除，全文只剩一处 `### 8.1`。

`p5-arch-closure-s0-owner-decisions.md` DC29（§12）与 Canonical Storage 3.2.0 段落里“storage projection version 不变”的表述属于 main 上的审核方文档，按第一轮报告的约定由审核方在合入时更正，不归实施方。

### S2b-F4：已关闭

- **测试：** `REPOSITORY_READ_FAILURE_CASES` 删除了绕开生产路径的“确定性错误”一行。新增 `test_deterministic_catalog_failure_is_publicly_diagnostic`，它从 provider 的 `get_catalog` 抛出确定性 `RepositoryProviderError`，依次经过 `materialize_repository_ref` 和 materialize handler，最终得到公开的 `FAILED` operation，诊断码为 `REPOSITORY_CATALOG_LOAD_FAILED`，消息带出 `RESPONSE_LIMIT_EXCEEDED`。
- **两段证据的衔接：** 这个用例使用 fake provider，消息格式 `catalog read failed (RESPONSE_LIMIT_EXCEEDED: …)` 与真实 `http_arrow._provider_error` 的输出一致（`f"{operation} failed ({wire_code}: {message})"`）。HTTP 500 + `RESPONSE_LIMIT_EXCEEDED` 被判为 non-retryable，由 `test_production_wiring.py::test_http_arrow_catalog_errors_have_stable_retry_classification` 负责。两段合起来覆盖了完整链路。
- **不可达分支：** `preview_jobs.py` 与 `compare_jobs.py` 中的 `if not exc.retryable: raise` 改成了断言。我核对了 `repository_ref.py`：`open_ref`、`get_catalog`、`open_table_reader` 和流读取抛出的确定性 `RepositoryProviderError`，都被转换为失败的物化结果或 `_Halt`，不会到达 handler。断言确实不可达。

## 3. 观察（不阻塞）

### R1-O1：handoff §8.10 的措辞

handoff §8.10 写的是“删除” `if not exc.retryable: raise`，实际是改成了 `assert`。这只是措辞偏差，且就算以 `python -O` 运行把断言去掉，这条分支也不可达。不要求修改。

### R1-O2：启动时阻断有效租约，前提是单 worker 部署

新行为（任何有效租约都阻断 startup）依赖当前设计的前提：single host、single worker，见纵切设计 `p5-business-vertical-slices-design.md` 和 P4 运行时计划。只要只有一个 worker，startup 遇到的有效租约必然属于已退出的上一个进程。

如果以后引入多 worker，新 worker 会一直等到其他活跃 worker 手上没有 RUNNING 租约才就绪。Phase 6 的容量重构（DC31 三）如果考虑多 worker，需要重新设计这一处，例如让租约记录 worker 身份并据此判定。在此之前不需要处理。

### R1-O3：可选的 ADDED / REMOVED 表数没有补

handoff §8.8 说明没有补，也没有把 t2 v2 Preview `table_count=219` 与 Catalog 208 张的差值当作观测结果，处理得当。这个差值留作 S5 或后续真实数据复核时的一个检查点。

## 4. 实际执行的检查

| 检查 | 结果 |
| --- | --- |
| 区间 | `e94008889c..b9424eafe7` 共 5 个提交；V→H 只改 `p5-arch-closure-s2b-handoff.md` |
| V 的 runner 日志 `s2b-revision-gate-753c5768a5.log` | 起止 HEAD 都是 V，status 前后都是 clean，`runner_exit_code=0`；shared_kernel 242、repository_contracts 152、repository_client 154、backend 2,847（1 warning）、RS parallel 1,684 + 1 skipped、RS serial 205 |
| provenance `s2b-revision-gate-753c5768a5-provenance.json` | project `ordered-bisect-b-4106342-baseline`；RS `196148be…`，backend `4c7dd924…`，worker `f8b59e3d…` |
| 我独立做的 carried（`s2b-rereview-carried-b9424eafe7.log`，在 V 的 worktree、HEAD=H、status clean） | RS identity：build-input `adc5d87fea…`，source-tree `sha256:5b34d0c5…`，与 RS 镜像 label 一致；`COMPOSE_PROJECT_NAME=ordered-bisect-b-4106342-baseline docker compose -f vnext/deploy/compose.yaml build backend worker` 后，backend `sha256:4c7dd924…`、worker `sha256:f8b59e3d…`，与 provenance 相同；两次构建之间没有运行测试 |
| backend focused（审核 worktree，HEAD=H） | takeover、preview assemble/materialize、history compare、recovery policy、production wiring 及 worker/cancel 相关文件：264 passed |
| backend 静态检查 | ruff 全部通过，mypy 475 个源文件无问题。修订只改了 backend，其余四个包和 `import_rules`（0 / 0 / 14）沿用 handoff 与 V runner 的结果 |
| 代码核对 | `recover_pair` 两处返回值、`worker_runtime` startup 退避循环、三处取消接线、`http_arrow._provider_error` 的消息格式与重试分类、`repository_ref` 对确定性错误的转换 |

## 5. 合入后的审核方事项

1. 在 main 上更正 owner 决议 DC29（§12）与 Canonical Storage 3.2.0 段落中“storage projection version 不变”的表述：版本已由 S2a-F1（`26560b2595`）从 1 升到 2。
2. 在 main 上更正 DC31 的 oracle 表述：History 一项按实际可观测的 record_count 与 bundle/surface digest 记录，不要求按 kind 计数。
3. S3 之前完成治理修订计划 G11（backend 并行化）。
