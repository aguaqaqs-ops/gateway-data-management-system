# P2-R6-S10 — External production-gate seal and S11 handoff

状态：`pass`

日期：2026-08-17

本记录是 S10-11 在 S10-10 independent final review `allow_s10_seal: yes` 之后的
documentation-only external seal 与 S11-ready handoff。未修改 production code、
Contract、snapshot 语义、Dockerfile、Compose、lock、entrypoint、adapter 或
candidate checkout。未重建或 retag image。未重跑 pytest、Dolt、Docker Compose
gate、W1/W2、W0 或 v8 formal。不宣称 Phase 2 完成。本文件的 docs-only 提交不是
`validated_code_sha`，也不是 `CANDIDATE_SHA`。

权威步骤：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §13
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §§3.6、8
S10-10 放行：[p2-r6-s10-final-gate-review.md](p2-r6-s10-final-gate-review.md)
Seal packet：[p2-r6-s10-step-9-final-packet.md](p2-r6-s10-step-9-final-packet.md)
上游 S9 seal：[p2-r6-s9-final-handoff.md](p2-r6-s9-final-handoff.md)

## Identity

S10-11 开始时用 `git rev-parse` 取得文档 HEAD 与 candidate HEAD。文档 HEAD 仍是
`0f9536c2`，docs-only，不是 image input。本地 candidate
`/root/gateway-s9-candidate-2ef88427` 与远端
`/home/issac/gateway-s10-candidate-2ef88427` 仍为字面量 `2ef88427`，porcelain
空，`git diff --check` pass。Identity helper、两份 lock hash、final Service/
Client labels 与 S10-4 / S10-9 packet / S10-10 逐字段一致。`git diff
--name-status 2ef88427..HEAD -- vnext` 为空。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
s9_handoff_record_commit_sha: 21c99ef3202f3cfd63a24d4e08cd869e36ff0af0
s10_entry_docs_commit_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
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
historical_s9_tag_retained: gateway-repository-service:2ef884278b49
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
adapter_sha256: af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150
installed_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
s10_10_review_sha256: 50a8175bbf73add8d9f34105ad3fcf7c1d90c37542e22eb89ea98752500ca8f2
s10_9_inventory_sha256: 2a3f355a24207beff87090e16474ec9550e79237a352399baa73d734302a90ad
archive_size_bytes: 332429824
archive_sha256: f2416c49c0e6b712fdf59fb2db7ba5bd62c81cdeefe67b83155b852cf6ed2245
archive_removed_after_packet: yes
same_daemon_build_and_gate: yes
cross_host_transfer: not_applicable
gate_host: issac@10.10.60.4
docker_daemon_id: dc91db82-3d49-41a4-a63c-f23dda721890
compose_version: 5.4.0
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
local_candidate_worktree: /root/gateway-s9-candidate-2ef88427
remote_candidate_worktree: /home/issac/gateway-s10-candidate-2ef88427
candidate_worktree_clean: yes
production_code_changed_in_s10: no
test_or_build_input_changed_in_s10: no
docker_or_compose_changed_in_s10: no
public_contract_change: no
phase_2_complete: no
```

`validated_code_sha` / `candidate_sha` / `container_validated_code_sha` 都是 S8
封印、S9 外部 seal 消费的干净 source SHA `2ef88427`。S10 未改 `vnext/`。本文件的
docs-only 提交不改变这些 SHA、build-input revision、source-tree digest 或任何
container image identity。`0f9536c2`、`21c99ef3` 与本 handoff 的 documentation
HEAD 都不得当作构建输入。

S10-11 只读 inspect 确认 `:p2-r6-final` 与 `:local` 仍解析为同一 immutable ID；
Client `:local` 未变；Service labels 携带 candidate、build-input、source-tree 与
Service lock；Client labels 携带 candidate 与 Client lock：

```text
image_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
image_label gateway.p2r1.build-input-revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
image_label gateway.p2r1.source-tree-sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
image_matches_build_context: true
dual_tag_identical: yes
```

祖先容器证据（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Independent reviews

| review | record | result |
| --- | --- | --- |
| S10-1 design | [p2-r6-s10-design-review.md](p2-r6-s10-design-review.md) | `review_status: fail`；保留原样 |
| S10-1 rereview | [p2-r6-s10-design-review-rerun.md](p2-r6-s10-design-review-rerun.md) | `review_status: pass`，`finding_count: 0`，`allow_s10_implementation: yes` |
| S10-3 adapter | [p2-r6-s10-audit-adapter-review.md](p2-r6-s10-audit-adapter-review.md) | `review_status: fail`；保留原样 |
| S10-3 rereview | [p2-r6-s10-audit-adapter-review-rerun.md](p2-r6-s10-audit-adapter-review-rerun.md) | pass on attempt-2 adapter；随后被 attempt-3 取代 |
| S10-3 rereview-2 | [p2-r6-s10-audit-adapter-review-rerun-2.md](p2-r6-s10-audit-adapter-review-rerun-2.md) | `review_status: pass`，`finding_count: 0`，`allow_w1_w2_execution: yes` |
| S10-10 final | [p2-r6-s10-final-gate-review.md](p2-r6-s10-final-gate-review.md) | `review_status: pass`，`finding_count: 0`，`allow_s10_seal: yes` |

权威独立设计审核是 S10-1 rereview。权威 adapter 审核是 S10-3 rereview-2（adapter
`af672fa0…`）。权威 final gate review 是 S10-10。失败与 superseded 记录不得改写成
pass。S10-10 只授权进入 S10-11；本文件才记录 `S10_exit`、`S11_ready` 和
`production_retest_required: no`。

## Step records

| step | record | result |
| --- | --- | --- |
| S10-0 attempt-1 | [p2-r6-s10-step-0-entry-preflight-attempt-1.md](p2-r6-s10-step-0-entry-preflight-attempt-1.md) | `S10_entry_ready: no`；保留 |
| S10-0 attempt-2 | [p2-r6-s10-step-0-entry-preflight.md](p2-r6-s10-step-0-entry-preflight.md) | `S10_entry_ready: yes` |
| S10-2 attempt-1 | [p2-r6-s10-step-2-audit-adapter-attempt-1.md](p2-r6-s10-step-2-audit-adapter-attempt-1.md) | superseded；adapter `b758febd…` |
| S10-2 attempt-2 | [p2-r6-s10-step-2-audit-adapter-attempt-2.md](p2-r6-s10-step-2-audit-adapter-attempt-2.md) | superseded；adapter `6282df80…` |
| S10-2 attempt-3 | [p2-r6-s10-step-2-audit-adapter.md](p2-r6-s10-step-2-audit-adapter.md) | pass；adapter `af672fa0…` |
| S10-4 | [p2-r6-s10-step-4-final-artifacts.md](p2-r6-s10-step-4-final-artifacts.md) | final Service/Client/archive identity pass |
| S10-5 | [p2-r6-s10-step-5-no-ignore-compose.md](p2-r6-s10-step-5-no-ignore-compose.md) | no-ignore + 八个 Docker nodeid pass |
| S10-6 attempt-1 | [p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md](p2-r6-s10-step-6-w1-w2-production-repeat-attempt-1.md) | leftover named volume；adapter defect；保留 |
| S10-6 attempt-2 | [p2-r6-s10-step-6-w1-w2-production-repeat.md](p2-r6-s10-step-6-w1-w2-production-repeat.md) | W1 medium / W2 hard gates pass |
| S10-7 | [p2-r6-s10-step-7-w0-smoke.md](p2-r6-s10-step-7-w0-smoke.md) | attempt-5 diagnostic smoke pass；非 formal |
| S10-8 | [p2-r6-s10-step-8-v8-formal.md](p2-r6-s10-step-8-v8-formal.md) | 66/66 `formal_status=go` |
| S10-9 | [p2-r6-s10-step-9-final-packet.md](p2-r6-s10-step-9-final-packet.md) | packet complete；hash consistent；zero owned residual |

## Exact no-ignore and Compose gate

权威：[p2-r6-s10-step-5-no-ignore-compose.md](p2-r6-s10-step-5-no-ignore-compose.md)
于 candidate `2ef88427`、S10-4 同一 gate-host 与 final image。权威日志 SHA-256
`59ae8de26c5a8e1b68d1af0a0308c5c721cc825b9d236dc4b98cd0c92983f2c7` 仍匹配
external audit 字节。未把完整日志写入文档 worktree。

权威命令（无 `--ignore` / `-m` / `-k` / `--ignore-glob` / xfail / skip / retry）。
`-vv -s` 是 reporting-only passthrough。未另跑 targeted four-node Compose 命令。

```bash
./vnext/scripts/run-tests.sh -vv -s
```

```text
authoritative_exit_code: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-s10-candidate-2ef88427
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
service_local_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
service_final_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
```

| suite | command | collected | passed | skipped | failed |
| --- | --- | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q -vv -s` | 242 | 242 | 0 | 0 |
| repository_contracts | `uv run pytest -q -vv -s` | 152 | 152 | 0 | 0 |
| repository_client | `uv run pytest -q -vv -s` | 154 | 154 | 0 | 0 |
| backend | `uv run pytest -q -vv -s` | 35 | 35 | 0 | 0 |
| repository_service parallel | `uv run pytest -q -m "not serial" -vv -s` | 1639 | 1638 | 1 | 0 |
| repository_service serial | `uv run pytest -q -m serial -n 0 -vv -s` | 205 | 205 | 0 | 0 |

