# P2-R6-S8 Step 2 — Classification Repair (S8-6 P1)

状态：`pass`

日期：2026-08-17

本记录关闭 S8-6 P1：`test_snapshot_admin.py` 的 subprocess CLI 测例被自动标成
`unit`。失败审查记录 [p2-r6-s8-implementation-review.md](p2-r6-s8-implementation-review.md)
未改写。没有重跑 S8-3、W1/W2、Compose 或无 ignore 全量。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §4 / §8 routing
原 S8-2：[p2-r6-s8-step-2-classification-and-static.md](p2-r6-s8-step-2-classification-and-static.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
s8_6_reviewed_head: 6ddd94d78a28c8345613693e6b487b3de69e84b7
classification_repair_sha: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
failed_review_preserved: yes
production_code_changed: no
test_classification_changed: yes
docker_or_compose_changed: no
public_contract_changed: no
phase_2_complete: no
```

开始时 `git status --short` 仅有未跟踪的失败审查记录，未纳入本修复提交。
`/usr/local/bin/dolt` 可执行，`dolt.parked` 不存在。

## Repair

删除模块级 `pytestmark = pytest.mark.serial`。46 个调用 `run_snapshot_admin` /
`run_hold` / `run_check` / `spawn_hold` 的 nodeid 改为 `@pytest.mark.integration`
且 `@pytest.mark.serial`。两个纯进程内用例保持自动 `unit`、无 `serial`：

```text
tests/test_snapshot_admin.py::test_checkpoint_truncate_is_quiescent_without_helper
tests/test_snapshot_admin.py::test_restore_procedure_rejects_non_empty_overlay_target
```

已有 8 个 `integration` nodeid 未改函数级标记。`test_check_does_not_mutate_business_files_schema_or_head`
仍无 `serial`；去掉模块级 `serial` 后它进入 parallel 段，这是原函数标记的本意。

重命名 `_UNIT_CHECK_FAULTS` / `_UNIT_INCOMPLETE_SHAPES` /
`_apply_unit_check_fault` 为 `_NON_DOLT_*`，避免 stale unit 声称。

## Marker collection

审查同口径 `--collect-only -q -n 0`：

```text
-m unit tests/test_snapshot_admin.py
2/56 tests collected (54 deselected)

-m integration tests/test_snapshot_admin.py
54/56 tests collected (2 deselected)
```

unit 两项即上面两个 in-process 用例。五条 S8-3 focused nodeid 仍收集为 5，
marker 未变。

## Focused and static

```text
uv run pytest -n 0 tests/test_snapshot_admin.py
56 passed in 37.00s
```

五包 `ruff check` / `mypy`：全部通过。`repository_service` mypy 仍为 195 files。

工具版本：ruff 0.15.21，mypy 2.3.0，pytest 9.1.1，Python 3.14.6。

```text
git diff --check: pass
```

## Parked-Dolt unit

binary 存在且未 parked，执行 `mv` + EXIT trap。

```text
16 workers [1449 items]
1448 passed, 1 skipped in 20.94s
pytest_status=0
dolt restored: yes
parked leftover: no
```

相对原 S8-2 parked 的 1495 collected，减少 46，与移出 unit 的 subprocess
nodeid 一致。唯一 skip 仍是
`test_target_container_has_real_delegated_cgroup`。

## Docker / Compose decision

```text
Current HEAD: 3e4bd1fca0e52a0497bbc5a7bf69071a744fd952
Container rebuild required: no
Reason: test marker classification only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

## Exit

```yaml
five_package_static: pass
parked_dolt_unit: pass
snapshot_admin_unit_collected: 2
snapshot_admin_integration_collected: 54
s8_6_p1: closed
source_regression_with_exact_docker_ignores: see rerun record
S8_exit: no
S9_ready: no
allow_s8_handoff: no
production_retest_required: yes
phase_2_complete: no
next: S8-4/S8-5 rerun evidence in this conversation; then new S8-6 review
```
