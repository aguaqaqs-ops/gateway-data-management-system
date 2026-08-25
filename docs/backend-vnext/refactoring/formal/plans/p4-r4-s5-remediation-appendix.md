# P4-R4-S5 Remediation Appendix

状态：**AUTHORIZED — finding-scoped remediation for S4 P2 and S6 P1/P2 findings**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

上游：[P4-R4-S4 Focused Review](p4-r4-s4-focused-review.md)、[P4-R4-S6 Independent Review](p4-r4-s6-independent-review.md)

## Finding P4-R4-S4-F1

- **Severity:** P2
- **Owner:** `application.checkpoints`
- **Allowed paths:**
  - `vnext/backend/src/gateway_backend/application/checkpoints.py`
  - `vnext/backend/tests/test_operation_checkpoint_contracts.py`
- **Required fix:** Reject non-canonical JSON bytes and duplicate top-level keys in
  `StepCheckpointEnvelope.from_canonical_bytes` and `ReadyClosureDocument.from_canonical_bytes`
  via `canonicalize_jcs` + byte equality gate before semantic parse.
- **Regression:** `CANONICAL_DOCUMENT_BYTE_FAULTS` parameterized unit owner covering both decoder axes.
- **Closure:** S4 counterexamples for non-canonical and duplicate-key checkpoint/closure bytes fail closed.
- **Reopen if:** R1/R2 schema change or new evidence mechanism required.

## Finding P4-R4-S4-F2

- **Severity:** P2
- **Owner:** `application.job_definitions` / `application.payloads`
- **Allowed paths:**
  - `vnext/backend/src/gateway_backend/application/job_definitions.py`
  - `vnext/backend/src/gateway_backend/application/payloads.py`
  - `vnext/backend/tests/test_job_definition_registry.py`
  - `vnext/backend/tests/test_job_payload_decoding.py`
- **Required fix:** Deep-freeze registry lookup maps with `types.MappingProxyType` at build time for
  `JobDefinitionRegistry`, `PayloadDecoderRegistry`, and worker executor adapter.
- **Regression:** Mutation attempts on `_by_key`, `_executors`, `_decoders` raise `TypeError`; lookup unchanged.
- **Closure:** Post-build map mutation cannot alter resolver behavior.
- **Reopen if:** Durable registry, watcher, or R3 protocol widening required.

## Finding P4-R4-S4-F3

- **Severity:** P2
- **Owner:** `application.synthetic_jobs`
- **Allowed paths:**
  - `vnext/backend/src/gateway_backend/application/synthetic_jobs.py`
  - `vnext/backend/tests/test_operation_job_synthetic.py`
- **Required fix:** Synthetic handlers load payload through shared `load_job_payload_bytes` + typed
  decoders instead of inline-only `_load_*_payload` helpers.
- **Regression:** `PAYLOAD_BINDING_PARITY` for pure-compute and external-effect-stub inline vs ref.
- **Closure:** Valid `job_payload_ref` operations produce identical semantic output/identity as inline.
- **Reopen if:** Second decoder, payload contract extension, or bootstrap wiring required.

## Finding P4-R4-S6-F1

- **Severity:** P1
- **Owner:** `application.synthetic_jobs` / ArtifactStore boundary
- **Allowed paths:**
  - `vnext/backend/src/gateway_backend/application/synthetic_jobs.py`
  - `vnext/backend/tests/test_operation_job_recovery.py`
- **Required fix:** Recovery path in `_request_state_from_job_state` must locate and verify the
  existing exact request ref only; must not call `put_with_built_ref` when the checkpoint references
  a durable request artifact.
- **Regression:** `STUB_REQUEST_ARTIFACT_FAULTS` parameterized owner for confirmed, unknown, and
  accepted stub reload paths; missing/corrupt request artifact raises bounded diagnostic and leaves
  no READY closure.
- **Closure:** Deleted or corrupt request bytes cannot be recreated during recovery and must not
  produce false terminal success.
- **Reopen if:** Cleanup broker, evidence state machine, or R5 policy required.

## Finding P4-R4-S6-F2

- **Severity:** P2
- **Owner:** `bootstrap.operation_worker` claim/version gate
- **Allowed paths:**
  - `vnext/backend/src/gateway_backend/bootstrap/operation_worker.py`
  - `vnext/backend/tests/test_operation_worker_integration.py`
- **Required fix:** Close the TOCTOU between `validate_active_pairs_job_contract_versions` and claim
  by performing version validation and `OperationLifecycleActions.claim_one` in one write transaction.
- **Regression:** Post-READY insertion of registered key with unsupported `job_contract_version`
  raises before RUNNING lease; operation/step remain QUEUED/PENDING.
- **Closure:** Unsupported version cannot receive RUNNING lease via claim-time race.
- **Reopen if:** R3 protocol widening or second registry required.

## Verification (all findings)

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_job_definition_contracts.py tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py \
  tests/test_architecture.py
uv run pytest -q -m 'integration and not serial' \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py tests/test_operation_worker_process.py \
  tests/test_operation_worker_integration.py
uv run ruff check . && uv run mypy
```

Five-package `ruff/mypy` and `git diff --check` required before S5 handoff. Container gate remains
`deferred_to_s7`; S6 re-review required after closure.
