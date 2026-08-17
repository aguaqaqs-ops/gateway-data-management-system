# P2-R6-S9 Step 3 — Exact no-ignore source regression

状态：`pass`

日期：2026-08-17

本记录是 S9-3 在冻结 candidate `2ef884278b4998dde1e5fe224532c89b7a0cd73a` 上的
无 ignore 源码全量回归。权威命令一次通过（环境修正后的 verbose 证据重跑），无失败、
无未分类 skip、无源码修复。没有重跑 W1/W2、S10 Compose/production image 或
v8。证据写在文档 worktree，未进入 candidate checkout。

S9-5 独立审核 [p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md)
`review_status: fail` **保留**；本步只补权威日志的逐条 PASSED 与 per-node 库存，
不覆盖该失败审核，也不进入新的 S9-5。

权威计划：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §5
S9-2：[p2-r6-s9-step-2-provisional-image.md](p2-r6-s9-step-2-provisional-image.md)
对照基线：[p2-r6-s8-step-4-source-full-regression-rerun.md](p2-r6-s8-step-4-source-full-regression-rerun.md)
权威日志：[p2-r6-s9-step-3-run-tests.log](p2-r6-s9-step-3-run-tests.log)
quiet 通过日志（已作废为权威 nodeid 证据，未删除）：[p2-r6-s9-step-3-run-tests.quiet.log](p2-r6-s9-step-3-run-tests.quiet.log)
首次失败日志：[p2-r6-s9-step-3-run-tests.fail-1.log](p2-r6-s9-step-3-run-tests.fail-1.log)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:local
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
worktree_clean_before: yes
worktree_clean_after: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
phase_2_complete: no
```

远端 worktree `/home/issac/gateway-gate-2ef884278b49` 与本地
`/root/gateway-s9-candidate-2ef88427` 在命令前后 `git status --porcelain` 均为空。
Identity helper 与 S9-2 image labels 一致。`gateway-repository-service:local` 与
`:2ef884278b49` 指向同一 immutable ID。verbose 重跑未重建 image。

## Authoritative command

在远端 candidate checkout、S7 同一 gate-host `issac@10.10.60.4` 上执行。未附加
`-m`、`-k`、`--ignore`、`--ignore-glob`、xfail、skip、retry 或 accepted-flake。
`run-tests.sh` 把 `"$@"` 透传到每段 pytest。本步只传 reporting 参数 `-vv -s`：
脚本写死的 `pytest -q` 与两级 `-v` 抵消为 verbose，于是每条测试打印
`nodeid` 与随后的 `PASSED`；`-s` 让 harness 的 `teardown_scan` /
`residual_inventory` 进入权威日志。未改脚本、未改 candidate。

```bash
./vnext/scripts/run-tests.sh -vv -s
```

candidate-bound image 通过默认 tag `:local` 绑定，而不是用
`GATEWAY_REPOSITORY_SERVICE_IMAGE` 覆盖整个六段套件（见 Repair ledger）。
Docker 测试的 token `chown` 需要 host root；整条权威命令经 S9-2 同一 `nsenter`
包装执行。日志 tee 在 candidate 外 `/tmp/s9-3-run-tests.verbose.log`，再拷入文档
worktree。

quiet 通过日志因 S9-5 P1（合计推断、无逐条 PASSED / per-node 库存）作废为权威
nodeid 证据，已改名为 `p2-r6-s9-step-3-run-tests.quiet.log`，**不删除**。

```text
run_started_at: 2026-08-17T00:22:32Z
run_finished_at: 2026-08-17T00:28:57Z
wall_clock: 385s (about 6m25s)
authoritative_exit_code: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-gate-2ef884278b49
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
service_local_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
pytest: 9.1.1
python: 3.14.6
authoritative_command: ./vnext/scripts/run-tests.sh -vv -s
```

## Package commands and counts

collected 对四快包等于 passed+skipped+failed。repository_service parallel
`16 workers [1639 items]`；serial `collected 1844 items / 1639 deselected / 205 selected`。
两段之和 1844 即无 ignore service total。

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q -vv -s` | 242 | 242 | 0 | 0 | 0.99s |
| repository_contracts | `uv run pytest -q -vv -s` | 152 | 152 | 0 | 0 | 0.26s |
| repository_client | `uv run pytest -q -vv -s` | 154 | 154 | 0 | 0 | 1.24s |
| backend | `uv run pytest -q -vv -s` | 35 | 35 | 0 | 0 | 1.26s |
| repository_service parallel | `uv run pytest -q -m "not serial" -vv -s` | 1639 | 1638 | 1 | 0 | 59.96s |
| repository_service serial | `uv run pytest -q -m serial -n 0 -vv -s` | 205 | 205 | 0 | 0 | 314.90s |

