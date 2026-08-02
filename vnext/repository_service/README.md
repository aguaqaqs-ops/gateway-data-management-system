# Gateway vNext Repository Service

当前状态：P2-R1 private runtime/provider feasibility probe；尚未实现业务服务。

以下能力当前均未实现：

- HTTP route、OpenAPI 和 client adapter；
- production persistence、artifact upload/import lifecycle 和 public versioned read；
- P2-R2–R6 的全部 feature delivery。

P2-R1 probe 只使用 disposable component-first roots，不创建 control SQLite、`current/`
或 public HTTP route。Local matrix 示例：

```bash
uv run python -m gateway_repository_service.matrix \
  --output /tmp/p2-r1-measurements.jsonl \
  --data-root /tmp/p2-r1-target
```

Target container 使用 `repository-probe` compose profile 和 named volume；matrix 的
raw records 与 decision summary 只记录脱敏测量，不保存 repository、secret、SQL 或 host
path。

本阶段不注册 stub route，不伪造 health/readiness 或 feature pass。真实 `/v1/` route、
OpenAPI 和 health behavior 只有在 P2-R1–R6 的真实纵切实现并通过集成测试后才会激活。
