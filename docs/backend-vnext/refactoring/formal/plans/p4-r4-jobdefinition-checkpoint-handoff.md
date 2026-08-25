# P4/R4 JobDefinition and Checkpoint Handoff

状态：**PASS — S7 module gate complete; P4-R5-S0 discussion only**

日期：2026-08-25

Owner：Application JobDefinition owner + Operation Runtime

上游：[P4-R4-S6 Independent Review](p4-r4-s6-independent-review.md)、
[P4-R4 JobDefinition and Checkpoint Detailed Execution Plan](p4-r4-jobdefinition-checkpoint-execution-plan.md)、
[P4-R4-S0 Entry Brief](p4-r4-s0-entry-brief.md)

本文是 R4 的最终 module handoff。它封存 S7 当前 HEAD 的 source/test gate、backend image
provenance 和 synthetic worker container smoke；它不授权 R5/P5 implementation 或真实
Repository effect。

```yaml
handoff_kind: p4_r4_jobdefinition_checkpoint
step_id: P4-R4-S7
input_handoff_sha: 89b46ca111f0c240e3011cac7915a9eac6d0d88a
input_validated_code_sha: 9ea535e138a7e498aeade69042bfbbff559fcfc0
validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
validated_source_tree: sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
candidate_worktree_at_gate: clean_committed
result: pass
p4_r4_exit: pass
applicable_steps:
  - P4-R4-S0
  - P4-R4-S1a
  - P4-R4-S1b
  - P4-R4-S2a
  - P4-R4-S2b
  - P4-R4-S3a
  - P4-R4-S3b
  - P4-R4-S3c
  - P4-R4-S4
  - P4-R4-S5
  - P4-R4-S6
  - P4-R4-S7
skipped_steps_with_reason: []
focused_review: pass_after_s5
independent_review: pass_after_s5_remediation
focused_tests: pass_670_deselected_22
backend_unit: pass_1504_deselected_61
integration: pass_30_non_serial_deselected_23
serial: pass_6_deselected_22
five_package_static: pass
container_rebuild_required: yes
container_reason: S2b changed worker bootstrap/composition; S7 rebuilt current HEAD image
last_verified_image_revision: sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b
last_verified_source_tree_image_identity: source_sha=d1d929dcee3b0620b649a248079d846dfbe7aba1; tree_sha256=sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
container_gate: passed
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - R5 retry, takeover, expired-lease disposition and external-effect reconciliation
  - P5 HTTP/global readiness, deployment signal wiring, Compose and global quiescence
  - production Repository/Dolt effect and multi-worker/HA/external DB operation
  - bootstrap default production handler registration beyond test injection
reopen_conditions:
  - Any source/test/build-input change invalidates the recorded candidate or image provenance.
  - Any fix requires R1 record/status/transition or R2 schema/store/CAS/error-taxonomy changes.
  - Any need arises for retry/takeover policy, real Repository effect or deployment/global readiness.
  - Any executor cannot cooperate with cancellation, lease loss or drain before an irreversible effect.
next_step: P4-R5-S0
next_entry: P4-R5-S0 discussion
next_step_authorized: yes_for_discussion_only
r5_implementation_authorized: no
p5_implementation_authorized: no
handoff_documentation_sha: pending_docs_commit
```

## 1. Sealed candidate and public boundary

The final code candidate is commit `d1d929dcee3b0620b649a248079d846dfbe7aba1`. The candidate
contains the R4 application layer (`gateway_backend.application`), bootstrap composition wiring,
synthetic job consumers, checkpoint/READY closure builders, S1a–S6 implementation records and
their focused/integration/serial evidence. The source/test identity was recomputed from every
Python file under `vnext/backend/src` and `vnext/backend/tests`.

The stable R4 public surface is:

