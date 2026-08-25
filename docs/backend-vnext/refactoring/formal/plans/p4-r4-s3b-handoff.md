# P4-R4-S3b Handoff: Deterministic external-effect stub synthetic job

状态：**PASS — S3b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s3b
step_id: P4-R4-S3b
input_handoff_sha: pending_r4_s3a_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/external_effect_stub.py
  - vnext/backend/src/gateway_backend/application/synthetic_jobs.py
  - vnext/backend/tests/test_operation_job_synthetic.py
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s3b-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: not_applicable_s3b_no_fixed_time_or_process_boundary
five_package_static: pass
container_rebuild_required: no
container_reason: stub handler and test-only port only; bootstrap composition unchanged
last_verified_image_revision: none_for_s3b
container_gate: deferred_to_s7
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3c reload/corruption/duplicate/crash fault matrix
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - need for bootstrap default synthetic registration or worker entrypoint change
  - need for R1/R2 schema, CAS, or status contract changes
  - need for retry/takeover/reconcile policy in R4 handler
next_step: P4-R4-S3c
next_step_authorized: no
```

## 1. Delivered boundary

R4 now owns a test-only external-effect stub synthetic consumer alongside S3a pure-compute:

- `gateway_backend.application.external_effect_stub` — bounded request JCS, deterministic
  `operation_identity`, `StubOutcome` (`accepted` / `confirmed` / `unknown`), ABC port and
  `RecordingExternalEffectStub` for blind-replay contract tests; no network, Dolt, or production
  fault control;
- `synthetic.external-effect-stub` / `request` JobDefinition with versioned payload decoder and
  terminal publication capability;
- `build_external_effect_stub_handler()` — request artifact + checkpoint durable identity before
  outcome branch; cancel-before-request → `CANCELLED` without identity; cancel-after-request
  retains checkpoint/identity; `accepted` → `SAFE_HANDOFF` with RUNNING step; `confirmed` → READY
  closure + `SUCCEEDED` + `repository_operation_id`; `unknown` → `MANUAL_RECOVERY_REQUIRED` with
  bounded diagnostic (not FAILED/CANCELLED);
- reload path restores checkpoint `job_state` without resubmitting to stub (no blind replay, no
  second idempotency key);
- `external_effect_stub_composition_bundle()` for test/worker injection without bootstrap wiring.

No bootstrap default registration, retry/takeover/reconcile, R1/R2 schema changes, or Operations
import of application were introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_job_synthetic.py tests/test_architecture.py
  -> 52 passed

cd vnext/backend && uv run pytest -q -m integration \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py
  -> 9 passed

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
```

`git diff --check` not run (no commit requested). Container gate deferred to S7 current-HEAD image
rebuild.

## 3. Handoff boundary

S3c is the only next step and remains unauthorized. This handoff does not authorize S3c fault
matrix implementation, R5, or P5 work.
