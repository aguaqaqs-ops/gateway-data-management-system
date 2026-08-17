# P2-R6-S10 Step 8 — Candidate A v8 formal

状态：`pass`（仅 S10-8 Candidate A 66-record v8 formal；attempt-1；不授予 S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 [S10-7 W0 smoke pass](p2-r6-s10-step-7-w0-smoke.md) 之后，于同一会话、同一
final image / launcher / checkout / cache / cgroup 挂载点上，执行唯一 Candidate A
v8 formal `--runs 5`。attempt-1 一次通过：`WRAPPER_EXIT=0`、`66/66`、
`formal_status=go`。未修改 candidate、Compose 或 image。本会话不进入 S10-9。
S10-7 smoke **不是**本步 evidence。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §10
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.5
上游：[p2-r6-s10-step-7-w0-smoke.md](p2-r6-s10-step-7-w0-smoke.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:p2-r6-final
service_image_also_tagged: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
installed_launcher_sha256: 2782a83f4465f1d9505a5347e1cc418ebd64f8fe73e2e9964d5235945da54a88
cache_condition: retained-dependency-cache
attempt_id: attempt-1
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
v8_records: 66
v8_formal_status: go
s10_8_status: pass
phase_2_complete: no
```

远端 `/home/issac/gateway-s10-candidate-2ef88427` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
`:p2-r6-final` 与 `:local` 仍指向 `sha256:4b8f88ed…2a2e4a2be6`。沿用 S10-7 环境：
nsenter/host-root、`git config --system safe.directory`、host
`/sys/fs/cgroup/gateway-p2r1` 挂载点、immutable image digest（非 tag-only）。

## Authoritative command

```bash
env \
  GATEWAY_P2R1_REPO_ROOT=/home/issac/gateway-s10-candidate-2ef88427 \
  GATEWAY_P2R1_IMAGE=sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6 \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/s10-8/p2-r1.jsonl \
  --v8-formal \
  --runs 5
```

未附加 `--v8-a-w0-smoke`、`--diagnostic`、`--workloads`、`--candidates` 或
`--reserved-b-w0-smoke`。远端 nohup + `alpine:3.20` nsenter；helper image 不是
candidate image。

```text
run_started_at: 2026-08-17T07:17:38Z
run_finished_at: 2026-08-17T09:37:17Z
nsenter_started_at: 2026-08-17T07:17:38Z
nsenter_finished_at: 2026-08-17T09:37:17Z
wall_clock: 2h 19min 39s (journal 2h 19min 37.309s; 历史参考约 2h20m，非验收阈值)
launcher_exit: 0
WRAPPER_EXIT: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-s10-candidate-2ef88427
run_id: 20260817151739_3215596
compose_project: gateway-p2r1-20260817151739_3215596
bound_tag: gateway-repository-service:p2-r6-final
image_ref_kind: immutable_sha256
```

## Formal gates (attempt-1)

raw JSONL 66 行、summary、Markdown 交叉核对，32 项 fail-closed 全过。

| gate | result |
| --- | --- |
| records | `66/66` unique；coverage complete；`record_set_valid=true` |
| normal / scaling | `30/30` / `36/36` |
| warm-ups / measured | `11` / `55` |
| execution / correctness / sample failures | `0` / `0` / `0` |
| Candidate A | `evaluated`；`hard_gate=true`；`result=pass`；selected |
| Candidate B | `reserved_not_evaluated` |
| `formal_status` / `formal_decision` | `go` / `true` |
| v8 batch | byte bound `1048576`；全部 raw `batch_contract_valid=true` |
| cgroup ceiling | 每条 `memory_limit_bytes=8589934592`；`effective >= 8GiB` |
| storage | `storage_mount_verified=true`；named volume；XFS |
| image / build / cache | S10-4 digest；candidate SHA；`retained-dependency-cache` |
| A provenance / memory / metadata / W2 split | 全部 complete |
| resource advisory | `within_reference`；`affects_formal_decision=false` |
| scale ratio | `warning`（advisory-only，不改变 hard-gate） |

observed max workflow cgroup peak `2702028800` bytes；ordinary reference
`2684354560`；boundary `3221225472`。summary `exceedances=[]` 且 status
`within_reference`。ratio observation `warning` 不构成 no-go。

summary 内历史 P2-R1 字段 `production_retest_required: true` **不是** S10 stage
字段；S10 在 seal 前仍为 `production_retest_required: yes`。`p2_r2_ready=true`
是 v8 artifact 字段，不单独关闭 Phase 2。

## Repair ledger

```yaml
first_failure: none
environment_repairs: none this step (carried S10-7 system git safe.directory + host cgroup mountpoint)
source_or_build_input_repairs: none
repairs_to_production_or_tests: none
retry_as_pass: no
attempt_id: attempt-1
```

## Cleanup inventory

成功 publication 后 launcher `down -v`。随后 stop 空的 per-run slice。本 run
container / network / volume / runner unit / slice = 0。

保留：

- S10-7 attempt-4 quarantine `gateway-p2r1-20260817150124_3123221_repository-data`
- 2026-08-03 历史三份 `gateway-p2r1-20260803*_repository-data`
- host 空 cgroup `/sys/fs/cgroup/gateway-p2r1`
- retained cache 与 final image tags
- S10-7 attempt-5 smoke artifacts

```text
a1_containers=0 a1_networks=0 a1_volumes=0
p2r6 containers=0 networks=0 volumes=0
dolt_pids=0
git_status_porcelain: empty (local and remote candidate)
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
```

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-8
remote_output: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/s10-8/
log_copied_to_docs_worktree: no
candidate_wrote_log: no
```

```text
9dcdd1b458ec96a7391dc5cb96619155c02edaa6e17d5cd763abf42bf1d0a256  attempt-1/p2-r1.jsonl
f530c36f331cc26e4c6fa8118a71ded8b0ca0d9d7225309f96ff9233cf327a4e  attempt-1/p2-r1.summary.json
0e2054c762073cfef093b75ea8159ffb72012c1bd28c5d05591c7e0bebf1ec57  attempt-1/p2-r1.md
1919a46b2cdf27ccf9143d71eecb791c291e4685d5769ad03a383ae4191eebf8  attempt-1/s10-8-v8.log
37a9ae904225efd31ede55eaf1c3a29909f7541cf5b25f0cb80a437b34384f23  attempt-1/s10-8-v8-formal.sh
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S10-4 final image reused; IDs unchanged)
Reason: S10-8 Candidate A v8 formal on unchanged final Service identity
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-9 final packet and zero-residual audit
Required execution point: S10-9 on this unchanged identity and v8 artifact set
```

本步不单独把 `container_validated_code_sha` 写成已 seal；仍等 S10-9 packet 与
S10-10/S10-11。

## Exit

```yaml
s10_8_status: pass
attempt_id: attempt-1
candidate_a_v8_formal: pass
v8_records: 66
v8_formal_status: go
selected_provider: candidate_a_offline_cli
candidate_b_status: reserved_not_evaluated
formal_decision: true
retry_as_pass: no
identity_unchanged: yes
this_run_zero_residual: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-9 final packet and zero-residual audit；身份与 evidence source 未变时可在同会话继续
```

本记录不构成 S10 seal 或 Phase 2 completion。
