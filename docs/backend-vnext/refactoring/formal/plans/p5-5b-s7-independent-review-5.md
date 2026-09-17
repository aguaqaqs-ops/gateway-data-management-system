# P5-5B-S7 Independent Review 5 — Round 3 Closure Verification

状态：**changes_required — S7-F7 确认 closed；S7-F8 仍未闭合（record sealing，仅剩 2 个机械项）**

日期：2026-09-17

Owner：Independent reviewer（read-only；本文件是唯一写入）

## 1. Review target

```yaml
stage: P5-5B-S7-remediation-closure-round-3
implementation_seal_verified: 7c511c4b8b59842b67d24083abf274ba620b2e7e   # 可达；code+test 内容 = 本次核验对象
records_head_at_review: b48ca5927d920f2227053658918d4953f646ec7a          # 其中 pin 不可解析，见 §3
worktree_uncommitted: 2 doc lines (p5-5b-s7-acceptance.md / p5-5b-s7-remediation-handoff.md)
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
diff_scope: git diff 30193dd5..7c511c4b
changed_paths_verified:
  - vnext/backend/src/gateway_backend/application/submission/abort_transaction.py
  - vnext/backend/src/gateway_backend/application/submit_jobs.py
  - vnext/backend/tests/test_submit_recovery.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s7-{acceptance,independent-review-3,remediation-handoff}.md
decision: changes_required
findings_closed: [S7-F1, S7-F4, S7-F6, S7-F7]
findings_reclassified: [S7-F2]
findings_open: [S7-F8]
observations_non_blocking: [S7-O1, S7-O2, S7-O3, S7-O4]
operations_package_untouched: true
s8_entry: blocked
p5_5b_slice_exit: not_declared
```

方法与 review-4 相同：先核 authority/changed paths，再逐 finding 复核 owner test；对 S7-F7 做
pre-fix 判别力复核与只读运行探针（§2.4）。未运行五包 static、权威 runner、镜像/Compose gate（属 S8）。

## 2. S7-F7 closure evidence

### 2.1 实现（@ 7c511c4b；与 review-4 指定的 S5/S2 allowed paths 一致）

- `submit_jobs.py:904-916`：stable abort 分支改为
  `lease_session.publish_operation(_make_stable_abort_builder(...))` 后 `return PUBLISHED`；
  独立 UoW + 裸 `PUBLISHED` 已删除。session 的 `publish_operation` 提交 fact 并设
  `_completion_acknowledgment=PUBLISHED`（`lease_session.py:244`），满足
  `worker_runtime.py::_validate_executor_outcome` 与 `recovery.py::finalize_handler_recovery`
  的 P4 协议要求。
- `submit_jobs.py:2263+` `_make_stable_abort_builder`：在 session UoW（`_active_submit_transaction`）
  内先 `validate_abort_proof`，再调 `abort_submit_in_control_transaction(... defer_operation_terminal=True)`
  完成 Attempt→ABORTED、Workspace/Occupancy/pin/checkpoint protection 处理，最后返回
  Step=FAILED / Operation=FAILED（diagnostic code=stable abort code、message="submit attempt aborted"、
  completed_at/updated_at=transaction_now、version+1）。与旧 `_fail_active_step_if_needed` /
  `_fail_operation_if_needed` 的终局字段逐项一致；**业务 abort 与 Step/Operation 收口仍在一个
  SQLite UoW**（design §10.3 要求保持）。
- `abort_transaction.py:46/76/137`：新增 `defer_operation_terminal`（默认 False）并把原私有
  `_abort_submit_in_transaction` 提升为 `abort_submit_in_control_transaction`；`abort_submit_transaction`
  （operator 路径，`submit_jobs.py:999` 调用）行为不变（仅内部函数改名，`defer` 取默认 False）：仍走
  read-only 预检 + `validate_abort_proof` + 自持 UoW + 非 defer 收口。
- 边界：本轮 diff 未触碰 `operations/**`、`application/recovery.py`、Repository packages；lease
  fencing 由 session 的 `_load_live_records` + `complete_operation` 前置条件承担（等价或更强于旧
  `WritePrecondition(worker_id=..., lease_token=...)`）。

