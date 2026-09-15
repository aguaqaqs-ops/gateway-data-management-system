# P5-5B-S3 Import Builder and Artifact Boundary Handoff

状态：**S3 delivery complete — pending independent review**

日期：2026-09-15

Owner：P5-5B Delivery

## Authority gate snapshot

```yaml
p4_r6_exit: pass
p5_5b_design: accepted
p5_5b_implementation_authorized: yes
p5b_real_repository_effect_authorized: yes
unresolved_contract_drift: none
s2_closure: pass
s3_entry: authorized
```

## Traceability

```yaml
stage: P5-5B-S3-import-builder-artifact-boundary
parent_head: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
candidate_head: 669f1ca00845c8ef2e82beb55c0063acf3951017
input_authority:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-execution-plan.md §S3
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s2-final-independent-review.md
scope_paths:
  - vnext/backend/src/gateway_backend/application/submission/import_builder.py
  - vnext/backend/src/gateway_backend/application/submission/contracts.py
  - vnext/backend/src/gateway_backend/repository_import_artifact.py
  - vnext/backend/src/gateway_backend/artifacts/**
  - vnext/backend/tests/test_submit_import_builder.py
  - vnext/backend/tests/test_repository_import_artifact_package.py
  - vnext/backend/tests/test_submit_artifact_protection.py
  - vnext/backend/tests/test_artifact_boundary.py
changed_paths:
  - vnext/backend/src/gateway_backend/artifacts/nominal_refs.py
  - vnext/backend/src/gateway_backend/artifacts/__init__.py
  - vnext/backend/src/gateway_backend/application/submission/contracts.py
  - vnext/backend/src/gateway_backend/application/submission/import_builder.py
  - vnext/backend/src/gateway_backend/repository_import_artifact.py
  - vnext/backend/tests/test_submit_import_builder.py
  - vnext/backend/tests/test_submit_artifact_protection.py
  - vnext/backend/tests/test_artifact_boundary.py
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-handoff.md
uv_lock_in_diff: no
```

## Invariants delivered

```yaml
invariants_delivered:
  - REBUILD_ALWAYS-only prepare import publication via SubmitImportPublicationPort
  - manifest-first then package-second publication order (SubmitImportPublicationAdapter)
  - one durable package identity: checkpoint reuse read-back preserves BackendArtifactRef + raw SHA
  - pre-checkpoint orphan bytes do not change published manifest digest or package raw SHA
  - BackendArtifactRef / RepositoryArtifactRef nominal conversion boundary in artifacts/nominal_refs.py
  - import_builder.py depends only on ports + artifacts + domain (no capabilities import)
  - pin transfer preview→attempt and terminal promote/clear helpers (application layer)
  - no Repository Service wire calls in S3 scope
unique_test_owners:
  - tests/test_submit_import_builder.py
  - tests/test_submit_artifact_protection.py
  - tests/test_artifact_boundary.py  # nominal ref negative matrix (reopen cases retained)
  - tests/test_repository_import_artifact_package.py  # existing formal v1 bytes/shape owner
```

## Evidence matrix

### Published ref / raw SHA reuse

| Owner test | Assertion |
| --- | --- |
| `test_rebuild_always_publish_is_deterministic_for_same_inputs` | Same inputs → identical manifest digest + package raw SHA + BackendArtifactRef |
| `test_checkpoint_reuse_read_back_preserves_package_identity` | After checkpoint, `reuse_prepare_import_checkpoint` read-back matches ref and SHA; no rebuild |

### Pre-checkpoint orphan boundary

| Owner test | Assertion |
| --- | --- |
| `test_orphan_bytes_before_checkpoint_do_not_change_published_identity` | Extra unreferenced store puts before first publish do not alter manifest digest or package identity |
| `test_reuse_rejects_mismatched_input_closure_digest` | Checkpoint reuse fail-closed on closure digest mismatch |

### Nominal type negative matrix

