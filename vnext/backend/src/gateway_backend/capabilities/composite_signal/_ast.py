"""Strict business AST builder over bounded XML events."""

from __future__ import annotations

import time

from gateway_backend.capabilities.composite_signal.contracts import (
    CompositeDiagnosticCode,
    DigitalNode,
    ExpressNode,
    PointNode,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserInvocationContext,
    XmlEvent,
    XmlEventKind,
)

_ROOT = "Logic_Set"
_EXPRESS = "Express"
_POINT = "Point"
_DIGITAL = "Digital"
_ATTR_TIME = "Time"
_ATTR_NAME = "Name"
_ATTR_OPERATOR = "Operator_Type"
_ATTR_VALUE = "Value"
_ALLOWED_ROOT_ATTRS = frozenset({_ATTR_TIME})
_ALLOWED_EXPRESS_ATTRS = frozenset({_ATTR_NAME, _ATTR_OPERATOR})
_ALLOWED_POINT_ATTRS = frozenset({_ATTR_NAME})
_ALLOWED_DIGITAL_ATTRS = frozenset({_ATTR_VALUE})


class AstHalt(Exception):
    def __init__(self, code: CompositeDiagnosticCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_logic_ast(
    events: tuple[XmlEvent, ...],
    context: ParserInvocationContext,
) -> tuple[ExpressNode, ...]:
    if type(events) is not tuple:
        raise ValueError("events must be a tuple")
    checkpoint(context)
    if not events:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "XML document has no root element")
    frames: list[_Frame] = []
    formulas: list[ExpressNode] = []
    finished = False
    for event in events:
        checkpoint(context)
        if event.kind is XmlEventKind.TEXT:
            _handle_text(event.text or "", finished)
            continue
        if finished:
            raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "unexpected content after Logic_Set")
        if event.kind is XmlEventKind.START_ELEMENT:
            _handle_start(frames, event.expanded_name or "", event.attributes or ())
            continue
        _handle_end(frames, formulas, event.expanded_name or "")
        if not frames:
            finished = True
    if frames:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "XML document is truncated")
    if not finished:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "XML document has no root element")
    return tuple(formulas)


def checkpoint(context: ParserInvocationContext) -> None:
    if context.cancel_requested.is_set():
        raise AstHalt(CompositeDiagnosticCode.MATERIALIZATION_CANCELLED, "materialization cancelled")
    deadline = context.deadline_monotonic
    if deadline is not None and time.monotonic() >= deadline:
        raise AstHalt(CompositeDiagnosticCode.MATERIALIZATION_TIMEOUT, "materialization deadline exceeded")


class _Frame:
    def __init__(self, name: str, attributes: dict[str, str], top_level: bool) -> None:
        self.name = name
        self.attributes = attributes
        self.top_level = top_level
        self.children: list[ExpressNode | PointNode | DigitalNode] = []


def _handle_text(text: str, finished: bool) -> None:
    if text.strip() == "":
        return
    if finished:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "unexpected content after Logic_Set")
    raise AstHalt(CompositeDiagnosticCode.UNEXPECTED_TEXT, "non-whitespace text is not allowed")


def _handle_start(
    frames: list[_Frame],
    expanded: str,
    attributes: tuple[tuple[str, str], ...],
) -> None:
    if "{" in expanded:
        if not frames:
            raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "root element must be Logic_Set")
        raise AstHalt(CompositeDiagnosticCode.UNKNOWN_ELEMENT, f"unknown element {expanded!r}")
    if not frames:
        if expanded != _ROOT:
            raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "root element must be Logic_Set")
        frames.append(_Frame(expanded, _require_attrs(attributes, _ALLOWED_ROOT_ATTRS, _ROOT), False))
        return
    parent = frames[-1]
    if parent.name == _ROOT:
        if expanded != _EXPRESS:
            raise AstHalt(CompositeDiagnosticCode.UNKNOWN_ELEMENT, f"unknown element {expanded!r}")
        frames.append(_Frame(expanded, _require_attrs(attributes, _ALLOWED_EXPRESS_ATTRS, _EXPRESS), True))
        return
    if parent.name == _EXPRESS:
        if expanded == _EXPRESS:
            frames.append(
                _Frame(expanded, _require_attrs(attributes, _ALLOWED_EXPRESS_ATTRS, _EXPRESS), False)
            )
            return
        if expanded == _POINT:
            frames.append(_Frame(expanded, _require_attrs(attributes, _ALLOWED_POINT_ATTRS, _POINT), False))
            return
        if expanded == _DIGITAL:
            frames.append(
                _Frame(expanded, _require_attrs(attributes, _ALLOWED_DIGITAL_ATTRS, _DIGITAL), False)
            )
            return
        raise AstHalt(CompositeDiagnosticCode.UNKNOWN_ELEMENT, f"unknown element {expanded!r}")
    raise AstHalt(CompositeDiagnosticCode.UNKNOWN_ELEMENT, f"unknown element {expanded!r}")


def _handle_end(frames: list[_Frame], formulas: list[ExpressNode], expanded: str) -> None:
    if not frames:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "unbalanced end element")
    frame = frames.pop()
    if frame.name != expanded:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "unbalanced end element")
    if frame.name == _ROOT:
        return
    node: ExpressNode | PointNode | DigitalNode
    if frame.name == _EXPRESS:
        node = _build_express(frame)
        if frame.top_level:
            formulas.append(node)
            return
    elif frame.name == _POINT:
        if _ATTR_NAME not in frame.attributes:
            raise AstHalt(CompositeDiagnosticCode.MISSING_ATTRIBUTE, "Point requires Name")
        node = PointNode(name=frame.attributes[_ATTR_NAME])
    elif frame.name == _DIGITAL:
        if _ATTR_VALUE not in frame.attributes:
            raise AstHalt(CompositeDiagnosticCode.MISSING_ATTRIBUTE, "Digital requires Value")
        node = DigitalNode(value=frame.attributes[_ATTR_VALUE])
    else:
        raise AstHalt(CompositeDiagnosticCode.UNKNOWN_ELEMENT, f"unknown element {expanded!r}")
    if not frames or frames[-1].name != _EXPRESS:
        raise AstHalt(CompositeDiagnosticCode.INVALID_ROOT, "illegal nesting")
    frames[-1].children.append(node)


def _build_express(frame: _Frame) -> ExpressNode:
    if _ATTR_OPERATOR not in frame.attributes:
        raise AstHalt(CompositeDiagnosticCode.MISSING_ATTRIBUTE, "Express requires Operator_Type")
    name = frame.attributes.get(_ATTR_NAME)
    if frame.top_level:
        if name is None:
            raise AstHalt(CompositeDiagnosticCode.MISSING_ATTRIBUTE, "top-level Express requires Name")
        if name == "":
            raise AstHalt(CompositeDiagnosticCode.EMPTY_TOP_LEVEL_NAME, "top-level Express Name is empty")
    return ExpressNode(
        operator=frame.attributes[_ATTR_OPERATOR],
        children=tuple(frame.children),
        name=name,
    )


def _require_attrs(
    pairs: tuple[tuple[str, str], ...],
    allowed: frozenset[str],
    element: str,
) -> dict[str, str]:
    collected: dict[str, str] = {}
    for name, value in pairs:
        if "{" in name or name not in allowed:
            raise AstHalt(
                CompositeDiagnosticCode.UNKNOWN_ATTRIBUTE,
                f"{element} forbids attribute {name!r}",
            )
        collected[name] = value
    return collected
