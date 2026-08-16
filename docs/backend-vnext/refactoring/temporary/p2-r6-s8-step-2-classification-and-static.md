# P2-R6-S8 Step 2 — Classification and Static Gates

状态：`pass`

日期：2026-08-16

本记录是 S8-2 的分类与静态门禁证据。本步运行五包 ruff/mypy、parked-Dolt
`-m unit`、五条 S8 focused nodeid 的 strict-marker 收集，以及 `git diff --check`。
没有运行 S8-3 worker 运行时/残留审计，没有运行 S8-4 三 ignore 全量回归，
也没有重跑 W1/W2 或 Compose。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §4
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md)
入口记录：[P2-R6-S8 Step 0 — Entry Reconciliation](p2-r6-s8-step-0-entry-reconciliation.md)
设计审核：[P2-R6-S8 Independent Design Review](p2-r6-s8-design-review.md)

## Entry identity

S8-2 开始时用 `git rev-parse HEAD` 取得字面量 SHA。该 SHA 与 S8-1
`reviewed_design_sha` 一致。本文件的后续 docs commit 不是实现入口 SHA。

```yaml
branch: phase1/gate-ownership-repair
implementation_start_sha: 77a43ebea9d8c97bac3e3c6987307e71413a7e4b
classification_repair_sha: 601206e4f9bd4c3d20c9b9e8b0b076127d0b4f4f
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s8_1_reviewed_design_sha: 77a43ebea9d8c97bac3e3c6987307e71413a7e4b
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
allow_s8_implementation: yes
production_code_changed: no
test_classification_changed: yes
docker_or_compose_changed: no
public_contract_changed: no
phase_2_complete: no
```

S8-2 开始时 `git status --short`：

```text
?? docs/backend-vnext/refactoring/temporary/p2-r6-s8-design-review.md
```

`vnext/**` 无已跟踪改动。唯一未跟踪文件是 S8-1 只读审核记录，不是未知生产漂移。
Dolt 入口状态：`/usr/local/bin/dolt` 可执行，`/usr/local/bin/dolt.parked` 不存在。

## Five-package static

工具版本（各包 `uv.lock` 钉死同一组）：

```text
ruff 0.15.21
mypy 2.3.0 (compiled: yes)
pytest 9.1.1
Python 3.14.6
```

命令：

```bash
for package in shared_kernel repository_contracts repository_service repository_client backend; do
  (cd vnext/$package && uv run ruff check . && uv run mypy)
done
```

| package | ruff | mypy |
| --- | --- | --- |
| shared_kernel | All checks passed | Success: no issues found in 34 source files |
| repository_contracts | All checks passed | Success: no issues found in 15 source files |
| repository_service | All checks passed | Success: no issues found in 195 source files |
| repository_client | All checks passed | Success: no issues found in 26 source files |
| backend | All checks passed | Success: no issues found in 26 source files |

分类修复后再次运行 `repository_service` ruff/mypy：通过，mypy 仍为 195 files。

## Parked-Dolt unit classification

环境门禁：binary 存在且未被 parked，因此执行 `mv`。使用 EXIT trap，pytest 失败也会还原。

### First run (failed)

```text
16 workers [1495 items]
8 failed, 1486 passed, 1 skipped in 146.13s (0:02:26)
pytest_status=1
dolt restored: yes
parked leftover: no
```

失败全部在 `tests/test_snapshot_admin.py`，表现为 `snapshot_admin` 子进程 ready/CLI
timeout，而不是 Dolt 可执行文件缺失后的 fail-closed：

```text
tests/test_snapshot_admin.py::test_ready_signal_releases_lock[15]
tests/test_snapshot_admin.py::test_broken_stdout_fails_closed_and_releases_lock
tests/test_snapshot_admin.py::test_uninitialized_layout_exits_4
tests/test_snapshot_admin.py::test_unknown_command_exits_2
tests/test_snapshot_admin.py::test_ready_signal_releases_lock[2]
tests/test_snapshot_admin.py::test_hold_checkpoints_and_holds_root_lock
tests/test_snapshot_admin.py::test_ready_json_omits_host_paths_and_secrets
tests/test_snapshot_admin.py::test_signal_during_dolt_check_reaps_child_and_releases_lock
```

隔离证明（仍 parked，精确 nodeid，`-n 0`，无 `-k` / `--ignore`）：

