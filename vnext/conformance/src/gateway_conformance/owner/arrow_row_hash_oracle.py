"""Independent Arrow IPC → row-hash multiset oracle (shared-kernel only)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import (
    DeclaredType,
    DeclaredTypeKind,
    EncodedRow,
    NullScalar,
    RawLogicalLiteral,
    RowField,
    TypedScalar,
    Utf8LogicalLiteral,
    canonicalize_identifier,
    encode_row,
    normalize_logical_literal,
    unordered_row_hashes_content_digest,
    unordered_row_hashes_content_digest_from_sorted_row_buffer,
)

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.owner.arrow_mapping import (
    assert_batch_schema_matches,
    assert_no_trailing_ipc_bytes,
    cross_check_stream_schema,
)


from gateway_conformance.owner.arrow_mapping import declared_type_from_json


def format_decimal_from_unscaled(unscaled: int, scale: int) -> str:
    text = str(unscaled)
    negative = text.startswith("-")
    magnitude = text[1:] if negative else text
    trimmed = magnitude.lstrip("0")
    magnitude_digits = trimmed if trimmed else "0"
    is_zero = magnitude_digits == "0"
    if scale == 0:
        body = magnitude_digits
        return f"-{body}" if negative and not is_zero else body
    if len(magnitude_digits) <= scale:
        padded = magnitude_digits.rjust(scale + 1, "0")
    else:
        padded = magnitude_digits
    split_at = len(padded) - scale
    integer, fraction = padded[:split_at], padded[split_at:]
    integer = integer if integer else "0"
    fraction_trimmed = fraction.rstrip("0")
    canonical = integer if not fraction_trimmed else f"{integer}.{fraction_trimmed}"
    if negative and not is_zero:
        return f"-{canonical}"
    return canonical


def _is_null_at(column: pa.Array | pa.ChunkedArray, row_index: int) -> bool:
    null_mask = column.is_null()
    return bool(null_mask[row_index].as_py())


def decimal_unscaled_at_scale(value: Decimal, scale: int) -> int:
    quantized = value * (Decimal(10) ** scale)
    return int(quantized.to_integral_value())


def _extract_typed_scalar(
    declared: DeclaredType,
    nullable: bool,
    column: pa.Array | pa.ChunkedArray,
    row_index: int,
) -> TypedScalar:
    if _is_null_at(column, row_index):
        if not nullable:
            raise ConformanceValidationError("null value in non-nullable column")
        return NullScalar()

    if declared.kind is DeclaredTypeKind.BOOLEAN:
        value = column[row_index].as_py()
        if type(value) is not bool:
            raise ConformanceValidationError("boolean column value must be bool")
        literal: RawLogicalLiteral | Utf8LogicalLiteral = RawLogicalLiteral(
            raw_bytes=bytes([int(value)])
        )
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.SIGNED_INTEGER:
        literal = Utf8LogicalLiteral(text=str(int(column[row_index].as_py())))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.UNSIGNED_INTEGER:
        literal = Utf8LogicalLiteral(text=str(int(column[row_index].as_py())))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.STRING:
        literal = Utf8LogicalLiteral(text=str(column[row_index].as_py()))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.DECIMAL:
        scale = int(declared.scale or 0)
        as_decimal = column[row_index].as_py()
        if not isinstance(as_decimal, Decimal):
            raise ConformanceValidationError("decimal column must yield decimal.Decimal")
        unscaled = decimal_unscaled_at_scale(as_decimal, scale)
        literal = Utf8LogicalLiteral(text=format_decimal_from_unscaled(unscaled, scale))
        return normalize_logical_literal(declared, literal).typed_value
    raise ConformanceValidationError(f"oracle extraction unsupported for {declared.kind.value}")


def _encode_row_for_compute(fields: Sequence[RowField]) -> EncodedRow:
    adapted: list[RowField] = []
    for field in fields:
        if (
            isinstance(field.typed_value, NullScalar)
            and field.declared_type.kind is not DeclaredTypeKind.NULL
        ):
            adapted.append(
                RowField(
                    name=field.name,
                    declared_type=DeclaredType(kind=DeclaredTypeKind.NULL),
                    typed_value=field.typed_value,
                )
            )
        else:
            adapted.append(field)
    return encode_row(adapted)


def _bindings_for_batch(
    batch: pa.RecordBatch, declared_fields: list[dict[str, Any]]
) -> list[tuple[str, int, DeclaredType, bool]]:
    schema = batch.schema
    resolved: list[tuple[str, int, DeclaredType, bool]] = []
    for field_decl in declared_fields:
        name = str(field_decl["name"])
        nullable = bool(field_decl["nullable"])
        declared = declared_type_from_json(field_decl["semantic_type"])
        canonical = canonicalize_identifier(name)
        column_index = None
        for index in range(len(schema)):
            if canonicalize_identifier(schema.field(index).name) == canonical:
                column_index = index
                break
        if column_index is None:
            raise ConformanceValidationError("arrow schema missing declared field")
        resolved.append((canonical, column_index, declared, nullable))
    resolved.sort(key=lambda item: item[0])
    return resolved


def compute_row_hashes_from_ipc(
    ipc_bytes: bytes,
    declared_fields: list[dict[str, Any]],
) -> list[bytes]:
    buffer = io.BytesIO(ipc_bytes)
    reader = pa.ipc.open_stream(buffer)
    stream_schema = reader.schema
    cross_check_stream_schema(declared_fields, stream_schema)
    row_hashes: list[bytes] = []
    for batch in reader:
        assert_batch_schema_matches(stream_schema, batch.schema)
        if batch.num_rows == 0:
            continue
        bindings = _bindings_for_batch(batch, declared_fields)
        for row_index in range(batch.num_rows):
            fields: list[RowField] = []
            for canonical_name, column_index, declared, nullable in bindings:
                column = batch.column(column_index)
                typed_value = _extract_typed_scalar(declared, nullable, column, row_index)
                fields.append(
                    RowField(
                        name=canonical_name,
                        declared_type=declared,
                        typed_value=typed_value,
                    )
                )
            encoded = _encode_row_for_compute(fields)
            row_hashes.append(encoded.raw_hash)
    assert_no_trailing_ipc_bytes(ipc_bytes, buffer.tell())
    return row_hashes


def compute_table_content_identity(
    ipc_bytes: bytes,
    declared_fields: list[dict[str, Any]],
) -> tuple[str, str, list[bytes]]:
    """Return (row_count, raw_content_digest wire form, sorted row hashes)."""

    row_hashes = compute_row_hashes_from_ipc(ipc_bytes, declared_fields)
    row_count = str(len(row_hashes))
    sorted_hashes = sorted(row_hashes)
    buffer = bytearray()
    for row_hash in sorted_hashes:
        buffer.extend(row_hash)
    digest = unordered_row_hashes_content_digest_from_sorted_row_buffer(
        bytes(buffer),
        len(sorted_hashes),
    )
    return row_count, digest.digest_ref.value, sorted_hashes


def multiset_digest_differs_from_deduped(row_hashes: list[bytes]) -> bool:
    """True when duplicate row hashes change the multiset content digest."""

    if len(row_hashes) < 2:
        return False
    multiset = unordered_row_hashes_content_digest(row_hashes).digest_ref.value
    unique = unordered_row_hashes_content_digest(list(dict.fromkeys(row_hashes))).digest_ref.value
    return multiset != unique
