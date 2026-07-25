"""Independent Arrow IPC → row-hash multiset oracle (shared-kernel only)."""

from __future__ import annotations

import io
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import (
    AnomalyScalar,
    DeclaredType,
    DeclaredTypeKind,
    EncodedRow,
    NullScalar,
    RawLogicalLiteral,
    RowField,
    TypedScalar,
    Utf8LogicalLiteral,
    canonicalize_identifier,
    canonicalize_jcs,
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

_ANOMALY_ENVELOPE_KEYS = frozenset({"declared_type", "raw_base64url", "raw_encoding", "reason"})


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


def _format_float32(value: float) -> str:
    if value == 0.0 and math.copysign(1.0, value) < 0:
        return "-0"
    return str(value)


def _format_float64(value: float) -> str:
    if value == 0.0 and math.copysign(1.0, value) < 0:
        return "-0"
    return str(value)


def _civil_from_days(days: int) -> tuple[int, int, int]:
    z = days + 719_468
    era = z // 146_097 if z >= 0 else (z - 146_096) // 146_097
    doe = z - era * 146_097
    yoe = (doe - doe // 1_460 + doe // 36_524 - doe // 146_096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + (3 if mp < 10 else -9)
    year = y + (1 if month <= 2 else 0)
    if year < 1:
        raise ConformanceValidationError("date civil year out of range")
    return int(year), int(month), int(day)


def _days_to_date(days: int) -> str:
    year, month, day = _civil_from_days(days)
    return f"{year:04}-{month:02}-{day:02}"


def _format_fraction(micro: int) -> str:
    if micro == 0:
        return ""
    raw = f".{micro:06}"
    return raw.rstrip("0")


def _civil_from_micros(micros: int) -> tuple[int, int, int, int, int, int, int]:
    days = micros // 86_400_000_000
    day_micros = micros % 86_400_000_000
    year, month, day = _civil_from_days(days)
    total_seconds = day_micros // 1_000_000
    micro = day_micros % 1_000_000
    hour = total_seconds // 3600
    minute = (total_seconds % 3600) // 60
    second = total_seconds % 60
    return year, month, day, hour, minute, second, micro


def _micros_to_datetime(micros: int) -> str:
    year, month, day, hour, minute, second, micro = _civil_from_micros(micros)
    fraction = _format_fraction(micro)
    return f"{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction}"


def _micros_to_timestamp(micros: int) -> str:
    year, month, day, hour, minute, second, micro = _civil_from_micros(micros)
    fraction = _format_fraction(micro)
    return f"{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}{fraction}Z"


def _micros_to_duration(micros: int) -> str:
    negative = micros < 0
    abs_micros = abs(micros)
    total_seconds = abs_micros // 1_000_000
    micro = abs_micros % 1_000_000
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    fraction = _format_fraction(micro)
    body = f"{hours:02}:{minutes:02}:{seconds:02}{fraction}"
    return f"-{body}" if negative else body


def _parse_anomaly_declared_type(value: Mapping[str, Any]) -> DeclaredType:
    keys = set(value.keys())
    kind = str(value["kind"])
    if kind in {
        "null",
        "boolean",
        "float32",
        "float64",
        "string",
        "binary",
        "date",
        "datetime",
        "timestamp",
        "time-duration",
        "source-literal-anomaly",
    }:
        if keys != {"kind"}:
            raise ConformanceValidationError("anomaly declared_type keys mismatch")
    elif kind in {"signed-integer", "unsigned-integer"}:
        if keys != {"kind", "bits"}:
            raise ConformanceValidationError("anomaly declared_type keys mismatch")
    elif kind == "decimal":
        if keys != {"kind", "precision", "scale"}:
            raise ConformanceValidationError("anomaly declared_type keys mismatch")
    elif kind == "bit":
        if keys != {"kind", "bit_width"}:
            raise ConformanceValidationError("anomaly declared_type keys mismatch")
    else:
        raise ConformanceValidationError("anomaly declared_type kind unsupported")
    return declared_type_from_json(dict(value))


def _extract_anomaly(column: pa.Array | pa.ChunkedArray, row_index: int) -> AnomalyScalar:
    raw = column[row_index].as_py()
    if not isinstance(raw, (bytes, bytearray)):
        raise ConformanceValidationError("anomaly column must yield bytes")
    try:
        canonical = canonicalize_jcs(bytes(raw))
    except Exception as exc:
        raise ConformanceValidationError("anomaly envelope JCS invalid") from exc
    try:
        root = json.loads(canonical)
    except json.JSONDecodeError as exc:
        raise ConformanceValidationError("anomaly envelope must be JSON object") from exc
    if not isinstance(root, dict):
        raise ConformanceValidationError("anomaly envelope must be JSON object")
    if set(root.keys()) != _ANOMALY_ENVELOPE_KEYS:
        raise ConformanceValidationError("anomaly envelope keys mismatch")
    declared_raw = root["declared_type"]
    if not isinstance(declared_raw, dict):
        raise ConformanceValidationError("anomaly declared_type must be object")
    _parse_anomaly_declared_type(declared_raw)
    for key in ("raw_base64url", "raw_encoding", "reason"):
        if not isinstance(root[key], str):
            raise ConformanceValidationError(f"anomaly {key} must be string")
    return AnomalyScalar(envelope=dict(root))


def _physical_int_at(column: pa.Array | pa.ChunkedArray, row_index: int) -> int:
    scalar = column[row_index]
    value = getattr(scalar, "value", None)
    if isinstance(value, int):
        return value
    raise ConformanceValidationError("column physical value must be integer-backed")


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

    if declared.kind is DeclaredTypeKind.SOURCE_LITERAL_ANOMALY:
        return _extract_anomaly(column, row_index)

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
    if declared.kind is DeclaredTypeKind.FLOAT32:
        value = float(column[row_index].as_py())
        if not math.isfinite(value):
            raise ConformanceValidationError("float32 must be finite")
        literal = Utf8LogicalLiteral(text=_format_float32(value))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.FLOAT64:
        value = float(column[row_index].as_py())
        if not math.isfinite(value):
            raise ConformanceValidationError("float64 must be finite")
        literal = Utf8LogicalLiteral(text=_format_float64(value))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind in {DeclaredTypeKind.BINARY, DeclaredTypeKind.BIT}:
        raw = column[row_index].as_py()
        if not isinstance(raw, (bytes, bytearray)):
            raise ConformanceValidationError("binary column must yield bytes")
        literal = RawLogicalLiteral(raw_bytes=bytes(raw))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.DATE:
        days = _physical_int_at(column, row_index)
        literal = Utf8LogicalLiteral(text=_days_to_date(days))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.DATETIME:
        micros = _physical_int_at(column, row_index)
        literal = Utf8LogicalLiteral(text=_micros_to_datetime(micros))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.TIMESTAMP:
        micros = _physical_int_at(column, row_index)
        literal = Utf8LogicalLiteral(text=_micros_to_timestamp(micros))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.TIME_DURATION:
        micros = _physical_int_at(column, row_index)
        literal = Utf8LogicalLiteral(text=_micros_to_duration(micros))
        return normalize_logical_literal(declared, literal).typed_value
    if declared.kind is DeclaredTypeKind.NULL:
        raise ConformanceValidationError("null kind column must be null at slot")
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