```text
8 passed in 8.41s
dolt restored: yes
```

这些测试不依赖真实 Dolt。失败原因是大量带 subprocess timeout 的 CLI 用例被自动标成
`unit`，在权威命令 `uv run pytest -m unit` 的默认 `-n auto` 下与 16 个 worker 争用
CPU。这属于 marker 分类失败，owning scope 在本步。

### Classification repair

在 [`vnext/repository_service/tests/test_snapshot_admin.py`](../../../vnext/repository_service/tests/test_snapshot_admin.py)
增加模块级 `pytestmark = pytest.mark.serial`。该文件的 CLI 用例通过
`run_snapshot_admin` / `run_hold` / `run_check` / `spawn_hold` 使用固定 subprocess
timeout，按 Testing Conventions 必须 `serial`。未把它们改标为 `integration`：parked
隔离已证明它们不需要 Dolt。未使用 `-m "unit and not serial"`、`--ignore` 或 `-k`
掩盖失败。

### Rerun (passed)

```text
16 workers [1495 items]
1494 passed, 1 skipped in 63.76s (0:01:03)
pytest_status=0
dolt restored: yes
parked leftover: no
/usr/local/bin/dolt executable after restore
```

唯一 skip 是既有容器门禁，不是 Dolt 错分类：

```text
tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup
skipif GATEWAY_P2R1_TARGET_CONTAINER != "1"
reason: runs only inside the delegated target container
```

该 skip 不是 required S8 nodeid，也不表示 unit 套件依赖 Dolt。

## Focused S8 nodeid markers

精确收集五条 nodeid，未使用宽泛 `-k` 或 `--ignore`。`--strict-markers` 已在
`repository_service` `addopts` 中生效。

| nodeid | collected markers | `-m unit` |
| --- | --- | --- |
| `tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files` | `integration`, `serial`, `xdist_group` | deselected |
| `tests/test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled` | `integration`, `serial`, `xdist_group` | deselected |
| `tests/test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream` | `integration`, `serial`, `xdist_group` | deselected |
| `tests/test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor` | `unit`, `serial`, `xdist_group` | selected |
| `tests/test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit` | `unit`, `serial`, `xdist_group` | selected |

```text
five focused nodeids collected: 5
-m unit: 2/5 collected (3 HTTP integration deselected)
-m "serial and integration": 3/5 collected (2 Arrow unit+serial deselected)
```

HTTP 三条文件级 `pytestmark = pytest.mark.integration` 且函数级 `@pytest.mark.serial`。
Arrow 两条文件级 `pytestmark = pytest.mark.unit` 且函数级 `@pytest.mark.serial`，无
`integration`，因此进入 parked-Dolt `-m unit`。本步只收集/验证 marker；三条 HTTP
integration 的运行时与 leak inventory 归 S8-3。Arrow 两条在 parked-Dolt unit 中执行
不构成 S8-3 worker-convergence PASS。

## Touched paths and diff check

```text
git diff --check: pass
```

| path | class |
| --- | --- |
| `vnext/repository_service/tests/test_snapshot_admin.py` | S8-2 owning-scope marker classification |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-2-classification-and-static.md` | this evidence |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-design-review.md` | S8-1 review record present at start; not rewritten |

未触碰 Dockerfile、Compose、entrypoint、依赖锁或 container harness。没有 production
行为修复。没有删除 dead helper。

## Docker / Compose decision

```text
Current HEAD: 601206e4f9bd4c3d20c9b9e8b0b076127d0b4f4f
Container rebuild required: no
Reason: test marker classification and documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S8-3 worker convergence; S8 source full regression with exact three Docker ignores; S9 no-ignore seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据，不得写成当前 HEAD container PASS。
本证据文件的 docs commit 是 `601206e4` 的文档后代，不改变 container identity。

## Exit

```yaml
five_package_static: pass
parked_dolt_unit: pass
focused_marker_collection: pass
git_diff_check: pass
owning_scope_repair: snapshot_admin module serial marker
worker_convergence: not_run
source_regression_with_exact_docker_ignores: not_run
container_gate_for_current_head: deferred
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-3 worker convergence and focused regression
```

下一步按执行计划运行 S8-3 owner/supporting nodeid（`integration`/`serial`，`-n 0`），
记录 warning、bounded convergence 和零残留。本记录不授权 S8 exit、S9 candidate seal
或 Phase 2 completion。
