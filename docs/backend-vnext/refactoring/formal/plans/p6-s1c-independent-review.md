# Phase 6 S1c 独立审核（代码候选）

状态：**结论为定向修订（F1–F4）。** F3 涉及 DC65 条文的解释，须 owner 先裁定。

## 1. 审核对象与方法

- 基线 `main` = `a48ade2e8f`。代码候选 V = `2ffdd0d22dcaa82125f9f19661d8ff876b89acd3`，handoff 提交 H = `6aa9ad466359251bac47d0b7a8b384e0825e15ab`，分支 `p6-s1c-impl`（本地）。`2ffdd0d22d..6aa9ad4663` 只改 handoff。
- 授权与依据：DC65 及 2026-10-30 修订、DC66；执行计划 §2 S1c；External Effect and Recovery Contract §4；P4 R5 设计 §6–§8；P5-5B 设计 §13.1。
- 方法：
  - 在开发主机的只读 detached worktree（`/home/dev/gdds-p6-logs/s1c/review-initial-wt`，HEAD = H）阅读 `a48ade2e8f..H` 的全部代码、测试与文档 diff，并与基线代码逐处对照；
  - 在 `ct108-gw-dms-05` 复跑 focused 测试，并用探针复现 F2；
  - 不运行完整 runner 与真实数据（DC64 第 1 项）。

## 2. 复跑结果（节点 `gw-dms-test-05`）

| 项 | 结果 | 日志 |
|---|---|---|
| focused 测试：`test_operation_recovery_policy`、`test_operation_takeover`、`test_submit_job_effect`、`test_operation_state`、`test_submit_recovery`、`test_operator_recovery_http`、`test_submit_job_prepare` | 2026-10-30 13:27:41–13:28:14 UTC，HEAD `2ffdd0d22d`，351 passed、exit 0，前后 worktree clean | `/home/dev/gdds-p6-logs/s1c/review-claude/focused-2ffdd0d2.log` |
| F2 探针（真实 `RepositoryClient`，进程内 MockTransport 固定返回 RUNNING） | 13:23:28–13:26:59 UTC，exit 0；见 F2 | `/home/dev/gdds-p6-logs/s1c/review-claude/poll-deadline-edge.log`（脚本 `poll_deadline_edge.py` 同目录） |

审核用 detached worktree 在 05 无法离线构建 backend 环境（依赖下载需网络）。focused 测试改在实施者的 05 worktree `/home/dev/gdds-p6-s1c-05` 中以 `--no-sync` 运行：该 worktree HEAD 为 `2ffdd0d22d` 且 clean，运行期间实施者空闲，Hypothesis 存储指向 TMPDIR 并在运行后删除，前后均无 tracked 改动。

## 3. Findings

### F1（高）等待上界在观测之前判定，超时后的 step 永远无法完成

位置：`application/submit_jobs.py` `build_await_import_result_handler`，约第 861–871 行（轮询前）与轮询返回后的 `now >= wait_upper_bound_at` 判断（在身份与状态判断之前）。

- 轮询前：`remaining_wait_seconds <= 0` 时直接 `_publish_wait_upper_bound_exceeded`，不查询 Repository Service。
- 轮询后：只要当前时间已过上界，即使本次轮询拿到的是 SUCCEEDED 或 FAILED 终态，也丢弃结果，转人工恢复。
- `started_at` 在人工恢复命令与重新领取后都不变。

失败情形：
1. await step 于 T0 开始；Repository Service 导入在 T0+50 min 成功；worker 在等待期间崩溃，或 operator 于 T0+70 min 处理人工恢复；
2. 重新领取或 `RESUME_RECONCILE` 之后，handler 不轮询就判定超出上界，回到 `MANUAL_RECOVERY_REQUIRED`；
3. 再次发送 `RESUME_RECONCILE` 得到同样结果。`ABORT_CONFIRMED_FAILURE` 需要 FAILED 证明，而 Repository 侧实际已经成功。于是这个 Submit 无法完成也无法中止，business occupancy 一直保留。

这正是 S1c 要消除的“人工恢复后无路可走”（DC65 修订第 2 项），只是触发条件改成了“距 await 开始超过 3630 s”。

修订要求：
- 上界只约束“继续健康等待”：
  - 每次领取都先观测一次（轮询期限取 `min(60, max(剩余时间, 一个下限))`，或在超界时做一次短轮询）；
  - 观测为终态时，照常处理 T3 或中止，与上界无关；
  - 只有观测为 QUEUED/RUNNING 且已过上界时，才转人工恢复；
  - 超界后的传输错误或结果未知转人工恢复。
