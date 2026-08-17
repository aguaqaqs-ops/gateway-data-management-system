# P2-R6-S11 Step 1 — Provenance and limitation packet

状态：`complete`（packet assembled；`phase_2_complete: no`）

日期：2026-08-17

本记录组装 P2-R1..R6 SHA lineage、final image provenance、S10 hard-gate 结果、
容量边界、known non-goals 与 attempt ledger。未修改 production code、测试、
Dockerfile、Compose、lock 或 candidate checkout。未重跑 pytest、Dolt、Compose、
W1/W2、W0 或 v8 formal。未把 raw package、token 或完整日志拷入文档 worktree。
`phase_2_complete` 保持 `no`，直到独立审核与 S11-4 post-commit 检查授权。

权威计划：[P2-R6-S11 Build-Context-External Provenance and Phase 2 Handoff Execution Plan](../formal/plans/p2-r6-s11-build-context-external-provenance-handoff-execution-plan.md) §3
入口：[p2-r6-s11-step-0-entry-reconciliation.md](p2-r6-s11-step-0-entry-reconciliation.md)
机器可读 inventory：[p2-r6-s11-lineage-inventory.json](p2-r6-s11-lineage-inventory.json)
Draft handoff：[p2-r6-s11-final-handoff.md](p2-r6-s11-final-handoff.md)
上游 seal：[p2-r6-s10-final-handoff.md](p2-r6-s10-final-handoff.md)

```yaml
s11_documentation_attempt: attempt-1
s11_attempt_prefix: p2-r6-s11-attempt-1
lineage_inventory_sha256: ae0db26a7154ca2af85838ff5d725634a2d898ec6837a0212c3d11fd4b9336e5
entry_identities_unchanged: yes
```

