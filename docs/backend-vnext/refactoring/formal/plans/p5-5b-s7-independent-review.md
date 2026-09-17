# P5-5B-S7 Independent Functional Review

状态：**changes_required — 4 findings; 2 non-blocking observations**

日期：2026-09-17

Owner：Independent reviewer（read-only）

## 1. Review target

```yaml
stage: P5-5B-S7-independent-functional-acceptance
implementation_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
s5_independent_review: pass
s6_independent_review: pass
decision: changes_required
findings_open: [S7-F1, S7-F2, S7-F4, S7-F6]
findings_closed: []
observations_non_blocking: [S7-O1, S7-O2]
```

## 2. Accumulated gate results（@ `37fa7c21`）

| Gate | Result |
| --- | --- |
| Accumulated unit（§4 27 files） | **316 passed, 2 failed** — `test_architecture.py` worker/runtime boundary |
| Integration `not serial` | 26 passed |
| Serial subset | 13 passed, 2 skipped |
| High-risk probes（response-loss / abort / operator HTTP） | pass |
| Backend ruff/mypy | pass |

## 3. Review matrix summary

| 主题 | Verdict | Notes |
| --- | --- | --- |
| T1 / no-change / idempotency / CAS / pin | pass | `test_submit_transactions.py` + HTTP preflight |
| exact Repository wire | pass | recording + live effect owners |
| builder / ref types | pass | import builder + artifact boundary |
| payload / checkpoints | pass | closed decoder matrix |
| effect / reconcile / finalize | pass | cross-owner; finalize owner thin but covered |
| T3 / stable abort | pass | transactions + recovery |
| PRE_REQUEST / unknown-outcome | pass (cross-owner) | 见 S7-O1 |
| response-loss upload/import | pass | worker + effect owners |
| **T3 post-commit worker response loss** | **finding S7-F1** | design §11 无 dedicated handler replay nodeid |
| admin HTTP / bearer / CAS | pass | operator recovery + read HTTP |
| **P4 capability external+RETRY HTTP** | **finding S7-F4** | prepare+RESUME 已测；external+RETRY 未测 |
| crash / takeover / late writer | pass | worker + recovery |
| reauthorization | pass | read + operation HTTP |
| readiness / shutdown | pass | S6 owners + process serial |
| mechanism exclusions | **finding S7-F6** | architecture owners 未反映 S6 runtime 接线 |
| **Compose Accept→T3→read** | **finding S7-F2** | S6 defer 未闭合；环境 dolt checksum 阻塞 build |
| Repository restart submit journey | observation S7-O2 | poll-only 设计；非当前 blocker |

## 4. Open findings

### S7-F6 — Architecture boundary tests out of sync with S6 wiring

- **Authority**：execution plan §S6；`test_architecture.py` mechanism exclusions
- **Business consequence**：accumulated unit gate 失败；S8 无法信任 architecture 屏障
- **Risk class**：B
- **Production path**：`bootstrap/operation_worker.py` → `http/runtime.py`；`http/runtime.py` → `gateway_repository_client`
- **Owner test**：`test_architecture.py`
- **Remediation paths（S6）**：`vnext/backend/tests/test_architecture.py`
- **Retest**：accumulated unit architecture nodeids + full accumulated unit

### S7-F1 — Missing handler replay after T3 commit before worker ack

- **Authority**：design §11 `after_business_finalize_commit_before_worker_ack`
- **Business consequence**：worker 丢失 ack 后可能重复 finalize 或错误失败
- **Risk class**：A
- **Production path**：`submit_jobs.py::build_await_import_result_handler` lines 678–680
- **Owner test**：`test_submit_recovery.py`（§4 response-loss owner）
- **Remediation paths（S5）**：`tests/test_submit_recovery.py`；必要时 `application/submit_jobs.py`
- **Retest**：owner + integration smoke

### S7-F4 — Missing HTTP negative for RETRY on external step

- **Authority**：design §10 operator matrix；S0-F3
- **Business consequence**：错误 operator command 可能绕过 capability guard
- **Risk class**：B
- **Production path**：`http/orchestration/operator_recovery.py`
- **Owner test**：`test_operator_recovery_http.py`
- **Remediation paths（S4）**：`tests/test_operator_recovery_http.py`
- **Retest**：operator HTTP unit subset

### S7-F2 — Compose functional journey incomplete

- **Authority**：design §13；S6 handoff deferred
- **Business consequence**：三进程 wiring 未经 Accept→finalize 路径验证
- **Risk class**：B
- **Production path**：compose backend/worker/repository conjunction
- **Owner test**：`test_submit_compose_e2e.py`
- **Remediation paths（S6）**：`tests/test_submit_compose_e2e.py`；`vnext/deploy/**`（仅 fixture/env）
- **Retest**：serial compose e2e；repository build 不可用时显式 skip 并记录 reason
- **Environment note**：`repository-service` build 失败（dolt checksum mismatch @ probe）

## 5. Non-blocking observations

### S7-O1 — PRE_REQUEST explicit negative

Cross-owner acceptable：`test_prepared_attempt_operator_abort_retains_occupancy`；
`test_submit_import_prepared_without_prepare_checkpoint_stays_manual_recovery`；
`test_await_import_result_disallowed_failure_marks_manual_recovery`；`ALLOWED_ABORT_CODES` 生产守卫。

### S7-O2 — Repository restart

Design §11：worker poll-only；Repository Service 自有 restart tests。记为 reopen candidate，非 S7 blocker。

## 6. Next step

Finding-scoped remediation per execution plan §7；closure review after remediation.

```yaml
next_step: P5-5B-S7-remediation
s8_entry: blocked_pending_s7_pass
```