相对 S8-4 rerun（三 ignore：parallel 1639 / serial 197 / service 1836）：serial
+8，service total 1844。四快包 counts 不变。backend 仍有 1 个
`StarletteDeprecationWarning`（`fastapi/testclient.py` 建议 `httpx2`），不是失败。

## Eight Docker nodeids

权威日志 serial 段对每条 nodeid 打印 stdout，随后单独一行 `PASSED`。以下为原文摘录，
不是 `--collect-only`、不是合计算术、也不是单独 8 条 `-v -s` 补跑。

### 1. import — `test_compose_repository_service_import_restart_replay`

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay compose_project=gateway-p2r6-s7-import-fa17effe0a8f
teardown_scan project=gateway-p2r6-s7-import-fa17effe0a8f container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-import-fa17effe0a8f containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 2. inside — `test_compose_remote_client_commit_pinned_read_inside_network`

```text
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network compose_project=gateway-p2r6-s7-inside-b4b7fe6e381d
teardown_scan project=gateway-p2r6-s7-inside-b4b7fe6e381d container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-inside-b4b7fe6e381d containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 3. gatehost — `test_compose_remote_client_commit_pinned_read_from_gate_host`

```text
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host compose_project=gateway-p2r6-s7-gatehost-26ce6471cc97
teardown_scan project=gateway-p2r6-s7-gatehost-26ce6471cc97 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-gatehost-26ce6471cc97 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 4. lifecycle + restored — `test_compose_repository_service_fresh_restart_restored_lifecycle`

该 nodeid 分配两个 project；两条库存均为 0。

```text
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle compose_project=gateway-p2r6-s7-lifecycle-56146264fa31,gateway-p2r6-s7-restored-f23742b06d3c
teardown_scan project=gateway-p2r6-s7-restored-f23742b06d3c container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restored-f23742b06d3c containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
teardown_scan project=gateway-p2r6-s7-lifecycle-56146264fa31 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-lifecycle-56146264fa31 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 5. readiness — `test_compose_missing_readiness_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up teardown_scan project=gateway-p2r6-s7-readiness-d9952172631d container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-readiness-d9952172631d containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 6. wrongtoken — `test_compose_wrong_token_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up teardown_scan project=gateway-p2r6-s7-wrongtoken-cb7e3b068ab3 container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-wrongtoken-cb7e3b068ab3 containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 7. wrongnet — `test_compose_wrong_network_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up teardown_scan project=gateway-p2r6-s7-wrongnet-79987bc30abc container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-wrongnet-79987bc30abc containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

### 8. restoreprobe — `test_compose_non_empty_restore_target_cleans_up`

```text
tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up teardown_scan project=gateway-p2r6-s7-restoreprobe-9ab92b4fb00c container_dolt=0 query_temps=0
residual_inventory project=gateway-p2r6-s7-restoreprobe-9ab92b4fb00c containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0
PASSED
```

per-node 库存字段：`containers` / `networks` / `volumes`（Docker 对象）、
`dolt_delta` / `check_temp_homes`（Dolt / query-temp）、`client_pids` /
`host_threads`（进程/线程）、`work_root_dirs`（work-root）。上表九条
`residual_inventory`（restored-lifecycle 两条）全部为 0。

