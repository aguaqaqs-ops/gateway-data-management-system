"""Repository SQL catalog normalization and bounded Arrow conversion."""

from __future__ import annotations

import datetime as dt
import decimal
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Iterator, NoReturn

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy

__all__ = [
    "ColumnCatalog",
    "CompiledColumnPlan",
    "CompiledTablePlan",
    "NormalizedRow",
    "TableCatalog",
    "TemporalSqlTypeKind",
    "TemporalSqlType",
    "SqlValueConversionError",
    "UnknownSqlTypeError",
    "UnknownTypePolicy",
    "arrow_type",
    "classify_temporal_sql_type",
    "compile_table_plan",
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

    def __init__(self, *, table: str, column: str, sql_type: str) -> None:
        self.table = table
        self.column = column
        self.sql_type = sql_type
        super().__init__(
            f"value conversion failed for {table}.{column} ({sql_type})"
        )


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
    r"\b(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)(\(\d+\))(?=\s|$|UNSIGNED)",
    re.IGNORECASE,
)


def _strip_integer_display_width(segment: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        base = match.group(1).upper()
        if base == "INTEGER":
            base = "INT"
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
        if base == "INTEGER":
            return "INT UNSIGNED"
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
    if raw == "INTEGER":
        return "INT"
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


def _convert_value_with_arrow(value: Any, sql_type: str, arrow: pa.DataType) -> Any:
    if value is None:
        return None
    upper = sql_type.upper()
    if pa.types.is_boolean(arrow):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"true", "t"}:
            return True
        if text in {"false", "f"}:
            return False
        return bool(int(text))
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
    if pa.types.is_large_string(arrow):
        return str(value) if not isinstance(value, str) else value
    return str(value) if not isinstance(value, str) else value


def convert_value(value: Any, sql_type: str, policy: UnknownTypePolicy) -> Any:
    try:
        arrow, _ = arrow_type(sql_type, policy)
    except UnknownSqlTypeError:
        if policy == UnknownTypePolicy.REJECT:
            raise
        return None if value is None else str(value)
    return _convert_value_with_arrow(value, sql_type, arrow)


def _immutable_metadata(metadata: dict[bytes, bytes]) -> dict[bytes, bytes]:
    return {bytes(key): bytes(value) for key, value in metadata.items()}


def _value_size_bytes(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, bytes):
        return len(value)
    return len(str(value).encode("utf-8"))


def _row_values_size_bytes(values: tuple[Any, ...]) -> int:
    return sum(_value_size_bytes(value) for value in values)


def _validate_bit_unused_high_bits(raw: bytes, width: int) -> None:
    byte_length = (width + 7) // 8
    if len(raw) > byte_length:
        raise ValueError("BIT value exceeds catalog width")
    excess_bits = byte_length * 8 - width
    if excess_bits > 0:
        max_first = (1 << (8 - excess_bits)) - 1
        if raw[0] > max_first:
            raise ValueError("BIT unused high bits must be zero")


def _validate_logical_range(
    *,
    table_name: str,
    column: ColumnCatalog,
    value: Any,
) -> Any:
    if value is None and not column.nullable:
        raise SqlValueConversionError(
            table=table_name,
            column=column.name,
            sql_type=column.sql_type,
        )
    if value is None:
        return value
    upper = column.sql_type.upper()
    if upper == "MEDIUMINT":
        if not isinstance(value, int) or value < -8388608 or value > 8388607:
            raise SqlValueConversionError(
                table=table_name,
                column=column.name,
                sql_type=column.sql_type,
            )
    elif upper == "MEDIUMINT UNSIGNED":
        if not isinstance(value, int) or value < 0 or value > 16777215:
            raise SqlValueConversionError(
                table=table_name,
                column=column.name,
                sql_type=column.sql_type,
            )
    bit_match = _BIT.match(upper)
    if bit_match is not None and isinstance(value, bytes):
        _validate_bit_unused_high_bits(value, int(bit_match.group(1)))
    return value


def _raise_column_conversion_error(
    exc: ValueError | TypeError,
    *,
    table_name: str,
    column: ColumnCatalog,
) -> NoReturn:
    if isinstance(exc, SqlValueConversionError):
        raise exc
    raise SqlValueConversionError(
        table=table_name,
        column=column.name,
        sql_type=column.sql_type,
    ) from exc


