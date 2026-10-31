# Phase 6 backend 镜像依赖层调整：证据复核 2

状态：**证据通过，具备 exit 条件。** 待 owner 授权办理 exit。

## 1. 对象

- 代码候选 `861ab2467329c9784f1d64c70855d50c84dc36f6`；handoff 提交 `30b656a65edf391ca31423ab41fef96bc8b544df`（分支 `p6-backend-image-deps`，本地）。
- 审核 bundle `/home/dev/gdds-p6-backend-image-deps-evidence-review-30b656a65e.bundle`，SHA256 `78a13987…`。
- 与 main 合并无冲突（`git merge-tree` 检查）。

## 2. 04 六包权威 runner

日志 04 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/04-authoritative-runner-861-retry.log`，SHA256 `5c530729…`（审核者在 04 上核对）。

| 项 | 结果 |
|---|---|
| 节点、HEAD | `gw-dms-test-04`；起止 HEAD 均为 `861ab24673`；起止 worktree clean |
| 时间 | 2026-10-31 03:37:37–03:59:02 UTC |
| 环境 | 与 S1c 的 04 runner 一致（`PATH` 以 `/home/dev/.cargo/bin` 开头，`UV_OFFLINE=1`，`CARGO_NET_OFFLINE=true`），另设 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-c668cef8e47e`、`GATEWAY_DOCKER_BUILD_NETWORK=none`；未设 `RUSTUP_*`、`CARGO_HOME`、`GATEWAY_COMPOSE_GATE_PREBUILT` 与代理 |
| 结果 | 六包均 passed：backend 3069 + 41（serial），Repository Service 1743 / 1 skipped + 207（serial），rust、shared_kernel、repository_contracts、repository_client 均通过；runner exit 0 |
| Compose | `compose_gate_prebuilt=false`。backend 与 worker 在 runner 内以 `network=none` 和预置模式离线构建，Compose 旅程在这些镜像上运行。这是本任务的核心验收 |

- 首次启动尝试（`04-authoritative-runner-861.log`）因工作目录错误找不到 `run-tests.sh`，exit 127，没有运行任何内容；修正后重做。handoff 已记录，符合 DC68。
- 日志中部分 runner 输出行重复出现，是记录方式造成的，不影响结果判读。

## 3. client e2e 镜像被重建

- runner 前 `gateway-repository-client-e2e:local` 为 `58d59883ac9c`；runner 后为 `sha256:c8c39843…`，label revision 为 `861ab24673`，client uv lock label 不变，仍从本机的 `gateway-repository-client-e2e-base:local`（`ba6c64db…`）构建。
- 判定：这是 Repository Service 门禁的正常行为。client e2e 镜像的 revision label 与当前 HEAD 不同时，harness 在本机从 dependency-base 离线重建，这次重建成功。项目约束“不得 `docker rmi` client e2e 镜像”针对的是手工删除，不针对 harness 的重建；实施者也没有手工操作该镜像。
- 影响：
  - S1c 的 04 runner 已经完成，S1c exit 不需要在 04 重新运行，不受影响；
  - 以后在 04 上运行任一 HEAD 时，harness 会按需再次离线重建该镜像；
  - 闭包的 `image_ids` 只记录 client e2e 的 dependency-base（未变），不记录 `gateway-repository-client-e2e:local` 本身，所以这次重建不改变已记录的闭包。
- 处置：无需恢复，handoff 中记录的说明即可。

## 4. 第 1–4 步

按[证据复核 1](p6-backend-image-deps-evidence-check-1.md) §2 通过，按其 §4 与[短复审](p6-backend-image-deps-evidence-check-1-rereview.md)沿用到 `861ab24673`（`642f2d3ac7..861ab24673` 只改测试与 docs）。

## 5. exit 事项（待 owner 授权）

1. 在分支上提交 exit 记录，更新 handoff 状态，并在 DC67 补充第 2、5 项下记录：
   - backend/worker 整镜像预构建改为只预填充并传输 dependency-base；
   - 测试节点上 runner 设置预置开关、dependency-base tag 与 `GATEWAY_DOCKER_BUILD_NETWORK=none`，在本机离线构建；
   - dependency-base 在锁文件或基础镜像变化时在 CT201 用 `build-backend-dependency-base.sh --save` 重建，跨节点身份按 DC67 澄清核对。
2. 在 exit 记录提交上打附注 tag `p6-backend-image-exit`，合入 main，推送 main 与 tag，同步三个节点。
3. 把 AGENTS 与 testing-conventions 需要同步的文字（handoff“待同步文档”一节）交负责这两份文件的会话；本会话不改这两份文件。
4. 清理：
   - 04 的取证 worktree、比较用镜像 tag 与归档、源码改动临时内容；
   - CT201 与 05 的临时 worktree 和 bundle；
   - 合入后删除本地分支 `p6-backend-image-deps`；
   - 保留 dependency-base `gateway-backend-deps:lock-c668cef8e47e`（04 的后续 runner 要用），以及 S1c 的 04 worktree、`/home/dev/gdds-p6-baseline-04`、S1c 镜像与 client e2e 镜像。
