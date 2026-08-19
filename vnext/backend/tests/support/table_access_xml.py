"""Helpers for XML parser tests. Not a production parser."""

from __future__ import annotations

from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParserInvocationContext,
    ResourceBudgets,
    XmlParseRequest,
    XmlParseResult,
    XmlSourceInput,
)
from gateway_backend.capabilities.table_access.xml import parse_xml
from gateway_shared_kernel import DigestRef

_ZERO_DIGEST = DigestRef("sha256:" + "00" * 32)


def xml_request(
    xml: str | bytes,
    context: ParserInvocationContext | None = None,
) -> XmlParseRequest:
    if type(xml) is str:
        data = xml.encode("utf-8")
    elif type(xml) is bytes:
        data = xml
    else:
        raise ValueError("xml must be str or bytes")
    return XmlParseRequest(
        source=XmlSourceInput(
            document_content_digest=_ZERO_DIGEST,
            xml_source_digest=_ZERO_DIGEST,
            parser_input_contract_version=1,
            encoding="utf-8",
            source_size_bytes=len(data),
        ),
        xml_utf8=data,
        context=context or ParserInvocationContext(NeverCancel()),
    )


def parse_xml_text(
    xml: str | bytes,
    *,
    context: ParserInvocationContext | None = None,
    budgets: ResourceBudgets | None = None,
) -> XmlParseResult:
    request = xml_request(xml, context)
    if budgets is None:
        return parse_xml(request)
    return parse_xml(request, budgets=budgets)
