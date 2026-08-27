# P4/R5 Retry, Takeover and Effect Recovery Handoff

状态：**PASS — S7 module gate complete; P4-R6-S0 discussion only**

日期：2026-08-27

Owner：Operation Runtime + Application Recovery owner

上游：[P4-R5-S6 Independent Review](p4-r5-s6-independent-review.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)、
[P4-R5-S0 Entry Brief](p4-r5-s0-entry-brief.md)

本文是 R5 的最终 module handoff。它封存 S7 当前 HEAD 的 source/test gate、backend image
provenance 和 worker container smoke；它不授权 P4-R6 implementation、P5B real Repository
effect 或 P5 deployment work。

```yaml
handoff_kind: p4_r5_retry_takeover_effect_recovery
step_id: P4-R5-S7
input_handoff_sha: 053d0fcb60d9ffcd4d647ed509692ae487438651
input_review_sha: f85c86729b4daed7ce41935bd1c8c0a186715d27
input_validated_code_sha: d1d929dcee3b0620b649a248079d846dfbe7aba1
validated_code_sha: 0fa2b897a75436b4319d4490bc97c54ced494783
validated_source_tree: sha256:911fe38dc274b809abfba320d68ef2e360e8e4ae9e303a6bc54dcfbe71f2ae5c
source_tree_method: sorted_per_file_sha256_records_for_vnext/backend/src_and_tests_python_files
candidate_worktree_at_gate: clean_committed
result: pass
p4_r5_exit: pass
applicable_steps:
  - P4-R5-S0
  - P4-R5-S1a
  - P4-R5-S1b
  - P4-R5-S2a
  - P4-R5-S2b
  - P4-R5-S2c
  - P4-R5-S3a
  - P4-R5-S3b
  - P4-R5-S3c
  - P4-R5-S4
  - P4-R5-S5
  - P4-R5-S6
  - P4-R5-S7
skipped_steps_with_reason: []
focused_review: pass_after_s5
independent_review: pass_after_s5_remediation
focused_tests: pass_184_deselected_27
backend_unit: pass_1615_deselected_105
integration: pass_57_non_serial_deselected_37
serial: pass_8_deselected_52
five_package_static: pass
container_rebuild_required: yes
container_reason: worker/runtime recovery composition touched; S7 rebuilt current HEAD image
last_verified_image_revision: sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95
last_verified_source_tree_image_identity: source_sha=0fa2b897a75436b4319d4490bc97c54ced494783; tree_sha256=sha256:911fe38dc274b809abfba320d68ef2e360e8e4ae9e303a6bc54dcfbe71f2ae5c
container_gate: passed
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - P4-R6 workspace/HTTP/global readiness and deployment coordination
  - P5B real Repository/Dolt external effect and production handler registration
  - HA, multi-worker, external DB and Compose/global quiescence
  - production Repository client wire beyond deterministic stub
reopen_conditions:
  - Any source/test/build-input change invalidates the recorded candidate or image provenance.
  - Any fix requires R1/R2 schema, status, CAS or error-taxonomy change.
  - Any need arises for real Repository effect, new principal/IPC, second registry or generic evidence state machine.
  - Any R3 protocol extension beyond bounded recovery-release (see p4-r5-r3-recovery-release-reopen.md).
next_step: P4-R6-S0
next_entry: P4-R6-S0
next_step_authorized: yes_for_discussion_only
r6_implementation_authorized: no
p5b_real_repository_effect_authorized: no
p5_implementation_authorized: no
handoff_documentation_sha: 91e96c2262529d80504fa5cdc50fdd111f2fe323
```

## 1. Sealed candidate and public boundary

The final code candidate is commit `0fa2b897a75436b4319d4490bc97c54ced494783`. The candidate
contains R5 recovery policy, startup/takeover scheduling, application reconcile adapter, authorized
operator port, synthetic consumer recovery paths, bootstrap composition wiring, S1a–S6 records and
their unit/integration/serial evidence. The source/test identity was recomputed from every Python
file under `vnext/backend/src` and `vnext/backend/tests`; it is independent of ignored caches and
of this docs-only handoff descendant.

The stable R5 public surface is:

