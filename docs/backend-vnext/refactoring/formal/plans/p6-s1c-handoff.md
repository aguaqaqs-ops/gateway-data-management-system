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
