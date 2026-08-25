# P4-R4-S3a Handoff: Idempotent pure-compute synthetic job

状态：**PASS — S3a implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s3a
step_id: P4-R4-S3a
input_handoff_sha: pending_r4_s2b_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/tests/test_operation_job_synthetic.py
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s3a-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s3a_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: synthetic job handler only; bootstrap composition unchanged
last_verified_image_revision: none_for_s3a
container_gate: deferred_to_s7
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3b external-effect stub synthetic job
  - S3c reload/corruption/duplicate/crash fault matrix
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - need for bootstrap default synthetic registration or worker entrypoint change
  - need for R1/R2 schema, CAS, or status contract changes
  - need for retry/takeover/reconcile policy in R4 handler
next_step: P4-R4-S3b
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.synthetic_jobs` now owns the first R4 synthetic consumer:

- `synthetic.pure-compute` / `compute` JobDefinition with versioned payload decoder and
  terminal publication capability;
- deterministic bounded `seed` input → canonical JCS output artifact and checkpoint
  `job_state` (`output_artifact_id`, `seed`);
- `build_pure_compute_handler()` composing artifact-first checkpoint publication,
  READY closure verification, and R3 `LeaseSession.publish_operation` terminal path;
- cooperative cancel before effect boundary publishes `CANCELLED` without `ready_closure_ref`;
- reload path reads durable `StepRecord.checkpoint_ref`, verifies identity, and preserves
  semantic output digest on duplicate delivery;
- `pure_compute_composition_bundle()` for test/worker injection without bootstrap wiring.

No bootstrap default registration, external-effect stub, retry/takeover, R1/R2 schema changes,
or Operations import of application were introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_job_synthetic.py tests/test_architecture.py
  -> 45 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py
  -> 4 passed

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 228 source files

cd vnext/shared_kernel && uv run ruff check . && uv run mypy
  -> pass; mypy 34 source files
cd vnext/repository_contracts && uv run ruff check . && uv run mypy
  -> pass; mypy 15 source files
cd vnext/repository_client && uv run ruff check . && uv run mypy
  -> pass; mypy 26 source files
cd vnext/repository_service && uv run ruff check . && uv run mypy
  -> pass; mypy 195 source files
```

`git diff --check` passed. Container gate deferred to S7 current-HEAD image rebuild.

## 3. Handoff boundary

S3b is the only next step and remains unauthorized. This handoff does not authorize S3b
implementation, S3c fault matrix, R5, or P5 work.
