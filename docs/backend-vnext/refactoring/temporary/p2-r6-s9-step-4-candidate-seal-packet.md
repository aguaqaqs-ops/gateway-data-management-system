# P2-R6-S9 Step 4 — Hygiene and candidate seal packet

状态：`pass`（packet complete；不授予 independent seal review、S9 exit 或 S10）

日期：2026-08-17

本记录在 S9-3 证据重跑（source/build-input/image 不变）之后重建 candidate seal
packet：五组 old-reference 搜索与分类、identity 重算、clean-source、八条 nodeid
PASSED 与 per-node 库存、zero-residual。未修改 candidate。未删除 historical
文档。未宣称 `candidate_seal`。失败的 S9-5
[p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md)
`review_status: fail` 保留；本步不启动新的 S9-5。

权威计划：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §6
搜索原文：[P2 Versioned Repository Execution Checklist](../formal/plans/p2-versioned-repository-execution-checklist.md) §9
分类口径：[P2-R6 Operational Closure Execution Plan](../formal/plans/p2-r6-operational-closure-execution-plan.md) §9
S9-3：[p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md)
S9-2：[p2-r6-s9-step-2-provisional-image.md](p2-r6-s9-step-2-provisional-image.md)
对照：[p2-r6-s8-step-5-hygiene-rerun.md](p2-r6-s8-step-5-hygiene-rerun.md)
失败 S9-5：[p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md)

原始命中：[p2-r6-s9-step-4-old-reference-raw/](p2-r6-s9-step-4-old-reference-raw/)

## Entry identity

