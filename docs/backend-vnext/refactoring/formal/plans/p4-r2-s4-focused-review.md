# P4/R2-S4 Focused Owner Review

状态：**REWORK REQUIRED**

日期：2026-08-24

Reviewer：Durable Operation Store focused owner review

上游：[P4/R2-S3b Handoff](p4-r2-s3b-handoff.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)、
[P4-R2-S0 Entry Brief](p4-r2-s0-entry-brief.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)

```yaml
step_id: P4-R2-S4
input_handoff_sha: 7f1d25a473e113bb75f1cb6c91230509a42b03f1
input_validated_code_sha: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
reviewed_candidate_sha: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
reviewed_handoff_sha: 7f1d25a473e113bb75f1cb6c91230509a42b03f1
candidate_worktree_at_entry: clean
result: rework_required
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-s4-focused-review.md
commands_and_results:
  - "candidate ancestry, allowed-path lineage and git diff --check -> candidate is the direct code ancestor of the S3b docs seal; diff check pass"
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_store.py tests/test_control_db_migrations.py tests/test_sqlite_operation_store.py tests/test_architecture.py -> 105 passed"
  - "cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py -> 14 passed, 1 failed at concurrent fresh-file bootstrap"
  - "concurrent bootstrap nodeid repeated 20 times -> 18 passed, 2 failed with StoreBusy during PRAGMA journal_mode=WAL"
  - "cd vnext/backend && uv run pytest -q -m serial tests/test_sqlite_operation_store_integration.py -> 2 passed, 13 deselected"
  - "cd vnext/backend && uv run pytest -q -m unit -> 1307 passed, 15 deselected, 1 pre-existing Starlette deprecation warning"
  - "five Python packages: uv run ruff check . && uv run mypy -> pass"
  - "temporary-file atomicity/clock/terminal-branch probes -> reproduced F1-F3 without repository changes"
focused_tests: pass_but_not_review_closure
integration: fail_migration_race
serial: pass_2
backend_unit: pass_1307_deselected_15
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary_change
benchmark: not_applicable_no_performance_claim
findings:
  - P4-R2-S4-F1: P2 caught second-leg failures can commit partial cross-record actions
  - P4-R2-S4-F2: P2 terminal duplicate branch drift can create an active Step under a terminal Operation
  - P4-R2-S4-F3: P2 action time is not bound to the Unit of Work transaction clock
  - P4-R2-S4-F4: P2 concurrent fresh-file bootstrap intermittently fails before migration serialization
  - P4-R2-S4-F5: P3 sealed step evidence contains path and next-step provenance inconsistencies
deferred_items:
  - No finding is remediated by this documentation-only review.
  - R3 worker/bootstrap/settings/volume/readiness remains outside R2.
  - R4 successor/final policy and R5 retry/effect-aware recovery remain outside R2.
  - Production outbox, business repositories, Repository effects and deployment wiring remain outside R2.
reopen_conditions:
  - F1 cannot be closed without changing the frozen store/UoW public composition boundary.
  - F2 requires a schema-v1 change, new persisted field, JobDefinition interpretation or a new public query/mutation surface.
  - F3 cannot bind action time without changing the accepted transaction-clock ownership or public port.
  - F4 requires a public timeout/retry policy or changes the accepted SQLite connection profile.
next_step: P4-R2-S5 remediation appendix and finding-scoped remediation
next_step_authorized: no
s6: required_after_s5
s7: blocked
```

## 1. Review decision

The reviewed lineage preserves the intended package and dependency direction. Operations owns the
SQLite-neutral port and lifecycle composition, infrastructure owns `sqlite3`, migrations and the
concrete Unit of Work, and no business table, outbox, Repository client, worker, settings or
deployment wiring entered R2. Schema v1 stores one scalar or canonical composite representation of
each R1 field rather than a second full-document authority, and readback continues through the R1
parsers.

R2 nevertheless cannot pass focused owner review. Three independent probes demonstrate that the
current public composition can commit or create durable cross-record states outside the accepted
atomicity matrix, and the required file-backed integration gate independently reproduced a
concurrent-bootstrap failure. These are durable-state and startup barriers, not test-style
preferences. S7 is blocked; S5 is required and must begin with the finding-scoped remediation
appendix required by the execution plan. This review does not authorize production or test changes.

## 2. Findings

### P4-R2-S4-F1 — P2: caught second-leg failures can commit partial cross-record actions

Owner：`gateway_backend.operations.persistence` composition contract and concrete control DB UoW

`OperationLifecycleActions` performs the two legs of claim, cancel, successor and final-operation
actions as sequential `OperationStore` calls. `ControlDbUnitOfWork.__exit__` rolls back only when an
exception escapes the `with` block. Neither the store nor the action composer marks the transaction
rollback-only or establishes an action-scoped rollback boundary after its first mutation.