- 测试（`test_submit_job_effect.py`）：
  - 超过上界后，`RESUME_RECONCILE` 遇到 Repository SUCCEEDED 时完成 Submit；
  - 轮询窗口恰在上界到达时返回终态，结果不被丢弃；
  - 超过上界仍为 RUNNING 时转人工恢复（已有用例保留）。

### F2（中）轮询截止边缘的请求超时会丢弃已有的健康观测，随机消耗恢复会话

位置：`repository_client/poll.py` `wait_for_operation_or_last_observed`；`client.py` `wait_operation_or_last_observed`，以及其调用的 `get_operation(deadline_at=...)` → `retry_idempotent_request`。

- 机制：
  - `retry_idempotent_request` 以 `asyncio.wait_for(timeout=remaining)` 把单次 GET 限制在本次 60 s 窗口的剩余时间内；
  - 如果最后一次 GET 在窗口快结束时发出，响应晚于截止时刻，就抛出 `RepositoryClientTimeoutError`；
  - 新函数不捕获这个异常，所以前面已经拿到的 RUNNING 观测作废；
  - backend 把它当作结果未知，计入一次恢复会话。可重试错误的退避睡眠跨过截止时刻时同理。
- 复现（第 2 节探针，每档 40 个窗口，窗口长度 1.00–2.95 s）：
  - 响应延迟 0.2 s：12/40 个窗口以超时结束；
  - 响应延迟 0.02 s：0/40。
- 估算：60 s 窗口、1 s 轮询间隔下，每个窗口出错的概率约为“响应延迟 / 轮询间隔”。按 1030b 日志中约 20 ms 的 GET 延迟，每窗口约 2%，一小时健康等待中误计满 3 次、转人工恢复的概率约 12%。Repository Service 负载高、延迟上升时更大。数值是估算，机制已复现。
- 修订要求：
  - 新函数中，如果超时是本次轮询自身的截止造成的，且已有成功的非终态观测，就返回该观测；
  - 或在剩余时间不足一次请求所需时不再发起请求；
  - 传输错误、协议错误仍抛出（DC65 第 2 项）。
- 测试缺口：新函数在 `vnext/repository_client` 包内没有任何测试；backend 测试用假的 `repository_write`，覆盖不到真实轮询。按测试 owner 原则，在 repository_client 包内补测试，覆盖：
  - 截止时刻有请求在途；
  - 截止前已有健康观测；
  - 没有任何成功观测；
  - 截止前观测到终态。

### F3（中，须 owner 先裁定）身份与指纹不符从立即人工恢复改为计数重试

位置：`submit_jobs.py` `_map_handler_failure_to_recovery_outcome` 新增的 `CheckpointDecodeError(code=EXTERNAL_EFFECT_IDENTITY_MISMATCH)` 分支；`_submit_state_from_job_state` 中六处 `CHECKPOINT_JOB_STATE_MISMATCH` 改为 `EXTERNAL_EFFECT_IDENTITY_MISMATCH`；await 中 Repository 返回的 operation_id 与 checkpoint 不符时的 `_publish_counted_reconcile_pending`；P4 R5 设计 §6 新增的 “identity or request-fingerprint mismatch → count as reconcile failure” 一行。

- 基线行为：这些不符都属于 `CheckpointDecodeError`，立即进入 `MANUAL_RECOVERY_REQUIRED`（`r5.manual_recovery_required`）。
- 候选行为：先按计数重试，第 3 次才进入人工恢复。不符是确定性的，重试不会改变结果。
- 诊断误导：经 `_publish_counted_reconcile_pending` 用尽后，诊断码是 `R5.RECONCILE_TIMEOUT`（消息中附原因）。这个码的含义是“Repository 慢，可以 RESUME_RECONCILE”，基准工具的恢复条件也正是 `r5.reconcile_timeout`。operator 或工具可能对一个证据矛盾发出恢复命令，命令后再次失败，回到人工恢复。
- 与 Contract 的关系：External Effect and Recovery Contract §4 规定，`MANUAL_RECOVERY_REQUIRED` 表示证据矛盾。确定性的身份与指纹不符正是证据矛盾，应立即进入人工恢复，并保留能说明原因的诊断码。
- 来源：DC65 决议第 2 项写有“身份或指纹不符……仍计入 3 个恢复会话”。实施者按字面实现。该句原意是“不属于健康等待”，并非把证据矛盾改为可重试。
- 建议 owner 裁定：
  - 澄清 DC65 第 2 项：身份或指纹不符（本地 checkpoint 与 payload 不符、Repository 返回的 operation identity 不符）维持基线的立即人工恢复，使用可区分的诊断码；只有传输错误与结果未知计入 3 个恢复会话。
  - 实施者恢复上述映射与诊断，并修订 P4 R5 §6 该行与 handoff 的调用方盘点表。

