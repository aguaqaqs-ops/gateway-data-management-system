# Phase 6 S1c handoff

## 状态

代码候选，等待独立审核。基线为 `main` / `a48ade2e8f99d9b7be8165adf99a257e0cca2a55`；
工作分支为 `p6-s1c-impl`。代码候选 HEAD：`2ffdd0d22dcaa82125f9f19661d8ff876b89acd3`。
该 HEAD 在 CT05 的 clean、已提交 worktree 上完成 focused、静态检查及 §8.9 预检；尚未运行
04 权威 runner 或真实数据，也不构成阶段取证。handoff 更新单独提交；不推送、不打 tag。

主题提交：实现 `9d13e9d3bd`，测试 `307b33ccec`，设计与 Contract `3eb02b691e`；后续修订
`3cb62ddaa1`、`a3500c26c0`、`db731e2299`、`4065dab7ba`、`407c72e034`、`a5489bc293`、
`60d91cea17`、`b584ef6b4e`、`57127c24c7`、`2ffdd0d22d`。`accb6e942a` 是早期 handoff 草稿，
最终候选以本 handoff 更新提交为准。

## 改动清单

- `vnext/repository_client/.../poll.py`、`client.py`：新增 bounded poll 入口；poll deadline 到期时，若已有成功的非终态观测则返回最后观测；没有成功观测或请求失败仍抛出原错误。
- `vnext/backend/.../application/submit_jobs.py`、`infrastructure/repository_write/http.py`：Submit 使用每次 60 秒 poll 和 3630 秒总等待上界；注入时钟、等待函数；匹配的 `QUEUED`/`RUNNING` 使用 checkpoint 和专用 healthy handoff；未知结果、传输错误和 identity/fingerprint mismatch 计入恢复会话。
- `vnext/backend/.../operations/`：仅 Submit 显式标记健康等待时把 Step 释放到立即可领取的 `RETRY_WAIT`，reclaim 保持 `attempt_count`；普通 safe handoff 沿用原行为。operator resume/retry 使用 `MANUAL_RECOVERY_REQUIRED → RETRY_WAIT`，由 worker claim 增加一次 attempt，并通过现有 diagnostic 字段保留授权会话。`R5.OPERATOR_RECOVERY_SESSION` 是唯一允许出现在 RUNNING Step 的 diagnostic。
- 测试更新位于 `test_operation_recovery_policy.py`、`test_operation_takeover.py`、`test_submit_job_effect.py`、`test_operation_state.py`、`test_submit_recovery.py` 与既有 Submit harness；`test_operator_recovery_http.py` 的现有 HTTP 200/409 断言保持 owner。替换了 `test_manual_recovery_retains_occupancy_and_excludes_claim` 中“命令后不可领取”断言，同时保留人工恢复期间不可领取断言。未新增按轮次命名的测试文件。
- 设计与 Contract 更新位于 P4 R5 §6–§8、P5-5B §5.4/§13.1、External Effect and Recovery Contract、Operation Lifecycle Contract，以及 P4 R5 S2c handoff 的 S1c 修订说明。

## 新旧规则与调用方盘点

| 调用路径 | 可取得的证据/行为 | S1c 规则 |
|---|---|---|
| Submit `await_import_result` 正常轮询 | checkpoint 已绑定原请求；Repository 响应身份与请求 fingerprint 匹配，状态明确为 `QUEUED`/`RUNNING` | 每次 60 秒到期复用 checkpoint 并 safe handoff；不增加 `attempt_count`；从 `started_at` 计算 3630 秒总上界 |
| Submit `await_import_result` transport/timeout/unknown response | 没有成功的匹配健康状态观测，外部结果未知 | 使用既有恢复策略和 3 个恢复会话预算；第 3 次进入人工恢复 |
| Submit identity、request fingerprint 或 operation ID 不匹配 | 观测不能证明是原 operation 的健康运行 | 按计数型 reconcile 失败处理，不进入健康等待分支 |
| Submit `submit_import` 与其他 Submit effect recovery | 可能有外部效果，但不是从健康 await poll 分支提交的明确健康证据 | `RECONCILE_PENDING` 仍走原恢复策略；不传 healthy-wait 标记 |
| Preview recovery | `PURE_RECOMPUTE`；恢复端返回已发布或人工恢复，不返回 Submit 健康等待证据 | 沿用原策略；不适用健康等待 |
| Worker takeover、crash、lease loss 与 startup recovery | 只有本地 lease/operation 状态，没有 Repository 明确健康响应 | 继续按原恢复会话预算处理；已耗尽时进入人工恢复。授权 operator 会话的 lease loss 回人工恢复 |
| Operator `RESUME_RECONCILE` / `RETRY_FROM_CHECKPOINT` | 命令本身只授权现有 `RETRY_WAIT`；尚无外部运行证据 | worker 下次 claim 恰好增加一次 `attempt_count`；其后失败按该会话规则处理 |

生产代码中唯一传入 `healthy_external_operation_wait=True` 的路径，是 Submit
`await_import_result` 在成功校验 Repository operation identity、request fingerprint 与
`QUEUED`/`RUNNING` 后调用 `acknowledge_safe_handoff`。通用 recovery policy、worker claim、
startup recovery 与其他调用方不具备这组健康证据，继续按原会话规则。至代码搜索结果，Submit
是生产 `RECONCILE_PENDING` recovery outcome 的调用方；Preview 恢复只返回 `PUBLISHED` 或
`MANUAL_RECOVERY`。本次没有把 policy 全局改为 count-free。