A temporary file-backed probe claimed an Operation/Step, then called `cancel_intent` with a valid
Operation precondition and a stale Step precondition. Catching `StaleWrite` inside the UoW let the
context exit cleanly. Reopen showed `operation.cancel_requested == true` while
`step.cancel_requested == false`. The same structure exists for terminal Step plus successor,
terminal Step plus Operation, and the first-claim Operation/Step pair. Existing rollback tests let
the exception escape the UoW, so they do not prove action atomicity under an ordinary caught owner
outcome.

Required S5 disposition：define one enforceable transaction-failure rule within the accepted
single-DB boundary, then prove that catching every representative second-leg store outcome inside
the UoW cannot commit a prefix. A rollback-only UoW contract, action savepoint or truly atomic store
operation may be considered, but any new public method/signature must first satisfy the reopen
condition rather than silently expanding the frozen port. The regression owner must cover cancel
and one terminal composition; it need not enumerate every SQLite statement.

### P4-R2-S4-F2 — P2: terminal duplicate branch drift admits terminal Operation plus active Step

Owner：Operation lifecycle composition plus the R2 cross-table structural invariant

Exact terminal record equality correctly returns `IDEMPOTENT`, but the composition layer does not
bind that duplicate to the already-persisted final branch. A probe first completed a Step and its
Operation as `SUCCEEDED`, then retried the exact terminal Step through
`complete_with_successor(...)`. The Step leg returned `IDEMPOTENT`; `insert_successor_step(...)`
returned `APPLY`. Reopen contained a `SUCCEEDED` Operation with a `PENDING` successor, and
`scan_active_integrity()` then raised `CorruptPersistedRecord: active step belongs to a terminal
operation`.

The inverse branch is also structurally unguarded: after terminal-Step-plus-successor publication,
an exact terminal Step retry can be combined with a terminal Operation candidate while the active
successor remains. The partial unique Step index does not constrain Operation terminality, and
`insert_successor_step` only verifies that the owning Operation exists.

Required S5 proof：terminal/successor branch retries must be deterministic and must never let a
public R2 API create a state that its own active-integrity scan rejects. Cover both branch orders,
direct successor insertion under a terminal Operation, and persisted-state non-mutation after
rejection. If closure needs a trigger/schema-v1 change, new active-Step lookup, JobDefinition
interpretation or another public axis, reopen that owner before remediation.

### P4-R2-S4-F3 — P2: action time is not bound to the Unit of Work clock sample

Owner：Operation lifecycle composition and concrete transaction-clock seam

The accepted profile requires one injected UTC wall-clock sample per transaction. The concrete UoW
captures that value and the SQLite adapter uses it for live-lease CAS, but
`OperationLifecycleActions` accepts a separate arbitrary `transaction_now`. Nothing checks that it
equals the store/UoW sample. `list_claim_candidates` also uses the action-provided value rather than
the adapter's captured transaction time.

A probe opened a UoW at `03:05:05Z` and constructed the action composer with `03:04:05Z`. Claim
succeeded and committed a new lease expiring at `03:04:35Z`, already expired relative to the
transaction clock. The opposite skew can make a future `RETRY_WAIT` candidate appear due early.
This bypasses both due-time and lease-duration correctness without malformed records or direct SQL.

Required S5 proof：the runnable scan and claim lease must derive from, or be checked against, the
same sampled transaction time used by live-lease CAS. Add mismatched-clock negative cases and due /
expiry boundary cases with fake clocks only. Do not add a second persisted clock, monotonic-time
protocol or timing evidence state.

### P4-R2-S4-F4 — P2: concurrent fresh-file bootstrap intermittently fails before migration serialization

Owner：`gateway_backend.infrastructure.control_db.database` connection/bootstrap boundary

The accepted migration gate requires two startup connections to bootstrap one fresh file normally,
with `BEGIN IMMEDIATE` serializing ledger creation and migration. The full integration run failed
that existing test: one connection raised `StoreBusy` from `PRAGMA journal_mode=WAL` in
`connect_control_db`, before `bootstrap_control_schema` could acquire its transaction. A bounded
20-run repetition produced 18 passes and 2 identical failures. The configured five-second busy
timeout therefore does not make the pre-migration WAL-profile race reliable.

This is not the accepted steady-state writer-contention outcome: it prevents a normal concurrent
startup from reaching the migration serialization boundary and contradicts both the S1b/S3b
handoff evidence and the current integration assertion.

Required S5 proof：two independent startup connections on a fresh file must converge on one v1
ledger/schema and WAL profile without an exposed transient `StoreBusy`. The fix must remain bounded
and local to connection/bootstrap semantics. Keep one barrier-based file-backed integration owner;
do not introduce an unbounded retry framework, daemon, durable migration evidence or exhaustive
SQLite schedule matrix.

