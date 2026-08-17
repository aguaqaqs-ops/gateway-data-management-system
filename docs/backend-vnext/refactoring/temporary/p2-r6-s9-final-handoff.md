# P2-R6-S9 — External candidate seal and S9 handoff

状态：`pass`

日期：2026-08-17

本记录是 S9-6 在 S9-5 rereview `allow_s9_seal: yes` 之后的 documentation-only
external seal 与 S10-ready handoff。未修改 production code、Contract、snapshot
语义、Dockerfile、Compose、lock、entrypoint 或 candidate checkout。未重建
image。未跑 pytest、Dolt、Docker、W1/W2 或 S10 production gate。未打
`p2-r6-final` tag，不宣称 Phase 2 完成。本文件的 docs-only 提交不是
`validated_code_sha`，也不是 `CANDIDATE_SHA`。

权威步骤：[P2-R6-S9 Final Candidate Seal Execution Plan](../formal/plans/p2-r6-s9-final-candidate-seal-execution-plan.md) §8–§9
权威设计：[P2-R6-S9 Final Candidate Seal Design](../formal/plans/p2-r6-s9-final-candidate-seal-design.md)
S9-5 放行：[p2-r6-s9-candidate-seal-review-rerun.md](p2-r6-s9-candidate-seal-review-rerun.md)
保留的失败审核：[p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md)
Seal packet：[p2-r6-s9-step-4-candidate-seal-packet.md](p2-r6-s9-step-4-candidate-seal-packet.md)

## Identity

S9-6 开始时用 `git rev-parse` 取得文档 HEAD 与 candidate HEAD。文档 HEAD 与
S8 handoff `71da5061` 一致，是 documentation-only。Candidate checkout
`/root/gateway-s9-candidate-2ef88427` 仍为字面量 `2ef88427`，porcelain 空，
`git diff --check` pass。Identity helper 与 lock hash 与 S9-2 labels / S9-4
packet / S9-5 rereview 逐字段一致。

```yaml
branch: phase1/gate-ownership-repair
documentation_head_sha: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_handoff_head: 71da506171d01bbccdf2c54137949cdd0bff234e
s8_handoff_head_docs_only: yes
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: deferred
build_input_revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
source_tree_sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
service_uv_lock_sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_uv_lock_sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
service_image: gateway-repository-service:local
service_image_also_tagged: gateway-repository-service:2ef884278b49
service_image_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
client_image: gateway-repository-client-e2e:local
client_image_id: sha256:4a6cacec7b4e5e24b45a7f569822e8e0e0a930904a6d13b6145e1c18c384ef1b
host_runner_identity: host-runner:candidate=2ef884278b4998dde1e5fe224532c89b7a0cd73a;client_uv_lock_sha256=6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_entry_is_ancestor: yes
candidate_worktree: /root/gateway-s9-candidate-2ef88427
candidate_worktree_clean: yes
production_code_changed_in_s9: no
test_or_build_input_changed_in_s9: no
docker_or_compose_changed_in_s9: no
public_contract_change: no
phase_2_complete: no
```

`validated_code_sha` / `candidate_sha` 仍是 S8 封印的干净 source SHA
`2ef88427`。S9 未改 `vnext/`。本文件的 docs-only 提交不改变
`validated_code_sha`、build-input revision、source-tree digest 或任何
container image identity。`71da5061` 与本 handoff 的 documentation HEAD 都不得
当作 S10 构建输入。

祖先容器证据（不得当作当前 candidate 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

S9-2 在同一 S7 retained-cache gate-host `issac@10.10.60.4` 上构建的
provisional Service/client image 绑定当前 candidate 与 effective inputs：

```text
image_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
image_label gateway.p2r1.build-input-revision: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
image_label gateway.p2r1.source-tree-sha256: sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686
image_label gateway.p2r1.uv-lock-sha256: 6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11
client_label org.opencontainers.image.revision: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
client_label gateway.p2r6.client-uv-lock-sha256: 6e9cf6bed196c6ead83df1076545f988b3420e599dbb443df0687a3f127f7954
image_matches_build_context: true
```

这些是 S9 candidate-bound provisional artifacts，不是 S10 final production
image。S10 必须对字面量 sealed candidate 独立重建并转移。

## Independent reviews

| review | record | result |
| --- | --- | --- |
| S9-1 design | [p2-r6-s9-design-review.md](p2-r6-s9-design-review.md) | `review_status: pass`，`allow_s9_implementation: yes`，`finding_count: 0` |
| S9-5 seal | [p2-r6-s9-candidate-seal-review.md](p2-r6-s9-candidate-seal-review.md) | `review_status: fail`，3 findings；保留原样 |
| S9-5 rereview | [p2-r6-s9-candidate-seal-review-rerun.md](p2-r6-s9-candidate-seal-review-rerun.md) | `review_status: pass`，`finding_count: 0`，`allow_s9_seal: yes`，`prior_findings_closed: yes` |

