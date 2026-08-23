# P4/R1-S1b Handoff: Closed Document Contract

状态：**PASS**

日期：2026-08-23

Owner：Operation Runtime (`gateway_backend.operations`)

上游：[P4-R1-S1a Handoff](p4-r1-s1a-handoff.md)、[P4-R1 Runtime Contract and State Detailed Execution Plan](p4-r1-runtime-contract-state-execution-plan.md)

```yaml
step_id: P4-R1-S1b
input_handoff_sha: 7b57097ef25011147deb5b10e59641ae767bce80
validated_code_sha: 8d0a8aa91f37ffa331a7aae59d2c54c780ca3f3a
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/operations/contracts.py
  - vnext/backend/src/gateway_backend/operations/__init__.py
  - vnext/backend/tests/test_operation_contracts.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/contracts/operation-lifecycle-and-integrity.md
commands_and_results:
  - "cd vnext/backend && uv run pytest -q -m unit tests/test_operation_contracts.py tests/test_architecture.py -> 61 passed"
  - "cd vnext/backend && uv run ruff check src/gateway_backend/operations tests/test_operation_contracts.py tests/test_architecture.py -> pass"
  - "cd vnext/backend && uv run mypy -> pass"
  - "five-package ruff/mypy -> pass"
  - "git diff --check -> pass"
focused_tests: pass
five_package_static: pass
container_gate: not_applicable_r1_no_runtime_boundary_change
benchmark: not_applicable_contract_state_only
normative_contract_anchor: operation-lifecycle-and-integrity.md#6
accepted_document_schema: operation/step closed documents per plan §2.4
parser_limits: plan §2.6 bounded defaults
public_exports:
  - OPERATION_RUNTIME_CONTRACT_VERSION
  - BusinessReference
  - JobStepKey
  - OperationDiagnostic
  - OperationRecord
  - OperationStatus
  - StepRecord
  - StepStatus
  - operation_record_from_document
  - step_record_from_document
findings: []
deferred_items:
  - S2a status cross-field invariants and enum predicates
  - S2b transition guards, WritePrecondition, state.py
reopen_conditions:
  - runtime interprets job payload business fields
  - duplicate ArtifactRef contract or relaxed parser
  - capability/infrastructure/Repository imports required
next_step: P4-R1-S2a
next_step_authorized: yes
```

## 1. Delivered surface

S1b adds closed persisted document support:

- `BusinessReference`, `OperationDiagnostic`
- `OperationRecord`, `StepRecord` with `to_document()`
- `operation_record_from_document`, `step_record_from_document`
- Shared field-level validators for budgets, UTC timestamps, payload/ref exclusivity,
  JCS inline payload bytes, host-path rejection, and duplicate artifact identity

Status-specific cross-field lifecycle invariants remain deferred to S2a. Transition guards
remain deferred to S2b.

## 2. Normative contract

[operation-lifecycle-and-integrity.md](../contracts/operation-lifecycle-and-integrity.md) §6
now owns the Phase 4 operation runtime contract snapshot.

## 3. Verification applicability

Container rebuild and benchmark are not applicable: no image, deployment, or runtime boundary
changed.
