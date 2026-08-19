"""XML resource budget boundary tests. Uses shrunk budgets, not huge documents."""

from __future__ import annotations

import pytest
from gateway_backend.capabilities.table_access.contracts import ParseStatus, ParserDiagnosticCode
from tests.support.table_access_sql import tiny_budgets
from tests.support.table_access_xml import parse_xml_text

RESOURCE_LIMIT_CASES = (
    (
        "max_xml_document_bytes",
        "<root/>",
        {"max_xml_document_bytes": 1},
    ),
    (
        "max_xml_depth",
        "<a><b><c/></b></a>",
        {"max_xml_depth": 2},
    ),
    (
        "max_xml_nodes",
        "<root/>",
        {"max_xml_nodes": 1},
    ),
    (
        "max_xml_attributes_per_element",
        '<root a="1" b="2"/>',
        {"max_xml_attributes_per_element": 1},
    ),
    (
        "max_xml_attribute_bytes",
        '<root a="ab"/>',
        {"max_xml_attribute_bytes": 1},
    ),
    (
        "max_xml_text_node_bytes",
        "<root>ab</root>",
        {"max_xml_text_node_bytes": 1},
    ),
    (
        "max_xml_expanded_name_bytes",
        "<abcd/>",
        {"max_xml_expanded_name_bytes": 2},
    ),
)


@pytest.mark.parametrize(("budget", "xml", "overrides"), RESOURCE_LIMIT_CASES)
def test_xml_resource_limit_exceeded_names_budget(
    budget: str, xml: str, overrides: dict[str, int]
) -> None:
    result = parse_xml_text(xml, budgets=tiny_budgets(**overrides))
    assert result.status is ParseStatus.FAILED
    assert result.events == ()
    assert any(
        item.code is ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED and budget in item.message
        for item in result.diagnostics
    )


def test_xml_diagnostics_truncation_appends_marker() -> None:
    result = parse_xml_text(
        '<?xml version="1.0" encoding="ISO-8859-1"?><root/>',
        budgets=tiny_budgets(max_diagnostics=1, max_diagnostics_total_bytes=28),
    )
    codes = [item.code for item in result.diagnostics]
    assert ParserDiagnosticCode.PARSER_DIAGNOSTICS_TRUNCATED in codes
    assert result.events == ()
