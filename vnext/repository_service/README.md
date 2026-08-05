# Gateway vNext Repository Service

当前状态：P2-R2 service shell、auth、readiness 与 control lifecycle 已激活；业务
create/upload/import/read 尚未实现。

## P2-R2 已激活

- FastAPI composition root 与 production lifespan；
- production bearer（secret file 优先，fail closed）；
- `/healthz` 与 `/readyz`；
- control DB migration/open/close 与 durable-root lock；
- selected provider（Candidate A offline CLI）capability check 与 subprocess shutdown/reap。

以下能力当前均未实现：

- create/upload/import/read 与任何 `/v1/` 业务 route；
- import worker pool（属 P2-R4）；
- Candidate B / Dolt SQL server（默认禁用）；
- P2-R3–R6 的全部 feature delivery。

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
docker compose -f vnext/deploy/compose.yaml --profile p2-r2 up -d
```

Compose 将 secret 只读挂载到 `/run/secrets/repository-bearer-token`，并使用独立 named
volume `repository-service-data` 挂载到 `/var/lib/gateway/repository`。healthcheck 使用
镜像内 Python 标准库访问 `/readyz`。

缺少 production secret 时 lifespan fail closed，服务不会进入 ready 状态。

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
在 v8 实现和 A/B W0 smoke 完成复审前，不运行上述 formal 命令。

真实 `/v1/` route、OpenAPI 与 mutation effect 从 P2-R3 首个业务 route 开始；P2-R2
只提供 shell/auth/readiness/lifecycle，不注册 stub 业务 route。
