# Gateway2 Upload Benchmark Runbook

这份 runbook 把 `gateway2` 的前后端联合 upload benchmark 固定成可重复流程，目标是避免每次复跑都重新摸索：

- 先清理 gateway 机数据，回到初始状态
- 再启动后端 benchmark
- 再开启前端 benchmark 并保留 console 日志
- 最后统一用 summary / compare 工具汇总结果

这条链路现在是 fail-closed 的：

- `upload_benchmark_run_gateway2.sh` 会先预检前端和 control plane，再决定是否清 state root。
- `upload_benchmark_prepare_run.sh` 会在 backend 真正可用后才继续。
- `upload_benchmark_collect.sh` 在 backend 或 frontend 日志缺失时直接失败，不再静默跳过。

如果你只想走最省心的入口，可以直接先跑一条命令：

```bash
gateway-data-management-system/backend/tools/upload_benchmark_run_gateway2.sh --slice gateway2-rerun
```

它会自动清 state root、拉起后端、自动完成前端初始化和第二轮 FULL 上传，并在 `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/` 下生成完整的 summary 和 compare。

如果你只想先把后端拉起来、再手工或单独跑前端，也可以继续用：

```bash
gateway-data-management-system/backend/tools/upload_benchmark_prepare_run.sh --slice gateway2-rerun
```

## 适用范围

- gateway device: `2`
- gateway name: `gateway2`
- login principal: `local:111111`
- 场景:
  - `INITIALIZE_BASELINE`，数据目录 `business_large/large`
  - `FULL`，数据目录 `business_large/large-1 + business_large/large-2`

## 目录约定

- 后端状态根目录默认: `~/test-dir/backend-vnext-formal-state`
- 后端 benchmark log:
  - `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend.log`
- 前端 console raw log:
  - `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.raw.jsonl`
- 前端 console 事件流:
  - `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl`
- 汇总目录:
  - `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/`

## 1. 清理并重置 gateway 数据

先确认 control plane 和 frontend 端口可用，再停掉正在跑的 `backend_vnext.api.formal_main`，最后清掉 state root。

预检命令：

```bash
gateway-data-management-system/backend/.venv/bin/python \
  gateway-data-management-system/backend/tools/upload_benchmark_preflight.py \
  --frontend-url http://127.0.0.1:5173 \
  --control-plane-url http://127.0.0.1:8010
```

```bash
gateway-data-management-system/backend/tools/upload_benchmark_reset_state.sh \
  --state-root "$HOME/test-dir/backend-vnext-formal-state"
```

如果你想保留当前 backend 进程，仅做一次 dry-run 检查：

```bash
gateway-data-management-system/backend/tools/upload_benchmark_reset_state.sh \
  --state-root "$HOME/test-dir/backend-vnext-formal-state" \
  --dry-run
```

## 2. 启动后端 benchmark

用统一入口启动后端，保留 tee 日志。

```bash
gateway-data-management-system/backend/tools/upload_benchmark_start_backend.sh \
  --state-root "$HOME/test-dir/backend-vnext-formal-state" \
  --log gateway-data-management-system/backend/logs/upload-benchmark/gateway2-rerun/backend.log
```

如果你希望直接用手工命令，也可以等价使用：

```bash
BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK=1 \
BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1 \
BACKEND_VNEXT_FORMAL_STATE_ROOT="$HOME/test-dir/backend-vnext-formal-state" \
PYTHONPATH=gateway-data-management-system/backend \
gateway-data-management-system/backend/.venv/bin/python -m backend_vnext.api.formal_main \
2>&1 | tee gateway-data-management-system/backend/logs/upload-benchmark/gateway2-rerun/backend.log
```

## 3. 开启前端 benchmark

在新浏览器 context 或新 profile 里执行：

```js
localStorage.setItem("formalUploadBenchmark", "1")
location.reload()
```

重要提醒:

