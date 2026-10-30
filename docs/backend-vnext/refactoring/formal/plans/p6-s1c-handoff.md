# Phase 6 S1c handoff

## 状态

F1–F4 定向修订代码候选，等待同一审核会话复审。基线为已推送的 `main` / `43c1d4d513`；
审核报告为 `main:docs/backend-vnext/refactoring/formal/plans/p6-s1c-independent-review.md`。
工作分支为 `p6-s1c-impl`，代码候选 V=`3008d578cf2ee0eaf9236f01e33b5008d65ef36c`。
该候选包含合并 `main` 的提交 `5bc5a22605`。focused、五包静态检查、backend 与
repository_client 预检均通过；Compose 镜像预检因构建缓存缺少 uv bootstrap 制品未完成，详见验证与偏差。
验证运行在其父提交 `d95430ee486bb396cc954b51b95c1547818dbf9d`；V 仅额外修订了设计/Contract 中诊断码的
准确名称，没有改生产代码、测试或依赖。尚未运行 04 权威 runner 或真实数据。handoff 单独提交；不推送、不打 tag。

F1–F4 主题提交：backend 实现/测试 `34e348c0d1`，Repository client 实现/测试 `8f9da6b788`，
设计与 Contract `6a4a127c50`、诊断码文档澄清 `3008d578cf`；测试夹具修订 `b41206aa49`、
Repository client 测试导入修订 `d95430ee48`。历史 S1c 实现提交均为 V 的祖先，不在本轮改写。

## 改动清单

- `vnext/repository_client/.../poll.py`：poll 自身 deadline 到期且此前已有成功的非终态观测时，`RepositoryClientTimeoutError` 与跨过 deadline 的可重试退避都返回最后观测；传输/协议错误以及没有成功观测的 timeout 仍抛出。poll 截止时成功返回的终态保留并正常处理。
- `vnext/backend/.../application/submit_jobs.py`、`infrastructure/repository_write/http.py`：每次 claim 先观测原 Repository operation；poll deadline 为 `min(60s, max(剩余预算, 5s))`。匹配的终态不受总等待上界影响；只有匹配的 `QUEUED`/`RUNNING` 到达上界、或上界后的传输错误/未知结果，才进入等待上界人工恢复。上界前的崩溃/lease 丢失、传输错误和未知结果计入恢复会话；身份/fingerprint 不符立即人工恢复并保留 identity-mismatch 诊断。
- `submit_import` 的传输错误同样计入恢复会话；恢复重发使用原 import idempotency key，测试确认不会创建第二个 Repository operation。
- `vnext/backend/.../operations/`：仅 Submit 显式标记健康等待时把 Step 释放到立即可领取的 `RETRY_WAIT`，reclaim 保持 `attempt_count`；普通 safe handoff 沿用原行为。operator resume/retry 使用 `MANUAL_RECOVERY_REQUIRED → RETRY_WAIT`，由 worker claim 增加一次 attempt，并通过现有 diagnostic 字段保留授权会话。`R5.OPERATOR_RECOVERY_SESSION` 是唯一允许出现在 RUNNING Step 的 diagnostic。
- 测试更新位于 `test_operation_recovery_policy.py`、`test_operation_takeover.py`、`test_submit_job_effect.py`、`test_operation_state.py`、`test_submit_recovery.py` 与既有 Submit harness；`test_operator_recovery_http.py` 的现有 HTTP 200/409 断言保持 owner。替换了 `test_manual_recovery_retains_occupancy_and_excludes_claim` 中“命令后不可领取”断言，同时保留人工恢复期间不可领取断言。未新增按轮次命名的测试文件。
- 设计与 Contract 更新位于 P4 R5 §6–§8、P5-5B §5.4/§13.1、External Effect and Recovery Contract、Operation Lifecycle Contract，以及 P4 R5 S2c handoff 的 S1c 修订说明。

## 新旧规则与调用方盘点

