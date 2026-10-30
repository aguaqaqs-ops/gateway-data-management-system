# Phase 6 backend dependency-base handoff

## 状态

- 来源基线：`26738ae5c4b8b15676d9822b28a64fd3dad1b009`
- 分支：`p6-backend-image-deps`
- 代码候选提交：`98181d7d192138d85db746132f78700c0252bd1e`。
- 本 handoff 紧随代码候选提交；handoff 提交号由 Git 记录并在交付消息中给出。
- 审核：待审核会话。
- 取证：审核通过前不运行；按 §5 在 04 完成后回填。
- 本任务不改应用代码、Contract、golden 或五个 Python/Rust 锁文件。
- 主 checkout 的 `AGENTS.md` 与 `testing-conventions.md` 保持原样。

## 改动清单

- `vnext/backend/Dockerfile`：将第三方依赖和 Cargo 下载层移到 Rust、共享内核、client、contracts 与 `backend/src` 源码复制之前；预置模式从 dependency-base 取得 uv、Python/Cargo 缓存与构建工具。完整源码复制后的 `uv sync` 与 maturin/Cargo 构建使用离线模式。
- `vnext/backend/Dockerfile.dependency-base`：构建只含锁定第三方 Python 依赖（含 maturin）与 `cargo fetch --locked` 缓存的 dependency-base；保留每个锁定输入的摘要文件，并以完整输入摘要设置 label。
- `vnext/scripts/build-backend-dependency-base.sh`：计算 canonical 输入摘要，生成 `gateway-backend-deps:lock-<摘要前12位>`，拒绝 tag/label 不匹配的复用，并支持 `--save <path>` 输出归档及 SHA256；`--print-input` 只读输出摘要。
- `vnext/deploy/compose.yaml`：backend 与 worker 增加 dependency-base 镜像和预置依赖 build args；默认依赖镜像仍为 Rust builder base，开关默认为 `0`。
- `vnext/scripts/test_input_closure.py`：backend 闭包记录实际选择的 dependency-base 名称、本机 image ID 与预置开关；closure schema 升至 10。
- 测试：backend Dockerfile 合同、dependency-base 脚本输入与复用行为、backend 闭包镜像与开关变化。

## 新旧层顺序

| 旧顺序 | 新顺序 |
| --- | --- |
| builder 复制 Rust/shared_kernel/client/contracts → 下载 uv 与 Python → `uv sync` → maturin 构建 | builder 先消费锁定的第三方依赖与 Cargo 缓存 → 复制 Rust/shared_kernel/client/contracts → `UV_OFFLINE=1 uv sync` → `CARGO_NET_OFFLINE=true maturin build --locked` |
| runtime 复制所有本地包 → 安装 uv → `uv sync` → 安装 Rust wheel | runtime 先装/复制 uv，并通过临时 BuildKit bind mount 使用第三方依赖缓存 → 复制 Rust/shared_kernel/client/contracts/backend/src → 离线安装本地包；Rust wheel 也通过临时 bind mount 安装 |

最终 runtime 仍由 `python:3.14.6-slim-bookworm` 起步，只含该运行期 venv、uv 与应用源码；Rust 工具链、Cargo 缓存、uv 缓存、临时 wheel 与编译目录不进入 runtime image layer。

