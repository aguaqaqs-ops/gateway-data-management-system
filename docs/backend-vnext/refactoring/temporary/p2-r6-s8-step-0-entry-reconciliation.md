# P2-R6-S8 Step 0 — Entry Reconciliation

状态：`complete`

日期：2026-08-16

本记录只做 S8 入口身份、S7 ancestry、worktree 分类和 closure inventory 的只读复核。
没有运行 pytest、Dolt、Docker 或 Compose，没有修改 production/test/deployment 文件，
也没有改写历史 S3/S6/S7 evidence。S8-0 不对 S8 设计做 pass/fail 判定；独立设计审核
归 S8-1。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §2
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)
上游 handoff：[P2-R6-S7 final handoff](p2-r6-s7-final-handoff.md)
总计划：[P2-R6 Operational Closure Execution Plan](../formal/plans/p2-r6-operational-closure-execution-plan.md) §§7–10

## Entry identity

S8-0 开始时用 `git rev-parse HEAD` 取得字面量 SHA。该 SHA 与执行计划冻结字段
`entry_head_at_last_review` 一致。本文件的后续 docs-only 提交不是入口 SHA。

```yaml
branch: phase1/gate-ownership-repair
entry_head_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
recorded_entry_head_at_last_review: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
recorded_entry_head_match: yes
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
merge_base_with_s7: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
post_s7_committed_delta: docs-only
production_code_dirty: no
s8_source_change_authorized: no
S7_exit: pass
S8_ready: yes
production_retest_required: yes
phase_2_complete: no
capacity_rerun_in_s8: no
exact_docker_ignores: 3
```

S8-0 开始时 `git status --short`：

```text
 M docs/backend-vnext/refactoring/formal/README.md
 M docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-design.md
?? docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-execution-plan.md
```

`vnext/**` 无已跟踪或未跟踪改动。脏文件全部是 S8 规划文档与 formal 索引，不是未知
生产漂移。分类见下一节。这不构成 `S8_entry_ready: no`；先例是 W1 Stage A 与 S7 的
`34801a16`（`docs(repository): define P2-R6-S7 lifecycle execution`）。本记录与这些
docs-only 路径一并提交后，S8-1 从干净 HEAD 审核设计。

## Ancestry and committed delta

S7 候选 `5f474ce2ccf15f11ea07f263edf3fb04c771d410` 是当前 HEAD 的祖先。HEAD 相对该
候选只有一个提交：

```text
1bfa1d7f docs(repository): record P2-R6-S7 final handoff
```

`git diff --name-status 5f474ce2..HEAD`：

```text
M	docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md
A	docs/backend-vnext/refactoring/temporary/p2-r6-s7-final-handoff.md
A	docs/backend-vnext/refactoring/temporary/p2-r6-s7-step-10-lifecycle-rereview.md
M	docs/backend-vnext/testing-conventions.md
```

该 delta 是 docs-only。用户未授权 S8 source change。S7 `container_validated_code_sha`
仍为 `5f474ce2`；文档 HEAD 相对 image label 是 stale-by-documentation-only-delta，
不得写成当前 HEAD 的 container PASS。

## Uncommitted worktree classification

| path | status | class |
| --- | --- | --- |
| `docs/backend-vnext/refactoring/formal/README.md` | modified | current S8 formal index and stage-status wording |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-operational-closure-execution-plan.md` | modified | current S8 design/plan links under the S8 stage block |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-design.md` | untracked | current S8 design authority |
| `docs/backend-vnext/refactoring/formal/plans/p2-r6-s8-full-regression-execution-plan.md` | untracked | current S8 execution authority |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-0-entry-reconciliation.md` | this record | S8-0 evidence; added after the status snapshot above |

```yaml
tracked_production_dirty: no
untracked_production: none
uncommitted_docs_only: yes
unknown_current_finding: none
unresolved_scope_ownership: none
```

## S7 authority

来源：[p2-r6-s7-final-handoff.md](p2-r6-s7-final-handoff.md)。S8-0 逐项核对，不重跑
四条 nodeid。

```yaml
stage: P2-R6-S7
stage_status: pass
s7_entry_sha: 0b4969fe04ab3d133c297a474bac1ecc27111336
validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
service_image_id: sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
client_image_id: sha256:d4e07d7900d70df49df6f2628cc1cf542a6e02c8772e8cab35cedf82972ee461
source_tree_sha256: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2
nodeids:
  import_restart_replay: pass
  pinned_read_inside_network: pass
  pinned_read_gate_host: pass
  fresh_restart_restored: pass
