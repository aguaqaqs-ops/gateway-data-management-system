"""Secure bounded XML event parser using stdlib expat."""

from __future__ import annotations

from typing import NoReturn
from xml.parsers import expat

from gateway_backend.capabilities.table_access._parser_runtime import ParserHalt, ParserRuntime
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    XmlEvent,
    XmlEventKind,
)

_CHUNK_BYTES = 64 * 1024
_XINCLUDE_NS = "http://www.w3.org/2001/XInclude"
_XMLNS_NS = "http://www.w3.org/2000/xmlns/"
_UTF8_ENCODINGS = frozenset({"utf-8", "utf8"})
_NETWORK_PREFIXES = ("http://", "https://", "ftp://", "file://")
_TRUNCATED_ERROR_CODES = frozenset(
    {
        expat.errors.codes[expat.errors.XML_ERROR_UNCLOSED_TOKEN],
        expat.errors.codes[expat.errors.XML_ERROR_NO_ELEMENTS],
        expat.errors.codes[expat.errors.XML_ERROR_UNCLOSED_CDATA_SECTION],
        expat.errors.codes[expat.errors.XML_ERROR_ASYNC_ENTITY],
        expat.errors.codes[expat.errors.XML_ERROR_PARTIAL_CHAR],
    }
)


def parse_xml_document(xml_utf8: bytes, runtime: ParserRuntime) -> tuple[XmlEvent, ...]:
    if type(xml_utf8) is not bytes:
        raise ValueError("xml_utf8 must be bytes")
    handler = _XmlHandler(runtime)
    try:
        handler.parse(xml_utf8)
    except ParserHalt:
        raise
    except expat.ExpatError as exc:
        runtime.fail_document(
            ParserDiagnosticCode.MALFORMED_XML,
            _malformed_message(exc),
            _expat_error_offset(exc, xml_utf8),
        )
    return handler.finish()


