# P5-5B-S7 Independent Review 2 — Remediation Closure

状态：**SUPERSEDED — rejected; see [p5-5b-s7-independent-review-3.md](p5-5b-s7-independent-review-3.md)**

日期：2026-09-17

Owner：Independent reviewer（closure）

> 本文件记录首轮 remediation 的错误 closure（handler 直调假阳性、architecture 过宽、compose smoke 无效）。Round 2 remediation 见 review-3。

## Decision

```yaml
stage: P5-5B-S7-remediation-closure
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
remediation_worktree: uncommitted (see p5-5b-s7-remediation-handoff.md)
decision: pass
findings_open: []
findings_closed: [S7-F1, S7-F2, S7-F4, S7-F6]
s8_entry: eligible
```

## Closure verification

| Finding | Closure evidence |
| --- | --- |
| S7-F6 | Architecture unit owners pass; accumulated unit 319 passed |
| S7-F1 | `submit_jobs.py` pre-refresh idempotent path; `test_await_import_replay_after_finalize_commit_before_worker_ack` pass；修复前 `StaleWrite` 可复现 |
| S7-F4 | `test_operator_recovery_rejects_retry_on_external_step` → 409 `RECOVERY_CAPABILITY_CONFLICT` |
| S7-F2 | `test_compose_submit_accept_route_is_wired_for_unprepared_workspace` pass；完整 journey 显式 defer S8 |

## Matrix residual

- S7-O1 PRE_REQUEST：cross-owner acceptable（无 open finding）
- S7-O2 Repository restart：reopen candidate；不阻塞 S7/S8 entry

## Static

Backend ruff/mypy pass @ remediation worktree.五包 static defer S8.

```yaml
next_step: P5-5B-S8 final current-HEAD gate and slice handoff
implementation_authority_unchanged: true
```
