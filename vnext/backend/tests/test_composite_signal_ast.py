"""Composite logic AST golden, malformed, security, and cancel tests."""

from __future__ import annotations

import time

import pytest
from gateway_backend.capabilities.composite_signal._digest import ast_to_json
from gateway_backend.capabilities.composite_signal.contracts import (
    CompositeDiagnosticCode,
    CompositeSignalStatus,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
    RESOURCE_BUDGETS,
)
from tests.support.composite_signal import load_text, materialize_logic, special_catalog
from tests.support.table_access_fixtures import load_text as load_table_access_text
from tests.support.table_access_xml import parse_xml_text

MALFORMED_CASES = (
    ("xml/malformed/s3-unknown-element/input.xml", CompositeDiagnosticCode.UNKNOWN_ELEMENT),
    ("xml/malformed/s3-missing-operator-type/input.xml", CompositeDiagnosticCode.MISSING_ATTRIBUTE),
    ("xml/malformed/s3-empty-top-level-name/input.xml", CompositeDiagnosticCode.EMPTY_TOP_LEVEL_NAME),
    ("xml/malformed/s3-invalid-root/input.xml", CompositeDiagnosticCode.INVALID_ROOT),
)

SECURITY_CASES = (
    "xml/security/s1-doctype-rejected/input.xml",
    "xml/security/s3-external-entity/input.xml",
    "xml/security/s3-xinclude/input.xml",
)

