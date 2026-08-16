# P2-R6-EXT-W1 Stage F — Five-fixture package generation

状态：`complete`

日期：2026-08-16

本记录用正式 identity-projection producer 为五份 fixture 生成 v1
`manifest.json + replay.sql` package 与可复现 digest。没有运行 production
validator，没有宣称 S6 PASS，没有改写历史 S5 evidence，也没有重建 image。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
Stage E 记录：[P2-R6-EXT-W1 Stage E Implementation Review](p2-r6-ext-w1-stage-e-implementation-review.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_f_entry_head_sha: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
stage_e_reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_e_is_ancestor: yes
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
package_version: v1
canonicalization_version: v1
published_package_compatibility: none
image_rebuilt: no
full_s6_run: no
production_validator_result: not_run
formal_package_generated: yes
raw_payload_in_git: false
```

Stage F 从 Stage D/E 收口 commit `02502f9a` 开始。该 commit 包含 Stage E 审核的
实现 SHA `8425c41b`。S5 候选 `e7a6e42d` 仍是祖先。Producer 源码在本会话 worktree
中落地；五份 package 由该 worktree 生成。

## Producer

Storage Projection identity-projection assembler 位于 Backend，不进入 Repository
生产 `src/`，也不 import Shared Kernel 到 Repository：

- [`canonicalization_cells.py`](../../../vnext/backend/src/gateway_backend/canonicalization_cells.py)：
  ENUM → string/null `scalar_frame`；SET NULL → null scalar；SET 非 null →
  `encode_collection(SEQUENCE)`。不调用 Shared Kernel row encoder。
- [`canonicalization_manifest.py`](../../../vnext/backend/src/gateway_backend/canonicalization_manifest.py)：
  外层 digest = `SHA256(b"gateway-vnext:canonicalization-manifest:v1\0" || JCS)`。
  未登记新的 Shared Kernel `DigestKind`。
- [`repository_import_artifact.py`](../../../vnext/backend/src/gateway_backend/repository_import_artifact.py)：
  可复现 USTAR + zstd（mtime 0，无 pax）。
- 证据驱动：[`generate_r6_w1_packages.py`](../../../vnext/scripts/generate_r6_w1_packages.py)

行序：有 PK 的表 `ORDER BY` 主键；无 PK 的表把行帧按 unsigned bytes 排序后做
multiset 拼接（保留重复）。这是为了不依赖 Dolt `SELECT *` 无序扫描。五份业务
fixture 确实含无主键表；未改 SQL、未丢列、未 STRINGIFY。

`replay.sql` 是源 `dbcfg.sql` 原样 bytes。

## Fixture results

本地产物（不进 Git）：`/root/test-data/<alias>/package.tar.zst` 与
`canonicalization-manifest.json`。全部低于 `max_upload_bytes` 256 MiB。

| alias | tables | nonempty | enum cols | set cols | rows | package_bytes | package_sha256 | canonicalization_manifest_digest | elapsed_s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| small_cut | 132 | 58 | 273 | 1 | 6091 | 83838 | `sha256:54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43` | `sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a` | 22.053 |
| small | 216 | 114 | 404 | 1 | 97095 | 613635 | `sha256:e440af6963d99315ef632fcf34f57741de0791ec9a8942ce284b2900efbf82c3` | `sha256:5c01406aba92537be95b3ba904e6ff092661c7bce30352f3369bdf3cc6958b49` | 66.804 |
| medium | 199 | 108 | 327 | 1 | 268460 | 2081228 | `sha256:3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` | `sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c` | 132.136 |
| data2 | 319 | 164 | 544 | 1 | 436714 | 3173874 | `sha256:72a266b25f2712d8f23f3010937693dc4a5a41dd93e2cb237928f711aa0fc813` | `sha256:c1cad27c519695ba9701cdf4b5572714dfcab295355bd614f42a0d5fad53e340` | 201.522 |
| data1 | 260 | 114 | 401 | 1 | 638088 | 5724227 | `sha256:bd607ecbca4890d273188f93d1020fa32e2cc0cbd5f6f9ffdbfcffe49feb9bf2` | `sha256:29a37b49168a04da8e802471f8eaf6221b64abbdef16eb64cc1ba9fa848dd435` | 257.035 |

源 SQL SHA/size 与 Stage A 字面量一致。`small_cut` 连跑两次，package SHA 与
manifest digest 逐字节相同。

medium 的 ENUM 列数为 327（readiness 预检为 328）。本记录以本次 catalog 扫描为准；
未改类型、未过滤列。data2 为 544 ENUM + 1 SET，与 readiness 预检一致。

## Capacity configuration snapshot

沿用 Stage A / `RepositoryServiceSettings` 默认值。Compose 未覆盖这些字节上限。

```yaml
raw_upload_bytes: 268435456          # 256 MiB
unpacked_package_bytes: 4294967296   # 4 GiB
expanded_entry_bytes: 4294967296     # 4 GiB
replay_sql_bytes: 209715200          # 200 MiB
manifest_json_bytes: 16777216        # 16 MiB
decoded_row_batch_bytes: 4194304     # 4 MiB
min_free_disk_bytes: 5368709120      # 5 GiB
largest_package_bytes: 5724227       # data1; below 256 MiB
hard_cap_rejection_expected: no
```

## Runtime and cleanup

```yaml
python_version: "3.14.6"
dolt_version: "2.1.11"
work_root: /tmp/p2-r6-ext-w1-stage-f
work_root_removed: yes
leftover_temp_files: none
dolt_home_seeded_offline: yes
production_validator_result: not_run
s6_capacity: not_run
```

每份 fixture 在私有 Dolt HOME 中 `init` → replay 源 SQL → commit → catalog/PK
scan，然后删除该份临时树。`DoltRunner._seed_private_dolt_config` 关闭 versioncheck。

## Verification

```text
cd vnext/backend
uv run ruff check . && uv run mypy
# ruff all checks passed; mypy Success: no issues found in 24 source files

uv run pytest -m unit
# 30 passed
```

未重建 image：未触碰 Dockerfile、Compose、entrypoint 或 lockfile。

```text
Current HEAD: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
Container rebuild required: no
Reason: Backend producer, evidence script and docs only; no image/deployment boundary
Last verified image revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
Last verified source-tree/image id: S5 Step E
Container gate for current HEAD: deferred
Deferred gates/nodeids: Stage J final image/lifecycle
Required execution point: 阶段最终候选
```

## Not in this stage

- production `validate_and_extract_import_package()`（Stage G）
- 发布 digest 到 readiness / `P2-R6-S6_ready=yes`（Stage H）
- S6 capacity、W2、concurrency matrix
- image rebuild

```yaml
stage_f_exit: pass
next: Stage G — Production validator execution
R6-EXT-W1: no
P2-R6-S6_ready: no
```
