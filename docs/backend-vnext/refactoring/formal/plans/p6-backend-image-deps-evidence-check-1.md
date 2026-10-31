# Phase 6 backend 镜像依赖层调整：证据复核 1

状态：**定向修订（只改测试）。** 04 取证第 1–4 步通过。第 5 步六包 runner exit 1，10 个失败用例分为三组，根因都是候选没有同步更新的测试，与节点环境和产品代码无关。修订后重跑 04 runner；第 1–4 步结果按第 4 节沿用。

## 1. 复核对象

- 代码候选 `642f2d3ac7`（复审 1 通过）；handoff 提交 `815a898155`（分支 `p6-backend-image-deps`，本地）。
- 审核 bundle `/home/dev/gdds-p6-backend-image-deps-evidence-review-815a8981.bundle`，SHA256 `6f7dfd3f…`。
- runner 日志 04 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/04-authoritative-runner-642.log`，SHA256 `f3c4bd57…`（审核者在 04 上核对）。

## 2. 第 1–4 步（通过）

| 步骤 | 结果 |
|---|---|
| 1 dependency-base | CT201 构建 `gateway-backend-deps:lock-c668cef8e47e`。归档 SHA256 两端相同；04 load 后 config digest `a8d9d1ac…` 与全部 20 个 DiffID 相同 |
| 2 04 离线构建 | `network=none`、预置模式，候选 clean worktree，backend/worker 构建成功（config digest `14ebd242…` / `4addcd95…`） |
| 3 源码改动后离线重建 | 首次尝试因 context 参数错误，在构建开始前失败，已按复核意见整步重做。重做时 client 与 Rust 两次改动都 exit 0；dependency-base 阶段全部 `CACHED`；Rust 改动后重新编译 `gateway-compute-python` 并生成 wheel |
| 4 镜像等价 | 基线 `26738ae5c4` 在 CT201 构建、传到 04 并核对身份。只读采集结果：两组镜像的 venv 包集合（25 个）与系统 Python 包相同；`/app` 文件路径与内容摘要相同；ENV、CMD、WORKDIR 相同。唯一差异是文件权限位（CT201 umask 0002，04 umask 0022），属构建机差异，handoff 已解释。首次采集脚本在任何 `docker run` 之前失败，修正后重做（符合 DC68） |

## 3. 第 5 步 runner 失败的根因

### E1 backend：两个测试文件的 Compose 环境字典没有传入预置参数（3 例）

- 失败用例：`test_ordered_history_compare_compose_journey`、`test_ordered_submit_bisect_control_cases`、`test_preview_worker_restart_takes_over_expired_running_operation`。
- `tests/test_ordered_compare_compose.py:51` 与 `tests/test_ordered_submit_bisect_compose.py:52` 中的 `_compose_env` 返回一个只含 project 名与密钥文件路径的新字典，没有继承 `os.environ`。其他 Compose 测试（例如 `test_submit_compose_e2e.py`、`test_history_compose_e2e.py`）以及 `real_dump_journey._compose_environment` 都从 `os.environ` 复制。
- 因此 `GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE`、`GATEWAY_DOCKER_BUILD_NETWORK` 都没有到达 Compose。Compose 按默认值走非预置分支，`curl astral.sh` 失败。原有的 `GATEWAY_BACKEND_UV_BOOTSTRAP_*` 同样会被丢掉，这是之前就潜伏的问题。
- S1c 的 runner 没有暴露它：S1c 使用 `GATEWAY_COMPOSE_GATE_PREBUILT=1`，harness 根据 `os.environ` 跳过了构建。
- 修正：这两个 `_compose_env` 改为在 `os.environ` 的副本上更新，与其他 Compose 测试一致；或者由 `compose_gate_harness` 提供统一的环境构造函数，各测试共用。

### E2 repository_service：runner 测试的仓库 fixture 缺少新增的 Dockerfile（6 例）

- 失败用例：`test_run_tests_script.py` 中凡是选中 backend 的 6 个用例，包括 Hypothesis storage 清理的两个参数组合。
- `_runner_fixture` 按固定清单在临时仓库中放置 Docker 输入文件，清单里有 `backend/Dockerfile`，没有本任务新增的 `backend/Dockerfile.dependency-base`。fixture 运行真实的 `test_input_closure.py`，候选已把这个新文件列为 backend 的 Docker 输入，于是 backend manifest 执行 `git rev-parse --verify HEAD:vnext/backend/Dockerfile.dependency-base` 失败，stderr 为 `error: fatal: Needed a single revision`。Hypothesis 用例中“manifest 事件缺项”是同一失败的后果。
- 这组失败与环境无关，在任何节点上都会出现。候选在 05 的 focused 测试只覆盖了 Dockerfile 合同、构建脚本与闭包测试，没有包括 `test_run_tests_script.py`，所以没有发现。
- 修正：把 `backend/Dockerfile.dependency-base` 加入 fixture 清单，并在 05 上补跑 `test_run_tests_script.py`。

### E3 repository_service：一个测试读取了 runner 的环境变量（1 例）

- 失败用例：`test_build_repository_service_image_script.py::test_build_script_defaults_docker_build_network_to_host`。
- 该测试检查构建脚本在未设置 `GATEWAY_DOCKER_BUILD_NETWORK` 时默认使用 `host`，但继承了 runner 环境中的 `GATEWAY_DOCKER_BUILD_NETWORK=none`。本任务的 runner 要在 `network=none` 下构建，所以测试必须与环境隔离。
- 修正：该测试先清除这个变量（`monkeypatch.delenv(..., raising=False)`，或者像 `_runner_fixture` 一样过滤 `GATEWAY_DOCKER_BUILD_NETWORK`）。

## 4. 修订后的取证范围

- 修订只改 `vnext/backend/tests/`、`vnext/repository_service/tests/` 与 docs。backend 镜像只复制 `backend/src`、`rust`、`shared_kernel`、`repository_client`、`repository_contracts`，这些测试目录不进入任何镜像，Dockerfile 与构建脚本也不变。
- 新候选与 `642f2d3ac7` 的 diff 满足上述范围时：
  - 第 1–4 步结果沿用，handoff 记录 diff stat；
  - 只需在新候选的 clean worktree 中重跑 04 六包权威 runner，该 runner 本身会在 `network=none` 下离线构建 backend/worker。
- runner 环境建议与 S1c 的 04 runner 一致：`PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`，不设置 `RUSTUP_TOOLCHAIN`、`RUSTUP_HOME`、`CARGO_HOME`。本次 runner 直接把 toolchain 目录放在 PATH 中，并设置了这三个变量，结果也能工作；但闭包会摘要 `RUST*`、`CARGO*` 设置，节点上 runner 的环境统一，后续阶段才能按包沿用。

## 5. 后续

1. 修订 E1–E3：另起提交，不改写已有提交。在 05 上跑受影响的测试文件（两个 backend Compose 测试文件只做收集与静态检查，`test_run_tests_script.py`、`test_build_repository_service_image_script.py`、闭包测试实际运行）与五包 ruff/mypy。由审核者做只针对这次修订的短复审。
2. 04 六包权威 runner 在新候选上重跑。
3. 证据复核通过后办理 exit：
   - tag `p6-backend-image-exit`，合入 main；
   - 记录本任务替代 DC67 补充第 2 项（整镜像预构建改为只预填充 dependency-base）；
   - 把 AGENTS 与 testing-conventions 的文字交负责这两份文件的会话；
   - 清理临时内容（保留 S1c 的 04 worktree）。
