# P5-5B-S3 Remediation Handoff

> **Superseded.** 当前权威 remediation 记录为 [p5-5b-s3-remediation-round2-handoff.md](p5-5b-s3-remediation-round2-handoff.md)（final candidate `d093caf9`）。本文保留首轮 remediation 历史证据。

状态：**superseded — round-1 remediation @ `33c14a92`**

日期：2026-09-16

Owner：P5-5B Delivery

## Authority

```yaml
baseline_commit: 8618b21a
remediation_commit: 33c14a92
input_reviews:
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review.md
  - docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-independent-review-2.md
implementation_authority_unchanged: true
```

## Finding closure

| Finding | Closure |
| --- | --- |
| S3-R1 / F1 | `storage_projection.import_replay.render_repository_import_replay_sql` emits `DROP TABLE IF EXISTS` + `CREATE TABLE` + planner DML; consumer no longer fabricates empty before manifest |
| S3-R2 / F2 | `materialize_canonical_source_rows` + `build_import_mutation_snapshots` use owner projection path (ordered pseudo-gid allocation) |
| S3-R3 / F3 | `vnext/backend/uv.lock` restored to canonical PyPI identity @ baseline; tests via `uv-consume.sh --no-sync` |
| S3-R4 / F4 | Snapshots built only for `projection.manifest.tables`; skipped tables omitted |
| S3-R5 / F5 | Owner `_mutation_cell` maps SET/ENUM to replay-safe string cells |
| S3-R6 | `plan_storage_mutation` called without `artifact_store` — no happy-path change-set-closure orphan |
| S3-R7 | Removed duplicate `transfer/promote/clear` helpers from `import_builder.py`; owner test is `pin_prepare_import_artifacts` only |
| S3-R8 | `_assert_projection_identity` validates `source_artifact_digest` / `repository_base_digest` against manifest |
| S3-R9 | `PrepareImportCheckpoint.canonicalization_manifest_ref` is `BackendArtifactRef`; reuse read-back verifies manifest bytes |

## Changed paths

```text
vnext/backend/src/gateway_backend/capabilities/storage_projection/import_replay.py (new)
vnext/backend/src/gateway_backend/capabilities/storage_projection/project.py
vnext/backend/src/gateway_backend/capabilities/storage_projection/__init__.py
vnext/backend/src/gateway_backend/capabilities/mutation_planning/__init__.py
vnext/backend/src/gateway_backend/repository_import_artifact.py
vnext/backend/src/gateway_backend/application/submission/contracts.py
vnext/backend/src/gateway_backend/application/submission/import_builder.py
vnext/backend/tests/test_submit_import_builder.py
vnext/backend/tests/test_submit_artifact_protection.py
vnext/backend/tests/test_storage_projection_import_replay.py (new)
docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-remediation-handoff.md
docs/backend-vnext/refactoring/formal/plans/p5-5b-s3-handoff.md (updated)
```

## Verification record

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --no-sync pytest -q -m unit \
  tests/test_submit_import_builder.py \
  tests/test_storage_projection_import_replay.py \
  tests/test_submit_artifact_protection.py \
  tests/test_repository_import_artifact_package.py \
  tests/test_artifact_boundary.py \
  tests/test_canonical_lock_identity.py
# 47 passed

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync ruff check \
  src/gateway_backend/application/submission \
  src/gateway_backend/repository_import_artifact.py \
  src/gateway_backend/artifacts \
  src/gateway_backend/capabilities/storage_projection/import_replay.py \
  tests/test_submit_import_builder.py tests/test_submit_artifact_protection.py \
  tests/test_storage_projection_import_replay.py
# pass

cd vnext/backend && ../scripts/uv-consume.sh -C . run --no-sync mypy
# 339 source files pass
```

```yaml
uv_lock_in_diff: no
five_package_static: deferred
container_rebuild_required: no
container_reason: remediation is Python/tests/docs only; canonical lock restored
next_step: independent S3 re-review
```

## Notes

- S5 will wire `pin_prepare_import_artifacts` into accept/finalize transactions and delete S2 inline duplicates per R7 guidance.
- Do not run bare `uv run` sync on this tree without `uv-consume.sh`; ambient index can rewrite `uv.lock`.
