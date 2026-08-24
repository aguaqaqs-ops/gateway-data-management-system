# P4/R3-S4 Focused Review

状态：**PASS AFTER S5 FOCUSED REREVIEW — S6 REQUIRED AND NOT AUTHORIZED**

日期：2026-08-24

Reviewer：Operation Worker Runtime focused review

上游：[P4/R3-S3b Handoff](p4-r3-s3b-handoff.md)、
[P4-R3 Worker and Process Lifecycle Detailed Execution Plan](p4-r3-worker-lifecycle-execution-plan.md)、
[P4-R3-S0 Entry Brief](p4-r3-s0-entry-brief.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[ADR 0016](../adr/0016-graceful-lifecycle-and-integrity-recovery.md)

```yaml
step_id: P4-R3-S4
input_handoff_sha: 6d9bbcd520ca628076e85ac0d85bd9602d9f4519ab2463314c7aa41fe7678599
input_validated_code_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
reviewed_head: edb15144ac5eae54e970c28f12f58e5e45b075a9
reviewed_candidate_sha: uncommitted_worktree_candidate
validated_source_tree: sha256:cf411aa52974d103cf5bb1d38eee87f550e2d0ed9da9fda14df3ebfd5e91a849
candidate_worktree_at_entry: tracked_and_untracked_r3_candidate_changes
initial_result: rework_required
result: pass_after_s5_focused_rereview
s5_appendix_sha: 40bfe239a70018fbe74ab48abbfed85ae7c68d3a636f347ccbde8d619f9e7aac
s5_handoff_sha: 4c9a29454043fb0fb8d2c0754560a0a2d341883a10fb99949192ccc976e1d038
s5_validated_source_tree: sha256:35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r3-s4-focused-review.md
initial_commands_and_results:
  - "source/test tree identity recomputation -> cf411aa...e91a849; matches S3b handoff"
  - "git merge-base --is-ancestor 31235dc... HEAD -> pass"
  - "focused unit gate -> 94 passed"
  - "integration and not serial gate -> 1 passed, 6 deselected"
  - "serial gate -> 6 passed, 1 deselected"
  - "backend unit gate -> 1387 passed, 31 deselected, 1 pre-existing Starlette warning"
  - "five Python packages: uv run ruff check . && uv run mypy -> pass"
  - "bounded startup/checkpoint counterexamples -> reproduced F2 and F5"
  - "authoritative module CLI probe -> functional drain plus RuntimeWarning; reproduced F6"
rereview_commands_and_results:
  - "S5 appendix/handoff content hashes and finding-scoped path review -> pass"
  - "focused unit gate -> 100 passed"
  - "integration and not serial gate -> 1 passed, 6 deselected"
  - "serial gate -> 6 passed, 1 deselected"
  - "backend unit gate -> 1393 passed, 31 deselected, 1 pre-existing Starlette warning"
  - "five Python packages: uv run ruff check . && uv run mypy -> pass"
  - "independent 31-second slow-claim counterexample -> fenced before thread start"
  - "authoritative module CLI probe -> clean ready/drain/exit; no RuntimeWarning or runpy output"
initial_focused_tests: pass_94_but_not_review_closure
initial_backend_unit: pass_1387_deselected_31
rereview_focused_tests: pass_100
rereview_backend_unit: pass_1393_deselected_31
rereview_integration: pass_1_non_serial
rereview_serial: pass_6
rereview_five_package_static: pass
focused_tests: pass_100
backend_unit: pass_1393_deselected_31
integration: pass_1_non_serial
serial: pass_6
five_package_static: pass
container_rebuild_required: yes
container_reason: S3b changed module entrypoint, settings, signal, startup and shutdown process boundaries
last_verified_image_revision: none_for_r3_candidate
container_gate: deferred_to_s7_final_candidate
benchmark: not_applicable_no_performance_claim
initial_findings:
  - P4-R3-S4-F1: P2 heartbeat lease budget is anchored after work that consumes the durable lease
  - P4-R3-S4-F2: P2 checkpoint publication can replace the fixed lease expiry with an arbitrary future value
  - P4-R3-S4-F3: P2 active drain before the first heartbeat enters a CPU busy loop
  - P4-R3-S4-F4: P2 DRAINING_TIMEOUT can return from runtime and exit the process with status zero
  - P4-R3-S4-F5: P2 one startup gate may exceed the 60-second budget and still publish READY
  - P4-R3-S4-F6: P3 authoritative module CLI is pre-imported and emits a runpy RuntimeWarning
  - P4-R3-S4-F7: P3 step handoff lineage and recorded test evidence are inconsistent
initial_deferred_items:
  - No production or test finding is remediated by this documentation-only review.
  - Current-HEAD image rebuild and worker container smoke remain owned by S7 after review closure.
  - R4 registry/payload/publication policy, R5 recovery/takeover and P5 deployment/global readiness remain out of scope.
reopen_conditions:
  - Any fix requires changing R1 state, R2 schema/store/CAS/error semantics or the fixed 30/10-second lease profile.
  - Any fix requires killing/detaching a thread, adding a second executor, durable worker evidence, IPC or global readiness.
  - The representative R4 executor cannot cooperate with lease-loss, cancellation or drain under the frozen timing profile.
open_findings: []
closed_findings:
  - P4-R3-S4-F1
  - P4-R3-S4-F2
  - P4-R3-S4-F3
  - P4-R3-S4-F4
  - P4-R3-S4-F5
  - P4-R3-S4-F6
  - P4-R3-S4-F7
next_step: P4-R3-S6
next_step_authorized: no
s6: required_not_authorized
s7: blocked
```

## 1. Review decision

The candidate preserves the intended package direction: Operations remains SQLite-neutral, bootstrap
owns concrete control-DB/settings/signal composition, the root Operations export surface is unchanged,
and no R4 payload/policy, R5 recovery decision, Repository effect, HTTP readiness, Compose, IPC or
durable worker evidence entered R3. Atomic registry preflight and claim are in one write UoW and the
unknown-key path mutates nothing. Startup performs the required integrity/topology/registry gate on
both sides of the out-of-transaction recovery hook. LeaseSession reloads records in fresh UoWs and
uses only the existing R2 actions.

R3 nevertheless cannot pass focused review. The runtime overstates the remaining durable lease,
allows checkpoint builders to replace its fixed expiry, and mishandles active drain before the first
heartbeat. A drain timeout can then be reported as a successful process exit. Separately, the startup
budget does not cover an individual slow gate, so READY can be published after the accepted deadline.
These are the stale-writer, bounded-wait and unsafe-drain classes that the S4 plan explicitly makes
blocking. S5 must begin with a finding-scoped remediation appendix; this record authorizes no source or
test change.

## 2. Finding and disposition table

| Finding | Severity | Owner | Disposition required before S6 |
| --- | --- | --- | --- |
| P4-R3-S4-F1 | P2 | `operations.worker_runtime` lease supervision | Rework in S5; prove conservative monotonic budget across claim, heartbeat transaction and observer latency. |
| P4-R3-S4-F2 | P2 | `operations.lease_session` lease-field ownership | Rework in S5; prevent checkpoint policy from selecting an expiry outside the fixed R3 lease rule. |
| P4-R3-S4-F3 | P2 | `operations.worker_runtime` active drain loop | Rework in S5; latch the local pending-drain branch immediately and prove no spin/no new claim. |
| P4-R3-S4-F4 | P2 | lifecycle/runtime/bootstrap exit boundary | Rework in S5; timeout must never be converted to clean exit 0 or `worker_exited`. |
| P4-R3-S4-F5 | P2 | bootstrap startup-budget composition | Rework in S5; no gate may publish/return READY after the 60-second deadline. |
| P4-R3-S4-F6 | P3 | `bootstrap` package/module CLI | Rework in S5; remove eager entrypoint import and assert warning-free `python -m` startup. |
| P4-R3-S4-F7 | P3 | R3 step evidence/provenance | Correct in the S5 appendix/handoff and use current rerun evidence; do not rewrite historical code claims silently. |

### P4-R3-S4-F1 — P2: heartbeat lease budget starts too late

`WorkerRuntime._run_claim` samples `initial_now` only after claim commit, `refresh_control`, lifecycle
bookkeeping, thread construction and `thread.start`, then grants a new full `lease_duration` monotonic
budget. After heartbeat it again samples monotonic time only after the fresh UoW, commit and observer
return, and grants another full duration. None of these elapsed intervals extends the durable
`lease_expires_at`.

A slow observer, thread factory or heartbeat return path can therefore leave less than 30 seconds in
SQLite while lines 250–275 of `worker_runtime.py` supervise as if 30 seconds remained. `StoreBusy`
retry at lines 321–342 may cross the real expiry before setting `lease_lost`. SQL live-lease checks
still reject a later publication once a transaction is acquired, but that does not satisfy the R3
requirement to fence on the current remaining lease budget or promptly notify an executor before an
effect boundary.

S5 must use a conservative monotonic anchor taken no later than the operation that establishes or
renews the durable lease. The regression should inject elapsed time in claim/session/observer paths
and prove that retry never uses that elapsed time as additional lease capacity. It must not add a
second durable clock or change R2's wall-clock lease owner.

### P4-R3-S4-F2 — P2: checkpoint builder can replace fixed lease expiry

`LeaseSession._validate_checkpoint_candidate` checks only that the candidate expiry is non-null and
later than `transaction_now`. It does not preserve the current expiry or enforce the fixed
`transaction_now + 30s` lease rule. A bounded fake-UoW probe submitted an otherwise valid checkpoint
with `lease_expires_at = transaction_now + 365 days`; the UoW committed and returned a checkpoint
generation.

Lease duration and fencing belong to R2/R3, not future R4 checkpoint policy. S5 must make the accepted
checkpoint shape explicit and enforce it before calling the R2 action. A regression should reject an
arbitrary extension and prove that heartbeat/checkpoint serialization still uses transaction-fresh
versions. This is an in-boundary validation change; needing a new R1 field, R2 action or configurable
duration triggers reopen.

### P4-R3-S4-F3 — P2: active drain before first heartbeat spins

When `_wait_interruptibly` observes drain at lines 289–290, the lifecycle and `ExecutionControl` are
updated but the loop-local `pending_drain` remains false. On the next iteration the same branch calls
`_wait_interruptibly` again; because `drain_requested()` is already true, it returns immediately
without waiting. With an active executor and a not-yet-due heartbeat, the main thread repeats this
path until monotonic time reaches `next_heartbeat`, producing a CPU busy loop for up to the ten-second
heartbeat interval. The drain deadline is also omitted from the wait calculation while the stale
local flag remains false.

S5 must latch the local drain branch at the first observation and use the executor-completion wait
while heartbeat supervision continues. The authoritative regression should request drain immediately
after thread start, keep the executor active and the fake clock fixed, and prove a bounded wait rather
than repeated polling. No second thread, force signal or cancellation write is needed.

### P4-R3-S4-F4 — P2: drain timeout is reported as exit zero

After an active executor eventually acknowledges, `mark_executor_completed` deliberately leaves the
lifecycle in `DRAINING_TIMEOUT`. `WorkerRuntime.run` then returns normally at lines 193–199. The same
normal return is also used by the pre-claim timeout branch at lines 170–173. Bootstrap `run` returns
zero after every normal runtime return at lines 124–145 and never checks that the lifecycle reached
`EXITED`.

The result contradicts both the method promise "zero only after a clean local drain" and the frozen
exit contract: timeout is not `QUIESCED -> STOPPING -> EXITED`, and no `worker_exited` fact is emitted.
S5 must surface timeout as a bounded worker-fatal result/non-zero exit while retaining the accepted
no-kill, no-detach and continued-heartbeat behavior until the non-daemon executor cooperates or an
administrator terminates the process. Unit ownership should cover runtime state/result; bootstrap
ownership should prove the exit mapping without waiting 180 real seconds.

### P4-R3-S4-F5 — P2: startup budget does not cover a slow gate

`_StartupBudget.startup` checks its deadline only before delegating and returns the delegate result
without a postcondition. A bounded fake-clock probe entered at zero, advanced to 61 seconds inside the
delegate and returned `READY`; the wrapper returned `READY` and emitted no timeout event. With the real
delegate, `worker_ready` is emitted inside `WorkerStartup.startup` before the wrapper regains control,
so adding only a post-return check would still publish a false readiness event.

S5 must ensure the complete gate attempt and readiness event respect the 60-second budget, while
retaining complete scans and out-of-transaction recovery. The test should own the overall deadline,
retry interruption and exactly-one bounded failure event; it need not enumerate SQLite schedules. If
a complete active-set scan cannot meet the deployment objective, the plan's capacity reopen condition
applies instead of truncating or sampling the scan.

### P4-R3-S4-F6 — P3: `python -m` eagerly pre-imports its target

`gateway_backend.bootstrap.__init__` imports and re-exports `operation_worker` at package import time.
The authoritative `python -m gateway_backend.bootstrap.operation_worker` flow therefore finds the
target already in `sys.modules`, emits a `runpy` RuntimeWarning that execution may be unpredictable,
and executes a second module instance as `__main__`. A temporary empty-DB CLI probe reproduced the
warning before `worker_ready`; SIGTERM still drained and emitted `worker_exited`.

S5 should keep the package initializer side-effect free (or use a non-eager surface) and extend the
existing process owner to assert that normal output contains no runpy warning. This requires no
console script, packaging, Dockerfile or Compose change.

### P4-R3-S4-F7 — P3: handoff lineage and counts are inconsistent

The current Python source/test hash exactly matches S3b's `cf411aa...e91a849`, so the reviewed bytes
are identifiable despite the uncommitted candidate. The intermediate records are not a consistent
chain, however:

- S1b records base HEAD `edb1514` instead of the actual S1a handoff content hash
  `51d9242...17925`;
- S3a repeats the S2a handoff hash `2e9b4d4...a6a2d8` instead of the actual S2b handoff hash
  `ab75132...591b9`;
- S2b and S3a record a 39-character, incorrect validated code SHA;
- S3b prose reports four serial passes and 29 unit deselections, while its YAML reports six serial
  passes and the unchanged current tree reruns as six serial passes and 31 unit deselections.

The candidate was intentionally not committed without authorization, so S4 does not invent a code
SHA. The S5 appendix/handoff must explicitly carry the corrected lineage and current command evidence,
and final code/docs seals remain prerequisites to S6/S7. Historical records must not be silently
rewritten to imply authorization or commits that did not occur.

## 3. Required S4 review matrix

| Review item | Disposition | Evidence |
| --- | --- | --- |
| Owner/import/public surface | **pass** | Operations has no infrastructure/settings/Repository import; bootstrap is the only concrete composition root; root Operations exports remain unchanged. |
| Atomic registry preflight and mutation-free failure | **pass** | Candidate lookup, registry resolve and R2 `claim_one` share one write UoW; exceptions roll back and missing keys occur before token generation/mutation. |
| Integrity/topology/registry/recovery/double scan | **rework required** | Ordering and complete pages pass; F5 permits a gate that crossed the 60-second startup boundary to publish READY. |
| LeaseSession fresh records and closed shapes | **rework required** | Fresh UoW/record/version and terminal/successor compositions pass; F2 leaves lease expiry under checkpoint-builder policy. |
| Heartbeat busy/stale/expired/token fencing | **rework required** | Typed stale/expired fencing and token immutability pass; F1 overstates the current lease budget. |
| One non-daemon executor/no DB cross-thread/bounded waits | **rework required** | One non-daemon slot and fresh per-thread UoWs pass; F3 is a pre-heartbeat drain busy loop. |
| Cancel-before-effect/drain-not-cancel/timeout-no-force | **rework required** | Pre-executor cancel refresh, monotonic control and no-force behavior pass; F4 maps timeout to successful process return. |
| Executor/observer/builder/invariant failure | **pass with S5 regressions required** | Failures stop claims and do not synthesize terminal state; F2/F5 add missing builder/startup postconditions rather than a recovery policy. |
| Module CLI/current image/no packaging leakage | **rework required** | Source-on-PYTHONPATH entry fits the Dockerfile and no packaging/app/Compose change exists; F6 makes the authoritative CLI warning/double-load. |
| Unit/integration/serial ownership | **rework required** | Marker split and shared fixtures are proportionate; existing owners pass but omit F1–F6 regressions, and F7 corrects stale counts. |
| Redaction/no durable evidence or IPC | **pass** | Logs/events exclude token/path/payload/SQL and no metrics SDK, evidence table, socket, pidfile, broker or sidecar was added. |
| Single-worker/local-volume/container/capacity boundary | **pass, container deferred** | `max_in_flight=1`, local SQLite/WAL and empty pre-R4 registry remain explicit; final current-HEAD image gate remains S7-owned. |

## 4. Verification and proportionality

The required focused unit, file-backed integration, serial process, backend unit and five-package
static gates all pass on the reviewed source/test tree. Those passes are regression evidence, not
closure of the counterexamples above. The existing heartbeat-busy test starts its full 30-second
monotonic budget after thread start and uses a fake durable lease much longer than that budget; it
cannot detect F1. The lifecycle timeout test stops at controller state transitions and never checks
runtime/process exit mapping; it cannot detect F4. No current test owns an active pre-heartbeat drain,
a slow single startup gate, an arbitrary checkpoint lease extension or warning-free module startup.

The two in-memory counterexamples reused existing fake UoWs and an injected monotonic clock. The CLI
probe used one temporary SQLite/WAL file and the real module entrypoint. They added no repository file,
sleep matrix, durable evidence, extra process role or external dependency. This is proportionate to
the authoritative lease, readiness and shutdown barriers under review.

## 5. Container and benchmark disposition

```text
Current review input HEAD: edb15144ac5eae54e970c28f12f58e5e45b075a9
Reviewed source/test tree: sha256:cf411aa52974d103cf5bb1d38eee87f550e2d0ed9da9fda14df3ebfd5e91a849
Container rebuild required: yes
Reason: the candidate changes the module entrypoint, settings, signal wiring and process startup/shutdown boundary
Last verified image revision/source tree: none for the R3 candidate
Container gate: deferred
Required execution point: P4-R3-S7 final committed candidate after S4/S5/S6 closure
```

No benchmark applies: R3 makes no throughput claim. F1, F3 and F5 are correctness-budget findings;
their bounded fake-clock probes are not capacity benchmarks. If a representative active-set scan or
R4 handler cannot meet the frozen objective, the explicit capacity/GIL reopen conditions apply.

## 6. Authorization and next action

**P4-R3-S4 is complete with `rework_required`.** S5 is required but is not authorized by this review.
Its first change must be `p4-r3-s5-remediation-appendix.md`, with one row per finding specifying owner,
exact S1a–S3b path subset, production change, regression, commands, closure rule, reopen trigger and
container impact. Only after the appendix exists may finding-scoped production/tests be changed.

S6 independent review and S7 module/container gate remain blocked. This record does not authorize R4,
R5, P5, Dockerfile, packaging, Compose or production Repository-effect work.

## 7. S5 focused rereview

S5 was subsequently implemented as the uncommitted source/test candidate
`sha256:35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a`, with remediation
appendix content SHA `40bfe239...e7aac` and handoff content SHA `4c9a294...1d038`. The focused
rereview read the appendix, handoff, complete changed production files, finding regressions and
current worktree rather than accepting the handoff's PASS assertion as closure evidence.

No S5 path exceeds the finding-scoped authorization. The candidate changes only the already-owned
runtime, LeaseSession and bootstrap boundaries plus their four authoritative tests. It does not
change R1/R2 semantics, the fixed 30/10-second profile, Operations root exports, dependencies,
Dockerfile, Compose, HTTP/application wiring, executor count, recovery policy, durable evidence or
IPC. All seven S4 findings are closed for focused review.

### 7.1 Finding closure

| Finding | Rereview result | Independent evidence |
| --- | --- | --- |
| P4-R3-S4-F1 | **closed** | Claim budget is anchored before `claim_one`; renewal budget is anchored before `LeaseSession.heartbeat`. The committed deadline is never replenished by transaction or observer latency. The checked-in observer-latency regression passes; an additional bounded probe advanced claim latency to 31 seconds and proved fencing before thread creation with one `lease_lost` event. |
| P4-R3-S4-F2 | **closed** | Checkpoint validation now requires the candidate expiry to equal the transaction-fresh Step expiry before the R2 action. The arbitrary 365-day extension rolls back without losing the live session. |
| P4-R3-S4-F3 | **closed** | The loop-local drain flag is latched on first observation and the active branch waits on executor completion/deadline while heartbeat supervision continues. The fixed-clock regression proves no repeated drain polling or second claim. |
| P4-R3-S4-F4 | **closed** | `DRAINING_TIMEOUT` now raises worker-fatal `RuntimeError` after the non-daemon executor cooperates; bootstrap maps it to status 1. Timeout emits `drain_timed_out`, never `worker_exited`, and does not add kill/detach/cancel behavior. |
| P4-R3-S4-F5 | **closed** | Startup READY is buffered by `_StartupObserver`; `_StartupBudget` performs the post-gate monotonic check before publication. The 61-second gate returns FATAL with exactly one `startup_timeout` event and no READY/claim. |
| P4-R3-S4-F6 | **closed** | `gateway_backend.bootstrap.__init__` is side-effect free. Both the authoritative process regression and a fresh temporary-DB CLI probe reach ready/drain/exit without `RuntimeWarning` or `runpy` output. |
| P4-R3-S4-F7 | **closed** | S5 records the actual S1a–S3b content hashes, the pending uncommitted code identity, current 100/1393/1/6 test counts and the recomputed source/test tree hash without rewriting historical claims. Backend tests do not require xdist; the authoritative single-process marker commands below are the current evidence. |

### 7.2 Rereview commands and results

```text
sha256sum p4-r3-s5-remediation-appendix.md p4-r3-s5-handoff.md
  -> 40bfe239a70018fbe74ab48abbfed85ae7c68d3a636f347ccbde8d619f9e7aac
     4c9a29454043fb0fb8d2c0754560a0a2d341883a10fb99949192ccc976e1d038

sorted per-file Python source/test SHA-256 records
  -> 35992e625422607d5dca560b428599cd92149402544864e1815a192be7fa4d9a

cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_worker_contracts.py \
  tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py \
  tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py \
  tests/test_architecture.py
  -> 100 passed

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 1 passed, 6 deselected

uv run pytest -q -m serial \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 6 passed, 1 deselected

uv run pytest -q -m unit
  -> 1393 passed, 31 deselected, 1 pre-existing Starlette warning

five Python packages: uv run ruff check . && uv run mypy
  -> pass; backend 217, shared_kernel 34, repository_contracts 15,
     repository_client 26, repository_service 195 mypy source files

independent slow-claim probe
  -> 31-second claim latency fenced before executor start; zero threads; one lease_lost event

independent authoritative module CLI probe
  -> worker_ready, drain_started, worker_exited; no RuntimeWarning/runpy output

git diff --check and untracked S4 document whitespace/link checks
  -> pass
```

The full backend unit gate retains one unrelated Starlette deprecation warning. No Dolt,
Repository Service integration, benchmark or container gate applies to this focused rereview.
The source/test identity after all reruns remains `35992e6254...fa4d9a`.

### 7.3 Rereview decision and next boundary

**S4 focused review now passes after S5 remediation.** There are no open S4 findings and no reopen
condition was hit. S5 does not need another production/test remediation round.

S6 remains mandatory and must start in a new independent-review conversation from the actual
source/tests, corrected lineage and current Git state. It is not authorized by this rereview. S7
remains blocked until S6 passes and final code/tests are committed; S7 still owns the required
current-HEAD image rebuild and container worker smoke. This rereview creates no commit and authorizes
no R4, R5, P5, packaging, Dockerfile, Compose or Repository-effect work.
