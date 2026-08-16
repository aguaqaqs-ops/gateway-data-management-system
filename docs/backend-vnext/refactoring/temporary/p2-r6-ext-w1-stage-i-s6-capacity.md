# P2-R6-EXT-W1 Stage I — S6 capacity（五份正向 package）

状态：`pass`

日期：2026-08-16

本记录对 Stage H 已发布 digest 的五份正向 v1 package 走生产 HTTP
upload → import(`FULL_SCAN`,`REJECT`) → catalog → 抽样 row-stream，并记录
raw / package / decoded / batch / staging 分层资源。这不是 Stage G 的
executor-only validator，也不是 container/S7/S10 证明。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
Stage H 审核：[P2-R6-EXT-W1 Stage H Validator Gate Review](p2-r6-ext-w1-stage-h-validator-gate-review.md)
W2 记录：[P2-R6-EXT-W1 Stage I W2](p2-r6-ext-w1-stage-i-w2.md)
Concurrency 记录：[P2-R6-EXT-W1 Stage I Concurrency Matrix](p2-r6-ext-w1-stage-i-concurrency-matrix.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
stage_h_reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
stage_h_is_ancestor: yes
selected_w1: medium
package_version: v1
canonicalization_version: v1
image_rebuilt: no
full_s6_run: yes
path: public HTTP (uvicorn + ServiceRuntime + RepositoryClient-equivalent httpx)
```

HEAD 为 Stage H 收口 `108cb90d`（`docs(repository): publish Stage H validator gate
and v1 digests`）。计划中的 Stage H review SHA `7f068a24` 是其祖先。S5 候选
`e7a6e42d` 仍是祖先。五份 live `package.tar.zst` size/SHA 与 Stage H 已发布字面量
逐字节一致；未改 Contract、未改五份 SQL、未设 rejection 预期。

## Production path

证据驱动：[`run_r6_s6_evidence.py`](../../../vnext/scripts/run_r6_s6_evidence.py)
`capacity`。本机 uvicorn + `ServiceRuntime`，与
[`versioned_fixture_consumer_harness.py`](../../../vnext/repository_service/tests/support/versioned_fixture_consumer_harness.py)
同一 public HTTP 边界。

每份 fixture：

1. `create_repository`
2. `upload_artifact`（声明 size/SHA = Stage H package）
3. `submit_versioned_import(FULL_SCAN, REJECT)`，poll `SUCCEEDED`
4. `resolve main`
5. `get catalog`；若 catalog JSON 超过 `MAX_CATALOG_JSON_BYTES`（256 KiB）返回
   `503 SERVICE_NOT_READY`，则从 package `manifest.json` 选表（Contract 规定，不是缺口）
6. 抽样 `stream table rows`（默认 `record_batch_bytes=4 MiB`）
7. ENUM/SET stream schema 不得出现 unknown/lossy
8. 删除 HTTP work root；记录 disk admission before/after

## Fixture results

全部 **accepted**（低于 256 MiB upload / 200 MiB replay）。`result=pass`。

| alias | elapsed_s | catalog | tables | stream table | streamed rows | upload_s | import_s | catalog_s | stream_s |
| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| small_cut | 82.573 | pass | 132 | device_model_table | 1678 | 0.012 | 39.401 | 19.891 | 22.688 |
| small | 154.086 | pass | 216 | device_model_table | 19580 | 0.020 | 85.650 | 32.786 | 35.254 |
| medium | 136.026 | pass | 199 | device_model_table | 66759 | 0.057 | 89.741 | 18.925 | 26.779 |
| data2 | 201.515 | 503 catalog wire limit | 319 | scdmod_fcda | 92428 | 0.032 | 126.372 | 34.973 | 39.752 |
| data1 | 246.397 | pass | 260 | scdmod_fcda | 141212 | 0.081 | 182.260 | 29.988 | 33.532 |

Package SHA 与 `canonicalization_manifest_digest` 与 Stage H 一致。

## Layer resources

| alias | raw/package bytes | decoded replay.sql | decoded manifest.json | max observed batch | peak durable-root | peak RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| small_cut | 83838 | 1296079 | 129844 | 211605 | 3093966 | 117340 |
| small | 613635 | 14956886 | 207322 | 236033 | 21192090 | 137308 |
| medium | 2081228 | 49323598 | 182544 | 245662 | 67070201 | 158440 |
| data2 | 3173874 | 79446967 | 294929 | 134741 | 105579263 | 178152 |
| data1 | 5724227 | 104957915 | 235464 | 132428 | 145598637 | 212496 |

Settings 快照（五份相同）：

```yaml
max_upload_bytes: 268435456            # 256 MiB
max_replay_sql_bytes: 209715200        # 200 MiB
record_batch_bytes: 4194304            # 4 MiB
max_decompressed_tar_stream_bytes: 4294967296
max_total_expanded_entry_bytes: 4294967296
min_free_disk_bytes: 5368709120
import_headroom_bytes: 1073741824
max_concurrent_uploads: 8
max_import_workers: 4
max_concurrent_row_streams: 8
```

disk admission 在每份 import 前后均为 `admitted: 1`。HTTP work root 已删除。

data2 的 catalog `503` 是 catalog JSON 超过 256 KiB 的 Contract 上限（319 表），
不是容量失败。stream 改用 package manifest 选最大表 `scdmod_fcda`，unknown=0、
lossy=0。未改 `MAX_CATALOG_JSON_BYTES`。

偶发 stderr `versioned read arrow bridge worker did not exit in time` 未导致
HTTP 失败或 residual worker 阻断本记录。

## Docker / Compose（延期）

```text
Current HEAD: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
Container rebuild required: no
Reason: evidence scripts/tests/docs only; no image/deployment boundary
Last verified image revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
Container gate for current HEAD: deferred
Deferred gates/nodeids: Stage J final image/lifecycle
```

## Not in this record

- 不把本记录写成 container PASS
- 不把 Dolt preflight 或 Stage G executor-only 写成 S6 PASS
- 不造超限拒绝样本（admission 拒绝已有 `test_import_package.py` owner）

```yaml
stage_i_s6_capacity: pass
five_packages_http_full_scan: pass
enum_set_unknown_or_lossy: no
contract_changed: no
image_rebuilt: no
next: W2 and concurrency matrix (independent records)
```
