"""Known SQL type mapping for the dump parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gateway_backend.capabilities.table_access._sql_types import map_sql_type
from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    ParserDiagnosticCode,
    SqlLogicalType,
)
from gateway_shared_kernel import DeclaredType, DeclaredTypeKind

VECTOR_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "vectors" / "table-access" / "sql-known-types" / "v1"
)

SQL_KNOWN_TYPE_CASES = (
    ("BOOLEAN", "BOOLEAN", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.BOOLEAN), None),
    ("BOOL", "BOOLEAN", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.BOOLEAN), None),
    ("TINYINT(1)", "TINYINT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=8), None),
    ("INT(11)", "INT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32), None),
    ("INTEGER", "INT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32), None),
    ("INT UNSIGNED", "INT UNSIGNED", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=32), None),
    ("MEDIUMINT", "MEDIUMINT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=24), None),
    ("BIGINT ZEROFILL", "BIGINT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=64), None),
    ("DECIMAL(10,2)", "DECIMAL(10,2)", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.DECIMAL, precision=10, scale=2), None),
    ("FLOAT", "FLOAT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.FLOAT32), None),
    ("DOUBLE", "DOUBLE", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.FLOAT64), None),
    ("BIT(8)", "BIT(8)", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=8), None),
    ("DATE", "DATE", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.DATE), None),
    ("TIME", "TIME", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.TIME_DURATION), None),
    ("DATETIME(6)", "DATETIME(6)", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.DATETIME), None),
    ("TIMESTAMP", "TIMESTAMP", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.TIMESTAMP), None),
    ("VARCHAR(16)", "VARCHAR(16)", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.STRING), None),
    ("TEXT CHARACTER SET utf8mb4", "TEXT", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.STRING), None),
    ("BLOB", "BLOB", SqlLogicalType.STANDARD, DeclaredType(kind=DeclaredTypeKind.BINARY), None),
    ("JSON", "JSON", SqlLogicalType.JSON, DeclaredType(kind=DeclaredTypeKind.STRING), None),
    ("ENUM('a','b')", "ENUM('a','b')", SqlLogicalType.ENUM, DeclaredType(kind=DeclaredTypeKind.STRING), None),
    ("SET('x','y')", "SET('x','y')", SqlLogicalType.SET, None, None),
    ("YEAR", "YEAR", SqlLogicalType.UNKNOWN, None, ParserDiagnosticCode.UNKNOWN_SQL_TYPE),
    ("ENUM()", "ENUM()", SqlLogicalType.UNKNOWN, None, ParserDiagnosticCode.SQL_TYPE_MALFORMED),
    ("TIME(7)", "TIME(7)", SqlLogicalType.UNKNOWN, None, ParserDiagnosticCode.SQL_TYPE_MALFORMED),
)


@pytest.mark.parametrize(
    ("raw", "sql_type", "logical", "declared", "error"),
    SQL_KNOWN_TYPE_CASES,
    ids=[item[0] for item in SQL_KNOWN_TYPE_CASES],
)
def test_known_sql_type_mapping(
    raw: str,
    sql_type: str,
    logical: SqlLogicalType,
    declared: DeclaredType | None,
    error: ParserDiagnosticCode | None,
) -> None:
    mapped = map_sql_type(raw, max_enum_set_bytes=RESOURCE_BUDGETS.max_enum_set_sql_type_bytes)
    assert mapped.sql_type == sql_type
    assert mapped.logical_type is logical
    assert mapped.declared_type == declared
    assert mapped.error is error


def test_known_type_vector_file_matches_parameter_table() -> None:
    payload = json.loads((VECTOR_ROOT / "cases.json").read_text(encoding="utf-8"))
    names = [item[0] for item in SQL_KNOWN_TYPE_CASES]
    assert payload["cases"] == names
