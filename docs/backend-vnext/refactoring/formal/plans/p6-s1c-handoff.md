# Phase 6 S1c handoff

## 状态

F1–F4 定向修订代码候选已通过复审（报告为本地 `main` 提交 `7d85b38d9b` 中的
`p6-s1c-independent-rereview-1.md`）。基线为已推送的 `main` / `43c1d4d513`；代码候选
V=`3008d578cf2ee0eaf9236f01e33b5008d65ef36c`，包含合并 `main` 的提交 `5bc5a22605`。
按 main `97a275359d` 修订的跨镜像 store 身份口径，04 六包权威 runner 已在 V 上通过；独立工具提交
T=`469a1549634d74dcf0e6c065998fa63c51ee7036` 的 focused/static 检查及 CT05 t1 冒烟也已通过。
CT108 2× t4 Submit 仍待基准续跑工具验证就绪；本 handoff 不包含该 Submit 的结果。handoff 单独提交；不推送、不打 tag。

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

## DC64 第 1 项 c 取证运行记录（2026-10-30）

### 04 权威 runner 首次尝试（历史；成功重跑见后文）

- 节点 `ct108-gw-dms-04`（hostname `gw-dms-test-04`）；worktree `/home/dev/gdds-p6-s1c-v-3008-04`，detached HEAD
  起止均为 V=`3008d578cf2ee0eaf9236f01e33b5008d65ef36c`，`legacy` 指向节点主 checkout；起止 worktree clean。
- 起止时间：`2026-10-30T14:44:31Z`–`2026-10-30T14:44:38Z`；命令 `./vnext/scripts/run-tests.sh`，未设置
  `GATEWAY_TEST_PACKAGES`，选取全部六包；runner exit code **1**。日志：
  `/home/dev/gdds-p6-logs/s1c/04-runner-3008d578cf.log`，SHA256
  `b45ccd7428fe1e44ae86f8924eeb9dd2e6c54c03625d7debaf551a4ce74ac8c2`。
- 失败发生在 backend 的 locked 环境同步：uv 在未设置 `UV_OFFLINE=1` 时刷新 canonical PyPI 索引，
  对 `https://pypi.org/simple/maturin/` 的请求因测试节点网络不可达失败。最初 runner 日志被误读为
  maturin 缓存缺失；owner 随后确认 04 本地缓存已有 maturin，并以离线环境同步成功，见下方 DC67 记录。
  原运行没有配置或使用代理，`GATEWAY_P2R1_CACHE_URL` 未设置。runner 未进入测试阶段，六包状态均标为 failed；
  没有生成包 manifest，没有运行 Compose，也没有构建 V 对应的 Repository Service 镜像。
- 失败时观察到的 `gateway-repository-service:local` 是旧缓存镜像，ID
  `sha256:b66c7fef0b8dd6c6b6d66e0463862e109f1d44cd8614e96fe93564bd8a2a4dd9`，label revision=`020deda2fd`；
  它不是 V 的镜像身份或本次门禁结果。
- runner 的有效环境：`LANG=C`、`LC_ALL=C.UTF-8`、`HOME=/root`、
  `PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、
  `umask=0022`、`TMPDIR=/home/dev/gdds-test-tmp`；`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT`、
  `GATEWAY_TEST_PACKAGES`、`GATEWAY_TEST_WORKERS`、`GATEWAY_DOCKER_BUILD_NETWORK`、`CARGO_HOME`、
  `RUSTUP_HOME`、`UV_OFFLINE`、`CARGO_NET_OFFLINE`、`GATEWAY_COMPOSE_GATE_PREBUILT`、
  `GATEWAY_COMPOSE_GATE_PROJECT_NAME` 与 HTTP/HTTPS/ALL proxy 变量均未设置。Docker server `29.9.1`，Compose `v5.6.0`；
  Rust toolchain `1.97.0`，uv `0.11.28`。
- 按 DC67 与 AGENTS 的 runner exit 规则停止后续验收；失败后 worktree 仍 clean，无运行容器、Dolt 进程或 8000
  端口监听。原“需预填充 maturin”的归因已由 owner 更正；下一次 runner 应设置 `UV_OFFLINE=1` 与
  `CARGO_NET_OFFLINE=true`，但须先满足 DC67 backend/worker image ID 预检。

### 05 t1 与后续取证（截至 16:32 的历史状态）

- 本轮未运行 t1：原 04 runner 非零退出后停止了该轮后续取证；DC67 镜像预检后续又因 image ID 不匹配而停止。
  05 在 16:32:57 UTC 的运行前清点显示无 benchmark/journey 进程、容器、Dolt 或 8000 端口监听，真实数据包目录
  存在；清点日志见 DC67 记录。尚未创建 V 的 05 worktree 或启动旅程。
- DC67 已更正 t1 要求：V 的 `real_dump_journey.py` 直接运行 t1 完整旅程即可，本项不保存 DC66 第 3 项的
  逐计时步骤 checkpoint；该 checkpoint/resume 要求只约束正式测量。本次因为 04 预检停止而未运行 t1。
  05 如需 backend/worker 镜像，应加载 DC67 第 1 项预构建镜像。基准工具就绪后，再按 DC66 第 4 项安排 2× t4 Submit。
- 截至本段记录时，本 handoff 尚无 t1、逐包 manifest、runner 记录中的 V 镜像身份或真实数据结果；这些项目后续
  取证见下文。也未启动 2× t4 Submit、取证合并提交或对照。

## 阶段取证计划（DC66 修订）

证据前提：本阶段不改 control DB schema、checkpoint payload 或 Repository Service；若最终候选不满足，
停止并改为 2× t4 整档运行。04 权威 runner 与 05 t1 已完成；CT108 2× t4 Submit 仍待基准续跑工具验证。

- 05：t1 完整旅程（冒烟）。
- `ct108-gw-dms`：不跑 t4 完整旅程；在该节点空闲并确认后，用 S1c 最终候选镜像，从
  `p6b2xwarmr5fix1030b` 的 v1-submit checkpoint 只读副本续跑 2× t4 Submit。
- 记录恢复会话数、健康让出次数、Repository 导入用时、Submit 用时，并与 1030b 保留卷只读副本的
  Dolt 表哈希及 canonical state 对照。
- 取证合并提交仅在节点上生成，包含 S1c 候选与基准工具提交；确认相对 S1c 候选仅改
  `vnext/backend/benchmarks`、相应测试与 docs，handoff 记录双亲和 `diff --stat`；不合入、不推送。
- 权威 runner 在 04；每包记录实际运行或沿用、来源 V 与来源日志、manifest 和镜像身份。
- 每条运行日志记录节点、HEAD、起止时间、exit code 与日志路径。正式测量的计时步骤 checkpoint 与失败续行
  按 DC66 规则记录；t1 冒烟不要求该 checkpoint/resume 能力。

## DC67 镜像预构建与 04 就绪预检（2026-10-30；按 main `604e28cb5b`）

### 开发节点预构建与传输

- 在开发节点 `heavy-dev-01` 的 clean detached worktree `/home/dev/gdds-p6-s1c-v-3008-dev`、HEAD
  `3008d578cf2ee0eaf9236f01e33b5008d65ef36c`，使用 V 的 `vnext/backend/Dockerfile` 和 `vnext` context，
  以 `--network=host` 构建；未在开发节点运行测试或 Compose。构建使用 project
  `s1c-v-3008`，产出 `s1c-v-3008-backend:latest` 与 `s1c-v-3008-worker:latest`（符合
  `compose_gate_harness` 的 `GATEWAY_COMPOSE_GATE_PREBUILT` 命名；后续 runner 需设置
  `GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-v-3008`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`）。