```text
gateway_backend.application:
  JobDefinition, JobDefinitionLookupError, JobDefinitionRegistry,
  NormalPublicationCapability, build_worker_registry
gateway_backend.application.job_definitions:
  JobWorkerComposition, build_job_worker_composition,
  validate_active_pairs_job_contract_versions
gateway_backend.application.payloads:
  PayloadDecoder, PayloadDecoderRegistry, PayloadDecodeError,
  CheckpointDecodeError, build_payload_decoder_registry, decode_job_payload,
  load_job_payload_bytes
gateway_backend.application.checkpoints:
  StepCheckpointEnvelope, ReadyClosureDocument, ReadyClosureEntry,
  load_checkpoint_envelope, load_ready_closure, prepare_step_checkpoint,
  prepare_ready_closure, make_checkpoint_step_builder,
  make_terminal_ready_closure_builder
gateway_backend.application.synthetic_jobs:
  pure_compute_* / external_effect_stub_* constants and bundles,
  build_pure_compute_handler, build_external_effect_stub_handler,
  pure_compute_composition_bundle, external_effect_stub_composition_bundle
gateway_backend.application.external_effect_stub:
  ExternalEffectStub, StubOutcome, DeterministicExternalEffectStub
gateway_backend.bootstrap.operation_worker:
  bootstrap_control_database, build_worker_runtime,
  build_job_worker_composition_for_settings, run, main
```

The authoritative process entrypoint remains:

```text
python -m gateway_backend.bootstrap.operation_worker
```

The module entrypoint uses an empty default `JobDefinition` registry; synthetic jobs are injected
through `build_worker_runtime(..., job_definitions=..., handlers=..., payload_decoders=...)`
for tests and bounded container fixtures. Production handler registration remains deferred to
later phases.

## 2. Registry and version matrix

| job_kind | step_name | job_contract_version | decoder identity | handler identity |
| --- | --- | --- | --- | --- |
| `synthetic.pure-compute` | `compute` | `backend-vnext/synthetic/pure-compute/v1` | `backend-vnext/synthetic/pure-compute/decoder/v1` | `backend-vnext/synthetic/pure-compute/handler/v1` |
| `synthetic.external-effect-stub` | `request` | `backend-vnext/synthetic/stub/v1` | `backend-vnext/synthetic/stub/decoder/v1` | `backend-vnext/synthetic/stub/handler/v1` |

Registry lookup is immutable (`mappingproxy`); unknown key or unsupported `job_contract_version`
fail closed at startup preflight and atomic claim. `_R4WorkerStartup` performs version validation
and claim in one write transaction (S5/S6 closure).

## 3. Payload, checkpoint and READY closure

- **Payload axis**: `JOB_PAYLOAD_DOCUMENT_TYPE` with per-decoder version strings; strict decode
  only; no implicit migration.
- **Checkpoint axis**: JCS `StepCheckpointEnvelope` with `STEP_CHECKPOINT_CONTRACT_VERSION`;
  active recovery cursor is `StepRecord.checkpoint_ref`.
- **READY closure**: versioned JCS document with ordered refs, size/digest and job contract
  version; set once on terminal publication after all refs are readable.
- **CAS publication**: artifact write precedes durable CAS; stale CAS does not publish READY.
- **I/O boundary**: decoders and handlers receive injected `ArtifactStorePort`; no DB transaction
  I/O or handler computation inside store transactions.

## 4. Synthetic job contracts

**Pure-compute** (`synthetic.pure-compute`): deterministic output bytes from bounded seed;
terminal `SUCCEEDED` with READY closure over output artifact ref.

**External-effect stub** (`synthetic.external-effect-stub`): test-only deterministic port;
`accepted` retains RUNNING checkpoint; `confirmed` publishes `SUCCEEDED` with READY closure;
`unknown` publishes `MANUAL_RECOVERY_REQUIRED` without READY. Request artifact missing after
checkpoint maps to `CHECKPOINT_REF_UNREADABLE` (S5/S6 closure). Cancel-before-request may
publish `CANCELLED`; cancel-after-request retains R5 handoff boundary.

These consumers prove recovery and publication semantics only; they do not validate production
Repository or Dolt effects.

## 5. Fault and reload evidence

S3c owns the cross-boundary fault matrix in `test_operation_job_recovery.py` and selected
process owners in `test_operation_worker_process.py`. Covered boundaries include duplicate
delivery, crash before/after CAS, stale CAS, corrupt checkpoint, cancel paths, closure
set-once and log redaction. S4–S6 findings F1–F3 and S6-F1/F2 are closed by S5 remediation;
see [p4-r4-s5-remediation-appendix.md](p4-r4-s5-remediation-appendix.md) and
[p4-r4-s6-independent-review.md](p4-r4-s6-independent-review.md).

## 6. Review records