### F4（低）handoff、Contract 与测试的补充

1. **传输错误映射的影响面**：`RepositoryWriteTransportError` 由人工恢复改为 `RECONCILE_PENDING`。这一改动同样作用于 `submit_import` 的恢复路径：重新领取后以同一 import idempotency key 重发。按 DC65 可以接受（键幂等），但 handoff 的新旧规则对照没有写出。需要补写，并补一个测试：`submit_import` 恢复时遇传输错误，计数，重新领取后以同一键重发，不产生第二个 Repository operation。
2. **诊断码承载计数语义**：领取时是否增加 `attempt_count`，现在取决于 RETRY_WAIT step 的诊断码（`R5.HEALTHY_WAIT_HANDOFF`、`R5.HEALTHY_WAIT_HANDOFF_OPERATOR`、`R5.RECOVERY_AUTHORIZED`）。Operation Lifecycle Contract 只写了 RUNNING step 的诊断规则，应补一条：上述诊断码在 RETRY_WAIT 上的含义，以及它们对领取计数的影响。
3. F1、F2 的测试缺口见各自条目。

## 4. 已核对、无需修改的事项

- 状态转换：
  - 人工恢复命令改为 `MANUAL_RECOVERY_REQUIRED → RETRY_WAIT`（立即可领取），不再持有 operator lease；领取时 `attempt_count` +1，诊断转为 `R5.OPERATOR_RECOVERY_SESSION`；
  - 该会话内计数型失败与 `RECONCILE_PENDING` 转人工恢复；
  - 会话 lease 丢失后，startup 转人工恢复且返回 READY。
  - 与 DC65 修订第 2 项一致；未新增状态、字段、IPC 或 sidecar。
- 健康等待：
  - 仅 Submit await 在拿到匹配 operation 的 QUEUED/RUNNING 后传 `healthy_external_operation_wait=True`；重新领取保持 `attempt_count` 与 `started_at`；
  - checkpoint ref 在多次让出间复用，不新增 artifact。
- 诊断清除：RUNNING step 只允许 `R5.OPERATOR_RECOVERY_SESSION`。Submit 的成功路径（`_terminal_step`、successor、finalize 两处）都清除诊断。operator 命令只接受 Submit 的三个 step（`build_submit_recovery_capability_mapping`），其他 job 的终态路径不会带上该诊断。
- startup：RETRY_WAIT（含命令后尚未领取）返回 READY，不判为会话用尽。
- HTTP 200/409、能力校验与 optimistic version 未变。
- 设计与 Contract 修订范围与 DC65 一致（F3、F4 第 2 项除外）。

## 5. 观察项（不要求本阶段修改，交 owner 知悉）

- **遗留**：非 operator 会话中，会话已用尽、lease 过期的 RUNNING step 在 startup 仍会转人工恢复，并阻断该次启动（`BLOCK_STARTUP_FATAL`）。这与 P4 R5 §8“人工恢复记录不阻断 readiness”的表述有出入。这是基线行为，不属于 S1c 范围，建议登记为遗留，由 owner 决定归属。
- **依赖获取**：05 的构建经开发节点上的受限代理访问 PyPI 与 GitHub release 主机，而不是取用已预置的缓存，且临时替换后恢复了 `rust:1.97.0-bookworm`。AGENTS 允许测试 CT 经局域网取用获准的缓存，但“不表示获准任意公网访问”。实施者已限制主机范围，并在 handoff 中记录。请 owner 确认这种代理方式是否可接受，或要求以后改为先预置缓存。

## 6. 结论

定向修订。F1、F2 为实现缺陷，修订后需补测试；F3 待 owner 裁定后实施；F4 为文档与测试补充。修订后由同一审核会话复审代码，复审通过前不进入取证（DC64 第 1 项）。
