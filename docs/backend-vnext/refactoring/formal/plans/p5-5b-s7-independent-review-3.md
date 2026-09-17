# P5-5B-S7 Independent Review 3 — Remediation Closure (Round 2)

状态：**SUPERSEDED — rejected @ review-4; see [p5-5b-s7-independent-review-4.md](p5-5b-s7-independent-review-4.md)**

日期：2026-09-18

Owner：Independent reviewer（closure）

> 本文件错误声明 pass / s8_entry eligible；review-4 打开 S7-F7/F8。Round 3 remediation 见 handoff round 3。

## Decision

```yaml
stage: P5-5B-S7-remediation-closure-round-2
parent_candidate: 37fa7c21ca261e5e89d15515f629106556ee43de
baseline_commit: 4cda6b9c
remediation_commit: pending
supersedes: p5-5b-s7-independent-review-2.md
decision: pass
findings_open: []
findings_closed: [S7-F1, S7-F4, S7-F6]
findings_reclassified: [S7-F2]
s8_entry: eligible
```

## Closure verification

| Finding | Status | Closure evidence |
| --- | --- | --- |
| S7-F1 | closed | `finalize_submit_transaction(..., defer_operation_terminal=True)` + `lease_session.publish_operation(_make_finalize_success_builder(...))`；`test_await_import_finalize_commits_lease_acknowledgment_via_worker_runtime`（integration + serial，经 `WorkerRuntime._run_claim`） |
| S7-F4 | closed | `test_operator_recovery_rejects_retry_on_external_step`（baseline 保留） |
| S7-F6 | closed | `test_repository_client_is_confined_to_repository_read_and_write` 精确 allow `http/runtime.py`；accumulated unit 319 passed |
| S7-F2 | reclassified_deferred_to_s8 | 删除无效 compose smoke；完整 Accept→upload→import→poll→T3→read 属 S8 container gate（execution plan §6.4） |

## Focused retest

```bash
cd vnext/backend

../scripts/uv-consume.sh -C . run pytest -q -m 'integration and serial' \
  tests/test_submit_recovery.py -k 'await_import and worker_runtime'
# 1 passed

../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_finalize.py tests/test_submit_transactions.py -k finalize
# 3 passed

../scripts/uv-consume.sh -C . run pytest -q -m unit tests/test_architecture.py
# architecture owners pass; accumulated unit 319 passed

../scripts/uv-consume.sh -C . run ruff check .
../scripts/uv-consume.sh -C . run mypy
# pass
```

## Matrix residual

- S7-O1 PRE_REQUEST：cross-owner acceptable（无 open finding）
- S7-O2 Repository restart：reopen candidate；不阻塞 S7/S8 entry

```yaml
next_step: P5-5B-S8 final current-HEAD gate and slice handoff
implementation_authority_unchanged: true
p5_5b_slice_exit: not_declared
```
