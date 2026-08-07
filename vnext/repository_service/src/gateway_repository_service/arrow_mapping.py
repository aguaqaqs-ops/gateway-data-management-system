"""Repository SQL catalog normalization and bounded Arrow conversion."""

from __future__ import annotations

import datetime as dt
import decimal
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Iterator

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy

__all__ = [
    "ColumnCatalog",
    "TableCatalog",
    "TemporalSqlTypeKind",
    "TemporalSqlType",
    "SqlValueConversionError",
    "UnknownSqlTypeError",
    "UnknownTypePolicy",
    "arrow_type",
    "classify_temporal_sql_type",
    "convert_value",
    "is_known_sql_type",
    "normalize_rows",
    "normalize_sql_type",
    "parse_temporal_sql_type",
    "record_batch",
]


class UnknownSqlTypeError(ValueError):
    """Raised when a catalog type is not in the Repository known family."""


class SqlValueConversionError(ValueError):
    """Raised when a catalog value cannot be converted for Arrow emission."""

    def __init__(self, *, column: str, sql_type: str) -> None:
        self.column = column
        self.sql_type = sql_type
        super().__init__(f"value conversion failed for column {column} ({sql_type})")


@dataclass(frozen=True)
class ColumnCatalog:
    name: str
    sql_type: str
    nullable: bool
    primary_key_position: int | None


@dataclass(frozen=True)
class TableCatalog:
    name: str
    columns: tuple[ColumnCatalog, ...]
    row_count: int

    @property
    def primary_key(self) -> tuple[str, ...]:
        ordered = sorted(
            (column for column in self.columns if column.primary_key_position is not None),
            key=lambda column: column.primary_key_position or 0,
        )
        return tuple(column.name for column in ordered)


_DECIMAL = re.compile(r"^DECIMAL\((\d+),(\d+)\)$")
_BIT = re.compile(r"^BIT\((\d+)\)$")
_TEMPORAL_BASE = frozenset({"TIME", "DATETIME", "TIMESTAMP"})
_TEMPORAL_LIKE = re.compile(r"^(TIME|DATETIME|TIMESTAMP)(?:\(|$|\s)")
_SIZED_CHARACTER = re.compile(r"^(CHAR|VARCHAR)\(\d+\)$")
_SIZED_BINARY = re.compile(r"^(BINARY|VARBINARY)\(\d+\)$")
_CHARACTER = {
    "CHAR",
    "VARCHAR",
    "TINYTEXT",
    "TEXT",
    "MEDIUMTEXT",
    "LONGTEXT",
}
_BINARY = {
    "BINARY",
    "VARBINARY",
    "TINYBLOB",
    "BLOB",
    "MEDIUMBLOB",
    "LONGBLOB",
}
SPATIAL_SQL_TYPES = frozenset({
    "GEOMETRY",
    "POINT",
    "LINESTRING",
    "POLYGON",
    "MULTIPOINT",
    "MULTILINESTRING",
    "MULTIPOLYGON",
    "GEOMETRYCOLLECTION",
})


class TemporalSqlTypeKind(StrEnum):
    VALID = "valid"
    MALFORMED = "malformed"
    NOT_TEMPORAL = "not_temporal"


@dataclass(frozen=True)
class TemporalSqlType:
    kind: str
    fsp: int | None


def classify_temporal_sql_type(
    sql_type: str,
    *,
    allow_zero_fsp_normalization: bool = False,
    normalize_whitespace: bool = False,
) -> tuple[TemporalSqlTypeKind, TemporalSqlType | None]:
    """Classify temporal spellings into valid, malformed temporal-like, or non-temporal."""

    upper = " ".join(sql_type.upper().split()) if normalize_whitespace else sql_type.upper()
    if upper in _TEMPORAL_BASE:
        return TemporalSqlTypeKind.VALID, TemporalSqlType(upper, None)
    for kind in ("TIME", "DATETIME", "TIMESTAMP"):
        prefix = f"{kind}("
        if not upper.startswith(prefix) or not upper.endswith(")"):
            continue
        inner = upper[len(prefix) : -1]
        if not inner:
            return TemporalSqlTypeKind.MALFORMED, None
        if not re.fullmatch(r"\d+", inner):
            return TemporalSqlTypeKind.MALFORMED, None
        if len(inner) > 1 and inner[0] == "0":
            if allow_zero_fsp_normalization and kind == "TIMESTAMP" and inner == "00":
                return TemporalSqlTypeKind.VALID, TemporalSqlType(kind, None)
            return TemporalSqlTypeKind.MALFORMED, None
        fsp = int(inner)
        if 0 <= fsp <= 6:
            return TemporalSqlTypeKind.VALID, TemporalSqlType(kind, fsp)
        return TemporalSqlTypeKind.MALFORMED, None
    if _TEMPORAL_LIKE.match(upper):
        return TemporalSqlTypeKind.MALFORMED, None
    return TemporalSqlTypeKind.NOT_TEMPORAL, None


