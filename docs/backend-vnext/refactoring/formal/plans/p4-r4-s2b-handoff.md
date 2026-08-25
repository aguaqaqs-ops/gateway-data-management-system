# P4-R4-S2b Handoff: Registry Composition and Executor Adapter

状态：**PASS — S2b implementation validated; candidate commit pending explicit authorization**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

```yaml
handoff_kind: p4_r4_s2b
step_id: P4-R4-S2b
input_handoff_sha: pending_r4_s2a_documentation_commit
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
result: pass
changed_paths:
  - vnext/backend/src/gateway_backend/application/job_definitions.py
  - vnext/backend/src/gateway_backend/bootstrap/operation_worker.py
  - vnext/backend/tests/test_job_definition_registry.py
  - vnext/backend/tests/test_operation_worker_integration.py
  - vnext/backend/tests/test_architecture.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r4-s2b-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: yes
container_reason: worker bootstrap/composition boundary now wires R4 registry, artifact store, and version-aware startup
last_verified_image_revision: none_for_s2b
container_gate: deferred
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S3a pure-compute synthetic job handlers
  - S3b external-effect stub synthetic job
  - S3c reload/corruption/duplicate/crash fault matrix
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - need for Operations import of application implementation
  - need for worker_startup.py protocol widening or R3 lifecycle policy change
  - need for OperationWorkerSettings artifact env or R1/R2 schema changes
next_step: P4-R4-S3a
next_step_authorized: no
```

## 1. Delivered boundary

`gateway_backend.application.job_definitions` now owns the S2b composition surface:

- `JobWorkerComposition` binding `JobDefinitionRegistry`, `PayloadDecoderRegistry`,
  R3 `WorkerRegistry` adapter, and injected `ArtifactStorePort`;
- `build_job_worker_composition()` wrapping handlers with bounded payload decode before
  inner `ClaimedExecutor` invocation;
- `validate_active_pairs_job_contract_versions()` for startup/claim preflight on
  `job_contract_version`.

`gateway_backend.bootstrap.operation_worker` is the composition root:

- replaces `EmptyWorkerRegistry` with `build_job_worker_composition_for_settings()`;
- derives artifact root as `{control_db_parent}/artifacts` via `LocalArtifactStore`;
- `_R4WorkerStartup` extends topology validation and claim preflight with version checks;
- `build_worker_runtime()` accepts optional test injection for definitions/handlers/decoders;
- logs remain bounded; `PayloadDecodeError` maps to `payload_decode_failed`.

`gateway_backend.operations` does not import application. No synthetic job business logic,
R1/R2 schema changes, second executor, hot reload, or R3 lifecycle policy changes were
introduced.

## 2. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_job_definition_registry.py \
  tests/test_architecture.py
  -> 57 passed

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 4 passed, 8 deselected

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_worker_process.py
  -> 6 passed

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

`git diff --check` passed. Container gate deferred to S7 current-HEAD image rebuild.

## 3. Handoff boundary

S3a is the only next step and remains unauthorized. The validated code is intentionally left in
the working tree because no explicit git commit authorization was provided. This handoff does not
authorize S3a, S3b, S3c, R5, or P5 implementation.
