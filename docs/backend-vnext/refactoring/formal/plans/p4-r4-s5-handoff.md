# P4-R4-S5 Handoff: Finding-scoped remediation

状态：**PASS — S4 P2 and S6 P1/P2 findings closed; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s5
step_id: P4-R4-S5
input_handoff_sha: pending_r4_s6_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/checkpoints.py
  - vnext/backend/src/gateway_backend/application/job_definitions.py
  - vnext/backend/src/gateway_backend/application/payloads.py
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/tests/test_operation_checkpoint_contracts.py
  - vnext/backend/tests/test_job_definition_registry.py
  - vnext/backend/tests/test_job_payload_decoding.py
  - vnext/backend/tests/test_operation_job_synthetic.py
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s5-remediation-appendix.md
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s5-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: application and bootstrap claim boundary only; no image or deployment boundary change in this round
last_verified_image_revision: none_for_s5_s6_round
container_gate: deferred_to_s7
benchmark: not_applicable_no_performance_claim
findings:
  - id: P4-R4-S4-F1
    status: closed
    fix: canonicalize_jcs + byte equality in checkpoint/closure from_canonical_bytes
  - id: P4-R4-S4-F2
    status: closed
    fix: MappingProxyType deep-freeze on registry lookup maps
  - id: P4-R4-S4-F3
    status: closed
    fix: synthetic handlers use load_job_payload_bytes + typed decoders
  - id: P4-R4-S6-F1
    status: closed
    fix: recovery locates existing request ref only; no put_with_built_ref on reload
  - id: P4-R4-S6-F2
    status: closed
    fix: job_contract_version validation and claim in one write transaction
deferred_items:
  - S6 independent re-review (mandatory new conversation)
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - R1/R2 schema or evidence mechanism change for checkpoint/closure bytes
  - durable registry, watcher, or R3 protocol widening
  - cleanup broker, evidence state machine, or R5 policy for missing request artifacts
next_step: P4-R4-S6
next_step_authorized: no
```

## 1. Delivered boundary

S5 closes S4 P2 findings (F1–F3) and S6 P1/P2 findings (F1–F2) with finding-scoped production
and regression changes only. No R1/R2 schema, R5 policy, or Dockerfile changes in this round.

| Finding | Fix | Regression owner |
|---|---|---|
| S4-F1 canonical/duplicate JSON | `_parse_canonical_document_bytes` in `checkpoints.py` | `CANONICAL_DOCUMENT_BYTE_FAULTS` |
| S4-F2 registry deep-freeze | `MappingProxyType` on lookup maps | registry/payload mutation probes |
| S4-F3 synthetic payload_ref | `load_job_payload_bytes` in handlers | `PAYLOAD_BINDING_PARITY` |
| S6-F1 missing request artifact | locate-only in `_request_state_from_job_state` | `STUB_REQUEST_ARTIFACT_FAULTS` × reload outcomes |
| S6-F2 claim/version TOCTOU | atomic `_R4WorkerStartup.claim_one` | `test_unsupported_job_contract_version_rejected_at_claim_without_running_lease` |

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py \
  tests/test_architecture.py
  -> 143 passed

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 36 passed

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py tests/test_operation_worker_process.py \
  tests/test_operation_worker_integration.py
  -> 8 passed

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 229 source files

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
```

Container gate remains deferred to S7 current-HEAD image rebuild.

## 3. Handoff boundary

S6 independent re-review is the only next step and remains unauthorized. This handoff does not
authorize S6 review execution, S7 module gate, R5, or P5 work.
