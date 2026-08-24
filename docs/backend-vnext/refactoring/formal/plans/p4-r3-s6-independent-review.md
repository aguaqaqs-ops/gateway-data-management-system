# P4/R3-S6 Independent Review

状态：**PASS — no open finding; S7 required and not authorized**

日期：2026-08-24

Reviewer：Operation Worker Runtime independent review

上游：[P4/R3-S4 Focused Review](p4-r3-s4-focused-review.md)、
[P4/R3-S5 Remediation Handoff](p4-r3-s5-handoff.md)、
[P4/R3-S5 Remediation Appendix](p4-r3-s5-remediation-appendix.md)、
[P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)、
[P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)

```yaml
step_id: P4-R3-S6
input_handoff_sha: 4c9a29454043fb0fb8d2c0754560a0a2d341883a10fb99949192ccc976e1d038
input_review_sha: c5882effa7990bf64668782edfb00d86f9de390573273f5fa179aa014ce991fa
input_remediation_appendix_sha: 40bfe239a70018fbe74ab48abbfed85ae7c68d3a636f347ccbde8d619f9e7aac
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
reviewed_head: edb15144ac5eae54e970c28f12f58e5e45b075a9
candidate_code_sha: pending_explicit_commit_authorization
candidate_worktree: uncommitted_r3_candidate_plus_s6_reusable_probes
entry_source_test_tree: sha256:35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a
validated_source_tree: sha256:26994ad239969afb95556c03d9f03590837a98ac3148f3a9d70d835241370146
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
result: pass
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s6-independent-review.md
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_operation_worker_process.py
focused_tests: pass_100
backend_unit: pass_1393_deselected_34
integration: pass_2_non_serial
serial: pass_8
five_package_static: pass
container_rebuild_required: yes
container_reason: S3b entrypoint/settings/signal/startup/shutdown boundary remains in the final candidate
last_verified_image_revision: none_for_r3_candidate
container_gate: deferred_to_s7_current_head
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - Current candidate source/tests and S6 record require an explicitly authorized commit before S7 entry.
  - S7 must rebuild and smoke the current committed candidate image; no R3 image result exists yet.
  - R4 registry/payload policy, R5 recovery/takeover and P5 deployment/global readiness remain out of scope.
reopen_conditions:
  - Any later change invalidates the recorded source/test identity or reopens an S4 finding.
  - Any reusable R4 executor cannot cooperate with cancel, lease-loss or drain before an irreversible effect.
  - Any fix requires R1 state, R2 schema/store/CAS/error, force-kill/detach, IPC or global readiness changes.
next_step: P4-R3-S7
next_step_authorized: no
s7_entry_status: blocked_pending_commit_authorization_and_current_head_image_gate
```

## 1. Independent decision

S6 passes. The eight required bounded counterexamples all fail closed at the frozen R3 boundaries.
No P1/P2, contract ambiguity, fencing, shutdown or new container-trigger finding remains open, and no
production source was changed during this review.

The candidate was independently reconstructed from the current source/tests rather than accepted from
the S4 conclusion. At entry, the combined Python source/test identity was exactly the S5 handoff value
`35992e...4d9a`. The only S6 code delta is reusable evidence in the two test paths explicitly allowed
by the S6 plan: a real SQLite multi-heartbeat publication probe, a cancellation reset assertion, both
sides of the process checkpoint commit barrier, and a persisted secret-bearing failure-log probe. The
post-probe source/test identity is `26994a...0146`.

The repository HEAD remains `edb1514`; the R3 candidate is still uncommitted because this step did not
receive commit authorization. Content hashes identify the reviewed bytes, but they are not represented
as a committed code SHA. S7 therefore remains unauthorized and its entry remains blocked until the
final source/tests and this review record are explicitly committed. S7 must then build the current-HEAD
image; prior steps supplied no current-candidate image evidence.

## 2. Required bounded probe matrix