def parse_temporal_sql_type(sql_type: str) -> tuple[str, int | None] | None:
    """Return valid temporal spelling or None when the type is not temporal."""

    classification, parsed = classify_temporal_sql_type(sql_type)
    if classification == TemporalSqlTypeKind.VALID and parsed is not None:
        return parsed.kind, parsed.fsp
    if classification == TemporalSqlTypeKind.MALFORMED:
        raise UnknownSqlTypeError(f"invalid temporal SQL type spelling: {sql_type}")
    return None


def _iter_sql_type_segments(text: str) -> Iterator[tuple[bool, str]]:
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character in "'\"`":
            quote = character
            start = index
            index += 1
            while index < length:
                if text[index] == "\\" and index + 1 < length:
                    index += 2
                    continue
                if text[index] == quote:
                    if quote == "'" and index + 1 < length and text[index + 1] == "'":
                        index += 2
                        continue
                    if quote == '"' and index + 1 < length and text[index + 1] == '"':
                        index += 2
                        continue
                    if quote == "`" and index + 1 < length and text[index + 1] == "`":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            yield True, text[start:index]
            continue
        start = index
        while index < length and text[index] not in "'\"`":
            index += 1
        yield False, text[start:index]


_COLLATE_MODIFIER = re.compile(r"\s+COLLATE\s+\S+", re.IGNORECASE)
_CHARACTER_SET_MODIFIER = re.compile(r"\s+CHARACTER\s+SET\s+\S+", re.IGNORECASE)
_ZEROFILL_MODIFIER = re.compile(r"\s+ZEROFILL\b", re.IGNORECASE)
_INTEGER_DISPLAY_WIDTH = re.compile(
    r"\b(TINYINT|SMALLINT|MEDIUMINT|INT|BIGINT)(\(\d+\))(?=\s|$|UNSIGNED)",
    re.IGNORECASE,
)


