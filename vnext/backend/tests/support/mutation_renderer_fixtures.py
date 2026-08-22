"""Thin loader for mutation renderer golden fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_backend.capabilities.mutation_planning import (
    ChangeSetClosure,
    change_set_closure_from_document,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "mutation" / "renderer"


def load_closure_document(relative_dir: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_ROOT / relative_dir / "closure.json").read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("closure.json must be an object")
    return payload


def load_closure(relative_dir: str) -> ChangeSetClosure:
    return change_set_closure_from_document(load_closure_document(relative_dir))


def load_expected_sql(relative_dir: str) -> bytes:
    return (FIXTURE_ROOT / relative_dir / "expected.sql").read_bytes()
