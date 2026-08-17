# P2-R6-S10 Step 5 — Exact no-ignore full and Compose gate

状态：`pass`（仅 S10-5 no-ignore / Compose；不授予 W1/W2、v8、S10 exit 或 Phase 2）

日期：2026-08-17

本记录在 S10-4 final Service/Client 身份不变的前提下，于密封 candidate
`2ef884278b4998dde1e5fe224532c89b7a0cd73a` 的干净 detached checkout 上执行权威
`./vnext/scripts/run-tests.sh -vv -s`。一次通过：exit 0、六段 counts 与 S9 inventory
逐字相等、唯一已分类 delegated-target cgroup skip、八个 Docker-starting nodeid 在
serial 段原文 `PASSED` 且 per-node 库存为 0。未修改 source、test、dependency、
Dockerfile、Compose 或 lock；未单独补跑四条 Compose；未传输 W1/W2；未执行 v8。
权威日志在 external audit root，未写入 candidate。

权威计划：[P2-R6-S10 Exact-Candidate Production Gate Execution Plan](../formal/plans/p2-r6-s10-exact-candidate-production-gate-execution-plan.md) §7
权威设计：[P2-R6-S10 Exact-Candidate Production Gate Design](../formal/plans/p2-r6-s10-exact-candidate-production-gate-design.md) §3.3
S10-4：[p2-r6-s10-step-4-final-artifacts.md](p2-r6-s10-step-4-final-artifacts.md)
对照 S9-3：[p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md)

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:local
service_image_also_tagged: gateway-repository-service:p2-r6-final
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
phase_2_complete: no
```

远端 `/home/issac/gateway-s10-candidate-2ef88427` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
Identity helper 与 S10-4 labels 一致。`:p2-r6-final` 与 `:local` 指向同一 immutable
ID；`ensure_*_image()` 未重建。

## Authoritative command

在远端 candidate checkout、S7/S9 同一 gate-host `issac@10.10.60.4` 上执行。未附加
`-m`、`-k`、`--ignore`、`--ignore-glob`、xfail、skip、retry 或 accepted-flake。
`run-tests.sh` 把 `"$@"` 透传到每段 pytest。本步只传 reporting 参数 `-vv -s`。
candidate-bound image 通过默认 tag `:local`（已绑定 `p2-r6-final` 同一 ID），未导出
`GATEWAY_REPOSITORY_SERVICE_IMAGE`。

Docker 测试的 token `chown` 需要 host root；整条权威命令经 S9-3 同一 `nsenter`
包装执行。helper image `alpine:3.20` 仅用于 nsenter，不是 candidate image。日志 tee
在 candidate 外 `/tmp/p2-r6-s10-20260817T015148Z-s10-5-run-tests.log`，再拷入
external audit root。未把完整日志写入文档 worktree。

```bash
./vnext/scripts/run-tests.sh -vv -s
```

```text
run_started_at: 2026-08-17T04:39:07Z
run_finished_at: 2026-08-17T04:46:37Z
nsenter_started_at: 2026-08-17T04:39:07Z
nsenter_finished_at: 2026-08-17T04:46:38Z
wall_clock: 451s (about 7m31s)
authoritative_exit_code: 0
WRAPPER_EXIT: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-s10-candidate-2ef88427
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
service_local_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
service_final_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_local_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
pytest: 9.1.1
python: 3.14.6
authoritative_command: ./vnext/scripts/run-tests.sh -vv -s
log_sha256: 59ae8de26c5a8e1b68d1af0a0308c5c721cc825b9d236dc4b98cd0c92983f2c7
log_bytes: 459573
wrapper_sha256: e44ee897e467498d0ab558a46ada032cd35f9b420254859ed2f347f5b712fd3b
```

## Package commands and counts

collected 对四快包等于 passed。repository_service parallel `16 workers [1639 items]`；
serial `collected 1844 items / 1639 deselected / 205 selected`。两段之和 1844 即无
ignore service total。与 S9 seal inventory 一致。

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q -vv -s` | 242 | 242 | 0 | 0 | 1.19s |
| repository_contracts | `uv run pytest -q -vv -s` | 152 | 152 | 0 | 0 | 0.29s |
| repository_client | `uv run pytest -q -vv -s` | 154 | 154 | 0 | 0 | 3.00s |
| backend | `uv run pytest -q -vv -s` | 35 | 35 | 0 | 0 | 1.37s |
| repository_service parallel | `uv run pytest -q -m "not serial" -vv -s` | 1639 | 1638 | 1 | 0 | 65.51s |
| repository_service serial | `uv run pytest -q -m serial -n 0 -vv -s` | 205 | 205 | 0 | 0 | 319.62s |

