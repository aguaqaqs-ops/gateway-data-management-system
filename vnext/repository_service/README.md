# Gateway vNext Repository Service

当前状态：P2-R5 functional exit complete（`validated_code_sha`:
`7091c2c4836eebdc4cbee4424f20297b2d2f88bb`）。Service shell、create/upload/import 与
commit-pinned read 已激活；container/Compose/W1/W2/formal retest 延期至 P2-R6；
`production_retest_required=yes`，`phase_2_complete=no`。完整 handoff 见
[P2-R5-S7 final handoff](../../docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md#p2-r5-s7-final-handoff--2026-08-12)。

## 已激活基础能力

- FastAPI composition root 与 production lifespan；
- production bearer auth（secret file 优先，fail closed）；
- `/healthz` 与 `/readyz`；
- control DB migration/open/close 与 durable-root lock；
- selected provider（Candidate A offline CLI）capability check 与 subprocess shutdown/reap。

## 已激活 public V1 routes

公开 wire 语义由 [Repository Service Contract](../../docs/backend-vnext/refactoring/formal/contracts/repository-service.md) 拥有。当前已注册 7 条 V1 业务 route（另有`/healthz`与`/readyz`）：

```text
POST /v1/repositories
POST /v1/repositories/{repository_id}/artifacts
POST /v1/repositories/{repository_id}/versioned/imports
GET  /v1/repositories/{repository_id}/operations/{operation_id}
GET  /v1/repositories/{repository_id}/versioned/refs/{ref_name}
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog
GET  /v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows?table_name=...
```

说明：

- `ref_name` 仅接受 literal `main`；
- catalog/rows 绑定 caller 指定的 immutable `CommitId`，不跟随 branch head；
- rows 成功响应为 raw Arrow IPC stream（`application/vnd.apache.arrow.stream`）；
- 不承诺 row/batch ordering；
- `unknown_type_policy` 为 frozen contract（省略等价 `REJECT`）；
- Remote Repository Client 位于独立 client distribution，不是 Service 内嵌库；
- contract-owned fixture consumer 仅为 contract test boundary，不是 production/P3 consumer。

## 明确未激活 / 限制

以下能力当前**未**激活或不在 P2-R5 scope：

- Current store 与 `/current/` routes；
- LATEST / branch-following read；
- public ref/table/schema CAS；
- diff、export、history API；
- public delete、repair、backup；
- generic ACL / multitenancy；
- multi-node writer；
- Candidate B production activation（默认禁用）；
- P3 Submit / Archive / History capability；
- Phase 2 production completion 声明。

## Container 与 provenance 状态

下文 P2-R2/R4 的 build/Compose 操作说明保留为**历史 gate 操作参考**，不代表当前 R5
source 已有匹配的 production image evidence。

- 当前 R5 validated source **没有**与 `7091c2c...` 对应的 container-validated image；
- `container_validated_code_sha`（`901a13b9...`）来自 R4 handoff，对当前 source 为
  historical/superseded；
- container gate、Compose e2e、W1/W2 workload、P2-R1 v8 formal retest 延期至 P2-R6；
- `production_retest_required=yes`；不得用旧 image 证明当前 source；
- R6 须从含 S7 handoff 文档的 source tree 重新 build、传输并验证 image provenance。

当前延期 container nodeid：

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
```

R6 计划新增（R5 未收集）：

```text
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
```

## 容器启动（P2-R2 `p2-r2` profile）

Repository Service HTTP shell 通过 Compose `p2-r2` profile 启动。镜像默认 CMD 为：

```bash
python -m uvicorn gateway_repository_service.app:create_app \
  --factory --host 0.0.0.0 --port 8000
```

容器以非 root 用户 `gateway` 运行；不发布 host port，仅在 Compose internal network
内可见。production profile 要求 bearer secret file：

```bash
export GATEWAY_P2R2_BEARER_TOKEN_FILE=/path/to/token   # chmod 0400
docker compose -f vnext/deploy/compose.yaml --profile p2-r2 config
docker compose -f vnext/deploy/compose.yaml --profile p2-r2 up -d repository-service
```

Compose 将 secret 只读挂载到 `/run/secrets/repository-bearer-token`，并使用独立 named
volume `repository-service-data` 挂载到 `/var/lib/gateway/repository`。healthcheck 使用
镜像内 Python 标准库访问 `/readyz`。

Docker Compose 的 file-backed secret 在 Linux 上是 bind mount；`uid`、`gid` 和 `mode`
不会替宿主机文件改变 owner。宿主机 token 文件必须由镜像内 `gateway` UID/GID 所有并
保持不可写，否则 non-root service 会收到 `bearer token file is unavailable`。构建镜像后
可用以下命令取得 UID/GID，再以 root provision 临时或生产 secret：

```bash
IMAGE=$(docker compose -f vnext/deploy/compose.yaml --profile p2-r2 \
  images -q repository-service)
test -n "$IMAGE"
GATEWAY_UID=$(docker run --rm --entrypoint id "$IMAGE" -u gateway)
GATEWAY_GID=$(docker run --rm --entrypoint id "$IMAGE" -g gateway)
sudo chown "$GATEWAY_UID:$GATEWAY_GID" /path/to/token
sudo chmod 0400 /path/to/token
```

生产 secret driver 必须提供等价的 non-root readable、read-only mount；不得通过把 token
设为 world-readable 来绕过权限错误。

缺少 production secret 时 lifespan fail closed，服务不会进入 ready 状态。

### Operational configuration（启动时冻结）

部署方通过 Compose `--env-file`（或宿主机环境）提供下列 `GATEWAY_REPOSITORY_*` 键；
Compose 显式透传并带有冻结默认值。Settings 仅在进程启动时读取，不做热更新。

```text
GATEWAY_REPOSITORY_ARTIFACT_TTL_SECONDS
GATEWAY_REPOSITORY_ARTIFACT_CLEANUP_INTERVAL_SECONDS
GATEWAY_REPOSITORY_ARTIFACT_TOMBSTONE_BUDGET
GATEWAY_REPOSITORY_MAX_CONCURRENT_UPLOADS
GATEWAY_REPOSITORY_MAX_IMPORT_WORKERS
GATEWAY_REPOSITORY_MAX_QUEUED_IMPORTS
GATEWAY_REPOSITORY_MAX_CONCURRENT_ROW_STREAMS
GATEWAY_REPOSITORY_FULL_SCAN_TIMEOUT_SECONDS
GATEWAY_REPOSITORY_MIN_FREE_DISK_BYTES
GATEWAY_REPOSITORY_MIN_FREE_DISK_FRACTION
GATEWAY_REPOSITORY_IMPORT_HEADROOM_BYTES
```

修改上述值后必须执行 `up --no-build --force-recreate`（或等价 recreate）以使新
container environment 生效；`docker restart` **不会**更新已有 container 的 environment。

```bash
docker compose -f vnext/deploy/compose.yaml --profile p2-r2 \
  --env-file /path/to/repository.env \
  up -d --no-build --force-recreate repository-service
```

## 镜像构建（P2-R4 Compose gate / 远端 cache）

本地直接 `docker compose build` 会尝试从公网下载 Dolt/uv，在网络受限环境下耗时很长且
容易失败。正式 gate 与 S10 Compose e2e 应使用保留的 P2-R1 依赖缓存或 dependency-base
镜像，在远端开发机构建：

```bash
# 可选：指向远端 Docker daemon
export DOCKER_HOST=ssh://<remote-builder>

# 使用保留 cache / dependency-base（见 vnext/deploy/p2r1-cache/README.md）
./vnext/scripts/build-repository-service-image.sh
export GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:local
export GATEWAY_P2R2_BEARER_TOKEN_FILE=/path/to/token

docker compose -f vnext/deploy/compose.yaml --profile p2-r2 config
docker compose -f vnext/deploy/compose.yaml --profile p2-r2 up -d --no-build repository-service
```

`build-repository-service-image.sh` 的优先级：

1. 本地存在 `gateway-p2r1-repository:dependency-base-python3.14-dolt2.1.11-uv0.11.28` 时
   使用 `USE_PRELOADED_DEPENDENCIES=1`（最快，source-only rebuild）；
2. 否则探测 `http://172.17.0.1:18080` 上的 artifact cache；
3. 两者都不可用则 fail closed，不会回退到无 cache 的公网下载。

S10 集成测试 `tests/test_import_compose_e2e.py` 调用同一脚本；可通过
`GATEWAY_REPOSITORY_SERVICE_IMAGE` 复用已构建镜像而跳过 rebuild。

远端开发机（`10.10.60.4`，`tmpuser`）用于 S10 container gate；完整 provenance 见
[`vnext/deploy/p2r1-cache/README.md`](../deploy/p2r1-cache/README.md)（候选 `cb1ef42`，
对当前 R5 source 为 historical）。优先使用 `git fetch` + 精确 SHA `checkout` 同步候选代码；
**禁止**包含 `vnext/rust`（约 24G）。S10 e2e 的 `os.chown` 步骤需在远端以交互式 `sudo`
执行 pytest；不得在文档或脚本中嵌入密码，也不使用无密码 sudo 提权运行 pytest。

## P2-R1 probe（`p2-r1` profile）

P2-R1 private runtime/provider feasibility probe 仍使用 `repository-probe` compose
profile 与 named volume `repository-data`；与 R2 HTTP service 使用不同 volume，不得共享
durable root。

旧 v7 diagnostics 示例：

```bash
uv run python -m gateway_repository_service.matrix \
  --output /tmp/p2-r1-measurements.jsonl \
  --data-root /tmp/p2-r1-target
```

Target container 使用 `repository-probe` compose profile 和 named volume；matrix 的
raw records 与 decision summary 只记录脱敏测量，不保存 repository、secret、SQL 或 host
path。

审核通过后，v8 formal 只能使用 target launcher、clean provenance image 和全新输出路径：

```bash
uv run python -m gateway_repository_service.matrix \
  --v8-formal \
  --output <new-audit-rerun>/p2-r1-v8.jsonl \
  --runs 5
```

v8 formal 固定为 Candidate A、66 records、1 MiB effective byte bound；不得附加
`--diagnostic`、`--workloads` 或 `--candidates`。Candidate B 只允许通过独立的
`--reserved-b-w0-smoke` 诊断入口验证代码路径，该诊断永不产生 provider selection。
P2-R1 v8 formal retest 延期至 P2-R6 final candidate；R6 canonical command 见
[P2-R5 execution plan §9](../../docs/backend-vnext/refactoring/formal/plans/p2-r5-commit-pinned-read-execution-plan.md#9-production-retest-handoff-to-r6)。