S9-3 证据重跑之后、本步重算，与 S9-2 labels / 新 S9-3 权威日志一致：

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:local
service_image_also_tagged: gateway-repository-service:2ef884278b49
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
image_matches_build_context: true
source_change_after_s9_3: no
worktree_clean: yes
phase_2_complete: no
```

本地 `/root/gateway-s9-candidate-2ef88427` 与远端
`/home/issac/gateway-gate-2ef884278b49` 的 helper 输出相同。`git diff --check`
pass。candidate `vnext/` 相对 `2ef88427` 无改动、无未跟踪文件。

## Five old-reference searches

在文档 worktree 仓库根执行 checklist §9 五条精确命令。`rg` 遵守 gitignore，未加
`--hidden` / `-uu` / 额外 `--glob`。新 S9-3 权威日志与重建 packet 会产生
self-hit，按 S8-5 口径分类。

```bash
rg -n "NONE \\| STRUCTURAL \\| FULL|completed_verification_level|SnapshotManifest" .
rg -n "PREPARED/APPLIED/VERIFIED|UNKNOWN/APPLIED|FailureDescriptor|FAILED_FINAL" .
rg -n "LAST_WRITE_WINS|CHECK_EXPECTED|table.?CAS|schema.?CAS|StoreKind|CurrentTableStore" .
rg -n "repository_path|run_dir|multipart|LATEST_AT_START|/v2/|compatibility adapter" .
rg -n "Repository wire JSON/gRPC|before_readback_verified|after_readback_verified" .
```

| group | raw file | hits | unclassified current production/test/CI/runbook old semantic |
| --- | --- | ---: | --- |
| 1 verification level | [g1-verification-level.txt](p2-r6-s9-step-4-old-reference-raw/g1-verification-level.txt) | 304 | none |
| 2 effect-state | [g2-effect-state.txt](p2-r6-s9-step-4-old-reference-raw/g2-effect-state.txt) | 480 | none |
| 3 CAS/store | [g3-cas-store.txt](p2-r6-s9-step-4-old-reference-raw/g3-cas-store.txt) | 1094 | none |
| 4 path/version | [g4-path-version.txt](p2-r6-s9-step-4-old-reference-raw/g4-path-version.txt) | 777 | none |
| 5 wire/readback | [g5-wire-readback.txt](p2-r6-s9-step-4-old-reference-raw/g5-wire-readback.txt) | 26 | none |

相对上一份 S9-4 packet（126 / 233 / 575 / 642 / 24）与 S8-5 rerun
（60 / 112 / 264 / 301 / 12），行数增加全部是：

- S8-5 原 raw 与 rerun raw 对自身命中的嵌套拷贝（self-hit）
- 本步 raw 写入同一文档树后被后续组再次命中
- S8-5 / 上一份 S9-4 证据文档引用的 `rg` 命令与分类摘录
- 新权威日志 [p2-r6-s9-step-3-run-tests.log](p2-r6-s9-step-3-run-tests.log) 的
  group 4 八行：否定 `/v2/` 路由、`run_dir` launcher、拒绝 `multipart` 的
  nodeid PASSED（negative / private，不是激活旧语义）

没有新的 `vnext/` production 旧语义。S9 design / execution plan / step 记录未引入
这五组模式的 current 旧语义命中。historical 文档未删。current / negative /
unrelated / historical 口径与 S8-5 相同。

### Group 1 — verification level

Current authority 使用 `FULL_SCAN`：ADR 0009、canonical-storage contract、P2
implementation design、R4 import design。Checklist §9 命令是 self-hit。

ADR 0008 的 `NONE | STRUCTURAL | FULL` 以及 phase-0 `SnapshotManifest`、phase-2
decision ledger / README / consumer-adequacy 中的旧 `FULL` 术语是 superseded
historical。无 `vnext/` 代码命中。

### Group 2 — effect-state

Current formal 命中是删除/禁止旧模型。Checklist 与计划中的同类 `rg` 是 self-hit。
`operations.md` / `glossary.md` 的 `FAILED_FINAL` 是其他 application capability。
phase-0 / phase-2 ledger 中的 `FailureDescriptor` 等是 historical。无生产代码激活
这些状态机。

### Group 3 — CAS/store

Current formal 命中均为 non-goal、reopen 或 future Current 说明。
`vnext/repository_service/README.md` 的 `public ref/table/schema CAS` 是否定清单，
不是激活实现。没有激活的 `StoreKind`、table/schema CAS 或 generic store。

### Group 4 — path/version

Production / 内部测试命中均为 private 变量、测试 helper 或明确拒绝，与 S8-5 相同：

- `runtime.py` `repository_path`：private layout
- `artifacts.py` 拒绝 multipart
- HTTP/Compose 测试断言无 `/v2/` route
- `target_gate.py` / `p2r1-target-launcher.sh` 的 `run_dir`：P2-R1 私有目录

权威日志中的八行是上述否定测试的 verbose PASSED 回显，归入同一 negative / private
口径。operations/flows/benchmark 的同名单词属于其他 application / benchmark 术语。
phase-2 `LATEST_AT_START` 是 historical。

### Group 5 — wire/readback

除 checklist 命令 self-hit 与 S8 hygiene/raw 拷贝外，只命中 phase-0
`before_readback_verified` / `after_readback_verified`。当前 Repository wire 没有
旧 JSON/gRPC 或 before/after readback 状态。

## Dead-symbol consumer search

```yaml
s9_deletions_considered: none
consumer_search_before_delete: not_applicable
r5_cleanup_06: carried_closed
s3_disposition_reopened: no
```

S9 不删除 production helper。S8 对 `vnext/` 的唯一改动仍是 marker 分类，不匹配这
五组删除语义。

## Eight Docker nodeids and per-node inventory

权威命令 `./vnext/scripts/run-tests.sh -vv -s`，`exit_code=0`。quiet 日志
[p2-r6-s9-step-3-run-tests.quiet.log](p2-r6-s9-step-3-run-tests.quiet.log)
已作废为权威 nodeid 证据，未删除。以下摘自新权威日志，不是合计推断。

| role | nodeid | project(s) | residual_inventory |
| --- | --- | --- | --- |
| import | `tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay` | `gateway-p2r6-s7-import-fa17effe0a8f` | containers=0 networks=0 volumes=0 hold=0 dolt_delta=0 check_temp_homes=0 client_pids=0 host_threads=0 work_root_dirs=0 |
| inside | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network` | `gateway-p2r6-s7-inside-b4b7fe6e381d` | same zeros |
| gatehost | `tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host` | `gateway-p2r6-s7-gatehost-26ce6471cc97` | same zeros |
| lifecycle | `tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle` | `gateway-p2r6-s7-lifecycle-56146264fa31` | same zeros |
| restored | （同上 nodeid 的第二 project） | `gateway-p2r6-s7-restored-f23742b06d3c` | same zeros |
| readiness | `tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up` | `gateway-p2r6-s7-readiness-d9952172631d` | same zeros |
| wrongtoken | `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up` | `gateway-p2r6-s7-wrongtoken-cb7e3b068ab3` | same zeros |
| wrongnet | `tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up` | `gateway-p2r6-s7-wrongnet-79987bc30abc` | same zeros |
| restoreprobe | `tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up` | `gateway-p2r6-s7-restoreprobe-9ab92b4fb00c` | same zeros |

每条 nodeid 在权威日志中于 stdout / `teardown_scan` / `residual_inventory` 之后单独
一行 `PASSED`。`teardown_scan` 的 `container_dolt=0 query_temps=0` 与上表一致。
原文见 S9-3。

