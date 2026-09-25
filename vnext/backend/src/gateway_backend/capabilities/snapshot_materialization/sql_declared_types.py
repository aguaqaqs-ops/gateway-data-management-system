"""Authoritative SQL column spelling to Shared Kernel DeclaredType mapping."""

from __future__ import annotations

import re

from gateway_shared_kernel import DeclaredType, DeclaredTypeKind

_TYPE_TOKEN = re.compile(r"^([A-Z]+)(?:\(([^)]*)\))?(?:\s+(UNSIGNED))?(?:\s+ZEROFILL)?.*$")
_INTEGER_BITS = {
    "TINYINT": 8,
    "SMALLINT": 16,
    "MEDIUMINT": 24,
    "INT": 32,
    "INTEGER": 32,
    "BIGINT": 64,
}
_TEXT_TYPES = frozenset(
    {"CHAR", "VARCHAR", "TINYTEXT", "TEXT", "MEDIUMTEXT", "LONGTEXT", "JSON", "ENUM", "SET"}
)
_BINARY_TYPES = frozenset(
    {"BINARY", "VARBINARY", "TINYBLOB", "BLOB", "MEDIUMBLOB", "LONGBLOB"}
)


class SqlDeclaredTypeMappingError(ValueError):
    """Raised when a SQL spelling cannot be mapped to a DeclaredType."""


def declared_type_for_sql_spelling(spelling: str) -> DeclaredType:
    """Map one SQL column type spelling to the canonical DeclaredType."""

    token = spelling.strip().upper()
    match = _TYPE_TOKEN.match(token)
    if match is None:
        raise SqlDeclaredTypeMappingError(f"unsupported SQL type spelling: {spelling}")
    base, args, unsigned = match.groups()
    if base in {"BOOLEAN", "BOOL"}:
        return DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    if base in _INTEGER_BITS:
        return DeclaredType(
            kind=(
                DeclaredTypeKind.UNSIGNED_INTEGER if unsigned else DeclaredTypeKind.SIGNED_INTEGER
            ),
            bits=_INTEGER_BITS[base],
        )
    if base == "FLOAT":
        return DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    if base in {"DOUBLE", "REAL"}:
        return DeclaredType(kind=DeclaredTypeKind.FLOAT64)
    if base == "DECIMAL":
        parts = tuple(int(item.strip()) for item in (args or "10,0").split(","))
        return DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=parts[0], scale=parts[1])
    if base == "BIT":
        return DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=int(args or "1"))
    if base == "DATE":
        return DeclaredType(kind=DeclaredTypeKind.DATE)
    if base == "DATETIME":
        return DeclaredType(kind=DeclaredTypeKind.DATETIME)
    if base == "TIMESTAMP":
        return DeclaredType(kind=DeclaredTypeKind.TIMESTAMP)
    if base == "TIME":
        return DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    if base in _TEXT_TYPES:
        return DeclaredType(kind=DeclaredTypeKind.STRING)
    if base in _BINARY_TYPES:
        return DeclaredType(kind=DeclaredTypeKind.BINARY)
    raise SqlDeclaredTypeMappingError(f"unsupported SQL type spelling: {spelling}")


def try_declared_type_for_sql_spelling(spelling: str) -> DeclaredType | None:
    try:
        return declared_type_for_sql_spelling(spelling)
    except SqlDeclaredTypeMappingError:
        return None
