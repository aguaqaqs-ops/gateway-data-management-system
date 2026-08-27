# P4-R5-S3c Handoff: Cross-boundary Fault Matrix

状态：**PASS — S3c tests-only matrix validated; candidate commit pending explicit authorization**

日期：2026-08-26

Owner：R5 Operation Runtime + Application Recovery consumer boundaries

上游：[P4-R5-S3b Handoff](p4-r5-s3b-handoff.md)、[P4-R5-S3a Handoff](p4-r5-s3a-handoff.md)、
[P4-R5 Retry, Takeover and Effect Recovery Design](p4-r5-retry-takeover-effect-recovery-design.md)、
[P4-R5 Retry, Takeover and Effect Recovery Detailed Execution Plan](p4-r5-retry-takeover-effect-recovery-execution-plan.md)

```yaml
handoff_kind: p4_r5_s3c
step_id: P4-R5-S3c
input_handoff_sha: 113cb99dc66560b6fd51384033ed31c26c5b580d0a91373512d87780d19cb8d5
input_validated_code_sha: pending_explicit_commit_authorization
validated_code_sha: pending_explicit_commit_authorization
validated_source_tree: pending_explicit_commit_authorization
candidate_code_commit: not_created
candidate_worktree: documented_dirty_candidate_on_s3b_validated_tip
result: pass
changed_paths:
  - vnext/backend/tests/test_operation_job_recovery.py
  - vnext/backend/tests/test_operation_takeover.py
  - vnext/backend/tests/test_operation_recovery_process.py
  - docs/backend-vnext/refactoring/formal/plans/p4-r5-s3c-handoff.md
focused_tests: pass
backend_unit: pass
integration: pass
serial: pass
five_package_static: pass
container_rebuild_required: no
container_reason: tests-only cross-boundary fault matrix; no bootstrap, image, or deployment boundary
last_verified_image_revision: none_for_s3c
container_gate: not_applicable
benchmark: not_applicable_no_performance_claim
findings: []
deferred_items:
  - S4 focused review (mandatory new conversation)
  - S7 current-HEAD container image gate and provenance
reopen_conditions:
  - production handler bug requiring source changes outside S3c allowed paths
  - need for R1/R2 schema, CAS, status or error-taxonomy change
  - need for real Repository client wire or P5 effect paths
next_step: P4-R5-S4
next_step_authorized: no
```

## 1. Delivered boundary

S3c completes the **tests-only** cross-consumer fault matrix. No production source, bootstrap,
or dependency changes were introduced.

R5 S3c fault matrix (one authoritative owner per invariant):

| Fault boundary | Authoritative owner |
|---|---|
| crash | `test_cross_boundary_crash_preserves_durable_state` (`CROSS_BOUNDARY_CRASH_CASES` × 4) |
| response loss | `test_cross_boundary_response_loss_preserves_original_identity` (`RESPONSE_LOSS_HANDLER_SCENARIOS` × 2); stub before-checkpoint also indexed via crash matrix; recovery-port poll indexed to S3b `test_external_effect_recovery_port_accepted_polls_original_identity`; pure-compute N/A |
| lease expiry | `test_operation_takeover`: `test_expired_running_*`, `test_due_retry_wait_*`, `test_concurrent_recovery_*`, `test_live_running_*`; process: `test_process_startup_takeover_*`; S3a `test_pure_compute_lease_takeover_*` (consumer E2E) |
| duplicate | `test_duplicate_delivery_*`, `test_terminal_publication_*`, `test_stub_duplicate_*`; S3a `test_pure_compute_recovery_port_duplicate_*`, `test_pure_compute_retry_does_not_duplicate_*` |
| stale writer | `test_old_lease_token_is_fenced_after_takeover`; `test_operator_command_stale_expected_version_*` |
| corrupt checkpoint | `test_reload_rejects_missing_or_corrupt_*` (`RELOAD_ARTIFACT_FAULTS` × `PAYLOAD_RELOAD_CONSUMERS`); `test_stub_reload_rejects_*` (`STUB_REQUEST_ARTIFACT_FAULTS` × `STUB_RELOAD_OUTCOMES`) |
| retry exhaustion | `test_session_budget_exhaustion_marks_manual_recovery` (`CROSS_BOUNDARY_RETRY_CAPABILITIES` × 2) |
| reconcile timeout | S3b `test_external_effect_recovery_port_reconcile_budget_exhausted`; S2b `test_operation_effect_reconcile` |
| operator action | S2c `test_operator_*` in `test_operation_takeover.py` |

Consolidation changes:

- **Crash**: merged four isomorphic pure/stub tests into one parametrized owner.
- **Response loss**: merged two handler reload scenarios into one parametrized owner with
  `_assert_response_loss_invariants`; stub before-checkpoint response loss shares crash matrix row.
- **Retry exhaustion**: removed duplicate `test_pure_compute_three_session_exhaustion_*` from
  job_recovery; takeover harness owns both `PURE_RECOMPUTE` and `EXTERNAL_EFFECT` capabilities.
- **S3a/S3b consumer RecoveryPort proofs** unchanged; matrix indexes them without duplication.

## 2. Diff review

- `gateway_backend.operations` does not import `gateway_backend.application`.
- No R1/R2 schema, migration, new status, CAS contract or shared error taxonomy change.
- No bootstrap RecoveryPort wiring, no Repository/Dolt effect.
- No second production probe for invariants already owned by S3a or S3b.

## 3. Verification

```text
cd vnext/backend && uv run pytest -q -m unit \
  tests/test_operation_recovery_policy.py \
  tests/test_operation_takeover.py \
  tests/test_operation_effect_reconcile.py \
  tests/test_job_definition_contracts.py \
  tests/test_job_definition_registry.py \
  tests/test_architecture.py
  -> 178 passed, 21 deselected

cd vnext/backend && uv run pytest -q -m unit
  -> 1608 passed, 96 deselected, 1 pre-existing Starlette deprecation warning

cd vnext/backend && uv run pytest -q -m 'integration and not serial' \
  tests/test_operation_effect_reconcile.py \
  tests/test_operation_job_recovery.py
  -> 40 passed, 8 deselected

cd vnext/backend && uv run pytest -q -m serial \
  tests/test_operation_takeover.py \
  tests/test_operation_recovery_process.py
  -> 2 passed, 16 deselected

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
```

Dolt, container and benchmark gates were not applicable to this tests-only matrix step.

## 4. Handoff boundary

S4 focused review is the only next step and remains unauthorized. The validated code is
intentionally left in the working tree because no explicit git commit authorization was provided;
`validated_code_sha` becomes the candidate code commit SHA once that commit is authorized. This
handoff does not authorize S4 review execution, S5 remediation, S6 independent review, S7 module
gate, or P5B/Repository implementation.