### P4-R2-S4-F5 — P3: sealed step evidence has path and next-step provenance inconsistencies

Owner：P4/R2 execution records

The S3a code candidate adds one public-export assertion to
`vnext/backend/tests/test_operation_contracts.py`, although that file is not in the frozen R2
allowed-path list. The assertion is a sensible single owner for the shared Operations export
surface and does not duplicate the R1 malformed-record matrix, but the handoff records the change
without an allowed-path exception or reopen disposition. Separately, the S2b handoff names
`P4-R3-S3a` as its next step in both YAML and prose instead of `P4-R2-S3a`.

Required S5 disposition：correct the next-step typo and explicitly resolve the one-line shared
public-export test ownership in the remediation appendix/plan record. Do not copy the export
inventory into another R2 test merely to satisfy path wording.

## 3. Required S4 review matrix

| Review item | Disposition | Evidence |
| --- | --- | --- |
| Operations/infrastructure/UoW ownership and dependency direction | **pass** | Operations remains SQLite-neutral; only control DB infrastructure imports `sqlite3` and the public Operations surface. F1 is a transaction-semantics gap, not an import inversion. |
| Schema avoids duplicate semantic authority | **pass** | Direct scalar columns plus canonical composite BLOBs reconstruct one closed R1 document; no duplicated full document, effect field, repair state or second version axis was added. |
| Create/claim/terminal/successor/cancel atomicity | **rework required** | Nominal commit/rollback paths pass, but F1 permits caught failures to commit prefixes and F2 permits a durable terminal/active cross-table contradiction. |
| Stale/expired/terminal duplicate/affected-row classification | **rework required** | Typed stale and expiry cases pass and affected-row reclassification is local to the transaction; F2 shows exact terminal idempotency is not closed across the selected action branch. |
| Migration race, unsupported version and corruption | **rework required** | Higher-version rejection, rollback and strict R1 readback pass; F4 makes the required concurrent fresh bootstrap nondeterministic. F2 also demonstrates that public writes can create a state later classified as corruption. |
| Busy/clock/limit budgets | **rework required** | Page and claim hard maxima, cursor caps, 30-second lease constant and steady-state `StoreBusy` mapping pass. F3 bypasses the single transaction clock, and F4 bypasses expected startup convergence before migration locking. |
| No outbox/business/Repository/worker/deployment expansion | **pass** | No production business/outbox table, Repository import, JobDefinition policy, settings, worker, HTTP, Docker or Compose path entered the candidate. |
| Test ownership and proportional SQLite evidence | **rework required** | Unit/integration/serial split and the single crash barrier are proportionate; tests do not duplicate the R1 invalid-shape matrix. F1-F3 are missing contract barriers, F4 is a failing existing owner, and F5 is a sealed evidence-path inconsistency. |

## 4. Verification and proportionality

The focused unit gate passed 105 tests, backend unit passed 1307 tests with the existing Starlette
warning, both serial cases passed, and all five packages passed full ruff/mypy. The full file-backed
integration gate did not pass because the concurrent-bootstrap owner failed; a bounded repetition
confirmed the same production-path exception rather than expanding into schedule enumeration.

The three independent probes used temporary SQLite files, the accepted public UoW/store/action
surface and fake UTC clocks. They added no test file, process harness, durable evidence state,
security principal or fault-injection framework. F1 and F2 concern authoritative durable
cross-table facts; F3 concerns the accepted lease/claim clock barrier; F4 concerns the required
startup migration contract. Their P2 severity is proportional to those business correctness
boundaries.

## 5. Container and benchmark disposition

```text
Current review input HEAD: 7f1d25a473e113bb75f1cb6c91230509a42b03f1
Reviewed code/test candidate: f77dd43d8f0e2e10b5c40048093161c3a70f4ffe
Container rebuild required: no
Reason: the R2 lineage changes pure Python persistence/SQL, tests and formal docs; it does not change an image, dependency lock, entrypoint, Compose, mount, UID/GID or container-only runtime behavior
Last verified image revision: none found for this Phase 4 candidate
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: Phase 4 final candidate must rebuild and execute its production container/Compose gate
Required execution point: Phase 4 final production candidate
```

Benchmark is `not_applicable`: R2 makes no throughput or capacity claim. The bounded migration-race
repetition diagnoses a correctness gate and is not a benchmark.

## 6. Authorization and next action

**P4-R2-S4 review is complete with `rework_required`.** S5 is required but is not authorized by this
record. Its first change must be a remediation appendix listing each finding's owner, allowed paths,
regression proof, focused/integration rerun, closure criterion and reopen trigger. All P2 findings
must be closed or explicitly reopened before the mandatory S6 independent review. P4-R2-S7 and R3
entry remain unauthorized.
