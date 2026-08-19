"""Composite logic materializer. Consumes XML document results; does not invoke a document parser."""

from __future__ import annotations

from gateway_backend.capabilities.composite_signal._ast import AstHalt, parse_logic_ast
from gateway_backend.capabilities.composite_signal._bind import bind_formulas
from gateway_backend.capabilities.composite_signal.contracts import (
    CompositeDiagnostic,
    CompositeDiagnosticCode,
    CompositeDiagnosticSeverity,
    CompositeSignalRequest,
    CompositeSignalResult,
    CompositeSignalStatus,
    ExpressNode,
)
from gateway_backend.capabilities.table_access.contracts import ParseStatus


def materialize_composite_signal(request: CompositeSignalRequest) -> CompositeSignalResult:
    if type(request) is not CompositeSignalRequest:
        raise ValueError("request must be CompositeSignalRequest")
    try:
        formulas: tuple[ExpressNode, ...] = ()
        if not request.logic.empty:
            xml = request.xml
            if xml is None:
                raise ValueError("non-empty source requires an XML document result")
            if xml.status is ParseStatus.FAILED:
                return _failed(
                    CompositeDiagnosticCode.XML_DOCUMENT_FAILED,
                    "XML document result is FAILED",
                )
            formulas = parse_logic_ast(xml.events, request.context)
        named, rows = bind_formulas(formulas, request.catalog, request.context)
    except AstHalt as halt:
        return _failed(halt.code, halt.message)
    return CompositeSignalResult(
        status=CompositeSignalStatus.COMPLETE,
        diagnostics=(),
        rows=rows,
        formulas=named,
    )


def _failed(code: CompositeDiagnosticCode, message: str) -> CompositeSignalResult:
    return CompositeSignalResult(
        status=CompositeSignalStatus.FAILED,
        diagnostics=(
            CompositeDiagnostic(
                code=code,
                severity=CompositeDiagnosticSeverity.ERROR,
                message=message,
            ),
        ),
    )