@dataclass(frozen=True)
class CompiledColumnPlan:
    field: pa.Field
    column: ColumnCatalog
    converter: Callable[[Any], Any]


@dataclass(frozen=True)
class NormalizedRow:
    values: tuple[Any, ...]
    logical_size_bytes: int


@dataclass(frozen=True)
class CompiledTablePlan:
    catalog: TableCatalog
    columns: tuple[CompiledColumnPlan, ...]
    expected_schema: pa.Schema

    def normalize_row(self, raw: tuple[Any, ...]) -> NormalizedRow:
        if len(raw) != len(self.columns):
            raise ValueError("row column count does not match catalog")
        converted: list[Any] = []
        for index, column_plan in enumerate(self.columns):
            column = column_plan.column
            try:
                value = column_plan.converter(raw[index])
                value = _validate_logical_range(
                    table_name=self.catalog.name,
                    column=column,
                    value=value,
                )
            except (ValueError, TypeError) as exc:
                _raise_column_conversion_error(
                    exc,
                    table_name=self.catalog.name,
                    column=column,
                )
            converted.append(value)
        values = tuple(converted)
        return NormalizedRow(
            values=values,
            logical_size_bytes=_row_values_size_bytes(values),
        )

    def record_batch(self, normalized_rows: Iterable[NormalizedRow]) -> pa.RecordBatch:
        row_list = list(normalized_rows)
        arrays: list[pa.Array] = []
        last_column = self.columns[0].column
        for index, column_plan in enumerate(self.columns):
            last_column = column_plan.column
            values = [row.values[index] for row in row_list]
            try:
                arrays.append(pa.array(values, type=column_plan.field.type))
            except (ValueError, TypeError) as exc:
                _raise_column_conversion_error(
                    exc,
                    table_name=self.catalog.name,
                    column=last_column,
                )
        try:
            return pa.RecordBatch.from_arrays(arrays, schema=self.expected_schema)
        except (ValueError, TypeError) as exc:
            _raise_column_conversion_error(
                exc,
                table_name=self.catalog.name,
                column=last_column,
            )


def _make_column_converter(
    table_name: str,
    column: ColumnCatalog,
    data_type: pa.DataType,
    metadata: dict[bytes, bytes],
) -> Callable[[Any], Any]:
    if metadata.get(b"gateway.lossy") == b"true":
        def stringify_unknown(raw: Any) -> Any:
            return None if raw is None else str(raw)

        return stringify_unknown

    def convert(raw: Any) -> Any:
        try:
            return _convert_value_with_arrow(raw, column.sql_type, data_type)
        except (ValueError, TypeError) as exc:
            if isinstance(exc, SqlValueConversionError):
                raise
            raise SqlValueConversionError(
                table=table_name,
                column=column.name,
                sql_type=column.sql_type,
            ) from exc

    return convert


def compile_table_plan(
    catalog: TableCatalog,
    policy: UnknownTypePolicy,
) -> CompiledTablePlan:
    column_plans: list[CompiledColumnPlan] = []
    for column in catalog.columns:
        data_type, metadata = arrow_type(column.sql_type, policy)
        immutable_metadata = _immutable_metadata(metadata)
        field = pa.field(
            column.name,
            data_type,
            nullable=column.nullable,
            metadata=immutable_metadata or None,
        )
        column_plans.append(
            CompiledColumnPlan(
                field=field,
                column=column,
                converter=_make_column_converter(
                    catalog.name,
                    column,
                    data_type,
                    immutable_metadata,
                ),
            )
        )
    columns = tuple(column_plans)
    expected_schema = pa.schema([column_plan.field for column_plan in columns])
    return CompiledTablePlan(
        catalog=catalog,
        columns=columns,
        expected_schema=expected_schema,
    )


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

    plan = compile_table_plan(catalog, policy)
    return [plan.normalize_row(row).values for row in rows]


def record_batch(
    catalog: TableCatalog,
    rows: Iterable[tuple[Any, ...]],
    policy: UnknownTypePolicy,
) -> pa.RecordBatch:
    plan = compile_table_plan(catalog, policy)
    normalized_rows = [plan.normalize_row(row) for row in rows]
    return plan.record_batch(normalized_rows)
