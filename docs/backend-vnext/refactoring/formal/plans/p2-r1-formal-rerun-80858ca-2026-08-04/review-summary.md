# P2-R1 Formal Rerun 审核汇总

日期：2026-08-04  
Provenance commit：`80858ca1d83c33080d9568b82283624f76a7d354`  
Methodology：`p2-r1-audit-corrective-v7`  
Image：`sha256:64f75e697f1d111c4e92022a0587e8e6909684cf69c708df49c6ad783d6e10f2`

## 结论

- `p2_r1_exit`: `no-go`
- `measurement_outcome`: `no-go`
- `selected_provider`: `null`
- `next_round_ready`: `false`
- `p2_r2_ready`: `false`
- 不选择 provider，不进入 P2-R2。

本汇总的单位修正仅澄清 raw measurement 的既有字段语义，不修改任何机器 artifact：

- `workflow_process_tree`：KiB；
- `provider_process_tree`：KiB；
- `cgroup`：bytes；
- `arrow_memory_pool`：bytes。

Candidate B 的 `8` 是 `8 KiB` 的 provider-process-tree delta，不是 `8 bytes`。
该单位修正不改变任何 ratio、不改变 38 个 bounded failure dimensions，也不改变 formal `no-go` 结论。

两个 candidate 的 workflow、correctness、storage provenance 和 W3 lifecycle 均完成；两者均因 bounded-stream scaling ratio 超过正式 `1.5` hard gate 被淘汰。

## Coverage and integrity

- Normal records：60
- Scaling records：72
- Total records：132
- Unique measurement keys：132/132
- Execution errors：0
- Correctness failures：0
- Metadata complete：132/132
- Verified named-volume storage provenance：132/132
- Filesystem：XFS
- W3 lifecycle/storage evidence：24/24 available
- Memory evidence coverage：132/132 available

## Candidate summary

| Candidate | W1 max import (s) | Capacity projection/day | First reported failing dimension | Ratio | Hard gate |
|---|---:|---:|---|---:|---:|
| Candidate A offline CLI | 83.097936 | 2911.26 | bound 256 / workflow process tree / first 10% | 1.543788 | fail |
| Candidate B SQL server | 91.424040 | 2646.13 | bound 256 / workflow process tree / first 10% | 1.523377 | fail |

Ratio calculation uses five measured runs per `(candidate, scale, row bound, subject, window)`, takes the maximum measured delta for each scale, then computes `max(S10,S40,S100) / min(S10,S40,S100)`. Warm-up samples are excluded from performance aggregation. No threshold relaxation or retry-based selection was applied.

## All failing bounded dimensions

Values below are baseline-adjusted delta plateau peaks for S10/S40/S100; each is the maximum of five measured runs. Units are subject-specific: workflow/provider process-tree values are KiB, while cgroup and Arrow values are bytes. The absolute plateau values remain in the raw JSONL.