- 构建时间 `2026-10-30T15:50:07Z`–`2026-10-30T17:14:36Z`，build/save exit 0。构建日志
  `/home/dev/gdds-p6-logs/s1c/dev-build-backend-worker-v-3008-retry2.log`，SHA256
  `bcf4a83b5df3324daadc82e1133c2b1bf76f4d526fffe83f50ab346d62a520f1`。开发节点 inspect ID 为
  `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049`；两 tag 指向该 ID。
- `docker save` 文件 `/home/dev/gdds-p6-logs/s1c/backend-worker-s1c-v-3008.tar`，379 MB，SHA256
  `37e8b5afd2f04e37916d3fa80c71b5975c2245a48c59b0e41c089795c81091b8`。Cargo 本地缓存准备日志
  `dev-cargo-cache-seed.log`（SHA256 `40a82a39f36733597f8591d4d8a40ab26c85b0c31d2dd82a3df887898f4f0923`）
  与锁定依赖 fetch 日志 `dev-cargo-fetch-locked.log`（SHA256
  `7935b794954b84199b42c966a9b11741870cc298cf3c357f521da41d9e041a2c`）记录构建缓存准备；代理环境未设置。
- 文件经 LAN 于 `17:15:15Z`–`17:15:19Z` 传至 `ct108-gw-dms-04` 并 `docker load` 成功，远端 tar SHA256
  与源文件相同。传输/load 日志 `/home/dev/gdds-p6-logs/s1c/04-image-load-transfer.log`，SHA256
  `5253aee36d5e58ecf8cf2971933bb8f744c156073ea77d57f3408bf085135bc9`；04 镜像清点日志
  `/home/dev/gdds-p6-logs/s1c/04-image-load.log`，SHA256
  `1fa95d70b58221b4120824008ddaf569835a913e9e719dab2553c2199efecd44`。

### 04 初次就绪预检与停止原因（历史；身份口径已被 main `97a275359d` 修订）

- 节点 `ct108-gw-dms-04`（hostname `gw-dms-test-04`），V worktree clean，预检时无容器、Dolt 进程或 8000
  端口占用。backend/worker 两个 tag 均已加载，但 04 的 Docker inspect ID 均为
  `sha256:0c61307c7e64c7cf1dc6c55ad1b73ce74d161215ea946b4ad124c22d24cee478`，不等于开发节点 inspect ID
  `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049`。按当时记录的 DC67 inspect-ID
  条件，该项未通过并停止；没有启动 04 runner。main `97a275359d` 后续澄清，跨 Docker image store 应比较 archive
  config digest 与全部 RootFS DiffID，inspect ID 只作参考；后续成功预检与 runner 记录见“DC65/DC67 修订后的
  04 runner 与 CT05 t1 取证”。
- 追加对照显示两端 inspect 的 Created timestamp 相同，15 个 RootFS DiffID 完全相同；两端 `docker save`
  中的 config digest 均为 `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049`。
  layer-path aggregate SHA256 则不同（开发端 `606018379a45a3058f22bb02a1ffbed2161af812c63d30fc94bab72caf67a563`；
  04 端 `115d99995f9100f6d9b469de426d2ce8ae342509697cc0fff0f5764d297a0150`）。该历史对照曾触发停止；按后续 owner
  裁定，config digest 与完整 DiffID 已相同，满足跨 store 身份口径。开发端 Docker 为
  `26.1.5+dfsg1`/`overlay2`，04 为 `29.9.1`/containerd `overlayfs` snapshotter；仅记录为环境差异，不据此推定
  ID 差异原因。完整对照日志 `/home/dev/gdds-p6-logs/s1c/04-image-id-comparison.log`，SHA256
  `0d01c98ed7b0eedcc1a4691f77ea377430eee983833a412cc221235da36b84be`。
- Repository Service 镜像按 V 的 build-input revision、source-tree SHA256 与 uv lock SHA256 核验：V 的
  revision=`4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree SHA256=`sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`、
  uv lock SHA256=`6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`；当前
  `gateway-repository-service:local` 的标签满足 V 身份，不需重建。`gateway-repository-client-e2e:local` 的 client
  uv lock label=`6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` 与 V 一致，不需重建。两者使用的依赖基础镜像也已存在：Repository Service
  `gateway-p2r1-repository:lock-6dc9659f0aee`，client e2e `gateway-repository-client-e2e-base:local`。故本次无需
  触发预置依赖模式离线重建，也未删除 client e2e 镜像。
- Owner 对先前 runner 失败的更正证据：04 上 `UV_OFFLINE=1 CARGO_NET_OFFLINE=true` 的 backend locked sync 与
  Rust 扩展离线构建成功，日志 `/home/dev/gdds-p6-logs/s1c/owner-04-offline-sync-probe.log`，SHA256
  `da15ba9e151034246fe4f0346aef209b653e55802fcb20f3e09565c4d241f580`。故此前“04 缺少 maturin 缓存”的判断
  已撤回；下一次 runner 环境还须启用 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，以及 prebuilt 和所需 project
  开关，并按新运行记录实际环境。

### 05 t1 状态（截至 16:32 的历史清点）

- `ct108-gw-dms-05` 在 `2026-10-30T16:32:57Z` 清点时 hostname=`gw-dms-test-05`，原 worktree
  `/home/dev/gdds-p6-s1c-05` clean 但 HEAD 为 `d95430ee486bb396cc954b51b95c1547818dbf9d`，不等于 V；无容器、Dolt、
  journey/benchmark/pytest/runner 进程，8000 端口空闲。清点日志
  `/home/dev/gdds-p6-logs/s1c/05-pre-t1-inventory.log`，SHA256
  `b0b548e7e4d0f047261834d29efed9d17e3fc1768d1747b9c114dcf83bcd7f4c`。
- 截至本清点时，没有在 05 创建 V worktree、加载镜像或运行 t1。DC67 更正要求为：后续直接使用 V 自带
  `real_dump_journey.py` 执行 t1，不保存逐步骤 checkpoint；如构建 backend/worker 则加载上述预构建 tar。
  由于 04 预检停止，本轮没有继续执行 05 项。

上述停止点已由 main `97a275359d` 的身份口径修订及后续取证取代。1030b 保留卷与 v1-submit checkpoint 未改动；
本轮仍未启动 CT108 2× t4 Submit，也未创建取证合并提交。

## DC65/DC67 修订后的 04 runner 与 CT05 t1 取证（2026-10-30）

### 04 六包权威 runner

- 节点 `ct108-gw-dms-04`，hostname `gw-dms-test-04`；clean detached worktree
  `/home/dev/gdds-p6-s1c-v-3008-04`，起止 HEAD 均为 V=`3008d578cf2ee0eaf9236f01e33b5008d65ef36c`，
  `legacy` 链接正确，起止 worktree clean。命令 `./vnext/scripts/run-tests.sh`，未设置
  `GATEWAY_TEST_PACKAGES`，六包全部运行；开始 `2026-10-30T23:31:53Z`，结束
  `2026-10-30T23:53:01Z`，exit 0。
- 环境：`LANG=C`、`LC_ALL=C.UTF-8`、`HOME=/root`、
  `PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、
  `umask=0022`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、
  `GATEWAY_COMPOSE_GATE_PREBUILT=1`、`GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-v-3008`、
  `TMPDIR=/home/dev/gdds-test-tmp`；`GATEWAY_TEST_PACKAGES` 与 `GATEWAY_TEST_WORKERS` 未设置；HTTP/HTTPS/ALL proxy
  均未设置。Docker client/server `29.9.1`，Compose `v5.6.0`，默认 context；构建网络未设置。
