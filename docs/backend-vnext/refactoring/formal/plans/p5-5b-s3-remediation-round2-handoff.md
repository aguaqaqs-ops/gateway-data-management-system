# P5-5B-S3 Remediation Round 2 Handoff (Review-3)

状态：**remediation complete — pending review-4 light re-confirmation**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority

```yaml
baseline_commit: 33c14a92
remediation_commit: pending
input_review:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-3.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-4.md
prior_remediation:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-remediation-handoff.md
implementation_authority_unchanged: true
```

## Finding closure (Review-3)

| Finding | Closure |
| --- | --- |
| S3-H1 / P1 | `SubmitImportPublicationAdapter` reopens snapshot readers after `project_storage` (`_reopen_projection_inputs`); materialize path closes reopened readers in `finally`. `test_build_and_publish_from_pinned_parquet_artifact_succeeds` covers real Parquet `ARTIFACTS_REQUIRED` → `build_and_publish`. `FakeSnapshotTableReader` fails closed on closed `descriptor`/`iter_rows`. |
| S3-H2 / P2 | Import replay split restores DAG: `storage_projection.import_replay` owns schema DDL + `build_import_projection_snapshots`; `mutation_planning.import_replay` owns `build_import_mutation_snapshots` (contracts-only upstream). DML orchestration lives in `repository_import_artifact._render_import_mutation_dml`. Removed `_dolt_renderer` re-export from `mutation_planning.__init__`. `test_architecture.py` 3/3 pass. |
| S3-H3 / P1 | `PrepareImportCheckpoint.canonicalization_manifest_digest` restored (semantic). `SubmitImportPublicationPort.verify_checkpoint_semantic_binding` validates manifest semantic digest + package `canonicalization_manifest_digest` binding. `reuse_prepare_import_checkpoint` calls port verify. Negative mismatch test added. |
| S3-H4 / P2 | `_assert_projection_identity` no longer equates `repository_base_digest` to `manifest.source_artifact_digest`; only `source_artifact_digest` checked. `test_repository_base_digest_may_differ_from_source_artifact_digest` added. |
| S3-H5 / P2 | `test_manifest_digest_is_independent_of_table_input_order` second `project_storage` call uses `reader.reopen()` for swapped table order; `FakeSnapshotTableReader` closed contract unchanged. Full unit suite green. |

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
  tests/test_canonical_lock_identity.py
# 95 passed (includes integrity owner after H5 fix)

./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit
# 1915 passed, 115 deselected, 68.41s

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync ruff check .
# pass

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync mypy
# 341 source files pass
```

```yaml
uv_lock_in_diff: no
five_package_static: backend-only (ruff + mypy full package)
container_rebuild_required: no
container_reason: Python/tests/docs only; no image or deployment boundary touched
next_step: independent S3 review-4 light re-confirmation
```

## Notes

- `test_architecture.py` allowlist unchanged; DAG and mutation_planning leaf token rules not relaxed.
- `accept_transaction.py` / `finalize_transaction.py` untouched per plan scope.