all_nodeids_current_candidate: yes
zero_process_thread_query_temp_residual: yes
zero_container_network_volume_residual: yes
independent_harness_review: pass
independent_lifecycle_review: pass
S7_exit: pass
S8_ready: yes
production_retest_required: yes
phase_2_complete: no
```

四条 exact nodeid 均在 candidate `5f474ce2` / image `sha256:ba0ac70a…85849fa3` 上
独立 PASS，gate 后无 `gateway-p2r6-s7-*` container / network / volume。S10 仍须在
最终 P2 candidate 上重跑这四条，以及 W1/W2 与 v8 formal `--runs 5`。

## Carried evidence

下列项不是 open S8 finding。S8 只在出现新的、可复现的、属于当前 S8 gate 的失败时
才重开对应范围。

### S7 findings

| item | S8 treatment | authority |
| --- | --- | --- |
| F-001 candidate binding | carried closed | [S7-10 rereview](p2-r6-s7-step-10-lifecycle-rereview.md) `f001_candidate_binding: closed` |
| F-002 residual inventory | carried closed | S7-10 rereview `f002_residual_inventory: closed` |
| independent harness review | carried pass | [S7-4 final rereview](p2-r6-s7-step-4-harness-final-review.md) `review_status: pass`, `finding_count: 0` |
| independent lifecycle review | carried pass | S7-10 rereview `review_status: pass`, `finding_count: 0`; final handoff `independent_lifecycle_review: pass` |
| four Compose nodeids | carry as passed ancestor evidence; do not reopen without a new affected change | S7 final handoff |
| S7 service/client images | ancestor evidence for `5f474ce2` only | S7 final handoff |

S7-10 rereview 当时写 `S7_exit: no` / `S8_ready: no` 是因为尚未执行 S7-11。S7-11
final handoff 已把这两项改为 `pass` / `yes`。S8 以 final handoff 为权威，不把
rereview 的中间 `no` 当成当前 blocker。

### S3 R5 cleanup dispositions

权威：[S3 staged execution guide](phase-2/p2-r6-s3-staged-execution-guide.md)、
[S3-E container gate](p2-r6-s3-step-e-container-gate.md) `P2-R6-S3_exit: pass`、
R6 operational plan §4.4。

| id | S3 implementation disposition | S8 treatment |
| --- | --- | --- |
| R5-CLEANUP-01 | `closed_no_process_wide_cache`; request/session-scoped bounded memo retained | carry; S6 already recorded W1/W2/1-4-8 measurement and did not introduce process-wide cache |
| R5-CLEANUP-02 | event-driven Arrow handoff; default-executor polling removed | carry closed; S8 focused worker gate does not reopen the S3 disposition |
| R5-CLEANUP-03 | remain closed | carry; original shutdown nodeid stays the owner |
| R5-CLEANUP-04 | instance-scoped test probes replaced process-global ClassVar hooks | carry closed |
| R5-CLEANUP-05 | effective cancellation propagated to `ProcessStream.close` and `CommandResult` | carry closed; S8-3 owner nodeid verifies current cancellation/cleanup behaviour |
| R5-CLEANUP-06 | S3 closed the then-confirmed dead helpers after exact consumer search | carry closed; S8-5 owns *new* S8 deletions only, and must save exact `rg` before any such deletion |

S3-E 没有单独的 batch handoff 文件留在 `temporary/`。这不是新的 S8 finding：
`P2-R6-S3_exit: pass` 已记录在 Step E container gate，implementation dispositions
由 S3 guide 与 R6 plan 拥有。

### S6 capacity, W2 and concurrency

权威：[Stage I S6 capacity](p2-r6-ext-w1-stage-i-s6-capacity.md)、
[Stage I W2](p2-r6-ext-w1-stage-i-w2.md)、
[Stage I concurrency](p2-r6-ext-w1-stage-i-concurrency-matrix.md)、
[Stage K handoff](p2-r6-ext-w1-stage-k-final-handoff.md)。

```yaml
R6-EXT-W1: yes
P2-R6-S6_ready: yes
s6_capacity: pass
w2: pass
concurrency_matrix: pass
process_wide_cache_introduced: no
capacity_rerun_in_s8: no
s6_container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
```

S6 记录中偶发 `versioned read arrow bridge worker did not exit in time` 未留下
owned residual，也未改写 S6 PASS。S8 不把该历史诊断当成 open finding；S8-3 按
bounded-convergence / zero-residual 政策证明当前 worker 边界。S8 不重跑 W1/W2
全量矩阵。

## S8 closure ledger

仅当前 S8 项。S7/S3/S6 已关闭证据不进入本表。

| item | owner | status | note |
| --- | --- | --- | --- |
| parked-Dolt unit classification | S8-2 | open | `uv run pytest -m unit` with Dolt parked and restored even on failure |
| five-package ruff/mypy | S8-2 | open | `shared_kernel`, `repository_contracts`, `repository_service`, `repository_client`, `backend` |
| worker convergence | S8-3 | open | owner `tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files`; warning is diagnostic; bounded convergence and zero final residual required |
| exact source regression | S8-4 | open | `./vnext/scripts/run-tests.sh` with exactly three Docker-test `--ignore` files |
| old-reference classification | S8-5 | open | five exact repository-wide searches; historical docs preserved |
| dead-symbol consumer search | S8-5 | open | required before any S8 deletion; does not reopen S3 CLEANUP-06 |
| leak audit | S8-3 / S8-5 | open | process / thread / Dolt child / query-temp / work-root inventory must be zero at S8-owned gate exit |

Supporting S8-3 nodeids remain in the same owner boundary and are not separate ledger
rows:

```text
tests/test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled
tests/test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream
tests/test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor
tests/test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit
```

Deferred, not S8-owned:

- S9 exact candidate seal and no-ignore `./vnext/scripts/run-tests.sh`
- S10 final production image / provenance / container gate
- S10 four Compose nodeids on the final P2 candidate
- S10 W1/W2 repeat and Candidate A v8 formal `--runs 5`

## Docker / Compose decision

```text
Current HEAD: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
Container rebuild required: no
Reason: committed delta since 5f474ce2 and uncommitted files at S8-0 start are documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S8 source full regression with exact three Docker ignores; S9 no-ignore seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 是祖先证据。本 docs-only 入口提交不改变
`container_validated_code_sha`，不得把当前 documentation HEAD 写成 container PASS。

## Exit

```yaml
entry_identity_consistent: yes
s7_ancestor: yes
post_s7_delta_docs_only: yes
production_code_dirty: no
s7_handoff_fields_complete: yes
unknown_current_finding: none
unresolved_scope_ownership: none
S8_entry_ready: yes
allow_s8_design_review: yes
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-1 independent design review in a new conversation
```

下一步读取本记录、S8 设计 §§1–6 和执行计划，只读审核设计、验收口径、步骤边界和
审核回退路径。S8-1 的 `reviewed_design_sha` 是本 docs-only 提交之后的干净 HEAD，
不是入口 SHA `1bfa1d7f`。
