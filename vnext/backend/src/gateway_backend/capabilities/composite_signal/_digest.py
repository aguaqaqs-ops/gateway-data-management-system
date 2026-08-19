"""Formula AST digest helpers owned by composite_signal."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.composite_signal.contracts import (
    DigitalNode,
    ExpressNode,
    PointNode,
)

_FORMULA_KIND = "composite-formula-ast"


def ast_to_json(node: ExpressNode | PointNode | DigitalNode) -> dict[str, Any]:
    if isinstance(node, PointNode):
        return {"kind": "POINT", "name": node.name}
    if isinstance(node, DigitalNode):
        return {"kind": "DIGITAL", "value": node.value}
    payload: dict[str, Any] = {
        "kind": "EXPRESS",
        "operator": node.operator,
        "children": [ast_to_json(child) for child in node.children],
    }
    if node.name is not None:
        payload["name"] = node.name
    return payload


def formula_ast_json(node: ExpressNode) -> str:
    return canonicalize_json_value(ast_to_json(node)).decode("utf-8")


def formula_digest_of(node: ExpressNode) -> DigestRef:
    payload = {"kind": _FORMULA_KIND, "ast": ast_to_json(node)}
    return raw_blob_digest(canonicalize_json_value(payload))
