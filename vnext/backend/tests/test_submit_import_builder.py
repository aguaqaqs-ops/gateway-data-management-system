"""Submit import builder publication and checkpoint reuse tests."""

from __future__ import annotations

import pytest
from gateway_backend.application.submission.contracts import (
    PrepareImportBuildInput,
    SnapshotTableBinding,
)
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.storage_projection import (
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.domain.submission.models import BuilderMutationPolicy
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from tests.support.storage_projection import as_row, int_cell, int_column, table_input, varchar_cell, varchar_column

pytestmark = pytest.mark.unit

_NET_CFG_COLUMNS = (
    varchar_column("board"),
    int_column("link_no"),
    int_column("no", nullable=True),
)
_NET_CFG_ROWS = (
    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
    as_row(varchar_cell("eth1"), int_cell(2), int_cell(20)),
)


def _build_input() -> PrepareImportBuildInput:
    ruleset = migrated_table_ruleset_snapshot()
    assert ruleset.ruleset_digest is not None
    return PrepareImportBuildInput(
        submit_attempt_id="sa-import-1",
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        input_closure_digest="sha256:closure",
        source_artifact_digest=ruleset.ruleset_digest.value,
        repository_base_digest="sha256:repo-base",
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=(
            SnapshotTableBinding(
                artifact_id="snap-net-cfg",
                media_type="application/json",
                size_bytes=1,
                raw_sha256="sha256:" + "aa" * 32,
            ),
        ),
    )


def _projection_inputs() -> tuple[ProjectionTableInput, ...]:
    reader, binding = table_input(
        "net_cfg",
        columns=_NET_CFG_COLUMNS,
        primary_key_columns=("board", "link_no"),
        rows=_NET_CFG_ROWS,
    )
    return (
        ProjectionTableInput(
            canonical_table="net_cfg",
            reader=reader,
            source_binding=binding,
        ),
    )


def test_rebuild_always_publish_is_deterministic_for_same_inputs() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    first_store = InMemoryArtifactStore()
    second_store = InMemoryArtifactStore()
    first = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=first_store,
        projection_inputs=_projection_inputs(),
    )
    second = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=second_store,
        projection_inputs=_projection_inputs(),
    )
    assert first.replay is False
    assert second.replay is False
    assert (
        first.checkpoint.canonicalization_manifest_digest
        == second.checkpoint.canonicalization_manifest_digest
    )
    assert (
        first.checkpoint.backend_import_artifact_ref.raw_sha256
        == second.checkpoint.backend_import_artifact_ref.raw_sha256
    )


def test_checkpoint_reuse_read_back_preserves_package_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    reused = reuse_prepare_import_checkpoint(
        build_input=build_input,
        checkpoint=published.checkpoint,
        publication=adapter,
        store=store,
    )
    assert reused.replay is True
    assert (
        reused.checkpoint.backend_import_artifact_ref
        == published.checkpoint.backend_import_artifact_ref
    )
    payload = adapter.read_back_package(checkpoint=reused.checkpoint, store=store)
    assert len(payload) == published.checkpoint.package_raw_size


def test_orphan_bytes_before_checkpoint_do_not_change_published_identity() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    orphan_count = len(store._artifacts)
    second = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    assert len(store._artifacts) > orphan_count
    reused = reuse_prepare_import_checkpoint(
        build_input=build_input,
        checkpoint=published.checkpoint,
        publication=adapter,
        store=store,
    )
    assert (
        reused.checkpoint.backend_import_artifact_ref.raw_sha256
        == published.checkpoint.backend_import_artifact_ref.raw_sha256
    )
    assert (
        second.checkpoint.backend_import_artifact_ref.artifact_id
        != reused.checkpoint.backend_import_artifact_ref.artifact_id
    )


def test_reuse_rejects_mismatched_input_closure_digest() -> None:
    adapter = SubmitImportPublicationAdapter()
    build_input = _build_input()
    store = InMemoryArtifactStore()
    published = adapter.build_and_publish_from_inputs(
        build_input=build_input,
        store=store,
        projection_inputs=_projection_inputs(),
    )
    mismatched = PrepareImportBuildInput(
        submit_attempt_id=build_input.submit_attempt_id,
        builder_mutation_policy=build_input.builder_mutation_policy,
        input_closure_digest="sha256:other",
        source_artifact_digest=build_input.source_artifact_digest,
        repository_base_digest=build_input.repository_base_digest,
        storage_projection_version=build_input.storage_projection_version,
        ruleset_id=build_input.ruleset_id,
        ruleset_version=build_input.ruleset_version,
        ruleset_digest=build_input.ruleset_digest,
        snapshot_tables=build_input.snapshot_tables,
    )
    with pytest.raises(SubmitImportBuilderError, match="input closure digest"):
        reuse_prepare_import_checkpoint(
            build_input=mismatched,
            checkpoint=published.checkpoint,
            publication=adapter,
            store=store,
        )