- 六包状态均通过：`rust`（fmt、clippy、test）、`shared_kernel`、`repository_contracts`、
  `repository_client`、`backend`、`repository_service`。backend 并行批次 3076 passed、serial 批次 51 passed；
  Repository Service 并行批次 1741 passed / 1 skipped、serial 批次 207 passed；runner 逐包结果均为 passed。
- 逐包 manifest 总摘要（HEAD 均为 V）：

  | 包 | total digest |
  |---|---|
  | rust | `143a9a6947aea4e69e3ad40356c3ca80d93b780c15ed6245e0da231a1f707e52` |
  | shared_kernel | `8464690c5acf4019f0d7647980144e822a5fa618a0143851d6260a0965908495` |
  | repository_contracts | `d4ac19be947da5516f22197e5fb16e58e9df8f3f2e8638e17aaf220cd292d7d2` |
  | repository_client | `e67670ce6a875658e82a570bd64993da0680ab2e48a0d60d1c48b0c95b8323e0` |
  | backend | `ec613d8f9fb6b6733a628d666cf0e3c768a2d0568517219fadff2188058bfa0c` |
  | repository_service | `12fe3bcad32a83e7a0e34f866e055c01592164009da8f063210bb096d55b8ba2` |

- backend manifest 的预构建镜像清单包含 `s1c-v-3008-backend:latest` 与
  `s1c-v-3008-worker:latest`，04 inspect ID 均为
  `sha256:0c61307c7e64c7cf1dc6c55ad1b73ce74d161215ea946b4ad124c22d24cee478`。按 main `97a275359d` 的身份口径，
  开发节点归档 config digest `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049` 与
  04 归档相同，全部 15 个 RootFS DiffID 也逐项相同；完整逐项记录见
  `/home/dev/gdds-p6-logs/s1c/04-image-id-comparison.log`，SHA256
  `0d01c98ed7b0eedcc1a4691f77ea377430eee983833a412cc221235da36b84be`。inspect ID 仅供参考，不参与跨 store 身份判定。
- runner 前 Repository Service 预检沿用匹配 V 的 `gateway-repository-service:local`：build-input revision
  `4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree
  `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`、uv lock
  `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11`；没有触发 Repository Service 或 client e2e
  重建。预检身份和依赖镜像见上文 `04-image-load.log`。权威 runner 日志为
  `/home/dev/gdds-p6-logs/s1c/04-runner-3008d578cf-dc67-offline.log`，SHA256
  `a2603a688daca9714006ab228ae2bcb17425be88c2ce34f00cca150e42633e0d`。

### CT05 t1 冒烟

- 工具提交 T=`469a1549634d74dcf0e6c065998fa63c51ee7036`，在 V 上独立提交，不并入 S1c 代码候选。提交主题依次为
  `f08a07dd00`、`4f082783ab`、`469a154963`；`V..T` 只改
  `vnext/backend/benchmarks/real_dump_journey.py` 与 `vnext/backend/tests/test_real_dump_journey.py`，diff stat 为
  339 insertions、6 deletions。T 在调用方启用 prebuilt 时不构建 backend/worker、核对 project tags，并在旅程结果中
  记录本机 image ID 与 config digest；未设置时保留原构建行为。
- 05 focused `tests/test_real_dump_journey.py`：65 passed；五包 `ruff check .` 与 `mypy` 全通过。hostname
  `gw-dms-test-05`，HEAD T，验证日志 `/home/dev/gdds-p6-logs/s1c/05-t1-tool-validation-469a154963.log`，SHA256
  `317c75b4a2774a7f30fed8be6e9135b9b7bf215a5cb38dad1d2a67f946b1c56d`。
- 05 从开发节点 tar 加载镜像成功，归档 SHA256 为
  `37e8b5afd2f04e37916d3fa80c71b5975c2245a48c59b0e41c089795c81091b8`；按 config digest 与全部 DiffID 核验通过，
  config digest 为 `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049`。身份日志
  `/home/dev/gdds-p6-logs/s1c/05-image-identity-check.log` SHA256
  `5fe4daf1464de15a2aae98c798aae9497032bb00baf6acbf304d06b7b8ce4afe`；传输/load 日志
  `/home/dev/gdds-p6-logs/s1c/05-image-load-transfer.log` SHA256
  `065b42274d8004f99541ee96859aed707b95fe970a18d56da98103f37b2eadf3`。
- 05 在 T 的 clean worktree 运行完整 t1，使用 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、
  `GATEWAY_COMPOSE_GATE_PREBUILT=1`、project `s1c-v-3008`，无代理；不保存逐步骤 checkpoint。起止时间
  `2026-10-30T23:39:25Z`–`23:43:20Z`，起止 HEAD 均为 T，exit 0，18 个 step checks 全部通过。
  旅程日志 `/home/dev/gdds-p6-logs/s1c/05-t1-real-data-f08a07dd00.log`，SHA256
  `49c11f9006b26b092e75e702c1de5478a82cea28293f700c678b2ca9c55691c5`。无 CT05 容器或 Dolt 残留。

### CT108 2× t4 Submit 状态

- 尚未运行，也未在 CT108 加载 V 的 backend/worker tar。1030b 原卷与 v1-submit checkpoint 保持只读且未改动。
- 基准会话在 `p6-baseline` 的独立候选 `a039d9b2c1f5c40daf71a328353fba11e5264689` 已提交预构建镜像工具修正，但 05
  focused 命令在 uv locked sync 时因 maturin 构建没有解析到 root SSH 环境的 Rust toolchain，尝试公网访问后 exit 1；
  按 DC67 停止，没有继续 pytest 或五包静态检查，也没有将该工具视为就绪。失败日志
  `/home/dev/gdds-p6-logs/baseline/05-prebuilt-image-tool-a039d9b2.log`，SHA256
  `7193082fcf80f71a50bdc10f3832b36cf53820e2e2183c10d82447df318a9197`。基准会话需先按节点 Rust toolchain 约束处理并
  完成该工具验证，之后再安排 CT108 Submit。

## 偏差与清理

F1–F4 复审已通过。04 的首次 uv 索引失败与初次 inspect-ID 身份停止均由后续 owner 澄清和 main `97a275359d`
修订取代；六包 runner 已通过，CT05 的 T 与 t1 也已通过。开发节点镜像构建、LAN 传输和 CT05 旅程均未使用代理。
CT108 2× t4 Submit、取证合并提交及 1030b 对照尚未执行；独立 `p6-baseline` 工具候选的 focused 环境失败后按 DC67
停止，五包静态检查尚未运行。1030b 保留卷与 v1-submit checkpoint 未改动；S1c exit 后由 owner 安排清理。

## DC69 mutation planner 修复代码候选

- 原候选 `V=3008d578cf2ee0eaf9236f01e33b5008d65ef36c`；新代码候选
  `V'=ebd1b60a3f7ad962bf1348d166a7ff18969d06c0`，位于 `p6-s1c-impl`，未推送、未打 tag，未改写已有提交。
  主题提交：`19727b1502e3b8e3a0bbda6b89da94c68e01638d`（patch mutation 分相排序与 PURE_RECOMPUTE 异常日志）、
  `ebd1b60a3f7ad962bf1348d166a7ff18969d06c0`（固定新 change-set/closure digest）。
