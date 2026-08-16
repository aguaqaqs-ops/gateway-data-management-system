# P2-R6-EXT-W1 Stage G — Production validator execution

状态：`complete`

日期：2026-08-16

本记录对 Stage F 五份 v1 package 运行 production
`validate_and_extract_import_package()` 与
`verify_import_candidate(FULL_SCAN, REJECT)`。没有发布 gate 通过结论，没有把
`P2-R6-S6_ready` 改为 `yes`，没有改写历史 S5 evidence，也没有重建 image。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
Stage F 记录：[P2-R6-EXT-W1 Stage F Five-fixture Packages](p2-r6-ext-w1-stage-f-five-fixture-packages.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_g_entry_head_sha: b11922135b30c70af668218fd558d0c77138a3c2
stage_f_commit_sha: b11922135b30c70af668218fd558d0c77138a3c2
stage_f_entry_head_sha: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
stage_e_reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
stage_f_is_ancestor: yes
package_version: v1
canonicalization_version: v1
published_package_compatibility: none
image_rebuilt: no
full_s6_run: no
production_validator_result: pending_review
P2-R6-S6_ready: no
raw_payload_in_git: false
```

Stage G 从 Stage F 收口 commit `b1192213` 开始。S5 候选 `e7a6e42d` 仍是祖先。
五份本地 `package.tar.zst` size/SHA 与 Stage F 字面量逐字节一致。

## Production path

证据驱动：[`validate_r6_w1_packages.py`](../../../vnext/scripts/validate_r6_w1_packages.py)。
不进入 Repository 生产 `src/`，不另写 parser/mapping。

正向路径对每份 fixture：

1. production `validate_and_extract_import_package()`，binding 为 Stage F size + 64-hex SHA；
2. production `CandidateAImportProvider`：私有 Dolt HOME → private ref → 解包出的
   `replay.sql`（不是源 `dbcfg.sql`）→ marker commit；
3. production `verify_import_candidate(FULL_SCAN, REJECT)`（含 STRUCTURAL catalog
   exact match、row count、Arrow compile 与全表值转换）；
4. compiled plan 断言 ENUM `utf8` / SET `list<utf8>`，无 `gateway.lossy`，unknown=0；
5. `main` 保持 `main_before`；删除临时树。

未走 HTTP worker，未 publish main。

## Fixture results

本地 `dataset.yaml` 的 `production_validator_result` 已改为 `pending_review`（不是
`pass`，不进 Git）。

| alias | tables | rows | enum | set | unknown | lossy | extract | FULL_SCAN | main_unchanged | elapsed_s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| small_cut | 132 | 6091 | 273 | 1 | 0 | 0 | pass | FULL_SCAN | yes | 14.853 |
| small | 216 | 97095 | 404 | 1 | 0 | 0 | pass | FULL_SCAN | yes | 44.147 |
| medium | 199 | 268460 | 327 | 1 | 0 | 0 | pass | FULL_SCAN | yes | 68.295 |
| data2 | 319 | 436714 | 544 | 1 | 0 | 0 | pass | FULL_SCAN | yes | 104.548 |
| data1 | 260 | 638088 | 401 | 1 | 0 | 0 | pass | FULL_SCAN | yes | 119.929 |

Package SHA 与 `canonicalization_manifest_digest` 与 Stage F 一致。raw size/SHA
observed 与 binding 一致。ENUM/SET 列数与 Stage F catalog 扫描一致。

## Negative probes

以 small_cut 正式 package 为底，不改五份正向 SQL。

| name | outcome | detail |
| --- | --- | --- |
| package_reopen | pass | 连续 extract 两次，`manifest.json` / `replay.sql` 逐字节相同 |
| truncated_zstd | rejected | `import package is malformed` |
| digest_mismatch | rejected | `artifact raw sha256 does not match binding` |
| error_metadata_extra_field | rejected | `manifest.json failed closed validation` |
| executor_truncated_no_dolt_effect | rejected | `IMPORT_REJECTED`；`main` 不变，无 private ref |
| verification_row_count_mismatch | rejected | `row count mismatch for adv_app_list`；`main` 不变 |

既有 unit owner 复核（111 passed）：

```text
cd vnext/repository_service
uv run pytest -m unit tests/test_import_package.py tests/test_import_verification.py tests/test_p2_r1_primitives.py
```

点名：`test_rejects_truncated_zstd_frame`、`test_rejects_raw_sha_mismatch`、
`test_rejects_invalid_manifest_contract`、`test_rejects_pax_headers`、
`test_compile_malformed_enum_set_is_import_rejected_even_under_stringify`、
`test_stringify_does_not_degrade_known_types`。

## Capacity configuration snapshot

沿用 Stage A / `RepositoryServiceSettings` 默认值。Compose 未覆盖这些字节上限。

```yaml
raw_upload_bytes: 268435456          # 256 MiB
unpacked_package_bytes: 4294967296   # 4 GiB
expanded_entry_bytes: 4294967296     # 4 GiB
replay_sql_bytes: 209715200          # 200 MiB
manifest_json_bytes: 16777216        # 16 MiB
decoded_row_batch_bytes: 4194304     # 4 MiB
full_scan_timeout_seconds: 3600
min_free_disk_bytes: 5368709120      # 5 GiB
largest_package_bytes: 5724227       # data1; below 256 MiB
hard_cap_rejection_expected: no
```

## Runtime and cleanup

```yaml
python_version: "3.14.6"
dolt_version: "2.1.11"
work_root: /tmp/p2-r6-ext-w1-stage-g
work_root_removed: yes
leftover_temp_files: none
dolt_home_seeded_offline: yes
production_validator_result: pending_review
s6_capacity: not_run
gate_published: no
```

每份 fixture 在私有 Dolt HOME 中 replay 解包 SQL，FULL_SCAN 后删除该份临时树。
`DoltRunner._seed_private_dolt_config` 关闭 versioncheck。

## Verification

```text
cd vnext/repository_service
uv run ruff check . && uv run mypy
# ruff all checks passed; mypy Success: no issues found in 191 source files
uv run ruff check ../scripts/validate_r6_w1_packages.py
# All checks passed

uv run pytest -m unit tests/test_import_package.py tests/test_import_verification.py tests/test_p2_r1_primitives.py
# 111 passed
```

未重建 image：未触碰 Dockerfile、Compose、entrypoint 或 lockfile。

```text
Current HEAD: b11922135b30c70af668218fd558d0c77138a3c2
Container rebuild required: no
Reason: evidence script and docs only; no image/deployment boundary
Last verified image revision: e7a6e42d961a75c5a35a385bd67d9417779c22b5
Last verified source-tree/image id: S5 Step E
Container gate for current HEAD: deferred
Deferred gates/nodeids: Stage J final image/lifecycle
Required execution point: 阶段最终候选
```

## Not in this stage

- 发布 `canonicalization_manifest_digest` 到 readiness / `P2-R6-S6_ready=yes`（Stage H）
- S6 capacity、W2、concurrency matrix
- image rebuild
- 宣称 production validator gate PASS

```yaml
stage_g_exit: pass
next: Stage H — Validator gate review
R6-EXT-W1: no
P2-R6-S6_ready: no
```