| Step | Document | Disposition |
| --- | --- | --- |
| S4 | [p4-r4-s4-focused-review.md](p4-r4-s4-focused-review.md) | pass after S5 |
| S5 | [p4-r4-s5-handoff.md](p4-r4-s5-handoff.md) | pass; all findings closed |
| S6 | [p4-r4-s6-independent-review.md](p4-r4-s6-independent-review.md) | pass after S5 remediation |

## 7. Gate record

All commands ran against current HEAD `d1d929d` before this handoff documentation commit:

```text
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_contracts.py tests/test_operation_state.py \
  tests/test_operation_store.py tests/test_sqlite_operation_store.py \
  tests/test_job_definition_contracts.py tests/test_job_definition_registry.py \
  tests/test_job_payload_decoding.py tests/test_operation_checkpoint_contracts.py \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_contracts.py tests/test_operation_lease_session.py \
  tests/test_operation_worker_startup.py tests/test_operation_worker_scheduler.py \
  tests/test_operation_worker_lifecycle.py tests/test_architecture.py
  -> 670 passed, 22 deselected in 2.69s

uv run pytest -q -m unit
  -> 1504 passed, 61 deselected, 1 pre-existing Starlette deprecation warning in 49.49s

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_job_synthetic.py tests/test_operation_job_recovery.py \
  tests/test_operation_worker_integration.py tests/test_operation_worker_process.py
  -> 30 passed, 23 deselected in 0.70s

uv run pytest -q -m serial \
  tests/test_operation_job_recovery.py tests/test_operation_worker_process.py
  -> 6 passed, 22 deselected in 2.34s

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
git merge-base --is-ancestor 9ea535e138a7e498aeade69042bfbbff559fcfc0 HEAD
  -> pass
git merge-base --is-ancestor acb3efca06a02aadaa5ce6d1e2a815e85d36e6af HEAD
  -> pass
```

R4 does not run Dolt or Repository Service integration. Benchmark is not applicable.

## 8. Current-HEAD image provenance and container smoke

The first local build attempt without host networking failed to install `uv==0.11.28` in the
runtime stage. The verified gate rebuilt with host networking:

```text
docker build --network host \
  -f vnext/backend/Dockerfile -t p4-r4-d1d929d vnext
  -> successfully built 443216f4a7e0
```

```yaml
build_host: local
image_tag: p4-r4-d1d929d
image_id: sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b
image_digest: p4-r4-d1d929d@sha256:443216f4a7e098abf3cd85a908e571d1236ed0a656913b96598d8bee4488ed5b
image_source_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
image_source_tree_sha256: sha256:76bbf7eef1ac26eb814d5ad5be6a86fec06a6850c42ac7a445b0b2fe93270de6
```

**Authoritative module CLI smoke** used a fresh `mktemp -d` host directory mounted at
`/var/lib/gateway/control`, ran `python -m gateway_backend.bootstrap.operation_worker`,
observed `worker_ready`, sent SIGTERM, and observed `drain_started`, `worker_exited` and exit
code 0.

**Bounded pure-compute fixture** used the same image with `pure_compute_composition_bundle`
injected through `build_worker_runtime` after `worker_ready`, queued one `synthetic.pure-compute`
operation, observed `SUCCEEDED` with `ready_closure_ref` set, then drained cleanly. This proves
the synthetic consumer inside the image; it is not a production effect validation.

**DB reopen** through the image returned:

```text
journal_mode=wal
schema_valid=1
tables=control_schema_migrations,operation_records,step_records
```

Smoke logs contained no configured DB path, lease token, payload body or SQL text. Temporary
control directories were removed after verification.

## 9. Limits and next boundary

R4 is a single-host, single-worker, local SQLite/WAL mechanism with immutable in-process registry
and two test-only synthetic jobs. It proves JobDefinition lookup, payload/checkpoint decoding,
READY closure publication and bootstrap composition; it does not implement retry/takeover,
reconcile production external effects, expose HTTP/global readiness, or support HA/multi-host
operation.

S4–S6 findings are closed, and S7 passed all backend/five-package/image/container gates. The
only next action is **P4-R5-S0 discussion**. That discussion may define retry/takeover and
external-effect recovery policy; it does not authorize R5 implementation, P5 deployment work or
real Repository effects from this handoff alone.
