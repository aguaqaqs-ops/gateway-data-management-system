# P4-R4-S1b Handoff: Payload and Versioned Decoder Boundary

状态：**PASS — S1b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s1b
step_id: P4-R4-S1b
input_handoff_sha: pending_r4_s1a_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/job_definitions.py
  - vnext/backend/src/gateway_backend/application/payloads.py
  - vnext/backend/tests/test_job_definition_contracts.py
  - vnext/backend/tests/test_job_payload_decoding.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s1b-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s1b_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: payload decoder seam only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s1b
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2a checkpoint/READY closure documents and checkpoint envelope decoder
  - S2b bootstrap composition root and worker entrypoint wiring
  - S3a/S3b synthetic jobs and recovery matrix
reopen_conditions:
  - need for Operations import of application payload decoder implementation
  - need for implicit payload migration or decoder I/O inside DB transactions
  - need for R1/R2 schema, CAS, or status contract changes
next_step: P4-R4-S2a
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.payloads` now owns the S1b surface:

- strict inline/ref payload loading via injected `ArtifactStorePort.locate` with exact ref,
  size, and raw digest verification;
- R1 bounded canonical JSON validation reused from `operations.contracts` private helpers
  without widening Operations public API;
- identity-axis checks for `job_kind`, `job_contract_version`, and `JOB_PAYLOAD_DOCUMENT_TYPE`
  before registered typed decoder invocation;
- immutable `PayloadDecoderRegistry` and `build_payload_decoder_registry()` aligned to
  `JobDefinition.decoder_identity`;
- owner-bounded `PayloadDecodeError` and independent-axis `CheckpointDecodeError` /
  `CHECKPOINT_DOCUMENT_TYPE` placeholder for S2a;
- typed decoder outputs constrained to re-encodable bounded documents, `ArtifactRef`, or
  frozen dataclass instances.

`JobDefinitionRegistry` now rejects duplicate `decoder_identity` and exposes
`decoder_identities()`. `gateway_backend.operations` does not import application. No checkpoint
envelope, synthetic job handler, bootstrap wiring, or new operations error taxonomy was introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py \
  tests/test_job_payload_decoding.py \
  tests/test_architecture.py
  -> 76 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_job_payload_decoding.py
  -> 4 passed

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 223 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
```

`git diff --check` passed. Serial, Dolt, container, and benchmark gates were not applicable to
this decoder-boundary step.

## 3. Handoff boundary

S2a is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided. This handoff does not
authorize S2a, S2b, S3, R5, or P5 implementation.
