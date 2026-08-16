# P2-R6-S8 - Independent Implementation Review

状态：`fail`

日期：2026-08-17

本记录是 S8-6 的独立只读 implementation review。审核对象是 S8 entry 之后的实际
commit range、S8-0 至 S8-5 证据、唯一 test classification 变更、回归 counts、worker
收敛与残留库存、old-reference 原始命中和 container 决策。审核没有修改 production、
test、deployment 或 handoff；只新增本审核记录。没有重跑 full regression、Docker、
Compose、W1/W2 或 v8 gate。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §8

权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)

候选准备：[P2-R6-S8 Step 5 - Hygiene and Candidate Preparation](p2-r6-s8-step-5-hygiene-and-candidate-preparation.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: 6ddd94d78a28c8345613693e6b487b3de69e84b7
reviewed_range: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09..6ddd94d78a28c8345613693e6b487b3de69e84b7
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_entry_is_ancestor: yes
review_worktree_clean_at_start: yes
production_code_changed_in_s8: no
test_code_changed_in_s8: yes
docker_or_compose_changed_in_s8: no
production_code_changed_by_review: no
test_or_deployment_input_changed_by_review: no
public_contract_changed: no
phase_2_complete: no
```

The reviewed range contains seven commits:

```text
77a43ebe  S8-0 entry reconciliation
97f0f454  S8-1 design review
601206e4  snapshot_admin marker classification
be2d1a03  S8-2 classification/static evidence
a27fe004  S8-3 worker convergence evidence
8e42bdd6  S8-4 source regression evidence
6ddd94d7  S8-5 hygiene/candidate-preparation evidence
```

`git diff --name-status 1bfa1d7f..6ddd94d7` shows one non-document path,
`vnext/repository_service/tests/test_snapshot_admin.py`; its only change is the module-level
`pytestmark = pytest.mark.serial`. `git diff --check 1bfa1d7f..6ddd94d7` passes.

## Finding

### P1 - Snapshot admin subprocess tests remain classified as unit

The frozen S8 rule says real Dolt, subprocess, or on-disk lifecycle tests are `integration`, while
fixed-time, signal, thread, stream, or cleanup-budget tests are `serial`
([execution plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md), §0.1). Testing
Conventions define the same boundary: `unit` is safe at full concurrency; `integration` includes
subprocess or durable on-disk state
([Testing Conventions](../../testing-conventions.md), §Marker 分层).

Commit `601206e4` only adds a module-level `serial` marker. Because
`tests/conftest.py::pytest_collection_modifyitems` automatically adds `unit` to every test without
an `integration` marker, the snapshot-admin subprocess cases remain in the parked-Dolt unit gate.
The S8-2 record explicitly says they were not marked integration because they do not require Dolt;
that substitutes the Dolt gate for the broader frozen integration definition.

Read-only collection on the reviewed tree proves the mismatch:

```text
cd vnext/repository_service
uv run pytest --collect-only -q -n 0 -m unit tests/test_snapshot_admin.py
48/56 tests collected (8 deselected)

uv run pytest --collect-only -q -n 0 -m integration tests/test_snapshot_admin.py
8/56 tests collected (48 deselected)
```

The unit selection includes, among others,
`test_missing_command_exits_2`, `test_unknown_command_exits_2`,
`test_hold_checkpoints_and_holds_root_lock`,
`test_signal_during_dolt_check_reaps_child_and_releases_lock`, and the unit-shape
`test_incomplete_restore_copy_fails_check` cases. Their helpers are concrete subprocess calls:

- `tests/support/snapshot_admin_harness.py::run_snapshot_admin` calls `subprocess.run` with a
  fixed timeout;
- `run_hold` and `run_check` delegate to that subprocess helper;
- `spawn_hold` calls `subprocess.Popen`, and `wait_ready_json` / `terminate_hold` use fixed
  readiness and exit budgets.

Of the 48 currently selected unit nodeids, 46 execute these subprocess helpers; the other two are
pure in-process checkpoint/restore-helper cases. The broad module-level `serial` marker therefore
both leaves subprocess/lifecycle cases in `unit` and serializes unrelated in-process cases. A green
parked-Dolt result proves only that Dolt is unnecessary; it does not satisfy the S8 marker contract.

This is an S8 acceptance blocker even though S8-4 passed: marker classification is an explicit gate,
and the full regression used the same incorrect marker selection. The finding routes to **S8-2**.
The owning implementation step must classify the affected nodeids according to the frozen
unit/integration/serial meanings, then rerun exact marker collection, the affected snapshot-admin
tests, parked-Dolt `-m unit`, and required static checks. Because the repair changes test source and
parallel/serial counts after S8-4, it must also refresh the exact three-ignore full regression counts
and the S8-5 clean-source/leak review packet before a fresh S8-6 review.

## Reviewed evidence without additional findings

### Entry, range, and scope

- `5f474ce2` and `1bfa1d7f` are ancestors of the reviewed HEAD. The S8 range has no production,
  Dockerfile, lockfile, Compose, entrypoint, client-image, or container-harness change.
- S3 cleanup dispositions and S6/S7 evidence remain carried records; the range does not reopen
  them or expand W1/W2, S9, or S10 into S8.

### Static, worker, and source regression

- S8-2 records all five package ruff/mypy results and preserves the first failed parked-Dolt run
  plus rerun. Those command records are internally consistent, but the parked-Dolt PASS cannot
  close the finding above.
- S8-3 records all five exact owner/supporting nodeids, `5 passed`, two diagnostic worker warnings,
  bounded convergence, `CommandResult.cancelled`, and final zero bridge/Dolt/query-temp/thread/
  work-root inventory. The warnings are correctly treated as diagnostics, not a count gate.
- S8-4 uses exactly the three Docker-starting file ignores. Its six suite rows balance collected
  against passed/skipped/failed: `242`, `152`, `154`, `35`, `1636`, and `200`; the only skip is the
  delegated-target container smoke. No first-failure repair is claimed.

### Hygiene and container decision

- The five raw old-reference files contain the recorded `27`, `53`, `126`, `143`, and `5` lines.
  The classifications distinguish current authority/negative use, unrelated terminology, and
  historical/superseded material. No S8 dead-symbol deletion occurred, so deletion-time consumer
  evidence is correctly `not_applicable`.
- S8-5 records zero owned Dolt PID, query temp, check temp home, pytest process, and work-root
  residual after cleanup. No contradictory current resource inventory was found.
- The S7 image at `5f474ce2` is described only as ancestor evidence. Since the S8 change is test/docs
  only, `Container rebuild required: no` and `Container gate for current HEAD: deferred` are
  accurate. S9 no-ignore sealing and S10 production/Compose/W1/W2/v8 gates remain deferred.

## Docker / Compose decision

```text
Current HEAD: 6ddd94d78a28c8345613693e6b487b3de69e84b7
Container rebuild required: no
Reason: reviewed S8 range changes test classification and documentation only; no image, dependency, deployment, container harness, or container-only runtime boundary changed
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

## Verdict

```yaml
review_status: fail
reviewed_head: 6ddd94d78a28c8345613693e6b487b3de69e84b7
reviewed_range: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09..6ddd94d78a28c8345613693e6b487b3de69e84b7
finding_count: 1
severity:
  p1_stage_blocker: 1
blocker_count: 1
allow_s8_handoff: no
return_step: S8-2
container_rebuild_required: no
container_gate_for_current_head: deferred
production_retest_required: yes
S8_exit: no-go
S9_ready: no
phase_2_complete: no
```

在 marker finding 修复、所需门禁与 current-tree counts 重新记录、并通过新的独立 S8-6
review 之前，不得进入 S8-7，也不得把当前 S8-4/S8-5 记录写成 S9-ready handoff。
