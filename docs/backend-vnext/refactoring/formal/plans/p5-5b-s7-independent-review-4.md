# P5-5B-S7 Independent Review 4 — Remediation Closure Round 2 Verification

状态：**changes_required — S7-F1/F4/F6 确认 closed，S7-F2 确认 reclassified；新增 S7-F7（blocker-class）+ S7-F8（record）**

日期：2026-09-17

Owner：Independent reviewer（read-only；本文件是唯一写入）

## 1. Review target

```yaml
stage: P5-5B-S7-remediation-closure-round-2
review_target: 30193dd5d3b34ec82da382cd7d85650cd98a3bb7
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_draft: 4cda6b9c
diff_scope: git diff 37fa7c21..30193dd5
changed_paths_verified:
  - vnext/backend/src/gateway_backend/application/submission/finalize_transaction.py
  - vnext/backend/src/gateway_backend/application/submit_jobs.py
  - vnext/backend/tests/test_architecture.py
  - vnext/backend/tests/test_submit_compose_e2e.py
  - vnext/backend/tests/test_submit_recovery.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-*.md, p5-5b-s6-independent-review-5.md
decision: changes_required
findings_open: [S7-F7, S7-F8]
findings_closed: [S7-F1, S7-F4, S7-F6]
findings_reclassified: [S7-F2]
observations_non_blocking: [S7-O1, S7-O2, S7-O3]
operations_package_untouched: true   # git diff 无 operations/**、application/recovery.py
s8_entry: blocked
p5_5b_slice_exit: not_declared
```

Review 方法：先核 authority/changed paths，再逐 finding 复核 owner test；对 F1 做 pre-fix 判别力
复核、对 stable abort 分支做只读运行探针（§5）。未运行五包 static、权威 runner、任何镜像/Compose
gate（属 S8，见 §7）。

## 2. Finding closure verification

| Finding | 交付方声称 | 独立核验 | 结论 |
| --- | --- | --- | --- |
| S7-F1 | finalize 经 `publish_operation` + `defer_operation_terminal`；WorkerRuntime serial 测试 | 见 §3 | **closed** |
| S7-F4 | operator HTTP negative | 见 §4.1 | **closed** |
| S7-F6 | architecture 屏障精确 allow | 见 §4.2 | **closed** |
| S7-F2 | reclassified → S8 | 见 §4.3 | **reclassified_deferred_to_s8（非 closed）** |

## 3. S7-F1 closure evidence（含判别力复核）

实现（HEAD 行号）：

- `submit_jobs.py:871-878`：T3 成功路径改为 `lease_session.publish_operation(_make_finalize_success_builder(...))`；
  builder 在 `_active_submit_transaction` 绑定的同一 UoW 内调用
  `finalize_submit_transaction(..., defer_operation_terminal=True)`，由 session 的
  `complete_operation` 收口 Step/Operation——**业务 finalize 与 Step/Operation terminal 同一 SQLite
  UoW**（design §10.2 的 single-transaction 要求保持）。
- 该分支不再有独立 UoW finalize + 裸 `return PUBLISHED`；`publish_operation` 设置
  `LeaseSession._completion_acknowledgment = PUBLISHED`（`lease_session.py:244`）。
- 旧 `FINALIZED and operation.status is SUCCEEDED → return PUBLISHED` 早返回已删除（无生产 caller：
  `finalize_submit_transaction` 唯一生产调用点是该 builder；单 UoW 下 step 与 attempt 不会分离）。

判别力（pre-fix 复核，read-only）：

```bash
# HEAD 测试文件 + parent(37fa7c21) source 前置（PYTHONPATH shadow，未改仓库）
cd vnext/backend && PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/tmp/p5_5b_s7_probe/parent_src:. .venv/bin/python -m pytest -q \
  -p no:cacheprovider -o addopts='' tests/test_submit_recovery.py \
  -k 'finalize_commits_lease_acknowledgment'
# 1 failed — ValueError: executor acknowledgment was not committed by LeaseSession
#            (parent_src/.../worker_runtime.py:383)
```

HEAD 同一 nodeid 通过（§6 gate 1）。测试经 `WorkerRuntime._run_claim`（非直调 handler），断言
Operation/Step SUCCEEDED、Attempt FINALIZED、`submission_records` count == 1，满足 review-1 对 F1
的 retest 要求。**F1 closed 成立。**

补充说明（非 finding）：owner test 使用未 routed 的 handler，而生产 claim 走
`build_recovery_routed_executor`→`_recover_external_effect_step`；该形态对 success 分支只追加
`finalize_handler_recovery` 的同一 session-fact 校验，cookie 语义相同，覆盖充分。

