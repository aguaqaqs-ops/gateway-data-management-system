# Phase 6 S1c 取证复核 1（04 镜像就绪预检停止）

状态：**停止原因已查明，不是镜像差异。** 第 3 节口径已由 owner 确认，记为 DC67 澄清（2026-10-30）；04 预检通过，04 权威 runner 可以启动。05 t1 需要先做一处测量工具修正（第 4 节）。ct108 2× t4 Submit 仍等待基准续跑工具。

## 1. 复核对象

- 代码候选 V = `3008d578cf2ee0eaf9236f01e33b5008d65ef36c`（复审 1 已通过）；handoff 提交 H = `9e2c0200e5722f84272a7578d24eb537c78aeb32`（分支 `p6-s1c-impl`，本地）。
- 停止点：开发节点构建的 backend/worker 镜像经 `docker save`/`docker load` 传到 04 后，04 的 `docker image inspect` ID（`sha256:0c61307c…`）不等于开发节点的 ID（`sha256:b1f3c7b6…`）。
- 依据：开发节点 `/home/dev/gdds-p6-logs/s1c/04-image-id-comparison.log`（SHA256 `0d01c98e…`，已核对）。04 当前镜像清单由审核者在 04 上重新列出。

## 2. 停止原因

- “04 inspect ID 与开发节点一致”这一要求出自审核者给出的取证提示词，不在 DC67 正文中。DC67 补充第 2 项只要求记录 image ID。
- 两端的 image store 不同：
  - 开发节点：Docker 26.1.5，`overlay2`（classic store），inspect ID 就是镜像 config 的 digest。
  - 04：Docker 29.9.1，containerd `overlayfs` snapshotter，inspect ID 是镜像 manifest 的 digest。`docker load` 时 manifest 在本机重新生成，ID 随之不同。AGENTS 已记载：在 containerd store 下，即使同一棵树连续构建，image ID 也不相同（DC34）。
- 内容身份一致：
  - 两端镜像 config digest 均为 `sha256:b1f3c7b619aeb2d24a086ba7ddd6a5f5a64c49940da3292853b0cfc423512049`，即开发节点的 inspect ID；
  - 15 个 RootFS DiffID 逐项相同；
  - Created 时间戳相同。
- layer 路径聚合摘要不同，原因是两种 store 导出时 layer blob 的编码与命名不同。DiffID 是解压后层内容的摘要，已经相同，因此这一差异不影响身份判断。
- 结论：实施者按提示词停下是正确的。提示词口径有误，镜像本身没有问题。

## 3. 身份口径（owner 已确认，见 DC67 澄清）

跨节点传输的镜像以“config digest + 全部 RootFS DiffID”判定身份，不比较 `docker image inspect` 的 ID。

- 取值方式：
  - 开发节点（classic store）：config digest 等于 inspect ID；
  - containerd store 节点：在本机 `docker save` 后，从归档 `manifest.json` 的 `Config` 读取 config digest；DiffID 用 `docker image inspect --format '{{json .RootFS.Layers}}'` 读取。
- 记录内容：两端的 config digest、DiffID 列表及其是否一致；两端 inspect ID 照常记录，仅供参考。
- 适用范围：
  - S1c 的 backend/worker 预构建镜像（04、05、ct108）；
  - backend 镜像依赖层调整中的 dependency-base 传输；
  - 其后所有 `docker save`/`docker load` 的预填充。
- 不变项：同一节点内的闭包与 carried 判定继续使用本机 image ID（同一 worktree、同一 store）。

按此口径，04 已加载的 `s1c-v-3008-backend:latest` 与 `s1c-v-3008-worker:latest` 与开发节点构建结果一致。Repository Service 与 client e2e 镜像的标签核对已通过。04 runner 的前提已满足。

## 4. 05 t1 的构建问题（工具缺陷）

- V 的 `real_dump_journey.py` 在非续跑模式下（未传 `--from-step`），会先清除调用方设置的 `GATEWAY_COMPOSE_GATE_PREBUILT`，再调用 `build_compose_stack_images` 构建 backend/worker（V 内该文件约 3731–3757 行）。
- 05 没有外网。V 的 backend Dockerfile 在安装依赖之前复制 `repository_client`，而 S1c 改动了 `repository_client`，所以依赖层必须重建。按 DC67，取证不得经代理。因此 V 的 t1 旅程在 05 上必然构建失败。
- 修正属于 DC66 第 5 项“测量工具修正的常设授权”的范围：
  - 调用方已设置 `GATEWAY_COMPOSE_GATE_PREBUILT=1` 时，旅程不构建 backend/worker，改为核对所用 project 的 backend/worker 镜像已存在；
  - 旅程记录中写入这两个镜像的本机 ID 与 config digest；
  - Repository Service 镜像的现有检查不变。
- 落点：在 V 之上新增一个只改 `vnext/backend/benchmarks/` 与其测试的工具提交 T。
  - 05 t1 在 T 的 clean worktree 中运行，使用加载后的预构建镜像。
  - handoff 记录 `V..T` 的 `diff --stat`，即 DC66 所说的“取证提交只含工具改动”。
  - T 不并入 S1c 代码候选，04 runner 仍在 V 上运行。
- ct108 需要同样的修正：基准正式测量在 `p6-s1c-exit` 上进行，那里同样无法离线构建 backend 镜像。基准会话应把同一修正并入 `p6-baseline`，ct108 的 2× t4 Submit 续跑与正式测量都使用传入的预构建镜像。续跑路径（`--from-step`）本来就设置 prebuilt，但也要能核对镜像来自同一产品提交。

## 5. 结论

| 项 | 判定 |
|---|---|
| 04 六包权威 runner（V） | 可以启动；环境为 `UV_OFFLINE=1`、`CARGO_NET_OFFLINE=true`、`GATEWAY_COMPOSE_GATE_PREBUILT=1`、`GATEWAY_COMPOSE_GATE_PROJECT_NAME=s1c-v-3008` |
| 05 t1 冒烟 | 先完成第 4 节的工具提交 T（05 focused 测试与五包静态检查通过），再加载预构建镜像，按第 3 节口径核对后运行；可与 04 runner 并行 |
| ct108 2× t4 Submit | 继续等待基准续跑工具（DC66 第 3 项），并需要第 4 节的同类修正 |
| 停止条件 | 不变：任一步缓存缺失或身份不符即停止，不经代理 |
