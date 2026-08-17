# P2-R6-S10 Step 7 — Candidate A W0 target smoke

状态：`pass`（仅 S10-7 Candidate A W0 diagnostic smoke；attempt-5；不授予 v8 formal、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-6 身份与 final image ID 不变之后，于密封 candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` 的干净 detached checkout 上，经
installed target launcher 执行 Candidate A `--v8-a-w0-smoke`。attempt-5
`smoke_status=pass`，`diagnostic_only=true`，`formal_decision=false`。attempt-1..4
失败记录与 quarantine **未覆盖**、未改写成 pass。未修改 candidate、Compose 或
image。本会话不进入 S10-8。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §9
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.5
Launcher README：`vnext/deploy/p2r1-cache/README.md` `--v8-a-w0-smoke`
上游：[p2-r6-s10-step-6-w1-w2-production-repeat.md](p2-r6-s10-step-6-w1-w2-production-repeat.md)

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
attempt_id: attempt-5
prior_attempts: attempt-1..4 preserved fail
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
smoke_status: pass
diagnostic_only: true
formal_decision: false
s10_7_status: pass
phase_2_complete: no
```

远端 `/home/issac/gateway-s10-candidate-2ef88427` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
`:p2-r6-final` 与 `:local` 仍指向 `sha256:4b8f88ed…2a2e4a2be6`。daemon 仍是
`Name=arch ID=dc91db82-3d49-41a4-a63c-f23dda721890`，CgroupDriver=`systemd`。
retained cache `http://172.17.0.1:18080` HTTP 200。installed launcher 与 candidate
字节一致（v3）。`GATEWAY_REPOSITORY_SERVICE_IMAGE` 未设置。

本步 **不是** S10-8 evidence，不能选择 provider。

## Authoritative command

设计文档写 `GATEWAY_P2R1_IMAGE=gateway-repository-service:p2-r6-final`。installed
launcher 拒绝 tag-only（`formal image reference must be an immutable sha256 ID`）。
attempt-5 在 fail-closed 确认 tag 解析为 S10-4 ID 后传入 digest：

```bash
env \
  GATEWAY_P2R1_REPO_ROOT=/home/issac/gateway-s10-candidate-2ef88427 \
  GATEWAY_P2R1_IMAGE=sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6 \
  GATEWAY_P2R1_CACHE_CONDITION=retained-dependency-cache \
  /usr/local/libexec/gateway-p2r1-target-launcher.sh \
  --output /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/s10-7/attempt-5/a-w0.jsonl \
  --v8-a-w0-smoke
```

未附加 `--v8-formal`、`--runs`、`--diagnostic`、`--workloads`、`--candidates` 或
`--reserved-b-w0-smoke`。

本会话无 TTY，`sudo -n` 失败。与 S10-5/S10-6 相同，经 `alpine:3.20` `nsenter -t 1
-m -u -i -n -p` 以 host root 执行。helper image 不是 candidate image。launcher
只要求 `id -u == 0`。

```text
run_started_at: 2026-08-17T07:04:21Z
run_finished_at: 2026-08-17T07:04:28Z
nsenter_started_at: 2026-08-17T07:04:21Z
nsenter_finished_at: 2026-08-17T07:04:28Z
wall_clock: ~7s
launcher_exit: 0
WRAPPER_EXIT: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-s10-candidate-2ef88427
run_id: 20260817150422_3140754
compose_project: gateway-p2r1-20260817150422_3140754
bound_tag: gateway-repository-service:p2-r6-final
image_ref_kind: immutable_sha256
```

## Smoke gates (attempt-5)

raw JSONL 1 行、summary、Markdown 交叉核对，41 项 fail-closed 全过。

| gate | result |
| --- | --- |
| `smoke_status` | `pass` |
| `diagnostic_only` / `formal_decision` / `formal_status` | `true` / `false` / `no-go` |
| `decision_kind` / `selected_provider` | `diagnostic` / `null` |
| records | 1 W0 warmup；Candidate A `diagnostic_only` / `not_evaluated` |
| Candidate B | `reserved_not_evaluated` |
| v8 batch | byte bound `1048576`；row bound `1024`；`batch_contract_valid=true` |
| correctness / error | `true` / `null`；execution/sample failures `0` |
| cgroup ceiling | `memory_limit_bytes=8589934592`；`effective_memory_limit_bytes=8589934592` |
| memory evidence | `coverage=available`；baseline + cgroup_stat coverage |
| storage | `storage_mount_verified=true`；named volume；XFS；layout v1 |
| image digest | `sha256:4b8f88ed…2be6` |
| build revision / lock / cache | candidate SHA；Service lock `6dc9659f…`；`retained-dependency-cache` |
| methodology | `p2-r1-audit-corrective-v8` |
| 66-record coverage | `complete=false`（1/30 normal，0/36 scaling）— **预期**，不是 S10-8 |

payload `347` bytes，max row `225`，`total_rows=6`。resource advisory
`within_reference`，`affects_formal_decision=false`。

summary 内历史 P2-R1 字段 `production_retest_required: false` **不是** S10 stage
字段；S10 仍为 `production_retest_required: yes`，直到 S10-11 seal。

## Repair ledger