repository_service 无 ignore 全集 1844 = 1639 + 205。唯一 skip：delegated-target
cgroup smoke（`GATEWAY_P2R1_TARGET_CONTAINER != "1"`），不是 required Docker
nodeid。无未分类 skip，无失败。S10-7/S10-8 target 执行关闭该环境能力。

### Eight Docker nodeids

每条由权威命令单独报告 `PASSED`，并带 per-node `residual_inventory` 全零。不是
合计算术，也不是单独补跑。前四条绑定 S10-4 final Service/Client identities。

| role | nodeid | result |
| --- | --- | --- |
| import | `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | PASSED |
| inside | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | PASSED |
| gatehost | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | PASSED |
| lifecycle | `tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | PASSED（两个 project 均为零库存） |
| readiness | `tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | PASSED |
| wrongtoken | `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | PASSED |
| wrongnet | `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | PASSED |
| restoreprobe | `tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | PASSED |

```yaml
first_failure: none
environment_repairs: none
source_or_build_input_repairs: none
repairs_to_production_or_tests: none
```

## W1 medium and W2 production repeat

权威：[p2-r6-s10-step-6-w1-w2-production-repeat.md](p2-r6-s10-step-6-w1-w2-production-repeat.md)
attempt-2。reviewed adapter SHA-256
`af672fa091a7388fb587ae2eef86e767990cf7b7990fd34a0b98b84f26b41150`。Sanitized
results：

