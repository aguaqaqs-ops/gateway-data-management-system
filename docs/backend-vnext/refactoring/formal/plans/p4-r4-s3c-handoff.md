# P4-R4-S3c Handoff: Cross-boundary reload and fault matrix

状态：**PASS — S3c tests-only matrix validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s3c
step_id: P4-R4-S3c
input_handoff_sha: pending_r4_s3b_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_operation_worker_process.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s3c-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: tests-only fault matrix; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s3c
container_gate: deferred_to_s7
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S4 focused review (mandatory new conversation)
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - production handler bug requiring source changes outside S3c allowed paths
  - need for R1/R2 schema, CAS, or status contract changes
  - need for retry/takeover/reconcile policy in R4 handler
next_step: P4-R4-S4
next_step_authorized: no
```

## 1. Delivered boundary

S3c completes the cross-consumer reload/fault matrix as **tests-only** evidence. No production
source, bootstrap, or dependency changes were introduced.

Fault matrix ownership:

| Boundary | Authoritative owner |
|---|---|
| payload reload | `test_cross_boundary_payload_reload_resolves_version_and_semantic_input` |
| checkpoint round-trip | `test_operation_checkpoint_contracts` (S2a); reload completion in recovery |
| artifact missing/corrupt | `test_reload_rejects_missing_or_corrupt_checkpoint_without_ready` |
| closure set-once | `test_ready_closure_ref_set_once_rejects_second_publication` (integration); S2a unit |
| duplicate delivery | `test_duplicate_delivery_*`, `test_terminal_publication_is_idempotent_on_duplicate` |
| cancel before request | `test_operation_job_synthetic` (S3b) |
| cancel after request/unknown | `test_operation_job_synthetic` + `test_stub_unknown_reload_does_not_resubmit` |
| crash before/after CAS | pure/stub recovery tests; process SIGKILL in `test_operation_worker_process` |
| stale CAS | `test_stale_cas_after_closure_artifact_put_leaves_no_ready_closure_ref` |

Process/crash tests prove durable readback only. Expired RUNNING lease timestamps are not R5
takeover or reconciliation.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m integration \
  tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py
  -> 24 passed

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py \
  tests/test_operation_worker_process.py
  -> 6 passed

cd vnext/backend && uv run pytest -q -m unit tests/test_architecture.py
  -> 40 passed

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

S4 focused review is the only next step and remains unauthorized. This handoff does not authorize
S4 review execution, S5 remediation, S6 independent review, S7 module gate, R5, or P5 work.