| 调用路径 | 可取得的证据/行为 | S1c 规则 |
|---|---|---|
| Submit `await_import_result` 健康等待 | checkpoint 与 Repository operation identity、请求 fingerprint 匹配；HTTP 成功且状态为 `QUEUED`/`RUNNING` | 单次 60 秒 poll 到期后复用 checkpoint 并 safe handoff；不增加 `attempt_count`。总上界从既有 `started_at` 计算；每次 claim 都先观察一次 |
| `await_import_result` 返回匹配终态 | HTTP 成功且原 operation identity 匹配；状态为 `SUCCEEDED`/`FAILED` | 即使 poll 恰在或超过总等待上界，仍按 T3/稳定中止处理 |
| `await_import_result` 的传输错误、timeout 或未知结果 | 无匹配的健康运行证据；尚未超过总上界 | 计入三个恢复会话；第 3 次进入人工恢复 |
| 上界时仍 `QUEUED`/`RUNNING`，或上界后的传输错误/timeout/未知结果 | 观测证明仍在运行或结果仍未知，但继续等待预算已用尽 | `MANUAL_RECOVERY_REQUIRED`，诊断 `r5.wait_upper_bound_exceeded` |
| 本地 checkpoint/payload identity 或 fingerprint 不符，或 Repository operation identity 不符 | 确认的身份/证据矛盾，不是健康等待或可重试错误 | 立即 `MANUAL_RECOVERY_REQUIRED`，诊断 `r5.effect_identity_mismatch`，不消耗恢复会话 |
| Submit `submit_import` transport recovery | 原 import idempotency key 与已 checkpoint 的 request bytes 保持不变 | 传输错误计数；重新领取后以同一 key 重发，不产生第二个 Repository operation |
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
`Settings.server_start_timeout_seconds`（默认 30 秒）耦合。每次 claim 都先观测；poll deadline 为
`min(60s, max(剩余预算, 5s))`。只有匹配的 `QUEUED`/`RUNNING` 在上界处或之后，或上界后的传输错误/timeout/
未知结果，才以 `r5.wait_upper_bound_exceeded` 进入人工恢复并写明“超出等待上界”。匹配的 `SUCCEEDED`/
`FAILED` 始终按终态处理。

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

- External Effect and Recovery Contract 仅更新与终态优先、等待上界及 identity-mismatch 立即人工恢复冲突的条款；operation 四态、T1/T2/T3 与 unknown outcome 不 blind replay 不变。
- Operation Lifecycle Contract 补入 `RETRY_WAIT` 上 `R5.HEALTHY_WAIT_HANDOFF`、`R5.HEALTHY_WAIT_HANDOFF_OPERATOR`、`R5.RECOVERY_AUTHORIZED` 的含义与 claim 计数。
- 健康等待、上界、传输/未知计数、identity mismatch 诊断、submit_import 同 key 重放与 checkpoint 去重由 `test_submit_job_effect.py` 覆盖；poll cutoff 由 `repository_client/tests/test_operation_poll_client.py` 覆盖；既有 operator 状态、重启与 HTTP 200/409 owner 文件未变。

## 原始候选 `2ffdd0d22d` 验证记录（历史）

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

## F1–F4 定向修订验证（当前候选 V）

所有测试都在 CT05 的 clean、已提交 worktree（HEAD `d95430ee486bb396cc954b51b95c1547818dbf9d`）运行，
`TMPDIR=/home/dev/gdds-test-tmp`，使用现有 locked 环境与 `--no-sync`，没有设置代理。