## 4. 其余 finding 复核

### 4.1 S7-F4 — closed

`tests/test_operator_recovery_http.py:412` 用 `advance_submit_to_external_step()`（step-2 =
`submit_import`，EXTERNAL_EFFECT）经真实 internal recovery route 发 `RETRY_FROM_CHECKPOINT`，断言
`409 / RECOVERY_CAPABILITY_CONFLICT`；同 fixture 存在正向对照
`test_operator_recovery_external_step_accepts_resume`（RESUME_RECONCILE 被接受），排除 fixture
假阳性。断言的是 capability guard 本体的 stable code。**closed。**

### 4.2 S7-F6 — closed

`test_architecture.py::test_repository_client_is_confined_to_repository_read_and_write` 现为
`allowed_files = (src/"http"/"runtime.py",)`（精确文件，非 `http/**`），扫描面仍为
`gateway_backend/**/*.py` 全量字符串检查；`test_worker_bootstrap_owns_concrete_process_composition`
追加 `gateway_backend.http.runtime` 到 bootstrap import allow-list。两者与 S6 handoff/review-5 记录的
生产接线（`operation_worker.py`→`http/runtime.py`→`gateway_repository_client`）一致。accumulated unit
319 passed（§6 gate 4）证明屏障与实现同步。**closed。**

### 4.3 S7-F2 — reclassified_deferred_to_s8（非 closed）

- 无效 smoke `test_compose_submit_accept_route_is_wired_for_unprepared_workspace`（只断言未准备
  workspace 的 4xx、且依赖 repository-service fallback/`skip`）已删除；`git diff` 只剩行尾空行。
- 保留的 `test_compose_three_process_submit_stack_smoke_and_backend_restart` 只覆盖 ready + backend
  restart + workspace 创建，**不**声称 Accept→upload→import→poll→T3→read。
- S7 文档（acceptance / review-3 / handoff）均将完整 journey 与 container conjunction 记为 S8 §6.4
  defer，未出现 full closure 表述。**reclassified 成立；S8 closure 前不得改记为 closed。**

## 5. New finding S7-F7 — await handler stable abort 分支裸 `PUBLISHED`（blocker-class）

- **Authority**：P4 executor 协议（`operations/worker_runtime.py:363-384`：返回的
  `ExecutorAcknowledgment` 必须等于 `LeaseSession.completion_acknowledgment()`；
  `operations/recovery.py:647-662`：PUBLISHED disposition 必须有 session fact）；design §10.3（matching
  ordinary not-published FAILED → 一个事务完成 Attempt→ABORTED + Operation/Step FAILED）；S7-F1 的
  闭包判据（handler 的 PUBLISHED 必须由 LeaseSession 提交）。
- **Exact path**：`vnext/backend/src/gateway_backend/application/submit_jobs.py`
  `build_await_import_result_handler` FAILED 分支（HEAD 880-914）：`abort_submit_transaction(...)`
  以 `_read_write_factory(deps.control_transaction_factory)` 在**独立 UoW** 内收口 Step/Operation 后
  `return ExecutorAcknowledgment.PUBLISHED`，session 未提交任何 fact。对该模块全部 13 个
  `return ExecutorAcknowledgment.*` 点逐条审计（433/502/511/529/588/644/655/680/797/870/878/896/914），
  其余 12 处均由 `publish_operation` / `publish_successor` 支撑，914（本分支）是唯一残留同类点。
- **Trigger 条件**：Repository operation 以**允许的** stable code（`IMPORT_REJECTED` /
  `EXPECTED_COMMIT_MISMATCH` / `VERIFICATION_FAILED_NOT_PUBLISHED`）FAILED——design §10.3/§11
  "matching ordinary not-published failure" 的正常业务路径，非异常注入。
- **Business consequence**：durable 业务状态仍然正确（Attempt ABORTED、Operation/Step FAILED，
  见下 §5 reproduction），但 worker claim 以 P4 协议错误收尾：
  - 非 routed / routed claim（`_run_claim`）：`ValueError: executor acknowledgment was not committed
    by LeaseSession`（`_emit_executor_failure(work, "unproven_acknowledgment")`），异常逃出
    `WorkerRuntime.run()` → worker 进程非预期退出 + 假 EXECUTOR_FAILED 信号；
  - recovery-routed 收口：`finalize_handler_recovery` 抛
    `ValueError: recovery returned PUBLISHED without committing session fact`（probe-C 以同一
    LeaseSession 复现 routed 收口顺序：handler 返回 PUBLISHED 后 session ack 仍为 None）。
  - Risk class **B**（SubmitAttempt/Operation/Step/occupancy/lease 恢复语义；非 A：无错误发布、
    无重复 Submission、无提前释放 occupancy）。