## Leak audit

S9-3 权威命令结束后、本步重核（gate-host `10.10.60.4`）：

```text
residual_inventory gate=s9-4-packet-rebuild
  gateway-p2r6 containers=0 networks=0 volumes=0
  dolt_pids=0 query_temps=0 check_temp_homes=0 work_root_gateway=0
  candidate_porcelain=empty
```

```yaml
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
git_diff_check: pass
broad_marker_exclusion: no
exact_no_ignore_command: ./vnext/scripts/run-tests.sh -vv -s
stale_source_claim: no
missing_nodeid_count: no
undocumented_current_old_reference: no
first_failure: preserved in p2-r6-s9-step-3-run-tests.fail-1.log
environment_repairs: retag :local to candidate digest; unset GATEWAY_REPOSITORY_SERVICE_IMAGE
source_or_build_input_repairs: none
repairs: environment-only
```

## Carried S9-3 counts

| suite | collected | passed | skipped | failed | duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | 242 | 242 | 0 | 0 | 0.99s |
| repository_contracts | 152 | 152 | 0 | 0 | 0.26s |
| repository_client | 154 | 154 | 0 | 0 | 1.24s |
| backend | 35 | 35 | 0 | 0 | 1.26s |
| repository_service parallel | 1639 | 1638 | 1 | 0 | 59.96s |
| repository_service serial | 205 | 205 | 0 | 0 | 314.90s |

service total 1844 = 1639 + 205。唯一 skip：delegated-target cgroup smoke。八个
Docker nodeid 全部由权威命令逐条报告 PASSED。权威命令 `exit_code=0`。

## Seal packet (external to candidate)

| item | value / location |
| --- | --- |
| candidate_sha | `2ef884278b4998dde1e5fe224532c89b7a0cd73a` |
| build_input_revision | `3e4bd1fca0e52a0497bbc5a7bf69071a744fd952` |
| source_tree_sha256 | `sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686` |
| service lock | `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` |
| client lock | `6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| service image id | `sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6` |
| client image id | `sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b` |
| host-runner identity | `host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954` |
| no-ignore command | `./vnext/scripts/run-tests.sh -vv -s` |
| no-ignore log | [p2-r6-s9-step-3-run-tests.log](p2-r6-s9-step-3-run-tests.log) |
| quiet log (superseded for nodeid evidence) | [p2-r6-s9-step-3-run-tests.quiet.log](p2-r6-s9-step-3-run-tests.quiet.log) |
| first-failure log | [p2-r6-s9-step-3-run-tests.fail-1.log](p2-r6-s9-step-3-run-tests.fail-1.log) |
| eight docker nodeids | 八条 PASSED + per-node 库存；见上文与 S9-3 |
| skip classification | cgroup smoke only |
| old-reference raw | `p2-r6-s9-step-4-old-reference-raw/` |
| clean source | candidate porcelain empty；`git diff --check` pass |
| zero residual | yes（aggregate 与 per-node） |
| repairs | environment-only；`source_or_build_input_repairs: none` |
| S8 carried | parked-Dolt unit、五包 static、worker convergence、三 ignore 全量、old-reference rerun、independent rereview |
| failed S9-5 | preserve `review_status: fail`；不覆盖 |
| deferred S10 | final production image/provenance；四条 Compose nodeid；W1/W2；Candidate A v8 formal `--runs 5` |

`71da5061` 及本文件仍是 documentation-only，不是 `CANDIDATE_SHA`。S9 provisional
image 不是 S10 final production image。

## Docker / Compose decision

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: hygiene searches, identity recomputation and documentation packet only
Last verified image revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id:
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10 final production image/provenance; S10 four Compose nodeids;
  W1/W2 and v8 formal --runs 5
Required execution point: S9-5 independent candidate seal review in a new conversation
```

## Exit

```yaml
old_reference_classification: pass
identity_matches_s9_2_and_s9_3: yes
git_diff_check: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
candidate_seal_packet: complete
independent_seal_review: required_at_s9_5
first_failure: preserved in p2-r6-s9-step-3-run-tests.fail-1.log
environment_repairs: retag :local to candidate digest; unset GATEWAY_REPOSITORY_SERVICE_IMAGE
source_or_build_input_repairs: none
repairs: environment-only
production_retest_required: yes
phase_2_complete: no
next: S9-5 independent candidate seal review in a new conversation
```

下一步必须**新开对话**做只读 S9-5。审核人读新权威日志里的 PASSED 行与 per-node
库存，而不是合计推断。本记录不授权 candidate seal、S9 exit 或 Phase 2
completion。