权威独立 seal review 是 rereview。失败记录不得改写成 pass。S9-5 rereview 只授权
进入 S9-6；本文件才记录 `candidate_seal`、`S9_exit` 和 `S10_ready`。

## Step records

| step | record | result |
| --- | --- | --- |
| S9-0 entry/preflight | [p2-r6-s9-step-0-entry-preflight.md](p2-r6-s9-step-0-entry-preflight.md) | `S9_entry_ready: yes` |
| S9-2 provisional image | [p2-r6-s9-step-2-provisional-image.md](p2-r6-s9-step-2-provisional-image.md) | `candidate_bound_provisional_images: pass` |
| S9-3 no-ignore regression | [p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md) | `no_ignore_source_regression: pass`；八条 nodeid PASSED |
| S9-4 seal packet | [p2-r6-s9-step-4-candidate-seal-packet.md](p2-r6-s9-step-4-candidate-seal-packet.md) | `candidate_seal_packet: complete` |

## No-ignore source regression

权威：[p2-r6-s9-step-3-no-ignore-regression.md](p2-r6-s9-step-3-no-ignore-regression.md)
于 candidate `2ef88427`、S9-2 同一 gate-host 与 candidate-bound provisional
image。权威日志：[p2-r6-s9-step-3-run-tests.log](p2-r6-s9-step-3-run-tests.log)。
quiet 日志已作废为权威 nodeid 证据，未删除：[p2-r6-s9-step-3-run-tests.quiet.log](p2-r6-s9-step-3-run-tests.quiet.log)。
首次失败保留：[p2-r6-s9-step-3-run-tests.fail-1.log](p2-r6-s9-step-3-run-tests.fail-1.log)。

权威命令（无 `--ignore` / `-m` / `-k` / `--ignore-glob` / xfail / skip / retry）。
`-vv -s` 是 reporting-only passthrough：脚本写死的包选择不变，只暴露 nodeid
`PASSED` 与 harness stdout。S9-5 rereview 接受该命令为 exact no-ignore source
selection。

```bash
./vnext/scripts/run-tests.sh -vv -s
```