### 2.2 Owner test

`tests/test_submit_recovery.py:584` `test_await_import_stable_abort_completes_via_worker_runtime`
（integration + serial，经 `WorkerRuntime._run_claim`），断言：无异常、Operation FAILED、
await Step FAILED、Attempt ABORTED、submit checkpoint protection released。命名按业务行为、
落在 review-4 指定的 owner file，无 round/finding 编号命名。

### 2.3 判别力（pre-fix 复核）

```bash
cd vnext/backend && PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/tmp/p5_5b_s7_probe/round2_src:. .venv/bin/python -m pytest -q \
  -p no:cacheprovider -o addopts='' tests/test_submit_recovery.py \
  -k 'stable_abort_completes_via_worker_runtime'
# 1 failed — ValueError: executor acknowledgment was not committed by LeaseSession
#            (round-2 src .../worker_runtime.py:383)
```

同一 nodeid 在 7c511c4b 通过（§4 gate 1）。测试确为失败-通过判别型，非恒真。

### 2.4 独立运行探针（review-4 所用的同一组，@ 7c511c4b worktree）

```text
[probe-A unrouted handler]    outcome: no-exception   db: (FAILED, FAILED, ABORTED)
[probe-B routed executor]     outcome: no-exception   db: (FAILED, FAILED, ABORTED)
[probe-C handler return]      PUBLISHED
[probe-C session ack]         PUBLISHED                ← review-4 时为 None
[probe-C recovery finalize]   acknowledgment: PUBLISHED
[control: finalize success]   outcome: no-exception   db: (SUCCEEDED, SUCCEEDED, FINALIZED)
```

probe-C 证明 recovery-routed 收口形态（`finalize_handler_recovery` 的
"PUBLISHED without committing session fact"）也已闭合。**S7-F7 closed。**

## 3. S7-F8 residual（记录未 sealed / pin 不可解析）

已修正并在 sealed revision 生效的部分：

- `remediation_commit: pending` → `remediation_round_2: 30193dd5...` + round-3 字段；
- `accumulated_submit_integration: pass_26`（实测 26 ✓，review-4 指出的陈旧 27 已改）；
- `s6_independent_review: pass (p5-5b-s6-independent-review-5.md)`（`_round: 6` 已移除）；
- review-3 已标 SUPERSEDED 并注明被 review-4 驳回；
- handoff 按 finding 分列 round-3 与 prior-round touched paths（与实际 diff 一致）。

仍未闭合的两项（均 record-only，无代码/测试影响）：

1. **pin 指向不可解析 revision**。HEAD `b48ca592` 的两份记录写
   `remediation_round_3: 5de2e0b7f958eb496e24af7f304aef23f245ad1f`，但该 commit
   `git branch -a --contains` 为空且非 HEAD 祖先（本轮 amend 产生的孤本；同批孤本还有
   `b60402dc`）——fresh clone 中该 SHA 无法解析，记录失去可追溯性。正确值 `7c511c4b`
   （可达）目前只存在于**工作区未提交**的 2 行修改中。`b48ca592` 的 commit message 声称
   "Point ... at 7c511c4b"，与其 diff 内容不符，任何 auditor 执行 `git show b48ca592`
   即可看到该矛盾。
2. **handoff 的 focused retest 注释陈旧**：`integration and not serial` 三文件行注
   "26 passed, 8 deselected"；实测 round-3 revision 为 **26 passed, 9 deselected**
   （新增 serial owner 后总数 35）。

closeout checklist（下一轮机械复核即可）：

```text
[ ] 提交工作区中已修正的 pin（acceptance + handoff 各 1 行，值 7c511c4b）
[ ] 确认被 pin 的 revision 从分支可达（7c511c4b 已满足）
[ ] 修正 handoff 陈旧计数（9 deselected；或删除 deselected 明细）
[ ] git status --short 干净 + git diff --check 通过（plan §6.5）
[ ] 可选：在记录中注明 amend 历史（b60402dc / 5de2e0b7 不是 branch revision）
```