backend 仍有 1 个 warning（S9 同类 `StarletteDeprecationWarning`），不是失败。权威日志
无 `XFAIL`、无 `--ignore`、无 retry/flake。

## Eight Docker nodeids

权威日志 serial 段对每条 nodeid 打印 stdout，随后单独一行 `PASSED`。以下为原文摘录，
不是 `--collect-only`、不是合计算术、也不是单独 8 条 `-v -s` 补跑。

### 1. import — `test_compose_repository_service_import_restart_replay`

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay compose_project=gateway-p2r6-s7-import-ebff40d0c4a1
teardown_scan project=gateway-p2r6-s7-import-ebff40d0c4a1 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-import-ebff40d0c4a1 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 2. inside — `test_compose_remote_client_commit_pinned_read_inside_network`

```text
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network compose_project=gateway-p2r6-s7-inside-8b957b303dde
service_image_id=sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_identity=sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
teardown_scan project=gateway-p2r6-s7-inside-8b957b303dde container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-inside-8b957b303dde containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 3. gatehost — `test_compose_remote_client_commit_pinned_read_from_gate_host`

```text
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host compose_project=gateway-p2r6-s7-gatehost-240e0dc53007
service_image_id=sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_identity=host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
teardown_scan project=gateway-p2r6-s7-gatehost-240e0dc53007 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-gatehost-240e0dc53007 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 4. lifecycle + restored — `test_compose_repository_service_fresh_restart_restored_lifecycle`

该 nodeid 分配两个 project；两条库存均为 0。

