# Phase 6 backend 镜像依赖层调整：独立复审 1（代码候选）

状态：**代码通过。** 可以进入 DC64 第 1 项的 04 取证，按 handoff §5 执行；取证结果由同一审核会话复核。04 取证须等 S1c 在 04 的权威 runner 结束（同节点整机单飞）。

## 1. 复审对象

- 首次审核：[p6-backend-image-deps-independent-review.md](p6-backend-image-deps-independent-review.md)（F1–F4，定向修订）。
- 分支 `p6-backend-image-deps`（本地），基线 `26738ae5c4`。
- 原代码候选 `98181d7d19` 未改写。定向修订代码提交 `642f2d3ac7fdf76045f3e64434e882661a5bfafa`，handoff 提交 `cc7f3a633f`、`4e01f97bd8`（两者只改 handoff）。
- 审核 bundle `/home/dev/gdds-p6-backend-image-deps-independent-review.bundle`，SHA256 `d6836443…`，`git bundle verify` 通过，ref 为 `4e01f97bd8`。
- 方法：
  - 阅读 `98181d7d19..642f2d3ac7` 的代码与测试 diff；
  - 核对 05 focused 日志与 CT201 构建冒烟日志；
  - 在 05 上补做跨 store 的基础镜像身份核对（只读，未运行测试）。

## 2. 逐项核对

| Finding | 修订 | 结论 |
|---|---|---|
| F1 runtime uv 缓存只读挂载 | `Dockerfile` runtime 的 `/root/.cache/uv` bind 加 `rw`；wheel bind 显式 `ro`；合同测试断言两者 | 已关闭。CT201 默认模式与 `network=none` 预置模式的 backend/worker 构建均通过 |
| F2 缺源码时 `--locked` | `Dockerfile.dependency-base` 与 `Dockerfile` 非预置分支改为 `uv sync --frozen --no-install-local --no-install-project`；builder 复制源码后的 `UV_OFFLINE=1 uv sync --locked` 保留；合同测试断言源码前不出现 `--locked` | 已关闭。CT201 dependency-base 构建通过 |
| F3 tag 含本机 inspect ID | `tag_inputs` 改为锁文件摘要、版本、基础镜像引用、config digest 与全部 RootFS DiffID（经 `docker image save` 读取 config blob）；inspect ID 只进 `inputs.json` 的 `base_image_id` 与 label `gateway.backend.base-image-inspect-id`；新增测试覆盖“inspect ID 不同、tag 相同”和“内容不同、tag 不同” | 已关闭。见第 3 节的跨 store 核对 |
| F4 uv 自我覆盖 | 删除 `COPY --from=dependency-base … /usr/local/bin/uv`；预置分支把 dependency-base 的 uv 只读挂到 `/tmp/dependency-base-uv`，用它以 pip 方式安装 `uv==0.11.28`；三个分支的 runtime uv 都来自 pip wheel | 已关闭。CT201 预置构建通过 |

## 3. 跨 store 核对（审核者补做）

- `rust:1.97.0-bookworm` 在 05（containerd store）上：
  - config digest `sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1`，与 CT201 冒烟记录的 config digest 相同；
  - inspect ID `sha256:99709b78…`，与 CT201 不同。
- 因此在节点上运行 `--print-input` 会得到与 CT201 相同的 tag，F3 的目的达到。
- 05 上对该镜像执行 `docker image save` 约 13 s，正常完成；脚本在 containerd 节点上也可取得基础镜像身份。

## 4. 复跑与日志核对

- 05 focused 日志 `/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-05-focused.log`，SHA256 `0bfe5eb5…`（已核对）：
  - HEAD `642f2d3ac7`；
  - Dockerfile 合同与脚本测试 11 passed，闭包测试 37 passed；
  - 五包 ruff/mypy 通过；
  - `runner_exit=0`。
- CT201 冒烟日志 `/home/dev/gdds-p6-logs/p6-backend-image-deps-642f2d3-ct201-build.log`，SHA256 `a4152a3d…`（已核对）：
  - HEAD `642f2d3ac7`，hostname `heavy-dev-01`；
  - 依次完成默认构建、dependency-base 构建（`gateway-backend-deps:lock-c668cef8e47e`）、`network=none` 预置构建；
  - 临时 tag 已删除，`build_smoke_exit=0`。
  - 冒烟用 `docker build` 直接映射 Compose 的 build 参数，没有启动 Compose，符合“只构建”的要求。
- 本复审没有在开发主机上运行任何内容。

## 5. 观察（不阻塞）

- O1：`load_base_image_identity` 在命令替换的子 shell 中执行，`TMP_BASE_IMAGE_ARCHIVE` 赋值不会传回父 shell。若 `docker image save` 或其后的 Python 解析失败，这个临时归档（rust 基础镜像约 1.5 GB）会留在 `$TMPDIR` 或 `/tmp`。成功路径会自行删除。建议下次改动该脚本时，改为在父 shell 里创建临时文件再传入函数；本阶段不要求修改。
- O2：handoff §5 第 3 步要在 04 临时 worktree 中做“无害源码改动后的离线重建”。该 worktree 会因此变 dirty，只能用于构建验证，不得用于 runner 或闭包；用后删除。权威 runner 须在另一个 clean 的候选 worktree 中运行。

## 6. 结论

代码通过，进入 04 取证。取证要求见 handoff §5 与 DC67 澄清：

1. dependency-base 在 CT201 从候选 clean worktree 构建并 `--save`，经局域网传到 04 后 `docker load`，按 config digest + 全部 DiffID 核对身份。
2. 04 以 `GATEWAY_DOCKER_BUILD_NETWORK=none`、`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1` 与该 tag 构建 backend/worker。
3. 在 04 临时 worktree 中分别改动 `repository_client/src` 与 Rust 源码后离线重建。
4. 与基线 `26738ae5c4` 的镜像比较已安装包、应用源码树、runtime ENV 与 CMD。
5. 04 六包权威 runner 设置 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、预置开关与 tag，不设置 `GATEWAY_COMPOSE_GATE_PREBUILT`。