| 验证 | 结果 |
|---|---|
| backend focused：原七个 owner 文件 | 355 passed、1 warning，exit 0；2026-10-30 14:06:16–14:06:51 UTC；日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-focused-backend-final-05.log` |
| repository_client focused：`test_operation_poll_client.py` | 23 passed，exit 0；14:00:48 UTC；日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-focused-repository-client-05.log` |
| 五包 ruff/mypy | `shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 全部通过，exit 0；14:00:59–14:01:01 UTC；日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-five-package-static-05.log` |
| backend §8.9 并行主体 | 3076 passed、64 warnings，exit 0；14:19:44–14:20:12 UTC；日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-preflight-backend-parallel-final-05.log` |
| repository_client §8.9 包预检 | 161 passed，exit 0；14:03:01–14:03:03 UTC；日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-preflight-repository-client-05.log` |
| F2 独立审核探针 | 0.02s 与 0.2s 延迟各 40 个窗口，80/80 正常返回，timeout 0，exit 0；14:07:05–14:09:43 UTC；完整逐窗口日志 `/home/dev/gdds-p6-s1c-logs/d95430ee-poll-deadline-edge-05.log`，原脚本 `/home/dev/gdds-p6-logs/s1c/review-claude/poll_deadline_edge.py` |
| backend Submit Compose 旅程 | 本轮未执行：需先构建含当前 `repository_client` 与 backend 源码的镜像；开发节点现有缓存缺少可用 uv bootstrap 层。没有在旧 V 镜像上冒充当前候选结果，未启动 Compose 栈。 |

本轮修订中，首轮 backend focused 暴露了固定 control clock 与重试 helper 的夹具冲突，已由 `b41206aa49` 修正；
Repository client focused 暴露测试漏导入 `RepositoryProtocolError`，已由 `d95430ee48` 修正。最终候选上的
focused 与 static 均通过。Repository client 全包预检最初误带 `-n auto`（该包未启用 xdist），随后改为单进程
运行并通过 161 项；失败命令日志在 `/home/dev/gdds-p6-s1c-logs/d95430ee-preflight-backend-repository-client-05.log`。

Compose 镜像预检只尝试缓存构建，没有使用代理、没有在开发节点运行测试或 Compose：CT201 的
`pve-registry-http` BuildKit metadata 访问未及时完成后被取消（日志
`/home/dev/gdds-p6-s1c-logs/d95430ee-compose-image-cache-build-ct201.log`）；CT201 默认 builder 复用到旧的
uv bootstrap 失败层，构建报 `uv: not found`（日志
`/home/dev/gdds-p6-s1c-logs/d95430ee-compose-image-cache-build-ct201-default.log`）；绕过旧层后用直接 host
网络重建，仍停在 uv 下载约 4 分钟，随后停止（日志
`/home/dev/gdds-p6-s1c-logs/d95430ee-compose-image-cache-build-ct201-nocache-hostnet.log`）。没有产出或传输
候选镜像。`pve-registry-http` builder 已恢复为 stopped；CT05 worktree clean，无运行中的容器、Dolt 进程或
8000 端口占用。当前代码与包级预检可供复审；Compose 预检的缓存缺口需在需要该项时补齐，不用代理绕过。

## 阶段取证计划（DC66 修订）

证据前提：本阶段不改 control DB schema、checkpoint payload 或 Repository Service；若最终候选不满足，
停止并改为 2× t4 整档运行。本 handoff 尚无权威 runner 与真实数据取证结果。

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

等待同一审核会话复审 F1–F4。复审通过前不运行 04 权威 runner 或真实数据；之后按 DC66 执行 CT05 t1
冒烟、ct108 从 1030b v1-submit checkpoint 副本续跑 2× t4 Submit、结果对照与证据复核。取证合并提交、
runner 来源 V、真实数据结果与比较结果尚未产生。

本轮没有启用代理。CT201 的 Compose 镜像构建因 uv bootstrap 制品不可用而停止，未生成候选镜像；
构建日志见上节。新启动的 `pve-registry-http` BuildKit builder 已停止，未创建容器栈或占用测试端口。
CT05 最终 worktree clean，Hypothesis 临时目录与 S1c bundle 临时文件已清理。1030b 保留卷和
v1-submit checkpoint 不动，在 S1c exit 后由 owner 安排清理。