- `V..V'` 代码差异为 4 个文件、142 insertions、12 deletions：
  `vnext/backend/src/gateway_backend/capabilities/mutation_planning/_changeset.py`、
  `vnext/backend/src/gateway_backend/operations/recovery.py`、
  `vnext/backend/tests/test_mutation_planning.py`、
  `vnext/backend/tests/test_operation_recovery_policy.py`。根因是 patch planner 按主键混排 UPDATE 与 DELETE，
  违反 change-set 的 DELETE → UPDATE → INSERT 顺序契约；`_patch_mutations` 现分别收集三组并保留组内主键顺序，
  `_rebuild_mutations` 未改。更新后的业务行为测试固定 change-set digest
  `sha256:c12e643cae74a0603d2e30f4fe97ff19f8573a56f98ac67e37b123401b04974d` 与 closure digest
  `sha256:d1525a4822ff2d9215b21044aa1c87befd2d655682871349e2a0f6e50e4ca2bc`，没有兼容路径。
- `test_patch_mutation_closure_orders_mixed_row_changes_by_operation_phase` 是 mutation ordering 的唯一权威测试，
  经 `build_change_set_closure` 覆盖低主键 UPDATE、高主键 DELETE 与 INSERT，断言 closure ordering validation、
  各操作的 row image / row digest、组间与组内次序，以及渲染 DML 顺序。没有增加第二个同义测试或 Hypothesis 属性测试。
- PURE_RECOMPUTE handler 未预期异常现在用 worker logger 记录 traceback；异常仍映射为既有的
  `OPERATION.PURE_RECOMPUTE_FAILED` bounded diagnostic，不把异常正文放入 diagnostic/API。权威行为测试
  `test_unexpected_pure_recompute_handler_exception_is_logged_without_exiting_worker` 验证日志有 traceback，
  而 diagnostic 不含内部异常正文。

### CT05 focused、静态检查与最小复现

- 节点 `ct108-gw-dms-05`，hostname `gw-dms-test-05`；clean detached worktree
  `/home/dev/gdds-p6-s1c-dc69-05`，HEAD 起止均为 V'。focused 测试于
  `2026-10-31T13:40:18Z`–`13:40:24Z` 运行，167 passed，exit 0；覆盖 mutation planning、import replay/publication、
  submit job prepare 与 operation recovery policy。日志
  `/home/dev/gdds-p6-s1c-logs/dc69-focused-05.log`，SHA256
  `c7b9436f040ac0ab14ef9d38496be6372cf922921badd8ab608d0da28d2db632`。
- 同一 worktree 的五包 `ruff check .` 与 `mypy` 全通过：`shared_kernel`、`repository_contracts`、
  `repository_client`、`backend`、`repository_service`。运行于 `2026-10-31T13:40:36Z`–`13:41:01Z`，exit 0。
  日志 `/home/dev/gdds-p6-s1c-logs/dc69-static-five-packages-05.log`，SHA256
  `31e08b4810beadacc7b50746d2295ae5b703fa24c861510c8ef4e92010f7e5ab`。
- 修复后的最小复现脚本在 CT05 通过，结果为
  `DELETE(399), UPDATE(0,1), INSERT(400)`，change-set digest 与权威测试一致，渲染 DML 顺序为
  DELETE → UPDATE → INSERT。脚本 `/home/dev/gdds-p6-s1c-logs/dc69-fixed-minimal-repro.py`，SHA256
  `28fc5cf0eb03cb824609cde400c7273991cc56474455163b06bb3a4349775a2b`；运行日志
  `/home/dev/gdds-p6-s1c-logs/dc69-fixed-minimal-repro-05.log`，SHA256
  `5619028376c968ac824ec96d18f87260fede0fd99e383ab16bef8ff34804a24b`。
