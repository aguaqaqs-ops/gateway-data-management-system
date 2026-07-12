from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time as time_type
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import base64
import re


_TYPED_SCALAR_SUFFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_()]*$")
_INTEGER_FAMILIES = {
    "bigint",
    "int",
    "integer",
    "mediumint",
    "smallint",
    "tinyint",
    "year",
}
_DECIMAL_FAMILIES = {"decimal", "numeric"}
_FLOAT_FAMILIES = {"double", "float", "real"}
_DATETIME_FAMILIES = {"datetime", "timestamp"}
_DATE_FAMILIES = {"date"}
_TIME_FAMILIES = {"time"}
_BOOLEAN_FAMILIES = {"bool", "boolean"}
_BINARY_FAMILIES = {
    "binary",
    "bit",
    "blob",
    "longblob",
    "mediumblob",
    "tinyblob",
    "varbinary",
}


def scalar_type_family(scalar_type: str | None) -> str:
    if scalar_type is None:
        return ""
    text = scalar_type.strip().lower()
    if not text:
        return ""
    text = text.split(None, 1)[0]
    text = text.split("(", 1)[0]
    return text


def strip_typed_scalar_suffix(value: object) -> object:
    if not isinstance(value, str):
        return value
    prefix, separator, suffix = value.rpartition(":")
    if not separator or not prefix:
        return value
    if _TYPED_SCALAR_SUFFIX_RE.fullmatch(suffix) is None:
        return value
    return prefix


def coerce_int_value(value: object) -> object:
    stripped = strip_typed_scalar_suffix(value)
    try:
        return int(stripped)
    except (TypeError, ValueError):
        return stripped


def coerce_decimal_value(value: object) -> object:
    stripped = strip_typed_scalar_suffix(value)
    try:
        return Decimal(str(stripped))
    except (InvalidOperation, TypeError, ValueError):
        return stripped


def coerce_float_value(value: object) -> object:
    stripped = strip_typed_scalar_suffix(value)
    try:
        return float(stripped)
    except (TypeError, ValueError):
        return stripped


def coerce_bool_value(value: object) -> object:
    stripped = strip_typed_scalar_suffix(value)
    if isinstance(stripped, bool):
        return stripped
    if isinstance(stripped, (int, Decimal)):
        return bool(stripped)
    text = str(stripped).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return stripped


def normalize_snapshot_scalar_value(value: object, scalar_type: str | None) -> object:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _encode_binary_value(value)
    family = scalar_type_family(scalar_type)
    if family in _INTEGER_FAMILIES:
        return coerce_int_value(value)
    if family in _DECIMAL_FAMILIES:
        return coerce_decimal_value(value)
    if family in _FLOAT_FAMILIES:
        return coerce_float_value(value)
    if family in _DATETIME_FAMILIES:
        value = strip_typed_scalar_suffix(value)
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        return str(value)
    if family in _DATE_FAMILIES:
        value = strip_typed_scalar_suffix(value)
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        return str(value)
    if family in _TIME_FAMILIES:
        value = strip_typed_scalar_suffix(value)
        if isinstance(value, time_type):
            return value.isoformat()
        return str(value)
    if family in _BOOLEAN_FAMILIES:
        return coerce_bool_value(value)
    if family in _BINARY_FAMILIES:
        return _encode_binary_value(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, time_type):
        return value.isoformat()
    return value


def normalize_json_scalar_value(value: object, scalar_type: str | None) -> object:
    normalized = normalize_snapshot_scalar_value(value, scalar_type)
    if isinstance(normalized, Decimal):
        return str(normalized)
    return normalized


@lru_cache(maxsize=512)
def parquet_scalar_value_normalizer(scalar_type: str | None) -> Callable[[object], object]:
    """Return a parquet scalar normalizer with scalar type parsing done once per column."""

    family = scalar_type_family(scalar_type)

    if family in _INTEGER_FAMILIES:
        def normalize_integer(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            return coerce_int_value(value)

        return normalize_integer

    if family in _DECIMAL_FAMILIES:
        def normalize_decimal(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            return coerce_decimal_value(value)

        return normalize_decimal

    if family in _FLOAT_FAMILIES:
        def normalize_float(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            return coerce_float_value(value)

        return normalize_float

    if family in _DATETIME_FAMILIES:
        def normalize_datetime(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            stripped = strip_typed_scalar_suffix(value)
            if isinstance(stripped, datetime):
                return stripped
            try:
                return datetime.fromisoformat(str(stripped))
            except ValueError:
                return str(stripped)

        return normalize_datetime

    if family in _DATE_FAMILIES:
        def normalize_date(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            stripped = strip_typed_scalar_suffix(value)
            if isinstance(stripped, date) and not isinstance(stripped, datetime):
                return stripped
            try:
                return date.fromisoformat(str(stripped))
            except ValueError:
                return str(stripped)

        return normalize_date

    if family in _TIME_FAMILIES:
        def normalize_time(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            stripped = strip_typed_scalar_suffix(value)
            if isinstance(stripped, time_type):
                return stripped
            try:
                return time_type.fromisoformat(str(stripped))
            except ValueError:
                return str(stripped)

        return normalize_time

    if family in _BOOLEAN_FAMILIES:
        def normalize_boolean(value: object) -> object:
            if value is None:
                return None
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            return coerce_bool_value(value)

        return normalize_boolean

    def normalize_default(value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, time_type):
            return value.isoformat()
        return value

    return normalize_default


def normalize_parquet_scalar_value(value: object, scalar_type: str | None) -> object:
    return parquet_scalar_value_normalizer(scalar_type)(value)


def normalize_snapshot_row(
    row: Sequence[object],
    columns: Sequence[object],
) -> tuple[object, ...]:
    return _normalize_row(row, columns, normalize_snapshot_scalar_value)


def normalize_snapshot_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
) -> tuple[tuple[object, ...], ...]:
    return tuple(normalize_snapshot_row(row, columns) for row in rows)


def normalize_json_row(
    row: Sequence[object],
    columns: Sequence[object],
) -> tuple[object, ...]:
    return _normalize_row(row, columns, normalize_json_scalar_value)


def normalize_json_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
) -> tuple[tuple[object, ...], ...]:
    return tuple(normalize_json_row(row, columns) for row in rows)


def normalize_parquet_row(
    row: Sequence[object],
    columns: Sequence[object],
) -> tuple[object, ...]:
    return _normalize_row(row, columns, normalize_parquet_scalar_value)


def normalize_parquet_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
) -> tuple[tuple[object, ...], ...]:
    return tuple(normalize_parquet_row(row, columns) for row in rows)


def _normalize_row(
    row: Sequence[object],
    columns: Sequence[object],
    scalar_value_encoder,
) -> tuple[object, ...]:
    if len(row) != len(columns):
        raise ValueError(f"row has {len(row)} values but expected {len(columns)}")
    return tuple(
        scalar_value_encoder(row[index], getattr(column, "scalar_type", None))
        for index, column in enumerate(columns)
    )


def _encode_binary_value(value: object) -> str:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return str(value)
