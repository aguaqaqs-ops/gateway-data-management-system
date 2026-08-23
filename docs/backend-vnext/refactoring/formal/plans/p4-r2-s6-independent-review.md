# P4/R2-S6 Risk-based Independent Review

状态：**PASS AFTER FINDING-SCOPED REMEDIATION**

当前处置见 §8；§1–7 保留初次 independent review 的 findings、证据与当时的
`rework_required` 决定。

日期：2026-08-24

Reviewer：independent durable Operation Store transaction/recovery review

上游：[P4/R2-S5 Handoff](p4-r2-s5-handoff.md)、
[P4-R2-S5 F1 Follow-up Handoff](p4-r2-s5-f1-follow-up-handoff.md)、
[P4/R2-S4 Focused Owner Review](p4-r2-s4-focused-review.md)、
[P4-R2 Durable Store and Atomic Transition Detailed Execution Plan](p4-r2-durable-store-atomic-transition-execution-plan.md)、
[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、
[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、
[Proportional Assurance and Risk-Based Verification Policy](../policies/proportional-assurance-and-risk-based-verification-policy.md)

```yaml
step_id: P4-R2-S6
input_s5_handoff_sha: d057ab3f229ebd513eba56748c7e528ba3efc48b
input_s4_closure_sha: 7c68ef3d829ad3b13aee98782526b3f9b9972602
reviewed_candidate_sha: 15fc3e80031cb503292c880afc9b77b245b3a23c
reviewed_handoff_sha: d057ab3f229ebd513eba56748c7e528ba3efc48b
candidate_worktree_at_entry: clean
result: rework_required
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r2-s6-independent-review.md
commands_and_results:
  - "candidate ancestry and source/test identity -> pass; 15fc3e8 is the unchanged code/test ancestor of d057ab3 and current review input 7c68ef3"
  - "independent file-backed caught claim-validation probe -> reproduced S6-F1; RUNNING Operation plus PENDING Step committed after the caller caught ValueError"
  - "independent accepted-version-boundary claim probe -> reproduced the same S6-F1 prefix when Step candidate construction overflowed its I-JSON version budget"
  - "independent file-backed unknown-status probe -> reproduced S6-F2; active integrity scan returned success while direct Step readback raised CorruptPersistedRecord"
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_operation_store.py tests/test_control_db_migrations.py tests/test_sqlite_operation_store.py tests/test_architecture.py -> 487 passed"
  - "cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py -> 20 passed"
  - "cd vnext/backend && uv run pytest -q -m serial tests/test_sqlite_operation_store_integration.py -> 2 passed, 18 deselected"
  - "concurrent fresh-file bootstrap nodeid repeated 20 times -> 20 passed"
  - "cd vnext/backend && uv run pytest -q -m unit -> 1315 passed, 20 deselected, 1 pre-existing Starlette deprecation warning"
  - "five Python packages: uv run ruff check . && uv run mypy -> pass"
  - "tracked git diff check and no-index whitespace check for the new review record -> pass"
focused_tests: pass_but_not_review_closure_487_unit
integration: pass_20
serial: pass_2_collected_2; 18_deselected
migration_bootstrap_repetition: pass_20_of_20
backend_unit: pass_1315_deselected_20
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary_change
benchmark: not_applicable_no_performance_claim
findings:
  - P4-R2-S6-F1: P2 claim-local validation failure can commit a cross-table prefix
  - P4-R2-S6-F2: P2 unknown active status is invisible to the readiness integrity scan
deferred_items:
  - R3 worker/bootstrap/settings/volume/readiness route remains outside R2.
  - R4 successor/final policy and R5 retry/effect-aware recovery remain outside R2.
  - Production outbox, business repositories, Repository effects and deployment wiring remain outside R2.
  - Retention, backup and a real capacity baseline remain deferred to a confirmed consumer.
reopen_conditions:
  - S6-F1 cannot be closed without a new public transaction outcome, savepoint/mutation API, schema field or neutral UoW contract change.
  - S6-F2 cannot fail closed without changing the accepted terminal-history exclusion or adding schema, repair, quarantine or durable evidence state.
  - Any remediation that requires a changed R1 record/transition contract, status matrix, persisted field, schema version, error taxonomy or deployment boundary.
next_step: P4-R2-S6 finding disposition and finding-scoped remediation
next_step_authorized: no
s7: blocked
```

## 1. Review decision

S6 independently reviewed the final S5 F1 follow-up candidate rather than treating the S4/S5
closure records as proof. Package direction, schema v1, guarded row CAS, live-lease comparison,
terminal duplicate handling, rollback-only behavior after a failed store mutation, migration
serialization and the S4 terminal/successor branch fix remain within the accepted R2 boundary.

The candidate nevertheless cannot pass S6. Two independent probes reach B-class durable-state
barriers that the passing suite does not cover. First, `claim_one(...)` can commit its Operation
prefix when local Step candidate validation fails between its two store mutations. Second, the
startup integrity seam silently skips a Step whose status scalar is corrupt and no longer matches a
known active enum. Both cases contradict an explicit R2 atomicity/readiness promise and can leave
worker-visible state without an owner-specific startup failure.

This review is documentation-only. It does not modify the reviewed production/tests, select a
schema or public-port expansion, or add repair/evidence machinery. P4-R2-S7 and R3 entry remain
blocked until both P2 findings are closed or their owning boundary is explicitly reopened and the
independent review is rerun.

## 2. Risk registration

```text
authoritative facts: none added by R2; future business T1/T3 and Repository effects remain outside this module
recoverable durable state: Operation/Step rows, optimistic versions, lease identity and migration ledger
derived/temporary state: eligible_at_us and opaque pagination cursors
external trust boundaries: caller-supplied accepted records/identities and the server-owned local SQLite file
accepted deployment assumptions: same-host trusted modules, reliable local WAL volume, one bounded writer
highest risk class: B — durable recoverable operation state
required semantic barriers: cross-table transaction atomicity, guarded CAS, migration convergence and fail-closed active corruption scan
explicitly out of scope: business/outbox/Repository effects, worker policy, automatic repair, multi-host/NFS/HA and exhaustive SQLite schedules
reopen conditions: public/schema/R1/deployment changes listed in the YAML record above
```

The probes use the existing public UoW/store/action surface, one temporary SQLite file and bounded
direct corruption setup. They do not model a malicious same-euid actor or justify a new evidence
service. The status-corruption setup is the same kind of deterministic storage-fault construction
already used by the R2 orphan/readback tests.

## 3. Independent findings

### P4-R2-S6-F1 — P2: claim-local validation failure can commit a cross-table prefix

Owner：`gateway_backend.operations.persistence.OperationLifecycleActions` and the concrete control
DB transaction-failure boundary

`claim_one(...)` validates `worker_id` and `lease_token` with a local helper that only checks
non-empty text and byte length. That is weaker than the R1 opaque-ID owner, which also rejects
control characters and host-path identities. For a first claim, the action then persists
`Operation QUEUED -> RUNNING` before constructing the RUNNING Step candidate. The Step dataclass
reapplies the stronger R1 validator and can raise after the first write but before a second store
mutation enters `SQLiteOperationStore._run_mutation(...)`.

A file-backed probe supplied a control-character worker ID through the accepted action surface and
caught the resulting `ValueError` inside the Unit of Work. Clean context exit committed
`Operation(status=RUNNING, optimistic_version=1)` while the Step remained
`PENDING, optimistic_version=0`. `scan_active_integrity()` accepted the pair. The original create
was valid, and no direct SQL, connection access or fake store was used for the claim.

A second probe used a valid PENDING Step at the accepted maximum I-JSON optimistic version. The
Operation first leg again applied; constructing the incremented Step then failed its version budget,
and catching that error committed the same prefix. This shows the gap is the ordering of local
candidate construction and transaction poisoning, not only the identity helper.

S5-F1 correctly made failed **store mutations** rollback-only and rejected later store mutations.
It does not see exceptions raised by action-local work between two store calls. The result violates
the required first-claim atomic fact and can expose a RUNNING Operation without a worker lease;
with a repeatedly invalid worker identity or exhausted Step version, ordinary claim retry does not
close the state.

Required disposition：validate claim identities with the existing R1 opaque-ID rule and construct
both complete accepted post-state records before the first store mutation. Add one action-level and
one file-backed caught-error regression proving that neither row/version changes after reopen. A
shared parameter table may cover the identity and version construction failures. Do not add a new
public outcome, action/savepoint API or durable rollback state unless the public boundary is first
reopened.

### P4-R2-S6-F2 — P2: unknown active status is invisible to the readiness integrity scan

Owner：`SQLiteOperationStore.scan_active_integrity` and the R2 corruption/readiness seam

The active Step scan selects only rows whose raw status already equals one of
`PENDING | RUNNING | RETRY_WAIT | MANUAL_RECOVERY_REQUIRED`. A row with an unknown or non-text
status is therefore filtered out before `step_record_from_row(...)` can reconstruct the closed R1
document and return `CorruptPersistedRecord`.

A temporary file-backed probe created a valid QUEUED Operation/PENDING Step, deterministically
changed the Step status to an unknown value while bypassing the CHECK solely to model persisted-row
corruption, then reopened the store. `scan_active_integrity()` returned
`operations_scanned=1, steps_scanned=0, next_cursor=None`; direct `get_step(...)` raised
`CorruptPersistedRecord` as expected. An R3 caller that follows the bounded cursor to completion
would therefore open readiness even though the only runnable Step cannot be parsed or claimed.

Known final-terminal history should remain excluded as accepted. Unknown/null/wrong-type statuses
cannot be classified as terminal history and must fail closed. The same raw-status filtering exists
on the Operation phase, although an active child can incidentally expose some corrupt Operation
rows during owner validation; that incidental path is not a complete Operation scan guarantee.

Required disposition：make both bounded phases include unrecognized/null status scalars and route
them through the existing R1 row parser, while continuing to exclude records with recognized
terminal statuses. Add one shared Operation/Step regression owner and retain bounded keyset
pagination. Do not introduce automatic repair, quarantine, a checksum ledger, full historical scan
or a new readiness route.

## 4. Required review matrix

| Review item | Disposition | Independent evidence |
| --- | --- | --- |
| Operations/infrastructure/UoW ownership and dependency direction | **pass** | Operations remains SQLite-neutral; connection, migration and adapter stay in control DB infrastructure. No business, Repository, worker or deployment import entered R2. |
| B-class durable state and cross-table atomicity | **rework required** | Create and the S5 cancel/successor caught-error paths pass, but F1 commits the first-claim Operation prefix when local second-record construction fails. |
| Version/lease CAS and terminal idempotency | **pass** | Current rows pass R1 transition and precondition guards inside `BEGIN IMMEDIATE`; SQL predicates retain identity/version/lease conditions, live lease uses the transaction sample, and exact terminal duplicates do not update. |
| Migration race and unsupported version | **pass** | Fresh/repeat/higher-version/rollback tests pass; file-backed integration passes and the formerly flaky concurrent fresh bootstrap passed 20/20 independent repetitions under the bounded retry. |
| Corruption and readiness seam | **rework required** | Strict ID readback, canonical/scalar mapping, orphan owner and terminal-history rules pass. F2 lets an unclassifiable Step status disappear from the complete active scan. |
| Busy/clock/query budgets | **pass** | Five-second busy profile, one sampled UoW clock, exact claim-clock comparison, limit 1 claim and bounded keyset pages remain enforced. No capacity or throughput claim is made. |
| S4/S5 finding closure | **pass within recorded scope** | F1 poison follow-up, terminal/successor branch consistency, transaction-clock seam, WAL startup convergence and path-owner correction reproduce as recorded. S6-F1 is a distinct action-local gap outside the store-mutation wrapper. |
| Proportional test ownership and scope | **rework required** | Existing unit/integration/serial split and one crash barrier are proportionate, but passing tests omit the two contract barriers above. No exhaustive schedule or duplicate R1 shape matrix is needed to close them. |

## 5. Verification and proportionality

The combined focused unit gate passed 487 tests; all 20 file-backed integration tests and both
serial owners passed. Backend unit passed 1315 tests with only the pre-existing Starlette/httpx
deprecation warning, and all five Python packages passed full ruff/mypy. The concurrent bootstrap
owner passed 20 additional bounded repetitions. These results establish candidate health and the
continued closure of the relevant S4/S5 regressions; they do not override independently reproduced
atomicity/readiness counterexamples.

The reviewed source/test candidate `15fc3e8` is the unchanged ancestor of the F1 follow-up handoff
`d057ab3` and current review input `7c68ef3`. The intervening commits change only the follow-up
handoff and focused-review record. No unrecorded source/test, schema, dependency or deployment delta
was inherited by S6.

F1 and F2 affect recoverable durable workflow state and startup availability, so P2 is
proportionate. Their closure needs local ordering/query changes and focused semantic tests, not a
generic transaction framework, durable evidence state, automatic repair or exhaustive SQLite
interleaving harness.

## 6. Container and benchmark disposition

```text
Current review input HEAD: 7c68ef3d829ad3b13aee98782526b3f9b9972602
Reviewed code/test candidate: 15fc3e80031cb503292c880afc9b77b245b3a23c
Container rebuild required: no
Reason: S6 is a documentation-only review and the reviewed R2 lineage changes pure Python/SQLite logic and tests; no image, dependency, entrypoint, Compose, mount, UID/GID or container-only boundary changed
Last verified image revision for this Phase 4 candidate: none found
Last verified source-tree/image id: none
Container gate for current candidate: not-applicable
Deferred gates/nodeids: Phase 4 final production candidate must rebuild and execute its production container/Compose gate
Required execution point: Phase 4 final production candidate
```

Benchmark is `not_applicable`: R2 freezes bounded limits but makes no latency, throughput or capacity
claim. The 20-run bootstrap repetition is correctness evidence for a previously reproduced startup
race, not a benchmark.

## 7. Initial authorization and next action

**The initial S6 review completed with `rework_required`.** S6-F1 and S6-F2 had to be closed or explicitly
reopened at their owning boundaries before the R2 module gate. The next work is a docs-only finding
disposition followed by separately authorized, finding-scoped remediation and an independent S6
rerun. This record does not authorize those production/test changes, P4-R2-S7, R3 entry, worker or
deployment work.

## 8. Independent remediation rerun

状态：**PASS**

```yaml
step_id: P4-R2-S6-independent-rerun
input_initial_review_head_sha: 7c68ef3d829ad3b13aee98782526b3f9b9972602
input_remediation_handoff_sha: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
reviewed_candidate_sha: 31235dc820472a5ca2c99138fdf150090cfe122d
reviewed_handoff_sha: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
review_worktree_at_entry: only_expected_untracked_independent_review_record
result: pass_after_finding_scoped_remediation
closed_findings:
  - P4-R2-S6-F1
  - P4-R2-S6-F2
open_findings: []
commands_and_results:
  - "candidate ancestry, exact changed paths and source/test identity -> pass; 31235dc is the unchanged source/test ancestor of docs-only handoff 29aa42d"
  - "independent file-backed F1 probes -> pass; control-character identity and maximum Step version both raise before either row changes and remain unchanged after reopen"
  - "independent file-backed F2 probes -> pass; Operation and Step unknown/null/integer-affinity/BLOB statuses all raise CorruptPersistedRecord without repair"
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_operation_store.py tests/test_control_db_migrations.py tests/test_sqlite_operation_store.py tests/test_architecture.py -> 491 passed"
  - "cd vnext/backend && uv run pytest -q -m integration tests/test_sqlite_operation_store_integration.py -> 24 passed"
  - "cd vnext/backend && uv run pytest -q -m serial tests/test_sqlite_operation_store_integration.py -> 2 passed, 22 deselected"
  - "cd vnext/backend && uv run pytest -q -m unit -> 1319 passed, 24 deselected, 1 pre-existing Starlette deprecation warning"
  - "five Python packages: uv run ruff check . && uv run mypy -> pass"
  - "candidate and review-record whitespace checks -> pass"
focused_tests: pass_491_unit
integration: pass_24
serial: pass_2_collected_2; 22_deselected
backend_unit: pass_1319_deselected_24
five_package_static: pass
container_gate: not_applicable_no_image_or_deployment_boundary_change
benchmark: not_applicable_no_performance_claim
deferred_items:
  - P4-R2-S7 module gate and final R2 handoff.
  - R3 worker/bootstrap/settings/volume/readiness route.
  - R4 successor/final policy and R5 retry/effect-aware recovery.
  - Production outbox, business repositories, Repository effects and deployment wiring.
  - Retention, backup and a real capacity baseline remain deferred to a confirmed consumer.
reopen_conditions:
  - A claim-local exception can again occur after the first cross-table mutation or persist either row/version.
  - An unknown, null or wrong-type Operation/Step status can complete the active integrity scan successfully.
  - Closure requires a new public transaction outcome, savepoint/mutation API, schema/version, repair/evidence state, R1 semantic change or deployment-boundary change.
next_step: P4-R2-S7
next_step_authorized: no
s7: pending_explicit_authorization
r3_entry: blocked_pending_s7
```

### 8.1 Rerun decision

The remediation candidate closes both P2 findings within their recorded owner and allowed paths.
No public store/UoW symbol or error, schema v1 field/version, R1 record/transition rule, SQLite
profile, dependency or deployment boundary changed. The candidate contains no unrelated cleanup,
and the handoff commit changes only the two S6 remediation records.

No new P1/P2 finding or contract ambiguity was found. The initial §1–7 decision is superseded for
the remediated candidate by this `pass_after_finding_scoped_remediation` result.

### 8.2 F1 closure — PASS

`claim_one(...)` now reuses the R1 opaque-ID validator and constructs the complete Step and
Operation post-state records before the first CAS. Identity, timestamp, lease-expiry and I-JSON
version construction failures therefore occur while both persisted rows are still untouched.
After construction, any second-leg store error continues to enter the existing mutation wrapper,
mark the participant rollback-only and roll back the complete UoW.

The independent file-backed rerun caught both original representative failures: a
control-character worker identity and a PENDING Step at the maximum I-JSON optimistic version.
After clean UoW exit and reopen, both cases retained the exact original QUEUED Operation and PENDING
Step, including optimistic versions. Normal claim and the existing caught second-leg regressions
remain green. F1 is closed without a public transaction outcome, savepoint or durable rollback
state.

### 8.3 F2 closure — PASS

Both integrity phases now exclude only recognized terminal statuses. Every other raw status enters
the same bounded keyset page and strict R1 row mapper. The independent file-backed rerun covered
Operation and Step rows with an unknown string, `NULL`, an integer-affinity value and a BLOB; every
case raised `CorruptPersistedRecord`, and direct SQL readback confirmed the scan did not repair or
rewrite the damaged value.

Recognized terminal history remains excluded, active owner validation and keyset cursors remain
unchanged, and the fix adds no full-history scan, repair, quarantine or evidence state. F2 is
closed.

### 8.4 Verification, container and benchmark disposition

The independently rerun focused, backend-unit, file-backed integration, serial and five-package
static gates all pass with the counts recorded above. Unit tests own the action/query semantics;
file-backed cases additionally prove clean UoW exit, reopen visibility and no repair. The two layers
therefore cover distinct in-transaction and durable barriers without adding an exhaustive SQLite
schedule matrix or duplicating the R1 malformed-record suite.

```text
Current review input HEAD: 29aa42d4b5c3d405ee9be24207e3fd1cddae9f72
Reviewed code/test candidate: 31235dc820472a5ca2c99138fdf150090cfe122d
Container rebuild required: no
Reason: remediation changes only Python/SQLite logic and tests; the rerun changes only this formal review record, with no image, dependency, entrypoint, Compose, mount, UID/GID or container-only boundary
Last verified image revision for this Phase 4 candidate: none found
Last verified source-tree/image id: none
Container gate for current candidate: not-applicable
Deferred gates/nodeids: Phase 4 final production candidate must rebuild and execute its production container/Compose gate
Required execution point: Phase 4 final production candidate
```

Benchmark remains `not_applicable`: neither remediation nor rerun introduces a latency, throughput
or capacity claim.

### 8.5 Authorization and next action

**P4-R2-S6 exits `pass_after_finding_scoped_remediation`; there are no open findings.** The only
next step is P4-R2-S7 module gate and final R2 handoff after separate authorization. This review
does not authorize S7, R3 entry, worker/settings/Compose work, R4/R5 policy, P5 business/outbox or
Repository-effect integration.
