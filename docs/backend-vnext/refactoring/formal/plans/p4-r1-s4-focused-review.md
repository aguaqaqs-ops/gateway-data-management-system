# P4/R1-S4 Focused Owner Review

状态：**PASS AFTER S5 REMEDIATION**

日期：2026-08-23

Reviewer：Operation Runtime focused owner review

上游：[P4-R1-S3b Handoff](p4-r1-s3b-handoff.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)、[Operation Lifecycle and Integrity](../contracts/operation-lifecycle-and-integrity.md)、[External Effect and Recovery](../contracts/external-effect-and-recovery.md)、[Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)

```yaml
step_id: P4-R1-S4
input_handoff_sha: 0159e15868c7f1510756126e1e6fd2df482659fe
reviewed_candidate_sha: 0159e15868c7f1510756126e1e6fd2df482659fe
validated_code_sha: 23c62a80ba22b990231e90d66e13e710e19bce34
candidate_worktree_at_entry: clean
result: pass_after_s5
s5_validated_code_sha: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
s5_result: pass
open_findings: []
finding_disposition: all_closed_in_s5
changed_paths:
  - docs/backend-vnext/refactoring/formal/plans/p4-r1-s4-focused-review.md
commands_and_results:
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py -> 354 passed"
  - "cd vnext/backend && uv run ruff check src/gateway_backend/operations tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py -> pass"
  - "cd vnext/backend && uv run ruff check . && uv run mypy -> pass"
  - "other four Python packages: uv run ruff check . && uv run mypy -> pass"
  - "targeted constructor/parser/state/precondition probes -> reproduced F1-F5"
  - "git diff --name-status a2da77f..0159e15; git diff --check -> allowed R1 paths only; pass"
focused_tests: pass_after_s5
five_package_static: pass
container_gate: not_applicable_r1_no_image_or_deployment_boundary_change
benchmark: not_applicable_contract_state_only
findings: []
historical_findings:
  - P4-R1-S4-F1: P2 trusted-constructor validation bypass
  - P4-R1-S4-F2: P2 inline JSON aggregate budget mismatch
  - P4-R1-S4-F3: P2 same-status mutation-scope guard gap
  - P4-R1-S4-F4: P2 first-started-at mutation accepted
  - P4-R1-S4-F5: P3 guard scalar type strictness
s5: pass
s6: required_after_s5
deferred_items:
  - SQLite/WAL atomic CAS remains R2-owned and is not implemented in R1.
  - External-effect cancel/fail/supersede authorization remains R5/JobDefinition-owned.
reopen_conditions:
  - F3 requires a new public guard or changes an accepted public signature instead of closing through the existing R1 surface.
  - Remediation changes persisted keys, status matrices, MANUAL attention semantics, or external-effect ownership.
next_step: P4-R1-S6
next_step_authorized: yes
```

## 1. Review disposition

The pre-remediation candidate preserved the intended package, owner and dependency boundaries, and
its current focused/static gates passed. It did not pass the owner review because the five findings
listed below admitted states or mutations outside the accepted R1 contract. The original focused
suite was therefore regression evidence for the implemented paths, not closure evidence for S4.

At the time of this original review, S5 was required and had to begin with the remediation appendix
required by the execution plan. S5 has now closed the findings. S6 remains required because the
findings touched persisted schema validation, lifecycle mutation rules and the stale-write seam
used by R2. S4 did not itself authorize production or test remediation.

## 2. Findings

### P4-R1-S4-F1 — P2: direct constructors bypass persisted contract validation

Owner：`gateway_backend.operations.contracts`

The parser produces validated records, but direct dataclass construction does not enforce the same
contract. Replacing an otherwise valid `OperationRecord` demonstrated all of the following:

- `contract_version="backend-vnext/operation-runtime/v2"` is accepted because constructors check
  only printable syntax, while parsers require the exact runtime version;
- non-canonical `job_payload=b'{"b":1,"a":2}'` is accepted and retained even though record storage
  is required to be canonical JCS bytes for a JSON object;
- `business_refs` accepts and retains a caller-owned mutable `list` despite the exact tuple field
  contract. The same container-type gap applies to tuple-valued artifact fields;
- several constructor validators rely on annotated runtime types rather than rejecting wrong types
  uniformly with `ValueError`.

