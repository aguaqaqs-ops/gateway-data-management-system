# P2-R6-S8 - Independent Implementation Re-review

状态：`pass`

日期：2026-08-17

本记录是 S8-6 P1 修复后的新一轮独立只读 implementation review。此前失败记录
[p2-r6-s8-implementation-review.md](p2-r6-s8-implementation-review.md) 保留原样，未被改写。
本审核检查修复后的实际 test marker、S8-2 repair rerun、S8-4 exact three-ignore rerun、
S8-5 hygiene rerun、当前 SHA 与工作树；没有修改 production、test、deployment 或 handoff，
也没有运行 Docker/Compose、W1/W2、v8 或 S9 no-ignore candidate seal。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §8

失败记录：[P2-R6-S8 Independent Implementation Review](p2-r6-s8-implementation-review.md)

修复记录：[P2-R6-S8 Step 2 - Classification Repair](p2-r6-s8-step-2-classification-repair.md)

## Review identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_head: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
reviewed_range_since_failed_review: 6ddd94d78a28c8345613693e6b487b3de69e84b7..2ef884278b4998dde1e5fe224532c89b7a0cd73a
full_s8_range: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09..2ef884278b4998dde1e5fe224532c89b7a0cd73a
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
repair_sha: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
repair_is_ancestor: yes
review_worktree_clean_at_start: no
untracked_preserved_failed_review: docs/backend-vnext/refactoring/temporary/p2-r6-s8-implementation-review.md
production_code_changed_in_repair: no
test_classification_changed_in_repair: yes
docker_or_compose_changed_in_repair: no
public_contract_changed: no
phase_2_complete: no
```

The only source change since the failed review is `3e4bd1fc`. It removes the module-level
`pytestmark = pytest.mark.serial`, adds `integration` + `serial` to the 46 subprocess/lifecycle
nodeids, leaves the two in-process cases as unit, and renames stale `_UNIT_*` helper aliases to
`_NON_DOLT_*`. `2ef88427` adds only the rerun evidence. The untracked failed review record was
present at review start and remains unchanged.

## Finding closure

The prior P1 required all subprocess/lifecycle snapshot-admin tests to be `integration` and
fixed-time cases to be `serial`, without serializing the two pure in-process tests. The repair
matches that contract:

```text
uv run pytest --collect-only -q -n 0 -m unit tests/test_snapshot_admin.py
2/56 tests collected (54 deselected)

uv run pytest --collect-only -q -n 0 -m integration tests/test_snapshot_admin.py
54/56 tests collected (2 deselected)

uv run pytest --collect-only -q -n 0 -m 'integration and serial' tests/test_snapshot_admin.py
53/56 tests collected (3 deselected)

uv run pytest --collect-only -q -n 0 -m 'integration and not serial' tests/test_snapshot_admin.py
1/56 tests collected (55 deselected)
```

The two unit nodeids are exactly:

```text
tests/test_snapshot_admin.py::test_checkpoint_truncate_is_quiescent_without_helper
tests/test_snapshot_admin.py::test_restore_procedure_rejects_non_empty_overlay_target
```

The sole non-serial integration nodeid is the pre-existing
`test_check_does_not_mutate_business_files_schema_or_head`; it has no fixed-time budget and is
correctly left in the parallel pass. The 46 subprocess nodeids are collected as integration and
serial, including the `run_snapshot_admin`/`run_hold`/`run_check`/`spawn_hold` cases identified by
the failed review.

## Rerun evidence

### S8-2 classification and static

The repair record reports focused `test_snapshot_admin.py`: `56 passed in 37.00s`, five-package
ruff/mypy pass, and `git diff --check: pass`. The parked-Dolt unit rerun reports:

```text
1449 collected
1448 passed, 1 skipped
dolt restored: yes
parked leftover: no
```

The 46-node reduction from the prior 1495 unit collection is consistent with the independent
2/56 collection above. The one skip remains the expected delegated-target cgroup test; no
Dolt-missing skip is reported.

### S8-4 source regression

The rerun preserves the exact three Docker-starting file ignores and reports `exit_code=0`, with no
failure or unclassified skip:

| suite | collected | passed | skipped | failed | duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | 242 | 242 | 0 | 0 | 0.81s |
| repository_contracts | 152 | 152 | 0 | 0 | 0.20s |
| repository_client | 154 | 154 | 0 | 0 | 1.26s |
| backend | 35 | 35 | 0 | 0 | 0.64s |
| repository_service parallel | 1639 | 1638 | 1 | 0 | 105.46s |
| repository_service serial | 197 | 197 | 0 | 0 | 189.90s |

The service total remains 1836. The expected 3-nodeid shift from serial to parallel is consistent
with removing the module-level serial marker: the two pure unit cases and the existing non-serial
integration case are no longer forced into the serial pass. The only skip is the expected
delegated-target cgroup smoke test.

### S8-5 hygiene and carried worker evidence

The hygiene rerun repeats all five old-reference searches into a new raw directory, classifies the
additional self-hit/evidence-document matches, preserves historical material, and reports no
unclassified current semantic. It records no S8 deletion, `git_diff_check: pass`, and zero owned
Dolt/query-temp/check-temp/process/work-root residual. The renamed test aliases are not production
dead-symbol deletion and do not reopen R5-CLEANUP-06.

S8-3 worker evidence is unchanged and remains valid: the repair does not touch worker/Arrow/process
implementation or its focused tests, and the exact three-ignore source rerun exercises the current
tree. No W1/W2 or Compose scope was added.

## Scope and container review

- S3 cleanup dispositions and S6/S7 carried evidence remain closed; no public Contract, persisted
  state, topology, capacity, S9, or S10 scope expansion is present.
- The repair changes test classification only. No Dockerfile, dependency closure, Compose,
  entrypoint, health/readiness, client image, or container harness boundary changed.
- The ancestor S7 image and Compose results remain ancestor evidence for `5f474ce2`; current-head
  container validation remains correctly deferred.

```text
Current HEAD: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
Container rebuild required: no
Reason: marker classification repair, tests and evidence docs only; no image/deployment/container-only runtime boundary changed
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

## Verdict

```yaml
review_status: pass
reviewed_head: 2ef884278b4998dde1e5fe224532c89b7a0cd73a
finding_count: 0
blocker_count: 0
prior_review_findings: 1
prior_review_status: fail
prior_p1: closed
allow_s8_handoff: yes
container_rebuild_required: no
container_gate_for_current_head: deferred
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-7 final S8 handoff in a new conversation
```

S8-6 now has zero open findings and permits S8-7. S8 exit and S9 readiness remain unset until the
documentation-only S8-7 handoff verifies the clean reviewed SHA and all evidence fields.
