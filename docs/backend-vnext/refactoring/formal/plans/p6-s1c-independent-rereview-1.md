# Phase 6 S1c 独立复审 1（代码候选）

状态：**代码通过。** 可以进入 DC64 第 1 项 c 的取证；取证结果由同一审核会话复核。

## 1. 复审对象

- 首次审核：[p6-s1c-independent-review.md](p6-s1c-independent-review.md)（F1–F4，定向修订）；owner 对 F3 的裁定见 DC65 的“澄清”。
- 代码候选 V = `3008d578cf2ee0eaf9236f01e33b5008d65ef36c`，handoff 提交 H = `f5c9da8ae7650f6c20f5a4de320b02e91db33de2`，分支 `p6-s1c-impl`（本地）。
- 关键区间：
  - V 已合并 main `43c1d4d513`；
  - `6aa9ad4663..3008d578cf` 为本轮修订；
  - `d95430ee48..3008d578cf` 只改 External Effect Contract、P4 R5 设计与 P5-5B 设计中诊断码的名称；
  - `3008d578cf..f5c9da8ae7` 只改 handoff。
- 方法：阅读本轮源码、测试与文档 diff；在 `ct108-gw-dms-05` 复跑 focused 测试、repository_client 新测试与 F2 探针。

## 2. 逐项核对

| Finding | 修订 | 结论 |
|---|---|---|
| F1 等待上界先于观测 | `build_await_import_result_handler`：去掉轮询前的超界判定，每次领取都先观测，轮询期限为 `min(60, max(剩余, 5 s))`；终态（SUCCEEDED/FAILED）不受上界影响；只有 QUEUED/RUNNING 且已过上界时转人工恢复；超界后的超时或传输错误转人工恢复，超界前的仍计数。新测试：`test_resume_reconcile_after_wait_upper_bound_accepts_succeeded_operation`、`test_terminal_operation_returned_at_wait_upper_bound_completes_submit`、`test_poll_failure_after_wait_upper_bound_requires_manual_recovery` | 已关闭 |
| F2 截止边缘丢弃健康观测 | `poll.py`：请求因本次截止而超时（`RepositoryClientTimeoutError` 且剩余时间 ≤ 0）且已有成功的非终态观测时，返回该观测；去掉终态之后的截止检查，截止时观测到的终态照常返回；传输与协议错误仍抛出。repository_client 包在已有的 `tests/test_operation_poll_client.py` 中新增 6 个测试函数（截止时请求在途、退避跨过截止、无成功观测、截止时与截止前的终态、传输与协议错误） | 已关闭；探针复核 0/80 超时 |
| F3 身份与指纹不符 | 本地 checkpoint 与 payload 不符、Repository 返回的 operation identity 不符，均立即进入 `MANUAL_RECOVERY_REQUIRED`，诊断码为 `r5.effect_identity_mismatch`，不计入会话。测试：`test_submit_recovery_classifies_transport_and_identity_mismatch`、`test_await_import_rejects_mismatched_repository_operation_id`（断言 attempt_count 不变、诊断码正确）；P4 R5 §6 与 External Effect Contract 已按 DC65 澄清修订 | 已关闭 |
| F4 文档与测试补充 | handoff 写明传输错误改为计数，并作用于 `submit_import` 恢复；新增 `test_submit_import_recovery_counts_transport_failure_and_reuses_idempotency_key`；Operation Lifecycle Contract 补写 RETRY_WAIT 上三个诊断码对领取计数的影响 | 已关闭 |

没有发现新的问题。附带核对：
- F2 的判定条件 `remaining() <= 0`：asyncio 的定时器最多可能提前一个时钟分辨率（约 1 ns）触发，而超时异常传到判定处至少要经过微秒级处理，实际不会落到正值一侧。探针结果与此一致。
- `_publish_manual_recovery` 复用了原超界路径，诊断码按调用方区分；超界与身份不符两条路径都不消耗会话。

## 3. 复跑结果（节点 `gw-dms-test-05`）

运行位置：实施者的 05 worktree `/home/dev/gdds-p6-s1c-05`，HEAD `d95430ee48`（V 的父提交，与 V 只差文档），clean，使用已有环境、`--no-sync`，未设置代理；Hypothesis 存储指向 TMPDIR，运行后删除。审核者没有移动该 worktree 的 HEAD。

| 项 | 结果 |
|---|---|
| backend focused：`test_operation_recovery_policy`、`test_operation_takeover`、`test_submit_job_effect`、`test_operation_state`、`test_submit_recovery`、`test_operator_recovery_http`、`test_submit_job_prepare` | 355 passed，exit 0 |
| repository_client：`tests/test_operation_poll_client.py`（全文件，含已有用例） | 23 passed，exit 0 |
| F2 探针（延迟 0.02 s 与 0.2 s，各 40 个窗口） | 0/40、0/40 超时；修订前在 0.2 s 下为 12/40 |

时间 2026-10-30 14:32:40–14:35:54 UTC，前后 worktree clean。日志：05 `/home/dev/gdds-p6-logs/s1c/review-claude/rereview1-d95430ee.log`。

## 4. 进入取证前的说明

- **Compose 镜像**：实施者在开发节点尝试的缓存构建因 uv bootstrap 层不可用而未完成（handoff“验证与偏差”），本轮没有 Compose 预检结果。取证时，04 权威 runner 的 backend 批次会构建并运行 Compose。04 现有约 15 GB 构建缓存，S1b 的 runner 也在 04 构建过。按 DC67，构建因缓存缺失失败时停止，先补预填充，不用代理，再从头运行。
- **carried 来源**：S1b 的 04 门禁 worktree 已在 S1b exit 后按 DC51 清理，本阶段没有可在同一 worktree 比较的来源 V。因此 04 权威 runner 在新的门禁 worktree 中运行全部六个包；这次运行将成为后续阶段的来源 V。
- **ct108 的 2× t4 Submit**：依赖基准会话按 DC66 第 3 项实现“从失败运行的 checkpoint 续跑”。截至本复审，`p6-baseline` 在开发主机、05、ct108 上都没有 `fc9ba62412` 之后的提交，该能力尚未就绪。04 runner 与 05 t1 冒烟可以先行。
