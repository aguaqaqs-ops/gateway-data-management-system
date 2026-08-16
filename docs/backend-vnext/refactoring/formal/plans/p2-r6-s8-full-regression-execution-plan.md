# P2-R6-S8 Full Regression and Candidate Preparation Execution Plan

状态：Ready for independent design review

日期：2026-08-16

关联设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](p2-r6-s8-full-regression-design.md)
总计划：[P2-R6 Operational Closure Execution Plan](p2-r6-operational-closure-execution-plan.md)
上游 handoff：[P2-R6-S7 final handoff](../../temporary/p2-r6-s7-final-handoff.md)

本文把 S8 拆为 bounded sessions。每个步骤的 session 字段明确是否延续上下文；独立审核、
候选准备和 handoff 必须新开对话。任务 prompt 只启动已经冻结的步骤，不替代本文的 allowed
paths、failure boundary、evidence owner 或回退规则。

## 0. Frozen entry and global rules

```yaml
stage: P2-R6-S8
branch: phase1/gate-ownership-repair
entry_head_at_last_review: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_container_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_exit: pass
s8_ready: yes
production_retest_required: yes
phase_2_complete: no
capacity_rerun_in_s8: no
exact_docker_ignores: 3
```

`entry_head_at_last_review` is a reference only. S8-0 must obtain the literal SHA with
`git rev-parse HEAD` and stop if branch, ancestry or worktree differs from the recorded state.

### 0.1 Session policy

- **Keep the same conversation:** within one implementation step, including local code edits,
  focused tests, static checks, failure repair and that step's evidence record.
- **Open a new conversation:** S8-0 entry reconciliation, S8-1 design review, S8-6 independent
  implementation review, S8-7 final handoff, and any step that crosses into a Docker/container
  boundary. A new conversation also starts after a review finding is routed back and fixed.
- **Read-only review:** reviewers inspect actual diffs, commands, counts, markers and evidence; they
  do not edit production code, tests, configuration or handoff text to hide a finding.
- **Failure loop:** a review finding returns to the owning implementation step listed in the routing
  table below. The owner reruns the affected tests and updates the evidence before a new review.
- **No partial pass:** a skipped/missing test, broad ignore, old-image substitution, unclassified
  current reference or residual resource is `no-go`.
- **Container trigger:** Dockerfile, dependency closure, Compose, entrypoint, environment wiring,
  health/readiness, client image or container harness changes require a current candidate rebuild
  and affected directed gate. Pure Python/test/docs changes may defer the final image to S9/S10.
- **Test markers:** real Dolt, subprocess or落盘 lifecycle is `integration`; fixed timeout, signal,
  thread, stream or cleanup budget is `serial` and runs with `-n 0`; pure parsing/classification is
  `unit` and must not initialize Dolt.

## 1. Step map

| step | name | session policy | kind | output | next / failure route |
| --- | --- | --- | --- | --- | --- |
| S8-0 | Entry reconciliation | new conversation | read-only | entry record and closure ledger | S8-1; entry no-go stops |
| S8-1 | Independent design review | new conversation | read-only | design review | S8-2 or design correction |
| S8-2 | Classification and static gates | new after review; continue within step | implementation/test | classification and five-package static evidence | S8-3; findings return here |
| S8-3 | Worker convergence and focused regression | same conversation as S8-2 only while scope stays focused; otherwise new | implementation/test | worker/leak evidence and focused counts | S8-4; failures return here or owning code |
| S8-4 | Source full regression | new conversation after focused gates | implementation/test | exact command/count and repair ledger | S8-5; failures return here |
| S8-5 | Hygiene and S8 candidate preparation | continue S8-4 only if no source changes; otherwise new | implementation/read-only checks | old-reference classification, clean-source pre-review record | S8-6; findings return to S8-2/3/4 |
| S8-6 | Independent implementation review | new conversation | read-only | review record | S8-7 or routed repair loop |
| S8-7 | Final S8 handoff | new conversation after review pass | docs-only | S8 handoff and S9-ready decision | S9 |

