# Phase 6 backend 镜像依赖层调整：独立审核（代码候选）

状态：**定向修订。** F1、F2 会使默认构建与预置模式构建都失败，须修正后复审。复审通过前不进入 04 取证。

## 1. 审核对象

- 分支 `p6-backend-image-deps`，基线 `26738ae5c4`。
- 代码候选 `98181d7d192138d85db746132f78700c0252bd1e`，handoff 提交 `5bb0a92fdea6d712251828b219680db5b57df563`。
- 审核 bundle SHA256 `a4df7194…`（已核对，`git bundle verify` 通过）。
- 改动 8 个文件：`backend/Dockerfile`、新增 `backend/Dockerfile.dependency-base`、`scripts/build-backend-dependency-base.sh`、`deploy/compose.yaml`、`scripts/test_input_closure.py`，以及 3 个测试文件。
- 方法：
  - 阅读全部 diff。
  - 在 `ct108-gw-dms-05` 上用 uv `0.11.28` 与 BuildKit 做最小探针。探针离线、在 `TMPDIR` 下的临时目录运行，用后删除，不涉及项目测试。
  - 没有在开发主机运行任何内容。

## 2. 发现

### F1（高）runtime 阶段的 uv 缓存以只读方式挂载，`uv sync` 必然失败

- 位置：`vnext/backend/Dockerfile:69`，`RUN --mount=type=bind,from=dependency-base,source=/root/.cache/uv,target=/root/.cache/uv`。
- BuildKit 的 `type=bind` 默认只读。uv 启动时要在缓存目录创建锁文件，只读缓存会直接报错。
- 证据（05）：
  - 最小 Dockerfile 中 `RUN --mount=type=bind,from=a,...` 写入挂载点，报 `Read-only file system`。
  - 把 uv 缓存以 `:ro` 挂进 `python:3.14.6-slim-bookworm` 后执行 `uv pip install`，报 `error: Could not acquire lock … Read-only file system (os error 30) at path "/root/.cache/uv/.tmp…"`，exit 2。同一缓存以可写方式挂载时成功。
- 影响：这一步不分模式都会执行，默认（非预置）构建和预置构建都在 runtime 第一步失败，backend/worker 镜像无法构建。
- 修正：给该挂载加 `rw`（写入在步骤结束后丢弃，不进入镜像层）。`from=builder` 的 wheel 挂载只读即可。

### F2（高）dependency-base 阶段在缺少本地包源码时使用 `uv sync --locked`

- 位置：`vnext/backend/Dockerfile.dependency-base:46` 与 `vnext/backend/Dockerfile:27`（非预置分支），都是 `uv sync --locked --no-install-local --no-install-project`。
- `--locked` 要先校验锁文件与项目元数据是否一致，为此需要读取本地路径依赖的元数据。此时 `/build/rust/gateway-compute-python` 只有 `Cargo.toml`，`shared_kernel`、`repository_client`、`repository_contracts` 也还没复制。
- 证据（05，按 Dockerfile 的实际目录布局复制 backend 锁输入与 Rust 清单，`UV_OFFLINE=1`，`--dry-run`）：
  - `uv sync --locked …` 报错：`…/build/rust/gateway-compute-python does not appear to be a Python project, as neither pyproject.toml nor setup.py are present`；
  - `uv sync --frozen …` 正常列出待安装的第三方依赖。
- 影响：dependency-base 镜像无法构建；默认构建在第一个阶段失败。
- 修正：这两处改回 `--frozen`（原 Dockerfile 即如此）。锁文件一致性由以下检查覆盖：
  - builder 阶段复制完整源码后的 `UV_OFFLINE=1 uv sync --locked`（第 50 行，保留）；
  - runner 的 `uv-consume.sh` 锁检查；
  - 预置模式下对各锁文件 SHA256 的核对。

### F3（低）dependency-base 的输入摘要含本机基础镜像 ID，跨节点重算会得到不同 tag