```text
gateway_backend.application.recovery:
  RecoveryCapability, RecoveryDecision, RecoveryOutcome, RecoveryPort,
  RecoveryDecisionDisposition, RecoveryOutcomeDisposition,
  ExternalEffectReconcilePhase, ExternalEffectRequestIdentity,
  compute_request_fingerprint, classify_external_effect_phase,
  reconcile_session_budget_exhausted, validate_external_effect_identity
gateway_backend.operations.recovery:
  RecoveryPolicyDecision, RecoveryTransitionIntent, RecoveryPolicyDecisionDisposition,
  RecoveryPolicyOutcomeDisposition, HandlerRecoveryResult, HandlerRecoveryCallback,
  StartupRecovery, OperatorRecoveryCommand, OperatorRecoveryRequest,
  AuthorizedOperatorRecovery, classify_expired_lease, classify_startup,
  classify_cancel, classify_handler_failure, transition_for_decision,
  transition_for_outcome, build_recovery_routed_executor,
  finalize_handler_recovery, build_startup_recovery,
  authorize_operator_command, build_authorized_operator_recovery
gateway_backend.operations.lease_session:
  LeaseSession.publish_recovery_release (bounded R3 reopen)
gateway_backend.operations.worker:
  LeaseSession protocol aligned with publish_recovery_release
gateway_backend.bootstrap.operation_worker:
  build_worker_runtime (recovery-aware registry composition)
```

`RecoveryPort` is an in-process composition port, not an R3 public protocol, HTTP API or persisted
registry. `RecoveryDecision` is read-only policy output; `RecoveryOutcome` is the only application
result R5 accepts for durable mapping. R3 `publish_recovery_release` is the single bounded protocol
widening accepted in [p4-r5-r3-recovery-release-reopen.md](p4-r5-r3-recovery-release-reopen.md).

The authoritative process entrypoint remains:

```text
python -m gateway_backend.bootstrap.operation_worker
```

## 2. Runtime behavior matrix

| Boundary | S7 disposition |
| --- | --- |
| Expired lease | `RUNNING` with expired lease classifies to guarded `RETRY_WAIT` via CAS; next claim establishes new lease and increments attempt; `started_at` preserved; stale token fenced. |
| Retry budget | Three sessions with `1/2/4s` backoff capped at `10s`; exhaustion maps to `MANUAL_RECOVERY_REQUIRED` with occupancy retained. |
| External reconcile | Post-request poll uses original idempotency key, fingerprint and `repository_operation_id`; 60-second reconcile budget; no new key or false READY. |
| Pure recompute | Checkpoint-based recompute; missing output artifact fails closed without recreation. |
| Operator port | Internal `RESUME_RECONCILE`, `RETRY_FROM_CHECKPOINT`, `ABORT_CONFIRMED_FAILURE` with expected version and bounded reason; authorized CAS only. |
| Cancel | Only before irreversible effect boundary; cancel-after-request retains manual recovery boundary. |
| Worker composition | `EXTERNAL_EFFECT` claims with durable checkpoint route through recovery port at claim time; outcomes apply via `publish_recovery_release`. |
| Drain | SIGTERM sets drain intent; idle drain exits cleanly; active drain waits cooperatively; no new claim during drain. |
| Logging | Events contain bounded IDs/categories only; smoke logs redact path, token, payload and SQL text. |

## 3. Fault and reload evidence

S3c owns the cross-boundary fault matrix in `test_operation_job_recovery.py`,
`test_operation_takeover.py` and `test_operation_recovery_process.py`. Covered boundaries include
crash before/after checkpoint and request, response loss, lease expiry, duplicate delivery, stale
writer, corrupt checkpoint, retry exhaustion, reconcile timeout and operator action. S4–S6 findings
F1–F4 are closed by S5 remediation and independent S6 rereview; see
[p4-r5-s5-handoff.md](p4-r5-s5-handoff.md) and
[p4-r5-s6-independent-review.md](p4-r5-s6-independent-review.md).

## 4. Review records

| Step | Document | Disposition |
| --- | --- | --- |
| S4 | [p4-r5-s4-focused-review.md](p4-r5-s4-focused-review.md) | pass after S5 |
| S5 | [p4-r5-s5-handoff.md](p4-r5-s5-handoff.md) | pass; F1–F4 closed |
| S6 | [p4-r5-s6-independent-review.md](p4-r5-s6-independent-review.md) | pass after S5 remediation |