- **Reproduction（HEAD，read-only probe `/tmp/p5_5b_s7_probe/test_probe_abort_ack.py`）**：

```text
[probe-A unrouted handler]       outcome: ValueError: executor acknowledgment was not committed by LeaseSession
[probe-A unrouted handler]       db state: (FAILED, FAILED, ABORTED)
[probe-B routed executor]        outcome: ValueError: executor acknowledgment was not committed by LeaseSession
[probe-B routed executor]        db state: (FAILED, FAILED, ABORTED)
[probe-C handler return]         PUBLISHED
[probe-C session ack]            None
[probe-C recovery finalize]      raised ValueError: recovery returned PUBLISHED without committing session fact
[control: finalize success]      outcome: no-exception  → (SUCCEEDED, SUCCEEDED, FINALIZED)
```

  复现形态：`build_submit_worker_harness` + `_run_submit_to_await_claim`，await 阶段 transport 返回
  `FAILED/IMPORT_REJECTED`，用真实 claim 的 `worker_id/lease_token` 驱动
  `WorkerRuntime._run_claim`（probe-A/B）或 `handler(...)`+`finalize_handler_recovery`（probe-C）。
  parent `37fa7c21` 该分支逐字节相同（`git diff` 未触碰），缺陷 pre-existing；review-1 矩阵中
  "T3 / stable abort: pass" 因此未被 worker 路径证据支撑。
- **Unique test owner**：`vnext/backend/tests/test_submit_recovery.py`（integration + serial，§4
  "T3 commit before worker ack crash barrier" 行相邻），按业务行为命名（如
  `test_await_import_stable_abort_completes_via_worker_runtime`），断言：无异常、Attempt ABORTED、
  Operation/Step FAILED、submit_checkpoint_protection released。
- **Remediation allowed paths（S5；必要时 S2）**：
  `vnext/backend/src/gateway_backend/application/submit_jobs.py`（主：把 abort 收口迁入
  `lease_session.publish_operation` builder，与 `_make_finalize_success_builder` 同形）、
  `vnext/backend/src/gateway_backend/application/submission/abort_transaction.py`（S2，若需与
  `FinalizeSubmitTransactionRequest.defer_operation_terminal` 对等的 deferred-terminal 契约）、
  owner tests `vnext/backend/tests/test_submit_recovery.py` + `vnext/backend/tests/test_submit_transactions.py`。
  **不得**修改 `operations/**`、`application/recovery.py`；不得拆成"先 publish terminal、后独立
  abort 事务"两段（design §10.3 要求同一事务，且 design §11 只对 operator 路径接受该 crash 窗口）。
  operator 路径（`ABORT_CONFIRMED_FAILURE`，无 LeaseSession）不得因本 finding 改动语义。
- **Focused retest**：新 owner test（integration + serial）+ 现有
  `test_await_import_stable_abort_releases_checkpoint_protection`（直调 handler 形态保留）+
  `tests/test_submit_transactions.py` + accumulated unit 319 + `test_submit_recovery.py` 全文件。

## 6. New finding S7-F8 — closure record 的 revision/evidence 准确性（record-class）

- **Authority**：execution plan §7（handoff 必须记录 candidate/head 与各命令 exact 结果）、§S8 entry
  （"worktree candidate 内容完整且可追溯"）、§3 S7 remediation allowed-path 规则。
- **已核实问题**：
  1. `p5-5b-s7-independent-review-3.md` / `p5-5b-s7-acceptance.md` / `p5-5b-s7-remediation-handoff.md`
     均写 `remediation_commit: pending`；实际 seal 的候选是 `30193dd5`（本 review 的 target），
     closure record 未 pin 任何可复核 revision；
  2. acceptance `accumulated_submit_integration: pass_27` 与 HEAD 不可复现：同一 selection
     （`-m 'integration and not serial'`，三文件）在 HEAD 为 **26 passed / 8 deselected**；27 是
     baseline draft `4cda6b9c` 状态（含未标 serial 的 round-1 replay test、不含新的 serial owner）
     的数字；
  3. acceptance `s6_independent_review_round: 6` 与 lineage 引用的 `p5-5b-s6-independent-review-5.md`
     （仓库无 review-6）不一致；
  4. F1 remediation 修改了 `application/submission/finalize_transaction.py`（S2 changed path），
     但 review-1 为 F1 分配的 remediation paths 仅 `tests/test_submit_recovery.py` +
     `application/submit_jobs.py`；改动本身必要且未越出 S2 family（无 P4 改动，S2 owner
     `test_submit_transactions.py` 全绿），但 closure record 未按 finding 逐条列出实际 touched paths。
