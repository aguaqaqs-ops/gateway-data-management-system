"""Shared path constants for schema tests."""

from __future__ import annotations

from pathlib import Path

_VNEXT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = _VNEXT_ROOT / "fixtures" / "schemas" / "shared-kernel" / "canonical-encoding" / "v1"

SCHEMA_FILES = (
    "definitions.schema.json",
    "vector-set.schema.json",
    "jcs-case.schema.json",
    "scalar-case.schema.json",
    "digest-case.schema.json",
    "invalid-case.schema.json",
)
