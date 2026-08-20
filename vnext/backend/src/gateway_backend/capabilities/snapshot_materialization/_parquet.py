"""Private Parquet encode/decode for SnapshotTableArtifact rows.

Public consumers use SnapshotTableReader and opaque ArtifactRef only.
"""

from __future__ import annotations

import io
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DecimalScalar,
    DeclaredType,
    DeclaredTypeKind,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.snapshot_materialization.batch import (
    schema_with_batch_metadata,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTableBatchMetadata,
)

from gateway_backend.capabilities.table_access.contracts import (
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
    SqlLogicalType,
    SqlSetValue,
)

_ENCODING_METADATA_KEY = b"gateway.sta.enc.v1"
_PHYS_BOOL = "bool"
_PHYS_UTF8 = "utf8"
_PHYS_BINARY = "binary"
_PHYS_LIST_UTF8 = "list_utf8"


def physical_type_for(column: SourceColumnDescriptor) -> str:
    if column.logical_type is SqlLogicalType.SET:
        return _PHYS_LIST_UTF8
    declared = column.declared_type
    if declared is None:
        return _PHYS_UTF8
    if declared.kind is DeclaredTypeKind.BOOLEAN:
        return _PHYS_BOOL
    if declared.kind in {DeclaredTypeKind.BINARY, DeclaredTypeKind.BIT}:
        return _PHYS_BINARY
    return _PHYS_UTF8


def export_schema_payload(columns: tuple[SourceColumnDescriptor, ...]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for column in columns:
        items.append(
            {
                "canonical_name": column.canonical_name,
                "physical_type": physical_type_for(column),
                "nullable": column.nullable,
            }
        )
    items.sort(key=lambda item: str(item["canonical_name"]))
    return items


def encode_source_columns(columns: tuple[SourceColumnDescriptor, ...]) -> bytes:
    payload = {
        "columns": [_column_payload(column) for column in columns],
    }
    return canonicalize_json_value(payload)


def decode_source_columns(raw: bytes) -> tuple[SourceColumnDescriptor, ...]:
    import json

    payload = json.loads(raw.decode("utf-8"))
    if type(payload) is not dict:
        raise ValueError("encoding schema must be an object")
    columns = payload.get("columns")
    if type(columns) is not list:
        raise ValueError("encoding schema columns must be a list")
    decoded: list[SourceColumnDescriptor] = []
    for index, item in enumerate(columns):
        if type(item) is not dict:
            raise ValueError("encoding schema column must be an object")
        decoded.append(_column_from_payload(item, index))
    return tuple(decoded)


def write_parquet_rows(
    columns: tuple[SourceColumnDescriptor, ...],
    rows: tuple[SourceRow, ...],
) -> bytes:
    fields = [_arrow_field(column) for column in columns]
    metadata = {_ENCODING_METADATA_KEY: encode_source_columns(columns)}
    schema = schema_with_batch_metadata(
        pa.schema(fields, metadata=metadata),
        SnapshotTableBatchMetadata(),
    )
    arrays = [_column_array(column, rows, index) for index, column in enumerate(columns)]
    table = pa.Table.from_arrays(arrays, schema=schema)
    sink = io.BytesIO()
    pq.write_table(
        table,
        sink,
        compression="zstd",
        write_statistics=False,
        use_dictionary=False,
        store_schema=True,
    )
    return sink.getvalue()


def read_parquet_table(raw_bytes: bytes) -> pa.Table:
    try:
        return pq.read_table(pa.BufferReader(raw_bytes))
    except (OSError, pa.ArrowInvalid, ValueError) as exc:
        raise ValueError("parquet rows are truncated or unreadable") from exc


def encoding_columns_from_table(table: pa.Table) -> tuple[SourceColumnDescriptor, ...]:
    metadata = table.schema.metadata
    if not metadata or _ENCODING_METADATA_KEY not in metadata:
        raise ValueError("parquet schema is missing encoding metadata")
    return decode_source_columns(metadata[_ENCODING_METADATA_KEY])


def iter_decoded_rows(
    table: pa.Table,
    columns: tuple[SourceColumnDescriptor, ...],
) -> tuple[SourceRow, ...]:
    names = [column.canonical_name for column in columns]
    if list(table.column_names) != names:
        raise ValueError("parquet schema columns do not match encoding schema")
    decoded: list[SourceRow] = []
    for batch in table.to_batches():
        width = len(columns)
        pylons = [batch.column(index).to_pylist() for index in range(width)]
        for row_index in range(batch.num_rows):
            cells: list[SourceCell] = []
            for col_index, column in enumerate(columns):
                cells.append(_arrow_to_cell(pylons[col_index][row_index], column))
            decoded.append(tuple(cells))
    return tuple(decoded)


def source_descriptor_for(
    snapshot_table_name: str,
    display_table_name: str,
    columns: tuple[SourceColumnDescriptor, ...],
    primary_key_columns: tuple[str, ...],
) -> SourceTableDescriptor:
    ordered = tuple(
        SourceColumnDescriptor(
            display_name=column.display_name,
            canonical_name=column.canonical_name,
            ordinal=index,
            sql_type=column.sql_type,
            logical_type=column.logical_type,
            declared_type=column.declared_type,
            nullable=column.nullable,
            enum_or_set_labels=column.enum_or_set_labels,
        )
        for index, column in enumerate(columns)
    )
    return SourceTableDescriptor(
        display_name=display_table_name,
        canonical_name=snapshot_table_name,
        columns=ordered,
        primary_key_canonical_names=primary_key_columns,
        reader_ready=True,
    )


def _column_payload(column: SourceColumnDescriptor) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "canonical_name": column.canonical_name,
        "display_name": column.display_name,
        "ordinal": column.ordinal,
        "sql_type": column.sql_type,
        "logical_type": column.logical_type.value,
        "nullable": column.nullable,
        "physical_type": physical_type_for(column),
        "declared_type": _declared_payload(column.declared_type),
        "enum_or_set_labels": (
            None if column.enum_or_set_labels is None else list(column.enum_or_set_labels)
        ),
    }
    return payload