使用 uv `0.11.28` 的 `uv sync --no-install-local --no-install-project` 安装远端锁定依赖，同时跳过 backend 与本地路径包。复制本地源码后再用 `UV_OFFLINE=1 uv sync` 安装本地包。该选项在 uv CLI 文档中定义为跳过当前项目、workspace 与其他本地路径/editable 包，适用于先缓存第三方依赖的 Docker 构建。[uv CLI reference](https://docs.astral.sh/uv/reference/cli/)

仓库本地包的 `build-system.requires` 为 `uv_build>=0.11.28,<0.12.0`；uv `0.11.28` 与该范围匹配，uv 可用可执行文件内置的 build backend 完成本地包安装，不需要未锁定的额外下载。[uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)

## Dependency-base 输入摘要

脚本对下列 canonical JSON 计算 SHA-256：

- `backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version`；
- `rust/Cargo.lock`、`rust/rust-toolchain.toml`；
- Python 版本、uv 版本、Rust toolchain channel/profile/components；
- Rust base image 引用与当前本机 image ID。

镜像 label：`gateway.backend.dependency-input-sha256`。tag 仅使用摘要前 12 位；完整 JSON 与摘要保存在 dependency-base 内。Dockerfile 消费预置镜像时检查 tag 后缀、摘要文件和当前 checkout 中各锁定文件的 SHA256。输入变化即得到新 tag；旧 tag label 不匹配时拒绝复用。

## 测试归属与代码候选验证

- Dockerfile / Compose 静态合同：`backend/tests/test_backend_dockerfile_contract.py`。
- dependency-base build/tag/label/save 脚本：`backend/tests/test_build_backend_dependency_base_script.py`。
- package closure：`repository_service/tests/test_test_input_closure.py`（该文件是 `test_input_closure.py` 的现有测试 owner）。
- 05 clean、已提交 worktree `HEAD=98181d7d192138d85db746132f78700c0252bd1e` 验证（hostname `gw-dms-test-05`；2026-10-30 23:11:30–23:12:01 UTC；`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-backend-image-deps-cargo-target`、`RUSTUP_TOOLCHAIN=1.97.0`）：
  - backend Dockerfile 与 dependency-base build script focused tests：10 passed。
  - `repository_service/tests/test_test_input_closure.py -m unit`：37 passed。
  - `shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 五包 `ruff check .` 和 `mypy` 均通过。
  - `docker compose -f vnext/deploy/compose.yaml config --quiet` exit 0；Compose 对未设置的 `GATEWAY_BACKEND_SESSION_FILE`、`GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE` 与 `GATEWAY_P2R2_BEARER_TOKEN_FILE` 输出默认空值提示。
  - 完整日志：`/home/dev/gdds-p6-logs/p6-backend-image-deps-98181d7d-05-focused.log`，SHA256 `977bc1a68b8d4b69b1f2402fcd1f97f638736811243a4ef1817ed4e8d36d1732`，exit code 0。
- 首次 focused 尝试在 backend venv 同步时发现 CT05 root SSH 初始 `PATH` 不含 Cargo 工具链；`/root/.rustup/toolchains/1.97.0-x86_64-unknown-linux-gnu/bin` 与 crates 缓存已存在。后续会话按 `rust-toolchain.toml` 选出该目录并临时置于 `PATH` 前端，Rust 扩展离线构建成功。重跑还发现一个静态合同测试要求出现字面 `--offline`，但 Dockerfile 用 `UV_OFFLINE=1`；该合同断言在 `98181d7d` 修正后通过。尝试日志：
  - `/home/dev/gdds-p6-logs/p6-backend-image-deps-43b62743-05-focused.log`，SHA256 `13d3b430567d6e63f54f3cd95fd9c8033d0482fa95d685fd51c165ffa6650cc2`，首次环境失败。
  - `/home/dev/gdds-p6-logs/p6-backend-image-deps-43b62743-05-focused-retry.log`，SHA256 `aad04b1e1e752b45111933424d0df23d591123014d94fc179784cd1f826c1676`，合同断言失败。
- 未在开发主机执行项目测试或静态检查。未运行全量 runner、Docker build 或真实数据旅程。

## 容器与 runner 取证

待审核通过后在此记录：

1. CT201 dependency-base 构建提交、tag、完整输入摘要、image ID、构建日志与时间；`docker save` 文件 SHA256、文件大小与局域网传输记录；04 `docker load` 后 image ID。
2. 04 以 `GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 和 dependency-base tag 构建 backend/worker 的日志、时间、image IDs。
3. 04 临时 worktree 对 `repository_client/src` 与 Rust 源码分别做无害改动后的 offline rebuild 日志、时间、镜像 ID；恢复与删除记录。
4. 新候选与基线 `26738ae5c4` 镜像的已安装包名/版本集合、应用源码树摘要、runtime ENV 与 CMD 比较，以及全部差异解释。
5. 04 权威 runner 的环境（含 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，backend preloaded=1，`GATEWAY_COMPOSE_GATE_PREBUILT` 未设置）、六包逐项运行/沿用判断、来源 V/日志、总 exit code 与镜像身份。
6. 本任务不运行真实数据旅程。镜像等价核对若发现无法解释的构建产物之外差异，停止并交 owner 决定是否补 t1 冒烟。

## 待同步文档

以下内容由负责治理文档的会话同步，本分支不改 `AGENTS.md` 与 `testing-conventions.md`：

- backend/worker 需要在测试节点离线构建时，先在 CT201 clean worktree 调用 `build-backend-dependency-base.sh --save <归档路径>`；通过获准局域网传输归档并在目标测试节点 `docker load`。记录来源提交、输入摘要、tag、image ID、归档 SHA256、缓存来源类别/端点与时间，不记录凭据。
- runner 设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 与 `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`；保留 Compose backend/worker build，使候选镜像在 `GATEWAY_DOCKER_BUILD_NETWORK=none` 下实际构建。不要设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- backend 闭包的 Docker 输入包含所选 dependency-base 名称、本机 image ID、预置开关及其 build 环境指纹；切换任一输入要求 backend 重新运行。
- 替代 DC67 补充第 2 项的 backend/worker 整镜像预构建和传输：只预填充并传输锁定 dependency-base；04 在候选 clean worktree 中离线构建 backend/worker，再由权威 runner 运行 Compose 门禁。Repository Service 与 client e2e 继续沿用各自的预置依赖模式。

## 偏差、未决与清理

- 05 代码候选检查已通过；04 镜像和 runner 取证待代码审核通过后进行。
- 主工作区未提交的治理文档修改未纳入本分支。
- 后续节点临时内容、bundle、归档及容器需在证据完成后列明清理位置；dependency-base tag 是否保留按 owner 的节点预填充安排执行。
