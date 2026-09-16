# P5-5B-S3 Remediation Round 2 Handoff (Review-3)

状态：**remediation complete — S3 final candidate `d093caf9`**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority

```yaml
baseline_commit: 33c14a92
remediation_commit: 2881e747
candidate_head: d093caf919d36631e99e832b7227fe5a4ec5ac9f
input_review:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-3.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-4.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-5.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-6.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-7.md
prior_remediation:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-remediation-handoff.md
implementation_authority_unchanged: true
```

## Finding closure (Review-3)

| Finding | Closure |
| --- | --- |
| S3-H1 / P1 | `SubmitImportPublicationAdapter` reopens snapshot readers after `project_storage` (`_reopen_projection_inputs`); materialize path closes reopened readers in `finally`. `test_build_and_publish_from_pinned_parquet_artifact_succeeds` covers real Parquet `ARTIFACTS_REQUIRED` → `build_and_publish`. `FakeSnapshotTableReader` fails closed on closed `descriptor`/`iter_rows`. |
| S3-H2 / P2 | Import replay split restores DAG: `storage_projection.import_replay` owns schema DDL + `build_import_projection_snapshots`; `mutation_planning.import_replay` owns `build_import_mutation_snapshots` + public `render_import_mutation_dml`. Removed `_dolt_renderer` re-export from `mutation_planning.__init__`. `test_architecture.py` 3/3 pass. |
| S3-H3 / P1 | `PrepareImportCheckpoint.canonicalization_manifest_digest` restored (semantic). `SubmitImportPublicationPort.verify_checkpoint_semantic_binding` validates manifest semantic digest + package `canonicalization_manifest_digest` binding. `reuse_prepare_import_checkpoint` calls port verify. Negative mismatch test added. |
| S3-H4 / P2 | `_assert_projection_identity` no longer equates `repository_base_digest` to `manifest.source_artifact_digest`; only `source_artifact_digest` checked. `test_repository_base_digest_may_differ_from_source_artifact_digest` added. |
| S3-H5 / P2 | `test_manifest_digest_is_independent_of_table_input_order` second `project_storage` call uses `reader.reopen()` for swapped table order; `FakeSnapshotTableReader` closed contract unchanged. Full unit suite green. |
| S3-J1 / P2 | `render_import_mutation_dml` accepts `repository_base_digest`; consumer passes `build_input.repository_base_digest` to `MutationRepositoryBase`. `test_repository_base_digest_reaches_mutation_planner` captures planner request. |
| S3-J2 / P2 | `_dolt_renderer` renamed to `_repository_replay_renderer`; public `render_import_mutation_dml` exported from `mutation_planning`. Consumer no longer imports `_dolt_renderer` or `storage_projection._digest`; manifest verify uses `open_canonicalization_manifest().manifest_digest`. Owner tests import public API only. |
| S3-J3 / P2 | Handoff binds final candidate/remediation SHAs; focused command lists all 10 owner files (131 passed); baseline evidence marked historical; five-package static provenance recorded. |
| S3-J4 / P2 | Main handoff records round-1 (`8618b21a..33c14a92`) + round-2/3 remediation paths and union `8618b21a..d093caf9`; final invariants/non-deliverables distinguish baseline vs remediation capability scope; S3 protection owner is `test_pin_prepare_import_artifacts_extends_attempt_protection` only. |

### Corrected prior claims

| Prior | Correction |
| --- | --- |
| S3-R8 (round 1) | `repository_base_digest` equality to projection manifest was incorrect; removed in H4. Field retained for S5 wiring. |
| S3-R9 (round 1) | Raw manifest SHA reuse check alone was insufficient; H3 restores semantic digest + package binding. |

## Changed paths

```text
vnext/backend/src/gateway_backend/capabilities/storage_projection/contracts.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/__init__.py
vnext/backend/src/gateway_backend/capabilities/mutation_planning/import_replay.py (new)
vnext/backend/src/gateway_backend/capabilities/mutation_planning/__init__.py
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/src/gateway_backend/application/submission/contracts.py
vnext/backend/src/gateway_backend/application/submission/import_builder.py
vnext/backend/tests/test_submit_import_builder.py
vnext/backend/tests/test_storage_projection_import_replay.py
vnext/backend/tests/test_mutation_planning_import_replay.py (new)
vnext/backend/tests/support/storage_projection.py
vnext/backend/tests/test_storage_projection_integrity.py
vnext/backend/src/gateway_backend/capabilities/mutation_planning/_repository_replay_renderer.py (renamed)
vnext/backend/tests/test_dolt_renderer.py
vnext/backend/tests/support/mutation_contracts.py
docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-remediation-round2-handoff.md
```

## Verification record

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_architecture.py \
  tests/test_submit_import_builder.py \
  tests/test_mutation_planning_import_replay.py \
  tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py \
  tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py \
  tests/test_canonical_lock_identity.py \
  tests/test_storage_projection_integrity.py \
  tests/test_dolt_renderer.py
# 131 passed

./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit
# 1916 passed, 115 deselected, 68.92s

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync ruff check .
# pass

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync mypy
# 341 source files pass
```

```yaml
uv_lock_in_diff: no
five_package_static: pass (provenance p5-5b-s3-independent-review-6; Backend 341, Shared Kernel 34, Repository Contracts 15, Repository Client 26, Repository Service 198 source files)
container_rebuild_required: no
container_reason: Python/tests/docs only; no image or deployment boundary touched
next_step: independent S3 review-6 traceability confirmation / S3 stage pass sign-off
```

## Notes

- `test_architecture.py` allowlist unchanged; DAG and mutation_planning leaf token rules not relaxed.
- `accept_transaction.py` / `finalize_transaction.py` untouched per plan scope.