## 等待上界

`SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS = 3600.0 + 30.0`（当前 3630 秒），起点为 await Step 已有的
`started_at`。这与 Repository Service `Settings.import_timeout_seconds`（默认 3600 秒）加
`Settings.server_start_timeout_seconds`（默认 30 秒）耦合。到达上界后进入
`MANUAL_RECOVERY_REQUIRED`，diagnostic message 包含“超出等待上界”。单次 poll 保持 60 秒。

## 人工恢复后状态与会话

`RESUME_RECONCILE` 和 `RETRY_FROM_CHECKPOINT` 被接受后，Step 变为已有可领取状态 `RETRY_WAIT`，
设置为立即可领取；Operation 回到 `RUNNING`；命令不持有 worker lease，也不直接改
`attempt_count`。现有 Step diagnostic 暂存 `RECOVERY_AUTHORIZED`，worker claim 时将
`attempt_count` 增加一次并转为 `OPERATOR_RECOVERY_SESSION`。这是 RUNNING Step 唯一允许的
diagnostic，使计数型失败或 lease 丢失回到人工恢复。健康等待可重复 handoff，但通过 operator
专用 healthy marker 保留该 attempt 与授权会话。

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
| focused 测试（05，CT05 `gw-dms-test-05`） | 2026-10-30 12:26:37–12:27:06 UTC；六个既有测试文件，344 passed、1 warning，exit 0；日志 `/home/dev/gdds-p6-s1c-logs/2ffdd0d2-focused-05.log` |
| 五包 ruff/mypy（05） | 2026-10-30 12:27:18–12:27:19 UTC；`shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 均通过，exit 0；日志 `/home/dev/gdds-p6-s1c-logs/2ffdd0d2-static-05.log` |
| 05 预检 §8.9 并行主体 | 2026-10-30 12:27:29–12:28:40 UTC；backend 3076 passed、64 warnings；Repository Service 1741 passed、1 skipped；两包 exit 0。目标文件 focused 与 Compose 旅程另见下行；日志 `/home/dev/gdds-p6-s1c-logs/2ffdd0d2-preflight-batches-05.log` |
| 05 Compose 镜像构建与 Submit 旅程 | 2026-10-30 13:05:16–13:06:17 UTC 构建 backend/worker，exit 0；2026-10-30 13:07:53–13:08:18 UTC 运行 `test_compose_accept_upload_import_poll_t3_read_journey`，1 passed、exit 0。backend image `sha256:a8359eee89b233d16776ac96d5c7c2d5d567f9995b0b5a046ded28840875d544`，worker image `sha256:efda5ae6b289027c29654715e8743bfa51e8a3e9a9390e7d6cb56f7979a16a95`；日志分别为 `/home/dev/gdds-p6-s1c-logs/2ffdd0d2-compose-build-offlinecache2-05.log`、`/home/dev/gdds-p6-s1c-logs/2ffdd0d2-submit-compose-prebuilt-05.log` |
| 04 权威 runner | 待审核通过后按 manifest compare 决定逐包运行或沿用 |

以上运行均在 CT05，起止 HEAD 为 `2ffdd0d22dcaa82125f9f19661d8ff876b89acd3`，worktree clean。
Compose 旅程前确认无运行容器、Dolt 进程与 8000 端口占用；结束后再次确认均已清空。
Compose build 使用预先构建的候选 backend/worker 镜像，测试设置
`GATEWAY_COMPOSE_GATE_PREBUILT=1`；Repository Service 身份检查由 harness 正常执行。该预检不替代
04 权威 runner、carried 判定或 DC66 真实数据取证。

CT05 通过 LAN 从开发节点 `heavy-dev-01` (`192.168.233.180:3142`) 访问受限依赖代理；代理只接受
CT05 客户端并允许 PyPI 文件与 GitHub release 主机，不传递凭据。构建使用 CT05 本地 uv 与 Cargo
缓存，并临时组装 builder cache layer；未在开发节点运行测试或 Compose。候选构建成功后已恢复
CT05 的 `rust:1.97.0-bookworm` 原始 image ID，并移除临时 cache tags。首次未缓存构建曾因依赖下载
失败/超时；后续离线缓存构建与 Compose 预检通过。缓存类别、端点标识和日志均记录在本段及上述日志路径。

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

仍待执行：独立代码审核；审核通过后在 04 跑权威 runner；按 DC66 在 CT05 做 t1 冒烟，并在
`ct108-gw-dms` 从只读副本续跑 1030b 的 2× t4 v1-submit checkpoint；复核 Dolt 表哈希及 canonical
state。取证合并工具提交、runner 来源 V、真实数据结果与比较结果都尚未产生。

开发节点上的受限代理和 `pve-registry-http` BuildKit builder 均已停止；代理脚本、PID 标记及初次
构建诊断日志仍在 `/home/dev/gdds-p6-s1c-cache/`。CT05 临时 builder cache tags 已删除，
`rust:1.97.0-bookworm` 已恢复原 image ID；为 CT05 离线 builder 留下的 cache context 仍在
`/home/dev/gdds-p6-s1c-cache/rust-cache-base-context`（1.7G）和
`/home/dev/gdds-p6-s1c-cache/cargo-cache-base-context`（177M），没有运行中的测试服务或容器。
候选 Compose/预检日志在上表路径。1030b 保留卷和 v1-submit checkpoint 在 S1c exit 后由 owner
安排清理；本阶段不清理。
