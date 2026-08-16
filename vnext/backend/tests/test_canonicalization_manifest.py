"""Unit tests for identity-projection CanonicalizationManifest producer."""

from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from gateway_backend.canonicalization_cells import encode_cell, encode_row_cells
from gateway_backend.canonicalization_manifest import (
    AssembledTable,
    ManifestColumn,
    assemble_identity_canonicalization,
    canonicalization_manifest_digest,
    repository_import_manifest,
    table_content_digest,
    table_schema_digest,
)
from gateway_backend.repository_import_artifact import (
    MANIFEST_ENTRY_NAME,
    REPLAY_SQL_ENTRY_NAME,
    build_repository_import_package,
)
from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    NullScalar,
    RowField,
    StringScalar,
    Utf8LogicalLiteral,
    encode_collection,
    encode_row,
    encode_typed_scalar,
    normalize_logical_literal,
)

pytestmark = pytest.mark.unit

_ENUM_SQL = "ENUM('','active','paused')"
_SET_SQL = "SET('read','write','admin')"


def test_enum_null_and_empty_label_are_distinct() -> None:
    null_cell = encode_cell(_ENUM_SQL, None)
    empty_cell = encode_cell(_ENUM_SQL, "")
    active_cell = encode_cell(_ENUM_SQL, "active")
    expected_null = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.NULL), NullScalar()
    ).scalar_frame
    expected_empty = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.STRING),
        Utf8LogicalLiteral(text=""),
    ).scalar_frame
    assert null_cell == expected_null
    assert empty_cell == expected_empty
    assert null_cell != empty_cell
    assert active_cell != empty_cell


def test_set_null_empty_and_members_are_distinct() -> None:
    null_cell = encode_cell(_SET_SQL, None)
    empty_cell = encode_cell(_SET_SQL, [])
    members_cell = encode_cell(_SET_SQL, ["read", "write"])
    expected_null = encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.NULL), NullScalar()
    ).scalar_frame
    expected_empty = encode_collection(CollectionSemantics.SEQUENCE, items=()).collection_frame
    read = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.STRING), Utf8LogicalLiteral(text="read")
    ).scalar_frame
    write = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.STRING), Utf8LogicalLiteral(text="write")
    ).scalar_frame
    expected_members = encode_collection(
        CollectionSemantics.SEQUENCE, items=[read, write]
    ).collection_frame
    assert null_cell == expected_null
    assert empty_cell == expected_empty
    assert members_cell == expected_members
    assert null_cell != empty_cell
    assert empty_cell != members_cell


def test_set_cell_is_bare_sequence_not_encode_row() -> None:
    cell = encode_cell(_SET_SQL, ["admin"])
    admin = normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.STRING), Utf8LogicalLiteral(text="admin")
    ).scalar_frame
    sequence = encode_collection(CollectionSemantics.SEQUENCE, items=[admin]).collection_frame
    row = encode_row(
        [
            RowField(
                name="flags",
                declared_type=DeclaredType(kind=DeclaredTypeKind.STRING),
                typed_value=StringScalar(text="admin"),
            )
        ]
    )
    assert cell == sequence
    assert cell != row.row_frame
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "gateway_backend"
        / "canonicalization_cells.py"
    )
    text = source.read_text(encoding="utf-8")
    assert text.count("encode_row") == text.count("encode_row_cells")
    assert "encode_typed_scalar" in text
    assert "encode_collection" in text


def test_set_preserves_given_declaration_order() -> None:
    declared_order = encode_cell(_SET_SQL, ["write", "read"])
    reversed_order = encode_cell(_SET_SQL, ["read", "write"])
    assert declared_order != reversed_order


def test_schema_digest_includes_declaration_order() -> None:
    first = (
        ManifestColumn("status", "ENUM('a','b')", True),
        ManifestColumn("flags", "SET('x','y')", False),
    )
    swapped_enum = (
        ManifestColumn("status", "ENUM('b','a')", True),
        ManifestColumn("flags", "SET('x','y')", False),
    )
    digest_a = table_schema_digest(first, ("status",))
    digest_b = table_schema_digest(swapped_enum, ("status",))
    assert digest_a != digest_b
    assert digest_a == table_schema_digest(first, ("status",))


def test_content_digest_is_stable_and_counts_rows() -> None:
    columns = (
        ManifestColumn("id", "INT", False),
        ManifestColumn("status", _ENUM_SQL, True),
        ManifestColumn("flags", _SET_SQL, False),
    )
    rows: tuple[tuple[object, ...], ...] = (
        (1, None, []),
        (2, "active", ["read", "write"]),
    )
    framed = encode_row_cells(("INT", _ENUM_SQL, _SET_SQL), rows[1])
    assert encode_cell("INT", 2) in framed
    digest = table_content_digest(columns, rows, expected_row_count=2)
    again = table_content_digest(columns, list(rows), expected_row_count=2)
    assert digest == again
    assert digest.startswith("sha256:")
    with pytest.raises(ValueError, match="row count"):
        table_content_digest(columns, rows, expected_row_count=1)


