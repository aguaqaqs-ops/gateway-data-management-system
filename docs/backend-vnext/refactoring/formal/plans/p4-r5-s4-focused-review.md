# P4-R5-S4 Focused Review

状态：**PASS AFTER FINDING-SCOPED REMEDIATION**

日期：2026-08-26

Reviewer：Independent focused reviewer

```yaml
step_id: P4-R5-S4
context: mandatory_new_conversation
reviewed_head: 9beea4572b5896f2e7268b1c38aa20e54c4ea1a3
reviewed_candidate: documented_dirty_worktree
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: sha256:6110bdd52f877489925ad3e8ad2dced856002a045b8ed074421335d48140ed28
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
result: pass
container_rebuild_required: yes
container_reason: candidate touches worker startup/runtime recovery boundary; current HEAD must be rebuilt in S7
container_gate: deferred_to_S7
next_step: P4-R5-S6
next_step_authorized: no
```

本次 rereview 读取了完整 R5 source/test/diff、R5 design/plan、Active Context、R4 handoff 和
S1a-S3c 全部 handoff。候选仍是未提交 dirty worktree；所有上游 handoff 的
`validated_code_sha` 仍为 `pending_explicit_commit_authorization`。本次 review 未修改
production、依赖或部署文件。

## Findings

| Finding | Owner | Severity | Status |
| --- | --- | --- | --- |
| R5 recovery is not composed into the real worker startup | Bootstrap + R5 Operation Runtime | P1 | closed |
| Normal external-effect submit path accepts an unverified operation identity | Application Recovery / synthetic external-effect owner | P1 | closed |
| Pure-compute recovery recreates a missing output artifact | Application Recovery / artifact checkpoint owner | P2 | closed |
| Post-request reconcile can omit or escape the 60-second budget | Application Recovery / effect reconcile owner | P2 | closed |
| Reconcile silently treats a non-polling or wrapped stub as confirmed | Application Recovery / effect reconcile owner | P1 | closed |
| An initial unknown external outcome is terminalized before R5 reconcile | Application Recovery / synthetic external-effect owner | P2 | closed |

### R5 recovery is not composed into the real worker startup

**Owner:** `bootstrap.operation_worker` + R5 Operation Runtime  
**Severity:** P1  
**Regression:** `test_registered_runtime_startup_recovers_expired_running_step` and
`test_process_startup_takeover_moves_expired_running_to_retry_wait` exercise expired `RUNNING`
recovery; focused result `225 passed`, process result `7 passed`.  
**Closure:** [operation_worker.py:150](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/bootstrap/operation_worker.py:150)
now composes `build_startup_recovery()` into the concrete runtime, and
[worker_startup.py:323](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/operations/worker_startup.py:323)
selects it before claim. The regression observes guarded CAS to `RETRY_WAIT` and a retryable startup
disposition. **Reopen** if startup bypasses this composition, loses lease/version fencing, or
requires an R1/R2 schema/CAS/status/error-taxonomy change.

### Normal external-effect submit path accepts an unverified operation identity

**Owner:** Application Recovery / synthetic external-effect owner  
**Severity:** P1  
**Regression:** `test_normal_submit_identity_mismatch_fails_closed_without_ready` injects a wrong
identity into the normal handler submit path and asserts `MANUAL_RECOVERY`, no READY, no response
artifact, and no checkpoint publication.  
**Closure:** [synthetic_jobs.py:462](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:462)
computes and checks `compute_operation_identity()` before checkpoint/terminal publication, mapping a
mismatch to bounded manual recovery. **Reopen** if any normal submit path publishes READY without
the same check, or remediation widens Repository/R1/R2 contracts.

### Pure-compute recovery recreates a missing output artifact

**Owner:** Application Recovery / artifact checkpoint owner  
**Severity:** P2  
**Regression:**
`test_pure_compute_recovery_missing_output_enters_manual_without_recreation` (at
[test_operation_job_recovery.py:1441](/root/gateway-data-management-system/vnext/backend/tests/test_operation_job_recovery.py:1441))
removes the checkpointed output and asserts `MANUAL_RECOVERY`, no `put`, no READY closure, and
unchanged artifact occupancy.  
**Closure:** [synthetic_jobs.py:1111](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:1111)
constructs the existing reference and verifies it with `locate()`; unreadable/missing bytes fail
closed without recreation. **Reopen** if recovery writes replacement output bytes or changes R4
artifact authority.

### Post-request reconcile can omit or escape the 60-second budget

**Owner:** Application Recovery / effect reconcile owner  
**Severity:** P2  
**Regression:** `test_recovery_port_invalid_timestamp_fails_closed_without_poll` routes missing,
empty, malformed, naive and non-UTC timestamps through the recovery port and asserts
`MANUAL_RECOVERY` with no poll; `test_external_effect_recovery_port_reconcile_budget_exhausted`
covers the elapsed-time boundary.  
**Closure:** [recovery.py:177](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/recovery.py:177)
requires a strict UTC timestamp, and [synthetic_jobs.py:634](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:634)
fail-closes invalid/missing checkpoint data before polling and enforces the 60-second budget.
**Reopen** if any such form can poll, loop unboundedly, or escape as an uncaught checkpoint error;
schema migration outside the existing checkpoint contract is also a reopen.

### Reconcile silently treats a non-polling or wrapped stub as confirmed

**Owner:** Application Recovery / effect reconcile owner  
**Severity:** P1  
**Regression:** `test_recovery_port_non_polling_stub_fails_closed_without_confirmed_fallback` uses a
submit-only stub and asserts no implicit `CONFIRMED`, no READY closure, and no artifact mutation;
polling-wrapper tests continue to assert original-identity polling.  
**Closure:** [synthetic_jobs.py:785](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:785)
returns no adapter for a non-polling stub and delegates explicit `poll()` implementations with a
`None` default, while [synthetic_jobs.py:814](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:814)
maps pending/unknown outcomes to bounded pending/manual recovery. **Reopen** if a wrapper restores an
implicit `CONFIRMED` fallback, polls a new identity, or requires real Repository protocol wiring
before its owning boundary is authorized.

### An initial unknown external outcome is terminalized before R5 reconcile

**Owner:** Application Recovery / synthetic external-effect owner  
**Severity:** P2  
**Regression:** `test_stub_terminal_outcomes` and
`test_accepted_handler_then_recovery_polls_without_resubmit` preserve the checkpoint and return
`SAFE_HANDOFF`/`RECONCILE_PENDING`; a later poll confirms without a second submit. The unknown-poll
case remains separately covered as manual/no-false-READY.  
**Closure:** [synthetic_jobs.py:511](/root/gateway-data-management-system/vnext/backend/src/gateway_backend/application/synthetic_jobs.py:511)
now retains the durable checkpoint and safe handoff for initial `UNKNOWN`, leaving terminalization to
bounded R5 reconcile policy. **Reopen** if initial unknown clears the checkpoint/lease before reconcile,
blindly resubmits, or changes the existing R4 handler status contract.

## Verification

```text
user-reported focused/process: 94 passed
independent synthetic/reconcile focused: 41 passed
process tests (worker process + recovery process): 7 passed
backend unit: 1614 passed, 104 deselected, 1 pre-existing Starlette deprecation warning
backend ruff: pass
backend mypy: pass (235 source files)
git diff --check: pass
```

All six findings are closed for this focused review; conditional S5 remediation is not required.
S6 remains the next named review but is not authorized. S7 remains the
required current-HEAD image rebuild and container gate because this candidate changes the worker
startup/runtime recovery boundary; no container result is claimed here.
