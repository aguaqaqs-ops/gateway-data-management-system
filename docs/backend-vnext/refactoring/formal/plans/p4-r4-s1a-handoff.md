# P4-R4-S1a Handoff: JobDefinition Contract and Immutable Registry

状态：**PASS — S1a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s1a
step_id: P4-R4-S1a
input_handoff_sha: pending_r4_s0_documentation_commit
input_validated_code_sha: acb3efca06a02aadaa5ce6d1e2a815e85d36e6af
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/__init__.py
  - vnext/backend/src/gateway_backend/application/job_definitions.py
  - vnext/backend/tests/test_job_definition_contracts.py
  - vnext/backend/tests/test_job_definition_registry.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s1a-handoff.md
focused_tests: pass
backend_unit: pass
integration: not_applicable_s1a_no_durable_state_or_process_harness
serial: not_applicable_s1a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: application-owned registry only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s1a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S1b strict payload/checkpoint decoder seams
  - S2a checkpoint/READY closure documents
  - S2b bootstrap composition root and worker entrypoint wiring
  - S3a/S3b synthetic jobs and recovery matrix
reopen_conditions:
  - need for Operations import of application implementation
  - need for mutable/hot-reloaded registry or dynamic script runner
  - need for R3 WorkerRegistry protocol widening or new worker error taxonomy
  - need for R1/R2 schema, CAS, or status contract changes
next_step: P4-R4-S1b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application` now owns the S1a surface:

- frozen `JobDefinition` descriptor binding `JobStepKey`, supported payload versions,
  decoder/handler identity strings, and `NormalPublicationCapability`;
- immutable `JobDefinitionRegistry` with bounded in-memory lookup via `build()`;
- `JobDefinitionLookupError` for unknown key or unsupported `job_contract_version`;
- `build_worker_registry()` adapter mapping handler identities to R3 `ClaimedExecutor`
  without widening the `WorkerRegistry` protocol.

`gateway_backend.operations` does not import application. No payload/checkpoint decoder,
synthetic job handler, bootstrap wiring, production fake executor, second `operation_kind`,
or new operations error taxonomy was introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py \
  tests/test_job_definition_registry.py \
  tests/test_architecture.py
  -> 64 passed

cd vnext/backend && uv run pytest -q -m unit
  -> 1425 passed, 34 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 221 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
```

`git diff --check` passed. Integration, serial, Dolt, container, and benchmark gates were not
applicable to this contract-only step.

## 3. Handoff boundary

S1b is the only next step and remains unauthorized. The validated code is intentionally left in the
working tree because no explicit git commit authorization was provided; the `validated_code_sha`
becomes the candidate code commit SHA once that commit is authorized. This handoff does not
authorize S1b, S2, S3, R5, or P5 implementation.