```text
365712104a784579be1d439c438a23eaf610fbb06bdba818a1dab42a2944a573  attempt-2-w1/w1-medium.json
0f18233493b397d1da49eb923591ab47c2873ca23c0a4d1516eaa34882c7a017  attempt-2-w2/w2.json
```

| dataset | package SHA-256 | status | unknown/lossy | notes |
| --- | --- | --- | --- | --- |
| W1 medium | `3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e` | `SUCCEEDED` / `container_pass=pass` | 0 / 0 | 2081228 bytes |
| W2 | `6cac7852d1174c126c182e82010b0ff9d4043e51826b8043103360c8e49f6d10` | `SUCCEEDED` / `container_pass=pass` | 0 / 0 | replay 201681690 bytes；180–199 MiB band；below 200 MiB cap |

Public HTTP 走 final container / 无 host-port bridge。attempt-1 leftover named
volume 失败保留，不是 retry-as-pass。传输包与 staging 已删；final inventory 全 0。
S6 时间/RSS 比较仅为 advisory，未发明 SLO。

## Candidate A W0 smoke and v8 formal

W0 权威：[p2-r6-s10-step-7-w0-smoke.md](p2-r6-s10-step-7-w0-smoke.md)
attempt-5。`diagnostic_only=true`，`formal_decision=false`。不得当作 S10-8
evidence。attempt-1..4 失败与 quarantine 保留。JSONL SHA-256
`0720b5a1eec0fe5d9670d7757120490655436a125b2ebf1962b89b07796bdeab`。

v8 权威：[p2-r6-s10-step-8-v8-formal.md](p2-r6-s10-step-8-v8-formal.md)
attempt-1。canonical `--v8-formal --runs 5`，final image immutable digest，
installed launcher `2782a83f…`。JSONL SHA-256
`9dcdd1b458ec96a7391dc5cb96619155c02edaa6e17d5cd763abf42bf1d0a256`。

```text
v8_records: 66/66 unique
normal/scaling: 30/36
warm-ups/measured: 11/55
execution/correctness/sample failures: 0/0/0
selected_provider: candidate_a_offline_cli
candidate_b_status: reserved_not_evaluated
formal_status: go
formal_decision: true
resource_advisory: within_reference; scale-ratio warning does not change hard gate
```

v8 产物内历史 P2-R1 字段 `production_retest_required: true` **不是** S10 stage
字段，未改写，也不覆盖本 seal。

## Attempt ledger

