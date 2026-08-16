# P2-R6-S8 — Final source-regression / candidate-preparation handoff

状态：`pass`

日期：2026-08-17

本记录是 S8-7 在 S8-6 rereview `allow_s8_handoff: yes` 之后的 documentation-only
handoff。未修改 production code、Contract、snapshot 语义、Dockerfile、Compose、
lock 或 entrypoint。未跑 pytest、Dolt、Docker、W1/W2 或 S9 no-ignore seal。未打
`p2-r6-final` tag，不宣称 Phase 2 完成。本文件的 docs-only 提交不是
`validated_code_sha`。

权威步骤：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §9–§10
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)
S8-6 放行：[p2-r6-s8-implementation-rereview.md](p2-r6-s8-implementation-rereview.md)
保留的失败审核：[p2-r6-s8-implementation-review.md](p2-r6-s8-implementation-review.md)

## Identity

S8-7 开始时用 `git rev-parse HEAD` 取得字面量 SHA。该 SHA 与 S8-6 rereview
`reviewed_head` 一致。工作树仅有未跟踪的失败审核与复审记录，均为 docs-only。

```yaml
branch: phase1/gate-ownership-repair
entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: deferred
reviewed_head: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_entry_is_ancestor: yes
last_test_change_sha: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
worktree_at_s8_7_start: docs-only untracked S8-6 review records
production_code_changed_in_s8: no
test_classification_changed_in_s8: yes
docker_or_compose_changed_in_s8: no
public_contract_change: no
phase_2_complete: no
```

`validated_code_sha` 是独立 implementation rereview 通过时的干净 HEAD
`2ef88427`。S8 对 `vnext/` 的唯一改动是
`vnext/repository_service/tests/test_snapshot_admin.py` 的 marker 分类
（`601206e4` 随后被 `3e4bd1fc` 取代）。本文件的 docs-only 提交不改变
`validated_code_sha` 或任何 container image identity。

S8 提交范围 `1bfa1d7f..2ef88427`：

```text
77a43ebe  docs(repository): record P2-R6-S8 entry reconciliation
97f0f454  docs(repository): record P2-R6-S8 design review
601206e4  test(repository): classify snapshot_admin CLI tests as serial
be2d1a03  docs(repository): record P2-R6-S8 classification and static gates
a27fe004  docs(repository): record P2-R6-S8 worker convergence
8e42bdd6  docs(repository): record P2-R6-S8 source full regression
6ddd94d7  docs(repository): record P2-R6-S8 hygiene and candidate preparation
3e4bd1fc  test(repository): classify snapshot_admin subprocess tests as integration
2ef88427  docs(repository): record S8-2 marker repair rerun evidence
```

祖先容器证据（不得当作当前 HEAD 已验证）：

```text
ancestor_candidate: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
ancestor_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
ancestor_source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
```

## Independent reviews

| review | record | result |
| --- | --- | --- |
| S8-1 design | [p2-r6-s8-design-review.md](p2-r6-s8-design-review.md) | `review_status: pass`，`allow_s8_implementation: yes`，`finding_count: 0` |
| S8-6 implementation | [p2-r6-s8-implementation-review.md](p2-r6-s8-implementation-review.md) | `review_status: fail`，P1 marker classification；保留原样 |
| S8-6 rereview | [p2-r6-s8-implementation-rereview.md](p2-r6-s8-implementation-rereview.md) | `review_status: pass`，`finding_count: 0`，`allow_s8_handoff: yes`，`prior_p1: closed` |

权威独立实现审核是 rereview。失败记录不得改写成 pass。

## Parked-Dolt unit and five-package static

权威分类修复与 rerun：[p2-r6-s8-step-2-classification-repair.md](p2-r6-s8-step-2-classification-repair.md)
`3e4bd1fc`。原 [S8-2](p2-r6-s8-step-2-classification-and-static.md) 保留为修复前证据。

工具版本：ruff 0.15.21，mypy 2.3.0，pytest 9.1.1，Python 3.14.6。