This contradicts detailed plan §2.4's explicit rule that every dataclass constructor and parser
share validation and cannot create a trusted-constructor bypass. Invalid semantic records could be
handed to the R2 persistence owner without passing the closed document parser.

Required S5 proof：module-level constructor fault table covering exact runtime version, canonical
object payload and all accepted payload budgets, exact immutable tuple ownership, strict timestamp
types, and uniform `ValueError`; parser round-trip behavior must remain unchanged.

### P4-R1-S4-F2 — P2: aggregate member/element budget is not enforced

Owner：`gateway_backend.operations.contracts`

`_validate_json_structure` increments its aggregate counter for nested `dict`/`list` containers,
not for each member or element. A payload containing `{"items": [0] * 4097}` is accepted and
round-trips, although §2.6 freezes an aggregate member/element maximum of 4096. The 64 KiB byte cap
still bounds total memory, but it does not satisfy the accepted independent structural budget.

Required S5 proof：shared malformed payload cases for scalar list elements and object members at the
4096 boundary, with a single documented counting rule used by parser and direct constructor.

### P4-R1-S4-F3 — P2: same-status mutation path cannot enforce accepted mutation scope

Owner：Operation Runtime contract/state; R2 is the first consumer

Detailed plan §2.7 routes heartbeat, checkpoint and cancel-intent same-status writes through record
invariants plus `validate_write_precondition`, while deliberately rejecting non-terminal same-state
calls to the transition guards. Those two routed checks are not relational: two individually valid
`QUEUED` records can change immutable `job_payload` and reset `cancel_requested` from true to false,
yet the documented write-precondition path succeeds because it checks only version and lease
identity.

The existing relational checks for immutable envelope, append-only refs and monotonic cancel intent
are private helpers reached only by status-changing transition guards. R2 therefore has no existing
public R1 guard that proves the full accepted mutation scope for same-status CAS writes. Narrow R2
methods could independently constrain updated columns, but that responsibility is not stated by the
accepted R1 contract and would make §2.7's claimed guard composition incomplete.

Required S5 disposition：either close this gap without expanding the frozen public surface and add
heartbeat/checkpoint/cancel-intent regression coverage, or explicitly reopen the owning contract and
public-surface decision before introducing a new guard/signature. Do not silently defer the
relational invariant to R2.

### P4-R1-S4-F4 — P2: retry transitions can rewrite the first start timestamp

Owner：`gateway_backend.operations.state`

Detailed plan §2.5 requires retry attempts to retain the first `started_at`. A valid
`RETRY_WAIT -> RUNNING` candidate with a different, still well-ordered `started_at` currently returns
`TransitionDisposition.APPLY`. The transition guard checks step identity, attempt count and lease,
but does not keep `started_at` immutable after the initial `PENDING -> RUNNING` claim.

Required S5 proof：allow `started_at` to be established exactly once on the initial claim, require it
to remain equal on every later transition (including retry and authorized MANUAL recovery), and add
matrix-adjacent regression cases.

### P4-R1-S4-F5 — P3: guard scalar types use Python equality/truthiness

Owner：`gateway_backend.operations.state`

Two malformed typed calls are accepted at runtime: `recovery_authorized=1` authorizes a MANUAL
recovery edge, and `WritePrecondition(expected_optimistic_version=True, ...)` matches current version
`1`. Mypy protects checked internal callers, so this is not treated as a distinct authorization or
stale-write P2 in the single-service trust domain. It is nevertheless inconsistent with the strict
bool/non-negative I-JSON integer contract used elsewhere and makes public guard rejection less
predictable.

Required S5 proof：exact bool/integer validation and constructor/guard negative cases, without adding
an error taxonomy or a new authorization mechanism.

## 3. Required S4 review matrix