def test_outer_digest_ignores_json_property_insertion_order() -> None:
    columns = (ManifestColumn("id", "INT", False),)
    table = AssembledTable(
        name="records",
        columns=columns,
        primary_key=("id",),
        row_count=0,
        schema_digest=table_schema_digest(columns, ("id",)),
        content_digest=table_content_digest(columns, (), expected_row_count=0),
    )
    source = "sha256:" + "ab" * 32
    assembled = assemble_identity_canonicalization(
        source_artifact_digest=source,
        tables=(table,),
    )
    shuffled = {
        "tables": assembled.document["tables"],
        "contract_version": assembled.document["contract_version"],
        "source_artifact_digest": assembled.document["source_artifact_digest"],
        "storage_projection_version": assembled.document["storage_projection_version"],
        "ruleset_id": assembled.document["ruleset_id"],
        "ruleset_version": assembled.document["ruleset_version"],
        "ruleset_digest": assembled.document["ruleset_digest"],
    }
    assert canonicalization_manifest_digest(shuffled) == assembled.digest
    package_manifest = repository_import_manifest(assembled)
    assert package_manifest["package_version"] == 1
    assert package_manifest["canonicalization_manifest_digest"] == assembled.digest


def test_keyless_content_digest_is_order_independent() -> None:
    columns = (ManifestColumn("note", "TEXT", True),)
    first = table_content_digest(
        columns,
        (("b",), ("a",), ("b",)),
        expected_row_count=3,
        unordered=True,
    )
    second = table_content_digest(
        columns,
        (("a",), ("b",), ("b",)),
        expected_row_count=3,
        unordered=True,
    )
    assert first == second


def test_keyless_table_uses_empty_primary_key() -> None:
    columns = (ManifestColumn("note", "TEXT", True),)
    table = AssembledTable(
        name="notes",
        columns=columns,
        primary_key=(),
        row_count=0,
        schema_digest=table_schema_digest(columns, ()),
        content_digest=table_content_digest(columns, (), expected_row_count=0, unordered=True),
    )
    assembled = assemble_identity_canonicalization(
        source_artifact_digest="sha256:" + "cd" * 32,
        tables=(table,),
    )
    assert assembled.tables[0].primary_key == ()


def test_tables_are_sorted_by_canonical_name_bytes() -> None:
    columns = (ManifestColumn("id", "INT", False),)
    schema = table_schema_digest(columns, ("id",))
    content = table_content_digest(columns, (), expected_row_count=0)

    def table(name: str) -> AssembledTable:
        return AssembledTable(
            name=name,
            columns=columns,
            primary_key=("id",),
            row_count=0,
            schema_digest=schema,
            content_digest=content,
        )

    assembled = assemble_identity_canonicalization(
        source_artifact_digest="sha256:" + "ef" * 32,
        tables=(table("zeta"), table("Alpha"), table("alpha")),
    )
    names = [item.name for item in assembled.tables]
    assert names == sorted(names, key=lambda item: item.encode("utf-8"))
    package_tables = repository_import_manifest(assembled)["tables"]
    assert isinstance(package_tables, list)
    manifest_names = [item["name"] for item in package_tables]
    assert manifest_names == names


def test_package_writer_is_reproducible_and_ustar_only() -> None:
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": "sha256:" + "11" * 32,
        "tables": [],
    }
    replay = b"CREATE TABLE records (id INT NOT NULL PRIMARY KEY);\n"
    first = build_repository_import_package(manifest=manifest, replay_sql=replay)
    second = build_repository_import_package(manifest=manifest, replay_sql=replay)
    assert first.payload == second.payload
    assert first.sha256 == second.sha256
    assert first.size_bytes == len(first.payload)
    assert first.sha256 == "sha256:" + hashlib.sha256(first.payload).hexdigest()

    with tarfile.open(fileobj=io.BytesIO(_decompress(first.payload)), mode="r:") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == [MANIFEST_ENTRY_NAME, REPLAY_SQL_ENTRY_NAME]
        for member in members:
            assert member.mtime == 0
            assert member.uid == 0
            assert member.gid == 0
            assert member.uname == ""
            assert member.gname == ""
            assert member.pax_headers == {}
            assert member.isfile()


def _decompress(payload: bytes) -> bytes:
    import compression.zstd

    return compression.zstd.decompress(payload)