| Candidate | Bound | Subject (unit) | Window | S10 | S40 | S100 | Ratio |
|---|---:|---|---|---:|---:|---:|---:|
| A | 256 | cgroup (bytes) | final | 74,326,016 | 118,120,448 | 188,583,936 | 2.537253 |
| A | 256 | cgroup (bytes) | first | 72,675,328 | 108,998,656 | 169,385,984 | 2.330722 |
| A | 256 | cgroup (bytes) | middle | 67,223,552 | 116,682,752 | 164,569,088 | 2.448087 |
| A | 256 | provider process tree (KiB) | final | 167,636 | 217,900 | 300,156 | 1.790522 |
| A | 256 | provider process tree (KiB) | first | 158,644 | 200,384 | 254,492 | 1.604170 |
| A | 256 | provider process tree (KiB) | middle | 161,092 | 213,676 | 278,608 | 1.729496 |
| A | 256 | workflow process tree (KiB) | final | 184,864 | 235,388 | 323,644 | 1.750714 |
| A | 256 | workflow process tree (KiB) | first | 176,120 | 217,824 | 271,892 | 1.543788 |
| A | 256 | workflow process tree (KiB) | middle | 178,320 | 231,160 | 300,168 | 1.683311 |
| A | 1024 | Arrow memory pool (bytes) | first | 248,256 | 496,512 | 496,512 | 2.000000 |
| A | 1024 | cgroup (bytes) | final | 80,367,616 | 136,290,304 | 212,180,992 | 2.640130 |
| A | 1024 | cgroup (bytes) | first | 72,781,824 | 143,421,440 | 196,517,888 | 2.700096 |
| A | 1024 | cgroup (bytes) | middle | 74,862,592 | 132,628,480 | 196,304,896 | 2.622203 |
| A | 1024 | provider process tree (KiB) | final | 169,516 | 222,204 | 302,248 | 1.783006 |
| A | 1024 | provider process tree (KiB) | first | 158,624 | 204,428 | 256,568 | 1.617460 |
| A | 1024 | provider process tree (KiB) | middle | 163,048 | 219,920 | 280,808 | 1.722241 |
| A | 1024 | workflow process tree (KiB) | final | 191,696 | 242,104 | 324,280 | 1.691637 |
| A | 1024 | workflow process tree (KiB) | first | 178,592 | 226,504 | 278,596 | 1.559958 |
| A | 1024 | workflow process tree (KiB) | middle | 185,224 | 242,000 | 302,976 | 1.635728 |
| B | 256 | cgroup (bytes) | final | 14,102,528 | 46,202,880 | 65,335,296 | 4.632878 |
| B | 256 | cgroup (bytes) | first | 9,842,688 | 10,600,448 | 15,052,800 | 1.529338 |
| B | 256 | cgroup (bytes) | middle | 12,357,632 | 21,209,088 | 38,096,896 | 3.082864 |
| B | 256 | provider process tree (KiB) | final | 6,160 | 36,916 | 55,388 | 8.991558 |
| B | 256 | provider process tree (KiB) | first | 2,056 | 2,060 | 8,204 | 3.990272 |
| B | 256 | provider process tree (KiB) | middle | 4,108 | 12,312 | 28,724 | 6.992210 |
| B | 256 | workflow process tree (KiB) | final | 16,024 | 46,644 | 65,308 | 4.075637 |
| B | 256 | workflow process tree (KiB) | first | 11,892 | 11,980 | 18,116 | 1.523377 |
| B | 256 | workflow process tree (KiB) | middle | 13,952 | 22,232 | 38,640 | 2.769495 |
| B | 1024 | Arrow memory pool (bytes) | first | 248,256 | 496,512 | 496,512 | 2.000000 |
| B | 1024 | cgroup (bytes) | final | 21,815,296 | 47,321,088 | 70,586,368 | 3.235637 |
| B | 1024 | cgroup (bytes) | first | 10,858,496 | 26,124,288 | 19,996,672 | 2.405885 |
| B | 1024 | cgroup (bytes) | middle | 16,281,600 | 36,671,488 | 43,532,288 | 2.673711 |
| B | 1024 | provider process tree (KiB) | final | 8,208 | 33,176 | 55,388 | 6.748051 |
| B | 1024 | provider process tree (KiB) | first | 8 | 12,672 | 6,164 | 1584.000000 |
| B | 1024 | provider process tree | middle | 2,060 | 22,920 | 28,732 | 13.947573 |
| B | 1024 | workflow process tree | final | 22,120 | 46,984 | 69,448 | 3.139602 |
| B | 1024 | workflow process tree | first | 12,880 | 27,464 | 20,216 | 2.132299 |
| B | 1024 | workflow process tree | middle | 16,168 | 36,724 | 42,768 | 2.645225 |

Unique failing dimensions: 38, Candidate A: 19, Candidate B: 19. The large Candidate B `1584x` ratio has an S10 provider delta of only 8 KiB; it is retained as raw evidence and is not manually normalized away.

## Artifact checksums

Formal run identity:

- run: `20260804093506_1902082`
- Compose project: `gateway-p2r1-20260804093506_1902082`
- image digest: `sha256:64f75e697f1d111c4e92022a0587e8e6909684cf69c708df49c6ad783d6e10f2`
- build revision: `80858ca1d83c33080d9568b82283624f76a7d354`
- methodology: `p2-r1-audit-corrective-v7`

| Artifact | Local path | Size | SHA-256 |
|---|---|---|---|
| Raw measurements | [`p2-r1.jsonl`](./p2-r1.jsonl) | `1,446,754 bytes` | `130a477bf0edbf0f5cfe0c417dc02b0b85d8be0d9b0f3b233c9c05043b1cc5e2` |
| Machine summary | [`p2-r1.summary.json`](./p2-r1.summary.json) | `5,956 bytes` | `4fc2761e95145634f4c6b240a604bfab9165ce153625c3cc1b8bfde3e097dc74` |
| Runner report | [`p2-r1.md`](./p2-r1.md) | `758 bytes` | `a144d5f708a0bd8659f621176e5c74843bed343cde8f76844bdf539e1f357db4` |

These are new local copies of the remote formal run. Historical 2026-08-02 and `19fb10f` artifacts were not modified.
