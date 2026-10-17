"""Submit preparation applies canonical table removals from its frozen parent."""

from __future__ import annotations

from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.contracts import PrepareImportBuildInput
from gateway_backend.application.submission.import_builder import (
    derive_removed_tables,
    resolve_canonical_snapshot_bindings,
)
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, artifact_ref_to_dict
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    STORAGE_PROJECTION_VERSION,
    durable_manifest_bytes,
    project_canonical_table_set,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.infrastructure.repository_read import HttpRepositoryParentCatalogPort
from gateway_backend.infrastructure.repository_write.import_publication import (
    SubmitImportPublicationAdapter,
)
from tests.support.snapshot_materialization import materialize_sql
from tests.support.submit_job_harness import repository_service_session

pytestmark = pytest.mark.integration


def _canonical_records_state(
    store: InMemoryArtifactStore,
) -> tuple[ArtifactRef, ArtifactRef, tuple[ArtifactRef, ...], str, str]:
    materialized = materialize_sql(
        "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY); INSERT INTO records VALUES (1);",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert materialized.status is SnapshotMaterializationStatus.COMPLETE
    assert materialized.table_set is not None
    table = materialized.table_set.tables[0]
    assert table.artifact is not None
    ruleset = migrated_table_ruleset_snapshot()
    projection = project_canonical_table_set(materialized.table_set, ruleset)
    assert projection.manifest is not None
    assert projection.manifest.manifest_digest is not None
    manifest_bytes = durable_manifest_bytes(projection.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="submit-removal-records-manifest",
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_bytes),
        raw_sha256=raw_blob_digest(manifest_bytes),
    )
    closure_bytes = canonicalize_json_value(
        {
            "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
            "tables": [
                {
                    "table_name": table.descriptor.table_name,
                    "manifest_ref": artifact_ref_to_dict(table.artifact.manifest_ref),
                }
            ],
        }
    )
    closure_ref = ArtifactRef(
        artifact_id="submit-removal-records-closure",
        media_type="application/jcs",
        size_bytes=len(closure_bytes),
        raw_sha256=raw_blob_digest(closure_bytes),
    )
    store.put(manifest_bytes, manifest_ref)
    store.put(closure_bytes, closure_ref)
    refs = (
        closure_ref,
        manifest_ref,
        table.artifact.manifest_ref,
        *table.artifact.manifest.row_file_refs,
    )
    return (
        closure_ref,
        manifest_ref,
        tuple(refs),
        table.artifact.manifest.snapshot_digest.value,
        projection.manifest.manifest_digest.value,
    )


