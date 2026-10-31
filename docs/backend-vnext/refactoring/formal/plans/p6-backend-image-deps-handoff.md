# Phase 6 backend dependency-base handoff

## 状态

- 来源基线：`26738ae5c4b8b15676d9822b28a64fd3dad1b009`
- 分支：`p6-backend-image-deps`
- 镜像代码候选 `642f2d3ac7fdf76045f3e64434e882661a5bfafa` 未修改；原代码修订 `642f2d3ac7` 与 handoff 提交 `815a898155` 均未改写。
- 依据复核 1（main `1a009ed102`）追加测试修订：E1–E3 提交 `9600b339272cbb6d0f95811f7e992e73e05893e9`；修复首次测试暴露的 selector fixture 内容后续提交 `861ab2467329c9784f1d64c70855d50c84dc36f6`。本 handoff 随后单独提交。
- 05 定向验证已通过。04 第 1–4 步沿用；新候选的 04 六包权威 runner 等短复审通过后运行，尚未运行。
- 本任务只改测试与文档；不改应用代码、Contract、golden 或五个 Python/Rust 锁文件；未运行真实数据旅程。
- 主 checkout 的 `AGENTS.md` 与 `testing-conventions.md` 保持原样。

## 改动清单

- `vnext/backend/Dockerfile`：前置依赖同步改用 `--frozen`；源码后 builder 同步保留 `UV_OFFLINE=1 uv sync --locked`。runtime 的 uv 缓存 bind mount 加 `rw`；预置模式把 dependency-base 的 uv 只读 bind mount 到临时路径，再用它通过 pip 安装 runtime uv。wheel mount 明确只读。
- `vnext/backend/Dockerfile.dependency-base`：构建锁定第三方 Python 依赖（含 maturin）与 `cargo fetch --locked` 缓存；前置 `uv sync` 使用 `--frozen`，并将完整输入摘要和基础镜像 inspect ID 写入 label/metadata。
- `vnext/scripts/build-backend-dependency-base.sh`：计算稳定 tag 输入摘要，生成 `gateway-backend-deps:lock-<摘要前12位>`，拒绝 tag/label 不匹配的复用，并支持 `--save <path>` 输出归档及 SHA256；`--print-input` 只读输出摘要。tag 输入包含基础镜像 config digest 与全部 RootFS DiffID，不包含 store-specific inspect ID。
- `vnext/deploy/compose.yaml`：backend 与 worker 增加 dependency-base 镜像和预置依赖 build args；默认依赖镜像仍为 Rust builder base，开关默认为 `0`。
- `vnext/scripts/test_input_closure.py`：backend 闭包记录实际选择的 dependency-base 名称、本机 image ID 与预置开关；closure schema 升至 10。
- 测试：backend Dockerfile 合同、dependency-base 脚本输入与复用行为、backend 闭包镜像与开关变化。

## 新旧层顺序

| 旧顺序 | 新顺序 |
| --- | --- |
| builder 复制 Rust/shared_kernel/client/contracts → 下载 uv 与 Python → `uv sync` → maturin 构建 | builder 先用 `uv sync --frozen` 消费锁定第三方依赖与 Cargo 缓存 → 复制 Rust/shared_kernel/client/contracts → `UV_OFFLINE=1 uv sync --locked` → `CARGO_NET_OFFLINE=true maturin build --locked` |
| runtime 复制所有本地包 → 安装 uv → `uv sync` → 安装 Rust wheel | runtime 经 pip 安装 uv；预置分支从临时只读 bind mount 执行 dependency-base 中的 uv → 通过临时可写 uv-cache bind mount 安装第三方依赖 → 复制 Rust/shared_kernel/client/contracts/backend/src → 离线安装本地包；Rust wheel 经只读临时 bind mount 安装 |

最终 runtime 仍由 `python:3.14.6-slim-bookworm` 起步，只含该运行期 venv、uv 与应用源码；Rust 工具链、Cargo 缓存、uv 缓存、临时 wheel 与编译目录不进入 runtime image layer。

