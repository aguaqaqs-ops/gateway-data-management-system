# Phase 6 backend dependency-base handoff

## 状态

- 来源基线：`26738ae5c4b8b15676d9822b28a64fd3dad1b009`
- 分支：`p6-backend-image-deps`
- 原代码候选 `98181d7d192138d85db746132f78700c0252bd1e` 保持不变；定向修订代码提交：`642f2d3ac7fdf76045f3e64434e882661a5bfafa`。
- 本 handoff 在定向修订代码提交之后单独提交；handoff 提交号由 Git 记录并在交付消息中给出。
- 审核：F1–F4 定向修订已复审前自检，等待复审会话。
- CT201 构建冒烟已完成，仅为调试，不作门禁证据。
- 04 取证：等待复审通过且 S1c 在 04 的 runner 结束后进行；按 §5 回填。
- 本任务不改应用代码、Contract、golden 或五个 Python/Rust 锁文件。
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
- 未运行权威全量 runner、04 Compose 门禁、真实数据旅程或镜像等价核对。CT201 冒烟只用于验证本次 Dockerfile 路径可构建，不作阶段取证。

## 容器与 runner 取证

待审核通过后在此记录：

1. 复审通过且 S1c 在 04 的 runner 结束后，在 CT201 clean worktree 构建 dependency-base；记录构建提交、tag、完整输入摘要、image ID、构建日志与时间；`docker save` 文件 SHA256、文件大小与局域网传输记录；04 `docker load` 后记录 config digest 与全部 DiffID。当前 CT201 调试冒烟构建的 dependency-base tag 已删除，不作为传输制品。
2. 04 以 `GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 和 dependency-base tag 构建 backend/worker 的日志、时间、image IDs。
3. 04 临时 worktree 对 `repository_client/src` 与 Rust 源码分别做无害改动后的 offline rebuild 日志、时间、镜像 ID；恢复与删除记录。
4. 新候选与基线 `26738ae5c4` 镜像的已安装包名/版本集合、应用源码树摘要、runtime ENV 与 CMD 比较，以及全部差异解释。
5. 04 权威 runner 的环境（含 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`，backend preloaded=1，`GATEWAY_COMPOSE_GATE_PREBUILT` 未设置）、六包逐项运行/沿用判断、来源 V/日志、总 exit code 与镜像身份。
6. 本任务不运行真实数据旅程。镜像等价核对若发现无法解释的构建产物之外差异，停止并交 owner 决定是否补 t1 冒烟。

## 待同步文档

以下内容由负责治理文档的会话同步，本分支不改 `AGENTS.md` 与 `testing-conventions.md`：

- backend/worker 需要在测试节点离线构建时，先在 CT201 clean worktree 调用 `build-backend-dependency-base.sh --save <归档路径>`；通过获准局域网传输归档并在目标测试节点 `docker load`。记录来源提交、输入摘要、tag、inspect ID（仅参考）、config digest、完整 DiffID 列表、归档 SHA256、缓存来源类别/端点与时间，不记录凭据。跨节点核对只用 config digest + 全部 DiffID，不比较 inspect ID。
- runner 设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 与 `GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE=<lock-tag>`；保留 Compose backend/worker build，使候选镜像在 `GATEWAY_DOCKER_BUILD_NETWORK=none` 下实际构建。不要设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
- backend 闭包的 Docker 输入包含所选 dependency-base 名称、本机 image ID、预置开关及其 build 环境指纹；切换任一输入要求 backend 重新运行。
- 替代 DC67 补充第 2 项的 backend/worker 整镜像预构建和传输：只预填充并传输锁定 dependency-base；04 在候选 clean worktree 中离线构建 backend/worker，再由权威 runner 运行 Compose 门禁。Repository Service 与 client e2e 继续沿用各自的预置依赖模式。

## 偏差、未决与清理

- 05 定向 focused 测试、闭包测试及五包 ruff/mypy 已通过；CT201 默认与预置离线构建冒烟已通过。04 镜像、source-change 离线重建、镜像等价与权威 runner 取证待复审通过且 S1c 在 04 的 runner 结束后进行。
- CT201 完整冒烟日志中的临时 backend/worker tag 与 dependency-base tag 均已删除；client e2e 镜像未删除，inspect ID 前后相同。输入摘要 JSON 留在 `/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-input-summary.json` 供复审查阅。
- CT201 冒烟前的三次无构建命令错误日志：
  - 路径误写：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-setup-error.log`，SHA256 `825df9360e33af011381a7dc5bf1d4a1efc303e3bb923433d04a0150a8c1dd4e`。
  - 临时 tag 含大写字母：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-tag-error.log`，SHA256 `dbcabfdf3131e3b14816a5f7c215abb6b71a724d6eb25486a0af41e4fb4c68e2`。
  - Docker context 路径错误：`/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-context-error.log`，SHA256 `c5be31f99d7c38cc033bb95fd809e3f60da0326b93a23ad087048088d51bd6b1`。
- CT201 与 CT05 的代码传输临时 bundle 完成最终审核 bundle 后删除；CT05 clean worktree `/home/dev/gdds-p6-backend-image-deps-test` 当前保持在 `642f2d3`，不清理以便复审复用。
- 主工作区未提交的治理文档修改未纳入本分支。
- 04 后续新建的归档、镜像 tag 与临时 worktree 在证据完成后记录和清理；最终传输用的 dependency-base tag 按 owner 的节点预填充安排处理。
