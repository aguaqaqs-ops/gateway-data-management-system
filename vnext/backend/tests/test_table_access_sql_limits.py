"""Resource budget boundary tests. Uses shrunk budgets, not huge dumps."""

from __future__ import annotations

import pytest
from gateway_backend.capabilities.table_access.contracts import ParseStatus, ParserDiagnosticCode
from tests.support.table_access_sql import parse_text, tiny_budgets

RESOURCE_LIMIT_CASES = (
    (
        "max_tables_per_source",
        "CREATE TABLE a (id INT NOT NULL PRIMARY KEY); CREATE TABLE b (id INT NOT NULL PRIMARY KEY);",
        {"max_tables_per_source": 1},
    ),
    (
        "max_columns_per_table",
        "CREATE TABLE t (a INT NULL, b INT NULL);",
        {"max_columns_per_table": 1},
    ),
    (
        "max_identifier_code_points",
        "CREATE TABLE abc (id INT NULL);",
        {"max_identifier_code_points": 2},
    ),
    (
        "max_rows_per_table",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1),(2);",
        {"max_rows_per_table": 1},
    ),
    (
        "max_rows_per_source",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1),(2);",
        {"max_rows_per_source": 1},
    ),
    (
        "max_field_bytes",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(16) NULL); INSERT INTO t VALUES (1, 'ab');",
        {"max_field_bytes": 1},
    ),
    (
        "max_statement_bytes",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);",
        {"max_statement_bytes": 8},
    ),
    (
        "max_insert_tuple_bytes",
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);",
        {"max_insert_tuple_bytes": 1},
    ),
)


@pytest.mark.parametrize(("budget", "sql", "overrides"), RESOURCE_LIMIT_CASES)
def test_resource_limit_exceeded_names_budget(
    budget: str, sql: str, overrides: dict[str, int]
) -> None:
    result = parse_text(sql, budgets=tiny_budgets(**overrides))
    assert result.status is ParseStatus.FAILED
    assert result.tables == () or all(table.reader is None for table in result.tables)
    assert any(
        item.code is ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED and budget in item.message
        for item in result.diagnostics
    )


def test_diagnostics_truncation_appends_marker() -> None:
    sql = (
        "CREATE TABLE t (`Id` INT NULL, `id` INT NULL, `ID` INT NULL);"
    )
    result = parse_text(sql, budgets=tiny_budgets(max_diagnostics=1, max_diagnostics_total_bytes=256))
    codes = [item.code for item in result.diagnostics]
    assert ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED in codes
    assert len(result.diagnostics) <= 2