The plan intentionally does not make S9's immutable candidate seal part of S8. If S8 changes a
container boundary, the affected gate is run in the owning S8 step, but S9 still rebuilds the exact
final candidate after S8 source closure.

## 2. S8-0 - Entry reconciliation

**Session:** New conversation. Read-only; do not modify source, tests or deployment files.

**Read first:** `AGENTS.md`, this plan §§0-1, the S8 design §§1-6, S7 final handoff, S3 cleanup
closure guide, S6 capacity/W2/concurrency evidence, Testing Conventions and the R6 operational plan
§§7-10.

**Checks:**

1. Record branch, literal `HEAD`, `git status --short`, and complete worktree state.
2. Verify S7 candidate `5f474ce2` is an ancestor of HEAD and that the post-candidate delta is docs-only
   unless the user has explicitly authorized an S8 source change already.
3. Verify S7 handoff fields `S7_exit: pass`, `S8_ready: yes`, `phase_2_complete: no`, all four
   nodeids current-candidate, both independent reviews pass and both residual inventories are zero.
4. Create the S8 closure ledger with only current S8 items: parked-Dolt unit, five-package static,
   worker convergence, exact source regression, old-reference classification, dead-symbol consumer
   searches and leak audit.
5. Mark S7 findings and S3 R5 cleanup dispositions as carried evidence, not open S8 findings.
6. Record the current container decision. A docs-only descendant is `deferred`/ancestor evidence,
   not current-container PASS.

**Evidence:** `p2-r6-s8-step-0-entry-reconciliation.md`, containing literal entry SHA, ancestry,
worktree, carried evidence and closure ledger.

**Exit:** branch/ancestry/worktree and authority are consistent; no unknown current finding or
unresolved scope ownership remains. Otherwise `S8_entry_ready: no` and stop.

**Prompt:** `复核 P2-R6-S8 入口、S7 handoff ancestry 和 closure inventory，生成 S8-0 entry record。`

## 3. S8-1 - Independent design review

**Session:** New conversation after S8-0. Read-only; no implementation edits.

**Review questions:**

- Does S8 remain source regression/candidate preparation, with no new public or persisted contract?
- Are S3 R5 cleanup dispositions and S7 Compose evidence carried without silent reopening?
- Is the worker warning policy precise: bounded convergence and zero final residual, not warning count?
- Are the three Docker ignores exact and is no-ignore full regression owned by S9?
- Are W1/W2 full reruns correctly retained for S10, with only focused worker/leak regression in S8?
- Are all fixed-time, subprocess and resource-lifecycle tests classified as `serial`/`integration`?
- Does every review finding have a route back to an owning implementation step?
- Does the handoff distinguish source SHA, container SHA, `S9_ready` and `phase_2_complete`?

**Output:** `p2-r6-s8-design-review.md` with reviewed design/execution SHA, findings,
`review_status: pass|fail` and `allow_s8_implementation: yes|no`.

**Exit:** zero design blockers. A finding returns to the design document and S8-0 is repeated if
entry scope or authority changed. The reviewer does not patch the issue.

**Prompt:** `只读审核 P2-R6-S8 设计、验收口径、步骤边界和审核回退路径。`

## 4. S8-2 - Classification and static gates

**Session:** New conversation after S8-1 pass. Keep this conversation through all focused checks and
minimal owning-scope repairs; do not start full source regression here.

**Allowed scope:** test classification, marker declarations, focused test fixes, static fixes and
minimal production/test changes directly required by a focused failure. Do not add a feature or
modify Docker/deployment unless a failure proves it is the owning scope.

**Required checks:**

1. Run five-package lint and type checks:

   ```bash
   for package in shared_kernel repository_contracts repository_service repository_client backend; do
     (cd vnext/$package && uv run ruff check . && uv run mypy)
   done
   ```

2. Park Dolt and run the authoritative unit classification. Use a trap or equivalent restoration
   path so the binary is restored even when pytest fails:

   ```bash
   mv /usr/local/bin/dolt /usr/local/bin/dolt.parked
   trap 'mv /usr/local/bin/dolt.parked /usr/local/bin/dolt' EXIT
   cd vnext/repository_service
   uv run pytest -m unit
   ```

   If the binary is already parked, stop and resolve the environment rather than overwriting it.
