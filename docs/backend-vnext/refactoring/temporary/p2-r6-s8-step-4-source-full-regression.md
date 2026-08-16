# P2-R6-S8 Step 4 — Source Full Regression

状态：`pass`

日期：2026-08-16

本记录是 S8-4 的精确三 ignore 源码全量回归证据。权威命令一次通过，无失败、
无未分类 skip、无源码修复。没有重跑 W1/W2、无 ignore 全量（S9）或四条
Compose nodeid（S10），也没有修改 production/test/deployment 文件。

权威计划：[P2-R6-S8 Full Regression and Candidate Preparation Execution Plan](../formal/plans/p2-r6-s8-full-regression-execution-plan.md) §6
权威设计：[P2-R6-S8 Full Regression and Candidate Preparation Design](../formal/plans/p2-r6-s8-full-regression-design.md) §3.3
S8-3：[P2-R6-S8 Step 3 — Worker Convergence and Focused Regression](p2-r6-s8-step-3-worker-convergence.md)

## Entry identity

S8-4 开始时用 `git rev-parse HEAD` 取得字面量 SHA。该 SHA 与 S8-3 证据提交一致。
本文件的后续 docs commit 不是实现入口 SHA。

```yaml
branch: phase1/gate-ownership-repair
implementation_start_sha: a27fe00453a910d6bdb2d0369b7923125d5d9278
s8_3_evidence_sha: a27fe00453a910d6bdb2d0369b7923125d5d9278
s8_2_evidence_sha: be2d1a03e0c03b7286d144b7609d62bfef663692
classification_repair_sha: 601206e4f9bd4c3d20c9b9e8b0b076127d0b4f4f
s8_entry_sha: 1bfa1d7f3eb6311d4895974bcec8238cf7cd6f09
s7_validated_code_sha: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
s7_is_ancestor: yes
s8_2_parked_dolt_unit: pass
s8_2_five_package_static: pass
s8_3_worker_convergence: pass
allow_s8_implementation: yes
production_code_changed: no
test_code_changed: no
docker_or_compose_changed: no
public_contract_changed: no
capacity_rerun: no
phase_2_complete: no
```

S8-4 开始时 `git status --short` 为空。`/usr/local/bin/dolt` 可执行，
`/usr/local/bin/dolt.parked` 不存在。

## Authoritative command

在仓库根执行，加且仅加三条 Docker-test `--ignore`。未附加 `-m`、`-k`、
`--ignore-glob`、`xfail`、skip、retry 或 accepted-flake。

```bash
./vnext/scripts/run-tests.sh \
  --ignore=tests/test_import_compose_e2e.py \
  --ignore=tests/test_versioned_read_compose_e2e.py \
  --ignore=tests/test_compose_lifecycle_negative_probes.py
```

`run-tests.sh` 把 `"$@"` 透传到六段 pytest。三条 ignore 文件均为
`integration`+`serial`，共 8 个 nodeid，只从 serial 段排除。`--collect-only`
同参数扫描未出现这三个文件名。静态 Dockerfile/Compose、build harness unit
和真实 Dolt integration 仍被收集。

被排除的精确 nodeid（S9 无 ignore 全量和 S10 Compose 门禁拥有，本步不跑）：

```text
tests/test_import_compose_e2e.py::test_compose_repository_service_import_restart_replay
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_inside_network
tests/test_versioned_read_compose_e2e.py::test_compose_remote_client_commit_pinned_read_from_gate_host
tests/test_versioned_read_compose_e2e.py::test_compose_repository_service_fresh_restart_restored_lifecycle
tests/test_compose_lifecycle_negative_probes.py::test_compose_missing_readiness_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_token_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_wrong_network_cleans_up
tests/test_compose_lifecycle_negative_probes.py::test_compose_non_empty_restore_target_cleans_up
```

权威命令 wall clock：`434521 ms`（约 7m15s），`exit_code=0`。

## Package commands and counts

collected 来自同 ignore 参数的 `--collect-only` 补充清单，不是替代门禁。
passed/skipped/failed/duration 来自权威命令本身。两列 collected 与
passed+skipped+failed 对齐。