- 不要复用上一次跑完后的浏览器 context，OPFS 里的 workbench bundle 会影响后续结果。
- 前端 console 日志请单独落盘，后面 summary 只吃事件 JSONL。
- 如果只拿到了 `frontend-console.raw.jsonl`，先让 `upload_benchmark_collect.sh` 转成 `frontend-console.events.jsonl`，不要手工删行。

## 4. 复跑路径

### 4.1 INITIALIZE_BASELINE

1. 进入 gateway2 的 workspace 页面，完成 SSO 登录。
2. 选择 `business_large/large`。
3. 执行首次上传，模式应为 `INITIALIZE_BASELINE`。
4. 让页面进入可继续提交/工作台状态。
5. 如要保留完整链路，再继续提交、审核通过，并把当前 batch 归档掉，确保下一轮 `FULL` 可以在新 batch 上进行。

### 4.2 FULL

1. 当前批次进入可上传状态后，再次加载 workspace。
2. 选择 `business_large/large-1` 作为 initial。
3. 选择 `business_large/large-2` 作为 modified。
4. 执行 `FULL` 上传。
5. 保持同一个浏览器 context，不要关闭窗口，避免 OPFS 丢失。

## 5. 前端 console 采集

如果你是通过 Playwright 或浏览器自动化保存 console 原始 JSONL，`upload_benchmark_collect.sh` 会自动识别并转换成纯事件流；你也可以手动先转一次，再喂给 summary 工具。

```bash
gateway-data-management-system/backend/.venv/bin/python \
  gateway-data-management-system/backend/tools/upload_benchmark_console_to_events_jsonl.py \
  --input gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.raw.jsonl \
  --output gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl
```

## 6. 汇总

### INITIALIZE

```bash
gateway-data-management-system/backend/.venv/bin/python \
  gateway-data-management-system/backend/tools/upload_benchmark_summary.py \
  --backend-log gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend.log \
  --frontend-log gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl \
  --scenario initialize_large \
  --output-md gateway-data-management-system/backend/logs/upload-benchmark/<slice>/initialize_large-summary.md \
  --output-json gateway-data-management-system/backend/logs/upload-benchmark/<slice>/initialize_large-summary.json
```

### FULL

```bash
gateway-data-management-system/backend/.venv/bin/python \
  gateway-data-management-system/backend/tools/upload_benchmark_summary.py \
  --backend-log gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend.log \
  --frontend-log gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl \
  --scenario full_large_pair \
  --output-md gateway-data-management-system/backend/logs/upload-benchmark/<slice>/full_large_pair-summary.md \
  --output-json gateway-data-management-system/backend/logs/upload-benchmark/<slice>/full_large_pair-summary.json
```

### Compare

```bash
gateway-data-management-system/backend/.venv/bin/python \
  gateway-data-management-system/backend/tools/upload_benchmark_compare.py \
  --before-json gateway-data-management-system/backend/logs/upload-benchmark/<slice>/initialize_large-summary.json \
  --after-json gateway-data-management-system/backend/logs/upload-benchmark/<slice>/full_large_pair-summary.json \
  --output-md gateway-data-management-system/backend/logs/upload-benchmark/<slice>/compare-initialize-vs-full.md
```

## 7. 常见坑

- 前端没有 `submit.sync.total` 事件，提交等待应看 `frontend.submit.poll_until_ready`。
- `archive-selection` 必须使用 `archive-candidates` upsert 之后的最新 `candidate_set_hash`。
- 前端页面运行在 `127.0.0.1:5173`，正式 API 在 `127.0.0.1:8001`。
- `FULL` 跑完后不要关浏览器，否则 OPFS 里的 workbench bundle 会消失。
- 如果 summary 里前端事件数为 0，先确认输入是不是纯事件 JSONL，而不是包裹过的 console 原始日志。
- 如果你想减少手工步骤，优先使用 `upload_benchmark_run_gateway2.sh`，它会直接产出 `backend.log`、`frontend-console.raw.jsonl`、`frontend-console.events.jsonl`、两个 summary 和 compare。
- `upload_benchmark_collect.sh` 现在是 fail-closed 的，只要 backend 或 frontend 日志缺失就会返回非零。
