# P4/R1 Runtime Contract and State Handoff

状态：**REWORK REQUIRED**（S7 module gate；S6-F2/F3 remediation pending）

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R1-S6 Finding Disposition](p4-r1-s6-finding-disposition.md)、[P4/R1-S6 Risk-based Independent Review](p4-r1-s6-independent-review.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)

```yaml
handoff_kind: p4_r1
step_id: P4-R1-S7
input_handoff_sha: 82b9b517fdd80b57a30c6f9ca750815f52b2be5a
validated_code_sha: 1243b1cdf736a1c8f3b10446d33753fce9cb9d40
validated_code_tree_identity: vnext_source_and_tests_match_validated_code_sha
candidate_worktree_at_gate: clean
p4_r1_exit: rework_required
applicable_steps:
  - P4-R1-S0
  - P4-R1-S1a
  - P4-R1-S1b
  - P4-R1-S2a
  - P4-R1-S2b
  - P4-R1-S3a
  - P4-R1-S3b
  - P4-R1-S4
  - P4-R1-S5
  - P4-R1-S6
  - P4-R1-S7
skipped_steps_with_reason:
  - step: P4-R1-S6 conditional remediation and independent re-review
    reason: S6-F2 and S6-F3 remain open; separate production/test remediation authorization has not been granted
focused_review: pass_after_s5
independent_review: rework_required_f2_f3_pending
focused_tests: pass
backend_unit: pass
five_package_static: pass
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
public_symbols:
  - OPERATION_RUNTIME_CONTRACT_VERSION
  - BusinessReference
  - JobStepKey
  - OperationDiagnostic
  - OperationRecord
  - OperationStatus
  - StepRecord
  - StepStatus
  - TransitionDisposition
  - WritePrecondition
  - operation_record_from_document
  - step_record_from_document
  - validate_operation_transition
  - validate_step_transition
  - validate_write_precondition
contract_version: backend-vnext/operation-runtime/v1
status_semantics: accepted_status_matrix_with_MANUAL_RECOVERY_REQUIRED_as_nonterminal_attention_state
deferred_items:
  - S6-F2 P2 finite binary64 inline payload acceptance remains unimplemented.
  - S6-F3 P3 WritePrecondition worker/lease opaque-ID bounds remain unimplemented.
  - SQLite/WAL atomic CAS remains R2-owned and is not implemented in R1.
  - External-effect cancel/fail/supersede authorization remains R5/JobDefinition-owned.
  - Worker lifecycle, deployment wiring and real Repository effects remain outside R1.
reopen_conditions:
  - Any remediation changes the public surface, persisted keys, status matrix or MANUAL attention semantics.
  - Any remediation changes Shared Kernel numeric semantics, payload wire shape or introduces a new digest/version axis.
  - Any remediation adds an identity type/security principal or crosses the R1 dependency, SQLite, worker, Repository or deployment boundary.
next_step: P4-R1-S6 conditional F2/F3 remediation after explicit authorization
next_entry: none
next_step_authorized: no
p4_r2_authorized: no
handoff_documentation_sha: pending_handoff_documentation_commit
```

## 1. Module gate identity

The S7 gate ran against the clean documentation candidate at `82b9b51`. Its Operations source and
tests are byte-for-byte unchanged from the validated code/test candidate `1243b1c`; the latter is
the `validated_code_sha` recorded above. S7 adds no production or test change and does not replace
the earlier S6 independent-review conclusion.

The S6 docs-only disposition closed the F1 owner ambiguity: the existing transition guards own
same-status mutation validation without adding a status-matrix self-loop. F2 and F3 remain open
until separately authorized code/test remediation and an independent S6 re-review.

## 2. Gate results

| Check | Result |
| --- | --- |
| focused R1 unit gate | **PASS**; 381 passed in 1.83s |
| backend unit gate | **PASS**; 1209 passed, 1 Starlette deprecation warning in 49.71s |
| backend `uv run ruff check .` | **PASS** |
| backend `uv run mypy` | **PASS**; 193 source files |
| shared_kernel ruff/mypy | **PASS**; 34 source files |
| repository_contracts ruff/mypy | **PASS**; 15 source files |
| repository_client ruff/mypy | **PASS**; 26 source files |
| repository_service ruff/mypy | **PASS**; 195 source files |
| `git diff --check` | **PASS** |
| Operations source/test tree identity against `1243b1c` | **PASS** |

Commands:

```text
cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_operation_state.py tests/test_architecture.py
cd vnext/backend && uv run pytest -q -m unit
cd vnext/backend && uv run ruff check .
cd vnext/backend && uv run mypy
cd vnext/shared_kernel && uv run ruff check . && uv run mypy
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
cd vnext/repository_client && uv run ruff check . && uv run mypy
cd vnext/repository_service && uv run ruff check . && uv run mypy
git diff --check
git diff 1243b1c..82b9b51 -- vnext
```

The full backend unit run has one pre-existing Starlette deprecation warning. No R1 test uses Dolt,
an external process, network I/O, a fixed timeout or serial scheduling; `integration` and `serial`
gates are therefore not applicable.

## 3. Boundary and authorization decision

The R1 source/test module gate is green, but the module contract is not closed because S6-F2 and
S6-F3 remain remediation findings. Accordingly this handoff records `p4_r1_exit: rework_required`.
It does not authorize R2-S0, SQLite/WAL CAS, worker implementation, Repository effects, P5, or
deployment work.

The next permitted action is a separately authorized, finding-scoped remediation of F2 and F3:
accept finite binary64 values supported by Shared Kernel JCS/I-JSON, reuse the existing opaque-ID
validator for precondition identities, add the required shared regression cases, rerun the focused
and five-package static gates, and obtain an independent S6 re-review. No remediation is performed
by this handoff.

Container rebuild is not applicable to this R1 candidate: no Dockerfile, dependency lock, Compose,
entrypoint, UID/GID, mount, socket, pidfile, broker/helper or container-only runtime boundary was
changed. No image revision is claimed. Benchmark is not applicable because R1 contains only bounded
in-process contract/state logic and makes no performance claim.
