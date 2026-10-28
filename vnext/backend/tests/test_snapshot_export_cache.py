"""TTL and repository-scoped snapshot Parquet export cache tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind, raw_blob_digest
from gateway_backend.capabilities.snapshot_materialization._reader import (
    BoundSnapshotTableReader,
)

import gateway_backend.capabilities.snapshot_materialization.contracts as snapshot_contracts
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    PARQUET_MEDIA_TYPE,
    SnapshotTable,
    SnapshotTableArtifactCacheKey,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    open_snapshot_table_artifact,
    publish_ready_tables,
    publish_snapshot_table_artifact,
    row_layout_digest_of,
)
from gateway_backend.infrastructure.control_db.database import (
    ControlDbUnitOfWork,
    initialize_control_db,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    SourceColumnDescriptor,
    SqlLogicalType,
)
from tests.support.snapshot_artifact import first_ready_table

pytestmark = pytest.mark.unit


def _key(
    *,
    repository_id: str = "repository-1",
    layout: bytes = b"layout-v1",
) -> SnapshotTableArtifactCacheKey:
    return SnapshotTableArtifactCacheKey(
        row_layout_digest=raw_blob_digest(layout),
        repository_id=repository_id,
    )


def _ref() -> ArtifactRef:
    payload = b"parquet-row-file"
    return ArtifactRef(
        artifact_id="snapshot-rows-1",
        media_type=PARQUET_MEDIA_TYPE,
        size_bytes=len(payload),
        raw_sha256=raw_blob_digest(payload),
    )


def _uow(db_path: Path, now: datetime | None = None) -> ControlDbUnitOfWork:
    if now is None:
        now = datetime.now(UTC)
    return ControlDbUnitOfWork(
        db_path,
        now=lambda: now,
    )


def test_export_cache_is_exact_by_repository_and_row_layout(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite"
    initialize_control_db(db_path)
    key = _key()
    cached_ref = _ref()

    with _uow(db_path) as unit_of_work:
        unit_of_work.snapshot_table_export_cache.store_many(((key, cached_ref),))

    with _uow(db_path) as unit_of_work:
        cache = unit_of_work.snapshot_table_export_cache
        assert cache.lookup_many((key,)) == {key: cached_ref}
        assert cache.lookup_many((_key(layout=b"different-export-schema"),)) == {}
        assert cache.lookup_many((_key(repository_id="repository-2"),)) == {}
        assert unit_of_work.protection.is_protected(cached_ref.artifact_id)


def test_row_layout_cache_identity_includes_enum_labels() -> None:
    source = first_ready_table()
    enum_ab = (
        SourceColumnDescriptor(
            display_name="state",
            canonical_name="state",
            ordinal=0,
            sql_type="ENUM('a','b')",
            logical_type=SqlLogicalType.ENUM,
            declared_type=DeclaredType(DeclaredTypeKind.STRING),
            nullable=True,
            enum_or_set_labels=("a", "b"),
        ),
    )
    enum_ac = (
        SourceColumnDescriptor(
            display_name="state",
            canonical_name="state",
            ordinal=0,
            sql_type="ENUM('a','c')",
            logical_type=SqlLogicalType.ENUM,
            declared_type=DeclaredType(DeclaredTypeKind.STRING),
            nullable=True,
            enum_or_set_labels=("a", "c"),
        ),
    )

    assert source.descriptor.raw_content_digest is not None
    assert row_layout_digest_of(source.descriptor, enum_ab) != row_layout_digest_of(
        source.descriptor,
        enum_ac,
    )


def test_export_cache_writer_version_is_part_of_the_exact_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "control.sqlite"
    initialize_control_db(db_path)
    version_one = _key()
    cached_ref = _ref()
    with _uow(db_path) as unit_of_work:
        unit_of_work.snapshot_table_export_cache.store_many(((version_one, cached_ref),))

    monkeypatch.setattr(snapshot_contracts, "PARQUET_WRITER_CONTRACT_VERSION", 2)
    version_two = SnapshotTableArtifactCacheKey(
        row_layout_digest=version_one.row_layout_digest,
        repository_id=version_one.repository_id,
        parquet_writer_contract_version=2,
    )
    with _uow(db_path) as unit_of_work:
        assert unit_of_work.snapshot_table_export_cache.lookup_many((version_two,)) == {}


def test_export_cache_expiry_releases_cache_protection(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite"
    initialize_control_db(db_path)
    key = _key()
    cached_ref = _ref()
    now = datetime.now(UTC)
    with _uow(db_path, now) as unit_of_work:
        unit_of_work.snapshot_table_export_cache.store_many(((key, cached_ref),))

    expired = now + timedelta(days=2)
    with _uow(db_path, expired) as unit_of_work:
        cache = unit_of_work.snapshot_table_export_cache
        assert cache.lookup_many((key,)) == {}
        assert not unit_of_work.protection.is_protected(cached_ref.artifact_id)


def test_repeated_parquet_export_uses_the_protected_cached_row_file() -> None:
    store = InMemoryArtifactStore()
    original = first_ready_table()
    assert original.reader is not None
    original_reader = original.reader
    snapshot_digest = raw_blob_digest(b"snapshot")
    cached = publish_snapshot_table_artifact(
        original,
        snapshot_digest=snapshot_digest,
        store=store,
        context=ParserInvocationContext(NeverCancel()),
    )
    cache_key = SnapshotTableArtifactCacheKey(
        row_layout_digest=cached.row_layout_digest,
        repository_id="repository-1",
    )

    class UnreadableSourceReader:
        def source_columns(self) -> tuple[object, ...]:
            return cast(BoundSnapshotTableReader, original_reader).source_descriptor().columns

        def reopen(self) -> object:
            raise AssertionError("cache hit must not read or re-export source rows")

    table = SnapshotTable(
        descriptor=original.descriptor,
        reader=UnreadableSourceReader(),  # type: ignore[arg-type]
        diagnostics=original.diagnostics,
        ordered_metadata=original.ordered_metadata,
    )

    class Cache:
        stored: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...] = ()

        def lookup_many(
            self,
            keys: tuple[SnapshotTableArtifactCacheKey, ...],
        ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
            return {cache_key: cached.manifest.row_file_refs[0]} if cache_key in keys else {}

        def store_many(
            self,
            entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...],
        ) -> None:
            self.stored = entries

        def discard_many(self, _keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> None:
            return None

    cache = Cache()
    published = publish_ready_tables(
        (table,),
        snapshot_digest=raw_blob_digest(b"next-snapshot"),
        store=store,
        context=ParserInvocationContext(NeverCancel()),
        export_cache=cache,
        repository_id="repository-1",
    )

    artifact = published[0].artifact
    assert artifact is not None
    assert artifact.manifest.row_file_refs == cached.manifest.row_file_refs
    assert cache.stored == ((cache_key, cached.manifest.row_file_refs[0]),)


def test_invalid_cached_parquet_falls_back_to_canonical_source_export() -> None:
    source = first_ready_table()
    store = InMemoryArtifactStore()
    invalid_ref = put_with_built_ref(
        store,
        b"not parquet",
        artifact_id="snapshot-rows-invalid-cache",
        media_type=PARQUET_MEDIA_TYPE,
    )

    published = publish_snapshot_table_artifact(
        source,
        snapshot_digest=raw_blob_digest(b"snapshot"),
        store=store,
        context=ParserInvocationContext(NeverCancel()),
        cached_row_ref=invalid_ref,
    )

    assert published.manifest.row_file_refs[0] != invalid_ref
    opened = open_snapshot_table_artifact(store, published.manifest_ref)
    assert opened.reader is not None
    assert source.reader is not None
    assert tuple(opened.reader.iter_rows()) == tuple(source.reader.reopen().iter_rows())