## Entry identity (unchanged from S11-0)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: a72227ae8132042924d90d602ea07772844f60e5
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
provenance_documentation_sha: deferred_until_s11_4_commit
S11_entry_ready: yes
phase_2_complete: no
```

S11-1 复算 HEAD、candidate porcelain、`vnext` delta 与 S10-10 / S10-9 inventory
哈希，与 S11-0 逐字相同。文档 HEAD `a72227ae` 不是 image input。

## SHA lineage

历史 round SHA 的 `role` 是 `ancestor_exit`。当前生产身份只绑定 S10 seal 的
`2ef88427`。祖先 container SHA 不得写成当前 candidate 已验证。

| round | validated_code_sha | container_validated_code_sha | documentation SHA | role |
| --- | --- | --- | --- | --- |
| P2-R1 | `80aff3e6ff92e6d21aaa7fe73c9a2feafdc1efce` | historical image `sha256:ddc7a412…` | `969b3691…` | ancestor_exit |
| P2-R2 | `c94e3e8ef90d42c10f7714383412082bd7e8e846` | none recorded | none (no separate handoff file) | ancestor_exit |
| P2-R3 | `a0ef723e0a8043beee09a0b0cb4f1408db5ffc5e` | none recorded | none (consumed as R4 ancestor) | ancestor_exit |
| P2-R4 | `bf8c3562018d264aed22987f00d14f2dbe233697` | `901a13b9…` historical | `52d66bf9…` | ancestor_exit |
| P2-R5 | `7091c2c4836eebdc4cbee4424f20297b2d2f88bb` | `901a13b9…` historical; not current source | `cbc894ff…` (+ review fix `1fc69258…`) | ancestor_exit |
| P2-R6-S6 | S5 `e7a6e42d…` | `656a66bf…` ancestor | `0b4969fe…` | ancestor_exit |
| P2-R6-S7 | `5f474ce2ccf15f11ea07f263edf3fb04c771d410` | same; image `sha256:ba0ac70a…` | `1bfa1d7f…` | ancestor_exit |
| P2-R6-S8 | `2ef884278b4998dde1e5fe224532c89b7a0cd73a` | deferred at S8 | `71da5061…` | sealed current source |
| P2-R6-S9 | `2ef88427…` | deferred at S9 | `21c99ef3…` | external candidate seal |
| P2-R6-S10 | `2ef88427…` | `2ef88427…` | `a72227ae…` | current production seal |
| P2-R6-S11 | unchanged | unchanged | deferred until S11-4 | documentation only |

权威出处与完整字面量见 inventory JSON。R2 无独立 handoff 文件，以 checklist §4
退出提交 `c94e3e8e` 为权威。R3 以 R4 计划要求的 ancestor `a0ef723e` 为权威。

`provenance_documentation_sha` 在 S11-4 docs-only 提交之后按仓库自引用约定登记。
不得把 `a72227ae`、本 packet 或 draft handoff 写成该字段。

## Final image provenance

从 S11-0 / S10-11 / S10-9 inventory 携带，未 inspect、未 rebuild：

```yaml
service_image: gateway-repository-service:p2-r6-final
service_image_local_tag: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
image_matches_build_context: true
dual_tag_identical: yes
```

S9 provisional 与 S10 final 解析为同一 Service ID。历史 S7 image `sha256:ba0ac70a…`
与 R1 image `sha256:ddc7a412…` 不是当前 candidate 证据。

## S10 hard gates

权威：[p2-r6-s10-final-handoff.md](p2-r6-s10-final-handoff.md)。本步不重跑。

```yaml
no_ignore_full_gate: pass
repository_service_total: 1844
eight_docker_nodeids: pass
w1_medium_production_repeat: pass
w2_production_repeat: pass
w1_w2_hard_vs_advisory: hard=SUCCEEDED/container_pass; timing_rss=advisory_not_slo
candidate_a_w0_smoke: pass
w0_classification: diagnostic_only_not_formal
candidate_a_v8_formal: pass
v8_records: 66/66
v8_formal_status: go
selected_provider: candidate_a_offline_cli
candidate_b_status: reserved_not_evaluated
v8_scale_ratio_resource: advisory_not_slo
zero_owned_residual: yes
independent_final_review: pass
production_retest_required: no
S10_exit: pass
```

v8 产物内历史字段 `production_retest_required: true` 是 P2-R1 内容，不覆盖
S10 seal。

## Capacity limits and non-goals

硬边界（不是 SLO）：

```yaml
max_upload_bytes: 268435456
max_replay_sql_bytes: 209715200
w2_replay_band: 180-199 MiB
w2_replay_bytes_s10: 201681690
max_import_workers: 4
max_queued_imports: 64
max_concurrent_row_streams: 8
max_concurrent_uploads: 8
import_headroom_bytes: 1073741824
min_free_disk_bytes: 5368709120
max_catalog_json_bytes: 262144
v8_supported_rows_max: 100000
v8_rows_100k_to_1m: controlled_preview_not_production_support
recommended_concurrency: 2  # advisory
```

Known non-goals：public GC / backup / repair、metrics platform、RPO/RTO、
启用 Candidate B、P3 实现、把文档 HEAD 当作 candidate。下一步在 S11 成功后是
Phase 3 **完整设计**，不是直接实现。

## Attempt ledger

失败与 superseded 记录全部保留，不得改写成 pass。完整表在 inventory JSON。
摘要：

- P2-R1 2026-08-04 no-go `f28783e4…` 保留；权威 go 是 `80aff3e6` / `969b3691`
- S10-0/1/2/3/6/7 失败或 superseded attempt 按 S10-11 ledger 原样携带
- S11-0 `attempt-1`：`S11_entry_ready: yes`

## Authoritative handoffs and retained external evidence

文档 worktree 内权威路径与 SHA 见 inventory `authoritative_handoffs`。S10-11
handoff SHA-256 `ed4c700f…`、S10-10 `50a8175b…`、S10-9 packet `43b80f2f…`、
S10-9 inventory `2a3f355a…`。

外部 audit root 只登记 path/hash：

```text
local:  /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z
remote: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z
```

未拷贝 raw W1/W2 package、token 或完整日志。S11 未创建新的 archive、container、
network、volume、work root 或 target output。

## Docker / Compose decision

```text
Current HEAD: a72227ae8132042924d90d602ea07772844f60e5
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S11-1 is documentation assembly only; lineage/packet/draft handoff are
  outside the effective source digest; no Dockerfile, dependency, Compose,
  entrypoint, client image or harness change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id:
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: passed on sealed candidate identity
Deferred: S11-2 docs-only boundary check; S11-3 independent review; S11-4 commit
Required execution point: S11 documentation/provenance only
```

## Exit

```yaml
packet_complete: yes
source_independent: yes
internally_consistent: yes
limitations_explicit: yes
candidate_b_limitation_retained: yes
advisory_not_promoted_to_slo: yes
failed_attempts_preserved: yes
raw_secrets_or_packages_copied: no
provenance_documentation_sha: deferred_until_s11_4_commit
S11_exit: no
phase_2_complete: no
next: S11-2 documentation boundary and consistency gate in the same conversation
  only while entry identities and evidence sources remain unchanged
```

下一步只读检查 docs-only diff、链接、字段分离、旧引用分类和零 S11 残留。
独立审核与最终 commit 另开对话。
