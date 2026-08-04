"""Repository SQL catalog normalization and bounded Arrow conversion."""

from __future__ import annotations

import datetime as dt
import decimal
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable

import pyarrow as pa  # type: ignore[import-untyped]


class UnknownTypePolicy(StrEnum):
    REJECT = "REJECT"
    STRINGIFY = "STRINGIFY"


class UnknownSqlTypeError(ValueError):
    """Raised when a catalog type is not in the Repository known family."""


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
_TEMPORAL = re.compile(r"^(TIME|DATETIME|TIMESTAMP)\((\d+)\)$")
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


def normalize_sql_type(data_type: str, column_type: str) -> str:
    """Normalize the Dolt catalog spelling used by the contract."""

    raw = " ".join(column_type.upper().split())
    raw = re.sub(r"\s+COLLATE\s+[^ ]+", "", raw)
    raw = re.sub(r"\s+CHARACTER SET\s+[^ ]+", "", raw)
    if raw in {"TINYINT(1)", "TINYINT(1) UNSIGNED"}:
        return "BOOLEAN"
    if raw.startswith("TINYINT(1)") and data_type.upper() == "TINYINT":
        return raw.replace("TINYINT(1)", "TINYINT", 1)
    match = _TEMPORAL.match(raw)
    if match is not None:
        return f"{match.group(1)}({match.group(2)})"
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
    return raw


def arrow_type(sql_type: str, policy: UnknownTypePolicy) -> tuple[pa.DataType, dict[bytes, bytes]]:
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
    temporal = _TEMPORAL.match(upper)
    if temporal is not None:
        kind = temporal.group(1)
        if kind == "TIME":
            return pa.duration("us"), {}
        if kind == "TIMESTAMP":
            return pa.timestamp("us", tz="UTC"), {}
        return pa.timestamp("us"), {}
    decimal_match = _DECIMAL.match(upper)
    if decimal_match is not None:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2))
        if not 1 <= precision <= 65 or not 0 <= scale <= 30 or scale > precision:
            raise UnknownSqlTypeError(f"invalid DECIMAL type: {sql_type}")
        if precision <= 38:
            return pa.decimal128(precision, scale), {}
        return pa.decimal256(precision, scale), {}
    bit_match = _BIT.match(upper)
    if bit_match is not None:
        width = int(bit_match.group(1))
        if not 1 <= width <= 64:
            raise UnknownSqlTypeError(f"invalid BIT type: {sql_type}")
        return pa.binary(), {b"gateway.bit_width": str(width).encode("ascii")}
    if upper in _CHARACTER or _SIZED_CHARACTER.fullmatch(upper) is not None:
        return pa.string(), {}
    if upper in _BINARY or _SIZED_BINARY.fullmatch(upper) is not None:
        return pa.binary(), {}
    if upper == "JSON":
        return pa.string(), {b"gateway.logical_type": b"json"}
    if policy == UnknownTypePolicy.STRINGIFY:
        return pa.large_string(), {b"gateway.sql_type": upper.encode("utf-8"), b"gateway.lossy": b"true"}
    raise UnknownSqlTypeError(f"unknown SQL type: {sql_type}")


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
        if isinstance(value, dt.datetime):
            return value
        parsed = dt.datetime.fromisoformat(str(value).replace(" ", "T"))
        if upper.startswith("TIMESTAMP") and parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    if pa.types.is_binary(arrow):
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
        normalized.append(
            tuple(
                convert_value(row[index], column.sql_type, policy)
                for index, column in enumerate(columns)
            )
        )
    return normalized


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
        values = [convert_value(row[index], column.sql_type, policy) for row in row_list]
        arrays.append(pa.array(values, type=data_type))
        fields.append(
            pa.field(column.name, data_type, nullable=column.nullable, metadata=metadata or None)
        )
    return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))
