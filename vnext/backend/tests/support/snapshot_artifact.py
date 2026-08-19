"""Helpers for SnapshotTableArtifact unit tests."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    publish_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotMaterializationResult,
    SnapshotTable,
    SnapshotTableArtifact,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
)
from tests.support.snapshot_materialization import materialize_sql, parse_fixture


def readers_result(
    relative_sql: str = "sql/valid/s2-minimal-create-insert/input.sql",
) -> SnapshotMaterializationResult:
    return materialize_sql(parse_fixture(relative_sql), policy=MaterializationPolicy.READERS_REQUIRED)


def first_ready_table(relative_sql: str = "sql/valid/s2-minimal-create-insert/input.sql") -> SnapshotTable:
    result = readers_result(relative_sql)
    assert result.snapshot is not None
    assert result.table_set is not None
    return result.table_set.tables[0]


def publish_first_table(
    store: InMemoryArtifactStore,
    relative_sql: str = "sql/valid/s2-minimal-create-insert/input.sql",
) -> tuple[SnapshotTableArtifact, DigestRef]:
    result = readers_result(relative_sql)
    assert result.snapshot is not None
    assert result.table_set is not None
    table = result.table_set.tables[0]
    artifact = publish_snapshot_table_artifact(
        table,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    return artifact, result.snapshot.snapshot_digest


def replace_stored_bytes(
    store: InMemoryArtifactStore,
    ref: ArtifactRef,
    new_bytes: bytes,
) -> ArtifactRef:
    new_ref = ArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=len(new_bytes),
        raw_sha256=raw_blob_digest(new_bytes),
    )
    store._artifacts[ref.artifact_id] = (new_ref, new_bytes)
    return new_ref