失败与被取代记录全部保留，不得改写成 pass。

| step | attempt | status | note |
| --- | --- | --- | --- |
| S10-0 | 1 | fail | `S10_entry_ready: no` |
| S10-0 | 2 | pass | operator repair after S10-1 fail |
| S10-1 | 1 | fail | `review_status: fail` |
| S10-1 | rerun | pass | `allow_s10_implementation: yes` |
| S10-2 | 1 | superseded | adapter `b758febd…` |
| S10-2 | 2 | superseded | adapter `6282df80…` |
| S10-2 | 3 | pass | adapter `af672fa0…` |
| S10-3 | 1 | fail | adapter review fail |
| S10-3 | rerun | superseded | pass on attempt-2 adapter |
| S10-3 | rerun-2 | pass | `allow_w1_w2_execution: yes` |
| S10-4 | 1 | pass | final Service/Client/archive |
| S10-5 | 1 | pass | no-ignore + 8 Docker nodeids |
| S10-6 | 1 | fail | leftover named volume；adapter defect |
| S10-6 | 2 | pass | W1/W2 hard gates |
| S10-7 | 1–4 | fail | tag-only / git identity / cgroup EROFS |
| S10-7 | 5 | pass | W0 diagnostic only；非 formal |
| S10-8 | 1 | pass | 66/66 `formal_status=go` |
| S10-9 | 1 | pass | packet / hashes / zero residual |
| S10-10 | 1 | pass | `allow_s10_seal: yes` |

## Zero-residual and retained classification

权威：[p2-r6-s10-step-9-final-packet.md](p2-r6-s10-step-9-final-packet.md)。
S10-11 未重跑 residual scan；S10-10 已独立核对 packet `hash_crosscheck` 与
`zero_owned_residual: yes`。S10-11 复核 inventory.json 与抽查对象哈希仍匹配。

S10-owned archive、staging packages、Compose 对象、Dolt 子进程、runner unit、
active slice、work root 与 pytest scratch 已删除。residual-after SHA-256
`bd5c2962736c3acd3e4945dd9a85ffa1eb3e4a8657f73a8a9eb8333cf3a3e504`。

分类保留（不是本 run owned residual，未删）：

- 2026-08-03 三份 `gateway-p2r1-20260803*_repository-data`
- host 空 cgroup `/sys/fs/cgroup/gateway-p2r1`（S10-7 环境修复；`child_dirs=0`）
- retained cache `gateway-p2r1-dependency-cache.service` / `http://172.17.0.1:18080`
- 最终 Service/Client image tags（含历史 S9 tag `:2ef884278b49`）
- 2026-03-11 anonymous volume 与 `open-webui`
- `/tmp/pytest-of-issac`、`/tmp/pytest-of-tmpuser`、`/tmp/compose-pkg.tar.zst`（早于本 run）

Raw adapter、W1/W2 sanitized results、v8 artifacts 仍在 external audit root
`/root/gateway-s10-audit/p2-r6-s10-20260817T015148Z` 与远端
`/var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z`。S11 审阅后
按既有 release evidence retention 处理；本步不把原始日志拷进仓库。

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S10-11 documentation/external seal only; no Dockerfile, dependency closure,
  Compose, entrypoint, health/readiness, client image, adapter or container harness change
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id:
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: passed on sealed candidate identity
Deferred gates/nodeids: none for S10; S11 docs-only must not change container identity
Required execution point: S10 final production (complete)
```

后续 docs-only handoff 提交会使 documentation HEAD 相对 image label 变为
stale-by-documentation-only-delta；`validated_code_sha` 与
`container_validated_code_sha` 仍为 `2ef88427`。不得把 `0f9536c2` 或本文件提交
SHA 写成构建输入。

## External seal schema

```yaml
stage: P2-R6-S10
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
final_service_image_provenance: pass
final_client_and_host_runner_identity: pass
same_daemon_archive_evidence: pass
no_ignore_full_gate: pass
four_compose_nodeids: pass
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
phase_2_complete: no
```

S10 在独立 final review 为零 finding 后关闭 production retest。S11 独占
documentation/provenance handoff、P2-R1 至 R6 SHA lineage、capacity limitations、
本 docs-only 提交的 `provenance_documentation_sha` 登记，以及最终
`phase_2_complete` 决策。S11 预期提交为
`docs(repository): record P2-R6 and Phase 2 handoff`。文档不能把缺失或失败的
S10 字段改写成 pass。本提交不回填自己的 SHA。
