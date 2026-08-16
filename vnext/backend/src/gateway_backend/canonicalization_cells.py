"""Storage Projection cell encoding for CanonicalizationManifest content bytes.

ENUM/SET content follows Shared Canonical Encoding §3.2. This module is the
production assembler path: it calls Shared Kernel ``encode_typed_scalar`` and
``encode_collection(SEQUENCE)``. It must not call the Shared Kernel row encoder.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
import struct
from collections.abc import Sequence
from math import isfinite
from typing import Any

from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    CollectionSemantics,
    DeclaredType,
    DeclaredTypeKind,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    Utf8LogicalLiteral,
    encode_collection,
    encode_typed_scalar,
    normalize_logical_literal,
)

_INTEGER_TYPES: dict[str, tuple[DeclaredTypeKind, int]] = {
    "TINYINT": (DeclaredTypeKind.SIGNED_INTEGER, 8),
    "TINYINT UNSIGNED": (DeclaredTypeKind.UNSIGNED_INTEGER, 8),
    "SMALLINT": (DeclaredTypeKind.SIGNED_INTEGER, 16),
    "SMALLINT UNSIGNED": (DeclaredTypeKind.UNSIGNED_INTEGER, 16),
    "MEDIUMINT": (DeclaredTypeKind.SIGNED_INTEGER, 24),
    "MEDIUMINT UNSIGNED": (DeclaredTypeKind.UNSIGNED_INTEGER, 24),
    "INT": (DeclaredTypeKind.SIGNED_INTEGER, 32),
    "INT UNSIGNED": (DeclaredTypeKind.UNSIGNED_INTEGER, 32),
    "BIGINT": (DeclaredTypeKind.SIGNED_INTEGER, 64),
    "BIGINT UNSIGNED": (DeclaredTypeKind.UNSIGNED_INTEGER, 64),
}
_CHARACTER = {
    "CHAR",
    "VARCHAR",
    "TINYTEXT",
    "TEXT",
    "MEDIUMTEXT",
    "LONGTEXT",
    "JSON",
}
_BINARY = {
    "BINARY",
    "VARBINARY",
    "TINYBLOB",
    "BLOB",
    "MEDIUMBLOB",
    "LONGBLOB",
}
_SIZED_CHARACTER = re.compile(r"^(CHAR|VARCHAR)\(\d+\)$")
_SIZED_BINARY = re.compile(r"^(BINARY|VARBINARY)\(\d+\)$")
_DECIMAL = re.compile(r"^DECIMAL\((\d+),(\d+)\)$")
_BIT = re.compile(r"^BIT\((\d+)\)$")
_TEMPORAL = re.compile(r"^(TIME|DATETIME|TIMESTAMP)(?:\((\d+)\))?$")
_SPATIAL = re.compile(
    r"^(GEOMETRY|POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|"
    r"MULTIPOLYGON|GEOMETRYCOLLECTION)(?:\s+SRID\s+\d+)?$"
)
_STRING_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)
_NULL_TYPE = DeclaredType(kind=DeclaredTypeKind.NULL)


class CanonicalizationCellError(ValueError):
    """Raised when a catalog value cannot be encoded as a v1 content cell."""


def encode_cell(sql_type: str, value: object) -> bytes:
    """Encode one identity-projection cell as CanonicalizationManifest bytes."""

    if type(sql_type) is not str or sql_type == "":
        raise CanonicalizationCellError("sql_type must be a non-empty str")
    upper = sql_type.upper()
    if upper.startswith("ENUM("):
        return _encode_enum_cell(value)
    if upper.startswith("SET("):
        return _encode_set_cell(value)
    if _SPATIAL.fullmatch(upper) is not None:
        raise CanonicalizationCellError(f"spatial SQL type is not mapped: {sql_type}")
    if value is None:
        return encode_typed_scalar(_NULL_TYPE, NullScalar()).scalar_frame
    if upper == "BOOLEAN":
        return _encode_boolean_cell(value)
    integer = _INTEGER_TYPES.get(upper)
    if integer is not None:
        return _encode_integer_cell(integer[0], integer[1], value)
    if upper == "FLOAT":
        return _encode_float_cell(value, width=32)
    if upper == "DOUBLE":
        return _encode_float_cell(value, width=64)
    decimal_match = _DECIMAL.fullmatch(upper)
    if decimal_match is not None:
        return _encode_decimal_cell(
            int(decimal_match.group(1)),
            int(decimal_match.group(2)),
            value,
        )
    bit_match = _BIT.fullmatch(upper)
    if bit_match is not None:
        return _encode_bit_cell(int(bit_match.group(1)), value)
    if upper == "DATE":
        return _encode_date_cell(value)
    temporal = _TEMPORAL.fullmatch(upper)
    if temporal is not None:
        kind = temporal.group(1)
        if kind == "TIME":
            return _encode_time_cell(value)
        if kind == "TIMESTAMP":
            return _encode_timestamp_cell(value)
        return _encode_datetime_cell(value)
    if upper in _CHARACTER or _SIZED_CHARACTER.fullmatch(upper) is not None:
        return _encode_string_cell(value)
    if upper in _BINARY or _SIZED_BINARY.fullmatch(upper) is not None:
        return _encode_binary_cell(value)
    raise CanonicalizationCellError(f"unsupported SQL type for content encoding: {sql_type}")


def _encode_enum_cell(value: object) -> bytes:
    if value is None:
        return encode_typed_scalar(_NULL_TYPE, NullScalar()).scalar_frame
    if type(value) is not str:
        raise CanonicalizationCellError("ENUM value must be str or None")
    return normalize_logical_literal(_STRING_TYPE, Utf8LogicalLiteral(text=value)).scalar_frame


def _encode_set_cell(value: object) -> bytes:
    if value is None:
        return encode_typed_scalar(_NULL_TYPE, NullScalar()).scalar_frame
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CanonicalizationCellError("SET value must be a sequence of labels or None")
    item_frames: list[bytes] = []
    for index, item in enumerate(value):
        if type(item) is not str:
            raise CanonicalizationCellError(f"SET member {index} must be str")
        item_frames.append(
            normalize_logical_literal(_STRING_TYPE, Utf8LogicalLiteral(text=item)).scalar_frame
        )
    return encode_collection(CollectionSemantics.SEQUENCE, items=item_frames).collection_frame


def _encode_boolean_cell(value: object) -> bytes:
    if type(value) is not bool:
        raise CanonicalizationCellError("BOOLEAN value must be bool")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.BOOLEAN),
        Utf8LogicalLiteral(text="true" if value else "false"),
    ).scalar_frame


def _encode_integer_cell(kind: DeclaredTypeKind, bits: int, value: object) -> bytes:
    if type(value) is not int or type(value) is bool:
        raise CanonicalizationCellError("integer value must be int")
    return normalize_logical_literal(
        DeclaredType(kind=kind, bits=bits),
        Utf8LogicalLiteral(text=str(value)),
    ).scalar_frame


def _encode_float_cell(value: object, *, width: int) -> bytes:
    if type(value) is bool or type(value) is not float:
        if isinstance(value, decimal.Decimal):
            number = float(value)
        else:
            raise CanonicalizationCellError("float value must be float")
    else:
        number = value
    if not isfinite(number):
        raise CanonicalizationCellError("float value must be finite")
    if width == 32:
        packed = struct.pack(">f", number)
        bits = struct.unpack(">I", packed)[0]
        rounded = struct.unpack(">f", packed)[0]
        if not isfinite(rounded):
            raise CanonicalizationCellError("float32 packing produced non-finite")
        if bits == 0x80000000:
            bits = 0
        return encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.FLOAT32),
            Float32Scalar(bits_hex=f"{bits:08x}"),
        ).scalar_frame
    packed = struct.pack(">d", number)
    bits = struct.unpack(">Q", packed)[0]
    if bits == 0x8000000000000000:
        bits = 0
    return encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.FLOAT64),
        Float64Scalar(bits_hex=f"{bits:016x}"),
    ).scalar_frame


def _encode_decimal_cell(precision: int, scale: int, value: object) -> bytes:
    if isinstance(value, decimal.Decimal):
        text = format(value, "f")
    elif type(value) is str:
        text = value
    else:
        raise CanonicalizationCellError("DECIMAL value must be Decimal or str")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=precision, scale=scale),
        Utf8LogicalLiteral(text=text),
    ).scalar_frame


def _encode_bit_cell(width: int, value: object) -> bytes:
    raw = _as_bytes(value, "BIT")
    return encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=width),
        BitScalar(raw_bytes=raw),
    ).scalar_frame


def _encode_date_cell(value: object) -> bytes:
    if isinstance(value, dt.datetime):
        text = value.date().isoformat()
    elif isinstance(value, dt.date):
        text = value.isoformat()
    elif type(value) is str:
        text = value
    else:
        raise CanonicalizationCellError("DATE value must be date or str")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.DATE),
        Utf8LogicalLiteral(text=text),
    ).scalar_frame


def _encode_datetime_cell(value: object) -> bytes:
    if isinstance(value, dt.datetime):
        text = _format_civil_datetime(value)
    elif type(value) is str:
        text = value.replace(" ", "T")
    else:
        raise CanonicalizationCellError("DATETIME value must be datetime or str")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.DATETIME),
        Utf8LogicalLiteral(text=text),
    ).scalar_frame


def _encode_timestamp_cell(value: object) -> bytes:
    if isinstance(value, dt.datetime):
        instant = value
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=dt.timezone.utc)
        else:
            instant = instant.astimezone(dt.timezone.utc)
        text = _format_civil_datetime(instant) + "Z"
    elif type(value) is str:
        text = value.replace(" ", "T")
        if not text.endswith("Z"):
            text += "Z"
    else:
        raise CanonicalizationCellError("TIMESTAMP value must be datetime or str")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.TIMESTAMP),
        Utf8LogicalLiteral(text=text),
    ).scalar_frame


def _encode_time_cell(value: object) -> bytes:
    if isinstance(value, dt.timedelta):
        text = _format_time_duration(value)
    elif type(value) is str:
        text = value
    else:
        raise CanonicalizationCellError("TIME value must be timedelta or str")
    return normalize_logical_literal(
        DeclaredType(kind=DeclaredTypeKind.TIME_DURATION),
        Utf8LogicalLiteral(text=text),
    ).scalar_frame


def _encode_string_cell(value: object) -> bytes:
    if type(value) is not str:
        raise CanonicalizationCellError("string value must be str")
    return normalize_logical_literal(_STRING_TYPE, Utf8LogicalLiteral(text=value)).scalar_frame


def _encode_binary_cell(value: object) -> bytes:
    raw = _as_bytes(value, "binary")
    return encode_typed_scalar(
        DeclaredType(kind=DeclaredTypeKind.BINARY),
        BinaryScalar(raw_bytes=raw),
    ).scalar_frame


def _as_bytes(value: object, label: str) -> bytes:
    if type(value) is bytes:
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    raise CanonicalizationCellError(f"{label} value must be bytes")


def _format_civil_datetime(value: dt.datetime) -> str:
    base = (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        f"T{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    )
    if value.microsecond == 0:
        return base
    fraction = f"{value.microsecond:06d}".rstrip("0")
    return f"{base}.{fraction}"


def _format_time_duration(delta: dt.timedelta) -> str:
    total_us = (
        delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    )
    negative = total_us < 0
    total_us = abs(total_us)
    hours, rem = divmod(total_us, 3_600_000_000)
    minutes, rem = divmod(rem, 60_000_000)
    seconds, microseconds = divmod(rem, 1_000_000)
    if hours == 0 and minutes == 0 and seconds == 0 and microseconds == 0:
        return "00:00:00"
    hour_text = f"{hours:02d}" if hours <= 99 else f"{hours:03d}"
    body = f"{hour_text}:{minutes:02d}:{seconds:02d}"
    if microseconds:
        body += f".{microseconds:06d}".rstrip("0")
    return f"-{body}" if negative else body


def encode_row_cells(sql_types: Sequence[str], values: Sequence[Any]) -> bytes:
    """Length-prefix each cell in DDL order. Does not call the Shared Kernel row encoder."""

    if len(sql_types) != len(values):
        raise CanonicalizationCellError("row cell count does not match sql_types")
    parts = bytearray()
    for sql_type, value in zip(sql_types, values, strict=True):
        cell = encode_cell(sql_type, value)
        parts.extend(_encode_uleb128(len(cell)))
        parts.extend(cell)
    return bytes(parts)


def _encode_uleb128(value: int) -> bytes:
    if type(value) is not int or value < 0:
        raise CanonicalizationCellError("ULEB128 length must be a non-negative int")
    if value == 0:
        return b"\x00"
    out = bytearray()
    remaining = value
    while True:
        byte = remaining & 0x7F
        remaining >>= 7
        if remaining:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)