- 位置：`vnext/scripts/build-backend-dependency-base.sh:61` 与 `:112`（`base_image_id` 进入 canonical 输入，tag 取其摘要前 12 位）。
- 开发节点是 classic store，ID 为 config digest；测试节点是 containerd store，ID 为 manifest digest。同一个 `rust:1.97.0-bookworm` 在两端的 ID 不同，所以在节点上运行 `--print-input` 得到的 tag 与开发节点构建的 tag 不同。
- 预置构建本身不受影响：Dockerfile 只核对镜像内摘要文件与锁文件，不核对基础镜像 ID。问题在于按 handoff 的流程，有人在节点上重算 tag 去核对时会得到“不符”。
- 修正：取两种方式之一，并在脚本 usage 与 handoff 中写明：
  - 基础镜像身份改记 config digest，取值方式见 [S1c 取证复核 1](p6-s1c-evidence-check-1.md) §3；
  - 或者 `base_image_id` 只作为 label 与 `inputs.json` 中的记录，不进入决定 tag 的摘要，节点上的身份核对一律按 config digest + DiffID。

### F4（低，取证时核实）预置分支用正在运行的 uv 覆盖自身

- 位置：`vnext/backend/Dockerfile:67–71`。先把 dependency-base 的 uv 复制为 `/usr/local/bin/uv`，预置分支再用它执行 `uv pip install --system "uv==…"`，安装目标正是 `/usr/local/bin/uv`。
- 自我覆盖在 Linux 上是否报 `Text file busy`，取决于 uv 写入脚本的方式。本次审核没有可离线获取的 uv wheel，未能验证。
- 建议：
  - 不要 COPY 到 `/usr/local/bin/uv`，改为把 dependency-base 的 uv 以 bind 挂到别的路径（例如 `/opt/uv-bootstrap/uv`），只在预置分支用它安装 `uv==${UV_VERSION}`；
  - 三个分支安装完成后，runtime 内的 uv 都来自 pip 安装，与基线镜像一致，便于镜像等价核对；
  - 若保留现写法，须在第 3 节的 CT201 构建冒烟中确认通过。

## 3. 其余核对（无问题）

- 本地包的 build backend 为 `uv_build>=0.11.28,<0.12.0`。05 探针在空缓存、离线条件下，用 uv 内置后端构建 editable `shared_kernel` 成功，不需要额外下载。
- `cargo fetch --locked` 使用占位源码：各 crate 显式声明的 target 路径（`src/main.rs`、`src/lib.rs`）都已占位，没有显式 `build`、bench 或 example 路径。
- builder 阶段的 `maturin build --locked` 配合 `CARGO_NET_OFFLINE=true`，使用 dependency-base 中 `CARGO_HOME` 已 fetch 的 crates。
- 闭包：
  - backend 记录所选 dependency-base 名称、本机 image ID 与预置开关；
  - schema 升至 10；
  - 新测试覆盖 image ID 变化与开关变化两种“运行”判定；
  - 新 Dockerfile 被列为 Docker 输入；没有新增 ignore 文件。
- Compose 的默认值（`rust:1.97.0-bookworm`，开关 `0`）不改变生产 build 参数的语义；`UV_BOOTSTRAP*` 仍不进入 runtime ENV。
- 静态合同测试只检查文本，没能发现 F1、F2。这两个问题只有实际构建才会暴露。

## 4. 修订要求

1. 修正 F1、F2；按建议处理 F3、F4，或在 handoff 说明不采纳的理由。
2. 合同测试补充两条断言：
   - uv 缓存的 bind 挂载带 `rw`；
   - 复制本地源码之前的 `uv sync` 使用 `--frozen`。
3. **CT201 构建冒烟**（调试，不作证据；DC67 补充第 2 项允许在开发节点只构建、不运行测试）：
   - 默认模式完整构建 backend/worker 一次；
   - 用 `build-backend-dependency-base.sh` 构建 dependency-base；
   - 以 `GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 构建 backend/worker 一次。
   - 记录日志、SHA256 与起止时间，用后删除临时 tag（不得删除 client e2e 镜像）。
   - 冒烟通过后再交复审。
4. 05 上重跑 focused 测试与五包静态检查。
5. 04 取证保持原计划。04 当前由 S1c 的权威 runner 使用，同节点整机单飞，需等 S1c 在 04 的运行结束。
6. 传输 dependency-base 后，按 config digest + DiffID 核对身份，不比较 inspect ID（见 [S1c 取证复核 1](p6-s1c-evidence-check-1.md) §3）。
