"""Bounded XML document parser owned by the Table Access capability."""

from __future__ import annotations

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access._xml_parser import parse_xml_document
from gateway_backend.capabilities.table_access.contracts import (
    RESOURCE_BUDGETS,
    DiagnosticSource,
    ParseStatus,
    ResourceBudgets,
    XmlParseRequest,
    XmlParseResult,
)

__all__ = ["parse_xml"]


def parse_xml(
    request: XmlParseRequest,
    *,
    budgets: ResourceBudgets = RESOURCE_BUDGETS,
) -> XmlParseResult:
    if type(request) is not XmlParseRequest:
        raise ValueError("request must be XmlParseRequest")
    if type(budgets) is not ResourceBudgets:
        raise ValueError("budgets must be ResourceBudgets")
    runtime = ParserRuntime(request.context, budgets, source=DiagnosticSource.XML)
    try:
        runtime.checkpoint(0)
        if len(request.xml_utf8) > budgets.max_xml_document_bytes:
            runtime.resource_exceeded("max_xml_document_bytes", 0)
        events = parse_xml_document(request.xml_utf8, runtime)
    except ParserHalt as halt:
        runtime.record_halt(halt)
        return XmlParseResult(
            status=ParseStatus.FAILED,
            events=(),
            diagnostics=runtime.finish_diagnostics(),
        )
    if runtime.document_failed:
        return XmlParseResult(
            status=ParseStatus.FAILED,
            events=(),
            diagnostics=runtime.finish_diagnostics(),
        )
    return XmlParseResult(
        status=ParseStatus.COMPLETE,
        events=events,
        diagnostics=runtime.finish_diagnostics(),
    )