## 5. Gate record

All commands ran against current HEAD `0fa2b89` before this handoff documentation commit:

```text
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_takeover.py \
  tests/test_operation_effect_reconcile.py \
  tests/test_job_definition_contracts.py \
  tests/test_job_definition_registry.py \
  tests/test_architecture.py
  -> 184 passed, 27 deselected in 1.41s

uv run pytest -q -m unit
  -> 1615 passed, 105 deselected, 1 pre-existing Starlette deprecation warning in 52.91s

uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py \
  tests/test_operation_job_synthetic.py \
  tests/test_operation_worker_integration.py \
  tests/test_operation_worker_process.py
  -> 57 passed, 37 deselected in 1.07s

uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py \
  tests/test_operation_job_recovery.py \
  tests/test_operation_worker_process.py
  -> 8 passed, 52 deselected in 2.86s

cd vnext/backend && uv run ruff check . && uv run mypy
  -> pass; mypy 235 source files
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
git merge-base --is-ancestor d1d929dcee3b0620b649a248079d846dfbe7aba1 HEAD
  -> pass
git merge-base --is-ancestor acb3efca06a02aadaa5ce6d1e2a815e85d36e6af HEAD
  -> pass
git merge-base --is-ancestor 9beea4572b5896f2e7268b1c38aa20e54c4ea1a3 HEAD
  -> pass
```

Bounded recovery harness evidence (same HEAD, host integration/process harness):

```text
uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_job_synthetic.py \
  tests/test_operation_worker_integration.py::test_worker_runtime_external_effect_accepted_takeover_polls_original_identity
  -> 2 passed, 16 deselected in 0.41s

uv run pytest -q -m serial \
  tests/test_operation_worker_process.py::test_module_worker_bootstraps_empty_db_and_drains_on_sigterm \
  tests/test_operation_recovery_process.py \
  tests/test_operation_takeover.py
  -> 3 passed, 16 deselected in 1.27s
```

R5 does not run Dolt or Repository Service integration. Benchmark is not applicable.

## 6. Current-HEAD image provenance and container smoke

Local build used host networking (same constraint as R4):

```text
docker build --network host \
  -f vnext/backend/Dockerfile -t p4-r5-0fa2b89 vnext
  -> successfully built a2db693e2e9f
```

```yaml
build_host: DESKTOP-V61T28L
image_tag: p4-r5-0fa2b89
image_id: sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95
image_digest: p4-r5-0fa2b89@sha256:a2db693e2e9f56747532134d819067cf850f1606b34f845460aebb872c6b3d95
image_source_code_sha: 0fa2b897a75436b4319d4490bc97c54ced494783
image_source_tree_sha256: sha256:911fe38dc274b809abfba320d68ef2e360e8e4ae9e303a6bc54dcfbe71f2ae5c
```

**Authoritative module CLI smoke** used a fresh `mktemp -d` host directory mounted at
`/var/lib/gateway/control`, ran `python -m gateway_backend.bootstrap.operation_worker`,
observed `worker_ready`, sent SIGTERM, and observed `drain_started`, `worker_exited` and exit
code 0. No `RuntimeWarning` or runpy duplicate-load warning.

**DB reopen** through the mounted control directory returned:

```text
journal_mode=wal
tables=control_schema_migrations,operation_records,step_records
```

Smoke logs contained no lease token, payload body or SQL text. Temporary control directory and
container were removed after verification.

## 7. Limits and next boundary

R5 is a single-host, single-worker, local SQLite/WAL mechanism with deterministic stub external
effects and in-process recovery ports. It proves retry/takeover scheduling, original-identity
reconcile, authorized operator CAS, pure-compute recompute and bootstrap composition; it does not
implement real Repository/Dolt effects, HTTP/global readiness, Compose deployment coordination,
HA/multi-host operation or production handler registration.

S4–S6 findings are closed, and S7 passed all backend/five-package/image/container gates. The only
next action is **P4-R6-S0 discussion**. That discussion may define workspace/HTTP/global readiness
boundaries; it does not authorize R6 implementation, P5B real Repository effects or P5 deployment
work from this handoff alone.
