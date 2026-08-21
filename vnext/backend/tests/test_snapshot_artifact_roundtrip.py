"""Parquet SnapshotTableArtifact round-trip tests."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    open_snapshot_table_artifact,
    publish_snapshot_table_artifact,
    validate_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance,
    CacheTrustLevel,
    DegradedReason,
    MaterializationPolicy,
    SnapshotTableOrderedMetadata,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.snapshot_materialization.batch import batch_metadata_from_schema
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
)
from tests.support.artifact_staging import assert_minimal_ref_has_no_host_path
from tests.support.repository_ref_materialization import materialize_ref, minimal_fixture
from tests.support.snapshot_artifact import first_ready_table, publish_first_table
from tests.support.snapshot_materialization import load_sql, materialize_business, materialize_sql, parse_fixture


def test_parquet_round_trip_preserves_descriptor_rows_and_digests() -> None:
    store = InMemoryArtifactStore()
    source = first_ready_table("sql/valid/s2-null-and-types/input.sql")
    result = materialize_sql(
        parse_fixture("sql/valid/s2-null-and-types/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    artifact = publish_snapshot_table_artifact(
        source,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
    assert opened.descriptor == source.descriptor
    assert opened.descriptor.row_count == source.descriptor.row_count
    assert opened.descriptor.raw_content_digest == source.descriptor.raw_content_digest
    assert opened.artifact is not None
    assert opened.artifact.manifest.artifact_content_digest == artifact.manifest.artifact_content_digest
    assert opened.reader is not None
    source_reader = source.reader
    assert source_reader is not None
    assert tuple(opened.reader.iter_rows()) == tuple(source_reader.reopen().iter_rows())
    validate_snapshot_table_artifact(store, artifact)
    assert_minimal_ref_has_no_host_path(artifact.manifest_ref)
    for ref in artifact.manifest.row_file_refs:
        assert_minimal_ref_has_no_host_path(ref)


def test_two_publishes_of_the_same_table_share_artifact_digest() -> None:
    store = InMemoryArtifactStore()
    first, _digest = publish_first_table(store, "sql/valid/s2-duplicate-rows/input.sql")
    second, _again = publish_first_table(InMemoryArtifactStore(), "sql/valid/s2-duplicate-rows/input.sql")
    assert first.manifest.artifact_content_digest == second.manifest.artifact_content_digest
    assert first.row_layout_digest == second.row_layout_digest


def test_ordered_blank_provenance_round_trips_through_artifact_and_batch() -> None:
    store = InMemoryArtifactStore()
    source = first_ready_table("sql/valid/s2-null-and-types/input.sql")
    metadata = SnapshotTableOrderedMetadata(BlankRowProvenance.SOURCE_MISSING_STABLE_KEY)
    source = replace(source, ordered_metadata=metadata)
    result = materialize_sql(
        parse_fixture("sql/valid/s2-null-and-types/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.snapshot is not None
    artifact = publish_snapshot_table_artifact(
        source,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=ParserInvocationContext(NeverCancel()),
    )

    opened = open_snapshot_table_artifact(store, artifact.manifest_ref)
    assert opened.ordered_metadata == metadata
    assert opened.batch_reader is not None
    assert opened.batch_reader.metadata().blank_provenance is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY
    assert (
        batch_metadata_from_schema(opened.batch_reader.schema())
        == opened.batch_reader.metadata()
    )


def test_artifacts_required_publishes_ready_tables_only() -> None:
    store = InMemoryArtifactStore()
    result = materialize_sql(
        parse_fixture("sql/partial/s2-unknown-type-mixed/input.sql"),
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.PARTIAL
    assert result.cache_trust_level is CacheTrustLevel.CONTENT_VERIFIED
    assert result.table_set is not None
    assert result.summary is not None
    by_name = {table.descriptor.table_name: table for table in result.table_set.tables}
    assert by_name["ok"].artifact is not None
    assert by_name["ok"].reader is not None
    failed = [table for table in result.summary.tables if table.degraded_reason is DegradedReason.TABLE_FAILED]
    assert failed
    assert all(
        table.artifact is None
        for table in result.table_set.tables
        if table.descriptor.degraded_reason is DegradedReason.TABLE_FAILED
    )


def test_business_artifacts_required_publishes_derived_table() -> None:
    store = InMemoryArtifactStore()
    xml = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "golden"
        / "composite-signal"
        / "xml"
        / "valid"
        / "s3-minimal-logic"
        / "input.xml"
    ).read_text(encoding="utf-8")
    result = materialize_business(
        load_sql("business/valid/s3-special-device/input.sql"),
        xml,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    names = [table.descriptor.table_name for table in result.table_set.tables]
    assert names[-1] == "composite_signal_point"
    assert all(table.artifact is not None for table in result.table_set.tables)


def test_repository_ref_artifacts_required_round_trip() -> None:
    store = InMemoryArtifactStore()
    provider, _rows = minimal_fixture()
    result = materialize_ref(
        provider,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    table = result.table_set.tables[0]
    assert table.artifact is not None
    opened = open_snapshot_table_artifact(store, table.artifact.manifest_ref)
    assert opened.descriptor.raw_content_digest == table.descriptor.raw_content_digest
    assert opened.reader is not None
    assert tuple(opened.reader.iter_rows())
