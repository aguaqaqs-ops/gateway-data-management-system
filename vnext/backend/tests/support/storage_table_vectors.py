"""Fixed S4 storage-table expectations, authored independently of the new renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


VECTOR_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures/vectors/mutation/storage-table/v1/cases.json"
)


def storage_table_vectors() -> dict[str, Any]:
    payload = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))
    if type(payload) is not dict or payload.get("case_schema_version") != 1:
        raise ValueError("storage-table vectors must be a v1 object")
    return payload
