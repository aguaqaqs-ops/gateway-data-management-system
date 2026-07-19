# Gateway2 Large Pair Benchmark Runbook

这份 runbook 只覆盖三对 `large` 业务数据的独立复测链路：

1. `large-1 -> large-2`
2. `large-1 -> large-4`
3. `large-1 -> large-5`

目标是把每一对都作为独立 benchmark run 记录下来，保留各自日志和 summary，再统一看三行结果。

## 前置条件

- 前端 dev server 已启动，且浏览器能访问 `http://127.0.0.1:5173`。
- Control Plane 已启动，且健康检查 `http://127.0.0.1:8010/api/health` 可通过。
- `gateway2` 当前没有残留的 `backend_vnext.api.formal_main` 进程。
- 数据目录存在：
  - `business_large/large`
  - `business_large/large-1`
  - `business_large/large-2`
  - `business_large/large-4`
  - `business_large/large-5`

## 一键三轮执行

推荐直接跑三轮 wrapper。它会对每一轮单独清理 state、启动后端、执行前端自动化、收集 summary，并在最后生成一个总览 markdown。

```bash
gateway-data-management-system/backend/tools/upload_benchmark_run_gateway2_large_pairs.sh \
  --slice-prefix gateway2-rerun-YYYYMMDDx \
  --run-root gateway-data-management-system/backend/logs/upload-benchmark/gateway2-rerun-YYYYMMDDx \
  --state-root "$HOME/test-dir/backend-vnext-formal-state" \
  --frontend-url http://127.0.0.1:5173 \
  --backend-url http://127.0.0.1:8001 \
  --control-plane-url http://127.0.0.1:8010 \
  --dataset-root /home/issac/test-dir/business-benchmark-data/business_large
```

说明：

- `large-1` 是三轮 FULL 的固定 initial 数据集。
- `large-2`、`large-4`、`large-5` 会按顺序分别作为 FULL modified 数据集。
- 三轮互相独立，不复用上一轮状态。
- 任一轮失败后会立即停下，已完成轮次的日志会保留。

## 输出布局

每轮都会落在独立子目录下：

- `gateway-data-management-system/backend/logs/upload-benchmark/<slice-prefix>/large2/`
- `gateway-data-management-system/backend/logs/upload-benchmark/<slice-prefix>/large4/`
- `gateway-data-management-system/backend/logs/upload-benchmark/<slice-prefix>/large5/`

每个子目录里都应有：

- `backend.log`
- `frontend-console.raw.jsonl`
- `frontend-console.events.jsonl`
- `initialize_large-summary.md/json`
- `full_large_pair-summary.md/json`
- `compare-initialize-vs-full.md`

总览文件：

- `gateway-data-management-system/backend/logs/upload-benchmark/<slice-prefix>/overview.md`

## 失败后怎么补跑

如果某一轮失败，只需要重新跑那一轮，不必把三轮全部重来。

例如只重跑 `large-1 -> large-4`：

```bash
gateway-data-management-system/backend/tools/upload_benchmark_run_gateway2.sh \
  --slice gateway2-rerun-YYYYMMDDx-large4 \
  --run-dir gateway-data-management-system/backend/logs/upload-benchmark/gateway2-rerun-YYYYMMDDx/large4 \
  --state-root "$HOME/test-dir/backend-vnext-formal-state" \
  --frontend-url http://127.0.0.1:5173 \
  --backend-url http://127.0.0.1:8001 \
  --control-plane-url http://127.0.0.1:8010 \
  --dataset-root /home/issac/test-dir/business-benchmark-data/business_large \
  --initialize-dataset large \
  --full-initial-dataset large-1 \
  --full-modified-dataset large-4
```

如果你只想先看单轮模板，可以继续参考 [gateway2 upload benchmark runbook](./upload-benchmark-gateway2-runbook.md)。