```yaml
first_failure: attempt-1 launcher rejected tag-only GATEWAY_P2R1_IMAGE
environment_repairs:
  - attempt-2/3: root systemd has no HOME; git config --system --add safe.directory
      /home/issac/gateway-s10-candidate-2ef88427
  - attempt-4/5: runc 1.5.1/libpathrs cannot mkdir bind dest on cgroup2;
      host mkdir /sys/fs/cgroup/gateway-p2r1 as pre-existing mountpoint
source_or_build_input_repairs: none
repairs_to_production_or_tests: none
retry_as_pass: no
new_attempt_id: attempt-5
```

| attempt | outcome | preserved |
| --- | --- | --- |
| 1 | fail: tag-only image ref | log + wrapper；无 artifact |
| 2 | fail: systemd identity helper dubious ownership（`--global` 对无 HOME 不可见） | log + wrapper |
| 3 | fail: 同 attempt-2；已加 `--global` 仍失败 | log + journal + wrapper |
| 4 | fail: cgroup bind-mount mkdir EROFS；launcher quarantine | log + journal + wrapper + volume + staging |
| 5 | pass | raw 三件套 + log + wrapper |

## Cleanup inventory

attempt-5 成功 publication 后 launcher `down -v`。随后 stop 空的 per-run slice。
attempt-5 project 的 container / network / volume / runner unit / slice = 0。

保留（不是本 run 成功路径残留）：

- attempt-4 quarantine volume `gateway-p2r1-20260817150124_3123221_repository-data`
- attempt-4 staging `.../s10-7/.p2-r1-export-20260817150124_3123221.pbmVIg`
- 2026-08-03 历史 quarantine 三份 `gateway-p2r1-20260803*_repository-data`
- host 空 cgroup `/sys/fs/cgroup/gateway-p2r1`（runc 1.5.1 bind 挂载点；S10-8 仍需要）
- retained cache 与 final image tags

```text
a5_containers=0 a5_networks=0 a5_volumes=0
p2r6 containers=0 networks=0 volumes=0
dolt_pids=0 query_temps=0
git_status_porcelain: empty (local and remote candidate)
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
attempt-4 artifacts: preserved
```

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-7
remote_output: /var/lib/gateway/repository/audit-rerun/p2-r6-s10-20260817T015148Z/s10-7/attempt-5/
log_copied_to_docs_worktree: no
candidate_wrote_log: no
```

```text
ec9f11f890b535ed4d17c70e3d654c134924d53cf4553e1cf36d64a6e8ac4649  attempt-1/s10-7-w0.log
60dd102a7236a1797d6c297f4a7dc873e649d2a2a20f1d5f9095f2388ac49196  attempt-1/s10-7-w0-smoke.sh
02a8204f3c294162569e287797ed1c4b88855a7ce309cda4de1a60558f6d33af  attempt-2/s10-7-w0.log
0547f8e81c91ce2469dbeee81a87be08308b300afc296fb4426aa29009b5ee1c  attempt-2/s10-7-w0-smoke.sh
c9c4bf9f36659d9a679368a1a8ee92baf3451801fbf0d9f8e89b22e6cb3a88ae  attempt-3/journal.txt
2a315270a1517c60b401a4cef23ae3152fb514a13ae8c56b29103f33ebb13d7a  attempt-3/s10-7-w0.log
11d132b767dd968cf2a14da306be9ba58ac7fae9c31885223d293a9b4068797f  attempt-3/s10-7-w0-smoke.sh
f473f47bf9922841188dae3547337a1b575bc3996d12f9f5e2539d631a3382be  attempt-4/journal.txt
880c829022da4f6ea8b31c0faca032f711992e7e5349ae301d2149d0bc395b48  attempt-4/s10-7-w0.log
d16a22b5fd3e3f99269493a80d43237f3956b0f7a03f4e1edd48ab47d1754fee  attempt-4/s10-7-w0-smoke.sh
0720b5a1eec0fe5d9670d7757120490655436a125b2ebf1962b89b07796bdeab  attempt-5/a-w0.jsonl
72f1d5422d048d34b5195233224688950d5569696e25b5480f258c069a3c41b6  attempt-5/a-w0.summary.json
cd3beb8eb265a287c5f390c0a921d35ada3cbbc87285831213ac5c9812abe6bb  attempt-5/a-w0.md
0e2e1758ee98f0658b225b321f418a9dfb97a1f0a833735af8ecef440b17fc73  attempt-5/s10-7-w0.log
d24e0976eac599527f21ec1492c0f4cc563fd5729d76bf46035e251274890060  attempt-5/s10-7-w0-smoke.sh
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S10-4 final image reused; IDs unchanged)
Reason: S10-7 Candidate A W0 target smoke on unchanged final Service identity
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-8 Candidate A v8 formal --runs 5
Required execution point: S10-8 on this unchanged identity, launcher, cgroup/storage preflight and audit root
```

本步不单独改变 `container_validated_code_sha`（仍 deferred 到 v8 formal 完成）。

## Exit

```yaml
s10_7_status: pass
attempt_id: attempt-5
candidate_a_w0_smoke: pass
smoke_status: pass
diagnostic_only: true
formal_decision: false
formal_status: no-go
selected_provider: null
prior_attempts_1_to_4: preserved fail
retry_as_pass: no
identity_unchanged: yes
this_run_zero_residual: yes
attempt_4_quarantine_preserved: yes
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-8 Candidate A v8 formal --runs 5；仅当 launcher、image、checkout、cache、cgroup/storage preflight 与 audit root 不变时可在同会话继续
```

本记录不构成 v8 formal、S10 seal 或 Phase 2 completion。
