# P4/R1-S6 Risk-based Independent Review

状态：**REWORK REQUIRED**

日期：2026-08-23

Reviewer：independent Operation Runtime contract/recovery review

上游：[P4/R1-S5 Handoff](p4-r1-s5-handoff.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)、[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)、[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md)

```yaml
step_id: P4-R1-S6
input_handoff_sha: 12bc06ccb83a6338eb94d97348f3c24eda1b6cff
reviewed_candidate_sha: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
reviewed_handoff_sha: 12bc06ccb83a6338eb94d97348f3c24eda1b6cff
candidate_worktree_at_entry: clean
result: rework_required
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r1-s6-independent-review.md
commands_and_results:
  - "candidate/tree identity and allowed-path diff checks -> pass; 1243b1c is the unchanged code/test ancestor of 12bc06c"
  - "independent finite-binary64/same-status/precondition-budget probes -> reproduced S6-F1 through S6-F3"
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py -> 381 passed"
  - "cd vnext/backend && uv run ruff check . && uv run mypy -> pass"
  - "other four Python packages: uv run ruff check . && uv run mypy -> pass"
  - "git diff --check a2da77f..1243b1c -> pass"
focused_tests: pass_but_not_contract_closure
five_package_static: pass
container_gate: not_applicable_r1_no_image_or_deployment_boundary_change
benchmark: not_applicable_contract_state_only
findings:
  - P4-R1-S6-F1: P2 non-final same-status guard semantics contradict the accepted contract
  - P4-R1-S6-F2: P2 valid finite binary64 inline payload is rejected as non-I-JSON
  - P4-R1-S6-F3: P3 write-precondition identities omit accepted opaque-ID bounds
deferred_items:
  - SQLite/WAL atomic CAS remains R2-owned and is not implemented in R1.
  - External-effect cancel/fail/supersede authorization remains R5/JobDefinition-owned.
  - No S6 finding is remediated by this documentation-only independent review.
reopen_conditions:
  - Same-status mutation ownership cannot be made unambiguous without changing the accepted guard semantics or R2 composition contract.
  - Remediation requires a new public guard/signature, persisted key, status matrix, version axis or external-effect authorization mechanism.
next_step: P4-R1-S6 finding disposition and owning-contract reopen plan
next_step_authorized: yes
next_step_scope: docs_only
```

## 1. Review decision

S6 independently reviewed the clean S5 code candidate rather than accepting the S4/S5 disposition
as evidence. Package placement, public exports, status matrices, MANUAL attention behavior,
terminal idempotency, immutable records, import direction and deployment scope remain within R1.
The candidate nevertheless cannot pass S6 because two P2 contract mismatches remain open. The
focused suite passes because it asserts the mismatching behavior; it is regression evidence for the
current implementation, not closure evidence for the accepted contract.

This review is documentation-only. It does not choose a replacement same-status API, revise an
owning contract, change production/tests, or introduce a new security/evidence mechanism. S7 and R2
entry remain unauthorized.

## 2. Independent findings

### P4-R1-S6-F1 — P2: non-final same-status guard behavior contradicts the accepted contract

Owner：Operation Runtime contract/state; R2 is the first persistence consumer

The S0-accepted detailed plan §2.7 states that
`validate_operation_transition` / `validate_step_transition` decide status publication only;
heartbeat, checkpoint and cancel-intent writes are not status self-loops, and a final-terminal
duplicate is the only same-status publication passed to a transition guard. The S3b handoff also
names “same-status mutation routed through transition guard” as a reopen condition.

S5 changed both transition guards to return `APPLY` for non-final same-status candidates and added
tests that require RUNNING heartbeat/checkpoint/cancel-intent calls to take this path. This closes
the relational validation hole reported as S4-F3 in code, but it does so by selecting the exact
semantic that the accepted contract and prior handoff forbid. Neither the Operation Lifecycle
contract nor the detailed plan was reopened or synchronized.

R2 therefore has no unambiguous authority for its CAS composition. If it follows the frozen §2.7
route, immutable envelope, cancel monotonicity and lease identity remain unproved for same-status
writes. If it follows the S5 implementation/handoff, it treats a mutation as a status publication
against the accepted API semantics.

Required disposition：reopen and make one owner path normative before code remediation. The
decision must either authorize relational same-status validation through the existing guard and
synchronize the formal contract/plan, or define a contract-compatible R2-enforceable mutation
composition. A new public guard/signature still requires an explicit public-surface decision. Add
regression coverage for the accepted route and rerun independent review; do not silently defer the
relational invariant to R2.

### P4-R1-S6-F2 — P2: valid finite binary64 payload is rejected as non-I-JSON

Owner：`gateway_backend.operations.contracts`; canonical JSON semantics remain Shared Kernel-owned

The accepted R1 representation requires an opaque inline payload to be a bounded JSON/I-JSON
object and permits Operations to reuse Shared Kernel JCS/I-JSON primitives without interpreting job
fields. The Shared Canonical Encoding contract explicitly includes finite binary64 numbers in
I-JSON.