| suite | command | collected | passed | skipped | failed | duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| shared_kernel | `uv run pytest -q` + 三 ignore | 242 | 242 | 0 | 0 | 0.99s |
| repository_contracts | `uv run pytest -q` + 三 ignore | 152 | 152 | 0 | 0 | 0.31s |
| repository_client | `uv run pytest -q` + 三 ignore | 154 | 154 | 0 | 0 | 1.98s |
| backend | `uv run pytest -q` + 三 ignore | 35 | 35 | 0 | 0 | 0.73s |
| repository_service parallel | `uv run pytest -q -m "not serial"` + 三 ignore | 1636 | 1635 | 1 | 0 | 191.68s |
| repository_service serial | `uv run pytest -q -m serial -n 0` + 三 ignore | 200 | 200 | 0 | 0 | 233.74s |

serial 段另有 `1636 deselected`（即 parallel 段那 1636 项），与
`--collect-only` 的 `200/1836 tests collected (1636 deselected)` 一致。
repository_service 在三 ignore 后的全集是 1836 项。

backend 段 pytest summary 有 1 个 `StarletteDeprecationWarning`
（`fastapi/testclient.py` 建议 `httpx2`）。这不是测试失败，也不改变 PASS。

## Skip classification

| nodeid | suite | reason | class |
| --- | --- | --- | --- |
| `tests/test_p2_r1_target_cgroup_smoke.py::test_target_container_has_real_delegated_cgroup` | repository_service parallel | `GATEWAY_P2R1_TARGET_CONTAINER != "1"`；`reason: runs only inside the delegated target container` | expected; not an S8 required nodeid |

隔离确认（精确 nodeid，`-rs`）：`SKIPPED [1] ... runs only inside the delegated target container`。
环境 `GATEWAY_P2R1_TARGET_CONTAINER` 未设置。该 skip 不是 Dolt 错分类，也不表示
套件依赖 Docker。

无 Dolt-missing skip。无其他 skip。无失败。

## Repair ledger

```yaml
repairs: none
first_failure: none
owning_scope_repair: none
container_boundary_touched: no
source_or_build_input_changed: no
rerun_of_authoritative_command_after_repair: not_applicable
```

权威命令第一次即 `exit_code=0`。没有进入失败循环，没有修改 production、test
或 deployment 文件。

## Touched paths and diff check

本步无 production/test 源码改动。证据文件为 docs-only。

```text
git diff --check: pass
```

| path | class |
| --- | --- |
| `docs/backend-vnext/refactoring/temporary/p2-r6-s8-step-4-source-full-regression.md` | this evidence |

未触碰 Dockerfile、Compose、entrypoint、依赖锁或 container harness。没有
production 行为修复。没有删除 dead helper。没有重跑 parked-Dolt unit 或
S8-3 focused worker gate：本命令未暴露分类或 worker 失败。

## Docker / Compose decision

```text
Current HEAD: a27fe00453a910d6bdb2d0369b7923125d5d9278
Container rebuild required: no
Reason: source full regression and documentation only; no Dockerfile, dependency closure, Compose, entrypoint, health/readiness, client image or container harness change
Last verified image revision: 5f474ce2ccf15f11ea07f263edf3fb04c771d410
Last verified source-tree/image id: sha256:b1e7576c8444967e4754774368ac34186724787494ff8fae6bb950b433c71ce2 / sha256:ba0ac70a6c63d2f415ff75328a210332ec5948edae6e654a29d5132e85849fa3
Container gate for current HEAD: deferred
Deferred gates/nodeids: S9 no-ignore ./vnext/scripts/run-tests.sh and exact candidate seal; S10 four Compose nodeids, W1/W2 and v8 formal --runs 5
Required execution point: S9 exact candidate / S10 final production
```

S7 image 与四条 Compose PASS 仍是祖先 `5f474ce2` 证据，不得写成当前 HEAD
container PASS。本证据 docs commit 是文档后代，不改变 container identity。

## Exit

```yaml
source_regression_with_exact_docker_ignores: pass
exact_docker_ignores: 3
unexpected_skip_or_failure: no
authoritative_exit_code: 0
repairs: none
parked_dolt_unit: pass
five_package_static: pass
worker_convergence: pass
git_diff_check: pass
container_gate_for_current_head: deferred
S8_exit: no
S9_ready: no
production_retest_required: yes
phase_2_complete: no
next: S8-5 hygiene and candidate preparation
```

下一步按执行计划做 old-reference 分类、dead consumer 搜索、leak audit 和
clean-source review packet。若 S8-5 在本证据 docs commit 之后立即开始且无
源码改动，可续在同一对话；任何源码修复后必须新开对话。本记录不授权 S8
exit、S9 candidate seal 或 Phase 2 completion。
