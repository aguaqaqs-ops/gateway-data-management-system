"""Thin loader for the Shared Kernel's ordinary canonical case corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CORPUS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "vectors"
    / "shared-kernel"
    / "canonical-encoding"
    / "v1"
)
CASE_FILES = ("digest.jsonl", "invalid.jsonl", "jcs.jsonl", "scalar.jsonl")
EXPECTED_CASE_COUNT = 128


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def load_canonical_cases() -> list[dict[str, Any]]:
    """Load every ordinary case directly from the tracked JSONL files."""

    cases: list[dict[str, Any]] = []
    for file_name in CASE_FILES:
        path = CORPUS_ROOT / file_name
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                raise ValueError(f"{path}:{line_number}: empty case line")
            case = json.loads(line, parse_constant=_reject_json_constant)
            if not isinstance(case, dict):
                raise ValueError(f"{path}:{line_number}: case must be an object")
            if not isinstance(case.get("case_id"), str):
                raise ValueError(f"{path}:{line_number}: case_id must be a string")
            cases.append(case)

    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("canonical corpus contains duplicate case_id")
    if len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError(
            f"canonical corpus contains {len(cases)} cases, expected {EXPECTED_CASE_COUNT}"
        )
    return cases