class _XmlHandler:
    def __init__(self, runtime: ParserRuntime) -> None:
        self._runtime = runtime
        self._parser = expat.ParserCreate("UTF-8", "}")
        self._parser.ordered_attributes = True
        self._parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        self._parser.XmlDeclHandler = self._xml_decl
        self._parser.StartDoctypeDeclHandler = self._start_doctype
        self._parser.EndDoctypeDeclHandler = self._end_doctype
        self._parser.EntityDeclHandler = self._entity_decl
        self._parser.UnparsedEntityDeclHandler = self._unparsed_entity
        self._parser.NotationDeclHandler = self._notation_decl
        self._parser.ElementDeclHandler = self._element_decl
        self._parser.AttlistDeclHandler = self._attlist_decl
        self._parser.ExternalEntityRefHandler = self._external_entity_ref
        self._parser.StartElementHandler = self._start_element
        self._parser.EndElementHandler = self._end_element
        self._parser.CharacterDataHandler = self._character_data
        self._events: list[XmlEvent] = []
        self._depth = 0
        self._text_chunks: list[str] = []
        self._text_bytes = 0

    def parse(self, xml_utf8: bytes) -> None:
        offset = 0
        length = len(xml_utf8)
        if length == 0:
            self._runtime.fail_document(
                ParserDiagnosticCode.MALFORMED_XML,
                "XML document is truncated",
                0,
            )
        while offset < length:
            self._runtime.checkpoint(offset)
            end = min(offset + _CHUNK_BYTES, length)
            self._parser.Parse(xml_utf8[offset:end], False)
            offset = end
        self._parser.Parse(b"", True)
        self._flush_text()

    def finish(self) -> tuple[XmlEvent, ...]:
        self._flush_text()
        return tuple(self._events)

    def _xml_decl(self, version: str, encoding: str | None, standalone: int) -> None:
        del version, standalone
        self._runtime.checkpoint(self._offset())
        if encoding is None or encoding.strip() == "":
            return
        normalized = encoding.strip().lower().replace("_", "-")
        if normalized not in _UTF8_ENCODINGS:
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_ENCODING_FORBIDDEN,
                "XML encoding declaration must be UTF-8",
                self._offset(),
            )

    def _start_doctype(
        self, doctype_name: str, sysid: str | None, pubid: str | None, has_internal_subset: int
    ) -> None:
        del doctype_name, pubid, has_internal_subset
        offset = self._offset()
        self._runtime.checkpoint(offset)
        if _is_network_resource(sysid):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
                "XML external resource is forbidden",
                offset,
            )

    def _end_doctype(self) -> None:
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_DTD_FORBIDDEN,
            "DOCTYPE/DTD is forbidden",
            self._offset(),
        )

    def _entity_decl(
        self,
        entity_name: str,
        is_parameter_entity: int,
        value: str | None,
        base: str | None,
        system_id: str | None,
        public_id: str | None,
        notation_name: str | None,
    ) -> None:
        del entity_name, is_parameter_entity, value, base, public_id, notation_name
        offset = self._offset()
        if _is_network_resource(system_id):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
                "XML external resource is forbidden",
                offset,
            )
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_EXTERNAL_ENTITY_FORBIDDEN,
            "XML entities are forbidden",
            offset,
        )

    def _unparsed_entity(
        self,
        entity_name: str,
        base: str | None,
        system_id: str | None,
        public_id: str | None,
        notation_name: str,
    ) -> None:
        del entity_name, base, public_id, notation_name
        offset = self._offset()
        if _is_network_resource(system_id):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
                "XML external resource is forbidden",
                offset,
            )
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_EXTERNAL_ENTITY_FORBIDDEN,
            "XML entities are forbidden",
            offset,
        )

    def _notation_decl(
        self, notation_name: str, base: str | None, system_id: str | None, public_id: str | None
    ) -> None:
        del notation_name, base, public_id
        offset = self._offset()
        if _is_network_resource(system_id):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
                "XML external resource is forbidden",
                offset,
            )
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_DTD_FORBIDDEN,
            "DOCTYPE/DTD is forbidden",
            offset,
        )

    def _element_decl(self, name: str, model: object) -> None:
        del name, model
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_DTD_FORBIDDEN,
            "DOCTYPE/DTD is forbidden",
            self._offset(),
        )

    def _attlist_decl(
        self, elname: str, attname: str, type_: str, default: str | None, required: int
    ) -> None:
        del elname, attname, type_, default, required
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_DTD_FORBIDDEN,
            "DOCTYPE/DTD is forbidden",
            self._offset(),
        )

    def _external_entity_ref(
        self, context: str | None, base: str | None, system_id: str | None, public_id: str | None
    ) -> NoReturn:
        del context, base, public_id
        offset = self._offset()
        if _is_network_resource(system_id):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_NETWORK_FORBIDDEN,
                "XML external resource is forbidden",
                offset,
            )
        self._runtime.fail_document(
            ParserDiagnosticCode.XML_EXTERNAL_ENTITY_FORBIDDEN,
            "XML entities are forbidden",
            offset,
        )

    def _start_element(self, name: str, attrs: dict[str, str] | list[str]) -> None:
        self._flush_text()
        offset = self._offset()
        self._runtime.checkpoint(offset)
        expanded = _expand_name(name)
        if _is_xinclude(expanded):
            self._runtime.fail_document(
                ParserDiagnosticCode.XML_XINCLUDE_FORBIDDEN,
                "XInclude is forbidden",
                offset,
            )
        self._check_expanded_name(expanded, offset)
        attributes = self._parse_attributes(attrs, offset)
        next_depth = self._depth + 1
        if next_depth > self._runtime.budgets.max_xml_depth:
            self._runtime.resource_exceeded("max_xml_depth", offset)
        self._add_event(
            XmlEvent(
                kind=XmlEventKind.START_ELEMENT,
                expanded_name=expanded,
                attributes=attributes,
            ),
            offset,
        )
        self._depth = next_depth

    def _end_element(self, name: str) -> None:
        self._flush_text()
        offset = self._offset()
        self._runtime.checkpoint(offset)
        expanded = _expand_name(name)
        self._check_expanded_name(expanded, offset)
        self._add_event(
            XmlEvent(kind=XmlEventKind.END_ELEMENT, expanded_name=expanded),
            offset,
        )
        if self._depth > 0:
            self._depth -= 1

    def _character_data(self, data: str) -> None:
        self._runtime.checkpoint(self._offset())
        if data:
            self._text_bytes += len(data.encode("utf-8"))
            if self._text_bytes > self._runtime.budgets.max_xml_text_node_bytes:
                self._runtime.resource_exceeded("max_xml_text_node_bytes", self._offset())
            self._text_chunks.append(data)

    def _flush_text(self) -> None:
        if not self._text_chunks:
            return
        text = "".join(self._text_chunks)
        self._text_chunks.clear()
        self._text_bytes = 0
        if text == "":
            return
        offset = self._offset()
        encoded = text.encode("utf-8")
        if len(encoded) > self._runtime.budgets.max_xml_text_node_bytes:
            self._runtime.resource_exceeded("max_xml_text_node_bytes", offset)
        self._add_event(XmlEvent(kind=XmlEventKind.TEXT, text=text), offset)

    def _parse_attributes(
        self, attrs: dict[str, str] | list[str], offset: int
    ) -> tuple[tuple[str, str], ...]:
        pairs: list[tuple[str, str]] = []
        for raw_name, value in _iter_attributes(attrs):
            expanded = _expand_name(raw_name)
            if _is_xmlns_attribute(raw_name, expanded):
                continue
            self._check_expanded_name(expanded, offset)
            if type(value) is not str:
                self._runtime.fail_document(
                    ParserDiagnosticCode.MALFORMED_XML,
                    "attribute value must be a string",
                    offset,
                )
            if len(value.encode("utf-8")) > self._runtime.budgets.max_xml_attribute_bytes:
                self._runtime.resource_exceeded("max_xml_attribute_bytes", offset)
            pairs.append((expanded, value))
        if len(pairs) > self._runtime.budgets.max_xml_attributes_per_element:
            self._runtime.resource_exceeded("max_xml_attributes_per_element", offset)
        return tuple(pairs)

    def _check_expanded_name(self, name: str, offset: int) -> None:
        if len(name.encode("utf-8")) > self._runtime.budgets.max_xml_expanded_name_bytes:
            self._runtime.resource_exceeded("max_xml_expanded_name_bytes", offset)

    def _add_event(self, event: XmlEvent, offset: int) -> None:
        if len(self._events) >= self._runtime.budgets.max_xml_nodes:
            self._runtime.resource_exceeded("max_xml_nodes", offset)
        self._events.append(event)

    def _offset(self) -> int:
        index = int(self._parser.CurrentByteIndex)
        return index if index >= 0 else 0