An independent probe confirmed that Shared Kernel canonicalizes `{"value": 1.5}` to
`b'{"value":1.5}'`, while `operation_record_from_document(...)` rejects the same payload with
`ValueError: job_payload must not contain non-I-JSON numbers`. The implementation rejects every
Python `float`, and the malformed-payload table records `1.5` as an expected rejection. This is not
a resource limit and no S0 decision narrowed the number grammar to integers; it changes the
accepted payload contract and can reject a valid JobDefinition-owned document.

Required disposition：accept finite binary64 values supported by the Shared Kernel JCS contract,
retain fail-closed handling for non-finite/out-of-contract numbers, and replace the incorrect
negative case with canonical parser/direct-constructor round-trip boundaries. No new payload
version, semantic digest or job-field interpretation is needed.

### P4-R1-S6-F3 — P3: write-precondition identities omit accepted opaque-ID bounds

Owner：`gateway_backend.operations.state`

The frozen budget covers worker and lease IDs with 1..255 UTF-8 bytes plus control/host-path
rejection. `StepRecord` enforces that boundary, but `WritePrecondition` and
`validate_write_precondition` validate only `str | None`. A 256-byte worker ID and lease token are
accepted by both the constructor and guard when the supplied current scalar values match; empty or
host-path-shaped identities are likewise outside the accepted validator.

This probe does not demonstrate a stale-write bypass against a valid `StepRecord`, because such a
record cannot contain the malformed IDs. The finding is therefore P3 contract consistency rather
than a separate P2 CAS failure. Close it with the existing opaque-ID rules and shared negative
cases; do not add a new identity type, error taxonomy or security principal.

## 3. Required review matrix

| Review item | Disposition | Evidence |
| --- | --- | --- |
| Public/persisted/wire separation and opaque job payload | **rework required** | No wire DTO or business-field interpretation was introduced, but F2 narrows the accepted opaque JSON/I-JSON payload grammar. |
| MANUAL/unknown/cancel/supersede ownership | **pass** | MANUAL remains non-terminal and non-claimable; authorized recovery edges exclude CANCELLED/SUPERSEDED. R1 still does not infer Repository effect safety. |
| Stale-writer contract for R2 atomic CAS | **rework required** | Version and lease comparison are deterministic, but F1 leaves the same-status relational composition contract contradictory; F3 leaves its scalar identity budget inconsistent. |
| Parser and bounded budgets; no extra axes | **rework required** | Closed keys, timestamps, aggregate/depth/byte limits and ArtifactRef reuse pass. F2 rejects a valid I-JSON number and F3 omits an accepted identity bound. No digest/evidence/version axis was added. |
| Import direction and public surface | **pass** | The sole package and exact 15-symbol `__all__` remain intact; no capability, infrastructure, Repository, HTTP or deployment dependency was introduced. |
| Tests prove contract barriers proportionally | **rework required** | Shared tables, matrices and pure unit tests are proportionate, but same-status and float cases assert behavior contrary to the accepted owners. |
| Container/dependency/P5/Repository boundary | **pass** | The R1 candidate changes only formal docs, Operations source and focused tests; no lockfile, image, Compose, worker, SQLite, P5 entity or Repository wire path changed. |

## 4. Verification and proportionality

The focused R1 gate passed 381 tests. Backend full ruff/mypy and the other four packages' full
ruff/mypy gates passed. Candidate identity checks show that `1243b1c` is the code/test candidate
immediately sealed by S5 handoff commit `12bc06c`; the latter changes only S4/S5 formal records, so
no unreviewed production or test delta was inherited by S6.

All focused tests are marked `unit` and use pure record/parser/guard logic. They create no Dolt
repository, external process, thread, network dependency, fixed timeout or serial scheduling
constraint. The independent probes target accepted B-class durable-operation boundaries: public
mutation composition, canonical payload admission and caller identity bounds. The findings require
only owner clarification and local validation; they do not justify a broker, sidecar, helper,
durable evidence service or generic state machine.

## 5. Container and benchmark disposition

```text
Current review input HEAD: 12bc06ccb83a6338eb94d97348f3c24eda1b6cff
Reviewed code/test candidate: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
Container rebuild required: no
Reason: R1 and this documentation-only review do not change an image, dependency, deployment, entrypoint, filesystem/UID boundary or container-only runtime behavior
Last verified image revision for this Phase 4 candidate: none found
Last verified source-tree/image id: none
Container gate for current candidate: not-applicable
Required execution point: Phase 4 final production candidate; R1-S7 must retain the provenance disposition
```

Benchmark is `not_applicable`: R1 contains bounded in-process contract/state logic and makes no
throughput or latency claim.

## 6. Authorization and next action

**S6 review task complete; S6 exit is `rework_required`.** F1 and F2 must be closed or explicitly
reopened at their owning contracts before the R1 module gate. The next authorized work is docs-only
finding disposition: define the owning-contract decision and a finding-scoped remediation/re-review
path. Production/test remediation is not authorized by this record alone. P4-R1-S7 and P4-R2-S0
remain unauthorized.