使用 uv `0.11.28` 的 `uv sync --frozen --no-install-local --no-install-project` 在源码复制前安装锁定的第三方依赖，避免缺少本地路径包元数据时 `--locked` 校验失败。完整源码复制后，builder 用 `UV_OFFLINE=1 uv sync --locked` 校验并安装本地依赖；runtime 使用 `UV_OFFLINE=1 uv sync --frozen` 完成离线安装。`--no-install-local` 跳过本地路径/editable 包，便于先缓存第三方依赖。[uv CLI reference](https://docs.astral.sh/uv/reference/cli/)

仓库本地包的 `build-system.requires` 为 `uv_build>=0.11.28,<0.12.0`；uv `0.11.28` 与该范围匹配，uv 可用可执行文件内置的 build backend 完成本地包安装，不需要未锁定的额外下载。[uv build backend](https://docs.astral.sh/uv/concepts/build-backend/)

## Dependency-base 输入摘要

脚本对 `tag_inputs` 对象的 canonical JSON 计算 SHA-256：

- `backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version`；
- `rust/Cargo.lock`、`rust/rust-toolchain.toml`；
- Python 版本、uv 版本、Rust toolchain channel/profile/components；
- Rust base image 引用、config digest 与完整 RootFS DiffID 列表。

本机 `docker image inspect` ID 不进入 tag 摘要，只写入 `inputs.json` 的 `base_image_id` 与 `gateway.backend.base-image-inspect-id` label。tag 摘要中的稳定 config digest 与所有 DiffID 用于识别基础镜像内容；跨节点 save/load 核对也只比较 config digest 与每个 DiffID，不比较 inspect ID。脚本 Usage 与输出的 `inputs.json` 都记录这套口径。

镜像 label `gateway.backend.dependency-input-sha256` 记录完整 tag 输入摘要；tag 仅使用摘要前 12 位。完整 JSON 与摘要保存在 dependency-base 内。Dockerfile 消费预置镜像时检查 tag 后缀、摘要文件和当前 checkout 中各锁定文件的 SHA256。锁定输入或基础镜像内容变化即得到新 tag；已有 tag label 与当前摘要不符时拒绝复用。

### 独立审核 F1–F4 定向修订

- **F1：已修复。** Runtime 对 `/root/.cache/uv` 的 bind mount 显式为 `rw`；该 mount 写入在 `RUN` 结束后丢弃。builder 的 wheel bind mount 显式为 `ro`。
- **F2：已修复。** dependency-base 与 backend Dockerfile 的非预置前置依赖同步使用 `uv sync --frozen --no-install-local --no-install-project`。builder 复制本地源码后的 `UV_OFFLINE=1 uv sync --locked` 保留。
- **F3：已处理，采用 inspect ID 仅作元数据。** `base_image_id` 不属于 `tag_inputs`；`tag_inputs` 改用基础镜像 config digest 与全部 DiffID，所以同内容镜像在不同 store 上得到同一依赖 tag，同时基础镜像内容变化会改变 tag。inspect ID 保留在 `inputs.json` 和 label。跨节点 identity 核对按 config digest + 全部 DiffID，不比较 inspect ID。
- **F4：已修复并冒烟通过。** 删除把 dependency-base 的 uv `COPY` 到 `/usr/local/bin/uv` 的步骤。预置分支把它只读挂载到 `/tmp/dependency-base-uv`，以该路径运行 `uv pip install --system --offline uv==0.11.28`。有/无 trusted-host 的两个非预置分支也都由 pip 安装 uv；最终 runtime 的 uv 均来自 pip wheel。

## 测试归属与代码候选验证

- Dockerfile / Compose 静态合同：`backend/tests/test_backend_dockerfile_contract.py`。
- dependency-base build/tag/label/save 脚本：`backend/tests/test_build_backend_dependency_base_script.py`。
- package closure：`repository_service/tests/test_test_input_closure.py`（该文件是 `test_input_closure.py` 的现有测试 owner）。
- 05 clean、已提交 worktree `HEAD=642f2d3ac7fdf76045f3e64434e882661a5bfafa` focused 与静态验证（hostname `gw-dms-test-05`；2026-10-30 23:36:14–23:36:21 UTC；`TMPDIR=/home/dev/gdds-test-tmp`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/p6-backend-image-deps-review-fix-cargo-target`、`RUSTUP_TOOLCHAIN=1.97.0`）：
  - backend Dockerfile 合同与 dependency-base build script 测试：11 passed（含 F1/F2/F3 新断言）。
  - `repository_service/tests/test_test_input_closure.py -m unit`：37 passed。
  - `shared_kernel`、`repository_contracts`、`repository_client`、`backend`、`repository_service` 五包 `ruff check .` 和 `mypy` 均通过。
  - 日志：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-05-focused.log`，SHA256 `0bfe5eb5eda54beabda42b7cbb31594af8056e14dbd6dbd6ff2c243a524303f2`，exit code 0。
- CT201（hostname `heavy-dev-01`）调试构建冒烟，2026-10-30 23:38:08–23:41:55 UTC；只运行 `docker build` 与 dependency-base build script，没有运行测试或启动 Compose：
  - 为遵守不调用 Compose 的要求，直接用 Docker build 输入映射配置：`GATEWAY_DOCKER_BUILD_NETWORK=none` 对应 `--network=none`；`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 与 dependency-base tag 对应 build args `USE_PRELOADED_DEPENDENCIES=1`、`DEPENDENCY_BASE_IMAGE=<lock-tag>`。默认构建对应 `USE_PRELOADED_DEPENDENCIES=0` 与 `rust:1.97.0-bookworm`。
  - 默认模式 backend/worker 构建通过，两个临时 tag 对应 image ID `sha256:f39037df173892a4c06a8daa0660d85798b3afe9dca58d005b4c6b3c2d468d47`。
  - dependency-base `gateway-backend-deps:lock-c668cef8e47e` 构建通过；完整输入摘要 `c668cef8e47ea2f75934f23a27b153662ac66ed546faf145ff903448bebea290`，构建时 image ID `sha256:a8d9d1ac7140bd2025080649a95146833f7ae8c2fb0e429a8f8e3856a0d9307d`。
  - 预置模式 backend/worker 在 Docker `--network=none` 下构建通过，两个临时 tag 对应 image ID `sha256:3d11bfe173de83df9cc8c239329bffa8a459568c88f07ee93dfbba5fef888764`。
  - Rust base image config digest 为 `sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1`，完整 DiffID 列表共 5 项。`--print-input` 摘要文件：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-input-summary.json`，SHA256 `19aea0121b5fce94db4751764622b98b9f4868d10a98d395029b4f9d13d7c289`。
  - 冒烟日志：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-build.log`，SHA256 `a4152a3d370bd926a54c844d3135e54a4289d6d0dc97acffb688f599772664bb`，exit code 0。四个 backend/worker smoke tag 与本次创建的 dependency-base tag 均已删除；两张 client e2e 镜像 ID 前后未变。
- CT201 冒烟前有三次未进入有效构建的命令组织错误（worktree 路径、临时 tag 大写、Docker build context 路径）；没有镜像被创建或改动，相关日志及 SHA256 列于“偏差、未决与清理”。修正后完整冒烟通过。
- CT201 冒烟只用于验证 Dockerfile 路径可构建，不作阶段取证。04 的离线构建、源码变化重建、镜像等价核对及权威 runner 结果见下方“容器与 runner 取证”。

## 容器与 runner 取证

取证 worktree 均为 clean、已提交的 `642f2d3ac7fdf76045f3e64434e882661a5bfafa`；source-check worktree 仅用于镜像构建。以下时间均为 UTC。完整命令输出和 DiffID 清单保存在列出的日志中。

### 1. Dependency-base 构建、传输与身份

- CT201（`heavy-dev-01`）从 642f2d3 clean worktree 运行 `build-backend-dependency-base.sh --save`，时间 `2026-10-31T00:04:01Z–00:04:41Z`，tag `gateway-backend-deps:lock-c668cef8e47e`，完整输入摘要 `c668cef8e47ea2f75934f23a27b153662ac66ed546faf145ff903448bebea290`。
- CT201 构建时 image ID/config digest：`sha256:a8d9d1ac7140bd2025080649a95146833f7ae8c2fb0e429a8f8e3856a0d9307d`。归档 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/backend-dependency-base-642f2d3.tar`，大小 `2292464640` bytes，SHA256 `ffab8d5b8676fbcfdb2ee0a28fba2cab4ce1a7db725ab0962b8e61e8da243f50`。
- CT04 收档后 SHA256 相同；load 后 config digest 与 CT201 相同，全部 20 个 DiffID 相同。CT04 的 store-specific inspect ID 为 `sha256:a944dca0b6e6a5f71c59082d2a3e6ddf93b88c1f929fc011a62dd31f1bd6e15e`，仅记录，不用于跨节点身份比较。输入摘要、config digest 与完整 DiffID 见两端 build/load 日志。
- 日志：CT201 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/ct201-dependency-base-build.log`，SHA256 `3d5e7aa452ddd9644bd096c8d5ebc61aab9a58b3cdd391ea2cc8b751f6dcb665`；输入摘要 JSON SHA256 `19aea0121b5fce94db4751764622b98b9f4868d10a98d395029b4f9d13d7c289`；CT04 `04-dependency-base-load.log`，SHA256 `02c425e201b33dd6fb73ecc0ad9b9c044e89710af21799f98b875f7478e649ef`。

### 2. CT04 预置模式离线构建

- 前置检查确认 S1c runner 已结束，整机无 runner、Dolt、容器或 8000 端口占用；日志 hostname `gw-dms-test-04`，候选 clean worktree `/home/dev/gdds-p6-backend-deps-evidence-642-04`，有 `legacy` 链接。检查日志 `04-runner-preflight.log` SHA256 `d65f76c5eff41a8bc0c56d18aad57bf82989bb0dc87d166511f64813ba11ae3c`。
- Compose 使用 `GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、`GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=gateway-backend-deps:lock-c668cef8e47e`；backend 与 worker 均构建成功。日志记录时间 `2026-10-31T00:06:37Z` 起，完整 Docker 输出及结束身份见 `04-candidate-offline-build.log`，SHA256 `00056902c34ccf7fca1c21b1d483ebdb4a3761ba9406d39288b34b122a7dfd06`。
- backend config digest `sha256:14ebd24291cd6b49e486022fafac62cd9c759ef0b6b1ebbfebb78e3cc84ddb5f`，worker config digest `sha256:4addcd9523ff4d228ff41e2db02f0a5635c3432b737a5007c9975f738d9601ea`；本节点 inspect metadata/image ID 见 `04-candidate-image-identities.log`（SHA256 `41aa339d10b0d3a8a350ee809b5df0125a2d00fec85cca88cc043c14e68a5940`）。

### 3. 本地源码变化后的离线重建

- 首次错误尝试使用 Docker context `.`，因 context 下找不到 `backend` 而在 Docker build 开始前失败；client 注释改动已恢复。日志 `04-source-change-offline-rebuilds.log`，SHA256 `7afdcf78e39510efdc9566126672ced57e3fc93f494266857fbad4517a6540d1`。按复核意见将整步重做，后续使用与生产接线相同的 Compose build。
- 重做在临时 worktree `/home/dev/gdds-p6-backend-deps-srcchk-642-04` 执行，项目名 `p6-deps-srcchk-642`，`network=none`、预置开关=1、dependency-base tag 同上。两次均 exit 0：
  - `repository_client/src` 的 Python 文件末尾临时追加注释，`00:13:13Z–00:13:44Z`；backend config digest `sha256:b0ae2ceb968496e3e6e2c7d88f096ab5091dcac8ba33547b46efc52a44eaf57a`，worker `sha256:c296526cffb17aae269c9cca88d7d239a44034d4fef0b6efbc84280a1e81081b`。
  - 恢复 client 改动后，在 Rust `.rs` 文件末尾临时追加注释，`00:13:47Z–00:14:18Z`；backend config digest `sha256:13a2a18e70b40633ab31f362f80a7d68f3fbecb8beb7ac26c6b327e4fe36120f`，worker `sha256:8b7965703beab3f4ace941847290774aa33e0df1fae4fa9e95e19e3eb7ee0885`。
- 两次日志均显示源码前 dependency-base 阶段 2/10–10/10 全部 `CACHED`；Rust 改动构建实际运行 maturin 并重新编译 `gateway-compute-python`，离线成功。构建日志 `04-srcchk-compose-builds.log`，SHA256 `4839ba0aff8676b318887ecfbd50ccec459e2fe82020aa2295fb457d27a92493`。
- 恢复后 client 与 Rust 源文件 SHA256 分别为 `1f0cbaff7058518f56044bc9064b3d83ec1d2582083b66ae52d3070c8eb0f241`、`f144f68b50e6785917b73b0b77eb4a3d5d3f9df083e6c8879a157e057c91143e`；临时 worktree clean 后删除，`p6-deps-srcchk-642` backend/worker tags 删除。preflight 日志 SHA256 `db9384c0bfdc080cd7cc829f81f748256adfa3b8b6f172efefeaf3082bae4e23`；清理日志 `04-srcchk-cleanup.log` SHA256 `19aeba22f9631b5f2e462cd952b3802b8439278b232661daf93b9b0f5edea7e0`。

### 4. 基线镜像与候选镜像等价比较

- CT201 从 `26738ae5c4b8b15676d9822b28a64fd3dad1b009` clean worktree 只构建 backend/worker，未运行测试或 Compose。构建时间 `00:15:35Z–00:16:55Z`，两 tag 的 config digest 均为 `sha256:b891550b1195a94894b9b6bb8f833a88a285bfe3c2e409e155a41d4abc469bdf`，共 15 个 DiffID。基线归档 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/backend-baseline-26738.tar`，大小 `397067264` bytes，SHA256 `dcccd0915dcbb56732db650ad6be7e9e4ba684cbc2765814627159652b726d3e`。CT04 收档 SHA 相同；load 后 config digest 与全部 15 个 DiffID 与 CT201 相同。inspect ID 不作跨节点比较。CT201 build/save 日志 SHA256 分别为 `bf46b46678572b253688f91c51fe1af82c353b1becdaa06ea7a57c0429d0db17`、`60d24febd7ce874161714fc7f139cd2806713c940d893b4d6c9669a794294858`；CT04 核验日志 `04-baseline-load-identity.log` SHA256 `d02ae556b6397a9355f431f0e10e59177e2995c5c7ff2ae70bbd4e4361098532`。
- 首次只读采集脚本在第一次 `docker run` 前因 `set -u` 失败：同一 `local` 声明中的 `snapshot="${OUT}/${key}..."` 在 `key` 初始化前展开。没有容器启动或镜像写入。失败日志 `04-image-equivalence-collection.log` SHA256 `e684a9dcfc1040872752f85aeead646143bd866ed4a57704b8b6ac68ea05c93b`。
- 修正变量初始化顺序后重跑。四次 `docker run --rm --network none --read-only` 只读采集均成功，无卷挂载；采集脚本不写镜像。重试日志 `04-image-equivalence-collection-retry.log` SHA256 `6b07011aee8cf3076ba3b15547e01c70df72f1ed71a93797b44a213990ad9522`。
- backend 与 worker 的 venv 包集合均为 25 个且名称/版本完全相同；系统 Python 均为 `pip==26.1.2`、`uv==0.11.28`。每组完整包清单见 `04-image-equivalence-final-comparison.log`（SHA256 `71c4ba6ecc58ae145340039715fd3275e5ff798f518414db7071acab126238fa`）。
- `/app` 下文件路径与内容摘要相同：SHA256 `5aabbe928953570debc64d3b6f43f76e28f0e2dd520d85d17cf6da6401563401`，466 文件、83 目录；26738 到 642 的 backend 源码、Rust、shared_kernel、repository_client、repository_contracts 与 backend 锁定输入 Git diff 为空。权限敏感摘要不同，但差异由构建机 umask 解释：CT201 umask `0002` 产出 466 个 `0664` 文件与 78 个 `0775` 目录；CT04 umask `0022` 产出 466 个 `0644` 文件与 83 个 `0755` 目录。路径和文件字节一致；root 运行时内容无差异。模式统计见 `04-image-source-mode-analysis.log`，SHA256 `5a7e466cbda143a6ada6e573ab9300633f8a82f88c57c34f7156c5cbb1f0e091`。
- backend/worker 的 image config 均相同：ENV 为 `PATH=/app/backend/.venv/bin:...`、`PYTHON_VERSION=3.14.6`、`PYTHON_SHA256=143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63`、`PYTHONPATH=/app/backend/src`；CMD 为 `python -m gateway_backend.bootstrap.http_server`；WORKDIR 为 `/app/backend`。bootstrap/build 参数未进入 runtime ENV。`docker run` 进程中动态 `HOSTNAME` 不同，属于 Docker 为容器生成的值，不是 image Config 差异。最终比较记录 `package_set_difference=none`、`runtime_config_difference=none`、`unexplained_difference=none`。

### 5. 04 六包权威 runner

- 启动前确认 runner/Dolt/容器/8000 均空闲；preflight 日志 SHA256 `d65f76c5eff41a8bc0c56d18aad57bf82989bb0dc87d166511f64813ba11ae3c`。root SSH 环境中仓库 selector 的 Rust 工具链通过显式 PATH、`RUSTUP_HOME=/root/.rustup`、`RUSTUP_TOOLCHAIN=1.97.0` 与 `CARGO_HOME=/root/.cargo` 解析；工具链确认日志 `04-rust-toolchain-path-confirmation.log` SHA256 `eadc00671080b1fdedafd60e102f8a701c541d87716fb9b38ebe6f0b37954f37`。
- 节点 `gw-dms-test-04`；worktree `/home/dev/gdds-p6-backend-deps-evidence-642-04`；起止 HEAD 均为 `642f2d3ac7fdf76045f3e64434e882661a5bfafa`，起止 worktree clean。时间 `2026-10-31T01:23:21Z–01:41:35Z`。环境：`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、backend preloaded=1、dependency-base tag `gateway-backend-deps:lock-c668cef8e47e`、`GATEWAY_DOCKER_BUILD_NETWORK=none`、`TMPDIR=/home/dev/gdds-test-tmp`；未设置 `GATEWAY_TEST_PACKAGES`（默认全六包），未设置 `GATEWAY_COMPOSE_GATE_PREBUILT`，proxy variables 均 unset。日志开头记录 hostname、HEAD、时间和环境。
- 六包均在当前 V 实际运行，无包沿用、无合格来源 V：rust manifest `7819702339c5e97d6b43969c04b206d82f6477811152affbe32f4ba317fffd2a` passed；shared_kernel `731ad04baa2855fdf12010c80918866e82c1fd9ac02a77b670e439b5a6eef607` passed；repository_contracts `f90ef879c998c1a22f2c9db451c21af11b03bdc48841518811cbcb383067f45d` passed；repository_client `796960d8be2a8a424e44614aaedcec66ef4eed45749cb33a89491dac0e3652cc` passed；backend `bc5c51b4313ab60bb1037e2b88cfd93c450fb65d5185198ebe87e41172a7c7fa` failed；repository_service `225f784335f8aa3a8d15abd4b81360f09a10d3ff1de485423d0b9af81265e69d` failed。manifest 与完整逐包日志见 `04-authoritative-runner-642.log`，SHA256 `f3c4bd57bc8f2a7edffb621e4c6d90a36c01861f6a9d72d6f4149b702dbd3927`。
- backend 并行批次 3069 passed；serial 批次 38 passed、3 failed：`test_ordered_history_compare_compose_journey`、`test_ordered_submit_bisect_control_cases`、`test_preview_worker_restart_takes_over_expired_running_operation`。失败 Compose 测试 helper 构造的环境字典没有传入 backend preloaded 与 dependency-base 变量，Compose 因而使用默认 `USE_PRELOADED_DEPENDENCIES=0` 并尝试 `curl https://astral.sh/...`；04 无公网连接，构建失败。此前第 2–3 步在同一节点的预置离线 Compose build 已成功。测试 helper 环境传递已由 E1 修复；新候选的 04 runner 待短复审后运行。
- repository_service 并行批次 1736 passed、1 skipped、7 failed；serial 批次 207 passed。复核 1 确认 7 个失败分三组：`test_build_script_defaults_docker_build_network_to_host` 继承 `GATEWAY_DOCKER_BUILD_NETWORK=none`；6 个 `test_run_tests_script.py` backend 选择用例的临时仓库缺少 `backend/Dockerfile.dependency-base`，导致 `fatal: Needed a single revision`，其中 Hypothesis storage 用例缺少 manifest event 是同一根因。对应 E2/E3 修订与 05 验证见下一节。
- runner pipeline exit 1（tee exit 0），按停止条件不继续验收、不重跑。日志末尾记录 runner exit code、结束 HEAD 和 worktree clean。post-runner 检查确认无 runner/Dolt/容器/8000 占用，Cargo target 与包专属 Hypothesis storage 已清理；日志 `04-post-runner-state.log` SHA256 `0ddc2d985837e333b40e4a185d14068647d17fa05705f199d10f020a8a337ab0`。

本任务不运行真实数据。642 候选的 runner exit 1；新候选尚无 04 runner 通过结果。

## 证据复核 1 定向修订与 05 验证

- 复核依据：main `1a009ed102` 的 `p6-backend-image-deps-evidence-check-1.md`。仅修订测试：
  - **E1**：`test_ordered_compare_compose.py` 与 `test_ordered_submit_bisect_compose.py` 的 `_compose_env` 改为复制 `os.environ` 后覆盖 Compose 项目名和临时密钥路径，保留离线预置构建参数。
  - **E2**：`test_run_tests_script.py::_runner_fixture` 清单加入 `backend/Dockerfile.dependency-base`。第一次运行继续暴露 synthetic repo 中 `rust-toolchain.toml` 也是无效 TOML 占位文本；依据 DC68 只修复并重跑这项测试一次，fixture 改为复制实际锁定 selector 文件。该补充仍只改测试夹具。
  - **E3**：默认网络测试通过 `monkeypatch.delenv("GATEWAY_DOCKER_BUILD_NETWORK", raising=False)` 与 runner 环境隔离。
- 提交：E1–E3 与 E2 新 Dockerfile 输入 `9600b339272cbb6d0f95811f7e992e73e05893e9`；fixture selector 补充 `861ab2467329c9784f1d64c70855d50c84dc36f6`。两次均为新提交，没有改写 `642f2d3ac7` 或已有 handoff 提交。
- 05 clean detached worktree：`/home/dev/gdds-p6-backend-image-deps-evidence-check1-retry-861ab246-05`，`HEAD=861ab2467329c9784f1d64c70855d50c84dc36f6`，有指向 `/home/dev/gateway-data-management-system/legacy` 的符号链接。hostname `gw-dms-test-05`。环境：`PATH=/home/dev/.cargo/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`、`UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`TMPDIR=/home/dev/gdds-test-tmp`；proxy unset。没有运行 Compose。
- 首次 `test_run_tests_script.py` 执行 `2026-10-31T03:05:55Z–03:06:01Z`，15 passed、6 failed，失败为占位 `rust-toolchain.toml` 的 TOML 解析错误。日志 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence-check1-9600-05.log`，SHA256 `54bf95dd44056ed4f058488d72a75107070a24b9cc9dec167aa6ca458aa4d1bd`。修正 selector fixture 后按 DC68 重跑一次，`03:06:36Z–03:06:42Z`，21 passed，exit 0；日志 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence-check1-retry-861ab246-05.log`，SHA256 `8b7bf06b0962af4faf4e4f889fa2287a34dc3997138cc0e02c19caa0cae26bbd`。
- 其余指定验证于 `2026-10-31T03:06:54Z–03:07:56Z` 完成，exit 0：`test_build_repository_service_image_script.py` 20 passed；`test_test_input_closure.py -m unit` 37 passed；两个 E1 文件 collect-only 为 3 tests collected；未执行这些 integration/serial 测试。shared_kernel、repository_contracts、repository_client、backend、repository_service 五包的 `ruff check .` 与 `mypy` 均通过（mypy 分别检查 34、15、26、492、200 个 source files）。日志 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence-check1-861ab246-validation.log`，SHA256 `1c4fcf0a37599695c11411a19f08d94208d4b638388780c3f8f5a2798b5fbd88`。
- E1–E3 代码修订相对 642 只涉及 `vnext/backend/tests/` 与 `vnext/repository_service/tests/`；包括 selector fixture 补充在内，测试代码变更为 4 个文件、39 insertions、17 deletions。`git diff --stat 642f2d3ac7..861ab24673` 为 5 files changed、123 insertions、50 deletions（含 handoff）；完整路径核对只含上述测试目录及 `docs/`。
- 05 验证后 worktree clean，未发现 runner、Dolt、容器或 8000 端口占用。失败初试、修复后重跑与剩余验证分别保留日志与 SHA256，不清理复核所需制品。

## 待同步文档

以下内容由负责治理文档的会话同步，本分支不改 `AGENTS.md` 与 `testing-conventions.md`：

- backend/worker 需要在测试节点离线构建时，先在 CT201 clean worktree 调用 `build-backend-dependency-base.sh --save <归档路径>`；通过获准局域网传输归档并在目标测试节点 `docker load`。记录来源提交、输入摘要、tag、inspect ID（仅参考）、config digest、完整 DiffID 列表、归档 SHA256、缓存来源类别/端点与时间，不记录凭据。跨节点核对只用 config digest + 全部 DiffID，不比较 inspect ID。
- runner 设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 与 `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`；保留 Compose backend/worker build，使候选镜像在 `GATEWAY_DOCKER_BUILD_NETWORK=none` 下实际构建。不要设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- backend 闭包的 Docker 输入包含所选 dependency-base 名称、本机 image ID、预置开关及其 build 环境指纹；切换任一输入要求 backend 重新运行。
- 替代 DC67 补充第 2 项的 backend/worker 整镜像预构建和传输：只预填充并传输锁定 dependency-base；04 在候选 clean worktree 中离线构建 backend/worker，再由权威 runner 运行 Compose 门禁。Repository Service 与 client e2e 继续沿用各自的预置依赖模式。

## 偏差、未决与清理

- 镜像/Docker 候选 642 与应用代码保持不变；当前测试修订候选为 861ab24673。05 定向测试与五包 ruff/mypy 通过。CT201 冒烟仅作调试记录；04 第 1–4 步沿用。642 上六包 runner exit 1 的三组测试问题已按 E1–E3 修订，新候选的权威 runner 需短复审通过后重跑。未运行真实数据。
- 第 3 步第一次直接 Docker build 的 context 错误、恢复与 Compose 重做均有记录；第 4 步第一次 collector 因 `set -u` 声明顺序在任何 `docker run` 前失败，修正后只读重试成功。两次失败及修正均未写入候选镜像。642 上第 5 步 runner 非零后先停止；本轮只做复核授权范围内的测试修订与 05 验证，04 新候选 runner 尚未启动。
- CT201 临时基线 worktree 已删除；CT04 `p6-backend-deps-srcchk-642` worktree 和临时 backend/worker tags 已删除，源码恢复且 SHA 已核对。CT201 与 CT04 上 dependency-base、基线和候选证据镜像/tag、两个传输归档及日志保留供复核。
- 保留 `/home/dev/gdds-p6-s1c-v-3008-04`、`/home/dev/gdds-p6-baseline-04`、S1c 镜像与 client e2e 镜像；没有全局 prune，也没有删除 client e2e 镜像。04 runner 后无容器、Dolt、runner 或 8000 端口占用。
- 临时构建内容清理记录：`04-srcchk-cleanup.log`（SHA256 `19aeba22f9631b5f2e462cd952b3802b8439278b232661daf93b9b0f5edea7e0`）、`ct201-baseline-worktree-cleanup.log`（SHA256 `427e933442233672371520905509d41546f5b1fa25ae71a08a5d176000db007e`）及 `04-post-runner-state.log`（SHA256 `0ddc2d985837e333b40e4a185d14068647d17fa05705f199d10f020a8a337ab0`）。
- 依赖基础镜像和基线归档分别保留在 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/backend-dependency-base-642f2d3.tar` 与 `/home/dev/gdds-p6-logs/p6-backend-image-deps-evidence/backend-baseline-26738.tar`；SHA256 与身份记录见 §5。复核完成前不删除这些证据文件或用于镜像比较的 tags。
- 主工作区未提交的治理文档修改未纳入本分支。新的 handoff commit 与审核 bundle 完成后交短复审；不推送、不打 tag。
