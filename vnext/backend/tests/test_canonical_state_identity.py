"""Business schema and canonical state digest semantics."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from gateway_shared_kernel import DigestRef, Float32Scalar, Float64Scalar, raw_blob_digest

from gateway_backend.capabilities.storage_projection import project_canonical_table_set
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot

from gateway_backend.capabilities.storage_projection._digest import compute_schema_digest
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    MaterializationStage,
    SnapshotColumnDescriptor,
    Snapshot,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    SourceKind,
    SUMMARY_CONTRACT_VERSION,
    canonical_state_digest_of,
    snapshot_from_document,
    snapshot_summary_from_document,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.snapshot_materialization._digest import raw_state_digest_of
from tests.support.storage_projection import (
    as_row,
    dummy_digest,
    int_cell,
    int_column,
    table_input,
    typed_column,
)

_ROW_DIGEST = raw_blob_digest(b"row-content")
_COMPARE_DIGEST = raw_blob_digest(b"compare-schema")
_BASE_COLUMNS = (
    SnapshotColumnDescriptor("id", "id", False, "INT UNSIGNED"),
    SnapshotColumnDescriptor("name", "name", True, "VARCHAR(16)"),
)


def _descriptor(
    columns: tuple[SnapshotColumnDescriptor, ...] = _BASE_COLUMNS,
    *,
    primary_key_columns: tuple[str, ...] = ("id",),
    row_count: int = 1,
    raw_content_digest: DigestRef | None = _ROW_DIGEST,
    materialization_stage: MaterializationStage = MaterializationStage.FINAL,
) -> SnapshotTableDescriptor:
    return SnapshotTableDescriptor(
        table_name="items",
        display_table_name="Items",
        columns=columns,
        primary_key_columns=primary_key_columns,
        compare_key_columns=("id",),
        row_count=row_count,
        materialization_stage=materialization_stage,
        compare_schema_digest=_COMPARE_DIGEST,
        table_ruleset_version=1,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=raw_content_digest,
    )


def _added_column() -> SnapshotTableDescriptor:
    return _descriptor(
        (
            SnapshotColumnDescriptor("id", "id", False, "INT UNSIGNED"),
            SnapshotColumnDescriptor("name", "name", True, "VARCHAR(16)"),
            SnapshotColumnDescriptor("empty", "empty", True, "TEXT"),
        ),
        row_count=0,
    )


def _changed_type() -> SnapshotTableDescriptor:
    return _descriptor(
        (_BASE_COLUMNS[0], SnapshotColumnDescriptor("name", "name", True, "TEXT"))
    )


def _changed_length() -> SnapshotTableDescriptor:
    return _descriptor(
        (_BASE_COLUMNS[0], SnapshotColumnDescriptor("name", "name", True, "VARCHAR(32)"))
    )


def _changed_nullability() -> SnapshotTableDescriptor:
    return _descriptor(
        (_BASE_COLUMNS[0], SnapshotColumnDescriptor("name", "name", False, "VARCHAR(16)"))
    )


def _changed_key_order() -> SnapshotTableDescriptor:
    return _descriptor(
        (
            SnapshotColumnDescriptor("left_key", "left_key", False, "INT"),
            SnapshotColumnDescriptor("right_key", "right_key", False, "INT"),
        ),
        primary_key_columns=("left_key", "right_key"),
    )


def _changed_key_order_reversed() -> SnapshotTableDescriptor:
    return _descriptor(
        (
            SnapshotColumnDescriptor("left_key", "left_key", False, "INT"),
            SnapshotColumnDescriptor("right_key", "right_key", False, "INT"),
        ),
        primary_key_columns=("right_key", "left_key"),
    )


def _reordered_columns() -> SnapshotTableDescriptor:
    return _descriptor(tuple(reversed(_BASE_COLUMNS)))


def _manifest_schema_digest(table: SnapshotTableDescriptor) -> DigestRef:
    return compute_schema_digest(
        columns=[
            {
                "name": column.name,
                "sql_type": column.scalar_type,
                "nullable": column.nullable,
            }
            for column in table.columns
        ],
        primary_key=table.primary_key_columns,
    )


BUSINESS_SCHEMA_VARIANTS: tuple[
    tuple[
        str,
        Callable[[], SnapshotTableDescriptor],
        Callable[[], SnapshotTableDescriptor],
        bool,
    ],
    ...,
] = (
    ("empty table gains a column", lambda: _descriptor(row_count=0), _added_column, True),
    ("column type changes", _descriptor, _changed_type, True),
    ("column length changes", _descriptor, _changed_length, True),
    ("column nullability changes", _descriptor, _changed_nullability, True),
    (
        "primary key order changes",
        _changed_key_order,
        _changed_key_order_reversed,
        True,
    ),
    ("physical column order changes", _descriptor, _reordered_columns, False),
)


@pytest.mark.parametrize(
    ("case", "build_baseline", "build_variant", "digest_changes"),
    BUSINESS_SCHEMA_VARIANTS,
)
def test_business_schema_digest_tracks_business_definition(
    case: str,
    build_baseline: Callable[[], SnapshotTableDescriptor],
    build_variant: Callable[[], SnapshotTableDescriptor],
    digest_changes: bool,
) -> None:
    baseline = build_baseline()
    candidate = build_variant()

    assert (candidate.business_schema_digest != baseline.business_schema_digest) is digest_changes
    baseline_state = canonical_state_digest_of((baseline,))
    candidate_state = canonical_state_digest_of((candidate,))
    assert baseline_state is not None
    assert candidate_state is not None
    assert (candidate_state != baseline_state) is digest_changes
    if case == "physical column order changes":
        assert _manifest_schema_digest(candidate) != _manifest_schema_digest(baseline)


def test_canonical_state_digest_uses_content_and_row_count() -> None:
    baseline = _descriptor()
    changed_content = _descriptor(raw_content_digest=raw_blob_digest(b"different-content"))
    changed_row_count = _descriptor(row_count=2)

    baseline_digest = canonical_state_digest_of((baseline,))
    assert baseline_digest is not None
    assert canonical_state_digest_of((changed_content,)) != baseline_digest
    assert canonical_state_digest_of((changed_row_count,)) != baseline_digest


def test_raw_state_digest_retains_schema_independent_identity() -> None:
    empty_baseline = _descriptor(row_count=0)
    empty_with_column = _added_column()

    assert canonical_state_digest_of((empty_baseline,)) != canonical_state_digest_of(
        (empty_with_column,)
    )
    assert raw_state_digest_of((empty_baseline,)) == raw_state_digest_of((empty_with_column,))


def test_canonical_state_digest_is_unavailable_without_raw_content_digest() -> None:
    provisional = _descriptor(
        raw_content_digest=None,
        materialization_stage=MaterializationStage.PROVISIONAL,
    )

    assert canonical_state_digest_of((provisional,)) is None


@pytest.mark.parametrize(
    ("sql_type", "negative_zero", "positive_zero"),
    (
        ("FLOAT", Float32Scalar(bits_hex="80000000"), Float32Scalar(bits_hex="00000000")),
        (
            "DOUBLE",
            Float64Scalar(bits_hex="8000000000000000"),
            Float64Scalar(bits_hex="0000000000000000"),
        ),
    ),
)
def test_canonical_state_digest_treats_signed_and_positive_float_zero_as_equal(
    sql_type: str,
    negative_zero: Float32Scalar | Float64Scalar,
    positive_zero: Float32Scalar | Float64Scalar,
) -> None:
    def state_digest(value: Float32Scalar | Float64Scalar) -> DigestRef:
        reader, binding = table_input(
            "float_zero_state",
            columns=(int_column("id"), typed_column("reading", sql_type)),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), value),),
            snapshot_digest=dummy_digest(),
        )
        raw_table_set = SnapshotTableSet(
            snapshot_id="float-zero-state",
            snapshot_digest=dummy_digest(),
            table_ruleset_version=TABLE_RULESET_VERSION,
            tables=(SnapshotTable(descriptor=binding.descriptor, reader=reader),),
        )
        projected = project_canonical_table_set(
            raw_table_set,
            migrated_table_ruleset_snapshot(),
        )
        assert projected.status.value == "COMPLETE", projected.diagnostics
        digest = canonical_state_digest_of(tuple(table.descriptor for table in projected.tables))
        assert digest is not None
        for table in projected.tables:
            if table.reader is not None:
                table.reader.close()
        reader.close()
        return digest

    assert state_digest(negative_zero) == state_digest(positive_zero)


def test_snapshot_and_summary_documents_round_trip_and_validate_schema_digest() -> None:
    snapshot = Snapshot(
        snapshot_id="a" * 32,
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        parser_version=1,
        table_ruleset_version=1,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        snapshot_materialization_contract_version=1,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        materialization_stage=MaterializationStage.FINAL,
        snapshot_digest=raw_blob_digest(b"snapshot"),
        raw_state_digest=raw_blob_digest(b"raw-state"),
        created_at="2026-10-11T00:00:00Z",
        source_context=SnapshotSourceContext(
            source_kind=SourceKind.SQL_DUMP_SOURCE,
            sql_source_digest=raw_blob_digest(b"sql-source"),
        ),
    )
    table = _descriptor()
    summary = SnapshotSummary(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        raw_state_digest=snapshot.raw_state_digest,
        materialization_stage=snapshot.materialization_stage,
        parser_version=snapshot.parser_version,
        table_ruleset_version=snapshot.table_ruleset_version,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        table_count=1,
        tables=(table,),
        source_context=snapshot.source_context,
        diagnostics=(),
        row_count_total=table.row_count,
    )

    assert snapshot_from_document(snapshot_to_document(snapshot)) == snapshot
    summary_document = snapshot_summary_to_document(summary)
    assert (
        snapshot_summary_from_document(summary_document, snapshot=snapshot, tables=(table,))
        == summary
    )
    corrupted = {**summary_document, "canonical_state_digest": raw_blob_digest(b"wrong").value}
    with pytest.raises(ValueError, match="summary document"):
        snapshot_summary_from_document(corrupted, snapshot=snapshot, tables=(table,))
