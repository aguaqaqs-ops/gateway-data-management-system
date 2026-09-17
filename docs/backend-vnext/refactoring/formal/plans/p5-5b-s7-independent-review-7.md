# P5-5B-S7 Independent Review 7 — Execution-Plan Owner Evidence + F8 Closeout

状态：**PASS — S7 closure 成立；S8 entry eligible（附 S8 前置 gate）**

日期：2026-09-17 (UTC+8)

Owner：Independent reviewer（read-only；本文件是唯一写入）

> **Supersedes** [p5-5b-s7-independent-review-6.md](p5-5b-s7-independent-review-6.md)（其在 execution-plan §490–491 owner evidence 补齐前 premature 声明 pass）。

## 1. Decision

```yaml
stage: P5-5B-S7-owner-evidence-and-f8-closeout
review_target: e5c43c0c9f71de3cd2e602504ec9034f16add8af
implementation_seal: e5c43c0c9f71de3cd2e602504ec9034f16add8af
records_head: pending_this_commit
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_round_2: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
remediation_round_3: 7c511c4b8b59842b67d24083abf274ba620b2e7e
remediation_round_4: e5c43c0c9f71de3cd2e602504ec9034f16add8af
decision: pass
findings_closed: [S7-F1, S7-F4, S7-F6, S7-F7, S7-F8, S7-O2-owner-T3-crash-barrier, S7-O2-owner-repository-restart-journey]
findings_reclassified: [S7-F2]
findings_open: []
s7_closure: pass
s8_entry: eligible
s8_entry_preconditions: 五包 static、权威 runner、三镜像 conjunction/full journey smoke（S8）
observations_non_blocking: [S7-O1, S7-O3, S7-O4]
p5_5b_slice_exit: not_declared
timezone: Asia/Shanghai
```

## 2. Owner evidence closed

| Owner | Test | Marker | Result |
| --- | --- | --- | --- |
| T3 `after_business_finalize_commit_before_worker_ack` | `test_await_import_finalize_response_loss_after_terminal_commit_before_worker_ack` | integration + serial | **pass** |
| Repository restart consumer journey | `test_await_import_result_consumes_matching_terminal_after_repository_restart` | integration + serial + requires_dolt | **pass** |

**§11 语义（测试 docstring + 本 review 记录，不改 production）**：design §11「replay 返回既有 Submission」在此窗口指 **T3 business finalize 已 durable**；commit-before-ack 时 worker 行为是 **terminal durable fact eliminates reclaim**（无 dup submission、无 reclaim），而非再次 claim/re-execute handler。

## 3. Gates re-run @ `e5c43c0c`

| Gate | 命令 | 结果 |
| --- | --- | --- |
| New serial owners | `pytest -m 'integration and serial' tests/test_submit_recovery.py -k 'after_terminal_commit_before_worker_ack or repository_restart'` | **2 passed** |
| WorkerRuntime serial regression | `pytest -m 'integration and serial' tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'` | **2 passed, 9 deselected** |
| All four serial recovery owners | `pytest -m 'integration and serial' tests/test_submit_recovery.py -k 'after_terminal_commit_before_worker_ack or repository_restart or (worker_runtime and (finalize or stable_abort))'` | **4 passed, 9 deselected** |
| accumulated unit（22 files） | `pytest -m unit <ACCUMULATED>` | **319 passed** |
| integration non-serial selection | `pytest -m 'integration and not serial' tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py` | **26 passed, 11 deselected** |
| backend ruff / mypy | `ruff check .` / `mypy` | **pass / 377 source files OK** |

## 4. Round 4 remediation paths

| Item | Paths |
| --- | --- |
| T3 crash barrier owner | `tests/test_submit_recovery.py`（UoW commit 后 fault 注入 + WorkerRuntime `_run_claim`） |
| Repository restart owner | `tests/test_submit_recovery.py`, `tests/support/submit_job_harness.py`（`shutdown_repository_service_client`, `build_dolt_compatible_prepare_publication`） |
| F8 closeout | `p5-5b-s7-acceptance.md`, `p5-5b-s7-remediation-handoff.md`, 本 review |

## 5. S8 entry note

S7 不宣称 `./vnext/scripts/run-tests.sh` 全量、五包 static、镜像 conjunction gate 已通过；上述为 S8 前置条件。
