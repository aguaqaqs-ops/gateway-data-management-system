# P2-R6-EXT-W1 Stage I — Concurrency matrix 1/4/8

状态：`pass`

日期：2026-08-16

本记录在已导入的 selected W1（medium）上测 row-stream / upload / import 的
1/4/8 并发，并在 W2 HTTP 成功后加一组只读 stream。第 9 路 row-stream 预期
`503 SERVICE_NOT_READY`（`max_concurrent_row_streams=8`）。8 路 import 只证明
排队（`peak_running=4`），不要求 8 个 RUNNING。这不是 S3 小表结果，也不引入
process-wide cache（R5-CLEANUP-01：先测量）。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
S6 capacity：[P2-R6-EXT-W1 Stage I S6 Capacity](p2-r6-ext-w1-stage-i-s6-capacity.md)
W2 记录：[P2-R6-EXT-W1 Stage I W2](p2-r6-ext-w1-stage-i-w2.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
selected_w1: medium
w2_readonly_streams: yes
max_concurrent_row_streams: 8
max_concurrent_uploads: 8
max_import_workers: 4
image_rebuilt: no
```

路径：本机 uvicorn + `ServiceRuntime` public HTTP。代表性大表
`device_model_table`（medium 66759 行；W2 267036 行）。upload/import 用
small_cut package，避免把 S3 小表冒充 S6，同时不把 8 路 import 做成 8 份 medium。

## Row streams（medium）

| concurrency | duration_s | peak RSS KiB | dolt children after | query temp after | result |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 49.043 | 162684 | 0 | 0 | pass |
| 4 | 173.526 | 264836 | 0 | 0 | pass |
| 8 | 357.524 | 410284 | 0 | 0 | pass |
| 9th hold | n/a | 410360 | 8 | 8 | 503 SERVICE_NOT_READY |

第 9 路在 8 路 unread hold 期间探测，`status=503`，`code=SERVICE_NOT_READY`。
hold 期间 8 个 Dolt child 与 8 个 query temp 与 cap 一致；release 后进入后续档。

## W2 readonly streams

W2 已成功，另导入后只读 stream（不测第 9 路 / upload / import）。

| concurrency | duration_s | peak RSS KiB | dolt children after | query temp after | result |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 62.278 | 500004 | 0 | 0 | pass |
| 4 | 207.623 | 687092 | 0 | 0 | pass |
| 8 | 696.866 | 687492 | 0 | 0 | pass |

ENUM/SET stream schema unknown=0、lossy=0。W2 只证明 boundary/resource，不是业务代表性。

## Uploads

small_cut package，跨 repository，上限 8。

| concurrency | duration_s | result |
| --- | ---: | --- |
| 1 | 0.162 | pass |
| 4 | 0.639 | pass |
| 8 | 1.589 | pass |

## Imports

跨 repository；`max_import_workers=4`。8 路全部 `202 accepted`（queue 64，未打到 429），
`peak_running=4`、`peak_queued=4`，证明排队而非 8 个 RUNNING。

| concurrency | duration_s | accepted | rejected_429 | peak_running | peak_queued | result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 29.264 | 1 | 0 | 1 | 0 | pass |
| 4 | 80.582 | 4 | 0 | 4 | 0 | pass |
| 8 | 160.835 | 8 | 0 | 4 | 4 | pass |

## Cleanup and cache decision

矩阵结束后 `dolt_child_count=0`、`query_temp_count=0`。work root 已删除。

观测到的进程树 RSS 峰约 162–687 MiB（随 1/4/8 stream 与 W2 只读档上升），没有证据
表明需要引入 process-wide cache。本 stage **不**新增 cache。偶发
`versioned read arrow bridge worker did not exit in time` 出现在档与档之间，
`wait_runtime_idle` 后 child 归零，未阻断 PASS。

## Docker / Compose（延期）

```text
Current HEAD: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
Container rebuild required: no
Reason: evidence scripts/tests/docs only; no image/deployment boundary
Last verified image revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
Container gate for current HEAD: deferred
Deferred gates/nodeids: Stage J final image/lifecycle
```

```yaml
stage_i_concurrency_matrix: pass
ninth_row_stream: 503 SERVICE_NOT_READY
import_8_peak_running: 4
import_8_peak_queued: 4
process_wide_cache_introduced: no
w2_readonly_streams: pass
```