- backend 环境在 CT05 以 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp` 和
  仓库 Rust toolchain PATH 同步成功；预检显示 Rust/Cargo 1.97.0，活动工具链由
  `vnext/rust/rust-toolchain.toml` 覆盖。成功同步日志
  `/home/dev/gdds-p6-s1c-logs/dc69-backend-sync-05-retry.log`，SHA256
  `880a02b12b8581b70866fa3eb3b94af472e2b21c0c4ada1cfdba0e8a169c7b6a`；工具链日志
  `/home/dev/gdds-p6-s1c-logs/dc69-rust-toolchain-precheck-05.log`，SHA256
  `6e5407bdfe5df84056926d430177fd4e22eee71ccc6f5a4a264b5499f2109719`。初次环境同步因命令 PATH 未含 Rust 工具链
  而退出，未运行测试；按 DC68 修正 PATH 后以离线模式重试通过。初次同步日志保留于
  `/home/dev/gdds-p6-s1c-logs/dc69-backend-sync-05.log`，SHA256
  `005ad6e19ffba4cd77e62f951fd7238f74e3901910f4a5456d5ffd452032e360`。
- focused 日志中附带的 Rust 版本探测在 worktree 根目录触发了 rustup “no default toolchain” 提示；该探测不属于
  pytest 命令，正式版本预检已在 `vnext/rust` 执行并记录于上述工具链日志。focused 测试、静态检查与最小复现
  均在离线环境运行，未使用代理。worktree 外的任务 Cargo target（448 MiB）已按约定清理。

### 复审与后续取证

- 本候选等待同一审核会话针对性复审。复审通过前不启动 04 六包 runner、05 t1 或 CT108 真实旅程。
- 复审通过后按 DC69 构建 V' backend/worker 镜像并以 config digest 与完整 RootFS DiffID 核验后传至 04、05、
  CT108；04 运行六包权威 runner，05 用 V' 与已复核基准工具取证合并提交运行 t1，CT108 用对应取证合并提交
  运行一次 2× t4 三节点完整旅程（冷 History、`--three-node-history`、新 project、保留卷及既定 checkpoint）。
  随后只读核对 v1 Submit 对 1030b 的 Dolt 表哈希与 canonical state，以及 v3 与同轮 v1 的表哈希。
- `fb534`、`20e634` 两次既有运行的卷与日志及 1030b 保留卷均未修改，仍须保留至 S1c exit 合入后。

## DC69 取证尝试：04 runner 环境错误后停止

- 同一审核会话在 main `0f5e4f02c9` 的 `p6-s1c-dc69-rereview.md` 判定 V' / H 通过，授权开始 DC69 第 2 项。代码候选 V'=`ebd1b60a3f7ad962bf1348d166a7ff18969d06c0`、handoff H=`0d032ff13b4d6481671e7abb7c86bd05a713a309` 均未改写或推送。
- 开发节点 `heavy-dev-01` 从 V' 的 clean detached worktree `/home/dev/gdds-p6-s1c-dc69-vprime` 构建 backend 镜像，仅执行 `docker build`，未运行测试或 Compose。project/tag 前缀为 `s1c-vprime-ebd1`；backend 与 worker tag 指向相同镜像。构建于 `2026-10-31T14:18:36Z`–`14:18:41Z`，exit 0。构建日志 `/home/dev/gdds-p6-logs/s1c/dev-build-backend-worker-vprime-ebd1.log` SHA256 `da9e200552b70a04649e8cd042fb223d869923adacd9363b9ca580b172e4dcbd`。
- 归档 `/home/dev/gdds-p6-logs/s1c/backend-worker-s1c-vprime-ebd1.tar`，SHA256 `5c691d1d86a564bd35d3c3d953576b63ac13833609e35677f597c64891df61ae`。从归档 `manifest.json` 的 Config 得到 config digest `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1`；全部 15 个 RootFS DiffID 在开发节点与 04、05、ct108 加载后逐项一致。inspect ID 只作参考，未用于跨节点身份判定。传输日志 `/home/dev/gdds-p6-logs/s1c/dev-transfer-vprime-ebd1.log` SHA256 `12d4b01ea7414cd5de3176c62cd8ee67c48ace515d07a2f51126bd6dd4da3686`；三节点逐项身份日志均为 `/home/dev/gdds-p6-logs/s1c/image-load-identity-vprime-ebd1.log`，04 SHA256 `57d9ef533db97f4db4a128916cf5cfa16e56750e1ffe86b9a8ec97e01ecc063f`，05 `3bd8a13d168c4745b16874c1cd698c1b01a1852a46230cb5d4496313eefd2214`，ct108 `f33912d708d8b096c0b103e9d46d44a3665ead06b8d37e2263cf9a77505fc9cc`。bundle SHA256 `8ea782152d12d929d7994fc187af81c9f0dc14f4a3585045355ded76ef63ccbd`。
- 04 `gateway-repository-service:local` 原 build-input label `861ab246...`，不匹配 V'。使用已预置的 `gateway-p2r1-repository:lock-6dc9659f0aee`（image ID `sha256:63b7e79899d4379f24a1d58f0e22e1960847733a76e684dd170b8e631e00367f`、lock label 与当前 RS lock 匹配），在 V' worktree 以 `GATEWAY_DOCKER_BUILD_NETWORK=none` 离线重建成功；新 label 为 build-input `4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，image ID `sha256:adb2aa7eb04578c5289c876f179042264ab4433b9527d60bf1f99f54347140c0`。日志 `/home/dev/gdds-p6-logs/s1c/04-rs-offline-preflight-vprime-ebd1.log` SHA256 `15cc5319b6ab6ccf5f77a06d0ee48015a6f111dd3cd8a66188773f7dae771648`。
- 04 client e2e tag 的 candidate label 也旧于 V'；用 lock 匹配的预置 `gateway-repository-client-e2e-base:local`（ID `sha256:ba6c64db44f5f5b7f573fb1df6295c11a5c9e20d9c188189921e717a623ff38c`）和 `GATEWAY_DOCKER_BUILD_NETWORK=none` 重建成功。client lock SHA256 `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954`，新 candidate label 为 V'。旧 image ID `sha256:c8c3984339bc187ef6ef5d5f424c645b5bbd0cb689704a62921ef51e3408b68a`，新 ID `sha256:928599451874c0bd2ca3ad9fa86a84f9026e3fd54331ff13921ea0b1ddd3de5e`。日志 `/home/dev/gdds-p6-logs/s1c/04-client-e2e-offline-prebuild-vprime-ebd1.log` SHA256 `4684544b17d2252103bd7948201e480d2d6d24179af90a21f84513c22611a028`。

### 04 六包 runner

- 节点 `ct108-gw-dms-04` / `gw-dms-test-04`，clean detached worktree `/home/dev/gdds-p6-s1c-dc69-vprime-04`，legacy 链接存在，起止 HEAD 均为 V'。`2026-10-31T14:26:20Z` 开始，`14:47:05Z` 结束，runner exit 1。未设置 `GATEWAY_TEST_PACKAGES`，六包均选中；`rust`、`shared_kernel`、`repository_contracts`、`repository_client`、`backend` 通过。逐包 manifest total digest：

  | 包 | total digest | 结果 |
  |---|---|---|
  | rust | `143a9a6947aea4e69e3ad40356c3ca80d93b780c15ed6245e0da231a1f707e52` | passed |
  | shared_kernel | `b02c08098dce1ad76841dede8a6e7dcdf97871970b90703692fc0bc1d433a0af` | 243 passed |
  | repository_contracts | `fa2e010bbc4c48f7580c21aeca7291458b40c4cb962e5d291dd5b8ce716db7fe` | 152 passed |
  | repository_client | `cbe107032d58cf33d6a378252701434238600a4f58c9e78a726bd192c836b1b0` | 161 passed |
  | backend | `3adc20d57f7cbd830e8dd869c3c5ff326a5c2ca1433cbbbfa25d397b5f66c9ea` | 3077 parallel + 51 serial passed |
  | repository_service | `23a6fcf824592415742043174748fcf49ec7dbb441b34f002e48b5fbba5fdd9a` | 1740 passed, 1 skipped, 1 failed parallel; 207 serial passed |

