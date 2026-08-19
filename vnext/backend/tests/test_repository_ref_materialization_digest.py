"""RepositoryRef catalog, scalar encoding, and digest contract tests."""

from __future__ import annotations

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    RepositoryColumn,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_shared_kernel import NullScalar, SignedIntegerScalar, StringScalar
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    hidden_summary_for,
    int_id_column,
    make_catalog,
    materialize_ref,
    text_column,
)


def test_catalog_to_descriptor_canonical_names() -> None:
    table = catalog_table(
        "Items",
        (
            int_id_column(),
            text_column("Name", 1, nullable=True),
        ),
    )
    rows = {"items": ((1, "a"),)}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    descriptor = result.summary.tables[0]
    assert descriptor.table_name == "items"
    assert descriptor.columns[1].name == "name"
    assert descriptor.columns[1].nullable is True
    assert descriptor.primary_key_columns == ("id",)


def test_identifier_collision_fails_closed() -> None:
    first = catalog_table("items", (int_id_column(),))
    second = catalog_table("ITEMS", (int_id_column(),))
    catalog = make_catalog((first, second))
    hidden = hidden_summary_for(make_catalog((first,)), {"items": ((1,),)})
    provider = FakeRepositoryTableAccessProvider(
        catalog=catalog, hidden=hidden, rows={"items": ((1,),)}
    )
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is (
        MaterializationDiagnosticCode.REPOSITORY_IDENTIFIER_COLLISION
    )


def test_tuple_null_and_extra_fields() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    padded = encode_repository_row(table.columns, (1, None), table="items")
    assert padded.cells[0] == SignedIntegerScalar(decimal="1")
    assert isinstance(padded.cells[1], NullScalar)
    extra = encode_repository_row(table.columns, (1, "a", "ignored"), table="items")
    assert extra.cells == (SignedIntegerScalar(decimal="1"), StringScalar(text="a"))
    assert extra.diagnostics


def test_provider_pads_omitted_nulls() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    hidden_rows = {"items": ((1, None),)}
    streamed = {"items": ((1,),)}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, hidden_rows)
    provider = FakeRepositoryTableAccessProvider(
        catalog=catalog, hidden=hidden, rows=streamed, pad_nulls=True
    )
    result = materialize_ref(provider, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.status is SnapshotMaterializationStatus.COMPLETE


def test_short_row_fails_read() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1,),)}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, {"items": ((1, "a"),)})
    provider = FakeRepositoryTableAccessProvider(
        catalog=catalog, hidden=hidden, rows=rows, pad_nulls=False
    )
    result = materialize_ref(provider, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED


def test_unknown_type_family_is_text_fallback() -> None:
    column = table_column_unknown()
    mapped = map_repository_column(column)
    assert mapped.unknown_family is True
    encoded = encode_repository_row((column,), ("keep-me",), table="items")
    assert encoded.cells == (StringScalar(text="keep-me"),)
    assert encoded.diagnostics


def table_column_unknown() -> RepositoryColumn:
    return RepositoryColumn(name="payload", ordinal=0, scalar_type="WEIRDTYPE", nullable=True)


def test_same_ref_repeats_same_snapshot_digest() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"), (2, "b"))}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    first = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    )
    second = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    )
    assert first.snapshot is not None and second.snapshot is not None
    assert first.snapshot.snapshot_digest == second.snapshot.snapshot_digest
    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id


def test_row_order_does_not_change_content_digest() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    forward = {"items": ((1, "a"), (2, "b"))}
    reverse = {"items": ((2, "b"), (1, "a"))}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, forward)
    left = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=forward),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    right = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=reverse),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert left.status is SnapshotMaterializationStatus.COMPLETE
    assert right.status is SnapshotMaterializationStatus.COMPLETE
    assert left.summary is not None and right.summary is not None
    assert left.summary.tables[0].raw_content_digest == right.summary.tables[0].raw_content_digest
    assert left.snapshot is not None and right.snapshot is not None
    assert left.snapshot.snapshot_digest == right.snapshot.snapshot_digest


def test_duplicate_rows_are_preserved_in_digest() -> None:
    table = catalog_table("items", (int_id_column(),), primary_key=())
    unique = {"items": ((1,),)}
    duplicated = {"items": ((1,), (1,))}
    catalog = make_catalog((table,))
    hidden_unique = hidden_summary_for(catalog, unique)
    hidden_dup = hidden_summary_for(catalog, duplicated)
    left = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden_unique, rows=unique)
    )
    right = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden_dup, rows=duplicated)
    )
    assert left.summary is not None and right.summary is not None
    assert left.summary.tables[0].raw_content_digest != right.summary.tables[0].raw_content_digest
    assert right.summary.tables[0].row_count == 2


def test_table_root_hash_does_not_replace_raw_digest() -> None:
    columns = (int_id_column(), text_column("name", 1))
    rows = {"items": ((1, "a"),)}
    left_table = catalog_table("items", columns, table_root_hash="root-a")
    right_table = catalog_table("items", columns, table_root_hash="root-b")
    left_catalog = make_catalog((left_table,))
    right_catalog = make_catalog((right_table,))
    hidden = hidden_summary_for(left_catalog, rows)
    left = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=left_catalog, hidden=hidden, rows=rows),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    right = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=right_catalog, hidden=hidden, rows=rows),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert left.status is SnapshotMaterializationStatus.COMPLETE
    assert right.status is SnapshotMaterializationStatus.COMPLETE
    assert left.summary is not None and right.summary is not None
    assert left.summary.tables[0].raw_content_digest == right.summary.tables[0].raw_content_digest
    assert left.snapshot is not None and right.snapshot is not None
    assert left.snapshot.snapshot_digest == right.snapshot.snapshot_digest


def test_readers_required_publishes_reopenable_rows() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"), (2, None))}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    result = materialize_ref(provider, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    published = result.table_set.tables[0]
    assert published.reader is not None
    consumed = list(published.reader.iter_rows())
    assert len(consumed) == 2
    assert isinstance(consumed[0][0], SignedIntegerScalar)
    assert isinstance(consumed[1][1], NullScalar)
    reopened = published.reader.reopen()
    assert len(list(reopened.iter_rows())) == 2
    reopened.close()
    published.reader.close()
