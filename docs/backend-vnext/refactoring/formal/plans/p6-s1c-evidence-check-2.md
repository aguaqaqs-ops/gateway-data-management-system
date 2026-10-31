# Phase 6 S1c 取证复核 2（04 runner 与 05 t1）

状态：**04 权威 runner 与 05 t1 证据通过。** S1c 只剩 ct108 的 2× t4 Submit（DC66 第 4 项）。该项等待基准会话的预构建镜像工具在 05 验证通过；目前的阻塞是基准会话的验证环境设置错误（第 4 节），不是产品或工具缺陷。

## 1. 复核对象

- 代码候选 V = `3008d578cf2ee0eaf9236f01e33b5008d65ef36c`（复审 1 通过）；handoff 提交 H = `d88dad7d3378a856e77995d4eda23dbf7d0bf515`（分支 `p6-s1c-impl`，本地）。
- 工具提交 T = `469a1549634d74dcf0e6c065998fa63c51ee7036`，在 V 之上，由 `f08a07dd00`、`4f082783ab`、`469a154963` 三个提交组成；存在于 05 的仓库，不并入 S1c 代码候选。
- 身份口径：DC67 澄清（main `4725697f32`）。

## 2. 04 六包权威 runner

日志 04 `/home/dev/gdds-p6-logs/s1c/04-runner-3008d578cf-dc67-offline.log`，SHA256 `a2603a68…`（审核者在 04 上核对）。

| 项 | 结果 |
|---|---|
| 节点、HEAD | `gw-dms-test-04`；起止 HEAD 均为 V；`END_WORKTREE_STATUS=0`；worktree `/home/dev/gdds-p6-s1c-v-3008-04` 现仍 clean |
| 时间 | 2026-10-30 23:31:53–23:53:01 UTC |
| 环境 | `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`、`GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-v-3008`、`TMPDIR=/home/dev/gdds-test-tmp`；六个 proxy 变量均未设置；未设 `GATEWAY_TEST_PACKAGES` |
| 结果 | 六包均 passed；backend 3076 + 51（serial），Repository Service 1741 / 1 skipped + 207（serial）；`RUNNER_EXIT_CODE=0` |
| 镜像 | backend/worker 为开发节点预构建、按 DC67 澄清核对过的 `s1c-v-3008-*`；Repository Service 镜像标签与 V 相符 |
| 结束后 | 04 无容器残留 |

这次运行是后续阶段的 carried 来源 V。按 DC51，04 worktree `/home/dev/gdds-p6-s1c-v-3008-04` 保留到 S1c exit 合入之后。

## 3. 05 t1

- T 的范围：`V..T` 只改 `vnext/backend/benchmarks/real_dump_journey.py` 与 `vnext/backend/tests/test_real_dump_journey.py`（339 行新增，6 行删除），已在 05 上核对。
- T 的行为：调用方设置 `GATEWAY_COMPOSE_GATE_PREBUILT=1` 时，不构建 backend/worker，改为核对所用 project 的镜像存在，从本机 `docker image save` 归档读取 config digest，并记录在旅程结果里；未设置时仍按原方式构建。这与 S1c 取证提示词的要求一致。
- T 的验证：05 focused 65 passed，五包 ruff/mypy 通过；日志 SHA256 `317c75b4…`。
- t1 旅程：日志 05 `/home/dev/gdds-p6-logs/s1c/05-t1-real-data-f08a07dd00.log`，SHA256 `49c11f90…`（审核者在 05 上核对）。
  - hostname `gw-dms-test-05`；起止 HEAD 均为 T；2026-10-30 23:39:25–23:43:20 UTC；`EXIT_CODE=0`；worktree clean。
  - `prebuilt_images_verified`：backend、worker 的 config digest 均为 `sha256:b1f3c7b6…`，与开发节点构建结果相同。
  - 各步骤 `step_succeeded`，v2 Preview、v2 Submit、History 的 operation 均为 SUCCEEDED；结论 `PASS`。
- 观察：T 只接受值 `1`，没有接受 `true`/`yes`；本次调用用的是 `1`，结果不受影响。T 没有记录 DiffID，S1c 的提示词也没有要求。基准会话的移植版本按其提示词同时记录 DiffID。

## 4. 基准会话工具验证失败的原因

- 失败日志 05 `/home/dev/gdds-p6-logs/baseline/05-prebuilt-image-tool-a039d9b2.log`，SHA256 `7193082f…`。
  - 新 worktree 第一次同步 backend 环境时要构建 `gateway-compute-python`。maturin 没有找到 Rust 工具链，于是经 puccinialin 安装或更新 rustup，下载失败（`Network is unreachable`），exit 1。
- 原因：日志记录的环境只有 `UV_OFFLINE=1`。
  - 没有设置 `CARGO_NET_OFFLINE=true`。
  - `PATH` 是 root SSH 的默认值，不包含 `/home/dev/.cargo/bin`。05 上的 rustup 代理在该目录中；工具链 `1.97.0` 在 `/root/.rustup/toolchains`，crates 缓存在 `/root/.cargo/registry`。
  - 对照：同节点成功的 S1c T 验证和 backend 镜像依赖层验证，都使用 `PATH=/home/dev/.cargo/bin:/root/.local/bin:…` 和 `CARGO_NET_OFFLINE=true`。
- 结论：这是验证环境设置错误，按 DC67 停止是正确的。修正方式是按 S1c runner 的环境重新运行，属于 DC66 第 5 项常设授权的范围，不需要 owner 另行决定。

## 5. 结论与下一步

| 项 | 判定 |
|---|---|
| 04 六包权威 runner（V） | 通过 |
| 05 t1（T，V 的产品代码） | 通过 |
| ct108 2× t4 Submit | 待基准工具候选 `a039d9b2c1` 按第 4 节环境在 05 验证通过，并在 ct108 加载、核对 V 的镜像之后执行；按 DC66 第 4 项从 1030b v1-submit checkpoint 的副本续跑，与 1030b 保留卷对照。**已由 DC66 修订（2026-10-31）改为**：ct108 跑一次 2× t4 完整旅程（预构建 V 镜像、保留卷），v1 Submit 结果与 1030b 保留卷只读对照；前提只剩工具候选在 05 验证通过与 ct108 加载核对 V 的镜像 |
| S1c exit | 第 3 行完成并复核后，交 owner 终审 |
| 04 节点 | S1c 在 04 的 runner 已结束，backend 镜像依赖层调整的 04 取证可以开始 |
