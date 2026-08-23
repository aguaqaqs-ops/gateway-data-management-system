# P4/R1 Runtime Contract and State Handoff

状态：**PASS**（S7 module gate；R2-S0 entry discussion）

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4/R1-S6 Remediation Handoff](p4-r1-s6-remediation-handoff.md)、[P4/R1-S6 Finding Disposition](p4-r1-s6-finding-disposition.md)、[P4/R1-S6 Risk-based Independent Review](p4-r1-s6-independent-review.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)

```yaml
handoff_kind: p4_r1
step_id: P4-R1-S7
input_handoff_sha: cb5ca31cc51ad06f3c226bab9a0c7db0494a3204
validated_code_sha: e2703407a1c80d31f6888ce86c0ab9b125464ad5
validated_code_tree_identity: vnext_source_and_tests_match_e270340
candidate_worktree_at_gate: clean_committed_on_e270340
p4_r1_exit: pass
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
skipped_steps_with_reason: []
focused_review: pass_after_s5
independent_review: pass_after_s6_remediation
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
  - SQLite/WAL atomic CAS remains R2-owned and is not implemented in R1.
  - External-effect cancel/fail/supersede authorization remains R5/JobDefinition-owned.
  - Worker lifecycle, deployment wiring and real Repository effects remain outside R1.
reopen_conditions:
  - Any remediation changes the public surface, persisted keys, status matrix or MANUAL attention semantics.
  - Any remediation changes Shared Kernel numeric semantics, payload wire shape or introduces a new digest/version axis.
  - Any remediation adds an identity type/security principal or crosses the R1 dependency, SQLite, worker, Repository or deployment boundary.
remediation_handoff: p4-r1-s6-remediation-handoff.md
next_step: P4-R2-S0 entry acceptance discussion
next_entry: P4-R2-S0
next_step_authorized: yes
p4_r2_authorized: no
handoff_documentation_sha: pending_handoff_documentation_commit
```

## 1. Module gate identity

The final S7 gate ran against clean candidate `e270340`. Its Operations source and tests are the
finding-scoped remediation of S6-F2/F3, independently rechecked in
[P4/R1-S6 Remediation Handoff](p4-r1-s6-remediation-handoff.md). The candidate preserves the
accepted public surface, persisted keys, status matrix, MANUAL attention semantics and R1 boundary.

The S6 docs-only disposition closed the F1 owner ambiguity: the existing transition guards own
same-status mutation validation without adding a status-matrix self-loop. The remediation handoff
closes F2 and F3 after code/test gates and independent boundary probes.

## 2. Gate results

| Check | Result |
| --- | --- |
| focused R1 unit gate | **PASS**; 398 passed in 2.39s |
| backend unit gate | **PASS**; 1226 passed, 1 Starlette deprecation warning in 48.30s |
| backend `uv run ruff check .` | **PASS** |
| backend `uv run mypy` | **PASS**; 193 source files |
| shared_kernel ruff/mypy | **PASS**; 34 source files |
| repository_contracts ruff/mypy | **PASS**; 15 source files |
| repository_client ruff/mypy | **PASS**; 26 source files |
| repository_service ruff/mypy | **PASS**; 195 source files |
| `git diff --check` | **PASS** |
| Operations source/test tree identity against `e270340` | **PASS** |

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
git diff 6d227e7..e270340 -- vnext
```

The full backend unit run has one pre-existing Starlette deprecation warning. No R1 test uses Dolt,
an external process, network I/O, a fixed timeout or serial scheduling; `integration` and `serial`
gates are therefore not applicable.

## 3. Boundary and authorization decision

The R1 source/test module gate and S6 remediation review are green. Accordingly this handoff records
`p4_r1_exit: pass` and authorizes the R2-S0 entry acceptance discussion. It does not authorize
SQLite/WAL CAS, worker implementation, Repository effects, P5, or deployment work.

The next permitted action is the R2-S0 entry acceptance discussion. R2 must retain the required CAS
composition: transition guard plus `validate_write_precondition`; it may not treat R1's先读后验 as
the persistence implementation.

Container rebuild is not applicable to this R1 candidate: no Dockerfile, dependency lock, Compose,
entrypoint, UID/GID, mount, socket, pidfile, broker/helper or container-only runtime boundary was
changed. No image revision is claimed. Benchmark is not applicable because R1 contains only bounded
in-process contract/state logic and makes no performance claim.