```text
shared_kernel ruff: pass
shared_kernel mypy: pass (34 source files)
repository_contracts ruff: pass
repository_contracts mypy: pass (15 source files)
repository_service ruff: pass
repository_service mypy: pass (195 source files)
repository_client ruff: pass
repository_client mypy: pass (26 source files)
backend ruff: pass
backend mypy: pass (26 source files)
git diff --check: pass
```

Parked-Dolt 权威 rerun（binary 存在，`mv` + EXIT trap）：

```text
uv run pytest -m unit
16 workers [1449 items]
1448 passed, 1 skipped in 20.94s
pytest_status=0
dolt restored: yes
parked leftover: no
```

唯一 skip：

```text
tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
```

无 Dolt-missing skip。`test_snapshot_admin.py` 收集为 unit 2 / integration 54；
46 个 subprocess/lifecycle nodeid 为 `integration` + `serial`。两个纯进程内用例保持
unit、无 serial。

## Worker convergence

权威：[p2-r6-s8-step-3-worker-convergence.md](p2-r6-s8-step-3-worker-convergence.md)。
marker 修复未改 Arrow/worker/process 实现或 focused tests；S8-6 rereview 接受该
carried 证据，因为精确三 ignore 全量已在 `3e4bd1fc` 上跑过。S8 未重跑 W1/W2。

```text
uv run pytest -n 0 --log-cli-level=WARNING --durations=10
  tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files
  tests/test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled
  tests/test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream
  tests/test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor
  tests/test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit
```

| nodeid | markers | result | call s |
| --- | --- | --- | ---: |
| owner `test_http_disconnect_cancels_worker_and_cleans_query_files` | integration, serial | PASSED | 2.13 |
| `test_http_disconnect_reports_command_result_cancelled` | integration, serial | PASSED | 10.80 |
| `test_http_runtime_shutdown_closes_active_row_stream` | integration, serial | PASSED | 1.60 |
| `test_close_all_waits_for_worker_thread_not_false_survivor` | unit, serial | PASSED | 0.25 |
| `test_join_timeout_keeps_alive_worker_registered_until_exit` | unit, serial | PASSED | 0.15 |

```yaml
collected: 5
passed: 5
failed: 0
skipped: 0
warning_count_diagnostic: 2
warning_count_gate: not_used
convergence_deadline_join_seconds: 30.0
owner_elapsed_call_seconds: 2.13
cancelled_supporting_elapsed_call_seconds: 10.80
unbounded_convergence: no
command_result_cancelled_owned: pass
```

诊断 `versioned read arrow bridge worker did not exit in time` 出现 2 次，随后均
PASSED 且低于 30s join deadline。最终库存：

```text
residual_inventory gate=s8-3-worker
  bridge=0 dolt_delta=0 query_temps=0 host_threads=0
  check_temp_homes=0 s8_owned_work_root_dirs=0
```

## Source full regression

权威 rerun：[p2-r6-s8-step-4-source-full-regression-rerun.md](p2-r6-s8-step-4-source-full-regression-rerun.md)
于 `3e4bd1fc`。原 [S8-4](p2-r6-s8-step-4-source-full-regression.md) 保留为修复前证据。
`2ef88427` 相对该运行 SHA 只增加 rerun 证据文档。

权威命令（恰好三条 Docker-starting file ignore；无 `-m` / `-k` / `--ignore-glob`）：

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