- 唯一失败为 `repository_service/tests/test_build_repository_service_image_script.py::test_build_script_defaults_docker_build_network_to_host`：runner 环境显式设置 `GATEWAY_DOCKER_BUILD_NETWORK=none`，测试验证变量未设置时脚本默认值为 `host`，实际读到 `none`。这是本次执行者传入的环境参数错误，不是产品或缓存缺陷；重跑候选环境应从 runner 环境中移除该变量。`none` 仅用于先前 RS 与 client 镜像预构建，不需保留在权威 runner 环境。
- 该失败发生在 runner 已启动并执行测试之后，不满足 DC68 §1“被测对象尚未运行”的自动重做条件；当时先停止后，owner 明确授权在移除错误继承的变量后重跑。首次运行不计作通过，授权后的重跑与通过结果见下节。
- runner 环境：`HOME=/root`、`LANG=C`、`LC_ALL=C.UTF-8`、`PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、umask `022`、`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`、project `s1c-vprime-ebd1`、预置 RS/client dependency-base 已选择、所有 proxy 变量 unset。唯一错误设置是把 `GATEWAY_DOCKER_BUILD_NETWORK=none` 继承进 runner。
- runner 日志 `/home/dev/gdds-p6-logs/s1c/04-runner-vprime-ebd1.log` SHA256 `0012957eb26d9b4dc60a0d1b7fb3747b7dc01c66ac1b52e7194c491f87f779be`。postflight `/home/dev/gdds-p6-logs/s1c/04-runner-postflight-vprime-ebd1.log` SHA256 `38f742eb6a457a90599bc194dc6712595549a6c2b9b57016a0f6ea08bd6981d9`：worktree clean，运行/全部容器为空，8000 无监听，无 Dolt、pytest、uv 进程，本轮命名卷为空。两份 04 postflight（本次首次停止与授权重跑后）均存于开发节点 `/home/dev/gdds-p6-logs/s1c/`。V' backend/worker、RS 与 client e2e 镜像仍已加载；05 与 ct108 未启动旅程，fb534、20e634 既有运行卷及日志、1030b 保留卷与 checkpoint 均未写入。

## DC69 最终取证：V' runner、t1 与三节点 2× t4

- 依据 owner 对 04 runner 环境错误的授权，移除权威 runner 环境中的 `GATEWAY_DOCKER_BUILD_NETWORK=none` 后重跑；该变量只用于 RS/client 镜像的离线预构建。重跑使用同一 clean V' worktree 与预检镜像，不改代码或镜像。初次失败日志保留于上述 `04-runner-vprime-ebd1.log`（SHA256 `0012957e…`）；成功重跑日志 `/home/dev/gdds-p6-logs/s1c/04-runner-vprime-ebd1-retry.log`，SHA256 `a77654a1fcd355bb6d6c5862b6576e90cb0f8116499fac75eb3569f095013745`。成功重跑的 postflight `/home/dev/gdds-p6-logs/s1c/04-runner-postflight-vprime-ebd1-retry.log`，SHA256 `342bc423da4614abc4873a767619c534d131f707d23c0a917b695394c1d96340`。
- **04 六包权威 runner 通过。** 节点 `ct108-gw-dms-04`（hostname `gw-dms-test-04`），clean worktree `/home/dev/gdds-p6-s1c-dc69-vprime-04`，legacy 链接存在，起止 HEAD 均为 V'=`ebd1b60a3f7ad962bf1348d166a7ff18969d06c0`。运行时间 `2026-10-31T14:50:44Z`–`15:11:16Z`，exit 0；未设置 `GATEWAY_TEST_PACKAGES`。环境为 `HOME=/root`、`LANG=C`、`LC_ALL=C.UTF-8`、`PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、umask `022`、`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`、`GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-vprime-ebd1`；所有 proxy 变量 unset，`GATEWAY_DOCKER_BUILD_NETWORK` unset，RS/client dependency-base 使用节点预置镜像。该 runner 作为后续阶段的来源 V。
- 逐包 manifest total digest 与结果：

  | 包 | manifest total digest | 结果 |
  |---|---|---|
  | rust | `143a9a6947aea4e69e3ad40356c3ca80d93b780c15ed6245e0da231a1f707e52` | passed |
  | shared_kernel | `b02c08098dce1ad76841dede8a6e7dcdf97871970b90703692fc0bc1d433a0af` | 243 passed |
  | repository_contracts | `fa2e010bbc4c48f7580c21aeca7291458b40c4cb962e5d291dd5b8ce716db7fe` | 152 passed |
  | repository_client | `cbe107032d58cf33d6a378252701434238600a4f58c9e78a726bd192c836b1b0` | 161 passed |
  | backend | `ba44ff016cebc706061d0a0536944be1e39681cd212e7e7170679b1c39d8e957` | 3077 parallel + 51 serial passed |
  | repository_service | `f780902707c9f33dca914388d57b55a5686f760e92d7d9a444cfeae9b4452511` | 1741 passed, 1 skipped, 207 serial passed |

- runner 中 backend/worker 使用 V' 预构建镜像；RS 镜像 build-input label 为 `4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`、image ID `sha256:adb2aa7eb04578c5289c876f179042264ab4433b9527d60bf1f99f54347140c0`；client e2e 镜像为 V' label，image ID `sha256:928599451874c0bd2ca3ad9fa86a84f9026e3fd54331ff13921ea0b1ddd3de5e`。backend/worker 传输身份以 config digest `sha256:6d0aab7e18caea0b157c401612cfd7acdb0fca1bbfd6ef7f2b57b7d5f3f588f1` 和 15 个 RootFS DiffID 判定：`66462cc862fe2053b9863fefa3866e07bb5dfb06f6b3ce3177cc096e4021aabe`、`97c8a655c2dfbb1952cd052cbe11b7e6e00af00f160154b47b0bad29e019b067`、`3fda3219c8f4a902e577efcdb924b514318c606d47ba4b53640511b27925da18`、`594ec838d0ae6e04f1fecf3283c6d40f24e0a03b5741d12090cbca47bf416cb5`、`8880dd60d255127aa44f563b0bbf88906620da53d2b63654a6a79a3c9a2b1ff3`、`aff9d7b41f398d228f79c2d5e9954e2267fe16dfccf2660b8b100ecbd30d56fa`、`aed1d7e6bff3d2c7d5ceffa62ba57d46eb17e66ea10745e9fb9cd33c8e07586d`、`684afe35f84526b1badf36f634d62d69572d09f120c1de23c0cb2cd830918b00`、`7cae7c4570212aafc62c5a2d1f1f58068b483cbcf74ada3526bd0e755db3427b`、`35093ccd429573f948e87605900c7b99fb5868cbe5543d4d8aa331dbf73e4dc3`、`de5af2e4a7d4cb9bb6922a68dd3287c0171410c377ded785dfd6114191f6b7a6`、`3905bdd7db5ccbdbd7fe8147c056352930a3e212928d31fc4db9e0b8d38ef463`、`fa257d96ca6b2e8ba5ed3f624b83b1d9e5584c4ec345afbced2c2dafbdfc7911`、`98ee0d1e3862b0f9f16125dc0bc881e2c988c78cb191edf16a7fc2dd8a4b4d78`、`408c4b69cbb93b6dfea07b38e34390c8e974c5e8dc9b603b179521b52c4df0ce`；开发节点、04、05、ct108 逐项一致。归档 SHA256 `5c691d1d86a564bd35d3c3d953576b63ac13833609e35677f597c64891df61ae`，构建日志 SHA256 `da9e200552b70a04649e8cd042fb223d869923adacd9363b9ca580b172e4dcbd`；身份日志 04/05/ct108 SHA256 分别为 `57d9ef533db97f4db4a128916cf5cfa16e56750e1ffe86b9a8ec97e01ecc063f`、`3bd8a13d168c4745b16874c1cd698c1b01a1852a46230cb5d4496313eefd2214`、`f33912d708d8b096c0b103e9d46d44a3665ead06b8d37e2263cf9a77505fc9cc`。inspect ID 仅供本机参考。

