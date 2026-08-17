# P2-R6-S11 — Phase 2 provenance handoff

状态：`pass`（`S11_exit: pass`；`phase_2_complete: yes`）

日期：2026-08-17

本记录是 S11-4 在 S11-3 independent review `allow_phase_2_complete: yes` 之后的
documentation-only Phase 2 handoff。未修改 production code、Contract、测试、
Dockerfile、Compose、lock、entrypoint 或 candidate checkout。未重建或 retag
image。未重跑 pytest、Dolt、Compose、W1/W2、W0 或 v8 formal。本文件的
docs-only 提交不是 `validated_code_sha`，也不是 `CANDIDATE_SHA` 或 image
revision。

权威步骤：[P2-R6-S11 Build-Context-External Provenance and Phase 2 Handoff Execution Plan](../formal/plans/p2-r6-s11-build-context-external-provenance-handoff-execution-plan.md) §6
Packet：[p2-r6-s11-step-1-provenance-packet.md](p2-r6-s11-step-1-provenance-packet.md)
Lineage inventory：[p2-r6-s11-lineage-inventory.json](p2-r6-s11-lineage-inventory.json)
入口：[p2-r6-s11-step-0-entry-reconciliation.md](p2-r6-s11-step-0-entry-reconciliation.md)
边界：[p2-r6-s11-step-2-documentation-boundary.md](p2-r6-s11-step-2-documentation-boundary.md)
S11-3 放行：[p2-r6-s11-handoff-review.md](p2-r6-s11-handoff-review.md)
S11-4 pre-commit：[p2-r6-s11-step-4-precommit-checks.md](p2-r6-s11-step-4-precommit-checks.md)
上游 S10 seal：[p2-r6-s10-final-handoff.md](p2-r6-s10-final-handoff.md)

```yaml
s11_documentation_attempt: attempt-1
review_attempt: p2-r6-s11-review-attempt-1
reviewed_lineage_inventory_sha256: ae0db26a7154ca2af85838ff5d725634a2d898ec6837a0212c3d11fd4b9336e5
reviewed_draft_handoff_sha256: 7665aa30f0812ecdd9c1665e6c645b10f507abfc4be9f2dcae31191ed30a7bff
s11_3_review_sha256: 2db552c27aefa61e012f14af134f77d3535d26f86639bca1c1c6beccf6e3fc71
```

## Identity