def _column_from_payload(item: dict[str, Any], ordinal: int) -> SourceColumnDescriptor:
    labels = item.get("enum_or_set_labels")
    enum_labels: tuple[str, ...] | None
    if labels is None:
        enum_labels = None
    elif type(labels) is list and all(type(label) is str for label in labels):
        enum_labels = tuple(labels)
    else:
        raise ValueError("enum_or_set_labels must be a string list or null")
    return SourceColumnDescriptor(
        display_name=str(item["display_name"]),
        canonical_name=str(item["canonical_name"]),
        ordinal=int(item.get("ordinal", ordinal)),
        sql_type=str(item["sql_type"]),
        logical_type=SqlLogicalType(str(item["logical_type"])),
        declared_type=_declared_from_payload(item.get("declared_type")),
        nullable=bool(item["nullable"]),
        enum_or_set_labels=enum_labels,
    )


def _declared_payload(declared: DeclaredType | None) -> dict[str, object] | None:
    if declared is None:
        return None
    payload: dict[str, object] = {"kind": declared.kind.value}
    if declared.bits is not None:
        payload["bits"] = declared.bits
    if declared.precision is not None:
        payload["precision"] = declared.precision
    if declared.scale is not None:
        payload["scale"] = declared.scale
    if declared.bit_width is not None:
        payload["bit_width"] = declared.bit_width
    return payload