### 05 t1 冒烟

- 节点 `ct108-gw-dms-05`（hostname `gw-dms-test-05`），clean worktree HEAD 为取证合并提交 `b96fe8e4cc10a1869ed30f9fec4afb302cce8152`（父提交 V' 与工具提交 `fb534592452e604bac87c7b3dd357db7fc0ef267`）。使用 project `s1c-vprime-ebd1`、预构建镜像和离线环境运行完整 t1；运行时间 `2026-10-31T15:22:19Z` 至最终 history 步骤成功 `15:26:14.077Z`。状态文件中各旅程步骤均成功，结果 PASS。日志 `/home/dev/gdds-p6-logs/s1c/05-t1-vprime-b96fe8e4cc-final.log` SHA256 `67b01d5970770a74b77dd77683df8d51ba5baa6e885ddaf58a968936c9a6f4e1`；状态 `/home/dev/gateway-real-dumps/runs/s1c-vprime-ebd1/t1.state.json` SHA256 `2c06de99d53a75d7702c29362952e9cf5a912959430fd61b97ac35d56b5d7f52`。
- 工具 wrapper 未将结束时间与 exit code 写入日志；状态文件也无 exit_code 字段。因此记录旅程明确 PASS，但不声称有已留存的外层 exit code。清理日志 `/home/dev/gdds-p6-logs/s1c/05-t1-vprime-b96fe8e4cc-cleanup.log` SHA256 `b44f5d9454c6147b89c68cd39e5fcf13682898377e6642ff20791502a91b3914`，表明 t1 卷已清理。backend 同步日志 SHA256 `2dffeda91c4c4d44adaef3377c54d2210c65c368d541ecba48b270f7b55bbacf`。t1 v1/v2 Submit 分别用时 `34.244 s` / `26.189 s`；各自 await attempt/captured session 为 `1/1`，剩余会话 `2`，健康让出 `0`。

### ct108 2× t4 三节点完整旅程

- 节点 `ct108-gw-dms`（hostname `gw-dms-test`），clean detached worktree `/home/dev/gdds-p6-s1c-dc69-evidence-ebd1`，取证合并提交 b96fe8e4cc；V' 与工具提交为双亲，合并相对 V' 仅改 benchmarks、对应测试与 docs（17 files changed，12,493 insertions(+)，674 deletions(-)）。项目 `s1c-vprime-ebd1`，使用 `--three-node-history`、cold History、2× t4 census 和 checkpoint `v1-submit`、`v2-preview`、`v2-submit`、`v3-preview`、`v3-submit`，预构建镜像、offline 环境、无代理。运行 `2026-10-31T15:36:31.277Z`–`20:59:36.448Z`，exit 0，`failure_step=null`，26/26 step checks 与 History 均通过。日志 `/home/dev/gdds-p6-logs/s1c/ct108-vprime-b96fe8e4cc-retry-journey.log` SHA256 `376a51af9b8e3dbb99c82616aee4097cd60de3fe11a8c8194f2ec9e6f4013bac`；状态 `/home/dev/gdds-p6-logs/s1c/evidence/ct108-vprime-b96fe8e4cc/state.json` SHA256 `072a2f5a128cc0d608943fd1ed072d04cdafdd1720cf302c45f6ada67aa0e56b`。
- v1/v2/v3 Submit 全部完成，恢复会话数均为 0；healthy handoff 分别为 3/2/2。Submit 总用时分别为 `1439.923 s`、`1312.896 s`、`1302.815 s`；Repository import 上界用时分别为 `195.639 s`、`155.066 s`、`148.846 s`。`await_import_result` 每次只领取一次，R5 会话预算未耗尽。v1 commit `gc0j1d5316nui249o5d1petnncn8u881`，v2 `ej01n1u7srga41mdsqbht4lri82kl1mp`，v3 `jlpa7e30svqudnem8uo40vrbf5j2upt6`；v1 与 v3 canonical digest 均为 `sha256:1f53df33093fa2cb0448a94af150ab4f288154bd45537e2ac2b88461b89e5c7c`。提交输入 census SHA256 `4c05fd9f16256403494dabea7cb90ee7a797c4add29ffa584d466b033d2a73dd`，v1 package SHA256 `74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c`，v2 package SHA256 `121dc3b0e0418a76e2563111970dd136cf00d0942c83f37b8cc19597995b6d20`。
- 离线 composite comparison 按输入 SHA256 与比较代码源码摘要复用既有结果：input `c9848e489968ecbe581b3140d895745c9bdd3405a51c3a085819beb077f9b3d2`，comparison source SHA256 `6c948e3a15b0598edb7e58f5215b56ac2681f7c880d61239a287167282c450a4`；cache 文件 `/home/dev/gdds-p6-logs/s1c/composite-cache/c9848e489968ecbe581b3140d895745c9bdd3405a51c3a085819beb077f9b3d2.json` SHA256 `ffa6e241f45f111ec5c863cd5a361cf8f68853aaa82d5bcb59275256d9900213`，本轮记录为复用。

### 只读对照与保留物