3. Collect exact S8 focused nodeids and verify strict markers. Do not use a broad `-k`, `--ignore` or
   marker exclusion to hide a misclassified test.
4. Run touched-package focused tests and `git diff --check`.

**Evidence:** package commands and versions, exact counts, parked-Dolt result/restoration, marker
collection and changed-path inventory.

**Exit:** five-package static checks and parked-Dolt unit classification pass. A classification or
static failure returns to this step; a production behavior failure routes to the owning step named in
the failure evidence.

**Prompt:** `执行 S8 parked-Dolt unit 分类、五包 ruff/mypy 和 focused marker 检查，修复 owning scope 后提交证据。`

## 5. S8-3 - Worker convergence and focused regression

**Session:** Continue S8-2 only while changes remain within the focused worker/read cleanup scope.
Open a new conversation if the change crosses an owning module or container boundary.

**Owner nodeid:**

```text
tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files
```

**Supporting focused checks (same owner boundary):**

```text
tests/test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled
tests/test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream
tests/test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor
tests/test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit
```

Run the owner and supporting checks with the required `integration`/`serial` markers and `-n 0`.
Capture baseline and final bridge registry, owned child PIDs, query-temp files, host thread idents
and work-root directories. Record warning occurrences, convergence deadline and elapsed cleanup.

**Acceptance:**

- cancellation or shutdown reaches the owner gate's cleanup boundary;
- any `worker did not exit in time` diagnostic is followed by bounded convergence;
- final bridge registry, child process, query-temp, thread and work-root inventories are zero;
- `CommandResult.cancelled` is true on disconnect where the supporting test owns that fact;
- no production result is changed merely because cleanup is retried.

Run affected integration/serial tests for any repair. Do not rerun W1/W2 capacity here.

**Evidence:** focused command/count table, warning and convergence summary, resource inventory and
repair commits. A residual or unbounded convergence is `no-go` and returns to this step or the owning
Arrow/process scope.

**Prompt:** `执行 S8 worker convergence 与 focused cleanup regression，记录 warning、收敛时间和零残留。`

## 6. S8-4 - Source full regression

**Session:** New conversation after S8-2 and S8-3 are green. Keep one conversation for the full
regression plus first-failure repairs; do not mix independent review into it.

**Authoritative command:**

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

The three ignores are exact Docker-starting files only. Do not add `-m`, `-k`, `--ignore-glob`,
`xfail`, skip, retry or accepted-flake substitution. Record every package's command, collected,
passed, skipped, failed and duration counts.

**Failure loop:** fix the first failure in its owning production/test scope, rerun the affected
focused gate, then rerun the relevant package command. A source/build-input change does not erase
the failed evidence and may make prior container evidence stale. If a failure touches a container
boundary, stop and run the required current candidate directed gate before proceeding.

**Exit:** command completes with no unexpected skip/failure, exact counts are recorded, and no
unreviewed source changes remain. A failure returns to S8-2 or S8-3 when classification/worker scope
is implicated; otherwise return to the owning package step and then repeat S8-4.

**Prompt:** `运行 S8 精确三 ignore 源码全量回归，按第一失败 owning scope 修复并记录完整 counts。`

## 7. S8-5 - Hygiene and candidate preparation

**Session:** Continue S8-4 only if no source changes occurred after the last full regression. Open a
new conversation after any repair or when the evidence must be independently assembled.

**Required searches and checks:**

1. Run the five exact old-reference searches from R6 operational plan §9 across the whole repository.
   Save raw matches and a manual classification of current authority, negative prohibition,
   unrelated terminology and historical/superseded material. Do not delete historical docs merely
   to make the search empty.
2. For every dead helper, parameter or branch considered for deletion, save the exact `rg` consumer
   search before editing and rerun affected tests after deletion. This is the owner for R5-CLEANUP-06
   evidence; it does not reopen the S3 disposition.
3. Run `git diff --check`, inspect changed paths against S8 allowed scope and perform the S8-owned
   process/thread/Dolt/query-temp/work-root leak audit.