def _strip_integer_display_width(segment: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        base = match.group(1).upper()
        width = match.group(2)
        if base == "TINYINT" and width == "(1)":
            return match.group(0)
        return base

    return _INTEGER_DISPLAY_WIDTH.sub(replacer, segment)


def _strip_modifiers_outside_quotes(text: str) -> str:
    parts: list[str] = []
    for quoted, segment in _iter_sql_type_segments(text):
        if quoted:
            parts.append(segment)
            continue
        segment = _COLLATE_MODIFIER.sub("", segment)
        segment = _CHARACTER_SET_MODIFIER.sub("", segment)
        segment = _ZEROFILL_MODIFIER.sub("", segment)
        segment = _strip_integer_display_width(segment)
        parts.append(segment)
    return "".join(parts)


def _collapse_whitespace_outside_quotes(text: str) -> str:
    parts: list[str] = []
    for quoted, segment in _iter_sql_type_segments(text):
        if quoted:
            parts.append(segment)
        else:
            parts.append(" ".join(segment.split()))
    return "".join(parts)


def _uppercase_outside_quotes(text: str) -> str:
    parts: list[str] = []
    for quoted, segment in _iter_sql_type_segments(text):
        parts.append(segment if quoted else segment.upper())
    return "".join(parts)


def _strip_type_modifiers(column_type: str) -> str:
    return _collapse_whitespace_outside_quotes(_strip_modifiers_outside_quotes(column_type))


def _normalize_unknown_sql_spelling(column_type: str) -> str:
    return _uppercase_outside_quotes(column_type)


def normalize_sql_type(data_type: str, column_type: str) -> str:
    """Normalize the Dolt catalog spelling used by the contract."""

    stripped = _strip_type_modifiers(column_type)
    raw = stripped.upper()
    if raw in {"TINYINT(1)", "TINYINT(1) UNSIGNED"}:
        return "BOOLEAN"
    if raw.startswith("TINYINT(1)") and data_type.upper() == "TINYINT":
        return raw.replace("TINYINT(1)", "TINYINT", 1)
    classification, temporal = classify_temporal_sql_type(
        raw,
        allow_zero_fsp_normalization=True,
        normalize_whitespace=True,
    )
    if classification == TemporalSqlTypeKind.MALFORMED:
        raise UnknownSqlTypeError(f"invalid temporal SQL type spelling: {column_type}")
    if classification == TemporalSqlTypeKind.VALID and temporal is not None:
        if temporal.fsp is None:
            return temporal.kind
        return f"{temporal.kind}({temporal.fsp})"
    match = _DECIMAL.match(raw)
    if match is not None:
        return f"DECIMAL({match.group(1)},{match.group(2)})"
    match = _BIT.match(raw)
    if match is not None:
        return f"BIT({match.group(1)})"
    if raw.endswith(" UNSIGNED"):
        base = raw.removesuffix(" UNSIGNED")
        if base in {"TINYINT", "SMALLINT", "MEDIUMINT", "INT", "BIGINT"}:
            return f"{base} UNSIGNED"
    if (
        raw in _CHARACTER
        or raw in _BINARY
        or _SIZED_CHARACTER.fullmatch(raw) is not None
        or _SIZED_BINARY.fullmatch(raw) is not None
        or raw in {"BOOLEAN", "JSON", "FLOAT", "DOUBLE", "DATE"}
    ):
        return raw
    if raw in {"TINYINT", "SMALLINT", "MEDIUMINT", "INT", "BIGINT"}:
        return raw
    srid_match = re.match(r"^([A-Z]+)\s+/\*!\d+\s+SRID\s+(\d+)\s*\*/\s*$", raw)
    if srid_match is not None:
        spatial_type = srid_match.group(1)
        if spatial_type not in SPATIAL_SQL_TYPES:
            raise UnknownSqlTypeError(f"invalid spatial SRID type: {column_type}")
        return f"{spatial_type} SRID {srid_match.group(2)}"
    return _normalize_unknown_sql_spelling(stripped)


def _known_arrow_type(sql_type: str) -> tuple[pa.DataType, dict[bytes, bytes]] | None:
    upper = sql_type.upper()
    integer_types: dict[str, pa.DataType] = {
        "TINYINT": pa.int8(),
        "TINYINT UNSIGNED": pa.uint8(),
        "SMALLINT": pa.int16(),
        "SMALLINT UNSIGNED": pa.uint16(),
        "MEDIUMINT": pa.int32(),
        "MEDIUMINT UNSIGNED": pa.uint32(),
        "INT": pa.int32(),
        "INT UNSIGNED": pa.uint32(),
        "BIGINT": pa.int64(),
        "BIGINT UNSIGNED": pa.uint64(),
    }
    if upper == "BOOLEAN":
        return pa.bool_(), {}
    if upper in integer_types:
        return integer_types[upper], {}
    if upper == "FLOAT":
        return pa.float32(), {}
    if upper == "DOUBLE":
        return pa.float64(), {}
    if upper == "DATE":
        return pa.date32(), {}
    classification, temporal = classify_temporal_sql_type(sql_type)
    if classification == TemporalSqlTypeKind.MALFORMED:
        raise UnknownSqlTypeError(f"invalid temporal SQL type spelling: {sql_type}")
    if classification == TemporalSqlTypeKind.VALID and temporal is not None:
        if temporal.kind == "TIME":
            return pa.duration("us"), {}
        if temporal.kind == "TIMESTAMP":
            return pa.timestamp("us", tz="UTC"), {}
        return pa.timestamp("us"), {}
    decimal_match = _DECIMAL.match(upper)
    if decimal_match is not None:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2))
        if not 1 <= precision <= 65 or not 0 <= scale <= 30 or scale > precision:
            return None
        if precision <= 38:
            return pa.decimal128(precision, scale), {}
        return pa.decimal256(precision, scale), {}
    bit_match = _BIT.match(upper)
    if bit_match is not None:
        width = int(bit_match.group(1))
        if not 1 <= width <= 64:
            return None
        return pa.binary(), {b"gateway.bit_width": str(width).encode("ascii")}
    if upper in _CHARACTER or _SIZED_CHARACTER.fullmatch(upper) is not None:
        return pa.string(), {}
    if upper in _BINARY or _SIZED_BINARY.fullmatch(upper) is not None:
        return pa.binary(), {}
    if upper == "JSON":
        return pa.string(), {b"gateway.logical_type": b"json"}
    return None


def arrow_type(sql_type: str, policy: UnknownTypePolicy) -> tuple[pa.DataType, dict[bytes, bytes]]:
    known = _known_arrow_type(sql_type)
    if known is not None:
        return known
    if policy == UnknownTypePolicy.STRINGIFY:
        return pa.large_string(), {
            b"gateway.sql_type": sql_type.encode("utf-8"),
            b"gateway.lossy": b"true",
        }
    raise UnknownSqlTypeError(f"unknown SQL type: {sql_type}")


def is_known_sql_type(sql_type: str) -> bool:
    try:
        arrow_type(sql_type, UnknownTypePolicy.REJECT)
        return True
    except UnknownSqlTypeError:
        return False


