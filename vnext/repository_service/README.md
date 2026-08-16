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

### S7 test-only Compose harness

S7 测试为每个 nodeid 分配独立 Compose project、token 文件和 named volume，并在
`finally` 中执行 `down -v --remove-orphans`。不要把 ephemeral client 加进 production
Compose：inside-network client 是一次性容器，gate-host 路径使用动态发现的 Linux
bridge/service IPv4，不发布 Service host port。

重启验证使用同一 named volume 上的 `up -d --no-build --force-recreate`，不是
`docker compose restart`。test-only client image 定义见
`vnext/repository_client/tests/Dockerfile`；`versioned_v1` fixture 只读挂载，不写入
client image。client stdout 只接受 typed summary
（`status/repository_id/c0/c1/c2/main_commit`），evidence 必须 redact bearer 与 host
path。

本说明不是 S7 Compose PASS，也不把 Stage J image 升级为当前 candidate 的容器证据。
镜像重建延期到 S7-5 provisional image。

## Private whole-root snapshot / restore（operator only）

这不是 public backup/restore API，也不注册 HTTP route。部署方对 **整个** quiescent
durable root 做一次性 snapshot，并恢复到 **已证明为空** 的目标 root。不承诺 RPO、RTO
或 CommitId 跨另一场灾难保持稳定。失败时保持 Service stopped，不自动修复、不 overlay
live root。

禁止：只拷 SQLite、只拷单个 Dolt tree、partial component、non-empty overlay、在
Service 仍运行时操作。`snapshot check` 不猜测目标曾经是否为空；empty-target 由本
runbook 在 restore 前证明。

Private CLI：

```bash
python -m gateway_repository_service.snapshot_admin hold [--data-root PATH]
python -m gateway_repository_service.snapshot_admin check [--data-root PATH]
```

stdout 只有一行 machine-readable JSON。`hold` 必须看到完整 `status=ready` 且确认 helper
仍存活后才能复制；`check` 必须看到 `status=passed` 且 exit 0 后才能启动 Service。helper
退出即表示 snapshot 窗口关闭。SIGINT/SIGTERM 是 hold 的受控结束。

### Host data-root

将 `<DATA_ROOT>` 换成实际 durable root。operator 与 Service 使用同一支持版本。

```bash
# 1. 停止 Service，确认无本机 gateway 进程再写该 root。
# 2. hold：checkpoint 成功后打印 ready JSON，并一直持锁。另开终端做 snapshot。
python -m gateway_repository_service.snapshot_admin hold --data-root "<DATA_ROOT>"

# 3. 仅在 ready JSON 完整且 hold 仍存活时，复制到新的空 snapshot 目录。
SNAPSHOT_ROOT="$PWD/repository-root-snapshot"
test ! -e "$SNAPSHOT_ROOT"
mkdir -p "$SNAPSHOT_ROOT"
cp -a "<DATA_ROOT>/." "$SNAPSHOT_ROOT/"

# 4. 结束 hold（对该进程 SIGTERM/SIGINT），确认它已退出。
# 5. 证明 restore 目标为空（允许不存在，或空目录 / 仅 lost+found）。
RESTORE_ROOT=/var/lib/gateway/repository-restore
test ! -e "$RESTORE_ROOT" || \
  test -z "$(find "$RESTORE_ROOT" -mindepth 1 ! -name lost+found -print -quit)"

# 6. 整根恢复。不要先跑会创建 layout 的普通 Service 入口。
mkdir -p "$RESTORE_ROOT"
cp -a "$SNAPSHOT_ROOT/." "$RESTORE_ROOT/"

# 7. Service 仍停止时 check。
python -m gateway_repository_service.snapshot_admin check --data-root "$RESTORE_ROOT"

# 8. 用相同支持版本启动，指向 $RESTORE_ROOT，确认 /readyz 与 snapshot 时的 public facts。
```

### Compose named volume

使用最终 Repository Service image、gateway euid，并 **覆盖** entrypoint，避免
`docker-entrypoint.sh` 在 check 前创建或修改 layout。不要新增常驻 snapshot service。
hold 需保持前台存活；snapshot 在第二个终端进行。