```text
authoritative_exit_code: 0
gate_host: issac@10.10.60.4
remote_worktree: /home/issac/gateway-gate-2ef884278b49
GATEWAY_REPOSITORY_SERVICE_IMAGE: unset
service_local_id: sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
```

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q -vv -s` | 242 | 242 | 0 | 0 | 0.99s |
| repository_contracts | `uv run pytest -q -vv -s` | 152 | 152 | 0 | 0 | 0.26s |
| repository_client | `uv run pytest -q -vv -s` | 154 | 154 | 0 | 0 | 1.24s |
| backend | `uv run pytest -q -vv -s` | 35 | 35 | 0 | 0 | 1.26s |
| repository_service parallel | `uv run pytest -q -m "not serial" -vv -s` | 1639 | 1638 | 1 | 0 | 59.96s |
| repository_service serial | `uv run pytest -q -m serial -n 0 -vv -s` | 205 | 205 | 0 | 0 | 314.90s |

repository_service 无 ignore 全集 1844 = 1639 + 205。唯一 skip：delegated-target
cgroup smoke（`GATEWAY_P2R1_TARGET_CONTAINER != "1"`），不是 S9 required Docker
nodeid。无未分类 skip，无失败。

### Eight Docker nodeids

每条由权威命令单独报告 `PASSED`，并带 per-node `residual_inventory` 全零。不是
合计算术，也不是单独补跑。

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

前四条 Compose/lifecycle nodeid 在 S9 作为 no-ignore source gate 的一部分已经
passed；S10 仍须在 sealed candidate 的 **production** image 上重跑它们。四条
negative probe 仍属 S9 no-ignore source gate，不得用 S10 production image gate
静默替换。

### Repair ledger

```yaml
first_failure: preserved in p2-r6-s9-step-3-run-tests.fail-1.log
environment_repairs: retag :local to candidate digest; unset GATEWAY_REPOSITORY_SERVICE_IMAGE
source_or_build_input_repairs: none
repairs: environment-only
repairs_to_production_or_tests: none
```

第一次失败是环境把 `GATEWAY_REPOSITORY_SERVICE_IMAGE` 导出到整条 `run-tests.sh`，
不是 candidate 源码缺陷。修复未改 source、test、dependency、build-input 或
container boundary。

## Old-reference classification and leak audit

权威：[p2-r6-s9-step-4-candidate-seal-packet.md](p2-r6-s9-step-4-candidate-seal-packet.md)。
原始命中：[p2-r6-s9-step-4-old-reference-raw/](p2-r6-s9-step-4-old-reference-raw/)。
未为清空搜索删除 historical 文档。

| group | raw file | hits | unclassified current production/test/CI/runbook old semantic |
| --- | --- | ---: | --- |
| 1 verification level | [g1-verification-level.txt](p2-r6-s9-step-4-old-reference-raw/g1-verification-level.txt) | 304 | none |
| 2 effect-state | [g2-effect-state.txt](p2-r6-s9-step-4-old-reference-raw/g2-effect-state.txt) | 480 | none |
| 3 CAS/store | [g3-cas-store.txt](p2-r6-s9-step-4-old-reference-raw/g3-cas-store.txt) | 1094 | none |
| 4 path/version | [g4-path-version.txt](p2-r6-s9-step-4-old-reference-raw/g4-path-version.txt) | 777 | none |
| 5 wire/readback | [g5-wire-readback.txt](p2-r6-s9-step-4-old-reference-raw/g5-wire-readback.txt) | 26 | none |

```yaml
s9_deletions_considered: none
consumer_search_before_delete: not_applicable
r5_cleanup_06: carried_closed
s3_disposition_reopened: no
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
git_diff_check: pass
broad_marker_exclusion: no
exact_no_ignore_command: ./vnext/scripts/run-tests.sh -vv -s
```

S9-4 leak audit（gate-host `10.10.60.4`）：`gateway-p2r6` containers/networks/volumes
= 0，`dolt_pids=0`，`query_temps=0`，`check_temp_homes=0`，`work_root_gateway=0`，
candidate porcelain empty。九条 per-node `residual_inventory` 全零。

## Carried evidence

不是 open S9 finding。S9 未重开这些范围。

| item | authority | S9 treatment |
| --- | --- | --- |
| S8 parked-Dolt unit / five-package static | [p2-r6-s8-final-handoff.md](p2-r6-s8-final-handoff.md) | carried |
| S8 worker convergence | [p2-r6-s8-step-3-worker-convergence.md](p2-r6-s8-step-3-worker-convergence.md) | carried；S9 未重跑 W1/W2 |
| S8 three-ignore source regression | [p2-r6-s8-step-4-source-full-regression-rerun.md](p2-r6-s8-step-4-source-full-regression-rerun.md) | superseded by S9 no-ignore for source seal；S8 记录仍保留 |
| S7 four Compose nodeids and images | [p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md) `5f474ce2` | ancestor evidence；不得当作 `2ef88427` production PASS |
| S6 capacity / W2 / concurrency | Stage I S6 / W2 / concurrency matrix | carried；S10 重跑 W1/W2 |

## Docker / Compose decision

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S9-6 documentation/external seal only; no Dockerfile, dependency closure,
  Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision (S9 provisional): 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Last verified source-tree/image id (S9 provisional):
  sha256:c35db6ace55c20b52b8a920b6c5b264b83ba6c7d67d2916282fb11cffcf76686 /
  sha256:4b8f88edf798b2d67b46effa2a9f7f10029bdd657b508b5e342fd26a2e4a2be6
Last verified image revision (S7, ancestor): 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id (S7, ancestor):
  sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 /
  sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S10 final production image/provenance; S10 four Compose
  nodeids on the sealed candidate; W1/W2 and Candidate A v8 formal --runs 5
Required execution point: S10 final production
```

S9 provisional image 不是 S10 final production image。后续 docs-only handoff
提交会使 documentation HEAD 相对 image label 变为
stale-by-documentation-only-delta；`validated_code_sha` 仍为 `2ef88427`，
`container_validated_code_sha` 仍为 `deferred`。不得把 `71da5061` 或本文件提交
SHA 写成 S10 构建输入。

## External seal schema

```yaml
stage: P2-R6-S9
stage_status: pass
candidate_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
no_ignore_source_regression: pass
all_eight_docker_nodeids: pass
candidate_bound_provisional_images: pass
old_reference_classification: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
independent_seal_review: pass
candidate_seal: pass
S9_exit: pass
S10_ready: yes
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S10 final production image/provenance/container gate
  - S10 four Compose nodeids on the sealed candidate
  - S10 W1/W2 repeat and Candidate A v8 formal --runs 5
```

S10 必须从字面量 `CANDIDATE_SHA` `2ef884278b4998dde1e5fe224532c89b7a0cd73a`
构建 final production image，不能用本 handoff 文档 HEAD、S9 provisional image
或祖先 `5f474ce2` image 替代。S10 仍拥有 production provenance、四条 Compose
nodeid、W1/W2 与 Candidate A v8 formal `--runs 5`。任一项不得从 handoff 静默删除。