运行后 `gateway-p2r6-*` container/network/volume = 0。image ID 未因
`ensure_*_image()` 重建。

## Skip classification

权威日志原文：

```text
[gw7] SKIPPED tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
```

| nodeid | suite | reason | class |
| --- | --- | --- | --- |
| `tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup` | repository_service parallel | `GATEWAY_P2R1_TARGET_CONTAINER != "1"`；`reason: runs only inside the delegated target container` | expected; not an S9 required Docker nodeid |

权威命令 parallel 段 `1638 passed, 1 skipped` 与此一致。无 Dolt-missing skip。无其他 skip。

## Repair ledger

第一次执行把 `GATEWAY_REPOSITORY_SERVICE_IMAGE=gateway-repository-service:2ef884278b49`
导出到整条 `run-tests.sh`。parallel unit
`test_ensure_repository_service_image_*` 断言返回值等于默认 tag
`gateway-repository-service:local`，因此失败。这不是 candidate 源码缺陷。失败日志
保留为 `p2-r6-s9-step-3-run-tests.fail-1.log`。随后的 quiet 通过日志因缺少逐条
PASSED 被 S9-5 P1 作废为权威 nodeid 证据；本步在同一 candidate/image 上以
reporting-only `-vv -s` 重跑权威入口。

```yaml
first_failure: preserved in p2-r6-s9-step-3-run-tests.fail-1.log
first_failure_nodeids: tests/test_compose_build_harness.py::test_ensure_repository_service_image_rebuilds_when_labels_stale
  and test_ensure_repository_service_image_skips_rebuild_when_labels_match
first_failure_counts: parallel 2 failed, 1636 passed, 1 skipped
environment_repairs: retag :local to candidate digest; unset GATEWAY_REPOSITORY_SERVICE_IMAGE
source_or_build_input_repairs: none
owning_scope_repair: S9-3 environment only; docker tag candidate image as
  gateway-repository-service:local (same Id sha256:4b8f88ed…); unset
  GATEWAY_REPOSITORY_SERVICE_IMAGE; rerun exact no-ignore command with reporting
  passthrough -vv -s
source_or_build_input_changed: no
container_boundary_touched: no
rerun_of_authoritative_command_after_repair: yes
repairs: environment-only
repairs_to_production_or_tests: none
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
git_diff_check: pass
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
identity: unchanged from S9-2
```

`.venv` 由 root `uv run` 创建，位于 gitignore / identity `excluded_dir_names`，未进入
porcelain。

## Docker / Compose decision

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no (S9-2 image reused; :local retagged to same Id)
Reason: no-ignore source regression on unchanged candidate-bound provisional image
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id:
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10 final production image/provenance; S10 four Compose nodeids;
  W1/W2 and v8 formal --runs 5
Required execution point: S9-4 packet reconstruction; new-conversation S9-5; S10 final production
```

S9 provisional image 不是 S10 final production image。四条 Compose nodeid 在本步作为
no-ignore source gate 的一部分已经 passed；S10 仍须在 sealed candidate 的 production
image 上重跑它们。

## Exit

```yaml
no_ignore_source_regression: pass
authoritative_exit_code: 0
all_eight_docker_nodeids: pass
unexpected_skip_or_failure: no
first_failure: preserved in p2-r6-s9-step-3-run-tests.fail-1.log
environment_repairs: retag :local to candidate digest; unset GATEWAY_REPOSITORY_SERVICE_IMAGE
source_or_build_input_repairs: none
repairs: environment-only
source_or_build_input_changed: no
image_matches_build_context: true
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
S9_exit: no
S10_ready: no
production_retest_required: yes
phase_2_complete: no
next: S9-4 hygiene and candidate seal packet
```

下一步在 source/image 不变时重建 old-reference、provenance 和 clean-source
packet。本记录不授权 candidate seal、S9 exit 或 Phase 2 completion。失败的 S9-5
审核保留；新的 S9-5 必须新开对话。
