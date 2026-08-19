"""Golden XML parser tests. Parses fixtures and compares public results."""

from __future__ import annotations

import time

import pytest
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
)
from gateway_backend.capabilities.table_access.xml import parse_xml
from tests.support.table_access_fixtures import load_expected, load_text, xml_parse_result_from_expected
from tests.support.table_access_xml import parse_xml_text, xml_request

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


@pytest.mark.parametrize("case_dir", XML_GOLDEN_CASES)
def test_xml_golden_parser_matches_expected(case_dir: str) -> None:
    xml = load_text(f"{case_dir}/input.xml")
    payload = load_expected(f"{case_dir}/expected.json")
    expected = xml_parse_result_from_expected(payload)
    actual = parse_xml_text(xml)
    assert actual.status is expected.status
    assert actual.status.value == payload["status"]
    assert actual.events == expected.events
    assert [(item.code, item.message, item.byte_offset) for item in actual.diagnostics] == [
        (item.code, item.message, item.byte_offset) for item in expected.diagnostics
    ]
    if actual.status is ParseStatus.FAILED:
        assert actual.events == ()


def test_prefixed_namespace_skips_xmlns_and_keeps_attribute_order() -> None:
    result = parse_xml_text('<root xmlns="urn:x" xmlns:ex="urn:y" b="1" a="2" ex:c="3"/>')
    assert result.status is ParseStatus.COMPLETE
    start = result.events[0]
    assert start.expanded_name == "{urn:x}root"
    assert start.attributes == (("b", "1"), ("a", "2"), ("{urn:y}c", "3"))


def test_comments_and_processing_instructions_are_ignored() -> None:
    result = parse_xml_text("<?pi data?><root><!--c-->x<!--d-->y</root>")
    assert result.status is ParseStatus.COMPLETE
    assert [event.kind.value for event in result.events] == [
        "START_ELEMENT",
        "TEXT",
        "END_ELEMENT",
    ]
    assert result.events[1].text == "xy"


def test_malformed_after_start_discards_events() -> None:
    result = parse_xml_text("<root>x</nope>")
    assert result.status is ParseStatus.FAILED
    assert result.events == ()
    assert result.diagnostics[0].code is ParserDiagnosticCode.MALFORMED_XML


def test_utf8_declaration_is_accepted() -> None:
    result = parse_xml_text('<?xml version="1.0" encoding="UTF-8"?><root/>')
    assert result.status is ParseStatus.COMPLETE
    assert result.events[0].expanded_name == "root"


def test_expired_deadline_fails_without_events() -> None:
    request = xml_request("<root/>", ParserInvocationContext(NeverCancel(), time.monotonic() - 1.0))
    result = parse_xml(request)
    assert result.status is ParseStatus.FAILED
    assert result.events == ()
    assert result.diagnostics[0].code is ParserDiagnosticCode.PARSER_TIMEOUT
    assert result.diagnostics[0].message == "parser deadline exceeded"


def test_cancel_probe_fails_without_events() -> None:
    request = xml_request("<root/>", ParserInvocationContext(CountCancel(1)))
    result = parse_xml(request)
    assert result.status is ParseStatus.FAILED
    assert result.events == ()
    assert result.diagnostics[0].code is ParserDiagnosticCode.PARSER_CANCELLED
    assert result.diagnostics[0].message == "parser cancelled"
