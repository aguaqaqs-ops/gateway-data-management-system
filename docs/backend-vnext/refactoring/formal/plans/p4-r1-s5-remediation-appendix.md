# P4/R1-S5 Remediation Appendix

状态：**PASS**

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R1-S4 Focused Owner Review](p4-r1-s4-focused-review.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)

```yaml
step_id: P4-R1-S5
input_handoff_sha: 520d6ca9190831b6549261c237593c200bd10e56
input_reviewed_candidate_sha: 0159e15868c7f1510756126e1e6fd2df482659fe
validated_code_sha: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
result: pass
scope_decision: close_findings_without_public_surface_expansion
allowed_paths:
  - vnext/backend/src/gateway_backend/operations/contracts.py
  - vnext/backend/src/gateway_backend/operations/state.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_operation_state.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r1-*.md
forbidden_paths:
  - vnext/backend/src/gateway_backend/operations/__init__.py
  - dependency and deployment files
  - SQLite, worker, HTTP, Repository and P5 implementation
focused_rerun: backend R1 contract/state/architecture unit tests plus focused ruff/mypy
focused_tests: "381 passed"
five_package_static: pass
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
findings: []
next_step: P4-R1-S6
next_step_authorized: yes
```

## Finding remediation matrix

| Finding | Owner | Allowed implementation | Regression proof | Exit condition |
| --- | --- | --- | --- | --- |
| P4-R1-S4-F1: trusted constructors bypass persisted validation | `contracts.py` | Make direct constructors and parsers share strict runtime-version, canonical-payload, tuple-ownership and type validation; preserve the 15-symbol surface. | Shared constructor fault table for runtime version, payload canonicality/budgets, tuple fields, timestamps and uniform `ValueError`; parser round-trip remains unchanged. | No direct `OperationRecord`/`StepRecord` or nested value object can create a record rejected by the accepted persisted contract. |
| P4-R1-S4-F2: aggregate JSON budget mismatch | `contracts.py` | Count every object member and list element with one shared rule; keep depth, byte, key and string limits unchanged. | Boundary cases accept aggregate count 4096 and reject 4097 for scalar lists and object members through both parser and direct construction. | Aggregate budget is enforced identically for object documents and canonical record bytes. |
| P4-R1-S4-F3: same-status mutation-scope guard gap | `contracts.py` / `state.py` | Reuse existing transition guard signatures. Non-final, non-attention same-status candidates run identity, append-only, cancel monotonic, timestamp, lease and version checks; terminal duplicates remain exact-record idempotency only. | Same-status heartbeat/checkpoint/cancel-intent cases; immutable payload/reset rejection; step lease identity and checkpoint cases; MANUAL same-status rejection. | R2 can compose the existing transition guard with `validate_write_precondition` without a new guard/signature or deferred relational invariant. |
| P4-R1-S4-F4: retry rewrites first `started_at` | `state.py` | Permit `started_at` to be established only on the initial claim; require equality thereafter, including retry and authorized MANUAL recovery. | Retry and recovery candidates with changed timestamps are rejected; initial `PENDING -> RUNNING` establishment remains accepted. | No valid transition rewrites the first started timestamp. |
| P4-R1-S4-F5: guard scalar type strictness | `state.py` | Validate exact bool/int types and non-negative I-JSON-safe versions in `WritePrecondition` and public guards; keep `ValueError` as the only rejection taxonomy. | Constructor and guard cases for `True`, non-integer, negative and invalid authorization values. | Python equality/truthiness cannot authorize recovery or satisfy a stale-write version check. |

## Shared exit and reopen rules

S5 closes the findings only if all focused tests and five-package static checks pass, the accepted
status matrix and persisted key sets remain unchanged, and no new public symbol or signature is
introduced. The appendix, updated S4 disposition and S5 handoff must record the validated code
revision and exact command results.

Reopen the owning contract before continuing if remediation requires a new public guard/signature,
changes status or MANUAL attention semantics, changes persisted keys or wire shapes, adds an
external-effect authorization mechanism, or crosses the R1 dependency/deployment boundary.

S6 remains required after S5 because the findings cover persisted validation, lifecycle mutation
rules and the stale-write seam consumed by R2. R1-S7 and R2 remain unauthorized until S6 closes.

The remediation candidate `1243b1cdf736a1c8f3b10446d33753fce9cb9d40` passed the focused unit gate
with 381 tests, backend operations ruff/mypy, all four other package ruff/mypy gates, and
`git diff --check`. No persisted key, status matrix, public symbol or deployment boundary changed.
