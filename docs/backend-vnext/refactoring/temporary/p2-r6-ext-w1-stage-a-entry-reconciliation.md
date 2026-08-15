# P2-R6-EXT-W1 Stage A — Entry Reconciliation

状态：`complete`

日期：2026-08-16

本记录只做入口身份、五份 fixture 与分层容量配置的只读复核。没有运行 full S6、没有
生成正式 package、没有修改生产代码，也没有改写历史 S5 evidence。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
entry_head_sha: 63b83779cbde2d88be132aee4f6d7700741cf54c
planning_head_sha: 63b83779cbde2d88be132aee4f6d7700741cf54c
planning_head_match: yes
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
merge_base_with_s5: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_evidence_path: docs/backend-vnext/refactoring/temporary/p2-r6-s5-step-e-container-gate.md
s5_evidence_last_commit: b5b4cca3310959f45cc527ab3e7d4eb1754d12d3
s5_evidence_worktree_modified: no
tracked_worktree_dirty: no
untracked_at_entry:
  - docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-design.md
  - docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md
production_code_dirty: no
full_s6_run: no
formal_package_generated: no
```

入口 HEAD 与 planning snapshot 字面量一致。S5 候选 `e7a6e42d` 是当前 HEAD 的祖先；
S5 Step E 记录仍绑定该候选，本会话未改写。Worktree 在 Stage A 开始时没有已跟踪脏文件；
仅有上述两份尚未提交的正式设计/计划文档。这不构成 blocker，本记录与它们一并作为
docs-only commit 收口。

## Readiness and descriptors

既有 readiness record：

```yaml
readiness_path: docs/backend-vnext/refactoring/temporary/p2-r6-s6-entry-readiness.md
readiness_status: not_ready
readiness_sha256: sha256:542943baae79f5f2119719b4a47b1778b850bd64508ecdeec86586a1d2f21fde
readiness_bytes: 3548
readiness_commit: 63b83779cbde2d88be132aee4f6d7700741cf54c
selected_w1_in_readiness: medium
R6-EXT-W1: no
P2-R6-S6_ready: no
canonicalization_manifest_digest: not_computed
formal_package_bytes: not_published
production_validator_result: not_run
```

readiness 记录的 medium 源摘要在本会话被独立复算，与本地 descriptor 一致：

```yaml
dataset_id: p2-r6-business-medium
source_sql_bytes: 49323598
source_sql_sha256: sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f
source_sql_utf8: pass
source_descriptor_consistent: yes
readiness_unmappable_columns: 328
readiness_table_count: 199
```

data2 作为当时允许的 fallback，其源摘要同样独立复算通过。ENUM/SET 列计数仍沿用
readiness 既有 preflight，本会话未重跑 Dolt catalog：

```yaml
dataset_id: p2-r6-business-large-in-range
local_alias: data2
source_sql_bytes: 79446967
source_sql_sha256: sha256:b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8
source_sql_utf8: pass
source_descriptor_consistent: yes
readiness_unmappable_columns: 545
readiness_unmappable_enum: 544
readiness_unmappable_set: 1
readiness_table_count: 319
```

readiness 记录的已发布外部 descriptor 事实为：

```yaml
recorded_external_descriptor_sha256: sha256:4098ccb7d2671874a2abbb66be284e2341f77463701f2f67ea0f6cd8cf175295
recorded_external_descriptor_bytes: 2746
recorded_external_descriptor_status: not_ready
recorded_content_class: sanitized_summaries_only
file_locatable_on_this_host: no
```

该 2746-byte 文件当前不在本机可检索路径中。这不是新的 blocker：入口事实仍由
readiness record 与五份本地 `dataset.yaml` 保存；原始 SQL 仍在批准位置且 SHA/size
可复算。后续若需对外发布，Stage K 按脱敏摘要重新生成，不得把 raw SQL、完整 schema
值、行、secret 或 host path 写入 Git。

本地每份 fixture 的脱敏 descriptor 位于 `/root/test-data/<alias>/dataset.yaml`，
不进入 Git。它们仍带有旧的 10–100 MB formal-W1 代表性标签（`small_cut` 低于下界、
`data1` 略高于上界）。本轮设计已明确：该区间只是常见体积，不是拒绝阈值；五份全部
是正向可接受样本。Stage B 之后不得把这些旧 `formal_w1.eligible` 旗标当成 admission
拒绝依据。

## Fixture matrix

根目录：`/root/test-data/`。本会话对每份 `dbcfg.sql` 独立计算 byte length、SHA-256
和 UTF-8 可解码性，并与对应 `dataset.yaml` 的 `package_bytes` / `package_sha256`
核对。五份全部匹配。未运行 Dolt replay，未生成 package。

当前 hard cap：upload `256 MiB`（268435456）、replay SQL `200 MiB`（209715200）。
设计要求至少覆盖 200MB。五份源 SQL 均低于这两层。

| alias | dataset_id | source_sql_bytes | source_sql_mib | source_sql_sha256 | utf8 | yaml_match | vs_200_mib_replay | vs_256_mib_upload | this_round_role |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| small_cut | p2-r6-business-small-cut | 1296079 | 1.236 | `sha256:8fdbd3d207b81e933da9a4812b97239737541e574e7be4777dffa4f0c80ec059` | pass | yes | below | below | positive accepted |
| small | p2-r6-business-small | 14956886 | 14.264 | `sha256:7e858ce1eb9c070814b29e9799548695ee71537f812373a021c5ca9681dce027` | pass | yes | below | below | positive accepted |
| medium | p2-r6-business-medium | 49323598 | 47.039 | `sha256:78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f` | pass | yes | below | below | positive accepted; readiness selected W1 |
| data2 | p2-r6-business-large-in-range | 79446967 | 75.767 | `sha256:b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8` | pass | yes | below | below | positive accepted |
| data1 | p2-r6-business-large-upper-overflow | 104957915 | 100.096 | `sha256:22abb5f2f75c1a9645189e3e68ab95f6047914313059f673d609fe71457c3c35` | pass | yes | below | below | positive accepted |

`data1` 源 SQL 比 100 MiB 多 100315 bytes，因此旧 descriptor 把它标成 W1 上界 overflow。
它仍低于 200 MiB replay 与 256 MiB upload，本轮不得写成 rejection 预期。

正式 package 的 compressed/expanded 体积尚未计算，留给 Stage F。即使 package 同时携带
replay SQL 与 Arrow payload，当前源 SQL 相对两层 hard cap 仍有余量；若 Stage F 发现
compressed package 触及 `max_upload_bytes`，应提高可配置上限并重测 admission，而不是
把这五份改成拒绝样本。

```yaml
fixture_root: /root/test-data
fixture_count: 5
all_locatable: yes
raw_payload_in_git: false
current_hard_cap_rejection_expected: no
```

## Capacity configuration snapshot

来源：`RepositoryServiceSettings` 当前代码默认值（`env_prefix=GATEWAY_REPOSITORY_`）。
Compose 目前接线 `MIN_FREE_DISK_*`、`IMPORT_HEADROOM_BYTES` 和并发上限，没有覆盖
upload/replay/expanded 字节上限；生产容器因此使用下列默认值。

```yaml
settings_class: gateway_repository_service.settings.RepositoryServiceSettings
env_prefix: GATEWAY_REPOSITORY_
profile_observed_for_defaults: test  # numeric defaults identical across profiles
layers:
  raw_upload_bytes:
    field: max_upload_bytes
    default: 268435456  # 256 MiB
    compose_override: none
  unpacked_package_bytes:
    field: max_decompressed_tar_stream_bytes
    default: 4294967296  # 4 GiB
    compose_override: none
  expanded_entry_bytes:
    field: max_total_expanded_entry_bytes
    default: 4294967296  # 4 GiB
    compose_override: none
  replay_sql_bytes:
    field: max_replay_sql_bytes
    default: 209715200  # 200 MiB
    compose_override: none
  manifest_json_bytes:
    field: max_manifest_json_bytes
    default: 16777216  # 16 MiB
    compose_override: none
  decoded_row_batch_bytes:
    field: record_batch_bytes
    default: 4194304  # 4 MiB
    v8_field: v8_record_batch_bytes
    v8_default: 1048576  # 1 MiB
    compose_override: none
  staging_free_disk:
    min_free_disk_bytes: 5368709120  # 5 GiB
    min_free_disk_fraction: 0.10
    import_headroom_bytes: 1073741824  # 1 GiB
    compose_wired: yes