```text
wall_clock_ms: 302927
exit_code: 0
first_failure: none
repairs_in_rerun: none
```

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q` + 三 ignore | 242 | 242 | 0 | 0 | 0.81s |
| repository_contracts | `uv run pytest -q` + 三 ignore | 152 | 152 | 0 | 0 | 0.20s |
| repository_client | `uv run pytest -q` + 三 ignore | 154 | 154 | 0 | 0 | 1.26s |
| backend | `uv run pytest -q` + 三 ignore | 35 | 35 | 0 | 0 | 0.64s |
| repository_service parallel | `uv run pytest -q -m "not serial"` + 三 ignore | 1639 | 1638 | 1 | 0 | 105.46s |
| repository_service serial | `uv run pytest -q -m serial -n 0` + 三 ignore | 197 | 197 | 0 | 0 | 189.90s |

repository_service 三 ignore 后全集 1836。唯一 skip 仍是 expected delegated-target
cgroup smoke test。无未分类 skip，无失败。

## Old-reference classification and leak audit

权威 rerun：[p2-r6-s8-step-5-hygiene-rerun.md](p2-r6-s8-step-5-hygiene-rerun.md)。
原始命中：[p2-r6-s8-step-5-old-reference-raw-rerun/](p2-r6-s8-step-5-old-reference-raw-rerun/)。
修复前命中保留在 [p2-r6-s8-step-5-old-reference-raw/](p2-r6-s8-step-5-old-reference-raw/)，
未为清空搜索删除 historical 文档。

| group | raw file | hits | unclassified current production/test/CI/runbook old semantic |
| --- | --- | ---: | --- |
| 1 verification level | [g1-verification-level.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g1-verification-level.txt) | 60 | none |
| 2 effect-state | [g2-effect-state.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g2-effect-state.txt) | 112 | none |
| 3 CAS/store | [g3-cas-store.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g3-cas-store.txt) | 264 | none |
| 4 path/version | [g4-path-version.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g4-path-version.txt) | 301 | none |
| 5 wire/readback | [g5-wire-readback.txt](p2-r6-s8-step-5-old-reference-raw-rerun/g5-wire-readback.txt) | 12 | none |

```yaml
s8_deletions_considered: none
consumer_search_before_delete: not_applicable
r5_cleanup_06: carried_closed
s3_disposition_reopened: no
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
git_diff_check: pass
broad_marker_exclusion: no
exact_docker_ignores: 3
```

hygiene rerun 残留：`dolt_pids=0`，`query-*.sql=0`，`snapshot-check-dolt=0`，
`s8_owned_work_root_dirs=0`。

## Carried evidence

不是 open S8 finding。S8 未重开这些范围。

| item | authority | S8 treatment |
| --- | --- | --- |
| S7 four Compose nodeids and images | [p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md) `5f474ce2` | ancestor evidence；未重跑 |
| S7 F-001 / F-002 | [S7-10 rereview](p2-r6-s7-step-10-lifecycle-rereview.md) | carried closed |
| S3 R5-CLEANUP-01..06 | [S3 staged execution guide](phase-2/p2-r6-s3-staged-execution-guide.md) | carried closed；S8 无新删除 |
| S6 capacity / W2 / concurrency | [Stage I S6](p2-r6-ext-w1-stage-i-s6-capacity.md)、[W2](p2-r6-ext-w1-stage-i-w2.md)、[concurrency](p2-r6-ext-w1-stage-i-concurrency-matrix.md) | carried；S8 未重跑 W1/W2 |

## Docker / Compose decision

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: S8 changes test marker classification and documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据。后续 docs-only handoff
提交会使 documentation HEAD 相对该 image label 变为
stale-by-documentation-only-delta；`validated_code_sha` 仍为 `2ef88427`，
`container_validated_code_sha` 仍为 `deferred`。

## Handoff schema

```yaml
stage: P2-R6-S8
stage_status: pass
entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
validated_code_sha: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
container_validated_code_sha: deferred
parked_dolt_unit: pass
five_package_static: pass
worker_convergence: pass
source_regression_with_exact_docker_ignores: pass
old_reference_classification: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
independent_review: pass
S8_exit: pass
S9_ready: yes
production_retest_required: yes
phase_2_complete: no
deferred_scope:
  - S9 exact candidate seal and no-ignore source gate
  - S10 final production image/provenance/container gate
  - S10 W1/W2 repeat and Candidate A v8 formal --runs 5
```

S9 必须从字面量 `validated_code_sha` `2ef884278b4998dde1e5fe224532c89b7a0cd73a`
起跑 `./vnext/scripts/run-tests.sh`（无 ignore）并封印精确候选，不能用本 handoff
文档 HEAD 当 candidate。S10 仍拥有最终 Compose、W1/W2、production 与 v8 证据。
任一项不得从 handoff 静默删除。
