"""Stable matrix suite identity (order-independent semantics)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from gateway_conformance.matrix.aggregate import MatrixCellOutcome, suite_summary_wire

_NON_SEMANTIC_RESULT_KEYS = frozenset({"run_id", "evidence_ref"})


def _strip_non_semantic_result(result: dict[str, Any]) -> dict[str, Any]:
    stripped = {key: value for key, value in result.items() if key not in _NON_SEMANTIC_RESULT_KEYS}
    return stripped


def matrix_semantic_fingerprint(cells: tuple[MatrixCellOutcome, ...]) -> str:
    """Deterministic digest over cell results excluding run_id and evidence_ref."""

    payload_cells: list[dict[str, Any]] = []
    for item in sorted(cells, key=lambda c: c.cell.execution_key_tuple()):
        payload_cells.append(
            {
                "profile": item.cell.profile,
                "provider_id": item.cell.provider_id,
                "result": _strip_non_semantic_result(dict(item.outcome.result)),
            }
        )
    summary = suite_summary_wire(cells)
    payload = {"cells": payload_cells, "summary": summary}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
