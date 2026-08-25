# P4-R4-S2a Handoff: Artifact, Checkpoint and READY Closure Contract

状态：**PASS — S2a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s2a
step_id: P4-R4-S2a
input_handoff_sha: pending_r4_s1b_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/checkpoints.py
  - vnext/backend/tests/test_operation_checkpoint_contracts.py
  - vnext/backend/tests/test_job_payload_decoding.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s2a-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s2a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: checkpoint/closure contract only; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s2a
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S2b bootstrap composition root and worker entrypoint wiring
  - S3a/S3b synthetic jobs and recovery fault matrix
reopen_conditions:
  - need for R1/R2 schema, CAS, or status contract changes
  - need for Operation same-status checkpoint mutation or cleanup/evidence state machine
  - need for Operations import of application checkpoint implementation
  - need for artifact I/O inside DB transactions
next_step: P4-R4-S2b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.checkpoints` now owns the S2a surface:

- versioned JCS `StepCheckpointEnvelope` bound to job/step identity, checkpoint generation,
  `prior_output_refs`, and bounded `job_state` on the independent `step-checkpoint` axis;
- minimal `ReadyClosureDocument` with stable `artifact_id` ordering, redundant size/digest
  entries, `closure_contract_version`, and `job_contract_version`;
- artifact integrity via `verify_artifact_refs`, `put`/`load` helpers on `ArtifactStorePort`,
  and exact-ref idempotency with identity-mismatch fail closed;
- artifact-before-CAS publication seam: `prepare_step_checkpoint` / `prepare_ready_closure`
  perform I/O outside transactions; `make_checkpoint_step_builder` and
  `make_terminal_ready_closure_builder` return pure `LeaseSession` publication callbacks;
- `ready_closure_ref` set-once enforced by existing R1 guards plus builder fail closed when
  already set; stale CAS leaves bounded unreferenced artifacts without R4 cleanup authority.

No bootstrap wiring, synthetic job handlers, R1/R2 schema changes, or Operations import of
application were introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_checkpoint_contracts.py \
  tests/test_job_payload_decoding.py \
  tests/test_architecture.py
  -> 85 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_operation_checkpoint_contracts.py
  -> 2 passed

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 225 source files

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
this checkpoint/closure contract step.

## 3. Handoff boundary

S2b is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided. This handoff does not
authorize S2b, S3, R5, or P5 implementation.
