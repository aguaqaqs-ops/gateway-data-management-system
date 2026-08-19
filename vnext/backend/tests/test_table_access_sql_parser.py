"""Golden SQL parser tests. Parses fixtures and compares public results."""

from __future__ import annotations

import pytest
from gateway_backend.capabilities.table_access.contracts import ParseStatus
from tests.support.table_access_fixtures import load_expected, load_text, parse_result_from_expected
from tests.support.table_access_sql import consumed_rows, parse_text

SQL_GOLDEN_CASES = (
    "sql/valid/s1-minimal-create-insert",
    "sql/valid/s2-dump-boilerplate",
    "sql/malformed/s1-unsupported-replace",
    "sql/malformed/s2-incomplete-insert",
)


@pytest.mark.parametrize("case_dir", SQL_GOLDEN_CASES)
def test_sql_golden_parser_matches_expected(case_dir: str) -> None:
    sql = load_text(f"{case_dir}/input.sql")
    payload = load_expected(f"{case_dir}/expected.json")
    expected = parse_result_from_expected(payload)
    actual = parse_text(sql)
    assert actual.status is expected.status
    assert actual.status.value == payload["status"]
    assert len(actual.tables) == len(expected.tables)
    for got, want in zip(actual.tables, expected.tables, strict=True):
        assert got.descriptor == want.descriptor
        if want.reader is None:
            assert got.reader is None
        else:
            assert got.reader is not None
            assert tuple(got.reader.iter_rows()) == tuple(want.reader.iter_rows())
    assert [(item.code, item.message, item.byte_offset) for item in actual.diagnostics] == [
        (item.code, item.message, item.byte_offset) for item in expected.diagnostics
    ]
    if actual.status is ParseStatus.FAILED:
        assert all(table.reader is None for table in actual.tables)


def test_s1_minimal_preserves_insert_order() -> None:
    sql = load_text("sql/valid/s1-minimal-create-insert/input.sql")
    result = parse_text(sql)
    assert result.status is ParseStatus.COMPLETE
    rows = consumed_rows(result)
    assert len(rows) == 1
    assert len(rows[0]) == 1