```bash
COMPOSE=(docker compose -f vnext/deploy/compose.yaml --profile p2-r2)
IMAGE="$("${COMPOSE[@]}" images -q repository-service)"
test -n "$IMAGE"

# 解析当前 service 已挂载的 data volume，不要猜测 project 前缀。
CONTAINER="$("${COMPOSE[@]}" ps -aq repository-service)"
test -n "$CONTAINER"
VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/gateway/repository"}}{{.Name}}{{end}}{{end}}' "$CONTAINER")"
test -n "$VOLUME"

# 1. 停止 Service。
"${COMPOSE[@]}" stop repository-service

# 2. hold（覆盖 entrypoint，gateway euid，同一 named volume）。固定名字使 signal、
#    liveness 与退出状态都可审计；detach 只用于让本 shell 执行 snapshot 命令。
HOLD_CONTAINER="repository-snapshot-hold"
docker rm -f "$HOLD_CONTAINER" 2>/dev/null || true
docker run -d --name "$HOLD_CONTAINER" --entrypoint python --user gateway \
  --env GATEWAY_REPOSITORY_PROFILE=production \
  --env GATEWAY_REPOSITORY_DATA_ROOT=/var/lib/gateway/repository \
  -v "$VOLUME":/var/lib/gateway/repository \
  "$IMAGE" -m gateway_repository_service.snapshot_admin hold

# 只接受一行完整 ready JSON，并再次确认 helper 仍存活。
HOLD_JSON=""
for _attempt in $(seq 1 80); do
  HOLD_JSON="$(docker logs "$HOLD_CONTAINER" 2>/dev/null || true)"
  test -n "$HOLD_JSON" && break
  test "$(docker inspect -f '{{.State.Running}}' "$HOLD_CONTAINER")" = true
  sleep 0.1
done
python -c 'import json,sys; p=json.loads(sys.argv[1]); assert p["action"] == "hold" and p["status"] == "ready"' "$HOLD_JSON"
test "$(docker inspect -f '{{.State.Running}}' "$HOLD_CONTAINER")" = true

# 3. ready JSON 完整且 hold 容器仍运行时，一次性 tar 整个 volume。
mkdir -p ./repository-root-snapshot
docker run --rm \
  -v "$VOLUME":/from:ro \
  -v "$PWD/repository-root-snapshot":/to \
  alpine:3.20 tar -C /from -cf /to/root.tar .

# 4. 对 hold 发送 SIGTERM，确认受控 exit 0 后删除容器。
docker stop --signal SIGTERM --time 5 "$HOLD_CONTAINER"
test "$(docker inspect -f '{{.State.ExitCode}}' "$HOLD_CONTAINER")" = 0
docker rm "$HOLD_CONTAINER"

# 5. 新 volume 必须为空。禁止先用普通 entrypoint 启动 Service。
RESTORE_VOLUME="repository-service-restore"
docker volume create "$RESTORE_VOLUME"
docker run --rm -v "$RESTORE_VOLUME":/data:ro alpine:3.20 \
  sh -c 'find /data -mindepth 1 ! -name lost+found | grep . && exit 1 || exit 0'

# 6. 整根恢复，再交给 gateway 所有权。
docker run --rm \
  -v "$RESTORE_VOLUME":/to \
  -v "$PWD/repository-root-snapshot":/from:ro \
  alpine:3.20 tar -C /to -xf /from/root.tar
docker run --rm --entrypoint chown --user root \
  -v "$RESTORE_VOLUME":/var/lib/gateway/repository \
  "$IMAGE" -R gateway:gateway /var/lib/gateway/repository

# 7. check：仍覆盖 entrypoint，gateway euid，挂载 restore volume。
docker run --rm --entrypoint python --user gateway \
  --env GATEWAY_REPOSITORY_PROFILE=production \
  --env GATEWAY_REPOSITORY_DATA_ROOT=/var/lib/gateway/repository \
  -v "$RESTORE_VOLUME":/var/lib/gateway/repository \
  "$IMAGE" -m gateway_repository_service.snapshot_admin check

# 8. 用同一 image 和 restore volume 走普通 entrypoint 启动。TOKEN_FILE 是当前部署
#    使用、且 container 内 gateway 可读的 bearer secret file。
TOKEN_FILE=/path/to/repository-bearer-token
RESTORED_CONTAINER="repository-service-restored"
docker run --rm -d --name "$RESTORED_CONTAINER" \
  --env GATEWAY_REPOSITORY_PROFILE=production \
  --env GATEWAY_REPOSITORY_DATA_ROOT=/var/lib/gateway/repository \
  --env GATEWAY_REPOSITORY_BEARER_TOKEN_FILE=/run/secrets/repository-bearer-token \
  -v "$TOKEN_FILE":/run/secrets/repository-bearer-token:ro \
  -v "$RESTORE_VOLUME":/var/lib/gateway/repository \
  -p 127.0.0.1:8000:8000 \
  "$IMAGE"

# 9. /readyz 必须通过；随后重放 snapshot 前保存的 RepositoryId、CommitId、ref/catalog
#    client 请求并逐字段比较 expected public facts。另重放 snapshot 后 mutation 的 ref
#    请求并确认 404。不要以直接读取 SQLite/Dolt 代替这些 public 检查。
until docker exec "$RESTORED_CONTAINER" python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz')"; do
  sleep 1
done

# 10. 保存 public 验证结果后停止；exit 和本轮 container inventory 必须收敛。
docker stop --signal SIGTERM --time 30 "$RESTORED_CONTAINER"
test -z "$(docker ps -aq --filter name="^/${RESTORED_CONTAINER}$")"
```

partial/SQLite-only/single-Dolt/non-empty overlay/live-root 都必须失败并保持
Service stopped。通过 `check` 只表示该 whole root 可以进入 same-version startup
验证，并不单独关闭 S7/S10 restored Compose lifecycle gate。

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