- 在临时副本上读取 `DOLT_HASHOF_TABLE`；原始当前卷与 1030b 卷未写入；v1/v3 通过临时 scratch 副本 checkout 对应 commit 后取值，未执行 Dolt add/commit。reference `v5fu8c7ej2do4smoruiglb5g8h864ka7` 的保存哈希列表与复制卷 631/631 匹配。
- (a) v1 `gc0j1d5316nui249o5d1petnncn8u881` 对 1030b：Dolt 表哈希 631/631 相同，canonical state 同为 `sha256:1f53df33093fa2cb0448a94af150ab4f288154bd45537e2ac2b88461b89e5c7c`。
- (b) v3 `jlpa7e30svqudnem8uo40vrbf5j2upt6` 对同轮 v1：Dolt 表哈希 631/631 相同。只读对照 JSON 结论 `MATCH`、`source_volumes_untouched=true`。日志 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-readonly-comparison.log` SHA256 `259acaed1f1728b1c4e91b6a2c4b9047cd5d81e3d3ce9a8233db00d942a9aca0`；结果 JSON SHA256 `bb713612da28ac16727d0b80778d9723ebb8df78374a1c142ed99cef3c15eeec`；临时副本清理日志 SHA256 `51bfc890f97419063c96a86e3d5b44416038518d2803c158d8031aa1ef394739`。1030b 对照哈希文件 `/home/dev/gdds-p6-logs/s1c/1030b-table-hashes-and-canonical-state.json` 未变。
- 新运行的 CT108 保留卷为 `s1c-vprime-ebd1_backend-artifacts`、`s1c-vprime-ebd1_backend-control`、`s1c-vprime-ebd1_repository-service-data`，保留至 S1c exit 合入后。`fb534`、`20e634` 两次既有运行卷与日志及 1030b 原保留卷未修改。已识别的偏差包括 DC68 范围内的工具/环境启动前失败、首次只读比较脚本解析失败、首次临时清理未清完，以及 05 最终日志未留存外层 exit code；六次尝试与处置见“DC69 取证补记”，不再使用“无未解释偏差”作为结论。

## DC69 取证补记

以下六项失败尝试均见 main `71d14f637f` 的 `p6-s1c-evidence-check-5.md` §3。失败阶段均在旅程栈启动前或仅操作临时副本/清理文件；05 两次 t1 启动前失败超过 DC68 一次重做，owner 已于 2026-10-31 追认，最终 `-final` 运行作为本轮证据。各次修正及成功记录如下：

| 节点与尝试时间 | 失败原因与修正 | 日志路径及 SHA256 |
|---|---|---|
| ct108，`2026-10-31T15:34:59Z`–`15:35:01Z`，三节点旅程首次启动 | 参数检查要求 `GATEWAY_P6_RUN_LOG` 指向 worktree 外的运行日志；旅程未启动。随后设置该变量并重启，成功运行见 `ct108-vprime-b96fe8e4cc-retry-journey.log`。 | 失败 journey `/home/dev/gdds-p6-logs/s1c/ct108-vprime-b96fe8e4cc-journey.log` SHA256 `4e2565f2a257084d04b931a28e22e4a8b42e5b84a9f04261ae22383a5c4c5ad5`；launch `/home/dev/gdds-p6-logs/s1c/ct108-vprime-b96fe8e4cc-launch.log` SHA256 `3e8ee734b8a10d481bc33fa0198b29140d7eb264c95035c39a1277898cd94f21`。 |
| ct108，`2026-10-31T21:03:58Z`–`21:04:30Z`，只读对照首次 | 对照脚本解析 `dolt log` 的 HEAD 时未去除 ANSI 颜色；在读取表哈希前失败，操作仅涉及副本。修正为解析前剥离 ANSI 转义序列，再执行成功对照。 | 首次对照 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-readonly-comparison-attempt1.log` SHA256 `6528aa3d0059421ec01471461725f0bd8f227b7978f1f1d7d52a652db57f6200`；诊断 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-readonly-comparison-attempt1-diagnosis.log` SHA256 `447ac1f787d01fa4ffd25bf3ef91bc0b7b695b06dd64ec55a2a8766c1645b429`；修正后对照 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-readonly-comparison.log` SHA256 `259acaed1f1728b1c4e91b6a2c4b9047cd5d81e3d3ce9a8233db00d942a9aca0`。 |
| ct108，`2026-10-31T21:06:12Z`，首次临时清理 | 清理检查发现哈希容器仍存在，未报告清理成功。随后停止并删除剩余哈希容器及临时副本；二次清理 exit 0。 | 首次清理 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-temp-cleanup-attempt1.log` SHA256 `50771b7ab18e2d2eac6df2705fdf65a04c0798e8d9ea7991c4b24694f5e88e9a`；完成清理 `/home/dev/gdds-p6-logs/s1c/ct108-dc69-vprime-temp-cleanup.log` SHA256 `51bfc890f97419063c96a86e3d5b44416038518d2803c158d8031aa1ef394739`。 |
| 05，`2026-10-31T15:19:00Z`，环境同步首次 | 同一 `uv sync` 命令重复传入 `--locked`，uv 拒绝执行。删除重复参数后于 `15:19:13Z` 同步成功。 | 首次 `/home/dev/gdds-p6-logs/s1c/05-env-sync-b96fe8e4cc.log` SHA256 `548906ea0d3a5c1bba75e53e5c41eae47bad784a17bec1927496748c2aea2f1e`；修正后 `/home/dev/gdds-p6-logs/s1c/05-env-sync-b96fe8e4cc-retry.log` SHA256 `2dffeda91c4c4d44adaef3377c54d2210c65c368d541ecba48b270f7b55bbacf`。 |
| 05，`2026-10-31T15:20:06Z`–`15:20:08Z`，t1 首次 | 工具参数校验拒绝 `--project-name` 单独使用，要求同时传 `--keep-stack`；旅程栈未启动。下一次尝试加入 `--keep-stack`。 | `/home/dev/gdds-p6-logs/s1c/05-t1-vprime-b96fe8e4cc.log` SHA256 `996f4702cb2c97441629d687df465188940a18bc87ac74a578c69132e69d9654`。 |
| 05，`2026-10-31T15:20:42Z`–`15:20:43Z`，t1 第二次 | 启动前预检未收到 project name，按默认项目名查找 backend 镜像并报缺失；旅程栈未启动。第三次命令同时传入 `--keep-stack` 与预构建镜像对应的 `--project-name s1c-vprime-ebd1`，运行成功。两次启动前失败超过 DC68 的一次重做限制，owner 已追认 `-final` 运行作为证据。 | 第二次 `/home/dev/gdds-p6-logs/s1c/05-t1-vprime-b96fe8e4cc-retry.log` SHA256 `59a7e2e9fb30bacb5ac08ca239ea99afb2601eb573f80a895547f05df31061e8`；追认的 `-final` `/home/dev/gdds-p6-logs/s1c/05-t1-vprime-b96fe8e4cc-final.log` SHA256 `67b01d5970770a74b77dd77683df8d51ba5baa6e885ddaf58a968936c9a6f4e1`，状态 SHA256 `2c06de99d53a75d7702c29362952e9cf5a912959430fd61b97ac35d56b5d7f52`。 |

- 第 3 个 RootFS DiffID 的完整值为 `sha256:3fda3219c8f4a902e577efcdb924b514318c606d47ba4b53640511b27925da18`，与三节点身份日志及状态文件一致。
- 04 首次 runner 失败后，owner 明确授权移除错误继承的 `GATEWAY_DOCKER_BUILD_NETWORK=none` 并重新运行；首次运行仍记为失败，最终证据取授权后的六包 runner 成功运行。两份 postflight 日志均存于开发节点 `/home/dev/gdds-p6-logs/s1c/`。
- S1c exit 清理清单增加 ct108 worktree 外缓存目录 `/home/dev/gdds-test-tmp/s1c-dc69-ct108-cargo-target`；按既定节点清理安排在 S1c exit 后删除。`fb534`、`20e634` 与 1030b 保留卷按原要求保留。