def _expand_name(name: str) -> str:
    separator = name.find("}")
    if separator < 0:
        return name
    uri = name[:separator]
    local = name[separator + 1 :]
    if uri == "":
        return local
    return "{" + uri + "}" + local


def _is_xmlns_attribute(raw_name: str, expanded: str) -> bool:
    if raw_name == "xmlns" or raw_name.startswith("xmlns:"):
        return True
    return expanded.startswith("{" + _XMLNS_NS + "}")


def _is_xinclude(expanded: str) -> bool:
    return expanded == "{" + _XINCLUDE_NS + "}include"


def _is_network_resource(system_id: str | None) -> bool:
    if type(system_id) is not str or system_id == "":
        return False
    lowered = system_id.strip().lower()
    return lowered.startswith(_NETWORK_PREFIXES)


def _iter_attributes(attrs: dict[str, str] | list[str]) -> list[tuple[str, str]]:
    if type(attrs) is dict:
        return [(name, value) for name, value in attrs.items()]
    if type(attrs) is not list:
        return []
    pairs: list[tuple[str, str]] = []
    index = 0
    while index + 1 < len(attrs):
        pairs.append((attrs[index], attrs[index + 1]))
        index += 2
    return pairs


def _malformed_message(exc: expat.ExpatError) -> str:
    if type(exc.code) is int and exc.code in _TRUNCATED_ERROR_CODES:
        return "XML document is truncated"
    return "XML document is malformed"


def _expat_error_offset(exc: expat.ExpatError, xml_utf8: bytes) -> int:
    offset = getattr(exc, "offset", None)
    if type(offset) is int and offset >= 0:
        # expat reports a column offset on the error line; reconstruct when possible.
        line = getattr(exc, "lineno", 1)
        if type(line) is int and line >= 1:
            reconstructed = _offset_from_line_column(xml_utf8, line, offset)
            if reconstructed is not None:
                return reconstructed
        if offset <= len(xml_utf8):
            return offset
    return 0


def _offset_from_line_column(xml_utf8: bytes, lineno: int, column: int) -> int | None:
    line = 1
    index = 0
    length = len(xml_utf8)
    while index < length and line < lineno:
        if xml_utf8[index] == 0x0A:
            line += 1
        index += 1
    if line != lineno:
        return None
    target = index + column
    if target < 0:
        return 0
    if target > length:
        return length
    return target
