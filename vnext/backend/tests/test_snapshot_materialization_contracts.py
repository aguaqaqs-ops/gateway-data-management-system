"""Snapshot Materialization public contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.capabilities.snapshot_materialization import (
    normalize_sql_type_spelling,
    materialize_business_snapshot,
    materialize_repository_ref,
    materialize_sql_snapshot,
    open_snapshot_table_artifact,
    publish_snapshot_table_artifact,
    validate_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DIGEST_CONTRACT_VERSION,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
    CacheTrustLevel,
    MaterializationPolicy,
    MaterializationStage,
    SnapshotMaterializationStatus,
    SourceKind,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    RepositoryColumn,
    SnapshotColumnDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_backend.capabilities.table_access.contracts import SqlLogicalType, SqlSetValue

_OWNER = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "gateway_backend"
    / "capabilities"
    / "snapshot_materialization"
)
_FORBIDDEN = (
    "parse_sql",
    "parse_xml",
    "host_path",
    "dolt",
    "_sql_reader",
    "_sql_scan",
    "_sql_statements",
    "_sql_types",
    "_sql_values",
    "_xml_parser",
    "_parser_runtime",
)

SQL_TYPE_NORMALIZATION_CASES = (
    (" int(11) unsigned ", "INT UNSIGNED"),
    ("TINYINT(1)", "TINYINT"),
    ("FLOAT(12,5)", "FLOAT"),
    ("DATETIME(000)", "DATETIME"),
    ("decimal( 10, 2 )", "DECIMAL(10,2)"),
)

SET_DECODE_CASES = (
    (("admin", "read"), SqlSetValue(("read", "admin"))),
    (("write", "read"), SqlSetValue(("read", "write"))),
    ((), SqlSetValue(())),
)


def test_versions_and_orthogonal_labels_match_s0() -> None:
    assert SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION == 1
    assert DIGEST_CONTRACT_VERSION == 1
    assert SCALAR_ENCODING_VERSION == 1
    assert ROW_MATERIALIZATION_PROFILE == "sql-canonical-v1"
    assert SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION == 1
    assert SnapshotMaterializationStatus.COMPLETE.value == "COMPLETE"
    assert SnapshotMaterializationStatus.PARTIAL.value == "PARTIAL"
    assert SnapshotMaterializationStatus.FAILED.value == "FAILED"
    assert MaterializationStage.PROVISIONAL.value == "PROVISIONAL"
    assert MaterializationStage.FINAL.value == "FINAL"
    assert CacheTrustLevel.PROVISIONAL.value == "PROVISIONAL"
    assert CacheTrustLevel.CONTENT_VERIFIED.value == "CONTENT_VERIFIED"
    assert CacheTrustLevel.COMMIT_VALIDATED.value == "COMMIT_VALIDATED"
    assert MaterializationPolicy.DESCRIPTOR_ONLY.value == "DESCRIPTOR_ONLY"
    assert MaterializationPolicy.READERS_REQUIRED.value == "READERS_REQUIRED"
    assert MaterializationPolicy.ARTIFACTS_REQUIRED.value == "ARTIFACTS_REQUIRED"
    assert SourceKind.SQL_DUMP_SOURCE.value == "SQL_DUMP_SOURCE"
    assert SourceKind.IMMUTABLE_REPOSITORY_REF.value == "IMMUTABLE_REPOSITORY_REF"


def test_public_entry_exists_without_parser_or_host_path() -> None:
    assert callable(materialize_sql_snapshot)
    assert callable(materialize_business_snapshot)
    assert callable(materialize_repository_ref)
    assert callable(publish_snapshot_table_artifact)
    assert callable(open_snapshot_table_artifact)
    assert callable(validate_snapshot_table_artifact)
    for source in _OWNER.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            assert token not in text, f"{source} contains forbidden token {token}"


@pytest.mark.parametrize(("spelling", "expected"), SQL_TYPE_NORMALIZATION_CASES)
def test_snapshot_column_descriptor_normalizes_sql_type_spelling(
    spelling: str,
    expected: str,
) -> None:
    descriptor = SnapshotColumnDescriptor("value", "value", True, spelling)

    assert descriptor.scalar_type == expected
    assert normalize_sql_type_spelling(spelling) == expected


@pytest.mark.parametrize(("wire_members", "expected"), SET_DECODE_CASES)
def test_repository_set_decoding_uses_declared_label_order(
    wire_members: tuple[str, ...],
    expected: SqlSetValue,
) -> None:
    column = RepositoryColumn(
        name="flags",
        ordinal=0,
        scalar_type="SET('read','write','admin')",
        nullable=False,
    )
    mapped = map_repository_column(column)
    encoded = encode_repository_row((column,), (list(wire_members),), table="items")

    assert mapped.source.logical_type is SqlLogicalType.SET
    assert mapped.source.enum_or_set_labels == ("read", "write", "admin")
    assert encoded.cells == (expected,)
    assert encoded.diagnostics == ()