说明：S8 allowed paths 不含 `p5-5b-s7-*.md`，该修正无法推迟到 S8；这正是本轮判定
`changes_required` 的原因（F8 的判据是"被接受的 revision 可追溯"，而 HEAD 上不可追溯）。

## 4. Gate results（本 review 实跑）

| # | Gate | 命令 | 结果 |
| --- | --- | --- | --- |
| 1 | WorkerRuntime serial（claim 原样命令） | `… -m 'integration and serial' tests/test_submit_recovery.py -k 'worker_runtime and (finalize or stable_abort)'` | **2 passed, 9 deselected** |
| 2 | abort unit | `… -m unit tests/test_submit_transactions.py -k abort` | **7 passed, 28 deselected** |
| 3 | accumulated unit（§4 22 unit files） | `… -m unit <22 files>` | **319 passed** |
| 4 | integration non-serial（3 files） | `… -m 'integration and not serial' tests/test_submit_job_effect.py tests/test_submit_recovery.py tests/test_submit_worker.py` | **26 passed, 9 deselected** |
| 5 | recovery 全文件 | `… tests/test_submit_recovery.py` | **11 passed** |
| 6 | serial integration（4 files，含 worker_process） | `… -m 'integration and serial' <4 files>` | **12 passed, 26 deselected** |
| 7 | effect stable abort（handoff 所列） | `… -m 'integration and not serial' tests/test_submit_job_effect.py -k stable_abort` | **1 passed, 15 deselected** |
| 8 | backend ruff / mypy | `… run ruff check .` / `… run mypy` | **All checks passed / 377 source files OK** |
| 9 | S7-F7 判别力 | 见 §2.3 | **round-2 src: 1 failed；7c511c4b: pass** |
| 10 | 只读探针 A/B/C + control | 见 §2.4 | **全部按预期** |

## 5. Verdict rationale

S7-F7（唯一 blocker-class finding）已在实现、owner test、判别力与运行证据四个层面闭合；S7-F1/F4/F6
延续 review-4 的 closed；S7-F2 保持 `reclassified_deferred_to_s8`。剩余未闭合项只有 S7-F8 的
record sealing（2 个机械修正）。因 HEAD 上被 pin 的 revision 不可解析、且修正仅存在于未提交工作区，
按 plan §7/§S8 entry（"candidate 内容完整且可追溯"）不能给出 pass。本轮**不**声明 S7 accept、
**不**声明 `p5_5b_slice_exit`。

## 6. Non-blocking observations

- **S7-O1 / S7-O2（carry）**：PRE_REQUEST cross-owner acceptable；Repository restart journey 仍为
  reopen candidate，不阻塞 S7/S8 entry。
- **S7-O3（carry）**：`FinalizeSubmitTransactionRequest.defer_operation_terminal` 默认分支在生产
  仍无 caller（仅 unit 覆盖）；不得在无关 remediation 中顺带重构。
- **S7-O4（new）**：`abort_submit_in_control_transaction` 为模块级公开名但未进入
  `application/submission/__init__.py` 的 `__all__`；当前只有 `submit_jobs.py` 与包内调用，
  可接受；若未来跨包消费需补导出。

## 7. Boundary confirmations

- 本轮 diff 未触碰 `operations/**`、`application/recovery.py`、Repository packages；operator abort
  语义与默认（非 defer）收口路径不变。
- 五包 static、`./vnext/scripts/run-tests.sh`、三镜像 current-HEAD container gate 保持 S8 defer；
  S7-F2 在 S8 §6.4 通过前不得记 closed。
- 本 review 未改代码/既有文档；唯一写入为本文件。

## 8. Next step

完成 §3 checklist（仅文档提交）后由本 reviewer 做机械复核（pin 可达性 + 计数 + clean status），
随即形成 S7 acceptance 并放行 S8。

```yaml
next_step: P5-5B-S7-F8-record-sealing
s7_closeable: blocked_by [S7-F8]
s8_entry: blocked
```
