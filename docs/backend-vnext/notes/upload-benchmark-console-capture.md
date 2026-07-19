# Upload Benchmark Console Capture

这份说明用于配合 `upload_benchmark_run_gateway2.sh`、`upload_benchmark_summary.py` 和 `upload_benchmark_compare.py` 采集前端 console benchmark。

## 开启前端 Benchmark

在浏览器控制台执行：

```js
localStorage.setItem("formalUploadBenchmark", "1")
location.reload()
```

## 推荐采集方式

如果前端已经把 `[formal-upload-benchmark]` 事件写到 console，建议把这些日志保存成 JSONL。下面给出一个轻量级的控制台采集 snippet，适合在开发环境临时使用：

```js
(() => {
  const prefix = "[formal-upload-benchmark]";
  window.__formalUploadBenchmarkEvents = [];
  const pushEvent = (payload) => {
    window.__formalUploadBenchmarkEvents.push({
      ts: new Date().toISOString(),
      type: "info",
      page_url: location.href,
      payload,
    });
  };
  const wrap = (original) => (...args) => {
    const first = args[0];
    if (typeof first === "string" && first.startsWith(prefix)) {
      const raw =
        first === prefix && typeof args[1] === "string"
          ? args[1]
          : first.slice(prefix.length).trim();
      try {
        pushEvent(JSON.parse(raw));
      } catch {
        pushEvent({ raw });
      }
    }
    return original(...args);
  };
  console.info = wrap(console.info.bind(console));
  console.log = wrap(console.log.bind(console));
  window.exportFormalUploadBenchmarkEvents = () =>
    window.__formalUploadBenchmarkEvents
      .map((item) => JSON.stringify(item))
      .join("\n");
})();
```

如果页面本身已经输出纯 JSONL 行，也可以直接保存那些行，不需要二次包裹。
`upload_benchmark_collect.sh` 会自动识别 raw wrapper JSONL，并在汇总前调用转换脚本。
现在 collect 是 fail-closed 的：只要 backend log 或 frontend log 缺失，就会直接退出失败，不会再静默跳过。

## 标准目录

建议每次 slice 都保存到下面的目录结构中，优先由 `upload_benchmark_run_gateway2.sh` 统一创建：

- backend log: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend.log`
- backend launch log: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/backend-launch.log`
- frontend raw log: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.raw.jsonl`
- frontend event log: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/frontend-console.events.jsonl`
- initialize summary markdown: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/initialize_large-summary.md`
- initialize summary json: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/initialize_large-summary.json`
- full summary markdown: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/full_large_pair-summary.md`
- full summary json: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/full_large_pair-summary.json`
- compare markdown: `gateway-data-management-system/backend/logs/upload-benchmark/<slice>/compare-initialize-vs-full.md`

例如：

```bash
gateway-data-management-system/backend/tools/upload_benchmark_run_gateway2.sh \
  --slice gateway2-rerun
```

如果你只需要汇总已有日志，可以单独调用 `upload_benchmark_collect.sh`，但它只会做解析和汇总，不会启动浏览器，也不会执行上传。

如果你想先把环境拉起来，可以用 `gateway-data-management-system/backend/tools/upload_benchmark_prepare_run.sh --slice <name>` 先清 state root、启动后端，并生成该次 run 的 next-step 提示。
