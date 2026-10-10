"""SQL dump parser reject and table-level error cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gateway_backend.capabilities.table_access.contracts import ParseStatus, ParserDiagnosticCode
from gateway_shared_kernel import canonicalize_identifier
from tests.support.table_access_sql import parse_text

SQL_STATEMENT_REJECTS = (
    ("REPLACE INTO `t` VALUES (1);", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "REPLACE"),
    ("INSERT IGNORE INTO `t` VALUES (1);", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "INSERT IGNORE"),
    ("USE db;", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "USE"),
    ("CREATE DATABASE d;", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "CREATE"),
    (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO `t` SET `id`=1;",
        ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        "INSERT ... SET",
    ),
    ("UPDATE `t` SET `id`=1;", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "UPDATE"),
    ('CREATE TABLE "t" (id INT);', ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "ANSI_QUOTES"),
    (
        "SET @@saved_cs_client = 1;",
        ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        "@@saved_cs_client",
    ),
    ("SET @other_client = 1;", ParserDiagnosticCode.UNSUPPORTED_STATEMENT, "@other_client"),
    (
        "SET @character_set_client = utf8mb4;",
        ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        "@character_set_client",
    ),
)

SQL_TYPE_MALFORMED_SHAPES = (
    "ENUM()",
    "ENUM('a','a')",
    "SET('')",
    "SET('a,b')",
    "ENUM('a',)",
    "TIME(7)",
    "DECIMAL(70,0)",
)

SQL_VALUE_ILLEGAL_SHAPES = (
    (
        "CREATE TABLE t (e ENUM('a','b') NOT NULL PRIMARY KEY); INSERT INTO t VALUES ('c');",
        ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
        "ENUM",
    ),
    (
        "CREATE TABLE t (s SET('a','b') NOT NULL PRIMARY KEY); INSERT INTO t VALUES ('c');",
        ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
        "SET",
    ),
    (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (NULL);",
        ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
        "NULL",
    ),
    (
        "CREATE TABLE t (id TINYINT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (9999);",
        ParserDiagnosticCode.SQL_VALUE_ILLEGAL,
        "integer",
    ),
)

IDENTIFIER_VECTOR_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "vectors"
    / "table-access"
    / "sql-identifier"
    / "v1"
)


@pytest.mark.parametrize(("sql", "code", "needle"), SQL_STATEMENT_REJECTS)
def test_unsupported_statements_fail_document(sql: str, code: ParserDiagnosticCode, needle: str) -> None:
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert result.tables == ()
    assert result.diagnostics[0].code is code
    assert needle in result.diagnostics[0].message


@pytest.mark.parametrize("sql_type", SQL_TYPE_MALFORMED_SHAPES)
def test_malformed_sql_types_do_not_publish_reader(sql_type: str) -> None:
    sql = f"CREATE TABLE t (`c` {sql_type} NULL);"
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert result.tables[0].reader is None
    assert result.diagnostics[0].code is ParserDiagnosticCode.SQL_TYPE_MALFORMED


def test_unknown_year_type_keeps_descriptor_without_reader() -> None:
    result = parse_text("CREATE TABLE t (`y` YEAR NULL);")
    assert result.status is ParseStatus.FAILED
    assert result.tables[0].descriptor.reader_ready is False
    assert result.tables[0].descriptor.columns[0].logical_type.value == "unknown"
    assert result.diagnostics[0].code is ParserDiagnosticCode.UNKNOWN_SQL_TYPE


@pytest.mark.parametrize(("sql", "code", "needle"), SQL_VALUE_ILLEGAL_SHAPES)
def test_illegal_values_invalidate_table(sql: str, code: ParserDiagnosticCode, needle: str) -> None:
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert result.tables[0].reader is None
    assert any(item.code is code and needle.lower() in item.message.lower() for item in result.diagnostics)


def test_duplicate_table_and_if_not_exists_still_errors() -> None:
    sql = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);"
        "CREATE TABLE IF NOT EXISTS t (id INT NOT NULL PRIMARY KEY);"
    )
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert result.tables[0].reader is None
    assert any(item.code is ParserDiagnosticCode.DUPLICATE_TABLE for item in result.diagnostics)


def test_canonical_identifier_collision_on_columns() -> None:
    sql = "CREATE TABLE t (`Id` INT NOT NULL, `id` INT NULL);"
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert any(
        item.code is ParserDiagnosticCode.CANONICAL_IDENTIFIER_COLLISION for item in result.diagnostics
    )


def test_duplicate_primary_key_is_table_error() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, PRIMARY KEY (id));"
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert any(item.code is ParserDiagnosticCode.DUPLICATE_PRIMARY_KEY for item in result.diagnostics)


def test_row_shape_mismatch() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1, 2);"
    result = parse_text(sql)
    assert result.status is ParseStatus.FAILED
    assert any(item.code is ParserDiagnosticCode.ROW_SHAPE_MISMATCH for item in result.diagnostics)


def test_partial_status_with_unknown_and_ready_tables() -> None:
    sql = (
        "CREATE TABLE ok (id INT NOT NULL PRIMARY KEY); INSERT INTO ok VALUES (1);"
        "CREATE TABLE bad (`y` YEAR NULL);"
    )
    result = parse_text(sql)
    assert result.status is ParseStatus.PARTIAL
    assert result.tables[0].reader is not None
    assert result.tables[1].reader is None


def test_identifier_vector_ascii_fold() -> None:
    payload = json.loads((IDENTIFIER_VECTOR_ROOT / "cases.json").read_text(encoding="utf-8"))
    for item in payload["cases"]:
        assert canonicalize_identifier(item["display"]) == item["canonical"]
