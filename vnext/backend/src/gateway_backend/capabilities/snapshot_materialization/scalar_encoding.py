"""Repository tuple values to Snapshot SourceCell encoding.

SQL materialization already receives typed cells from table_access. This module
normalizes provider tuples onto the same Shared Kernel scalars so SQL dump and
repository readback share digest frames. It does not import table_access
parser-private type maps.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal

from gateway_shared_kernel import (
    CanonicalEncodingError,
    CanonicalErrorCode,
    DeclaredType,
    DeclaredTypeKind,
    NullScalar,
    RawLogicalLiteral,
    StringScalar,
    Utf8LogicalLiteral,
    canonicalize_identifier,
    normalize_logical_literal,
)

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    RepositoryColumn,
)
from gateway_backend.capabilities.table_access.contracts import (
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SqlLogicalType,
)

_INTEGER_BITS = {
    "TINYINT": 8,
    "SMALLINT": 16,
    "MEDIUMINT": 24,
    "INT": 32,
    "INTEGER": 32,
    "BIGINT": 64,
}
_TEXT_BASES = frozenset(
    {
        "CHAR",
        "VARCHAR",
        "TINYTEXT",
        "TEXT",
        "MEDIUMTEXT",
        "LONGTEXT",
        "JSON",
        "ENUM",
        "SET",
    }
)
_BLOB_BASES = frozenset(
    {"BINARY", "VARBINARY", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"}
)
_LEADING_TOKEN = re.compile(r"^([A-Z]+)(?:\((.*)\))?$")
_STRING_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)


@dataclass(frozen=True, slots=True)
class EncodedRepositoryRow:
    cells: SourceRow
    diagnostics: tuple[MaterializationDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class MappedRepositoryColumn:
    source: SourceColumnDescriptor
    unknown_family: bool


def map_repository_column(column: RepositoryColumn) -> MappedRepositoryColumn:
    canonical = canonicalize_identifier(column.name)
    display = column.display_name if column.display_name is not None else column.name
    nullable = True if column.nullable is None else column.nullable
    spelling = column.scalar_type if column.scalar_type is not None else column.raw_type
    declared, unknown = _declared_type_for(spelling)
    source = SourceColumnDescriptor(
        display_name=display,
        canonical_name=canonical,
        ordinal=column.ordinal,
        sql_type=spelling if spelling else "UNKNOWN",
        logical_type=SqlLogicalType.STANDARD,
        declared_type=declared,
        nullable=nullable,
    )
    return MappedRepositoryColumn(source=source, unknown_family=unknown)


def encode_repository_row(
    columns: tuple[RepositoryColumn, ...],
    raw: tuple[object | None, ...],
    *,
    table: str,
) -> EncodedRepositoryRow:
    if type(raw) is not tuple:
        raise ValueError("repository row must be a tuple")
    width = len(columns)
    diagnostics: list[MaterializationDiagnostic] = []
    if len(raw) < width:
        raise ValueError(f"repository row width {len(raw)} is short of catalog width {width}")
    if len(raw) > width:
        diagnostics.append(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode.REPOSITORY_SCALAR_ENCODING_DIAGNOSTIC,
                severity=DiagnosticSeverity.WARNING,
                message="extra tuple fields outside the catalog were ignored",
                table=table,
            )
        )
    cells: list[SourceCell] = []
    mapped = tuple(map_repository_column(column) for column in columns)
    for column, mapped_column, value in zip(columns, mapped, raw[:width], strict=True):
        cell, diagnostic = encode_repository_value(column, mapped_column, value, table=table)
        cells.append(cell)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return EncodedRepositoryRow(cells=tuple(cells), diagnostics=tuple(diagnostics))


def encode_repository_value(
    column: RepositoryColumn,
    mapped: MappedRepositoryColumn,
    value: object,
    *,
    table: str,
) -> tuple[SourceCell, MaterializationDiagnostic | None]:
    if value is None:
        return NullScalar(), None
    if mapped.unknown_family:
        return StringScalar(text=_as_text(value)), _encoding_warning(
            table,
            mapped.source.canonical_name,
            "scalar type family is unknown; value preserved as text",
        )
    declared = mapped.source.declared_type
    if declared is None:
        return StringScalar(text=_as_text(value)), _encoding_warning(
            table,
            mapped.source.canonical_name,
            "declared type is missing; value preserved as text",
        )
    try:
        if declared.kind is DeclaredTypeKind.BINARY:
            raw = _as_bytes(value)
            typed = normalize_logical_literal(
                declared, RawLogicalLiteral(raw_bytes=raw)
            ).typed_value
            return typed, None
        if declared.kind in {DeclaredTypeKind.FLOAT32, DeclaredTypeKind.FLOAT64}:
            number = _as_float(value)
            if not math.isfinite(number):
                raise CanonicalEncodingError(
                    CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
                    "non-finite float values are forbidden",
                )
        text = _as_text(value)
        typed = normalize_logical_literal(declared, Utf8LogicalLiteral(text=text)).typed_value
        return typed, None
    except (CanonicalEncodingError, TypeError, ValueError):
        return StringScalar(text=_as_text(value)), _encoding_warning(
            table,
            mapped.source.canonical_name,
            "value could not be parsed as the declared type; original text preserved",
        )


def _declared_type_for(spelling: str | None) -> tuple[DeclaredType, bool]:
    if spelling is None or spelling == "":
        return _STRING_TYPE, True
    token = spelling.strip().upper()
    token = re.sub(r"\s+UNSIGNED$", "", token)
    token = re.sub(r"\s+ZEROFILL$", "", token)
    match = _LEADING_TOKEN.match(token.split()[0] if " " in token and "(" not in token else token)
    if match is None:
        base = token.split("(", 1)[0].split()[0]
        args = None
    else:
        base = match.group(1)
        args = match.group(2)
    if base in {"BOOLEAN", "BOOL"}:
        return DeclaredType(kind=DeclaredTypeKind.BOOLEAN), False
    if base in _INTEGER_BITS:
        return (
            DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=_INTEGER_BITS[base]),
            False,
        )
    if base in {"FLOAT"}:
        return DeclaredType(kind=DeclaredTypeKind.FLOAT32), False
    if base in {"DOUBLE", "REAL"}:
        return DeclaredType(kind=DeclaredTypeKind.FLOAT64), False
    if base == "DECIMAL":
        precision, scale = _decimal_args(args)
        return DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=precision, scale=scale), False
    if base == "BIT":
        width = _positive_arg(args, default=1)
        return DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=width), False
    if base == "DATE":
        return DeclaredType(kind=DeclaredTypeKind.DATE), False
    if base == "DATETIME":
        return DeclaredType(kind=DeclaredTypeKind.DATETIME), False
    if base == "TIMESTAMP":
        return DeclaredType(kind=DeclaredTypeKind.TIMESTAMP), False
    if base == "TIME":
        return DeclaredType(kind=DeclaredTypeKind.TIME_DURATION), False
    if base in _TEXT_BASES:
        return _STRING_TYPE, False
    if base in _BLOB_BASES:
        return DeclaredType(kind=DeclaredTypeKind.BINARY), False
    return _STRING_TYPE, True


def _decimal_args(args: str | None) -> tuple[int, int]:
    if args is None or args == "":
        return 10, 0
    parts = [item.strip() for item in args.split(",")]
    precision = int(parts[0]) if parts and parts[0] else 10
    scale = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return precision, scale


def _positive_arg(args: str | None, *, default: int) -> int:
    if args is None or args == "":
        return default
    return int(args.split(",", 1)[0].strip())


def _as_text(value: object) -> str:
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if type(value) is bytes:
        return value.hex()
    return str(value)


def _as_bytes(value: object) -> bytes:
    if type(value) is bytes:
        return value
    if type(value) is str:
        return bytes.fromhex(value) if _looks_hex(value) else value.encode("utf-8")
    raise TypeError("binary value must be bytes or hex text")


def _as_float(value: object) -> float:
    if type(value) is float:
        return value
    if type(value) is int:
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if type(value) is str:
        return float(value)
    raise TypeError("float value must be numeric")


def _looks_hex(value: str) -> bool:
    if len(value) < 2 or len(value) % 2 != 0:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def _encoding_warning(table: str, column: str, message: str) -> MaterializationDiagnostic:
    return MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.REPOSITORY_SCALAR_ENCODING_DIAGNOSTIC,
        severity=DiagnosticSeverity.WARNING,
        message=message,
        table=table,
        column=column,
    )