```text
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle compose_project=gateway-p2r6-s7-lifecycle-fe83a85882df,gateway-p2r6-s7-restored-230698530dd8
service_image_id=sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_identity=host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
teardown_scan project=gateway-p2r6-s7-restored-230698530dd8 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restored-230698530dd8 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
teardown_scan project=gateway-p2r6-s7-lifecycle-fe83a85882df container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-lifecycle-fe83a85882df containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 5. readiness — `test_compose_missing_readiness_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up teardown_scan project=gateway-p2r6-s7-readiness-84ee1c6d3308 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-readiness-84ee1c6d3308 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 6. wrongtoken — `test_compose_wrong_token_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up teardown_scan project=gateway-p2r6-s7-wrongtoken-bdd1ec08a6be container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-wrongtoken-bdd1ec08a6be containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 7. wrongnet — `test_compose_wrong_network_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up teardown_scan project=gateway-p2r6-s7-wrongnet-3e95578e2f37 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-wrongnet-3e95578e2f37 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 8. restoreprobe — `test_compose_non_empty_restore_target_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up teardown_scan project=gateway-p2r6-s7-restoreprobe-7d09c3d99abf container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restoreprobe-7d09c3d99abf containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

前四条是 S10 Compose nodeid，均绑定 S10-4 final Service ID
`sha256:4b8f88ed…2a2e4a2be6`（import 段未打印 `service_image_id=`，但使用
`ensure_repository_service_image()` 默认 `:local`；命令后两 tag ID 未变）。inside
绑定 Client image ID `sha256:4a6cacec…c384ef1b`；gate-host / lifecycle 绑定
S10-4 `host_runner_identity`。九条 `residual_inventory`（restored-lifecycle 两条）
全部为 0。未另跑 targeted four-node 命令。

## Skip classification

权威日志原文（全文仅此一条 `SKIPPED`）：

```text
[gw3] SKIPPED tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
```

| nodeid | suite | reason | class |
| --- | --- | --- | --- |
| `tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup` | repository_service parallel | `GATEWAY_P2R1_TARGET_CONTAINER != "1"`；`reason: runs only inside the delegated target container` | expected; not an S10 required Docker nodeid |

权威命令 parallel 段 `1638 passed, 1 skipped` 与此一致。无 Dolt-missing skip。无其他 skip。
该环境能力由 S10-7/S10-8 target 执行关闭。

## Repair ledger

```yaml
first_failure: none
environment_repairs: none
source_or_build_input_repairs: none
repairs: none
repairs_to_production_or_tests: none
source_or_build_input_changed: no
container_boundary_touched: no
rerun_of_authoritative_command_after_repair: no
```

## Cleanup inventory

权威命令结束后（gate-host）：

```text
gateway-p2r6 containers=0 networks=0 volumes=0
dolt_pids=0
query-*.sql=0
snapshot-check-dolt homes=0
work_root_gateway=0
git_status_porcelain: empty
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
identity: unchanged from S10-4
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
```

`.venv` 由 root `uv run` 创建，位于 gitignore / identity `excluded_dir_names`，未进入
porcelain。

## External audit artifacts

```text
local_audit_root: /root/gateway-s10-audit/p2-r6-s10-20260817T015148Z/artifacts/s10-5
remote_log: /tmp/p2-r6-s10-20260817T015148Z-s10-5-run-tests.log
log_copied_to_docs_worktree: no
candidate_wrote_log: no
```

```text
59ae8de26c5a8e1b68d1af0a0308c5c721cc825b9d236dc4b98cd0c92983f2c7  p2-r6-s10-20260817T015148Z-s10-5-run-tests.log
e44ee897e467498d0ab558a46ada032cd35f9b420254859ed2f347f5b712fd3b  s10-5-run-tests.sh
```

## Docker / Compose decision

```text
Current HEAD: 0f9536c21a9ea789e4c5bc332e77b58efdf54c47
Source candidate: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S10-4 final image reused; IDs unchanged)
Reason: exact no-ignore / Compose gate on unchanged final Service/Client identity
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 / sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10-6 W1 medium/W2 with adapter SHA 6282df80…827ebf; S10-7/S10-8 Candidate A W0/v8 formal
Required execution point: S10-6 on this unchanged identity and reviewed adapter
```

本步不改变 `container_validated_code_sha`（仍 deferred 到 W1/W2+v8 完成）。四条
Compose 已作为 no-ignore 命令的一部分在 final image 上 passed，不得再 targeted 重跑。

## Exit

```yaml
s10_5_status: pass
no_ignore_full_gate: pass
four_compose_nodeids: pass
authoritative_exit_code: 0
all_eight_docker_nodeids: pass
unexpected_skip_or_failure: no
repair_ledger: none
image_matches_build_context: true
client_image_matches: true
worktree_clean: yes
zero_owned_gateway_p2r6_residual: yes
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
container_validated_code_sha: deferred
S10_exit: no
S11_ready: no
production_retest_required: yes
phase_2_complete: no
next: S10-6 W1 medium and W2 production repeat on this unchanged identity/adapter
```

S10-6 必须继续使用：

```text
GATEWAY_REPOSITORY_SERVICE_IMAGE unset
image: gateway-repository-service:local
  == gateway-repository-service:p2-r6-final
  == sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
  == sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
remote worktree: /home/issac/gateway-s10-candidate-2ef88427
gate-host: issac@10.10.60.4
adapter_sha256: 6282df8089644befdd66ac1d1381d81b2425c32167e71ea8a6140cac46827ebf
```

同一会话仅在 candidate、final image IDs、reviewed adapter SHA、topology 与 baseline
全程不变时可以继续到 S10-6。本记录本身不构成 W1/W2 production、v8 formal、S10 seal
或 Phase 2 completion。