| Review item | Disposition | Evidence |
| --- | --- | --- |
| Public/persisted/wire separation and opaque job payload | **rework required** | No wire DTO or job-field interpretation was introduced, but F1 lets direct records bypass the accepted persisted form. |
| MANUAL/unknown/cancel/supersede ownership | **rework required** | Matrices and attention predicates match the accepted snapshot; F3/F4 leave relational lifecycle mutations incomplete and F5 weakens strict recovery input typing. |
| Stale-writer contract for R2 atomic CAS | **rework required** | Version plus worker/lease matching is present and deterministic; F3 shows it is insufficient for the documented same-status mutation composition. |
| Parser and bounded budgets; no extra axes | **rework required** | Closed keys, size/depth/key/string caps and ArtifactRef reuse are present; F1/F2 violate constructor and aggregate closure. No digest/evidence/version axis was added. |
| Import direction and public surface | **pass** | Sole `gateway_backend.operations` package, exact 15-symbol `__all__`, no `operation_kind`, and only shared-kernel/public artifact serialization dependencies. |
| Tests prove contract barriers proportionally | **rework required** | Tests use shared tables and avoid process/time dependencies, but omit the accepted boundaries reproduced by F1-F5. |
| Container/dependency/P5/Repository boundary | **pass** | R1 lineage changes only allowed formal docs, operations source and focused tests; no lockfile, Docker/Compose, worker, SQLite, P5 entity or Repository wire change. |

## 4. Verification and proportionality

The focused unit gate passed 354 tests in 1.60 seconds. Focused operations/architecture ruff,
backend full ruff/mypy and the other four packages' full ruff/mypy all passed. The probes for F1-F5
were read-only executions against the reviewed candidate; no regression tests or production fixes
were added during S4.

The test inventory remains proportionate: pure parser/state logic uses unit tests, shared malformed
tables and generated transition matrices, with no Dolt, process, thread, wall-clock or fixed-timeout
dependency. The finding disposition asks only for the missing semantic barriers; it does not add a
generic evidence system, a second version axis or an external security principal.

## 5. Container and benchmark disposition

```text
Current reviewed HEAD: 0159e15868c7f1510756126e1e6fd2df482659fe
Container rebuild required: no
Reason: the reviewed R1 lineage contains pure Python contract/state code, tests and formal docs only; no image, dependency, deployment or container-only runtime boundary changed
Last verified image revision: none found for this Phase 4 candidate
Last verified source-tree/image id: none
Container gate for current HEAD: not-applicable
Deferred gates/nodeids: none for R1; the final Phase 4 production candidate must still rebuild and verify its own image provenance
Required execution point: Phase 4 final candidate / production gate
```

Benchmark is `not_applicable`: R1 defines bounded contract/state logic and no performance baseline,
external process, queue or storage implementation.

## 6. S5/S6 and next-step authorization

- `S5: pass`. Its first change was the finding-scoped remediation appendix naming owner, allowed
  paths, regression tests, focused rerun and exit for F1-F5.
- `S6: required_after_s5`. F1/F2 affect persisted schema validation and F3/F4 affect lifecycle and
  stale-write semantics, which directly meet the plan's independent-review trigger.
- The only authorized next step is `P4-R1-S6`. R1-S7 and R2 entry remain unauthorized until S6
  disposition is closed.

## 7. S5 remediation disposition

S5 was executed from this review on clean candidate `520d6ca9190831b6549261c237593c200bd10e56`.
The first change was the finding-scoped [S5 remediation appendix](p4-r1-s5-remediation-appendix.md).
The validated remediation candidate is `1243b1cdf736a1c8f3b10446d33753fce9cb9d40`.

| Finding | S5 disposition | Evidence |
| --- | --- | --- |
| F1 | closed | Direct constructors now enforce exact runtime version, canonical payload bytes, tuple ownership, strict timestamp/type checks and `ValueError`; shared constructor fault cases pass. |
| F2 | closed | JSON aggregate validation counts object members and list elements; 4096 aggregate cases pass and 4097 cases fail through parser and direct construction. |
| F3 | closed | Existing transition guards now validate non-final same-status mutation scope; heartbeat/checkpoint/cancel cases and immutable/reset/MANUAL rejection cases pass without public-surface expansion. |
| F4 | closed | `started_at` is established only on the initial claim and is immutable across retry and authorized recovery. |
| F5 | closed | `WritePrecondition` and public guards reject bool/non-integer versions and non-bool recovery authorization with `ValueError`. |

S5 focused tests passed (`381 passed`); backend focused ruff/mypy, all five-package static gates and
`git diff --check` passed. The original findings above remain as the S4 evidence record; they are
closed here, with no open P1/P2 finding. S6 remains required independently, and its only authorized
next step is `P4-R1-S6`.