DIGITAL_ATTRIBUTE_CASES = (
    (
        '<Logic_Set><Express Name="top" Operator_Type="+"><Digital value="1"/></Express></Logic_Set>',
        None,
    ),
    (
        '<Logic_Set><Express Name="top" Operator_Type="+"><Digital/></Express></Logic_Set>',
        CompositeDiagnosticCode.MISSING_ATTRIBUTE,
    ),
    (
        '<Logic_Set><Express Name="top" Operator_Type="+"><Digital Value="1"/></Express></Logic_Set>',
        CompositeDiagnosticCode.UNKNOWN_ATTRIBUTE,
    ),
    (
        '<Logic_Set><Express Name="top" Operator_Type="+"><Digital value="1" Extra="x"/></Express></Logic_Set>',
        CompositeDiagnosticCode.UNKNOWN_ATTRIBUTE,
    ),
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def test_minimal_logic_builds_ordered_ast() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    result = materialize_logic(xml, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.COMPLETE
    assert len(result.formulas) == 1
    assert ast_to_json(result.formulas[0].ast) == {
        "kind": "EXPRESS",
        "operator": "+",
        "name": "top",
        "children": [
            {"kind": "POINT", "name": "top"},
            {"kind": "DIGITAL", "value": "1"},
        ],
    }


@pytest.mark.parametrize(("xml", "expected_code"), DIGITAL_ATTRIBUTE_CASES)
def test_digital_value_attribute_matches_source_contract(
    xml: str, expected_code: CompositeDiagnosticCode | None
) -> None:
    result = materialize_logic(xml, catalog=special_catalog())
    if expected_code is not None:
        assert result.status is CompositeSignalStatus.FAILED
        assert result.diagnostics[0].code is expected_code
        if expected_code is CompositeDiagnosticCode.MISSING_ATTRIBUTE:
            assert result.diagnostics[0].message == "Digital requires value"
        return
    assert result.status is CompositeSignalStatus.COMPLETE
    assert ast_to_json(result.formulas[0].ast) == {
        "kind": "EXPRESS",
        "operator": "+",
        "name": "top",
        "children": [{"kind": "DIGITAL", "value": "1"}],
    }


def test_xml_depth_budget_covers_composite_ast_digest_serialization() -> None:
    def nested_logic(depth: int) -> str:
        expression_count = depth - 2
        opening = '<Logic_Set><Express Name="top" Operator_Type="+">'
        opening += '<Express Operator_Type="+">' * (expression_count - 1)
        closing = "</Express>" * expression_count
        return f'{opening}<Digital value="1"/>{closing}</Logic_Set>'

    depth_limit = RESOURCE_BUDGETS.max_xml_depth
    at_limit = parse_xml_text(nested_logic(depth_limit))
    assert at_limit.status is ParseStatus.COMPLETE
    result = materialize_logic(at_limit, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.COMPLETE
    assert result.formulas[0].formula_digest.value
    assert '"value":"1"' in result.formulas[0].formula_ast_json
    assert ast_to_json(result.formulas[0].ast)["kind"] == "EXPRESS"

    over_limit = parse_xml_text(nested_logic(depth_limit + 1))
    assert over_limit.status is ParseStatus.FAILED
    assert over_limit.events == ()
    assert over_limit.diagnostics[0].code is ParserDiagnosticCode.RESOURCE_LIMIT_EXCEEDED
    assert "max_xml_depth" in over_limit.diagnostics[0].message


def test_empty_logic_set_is_complete_with_no_formulas() -> None:
    xml = load_text("xml/valid/s3-empty-logic-set/input.xml")
    result = materialize_logic(xml, catalog=special_catalog(point_names=()))
    assert result.status is CompositeSignalStatus.COMPLETE
    assert result.formulas == ()
    assert result.rows == ()


def test_nested_express_preserves_name_and_child_order() -> None:
    xml = load_text("xml/valid/s3-nested-express/input.xml")
    result = materialize_logic(xml, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.COMPLETE
    assert ast_to_json(result.formulas[0].ast) == {
        "kind": "EXPRESS",
        "operator": "+",
        "name": "top",
        "children": [
            {
                "kind": "EXPRESS",
                "operator": "*",
                "name": "inner",
                "children": [
                    {"kind": "POINT", "name": "top"},
                    {"kind": "DIGITAL", "value": "2"},
                ],
            }
        ],
    }


def test_empty_operator_is_preserved() -> None:
    xml = load_text("xml/valid/s3-unknown-operator/input.xml")
    result = materialize_logic(xml, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.COMPLETE
    assert result.formulas[0].ast.operator == ""


def test_unknown_operator_value_is_preserved() -> None:
    xml = '<Logic_Set><Express Name="top" Operator_Type="??"><Point Name="top"/></Express></Logic_Set>'
    result = materialize_logic(xml, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.COMPLETE
    assert result.formulas[0].ast.operator == "??"


@pytest.mark.parametrize(("relative", "code"), MALFORMED_CASES)
def test_malformed_logic_fails_closed(relative: str, code: CompositeDiagnosticCode) -> None:
    result = materialize_logic(load_text(relative), catalog=special_catalog())
    assert result.status is CompositeSignalStatus.FAILED
    assert result.rows == ()
    assert result.formulas == ()
    assert result.diagnostics[0].code is code


@pytest.mark.parametrize("relative", SECURITY_CASES)
def test_security_failures_never_reach_ast(relative: str) -> None:
    parsed = parse_xml_text(load_table_access_text(relative))
    assert parsed.status is ParseStatus.FAILED
    result = materialize_logic(parsed, catalog=special_catalog())
    assert result.status is CompositeSignalStatus.FAILED
    assert result.formulas == ()
    assert result.diagnostics[0].code is CompositeDiagnosticCode.XML_DOCUMENT_FAILED


def test_empty_source_skips_xml_document() -> None:
    result = materialize_logic(empty=True, catalog=special_catalog(point_names=()))
    assert result.status is CompositeSignalStatus.COMPLETE
    assert result.formulas == ()
    assert result.rows == ()


def test_ast_digest_is_deterministic() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    left = materialize_logic(xml, catalog=special_catalog())
    right = materialize_logic(xml, catalog=special_catalog())
    assert left.formulas[0].formula_digest == right.formulas[0].formula_digest
    assert left.formulas[0].formula_ast_json == right.formulas[0].formula_ast_json


def test_cancel_fails_closed() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    result = materialize_logic(xml, catalog=special_catalog(), context=ParserInvocationContext(CountCancel(1)))
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.MATERIALIZATION_CANCELLED


def test_timeout_fails_closed() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    result = materialize_logic(
        xml,
        catalog=special_catalog(),
        context=ParserInvocationContext(CountCancel(10_000), deadline_monotonic=time.monotonic() - 1.0),
    )
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.MATERIALIZATION_TIMEOUT