def _declared_from_payload(payload: object) -> DeclaredType | None:
    if payload is None:
        return None
    if type(payload) is not dict:
        raise ValueError("declared_type must be an object or null")
    kind = DeclaredTypeKind(str(payload["kind"]))
    return DeclaredType(
        kind=kind,
        bits=_optional_int(payload.get("bits")),
        precision=_optional_int(payload.get("precision")),
        scale=_optional_int(payload.get("scale")),
        bit_width=_optional_int(payload.get("bit_width")),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError("declared type numeric fields must be integers")
    return value


def _arrow_field(column: SourceColumnDescriptor) -> pa.Field:
    physical = physical_type_for(column)
    if physical == _PHYS_BOOL:
        arrow_type: pa.DataType = pa.bool_()
    elif physical == _PHYS_BINARY:
        arrow_type = pa.binary()
    elif physical == _PHYS_LIST_UTF8:
        arrow_type = pa.list_(pa.string())
    else:
        arrow_type = pa.string()
    return pa.field(column.canonical_name, arrow_type, nullable=True)


def _column_array(
    column: SourceColumnDescriptor,
    rows: tuple[SourceRow, ...],
    index: int,
) -> pa.Array:
    values = [_cell_to_arrow(row[index], column) for row in rows]
    return pa.array(values, type=_arrow_field(column).type)


def _cell_to_arrow(cell: SourceCell, column: SourceColumnDescriptor) -> object:
    if isinstance(cell, NullScalar):
        return None
    physical = physical_type_for(column)
    if physical == _PHYS_BOOL:
        if not isinstance(cell, BooleanScalar):
            raise ValueError("boolean column requires BooleanScalar")
        return cell.value
    if physical == _PHYS_BINARY:
        if isinstance(cell, BinaryScalar):
            return cell.raw_bytes
        if isinstance(cell, BitScalar):
            return cell.raw_bytes
        raise ValueError("binary column requires BinaryScalar or BitScalar")
    if physical == _PHYS_LIST_UTF8:
        if not isinstance(cell, SqlSetValue):
            raise ValueError("SET column requires SqlSetValue")
        return list(cell.members)
    return _scalar_text(cell)


def _scalar_text(cell: SourceCell) -> str:
    if isinstance(cell, StringScalar):
        return cell.text
    if isinstance(cell, SignedIntegerScalar):
        return cell.decimal
    if isinstance(cell, UnsignedIntegerScalar):
        return cell.decimal
    if isinstance(cell, DecimalScalar):
        return cell.decimal
    if isinstance(cell, Float32Scalar):
        return cell.bits_hex
    if isinstance(cell, Float64Scalar):
        return cell.bits_hex
    if isinstance(cell, DateScalar):
        return cell.text
    if isinstance(cell, DateTimeScalar):
        return cell.text
    if isinstance(cell, TimestampScalar):
        return cell.text
    if isinstance(cell, TimeDurationScalar):
        return cell.text
    if isinstance(cell, BooleanScalar):
        return "true" if cell.value else "false"
    raise ValueError("unsupported scalar for utf8 parquet encoding")


def _arrow_to_cell(value: object, column: SourceColumnDescriptor) -> SourceCell:
    if value is None:
        return NullScalar()
    if column.logical_type is SqlLogicalType.SET:
        if not isinstance(value, list):
            raise ValueError("SET parquet value must be a list")
        members = tuple(str(item) for item in value)
        return SqlSetValue(members=members)
    declared = column.declared_type
    if declared is None:
        return StringScalar(text=str(value))
    if declared.kind is DeclaredTypeKind.BOOLEAN:
        return BooleanScalar(value=bool(value))
    if declared.kind is DeclaredTypeKind.BINARY:
        return BinaryScalar(raw_bytes=_as_bytes(value))
    if declared.kind is DeclaredTypeKind.BIT:
        return BitScalar(raw_bytes=_as_bytes(value))
    text = value if type(value) is str else str(value)
    if declared.kind is DeclaredTypeKind.SIGNED_INTEGER:
        return SignedIntegerScalar(decimal=text)
    if declared.kind is DeclaredTypeKind.UNSIGNED_INTEGER:
        return UnsignedIntegerScalar(decimal=text)
    if declared.kind is DeclaredTypeKind.DECIMAL:
        return DecimalScalar(decimal=text)
    if declared.kind is DeclaredTypeKind.FLOAT32:
        return Float32Scalar(bits_hex=text)
    if declared.kind is DeclaredTypeKind.FLOAT64:
        return Float64Scalar(bits_hex=text)
    if declared.kind is DeclaredTypeKind.DATE:
        return DateScalar(text=text)
    if declared.kind is DeclaredTypeKind.DATETIME:
        return DateTimeScalar(text=text)
    if declared.kind is DeclaredTypeKind.TIMESTAMP:
        return TimestampScalar(text=text)
    if declared.kind is DeclaredTypeKind.TIME_DURATION:
        return TimeDurationScalar(text=text)
    if declared.kind is DeclaredTypeKind.STRING:
        return StringScalar(text=text)
    return StringScalar(text=text)


def _as_bytes(value: object) -> bytes:
    if type(value) is bytes:
        return value
    if type(value) is bytearray:
        return bytes(value)
    if isinstance(value, memoryview):
        return bytes(value)
    raise ValueError("binary parquet value must be bytes")
