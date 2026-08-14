# P2-R9-S2 Step E container gate provenance

状态：Executed

候选 SHA（`validated_code_sha` / `container_validated_code_sha`）：
`e78b564a112b2a040740e3e07d7e6f04329d06e9`

本文件在 build-context digest 之外（不位于 `vnext/repository_service/**` 或
`vnext/repository_contracts/**`）。本提交的 SHA 是 `provenance_documentation_sha`，
不得回填进候选代码或镜像 label。

## Build path

本地因公共网络受限，不在本机重建 production 镜像。远端 `10.10.60.4`（`tmpuser`）用
retained cache `http://172.17.0.1:18080`（HTTP 200）构建后，镜像 tar 拉回本机执行
Compose 门禁。未复用 `3616ef0` 或其他祖先镜像关闭门禁。

```text
remote worktree: /home/tmpuser/gateway-gate-e78b564a112b
remote HEAD: e78b564a112b2a040740e3e07d7e6f04329d06e9
local HEAD:  e78b564a112b2a040740e3e07d7e6f04329d06e9
worktree_clean: yes
AUDIT_BASE ancestor: 3616ef0d9707e6ec165376d175003ca80843ab1a
build_input_revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
source_tree_sha256: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2
image: gateway-repository-service:e78b564
image_id: sha256:87e4e908bfa63370033256b380c6582c39fb6888749131633d5e856ae649a007
image_label org.opencontainers.image.revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
image_label gateway.p2r1.source-tree-sha256: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
image_matches_build_context: true
```

构建命令：远端 `vnext/scripts/build-repository-service-image.sh`，tag
`gateway-repository-service:e78b564`，随后 `docker save | gzip` 拉回并
`docker load`，再 tag 为 `gateway-repository-service:local`。
`ensure_repository_service_image()` 核对 label 后未再本机 rebuild。

## Compose wiring

`docker compose -f vnext/deploy/compose.yaml --profile p2-r2 config` 渲染结果中无
`artifact-broker`、broker socket、`SCM_RIGHTS`、`pidfd`、tombstone budget、helper、
`GATEWAY_REPOSITORY_ARTIFACT_BROKER` 或额外 UID/GID 接线。`repository-service` 保留
production env、bearer secret、`repository-service-data` volume 与 `/readyz` healthcheck。

## Gates

1. Fresh volume import/restart/replay：
   `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay`
   **PASSED (27.44s)**。本机执行，使用拉回的 `e78b564` 镜像。

2. Directed probe（TTL=1s / cleanup interval=1s，project `gateway-p2r9-e-1c12969750e6`）：
   - 容器 euid/egid/user：`100 / 101 / gateway`
   - `/readyz`：`{"status": "ready"}`（import 后、legacy restart 后均 ready）
   - 目录 owner/mode（gateway 100:101）：
     - `/var/lib/gateway/repository` `0750`
     - `.../artifacts` `0750`
     - `.../staging` `0755`
     - `.../control` `0755`
     - `.../service-state` `0755`
   - upload/import SUCCEEDED 后 ready 对象被 package cleanup 删除；tombstone 计数 `0`
   - restart 后 replay 同一 `operation_id`，status `SUCCEEDED`
   - 运行时 unix 路径无 artifact-broker socket；无 broker/helper 进程
   - v15 volume（`PRAGMA user_version = 15`）注入 legal/FIFO/symlink/ambiguous leftover
     与 receipt 行：legal 与后续 candidate leftover 收敛；FIFO、symlink、ambiguous 保留；
     receipt generation 被 clear；restart 后 poison 仍在、legal 仍 absent
   - `compose down -v` 后该 project 的 container/network/volume 为空

3. 停止后残留：无本门禁的 container/volume/network，无 live `artifact-broker` 进程或
   unix socket。主机 `/tmp/r21-dual-uid.*` 是 2026-08-13 的旧 pytest 目录，不属于本
   HEAD 的 Compose 运行。

未复用 `3616ef0d9707e6ec165376d175003ca80843ab1a` 镜像。

## Docker record

```text
Current HEAD: e78b564a112b2a040740e3e07d7e6f04329d06e9
Container rebuild required: yes
Reason: Step E最终候选；相对AUDIT_BASE的Dockerfile/entrypoint/Compose/UID/layout及production runtime边界已改变
Last verified image revision: e78b564a112b2a040740e3e07d7e6f04329d06e9
Last verified source-tree/image id: sha256:2cc377e74be2ab342ee09028ce54ff77a4690c5a5f12ce633959bfe6643172a2 / sha256:87e4e908bfa63370033256b380c6582c39fb6888749131633d5e856ae649a007
Container gate for current HEAD: passed
Deferred gates/nodeids: none
Required execution point: Step E最终候选（当前HEAD）
S3 ready: yes
```
