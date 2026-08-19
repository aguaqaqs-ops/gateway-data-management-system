"""SQL/XML shared diagnostic, cancel/timeout and golden oracle conformance."""

from __future__ import annotations

import time

import pytest
from gateway_backend.capabilities.table_access.contracts import (
    DiagnosticSeverity,
    DiagnosticSource,
    NeverCancel,
    ParseStatus,
    ParserDiagnostic,
    ParserDiagnosticCode,
    ParserInvocationContext,
    diagnostic_sort_key,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_access.xml import parse_xml
from tests.support.table_access_fixtures import (
    load_expected,
    load_text,
    parse_result_from_expected,
    xml_parse_result_from_expected,
)
from tests.support.table_access_sql import parse_text, sql_request, tiny_budgets
from tests.support.table_access_xml import parse_xml_text, xml_request

SQL_GOLDEN_CASES = (
    "sql/valid/s1-minimal-create-insert",
    "sql/valid/s2-dump-boilerplate",
    "sql/malformed/s1-unsupported-replace",
    "sql/malformed/s2-incomplete-insert",
)
XML_GOLDEN_CASES = (
    "xml/valid/s1-minimal-element",
    "xml/valid/s3-prefixed-namespace",
    "xml/malformed/s1-truncated",
    "xml/malformed/s3-encoding-declared-latin1",
    "xml/security/s1-doctype-rejected",
    "xml/security/s3-external-entity",
    "xml/security/s3-xinclude",
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def test_diagnostic_sort_key_is_offset_then_code_for_sql_and_xml() -> None:
    sql_later = ParserDiagnostic(
        code=ParserDiagnosticCode.MALFORMED_SQL,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.SQL,
        byte_offset=8,
        message="later",
    )
    xml_later = ParserDiagnostic(
        code=ParserDiagnosticCode.MALFORMED_XML,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.XML,
        byte_offset=8,
        message="later",
    )
    sql_early = ParserDiagnostic(
        code=ParserDiagnosticCode.UNSUPPORTED_STATEMENT,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.SQL,
        byte_offset=1,
        message="early",
    )
    xml_early = ParserDiagnostic(
        code=ParserDiagnosticCode.XML_DTD_FORBIDDEN,
        severity=DiagnosticSeverity.ERROR,
        source=DiagnosticSource.XML,
        byte_offset=1,
        message="early",
    )
    assert diagnostic_sort_key(sql_early)[0] == diagnostic_sort_key(xml_early)[0]
    assert diagnostic_sort_key(sql_later)[0] == diagnostic_sort_key(xml_later)[0]
    ordered = tuple(sorted((xml_later, sql_early, xml_early, sql_later), key=diagnostic_sort_key))
    assert [item.byte_offset for item in ordered] == [1, 1, 8, 8]
    assert ordered[0].code.value < ordered[1].code.value


def test_cancel_and_timeout_copy_are_shared() -> None:
    sql_cancel = parse_sql(sql_request("CREATE TABLE t (id INT NULL);", ParserInvocationContext(CountCancel(1))))
    xml_cancel = parse_xml(xml_request("<root/>", ParserInvocationContext(CountCancel(1))))
    assert sql_cancel.status is ParseStatus.FAILED
    assert xml_cancel.status is ParseStatus.FAILED
    assert sql_cancel.diagnostics[0].code is ParserDiagnosticCode.PARSER_CANCELLED
    assert xml_cancel.diagnostics[0].code is ParserDiagnosticCode.PARSER_CANCELLED
    assert sql_cancel.diagnostics[0].message == xml_cancel.diagnostics[0].message == "parser cancelled"

    expired = ParserInvocationContext(NeverCancel(), time.monotonic() - 1.0)
    sql_timeout = parse_sql(sql_request("CREATE TABLE t (id INT NULL);", expired))
    xml_timeout = parse_xml(xml_request("<root/>", expired))
    assert sql_timeout.diagnostics[0].code is ParserDiagnosticCode.PARSER_TIMEOUT
    assert xml_timeout.diagnostics[0].code is ParserDiagnosticCode.PARSER_TIMEOUT
    assert sql_timeout.diagnostics[0].message == xml_timeout.diagnostics[0].message == "parser deadline exceeded"


def test_diagnostic_truncation_marker_copy_is_shared() -> None:
    sql = parse_text(
        "CREATE TABLE t (`Id` INT NULL, `id` INT NULL, `ID` INT NULL);",
        budgets=tiny_budgets(max_diagnostics=1, max_diagnostics_total_bytes=256),
    )
    xml = parse_xml_text(
        '<?xml version="1.0" encoding="ISO-8859-1"?><root/>',
        budgets=tiny_budgets(max_diagnostics=1, max_diagnostics_total_bytes=28),
    )
    sql_marker = [item for item in sql.diagnostics if item.code is ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED]
    xml_marker = [item for item in xml.diagnostics if item.code is ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED]
    assert sql_marker and xml_marker
    assert sql_marker[0].message == xml_marker[0].message == "parser diagnostics truncated"


@pytest.mark.parametrize("case_dir", SQL_GOLDEN_CASES)
def test_sql_golden_oracle_exact_comparison(case_dir: str) -> None:
    sql = load_text(f"{case_dir}/input.sql")
    payload = load_expected(f"{case_dir}/expected.json")
    expected = parse_result_from_expected(payload)
    actual = parse_text(sql)
    assert actual.status is expected.status
    assert [(item.code, item.message, item.byte_offset) for item in actual.diagnostics] == [
        (item.code, item.message, item.byte_offset) for item in expected.diagnostics
    ]
    assert len(actual.tables) == len(expected.tables)
    for got, want in zip(actual.tables, expected.tables, strict=True):
        assert got.descriptor == want.descriptor
        if want.reader is None:
            assert got.reader is None
        else:
            assert got.reader is not None
            assert tuple(got.reader.iter_rows()) == tuple(want.reader.iter_rows())


@pytest.mark.parametrize("case_dir", XML_GOLDEN_CASES)
def test_xml_golden_oracle_exact_comparison(case_dir: str) -> None:
    xml = load_text(f"{case_dir}/input.xml")
    payload = load_expected(f"{case_dir}/expected.json")
    expected = xml_parse_result_from_expected(payload)
    actual = parse_xml_text(xml)
    assert actual.status is expected.status
    assert actual.events == expected.events
    assert [(item.code, item.message, item.byte_offset, item.source) for item in actual.diagnostics] == [
        (item.code, item.message, item.byte_offset, item.source) for item in expected.diagnostics
    ]