def test_prepare_removes_parent_tables_omitted_from_frozen_canonical_state(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    store = InMemoryArtifactStore()
    closure_ref, manifest_ref, artifact_refs, source_digest, manifest_digest = (
        _canonical_records_state(store)
    )
    closure_digest = closure_ref.raw_sha256.value
    snapshot_tables, _canonical_refs = resolve_canonical_snapshot_bindings(
        operation_artifact_refs=artifact_refs,
        canonical_table_set_closure_ref=closure_ref.artifact_id,
        canonical_table_set_closure_digest=closure_digest,
        canonicalization_manifest_ref=manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest,
        read_artifact=store.locate,
    )
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    adapter = SubmitImportPublicationAdapter()

    with repository_service_session(tmp_path) as service:
        seeded = service.repository_id_factory(idempotency_key="submit-removal-parent")
        parent_catalog = HttpRepositoryParentCatalogPort(
            base_url=service.base_url,
            bearer_token=service.bearer_token,
        )
        assert parent_catalog.get_table_names(
            repository_id=seeded.repository_id,
            commit_id=seeded.initial_commit_id,
        ) == ()
        first_input = PrepareImportBuildInput(
            submit_attempt_id="sa-submit-table-removal-create",
            builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
            canonical_table_set_closure_ref=closure_ref,
            canonical_table_set_closure_digest=closure_digest,
            canonicalization_manifest_ref=manifest_ref,
            canonicalization_manifest_digest=manifest_digest,
            expected_parent_commit_id=seeded.initial_commit_id,
            removed_tables=(),
            source_artifact_digest=source_digest,
            repository_base_digest=source_digest,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            ruleset_id=ruleset.ruleset_id,
            ruleset_version=ruleset.ruleset_version,
            ruleset_digest=ruleset.ruleset_digest.value,
            snapshot_tables=snapshot_tables,
        )
        first_checkpoint = adapter.build_and_publish(
            build_input=first_input,
            store=store,
        ).checkpoint
        first_package = adapter.read_back_package(checkpoint=first_checkpoint, store=store)
        repository_client = service.write_client()
        first_artifact = repository_client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key="submit-removal-upload-table",
            media_type=first_checkpoint.backend_import_artifact_ref.media_type,
            raw_sha256=raw_blob_digest(first_package).value,
            body=first_package,
        )
        first_operation_id = repository_client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key="submit-removal-import-table",
            artifact_ref=first_artifact,
            expected_commit_id=seeded.initial_commit_id,
        )
        first_operation = repository_client.wait_operation(
            repository_id=seeded.repository_id,
            operation_id=first_operation_id,
            deadline_seconds=120.0,
        )
        assert first_operation.status.value == "SUCCEEDED", first_operation.error
        assert first_operation.result is not None
        parent_commit_id = first_operation.result.commit_id

        parent_tables = parent_catalog.get_table_names(
            repository_id=seeded.repository_id,
            commit_id=parent_commit_id,
        )
        assert parent_tables == ("records",)
        removed_tables = derive_removed_tables(
            parent_table_names=parent_tables,
            snapshot_tables=(),
        )
        assert removed_tables == ("records",)

        empty_materialized = materialize_sql(
            "SET FOREIGN_KEY_CHECKS=0;",
            policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
            artifact_store=store,
        )
        assert empty_materialized.status is SnapshotMaterializationStatus.COMPLETE
        assert empty_materialized.table_set is not None
        assert empty_materialized.table_set.tables == ()
        empty_projection = project_canonical_table_set(empty_materialized.table_set, ruleset)
        assert empty_projection.manifest is not None
        assert empty_projection.manifest.manifest_digest is not None
        empty_manifest_bytes = durable_manifest_bytes(empty_projection.manifest)
        empty_manifest_ref = ArtifactRef(
            artifact_id="submit-removal-empty-manifest",
            media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
            size_bytes=len(empty_manifest_bytes),
            raw_sha256=raw_blob_digest(empty_manifest_bytes),
        )
        empty_closure_bytes = canonicalize_json_value(
            {
                "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
                "tables": [],
            }
        )
        empty_closure_ref = ArtifactRef(
            artifact_id="submit-removal-empty-closure",
            media_type="application/jcs",
            size_bytes=len(empty_closure_bytes),
            raw_sha256=raw_blob_digest(empty_closure_bytes),
        )
        store.put(empty_manifest_bytes, empty_manifest_ref)
        store.put(empty_closure_bytes, empty_closure_ref)
        second_input = PrepareImportBuildInput(
            submit_attempt_id="sa-submit-table-removal-delete",
            builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
            canonical_table_set_closure_ref=empty_closure_ref,
            canonical_table_set_closure_digest=empty_closure_ref.raw_sha256.value,
            canonicalization_manifest_ref=empty_manifest_ref,
            canonicalization_manifest_digest=empty_projection.manifest.manifest_digest.value,
            expected_parent_commit_id=parent_commit_id,
            removed_tables=removed_tables,
            source_artifact_digest=empty_projection.manifest.source_artifact_digest.value,
            repository_base_digest=source_digest,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            ruleset_id=ruleset.ruleset_id,
            ruleset_version=ruleset.ruleset_version,
            ruleset_digest=ruleset.ruleset_digest.value,
            snapshot_tables=(),
        )
        second_checkpoint = adapter.build_and_publish(
            build_input=second_input,
            store=store,
        ).checkpoint
        assert second_checkpoint.removed_tables == ("records",)
        second_package = adapter.read_back_package(checkpoint=second_checkpoint, store=store)
        second_artifact = repository_client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key="submit-removal-upload-empty-state",
            media_type=second_checkpoint.backend_import_artifact_ref.media_type,
            raw_sha256=raw_blob_digest(second_package).value,
            body=second_package,
        )
        second_operation_id = repository_client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key="submit-removal-import-empty-state",
            artifact_ref=second_artifact,
            expected_commit_id=parent_commit_id,
        )
        second_operation = repository_client.wait_operation(
            repository_id=seeded.repository_id,
            operation_id=second_operation_id,
            deadline_seconds=120.0,
        )
        assert second_operation.status.value == "SUCCEEDED", second_operation.error
        assert second_operation.result is not None
        assert parent_catalog.get_table_names(
            repository_id=seeded.repository_id,
            commit_id=second_operation.result.commit_id,
        ) == ()