def convert_value(value: Any, sql_type: str, policy: UnknownTypePolicy) -> Any:
    try:
        arrow, _ = arrow_type(sql_type, policy)
    except UnknownSqlTypeError:
        if policy == UnknownTypePolicy.REJECT:
            raise
        return None if value is None else str(value)
    if value is None:
        return None
    upper = sql_type.upper()
    if pa.types.is_boolean(arrow):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t"}
        return bool(value)
    if pa.types.is_integer(arrow):
        return int(value)
    if pa.types.is_floating(arrow):
        return float(value)
    if pa.types.is_decimal(arrow):
        return value if isinstance(value, decimal.Decimal) else decimal.Decimal(str(value))
    if pa.types.is_date32(arrow):
        if isinstance(value, dt.date):
            return value
        return dt.date.fromisoformat(str(value).replace("T", " ").split(" ", 1)[0])
    if pa.types.is_duration(arrow):
        if isinstance(value, dt.timedelta):
            return value
        text = str(value)
        sign = -1 if text.startswith("-") else 1
        parts = text.lstrip("-").split(":")
        hours, minutes, seconds = (int(parts[0]), int(parts[1]), float(parts[2]))
        return sign * dt.timedelta(hours=hours, minutes=minutes, seconds=seconds)
    if pa.types.is_timestamp(arrow):
        parsed = (
            value
            if isinstance(value, dt.datetime)
            else dt.datetime.fromisoformat(str(value).replace(" ", "T"))
        )
        if upper.startswith("TIMESTAMP"):
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        return parsed
    if pa.types.is_binary(arrow):
        bit_match = _BIT.match(upper)
        if bit_match is not None:
            width = int(bit_match.group(1))
            byte_length = (width + 7) // 8
            if isinstance(value, (bytes, bytearray, memoryview)):
                raw = bytes(value)
            elif isinstance(value, int):
                raw = value.to_bytes(byte_length, "big", signed=False)
            else:
                text = str(value)
                if text.startswith(("0x", "0X")):
                    raw = bytes.fromhex(text[2:])
                elif len(text) % 2 == 0 and text and all(
                    character in "0123456789abcdefABCDEF" for character in text
                ):
                    raw = bytes.fromhex(text)
                else:
                    raw = int(text, 0).to_bytes(byte_length, "big", signed=False)
            if len(raw) > byte_length:
                raise ValueError("BIT value exceeds catalog width")
            return raw.rjust(byte_length, b"\x00")
        if isinstance(value, bytes):
            return value
        text = str(value)
        if text.startswith("0x"):
            return bytes.fromhex(text[2:])
        if len(text) % 2 == 0 and text and all(character in "0123456789abcdefABCDEF" for character in text):
            return bytes.fromhex(text)
        return text.encode("utf-8")
    return str(value) if not isinstance(value, str) else value


def normalize_rows(
    catalog: TableCatalog,
    rows: Iterable[tuple[Any, ...]],
    policy: UnknownTypePolicy,
) -> list[tuple[Any, ...]]:
    """Normalize provider rows using the exact values emitted to Arrow.

    Candidate A receives tagged-CSV text while Candidate B receives connector
    Python values.  Keeping this conversion in one place makes decoded payload
    accounting and batch splitting independent of the provider framing.
    """

    columns = catalog.columns
    normalized: list[tuple[Any, ...]] = []
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("row column count does not match catalog")
        converted_row: list[Any] = []
        for index, column in enumerate(columns):
            try:
                converted_row.append(convert_value(row[index], column.sql_type, policy))
            except ValueError as exc:
                if isinstance(exc, SqlValueConversionError):
                    raise
                raise SqlValueConversionError(
                    column=column.name,
                    sql_type=column.sql_type,
                ) from exc
        normalized.append(tuple(converted_row))
    return normalized


def _raise_column_conversion_error(exc: ValueError, *, column: ColumnCatalog) -> None:
    if isinstance(exc, SqlValueConversionError):
        raise exc
    raise SqlValueConversionError(column=column.name, sql_type=column.sql_type) from exc


def record_batch(
    catalog: TableCatalog,
    rows: Iterable[tuple[Any, ...]],
    policy: UnknownTypePolicy,
) -> pa.RecordBatch:
    row_list = normalize_rows(catalog, rows, policy)
    arrays: list[pa.Array] = []
    fields: list[pa.Field] = []
    for index, column in enumerate(catalog.columns):
        data_type, metadata = arrow_type(column.sql_type, policy)
        values = [row[index] for row in row_list]
        try:
            arrays.append(pa.array(values, type=data_type))
        except ValueError as exc:
            _raise_column_conversion_error(exc, column=column)
        fields.append(
            pa.field(column.name, data_type, nullable=column.nullable, metadata=metadata or None)
        )
    try:
        return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))
    except ValueError as exc:
        _raise_column_conversion_error(exc, column=catalog.columns[0])