| Probe | Result | Independent evidence |
| --- | --- | --- |
| Unknown first candidate leaves no `RUNNING` fact | **pass** | After an empty startup reached READY, an unknown first candidate was inserted. Claim preflight rejected it before token generation, rolled back the write UoW, and preserved the exact QUEUED/PENDING snapshots. |
| Publication does not reuse the claim version after heartbeats | **pass** | A real SQLite lease received two heartbeats, then a checkpoint and terminal Operation publication. Step versions advanced from claimed `v` to `v+1`, `v+2`, `v+3`, and `v+4`; the session reloaded each transaction-fresh version and closed after terminal commit. |
| Independent cancellation is visible before the effect boundary and cannot clear | **pass** | A separate file-backed connection committed Operation/Step cancellation while `LeaseSession.refresh_control()` waited. The control signal latched true, durable flags read back true, and a checkpoint builder attempting `true -> false` rolled back under the R1 monotonic guard. |
| Busy expiry and stale writer fence publication and new claim | **pass** | Heartbeat busy retry exhausted only the remaining lease budget, emitted `lease_lost`, joined the cooperative executor and raised worker-fatal instead of returning to claim. Expired, replaced-worker and mismatched-owner sessions latched lease loss, closed, and rejected the next mutation without opening another UoW. |
| Process termination on both sides of checkpoint commit | **pass** | A real subprocess was stopped at explicit pre-commit and post-commit barriers. Both retained the authoritative RUNNING/expired lease; the pre-commit Step remained at claim version 1 and the post-commit Step was atomically visible at version 2. No partial checkpoint mutation appeared. |
| Fake timeout keeps heartbeat supervision and does not detach or kill | **pass** | A deterministic timeout probe entered `DRAINING_TIMEOUT`, then observed a successful heartbeat before executor completion. The runtime joined the non-daemon executor, emitted no `worker_exited`, performed no detach/kill, and retained fatal timeout exit. |
| Recovery-created unknown successor is rejected by the second gate | **pass** | The recovery hook introduced a new active unknown JobStepKey after the first scan. The repeated topology/registry gate returned FATAL, emitted only `startup_failed`, and never enabled claim. Existing corruption/higher-schema process probes also remained non-zero. |
| Failure logs redact token, path, payload and SQL and exit non-zero | **pass** | A real module process opened a file-backed DB containing payload sentinels for a lease token, absolute DB path and SQL text. Missing-handler startup failed non-zero; output contained only bounded failure categories and none of the sentinels. Corrupt and higher-schema shapes retained the same redacted non-zero behavior. |

The probe command selected the exact owners above and completed as `12 passed`. A separate deterministic
timeout-after-heartbeat command printed:

```text
PASS timeout remained fatal; heartbeat followed timeout; executor joined without detach/kill
```

No exhaustive SQL permutation or thread-schedule matrix was introduced. The added file-backed and
subprocess probes are owned by the existing integration/serial suites, and the two crash phases share
one parameterized process harness.

## 3. Verification record

Commands were run against the post-probe candidate:

```text
cd vnext/backend
uv run pytest -q <twelve exact S6 counterexample cases>
  -> 12 passed

uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py \
  tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py \
  tests/test_architecture.py
  -> 100 passed

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 2 passed, 8 deselected

uv run pytest -q -m serial \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 8 passed, 2 deselected

uv run pytest -q -m unit
  -> 1393 passed, 34 deselected, 1 pre-existing Starlette deprecation warning

uv run ruff check . && uv run mypy
  -> backend pass; mypy 217 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files

git diff --check
  -> pass
git merge-base --is-ancestor 31235dc820472a5ca2c99138fdf150090cfe122d HEAD
  -> pass
```

The warning is the same pre-existing FastAPI/Starlette test-client warning recorded by S4/S5. R3 does
not require Dolt, Repository Service integration, a benchmark, or an S6 image build. The image gate is
not waived: S7 owns the mandatory rebuild and worker container smoke for the final committed candidate.

## 4. Findings, deferrals and next boundary

There are no S6 findings and no S5 return is required. S4 findings F1-F7 remain closed on the reviewed
bytes. S6 introduced no durable evidence, IPC, recovery policy, deployment wiring, packaging change,
second executor, force escalation, R1/R2 semantic change or additional container boundary.

The next workflow step is P4-R3-S7, but this record does not authorize it or any commit. Before S7 can
start, the final source/test candidate and S6 documentation must be committed under explicit user
authorization with no unrecorded in-scope drift. S7 must validate that committed current HEAD, rebuild
the backend image, run the module worker container smoke, and produce the final R3 handoff. R4, R5 and
P5 implementation remain unauthorized.