| Owner test | Assertion |
| --- | --- |
| `test_backend_and_repository_refs_are_distinct_nominal_types` | Backend/Repository refs are separate nominal types |
| `test_store_ref_round_trip_preserves_backend_identity` | ArtifactRef ↔ BackendArtifactRef round-trip |
| `test_nominal_ref_cross_type_substitution_is_rejected` | Parameterized cross-type substitution faults rejected |
| `test_artifact_boundary.py` reopen cases | Existing canonical row hash reopen owner retained (P3 history) |

### Pin transfer / release

| Owner test | Assertion |
| --- | --- |
| `test_transfer_preview_protection_to_attempt_moves_exact_refs` | Preview pins cleared; submit-attempt holds exact snapshot/closure refs |
| `test_accept_transaction_transfers_preview_pins_to_attempt` | T1 accept harness: preview pins move to attempt |
| `test_finalize_promotes_source_and_manifest_pins` | T3 finalize: attempt snapshot pins cleared; source-package + canonicalization-manifest intents |
| `test_abort_clears_attempt_pins_without_promotion` | Abort clears attempt pins; no promote |

## Explicit non-deliverables

- **No generic refcount/GC** or second canonical owner introduced.
- `accept_transaction.py` / `finalize_transaction.py` **not modified**; S5 wires S3 helpers.
- No `prepare_import` JobDefinition handler, HTTP routes, or Repository upload-import wire.
- No `capabilities/**`, `test_architecture.py`, lockfile, or Repository package changes.

## Verification record

```bash
cd vnext/backend
uv run pytest -q -m unit \
  tests/test_submit_import_builder.py \
  tests/test_repository_import_artifact_package.py \
  tests/test_submit_artifact_protection.py \
  tests/test_artifact_boundary.py
# 37 passed

uv run ruff check src/gateway_backend/application/submission \
  src/gateway_backend/repository_import_artifact.py \
  src/gateway_backend/artifacts \
  tests/test_submit_import_builder.py tests/test_submit_artifact_protection.py
# All checks passed

uv run mypy
# Success: no issues found in 337 source files
```

```yaml
focused_commands_and_results:
  - cd vnext/backend && uv run pytest -q -m unit tests/test_submit_import_builder.py tests/test_repository_import_artifact_package.py tests/test_submit_artifact_protection.py tests/test_artifact_boundary.py => 37 passed
  - cd vnext/backend && uv run ruff check src/gateway_backend/application/submission src/gateway_backend/repository_import_artifact.py src/gateway_backend/artifacts tests/test_submit_import_builder.py tests/test_submit_artifact_protection.py => pass
  - cd vnext/backend && uv run mypy => pass (337 source files)
five_package_static: deferred
authoritative_runner: deferred
container_rebuild_required: no
container_reason: S3 is application/artifact adapter logic only; no Dockerfile, Compose, entrypoint, or deployment boundary touched
last_verified_image_revision: not_applicable
container_gate_for_current_head: not_applicable
findings: []
deferred:
  - accept/finalize transaction wiring to import_builder helpers (S5)
  - prepare_import JobDefinition handler and HTTP (S4/S5)
  - Repository Service upload-import wire (S5)
reopen_required: []
implementation_authority_unchanged: true
next_step: P5-5B-S4
```

## Notes

- `SubmitImportPublicationAdapter` in `repository_import_artifact.py` orchestrates projection → REBUILD_ALWAYS planner → `_dolt_renderer.render_change_set_replay` → `publish_canonicalization`, then converts store `ArtifactRef` to `BackendArtifactRef` via `artifacts/nominal_refs.py`.
- `PrepareImportBuildInput.ruleset_version` is the table-rules **string** version (`TableRulesetSnapshot.ruleset_version`), distinct from `table_ruleset_version` int.
- `import_builder.publish_prepare_import_package` is the application entry; tests also exercise adapter `build_and_publish_from_inputs` where direct `ProjectionTableInput` injection is required.
