"""Special-device invariants, exact matching, and derived-row tests."""

from __future__ import annotations

import pytest
from gateway_backend.capabilities.composite_signal.contracts import (
    SPECIAL_DEV_ADDR,
    SPECIAL_DEVICE_DESCRIPTION,
    CompositeDiagnosticCode,
    CompositeSignalStatus,
    SpecialDevice,
    SpecialPointFact,
)
from tests.support.composite_signal import load_text, materialize_logic, special_catalog

BIND_FAILURES = (
    (
        '<Logic_Set><Express Name="missing" Operator_Type="+"><Point Name="x"/></Express></Logic_Set>',
        CompositeDiagnosticCode.ORPHAN_FORMULA,
        ("top",),
    ),
    (
        (
            '<Logic_Set>'
            '<Express Name="top" Operator_Type="+"><Point Name="top"/></Express>'
            '<Express Name="top" Operator_Type="*"><Point Name="top"/></Express>'
            "</Logic_Set>"
        ),
        CompositeDiagnosticCode.DUPLICATE_TOP_LEVEL_FORMULA,
        ("top",),
    ),
)


def test_point_without_formula_is_legal() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    result = materialize_logic(xml, catalog=special_catalog(point_names=("top", "unbound")))
    assert result.status is CompositeSignalStatus.COMPLETE
    by_name = {row.point_name: row for row in result.rows}
    assert by_name["top"].formula_digest is not None
    assert by_name["top"].formula_ast_json is not None
    assert by_name["unbound"].formula_digest is None
    assert by_name["unbound"].formula_ast_json is None


def test_matching_is_exact_and_case_sensitive() -> None:
    xml = '<Logic_Set><Express Name="Top" Operator_Type="+"><Point Name="Top"/></Express></Logic_Set>'
    result = materialize_logic(xml, catalog=special_catalog(point_names=("top",)))
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.ORPHAN_FORMULA


def test_matching_does_not_trim() -> None:
    xml = '<Logic_Set><Express Name=" top" Operator_Type="+"><Point Name=" top"/></Express></Logic_Set>'
    result = materialize_logic(xml, catalog=special_catalog(point_names=("top",)))
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.ORPHAN_FORMULA


@pytest.mark.parametrize(("xml", "code", "points"), BIND_FAILURES)
def test_bind_failures_are_parameterized(
    xml: str, code: CompositeDiagnosticCode, points: tuple[str, ...]
) -> None:
    result = materialize_logic(xml, catalog=special_catalog(point_names=points))
    assert result.status is CompositeSignalStatus.FAILED
    assert result.rows == ()
    assert result.diagnostics[0].code is code


def test_duplicate_special_point_names_fail() -> None:
    catalog = special_catalog(point_names=("top",))
    duplicate = SpecialPointFact(
        source_table="device_mx",
        point_gid=99,
        dev_addr=SPECIAL_DEV_ADDR,
        point_name="top",
        payload=(("gid", 99), ("name", "top")),
    )
    catalog = type(catalog)(devices=catalog.devices, points=(*catalog.points, duplicate))
    xml = load_text("xml/valid/s3-empty-logic-set/input.xml")
    result = materialize_logic(xml, catalog=catalog)
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.DUPLICATE_SPECIAL_POINT_NAME


def test_special_device_identity_requires_unique_match() -> None:
    xml = load_text("xml/valid/s3-empty-logic-set/input.xml")
    extra = SpecialDevice(gid=9, dev_addr=SPECIAL_DEV_ADDR, description=SPECIAL_DEVICE_DESCRIPTION)
    result = materialize_logic(
        xml,
        catalog=special_catalog(point_names=(), extra_devices=(extra,)),
    )
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.SPECIAL_DEVICE_IDENTITY_INVALID


def test_nonempty_device_without_special_identity_fails() -> None:
    xml = load_text("xml/valid/s3-empty-logic-set/input.xml")
    catalog = special_catalog(point_names=(), include_device=False)
    catalog = type(catalog)(
        devices=(SpecialDevice(gid=2, dev_addr=10, description="ordinary"),),
        points=(),
    )
    result = materialize_logic(xml, catalog=catalog)
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.SPECIAL_DEVICE_IDENTITY_INVALID


def test_special_points_without_device_fail() -> None:
    result = materialize_logic(
        load_text("xml/valid/s3-empty-logic-set/input.xml"),
        catalog=special_catalog(include_device=False),
    )
    assert result.status is CompositeSignalStatus.FAILED
    assert result.diagnostics[0].code is CompositeDiagnosticCode.SPECIAL_DEVICE_IDENTITY_INVALID


def test_derived_rows_are_sorted_and_include_payload() -> None:
    xml = load_text("xml/valid/s3-minimal-logic/input.xml")
    result = materialize_logic(xml, catalog=special_catalog(point_names=("top", "unbound")))
    assert result.status is CompositeSignalStatus.COMPLETE
    assert tuple(row.point_name for row in result.rows) == ("top", "unbound")
    assert all(row.device_gid == 1 for row in result.rows)
    assert all(row.dev_addr == SPECIAL_DEV_ADDR for row in result.rows)
    assert '"name":"top"' in result.rows[0].point_payload_json