4. Confirm no broad marker exclusion, stale source claim, missing nodeid count or undocumented
   current reference remains.
5. Record the current container decision using the Testing Conventions template. A pure Python,
   test or docs S8 tree may remain `container_gate_for_current_head: deferred`; a triggered boundary
   must be `passed` on its current candidate or `no-go`.

**Exit:** source tree is clean, all searches are classified, exact consumer evidence is saved,
resource inventory is zero and the implementation review packet is complete. Any current hit,
residual or scope mismatch returns to the owning S8 step.

**Prompt:** `完成 S8 old-reference 分类、dead consumer 搜索、leak audit 和 clean-source review packet。`

## 8. S8-6 - Independent implementation review

**Session:** New conversation. Read-only; no source, test, deployment or handoff edits.

**Review the actual S8 range:**

- entry ancestry and all S8 commits;
- first-failure repairs and rerun evidence;
- parked-Dolt classification and five-package static outputs;
- worker warning/convergence and zero-residual inventory;
- exact three-ignore full regression and counts;
- five old-reference classifications and saved dead-symbol consumers;
- container decision and stale/deferred wording;
- no reopen of S3/S7 closed evidence and no accidental W1/W2/S9/S10 scope expansion.

**Output:** `p2-r6-s8-implementation-review.md` containing reviewed commit range, finding count,
severity, concrete path/command evidence, `review_status: pass|fail` and `allow_s8_handoff: yes|no`.

**Review finding routing:**

| finding type | return step | required rerun before review |
| --- | --- | --- |
| marker/classification/static | S8-2 | affected package, parked-Dolt unit and static checks |
| bridge/worker/child/temp/thread cleanup | S8-3 | owner/supporting focused serial gate and leak inventory |
| source regression/count/first-failure repair | S8-4 | affected package plus exact three-ignore command |
| old-reference/dead-symbol/hygiene | S8-5 | exact search, affected tests, diff check and leak audit |
| scope/authority/container decision | S8-0 or owning step | entry/design or affected directed gate |

The reviewer never fixes a finding. After repair, open a new implementation conversation, preserve
the failed review record, rerun the route above and start a fresh S8-6 review. Repeat until
`finding_count: 0` and `allow_s8_handoff: yes`.

**Prompt:** `只读审核 S8 实际实现范围、回归 counts、分类、残留审计和候选准备证据；发现问题只路由回 owning step。`

## 9. S8-7 - Final S8 handoff

**Session:** New conversation after S8-6 pass. Documentation-only; no production/test/build input
changes.

**Verify:**

- current HEAD is the reviewed clean source SHA;
- no source/build-input change occurred after the independent review;
- all required S8 evidence fields and exact counts are present;
- current container decision is accurate (`deferred`, `passed` or `no-go`);
- S3/S6/S7 carried evidence and S9/S10 deferred scope remain explicit.

**Handoff schema:**

```yaml
stage: P2-R6-S8
stage_status: pass
entry_sha: <literal S8 entry SHA>
validated_code_sha: <exact clean S8 source SHA>
container_validated_code_sha: <same SHA | deferred>
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

The handoff must also include the full source command, package counts, worker convergence timing,
old-reference classification artifact locations, review SHA and current container decision. A
docs-only handoff does not alter `validated_code_sha` or any container image identity.

**Exit:** `S8_exit: pass`, `S9_ready: yes`, `phase_2_complete: no`. Any missing evidence is `no-go`;
documentation cannot turn a failed or missing gate into pass.

**Prompt:** `在独立 S8 review 通过后，核对 clean SHA 和全部 evidence，形成 S8 handoff，下一步进入 S9。`

## 10. S8 completion decision

S8 is complete only when S8-0 through S8-7 have the required records, S8-6 has zero findings and
S8-7 records `S9_ready: yes`. S9 then starts from the literal clean `validated_code_sha`, runs
`./vnext/scripts/run-tests.sh` without any ignore, seals the exact candidate and owns the final image
input. S10 remains the owner of final Compose, W1/W2, production and v8 evidence.
