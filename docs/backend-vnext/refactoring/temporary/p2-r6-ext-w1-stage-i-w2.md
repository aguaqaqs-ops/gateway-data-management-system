# P2-R6-EXT-W1 Stage I — Synthetic W2

状态：`pass`

日期：2026-08-16

本记录从 selected W1（medium）同 schema 生成 synthetic W2：`replay.sql` 逼近
`max_replay_sql_bytes=200 MiB` 的成功导入。W2 **只证明 boundary/resource safety**，
不是业务代表性样本。package/canonicalization 保持 **v1**；`synthetic=true` 只写
descriptor/evidence，不给 manifest 加字段、不升 v2。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
S6 capacity：[P2-R6-EXT-W1 Stage I S6 Capacity](p2-r6-ext-w1-stage-i-s6-capacity.md)
Concurrency 记录：[P2-R6-EXT-W1 Stage I Concurrency Matrix](p2-r6-ext-w1-stage-i-concurrency-matrix.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
selected_w1: medium
source_sql_bytes: 49323598
source_sql_sha256: sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f
generator_version: p2-r6-w2-scaler-v1
seed: p2-r6-ext-w1-medium
package_version: v1
canonicalization_version: v1
synthetic: true
business_representative: no
image_rebuilt: no
```

形状源 medium：199 表、327 ENUM + 1 SET、268460 行、源 SQL 49 323 598 bytes。

## Generation

确定性 scaler：[`synthetic_w2.py`](../../../vnext/backend/src/gateway_backend/synthetic_w2.py)。
固定 `generator_version` + `seed`。用 medium `dbcfg.sql` **原始 bytes** decode
（不用 `read_text`，避免 newline 翻译）。

1. 按 catalog 对可证明唯一键的表做 replica 倍增：整数 PK
   `value + replica * 1_000_000`；VARCHAR PK 加稳定前缀 `r{nn}_`。
2. 不改 CREATE TABLE，不 STRINGIFY，失败的表只在 evidence 标明未倍增。
3. 导出合成 `replay.sql`，夹在 180–199 MiB，且 `< 200 MiB`。
4. 复用 Stage F identity-projection producer 打 v1 package。
5. 对 W2 跑与 W1 相同的 HTTP upload/import/FULL_SCAN/read。
6. 产物留在 `/root/test-data/w2/`（不进 Git）。

```yaml
replay_sql_bytes: 201681690          # 192.337 MiB
replay_band_mib: [180, 199]
max_replay_sql_bytes: 209715200      # 200 MiB hard cap
replicas_emitted: 4
table_count: 199
scaled_tables: 108
unscaled_tables: []
enum_column_count: 327
set_count: 1
total_row_count: 1105978
package_bytes: 8301271
package_sha256: sha256:6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10
canonicalization_manifest_digest: sha256:895732a5bbfcc406b9a5edab24ff742186fb5f268ce68ca5774a798b2bd2b32f
dataset_id: p2-r6-synthetic-w2-medium-shape
```

compressed `package.tar.zst`（8.3 MiB）远小于 replay SQL。只记录，不因此判失败。
199 张表全部可 scale；`unscaled_tables` 为空。ENUM/SET 列数与 medium 相同。

## HTTP verification

与 S6 capacity 同一 public HTTP 路径。catalog `pass`。stream
`device_model_table` 267036 行，unknown=0、lossy=0。digest 与 producer 一致。

| step | seconds |
| --- | ---: |
| producer (Dolt replay + identity digest) | 452.679 |
| upload | 0.165 |
| import + FULL_SCAN | 410.532 |
| catalog | 39.301 |
| row-stream | 87.086 |
| HTTP total | 538.147 |

| layer | value |
| --- | ---: |
| raw/package bytes | 8301271 |
| decoded replay.sql | 201681690 |
| decoded manifest.json | 182616 |
| max observed batch | 245662 |
| peak durable-root | 272287052 |
| peak RSS KiB | 635248 |

disk admission before/after 均为 `admitted: 1`。HTTP work root 已删除。stderr
偶发 `versioned read arrow bridge worker did not exit in time` 未导致失败。

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
stage_i_w2: pass
replay_in_180_199_mib: yes
replay_below_200_mib_cap: yes
http_full_scan: pass
enum_set_unknown_or_lossy: no
manifest_fields_added: no
package_version: v1
business_representative: no
```
