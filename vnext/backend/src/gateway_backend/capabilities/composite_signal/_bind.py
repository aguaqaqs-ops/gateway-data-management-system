"""Bind formulas to special-device points and emit derived rows."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.composite_signal._ast import AstHalt, checkpoint
from gateway_backend.capabilities.composite_signal._digest import formula_ast_json, formula_digest_of
from gateway_backend.capabilities.composite_signal.contracts import (
    SPECIAL_DEV_ADDR,
    SPECIAL_DEVICE_DESCRIPTION,
    CompositeDiagnosticCode,
    CompositeSignalPointRow,
    ExpressNode,
    NamedFormula,
    SpecialDevice,
    SpecialDeviceCatalog,
    SpecialPointFact,
)
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext


def bind_formulas(
    formulas: tuple[ExpressNode, ...],
    catalog: SpecialDeviceCatalog,
    context: ParserInvocationContext,
) -> tuple[tuple[NamedFormula, ...], tuple[CompositeSignalPointRow, ...]]:
    checkpoint(context)
    special = _require_special_device(catalog)
    named = _named_formulas(formulas)
    checkpoint(context)
    points = catalog.points
    _reject_duplicate_point_names(points)
    if special is None:
        if points:
            raise AstHalt(
                CompositeDiagnosticCode.SPECIAL_DEVICE_IDENTITY_INVALID,
                "special points require the special device identity",
            )
        if named:
            raise AstHalt(
                CompositeDiagnosticCode.ORPHAN_FORMULA,
                f"orphan formula {named[0].name!r} is not bound to a special point",
            )
        return named, ()
    unused = {formula.name for formula in named}
    rows: list[CompositeSignalPointRow] = []
    for point in points:
        checkpoint(context)
        formula = _formula_for(point.point_name, named)
        if formula is not None:
            unused.discard(formula.name)
        rows.append(_row_for(point, special, formula))
    if unused:
        leftover = sorted(unused)[0]
        raise AstHalt(
            CompositeDiagnosticCode.ORPHAN_FORMULA,
            f"orphan formula {leftover!r} is not bound to a special point",
        )
    rows.sort(key=lambda item: (item.source_table, item.point_gid))
    return named, tuple(rows)


def _require_special_device(catalog: SpecialDeviceCatalog) -> SpecialDevice | None:
    if not catalog.devices:
        return None
    matching = [
        device
        for device in catalog.devices
        if device.dev_addr == SPECIAL_DEV_ADDR and device.description == SPECIAL_DEVICE_DESCRIPTION
    ]
    if len(matching) != 1:
        raise AstHalt(
            CompositeDiagnosticCode.SPECIAL_DEVICE_IDENTITY_INVALID,
            "device table must contain exactly one special device identity",
        )
    return matching[0]


def _named_formulas(formulas: tuple[ExpressNode, ...]) -> tuple[NamedFormula, ...]:
    seen: set[str] = set()
    named: list[NamedFormula] = []
    for node in formulas:
        name = node.name
        if name is None or name == "":
            raise AstHalt(CompositeDiagnosticCode.EMPTY_TOP_LEVEL_NAME, "top-level Express Name is empty")
        if name in seen:
            raise AstHalt(
                CompositeDiagnosticCode.DUPLICATE_TOP_LEVEL_FORMULA,
                f"duplicate top-level formula name {name!r}",
            )
        seen.add(name)
        named.append(
            NamedFormula(
                name=name,
                ast=node,
                formula_digest=formula_digest_of(node),
                formula_ast_json=formula_ast_json(node),
            )
        )
    return tuple(named)


def _reject_duplicate_point_names(points: tuple[SpecialPointFact, ...]) -> None:
    seen: set[str] = set()
    for point in points:
        if point.point_name in seen:
            raise AstHalt(
                CompositeDiagnosticCode.DUPLICATE_SPECIAL_POINT_NAME,
                f"duplicate special point name {point.point_name!r}",
            )
        seen.add(point.point_name)


def _formula_for(point_name: str, formulas: tuple[NamedFormula, ...]) -> NamedFormula | None:
    for formula in formulas:
        if formula.name == point_name:
            return formula
    return None


def _row_for(
    point: SpecialPointFact,
    special: SpecialDevice,
    formula: NamedFormula | None,
) -> CompositeSignalPointRow:
    return CompositeSignalPointRow(
        source_table=point.source_table,
        point_gid=point.point_gid,
        dev_addr=point.dev_addr,
        device_gid=special.gid,
        point_name=point.point_name,
        point_payload_json=_payload_json(point.payload),
        formula_digest=None if formula is None else formula.formula_digest.value,
        formula_ast_json=None if formula is None else formula.formula_ast_json,
    )


def _payload_json(payload: tuple[tuple[str, Any], ...]) -> str:
    return canonicalize_json_value(dict(payload)).decode("utf-8")
