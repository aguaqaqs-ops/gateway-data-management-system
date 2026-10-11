"""SQL Snapshot digest helpers owned by snapshot_materialization.

Uses Shared Kernel row/raw-content kinds for row hashes and raw_content_digest.
snapshot/compare-schema/fast-row/raw-state use owner JCS or domain-prefixed
frames plus raw_blob_digest. Does not import canonicalization_cells.
"""

from __future__ import annotations

import hashlib
from typing import Any

from gateway_shared_kernel import (
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    DigestRef,
    NullScalar,
    StringScalar,
    TypedScalar,
    canonicalize_identifier,
    encode_collection,
    encode_typed_scalar,
    raw_blob_digest,
    semantic_digest,
    unordered_row_hashes_content_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.uleb128 import encode_uleb128

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DIGEST_CONTRACT_VERSION,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    MaterializationStage,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import (
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SqlLogicalType,
    SqlSetValue,
)

_NULL_TYPE = DeclaredType(kind=DeclaredTypeKind.NULL)
_STRING_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)
_FAST_ROW_DOMAIN = b"gateway-vnext:snapshot-materialization:fast-row:v1\0"
_COMPARE_SCHEMA_KIND = "compare-schema"
_SNAPSHOT_KIND = "snapshot"
_RAW_STATE_KIND = "raw-state"


def encode_cell_frame(column: SourceColumnDescriptor, cell: SourceCell) -> bytes:
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(_NULL_TYPE, cell).scalar_frame
    if isinstance(cell, SqlSetValue):
        if column.logical_type is not SqlLogicalType.SET:
            raise ValueError("SqlSetValue requires a SET column")
        items = tuple(
            encode_typed_scalar(_STRING_TYPE, StringScalar(member)).scalar_frame
            for member in cell.members
        )
        return encode_collection(CollectionSemantics.SEQUENCE, items=items).collection_frame
    if not isinstance(cell, TypedScalar):
        raise ValueError("cell is not a SourceCell")
    if column.declared_type is None:
        raise ValueError("non-SET typed cell requires declared_type")
    return encode_typed_scalar(column.declared_type, cell).scalar_frame


def encode_row_frame(columns: tuple[SourceColumnDescriptor, ...], row: SourceRow) -> bytes:
    if len(row) != len(columns):
        raise ValueError("row width must match descriptor columns")
    prepared: list[tuple[bytes, bytes]] = []
    seen: set[bytes] = set()
    for column, cell in zip(columns, row, strict=True):
        name_utf8 = canonicalize_identifier(column.canonical_name).encode("utf-8")
        if name_utf8 in seen:
            raise ValueError("duplicate canonical column name in row encoding")
        seen.add(name_utf8)
        prepared.append((name_utf8, encode_cell_frame(column, cell)))
    prepared.sort(key=lambda item: item[0])
    parts = bytearray(encode_uleb128(len(prepared)))
    for name_utf8, cell_frame in prepared:
        parts.extend(encode_uleb128(len(name_utf8)))
        parts.extend(name_utf8)
        parts.extend(cell_frame)
    return bytes(parts)


def row_content_hash(columns: tuple[SourceColumnDescriptor, ...], row: SourceRow) -> bytes:
    return semantic_digest(DigestKind.ROW, encode_row_frame(columns, row)).raw_digest


def fast_row_hash(columns: tuple[SourceColumnDescriptor, ...], row: SourceRow) -> bytes:
    payload = b"".join(
        encode_cell_frame(column, cell) for column, cell in zip(columns, row, strict=True)
    )
    return hashlib.sha256(payload).digest()


def raw_content_digest_of(row_hashes: tuple[bytes, ...]) -> DigestRef:
    return unordered_row_hashes_content_digest(row_hashes).digest_ref


def fast_row_digest_of(row_hashes: tuple[bytes, ...]) -> DigestRef:
    frame = _unordered_hash_frame(row_hashes)
    return raw_blob_digest(_FAST_ROW_DOMAIN + frame)


def compare_schema_digest(
    canonical_table: str,
    column_names: tuple[str, ...],
    compare_key_columns: tuple[str, ...],
) -> DigestRef:
    payload = {
        "kind": _COMPARE_SCHEMA_KIND,
        "digest_contract_version": DIGEST_CONTRACT_VERSION,
        "scalar_encoding_version": SCALAR_ENCODING_VERSION,
        "canonical_table": canonical_table,
        "columns": sorted(column_names),
        "compare_key_columns": sorted(compare_key_columns),
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def snapshot_digest_of(
    *,
    stage: MaterializationStage,
    parser_version: int,
    table_ruleset_version: int,
    tables: tuple[SnapshotTableDescriptor, ...],
    composite_logic_source_digest: DigestRef | None = None,
    composite_signal_contract_version: int | None = None,
) -> DigestRef:
    payload: dict[str, Any] = {
        "kind": _SNAPSHOT_KIND,
        "digest_contract_version": DIGEST_CONTRACT_VERSION,
        "materialization_stage": stage.value,
        "parser_version": parser_version,
        "table_ruleset_version": table_ruleset_version,
        "scalar_encoding_version": SCALAR_ENCODING_VERSION,
        "snapshot_materialization_contract_version": SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
        "row_materialization_profile": ROW_MATERIALIZATION_PROFILE,
        "tables": [_table_digest_payload(table) for table in _sorted_tables(tables)],
    }
    if composite_logic_source_digest is not None:
        payload["composite_logic_source_digest"] = composite_logic_source_digest.value
        payload["composite_signal_contract_version"] = composite_signal_contract_version
    return raw_blob_digest(canonicalize_json_value(payload))


def raw_state_digest_of(tables: tuple[SnapshotTableDescriptor, ...]) -> DigestRef:
    payload = {
        "kind": _RAW_STATE_KIND,
        "digest_contract_version": DIGEST_CONTRACT_VERSION,
        "tables": [
            {
                "canonical_table": table.table_name,
                "row_count": table.row_count,
                "raw_content_digest": _digest_value(table.raw_content_digest),
                "fast_row_digest": _digest_value(table.fast_row_digest),
            }
            for table in _sorted_tables(tables)
        ],
    }
    return raw_blob_digest(canonicalize_json_value(payload))


def cell_count_key(column: SourceColumnDescriptor, cell: SourceCell) -> str | None:
    if isinstance(cell, NullScalar):
        return None
    return encode_cell_frame(column, cell).hex()


def _table_digest_payload(table: SnapshotTableDescriptor) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "canonical_table_name": table.table_name,
        "compare_schema_digest": table.compare_schema_digest.value,
        "row_count": table.row_count,
        "raw_content_digest": _digest_value(table.raw_content_digest),
        "fast_row_digest": _digest_value(table.fast_row_digest),
        "business_schema_digest": table.business_schema_digest.value,
        "compare_key_columns": list(table.compare_key_columns),
    }
    return payload


def _sorted_tables(
    tables: tuple[SnapshotTableDescriptor, ...],
) -> tuple[SnapshotTableDescriptor, ...]:
    return tuple(sorted(tables, key=lambda item: item.table_name.encode("utf-8")))


def _digest_value(digest: DigestRef | None) -> str | None:
    if digest is None:
        return None
    return digest.value


def _unordered_hash_frame(row_hashes: tuple[bytes, ...]) -> bytes:
    hashes = list(row_hashes)
    hashes.sort()
    parts = bytearray(encode_uleb128(len(hashes)))
    for item in hashes:
        if len(item) != 32:
            raise ValueError("row hash must be exactly 32 bytes")
        parts.extend(item)
    return bytes(parts)
