# Phase 6 S1c handoff

## 状态

代码候选，等待独立审核。当前基线为 `main` / `a48ade2e8f99d9b7be8165adf99a257e0cca2a55`；
工作分支为 `p6-s1c-impl`。此版尚未运行节点验证、权威 runner 或真实数据，不包含阶段证据。

实现提交：`9d13e9d3bd`（backend / repository client）；
测试提交：`307b33ccec`；设计与 Contract 文档提交：`3eb02b691e`。
handoff 本身随后单独提交，节点验证结果在 clean worktree 完成后补记。

## 改动清单

- `vnext/repository_client/.../poll.py`、`client.py`：新增 bounded poll 入口；poll deadline 到期时，若已有成功的非终态观测则返回最后观测；没有成功观测或请求失败仍抛出原错误。
- `vnext/backend/.../application/submit_jobs.py`、`infrastructure/repository_write/http.py`：Submit 使用每次 60 秒 poll 和 3630 秒总等待上界；注入时钟、等待函数；匹配的 `QUEUED`/`RUNNING` 使用 checkpoint 和专用 healthy handoff；未知结果、传输错误和 identity/fingerprint mismatch 计入恢复会话。
- `vnext/backend/.../operations/`：仅 Submit 显式标记健康等待时把 Step 释放到立即可领取的 `RETRY_WAIT`，reclaim 保持 `attempt_count`；普通 safe handoff 沿用原行为。operator resume/retry 使用 `MANUAL_RECOVERY_REQUIRED → RETRY_WAIT`，由 worker claim 增加一次 attempt，并通过现有 diagnostic 字段保留授权会话。
- 测试更新位于 `test_operation_recovery_policy.py`、`test_operation_takeover.py`、`test_submit_job_effect.py` 与既有 Submit harness；`test_operator_recovery_http.py` 的现有 HTTP 200/409 断言保持 owner。未新增按轮次命名的测试文件。
- 设计与 Contract 更新位于 P4 R5 §6–§8、P5-5B §5.4/§13.1、External Effect and Recovery Contract、Operation Lifecycle Contract，以及 P4 R5 S2c handoff 的 S1c 修订说明。

## 新旧规则与调用方盘点

| 调用路径 | 可取得的证据/行为 | S1c 规则 |
|---|---|---|
| Submit `await_import_result` | 本地 Submit checkpoint 的请求字节、request fingerprint、operation identity 已验证；成功读取原 Repository operation，响应 ID 匹配且状态为 `QUEUED`/`RUNNING` | 单次 60 秒到期不计恢复会话；复用 checkpoint，专用 healthy handoff 立即让出 lease；重新领取不增加 `attempt_count` |
| Submit poll timeout 且无成功观测、transport error、无效/未知结果 | 未取得健康运行证据，结果仍未知 | 继续使用最多 3 个恢复会话；第 3 次进入 `MANUAL_RECOVERY_REQUIRED` |
| Submit Repository operation ID 或本地请求 fingerprint/identity 不匹配 | 观测与原 operation/request 绑定不一致 | 作为计数型 reconcile 失败；不进入健康等待路径 |
| Worker crash、lease 丢失或运行期 takeover | 没有 Repository 明确健康观测 | 沿用 R5 会话预算；已耗尽时转人工恢复 |
| 其他 `RECONCILE_PENDING` policy 调用方 | 无法给出上述 Submit 健康观测 | 保持原来的三会话规则，不使用 healthy-wait marker |
| 通用 safe handoff 的其他调用方 | 例如测试 external-effect stub 的 accepted/unknown 结果，没有 Repository 健康观测 | 默认保留原 safe-handoff 行为；只有 Submit 显式传入健康观测资格才释放为 count-free `RETRY_WAIT` |

生产代码中唯一 `acknowledge_safe_handoff` 调用方是 Submit await handler。R5 的通用
`RECONCILE_PENDING` policy 仍负责其他失败路径；本次没有把 policy 全局改为 count-free。

## 等待上界

`SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS = 3600.0 + 30.0`（当前 3630 秒），起点为 await Step 已有的
`started_at`。这与 Repository Service `Settings.import_timeout_seconds`（默认 3600 秒）加
`Settings.server_start_timeout_seconds`（默认 30 秒）耦合。到达上界后进入
`MANUAL_RECOVERY_REQUIRED`，diagnostic message 包含“超出等待上界”。单次 poll 保持 60 秒。

## 人工恢复后状态与会话

`RESUME_RECONCILE` 和 `RETRY_FROM_CHECKPOINT` 被接受后，Step 变为已有可领取状态 `RETRY_WAIT`，
设置为立即可领取；Operation 回到 `RUNNING`；命令不持有 worker lease，也不直接改
`attempt_count`。现有 Step diagnostic 暂存 `RECOVERY_AUTHORIZED`，worker claim 时将
`attempt_count` 增加一次并转为 `OPERATOR_RECOVERY_SESSION`。该会话的计数型失败回到人工恢复。
健康等待可重复 handoff，但通过 operator 专用 healthy marker 保留该 attempt 与授权会话。

命令后、首次 claim 前重启时 Step 仍是可领取的 `RETRY_WAIT`，startup 不将其判为会话耗尽且不阻断
启动。授权会话 claim 后若 lease 丢失，startup 将 Step/Operation 转回人工恢复并保持 `READY`。
HTTP 200/409、能力校验、授权和 optimistic-version 语义不变。实现只使用现有状态和 diagnostic 字段；
没有增加 schema、checkpoint payload、IPC 或 sidecar。

## Contract 与测试归属

- External Effect and Recovery Contract 仅补入 Submit 健康等待与总等待上界规则；operation 四态、T1/T2/T3 与 unknown outcome 不 blind replay 不变。
- Operation Lifecycle Contract 仅补入已授权 manual Step 到现有 `RETRY_WAIT` 的转移及实际 lease 由 worker claim 授予。
- 健康等待、上界、transport/unknown/identity 计数与 checkpoint 去重由 `test_submit_job_effect.py` 覆盖；通用恢复决策及 operator counted failure 由 `test_operation_recovery_policy.py` 覆盖；worker claim、operator 命令、重启与 lease loss 由 `test_operation_takeover.py` 覆盖；operator HTTP 200/409 语义由 `test_operator_recovery_http.py` 继续覆盖。

## 代码候选验证

| 验证 | 结果 |
|---|---|
| focused 测试（05） | 待审核通过后运行 |
| 五包 ruff/mypy（05） | 待审核通过后运行 |
| 05 预检 §8.9 | 待审核通过后运行 |
| 04 权威 runner | 待审核通过后按 manifest compare 决定逐包运行或沿用 |

## 阶段取证计划（DC66 修订）

证据前提：本阶段不改 control DB schema、checkpoint payload 或 Repository Service；若最终候选不满足，
停止并改为 2× t4 整档运行。当前 handoff 不记录实际运行结果。

- 05：t1 完整旅程（冒烟）。
- `ct108-gw-dms`：不跑 t4 完整旅程；在该节点空闲并确认后，用 S1c 最终候选镜像，从
  `p6b2xwarmr5fix1030b` 的 v1-submit checkpoint 只读副本续跑 2× t4 Submit。
- 记录恢复会话数、健康让出次数、Repository 导入用时、Submit 用时，并与 1030b 保留卷只读副本的
  Dolt 表哈希及 canonical state 对照。
- 取证合并提交仅在节点上生成，包含 S1c 候选与基准工具提交；确认相对 S1c 候选仅改
  `vnext/backend/benchmarks`、相应测试与 docs，handoff 记录双亲和 `diff --stat`；不合入、不推送。
- 权威 runner 在 04；每包记录实际运行或沿用、来源 V 与来源日志、manifest 和镜像身份。
- 每条运行日志记录节点、HEAD、起止时间、exit code 与日志路径；真实数据各步骤 checkpoint 来源和失败续行
  按 DC66 规则记录。

## 偏差与清理

目前无运行偏差。1030b 保留卷和 v1-submit checkpoint 在 S1c exit 后由 owner 安排清理；本阶段不清理。