- **Business consequence**：S8/provenance 复核无法从 closure record 判定被接受的 revision 与证据
  provenance；历史上 review-2 的错误 closure 正是 revision/证据不实造成的。
- **Risk class**：D（record/handoff，无运行时代码影响）。
- **Remediation allowed paths**：`docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-*.md`（S7 默认
  allowed paths）。修正内容：pin `candidate_head`（本轮 remediation seal 后的 SHA）、按 finding 列出
  touched paths 与 owning stage、用当轮实测替换陈旧计数、更正 S6 round 引用。
- **Retest**：文档一致性与 `git diff --check`（S8 §6.5）。

## 7. Gate results（本 review 实跑，@ `30193dd5`，worktree clean）

| # | Gate | 命令 | 结果 |
| --- | --- | --- | --- |
| 1 | F1 focused integration+serial | `uv-consume.sh -C . run pytest -q -m 'integration and serial' tests/test_submit_recovery.py -k 'await_import and worker_runtime'` | **1 passed, 9 deselected** |
| 2 | finalize focused unit | `… -m unit tests/test_submit_finalize.py tests/test_submit_transactions.py -k finalize` | **3 passed, 33 deselected** |
| 3 | architecture unit | `… -m unit tests/test_architecture.py` | **45 passed** |
| 4 | accumulated unit（§4 22 unit files，319 期望） | `… -m unit <22 files>` | **319 passed** |
| 5 | integration non-serial（3 files） | `… -m 'integration and not serial' tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py` | **26 passed, 8 deselected**（声称的 27 不可复现，见 F8） |
| 6 | serial integration（4 files，含 worker_process） | `… -m 'integration and serial' <4 files>` | **11 passed, 26 deselected** |
| 7 | backend ruff | `.../uv-consume.sh -C . run ruff check .` | **All checks passed** |
| 8 | backend mypy | `.../uv-consume.sh -C . run mypy` | **Success: 377 source files** |
| 9 | F1 判别力（parent source shadow） | 见 §3 | **parent: 1 failed（unproven acknowledgment）；HEAD: pass** |
| 10 | S7-F7 只读探针 | 见 §5 | **复现 3 形态；control probe pass** |

F4/F6 结论由 gate 4 覆盖（owner files 在 selection 内）；F2 由 diff/文档核查，无运行 gate。

## 8. Non-blocking observations

- **S7-O1（carry）**：PRE_REQUEST 显式负例 cross-owner acceptable（无 open finding）。
- **S7-O2（carry）**：Repository restart submit journey 仍为 reopen candidate；workers poll-only
  设计不变，不阻塞 S7/S8 entry。
- **S7-O3（new）**：`FinalizeSubmitTransactionRequest.defer_operation_terminal` 默认（False）分支在
  生产已无 caller（仅 `test_submit_transactions.py` / `test_submit_finalize.py` unit 覆盖）；作为
  transaction-level 契约的 owner 保留可接受，但下一次触及该文件的 remediation 不得顺带重构，需
  单独 finding/记录。

## 9. Boundary confirmations

- 未触碰 `operations/**`、`application/recovery.py`、Repository packages（`git diff 37fa7c21..30193dd5`
  仅 backend 5 个文件 + docs）。
- 五包 static、`./vnext/scripts/run-tests.sh`、三镜像 current-HEAD container gate 保持 S8 defer；
  本 review 不据此判定容器/权威门禁。
- 本 review 不声明 `p5_5b_slice_exit`；`p5_5b_slice_exit=not_declared`。
- S7-F2 保持 `reclassified_deferred_to_s8`，S8 container gate（execution plan §6.4）通过前不得记 closed。

## 10. Next step

Finding-scoped remediation（S7-F7 必做；S7-F8 record 同步修正），随后由本 reviewer 复核 closure；
`S7-F7` 未关闭前 S8 entry 不成立。

```yaml
next_step: P5-5B-S7-remediation-round-3
s7_closeable: blocked_by [S7-F7, S7-F8]
s8_entry: blocked
```
