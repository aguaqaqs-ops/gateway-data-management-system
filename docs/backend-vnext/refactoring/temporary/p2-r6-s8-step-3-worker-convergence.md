# P2-R6-S8 Step 3 — Worker Convergence and Focused Regression

状态：`pass`

日期：2026-08-16

本记录是 S8-3 的 worker 收敛与 focused cleanup 证据。运行 1 条 owner + 4 条
supporting nodeid（精确 path，`-n 0`），采集 warning、bounded convergence 和
baseline/final 资源库存。没有运行 S8-4 三 ignore 全量回归，没有重跑 W1/W2 或
Compose，也没有修改 production 行为。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §5
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md) §3.2
S8-2：[P2-R6-S8 Step 2 — Classification and Static Gates](p2-r6-s8-step-2-classification-and-static.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
implementation_start_sha: be2d1a03e0c03b7286d144b7609d62bfef663692
s8_2_evidence_sha: be2d1a03e0c03b7286d144b7609d62bfef663692
classification_repair_sha: 601206e4f9bd4c3d20c9b9e8b0b076127d0b4f4f
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_2_parked_dolt_unit: pass
s8_2_five_package_static: pass
allow_s8_implementation: yes
production_code_changed: no
docker_or_compose_changed: no
public_contract_changed: no
capacity_rerun: no
phase_2_complete: no
```

S8-3 开始时 `git status --short` 为空。`/usr/local/bin/dolt` 可执行，
`/usr/local/bin/dolt.parked` 不存在。

## Focused command and counts

精确 nodeid，无 `-k` / `--ignore` / marker 排除。`-n 0`。`--log-cli-level=WARNING`
用于捕获诊断。收敛时限：生产 `_WORKER_JOIN_TIMEOUT_SECONDS = 30.0`，owner 内
registry/child `_wait_until(..., timeout_seconds=10.0)`。

```text
uv run pytest -n 0 --log-cli-level=WARNING --durations=10
  tests/test_versioned_read_http_integration.py::test_http_disconnect_cancels_worker_and_cleans_query_files
  tests/test_versioned_read_http_integration.py::test_http_disconnect_reports_command_result_cancelled
  tests/test_versioned_read_http_integration.py::test_http_runtime_shutdown_closes_active_row_stream
  tests/test_versioned_read_arrow_bridge.py::test_close_all_waits_for_worker_thread_not_false_survivor
  tests/test_versioned_read_arrow_bridge.py::test_join_timeout_keeps_alive_worker_registered_until_exit
```

| nodeid | markers | result | call s | total s |
| --- | --- | --- | --- | --- |
| `...::test_http_disconnect_cancels_worker_and_cleans_query_files` (owner) | integration, serial | PASSED | 2.13 | 2.372 |
| `...::test_http_disconnect_reports_command_result_cancelled` | integration, serial | PASSED | 10.80 | 10.902 |
| `...::test_http_runtime_shutdown_closes_active_row_stream` | integration, serial | PASSED | 1.60 | 1.719 |
| `...::test_close_all_waits_for_worker_thread_not_false_survivor` | unit, serial | PASSED | 0.25 | 0.253 |
| `...::test_join_timeout_keeps_alive_worker_registered_until_exit` | unit, serial | PASSED | 0.15 | 0.153 |

```text
collected 5
5 passed, 1 warning in 16.11s
failed: 0
skipped: 0
```

pytest summary 的 1 warning 是 `PytestAssertRewriteWarning: Module already imported so cannot be rewritten; anyio`（inventory 插件与 pytest.main 同进程导入），不是 worker 诊断，也不改变 PASS。

## Warning and convergence

诊断原文：`versioned read arrow bridge worker did not exit in time`。政策是 bounded
convergence + 零最终残留，不是 warning-count 门禁。无 warning 也可以 PASS。

| event | nodeid | treatment |
| --- | --- | --- |
| logging WARNING at `arrow_bridge.py:340` | `test_http_disconnect_reports_command_result_cancelled` | 诊断；随后测试 PASSED；call 10.80s < 30s join deadline |
| logging WARNING at `arrow_bridge.py:340` | `test_join_timeout_keeps_alive_worker_registered_until_exit` | 该用例主动 `join_timeout_seconds=0.05` 触发诊断，再等待 worker 退出并 `close_all`；PASSED；call 0.15s |
| none | owner `test_http_disconnect_cancels_worker_and_cleans_query_files` | probe 在 join deadline 前释放 worker；call 2.13s |
| none | `test_http_runtime_shutdown_closes_active_row_stream` | shutdown 清空 registry 且 worker 已退出 |
| none | `test_close_all_waits_for_worker_thread_not_false_survivor` | close_all 等待 unregister，无 false survivor |

Owner 中间态（测试断言，非最终残留）：

- `BRIDGE_REGISTRY.snapshot() != ()` 出现在 `worker_can_finish` 之前
- `close_entered` 后 0.5s 内 cleanup 尚未完成（证明 close 等待 worker）
- `worker_can_finish` 之后 `close_completed`、registry `== ()`、`_active_children == ()`、observed PIDs reaped、`query-*.sql == []`

`CommandResult.cancelled` 由 supporting `test_http_disconnect_reports_command_result_cancelled` 拥有并 PASSED。没有为了重试 cleanup 修改生产结果。

```yaml
warning_count_diagnostic: 2
warning_count_gate: not_used
convergence_deadline_join_seconds: 30.0
owner_elapsed_call_seconds: 2.13
cancelled_supporting_elapsed_call_seconds: 10.80
unbounded_convergence: no
```

## Resource inventory

进程内 baseline/final 在同一 pytest session 采集。host `/proc` Dolt PID 与
`list_host_thread_idents()` 相对 baseline。

| item | baseline | final (session end) | S8-owned extra after keepdir removal |
| --- | --- | --- | --- |
| bridge registry | 0 `()` | 0 `()` | 0 |
| dolt pids | 0 | 0 | 0 |
| host thread idents | 0 | 0 | 0 |
| query-*.sql | 0 | 0 | 0 |
| snapshot-check-dolt homes | 0 | 0 | 0 |
| pytest work-root extra | — | `pytest-186` (keep-last tmp_path, 136M data-root; seed `cancel.sql`/`cancelled.sql`/`shutdown.sql` only, **no** `query-*.sql`) | 0 after removing `pytest-186` |

`pytest-186` 是 pytest 默认保留的最近一次 `tmp_path`，不是 worker query-temp 或活进程。
gate 后删除该 session 目录；无 `query-*.sql`、无 Dolt 子进程、无 bridge、无 host thread。
`/tmp/pytest-of-root/pytest-184` 与 `pytest-185` 时间戳为 S8-2 parked-Dolt unit
（22:44 / 22:46），不是本 gate 新增 extra，不记为 S8-3 residual。

```text
residual_inventory gate=s8-3-worker
  bridge=0 dolt_delta=0 query_temps=0 host_threads=0
  check_temp_homes=0 s8_owned_work_root_dirs=0
```

## Touched paths and diff check

本步无 production/test 源码改动。证据文件为 docs-only。

```text
git diff --check: pass
```

## Docker / Compose decision

```text
Current HEAD: be2d1a03e0c03b7286d144b7609d62bfef663692
Container rebuild required: no
Reason: focused pytest and documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S8 source full regression with exact three Docker ignores; S9 no-ignore seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据。本证据 docs commit 是文档后代，
不改变 container identity。

## Exit

```yaml
worker_convergence: pass
zero_owned_process_thread_dolt_query_temp_work_root_residual: yes
command_result_cancelled_owned: pass
production_result_unchanged: yes
w1_w2_rerun: no
source_regression_with_exact_docker_ignores: not_run
container_gate_for_current_head: deferred
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-4 source full regression with exact three Docker ignores
```

下一步按执行计划在**新对话**运行
`./vnext/scripts/run-tests.sh` 加且仅加三条 Docker-test `--ignore`。本记录不授权
S8 exit、S9 candidate seal 或 Phase 2 completion。