当前生产身份是 S8 封印、S10 消费的干净 source SHA。文档 HEAD `a72227ae` 与本
docs-only 提交都不是 image input。

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
service_image: gateway-repository-service:p2-r6-final
service_image_local_tag: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
provenance_documentation_sha: this_docs_only_commit
production_code_changed_in_s11: no
test_or_build_input_changed_in_s11: no
docker_or_compose_changed_in_s11: no
public_contract_change: no
phase_2_complete: yes
```

`validated_code_sha` / `candidate_sha` / `container_validated_code_sha` 仍是
`2ef88427`。S11 未改 `vnext/`。本文件的 docs-only 提交不改变这些 SHA、
build-input revision、source-tree digest 或任何 container image identity。
`a72227ae` 与本提交都不得当作构建输入。

按仓库自引用约定，本提交不在自身内容中写入自己的最终 SHA。
`provenance_documentation_sha` 是本 docs-only 提交的 `git rev-parse HEAD`，在
post-commit 记录中登记字面量。不得把它写成 `validated_code_sha`、
`CANDIDATE_SHA` 或 image revision。

`vnext/repository_service/README.md` 仍保留 R5 功能退出措辞。该文件位于
effective source digest 内，S11 禁止改写；它不是当前 Phase 2 完成状态的
authority。

## P2-R1 through R6 SHA lineage

完整字面量与 ancestor/current 分类见
[p2-r6-s11-lineage-inventory.json](p2-r6-s11-lineage-inventory.json)。摘要：

| round | validated_code_sha | container status |
| --- | --- | --- |
| P2-R1 | `80aff3e6ff92e6d21aaa7fe73c9a2feafdc1efce` | historical image superseded |
| P2-R2 | `c94e3e8ef90d42c10f7714383412082bd7e8e846` | ancestor; no current image claim |
| P2-R3 | `a0ef723e0a8043beee09a0b0cb4f1408db5ffc5e` | ancestor; no current image claim |
| P2-R4 | `bf8c3562018d264aed22987f00d14f2dbe233697` | historical `901a13b9…` |
| P2-R5 | `7091c2c4836eebdc4cbee4424f20297b2d2f88bb` | historical `901a13b9…`; source not container-validated |
| P2-R6-S7 | `5f474ce2ccf15f11ea07f263edf3fb04c771d410` | ancestor image `sha256:ba0ac70a…` |
| P2-R6-S8/S9/S10 | `2ef884278b4998dde1e5fe224532c89b7a0cd73a` | S10 sets `container_validated_code_sha` to this SHA |

当前 image / lock / source-tree 只证明 `2ef88427`。祖先 SHA 保留为 lineage，
不改写为当前 pass。

## S10 hard-gate outcomes

权威：[p2-r6-s10-final-handoff.md](p2-r6-s10-final-handoff.md)。S11 不重跑、不改写。

```yaml
no_ignore_full_gate: pass
four_compose_nodeids: pass
eight_docker_nodeids: pass
w1_medium_production_repeat: pass
w2_production_repeat: pass
candidate_a_w0_smoke: pass
candidate_a_v8_formal: pass
v8_records: 66
v8_formal_status: go
zero_owned_residual: yes
independent_final_review: pass
production_retest_required: no
S10_exit: pass
S11_ready: yes
```

W0 是 diagnostic-only，不得当作 v8 formal。W1/W2 时间与 RSS、v8 scale-ratio /
resource advisory 不是 SLO。Candidate B 保持 `reserved_not_evaluated`。

## Capacity limitations and known non-goals

```yaml
max_upload_bytes: 268435456
max_replay_sql_bytes: 209715200
w2_replay_band: 180-199 MiB
max_import_workers: 4
max_queued_imports: 64
max_concurrent_row_streams: 8
max_concurrent_uploads: 8
v8_supported_rows_max: 100000
candidate_b_status: reserved_not_evaluated
```

Non-goals：public GC/backup/repair、metrics platform、RPO/RTO guarantee、
启用 Candidate B、把文档 HEAD 当作 `CANDIDATE_SHA`、直接开始 Phase 3 实现。
100,000–1,000,000 rows 仅为 controlled preview。

## Attempt ledger

失败与 superseded attempt 原样保留。权威表在 lineage inventory。S11 当前
`attempt-1`。本 handoff 不删除 S10-0/1/2/3/6/7 失败记录或 R1 no-go。S11-3
`review-attempt-1` 为 `pass` / `finding_count: 0`。

## External evidence

S10-9 inventory SHA-256
`2a3f355a24207beff87090e16474ec9550e79237a352399baa73d734302a90ad`。
Raw artifacts 留在
`/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z` 与远端
`/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z`。
本 handoff 不拷贝 secrets 或 package bytes。S11 未创建 archive、package、
secret、container、network、volume、work root 或 target output。

## Docker / Compose decision

```text
Current documentation HEAD at S11-4 start: a72227ae8132042924d90d602ea07772844f60e5
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S11 is documentation/provenance only; no source, dependency, Dockerfile,
  Compose, entrypoint, client image or container harness change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id:
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: passed on sealed candidate identity
Deferred gates/nodeids: none for S11; Phase 3 is design-only next work
Required execution point: S11 documentation/provenance only
```

后续若有 docs-only 提交，documentation HEAD 相对 image label 会变为
stale-by-documentation-only-delta；`validated_code_sha` 与
`container_validated_code_sha` 仍为 `2ef88427`。

## External seal schema

```yaml
stage: P2-R6-S11
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
provenance_documentation_sha: this_docs_only_commit
S10_exit: pass
S11_exit: pass
phase_2_complete: yes
next_stage_ready: Phase 3 full design
```

S11 关闭 P2-R1 至 R6 SHA lineage、final image provenance、capacity
limitations 与 Phase 2 完成决策。下一步授权工作是 Phase 3 **完整设计**，不是
直接实现。Phase 3 设计收口前不得开始 P3-R1 implementation。
