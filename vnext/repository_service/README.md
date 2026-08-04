# Gateway vNext Repository Service

当前状态：P2-R1 private runtime/provider feasibility probe；尚未实现业务服务。

以下能力当前均未实现：

- HTTP route、OpenAPI 和 client adapter；
- production persistence、artifact upload/import lifecycle 和 public versioned read；
- P2-R2–R6 的全部 feature delivery。

P2-R1 probe 只使用 disposable component-first roots，不创建 control SQLite、`current/`
或 public HTTP route。旧 v7 diagnostics 示例：

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

本阶段不注册 stub route，不伪造 health/readiness 或 feature pass。真实 `/v1/` route、
OpenAPI 和 health behavior 只有在 P2-R1–R6 的真实纵切实现并通过集成测试后才会激活。