concurrency_not_size_caps:
  max_concurrent_uploads: 8
  max_import_workers: 4
  max_queued_imports: 64
```

`10–100MB` 仍只是常见 package 体积，不是本快照中的拒绝阈值。当前覆盖 200MB 的权威
hard cap 是 `max_replay_sql_bytes=200 MiB` 与 `max_upload_bytes=256 MiB`。

### 未来提高上限时的重测规则

1. 五份现有 fixture 保持正向可接受；提高上限不得给它们补 rejection 预期。
2. 若新上限仍高于这五份的源 SQL 与后续正式 package，类型/digest/validator 语义证据
   不必仅因数字变大而作废；容量 evidence 必须按新配置重跑，且不得引用旧 image 作为
   当前 HEAD 的容量证明。
3. 真正超限样本另造，只验证 bounded admission、错误码、无 Dolt effect 和 cleanup。
4. 只改 Settings 默认值属于生产代码变更，镜像重建可按 testing conventions 延期到必要
   节点；延期期间不得宣称旧 image 已使用新上限。
5. 若新增或修改 Compose/env 接线（例如 `GATEWAY_REPOSITORY_MAX_UPLOAD_BYTES`），则属于
   deployment boundary，必须按当前 HEAD 重建并跑相应容器门禁。
6. 提高 `max_upload_bytes` 时必须同时审查 `max_replay_sql_bytes`、expanded/decompressed
   上限和 disk/headroom；只抬一层会造成静默拒绝。
7. 不得把 Dolt replay preflight 或 package generation 单独宣称为 S6 PASS。

## Pending implementation scope

未决范围仍是既有 ENUM/SET 生产边界，不是新的入口 blocker：

```yaml
remaining_blockers:
  - current production ImportManifest/Arrow mapping rejects ENUM and SET; all five fixtures fail this type gate until Contract freeze and implementation land
new_blockers: none
deferred_not_blockers:
  - published 2746-byte external descriptor file is not retained on this host; facts remain in readiness record and local dataset.yaml files
  - formal package size/SHA and catalog ENUM/SET column counts for small_cut/small/data1 are not recomputed this session
next_stage: Stage B — Contract design freeze
must_not_start_until_contract_review_passes:
  - parser/model production code
  - Arrow/provider/verification production code
  - five-fixture package generation
  - production validator execution
  - S6 capacity, W2, concurrency matrix
  - image rebuild as EXT-W1 proof
status_unchanged:
  R6-EXT-W1: no
  P2-R6-S6_ready: no
  package_version: v1
  canonicalization_version: v1
  published_package_compatibility: none
container_rebuild_required_for_this_docs_commit: no
production_retest_required: yes
phase_2_complete: no
```

## Exit

```yaml
entry_identity_consistent: yes
five_fixtures_locatable: yes
all_five_below_current_hard_cap: yes
new_blocker: no
stage_a_exit: pass
```

本记录不修改历史 S5 evidence。S5 image/provenance 仍绑定 `e7a6e42d`。
