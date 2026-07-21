"""Shared case-seed types for the candidate catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Bucket = Literal["jcs", "scalar", "digest", "invalid"]


@dataclass(frozen=True, slots=True)
class CaseSeed:
    """Logical case definition prior to expected-byte materialization."""

    case_id: str
    bucket: Bucket
    operation: str
    input: dict[str, Any]
    expected_error: str | None = None

    def to_envelope(self, expected: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {
            "case_schema_version": 1,
            "case_id": self.case_id,
            "operation": self.operation,
            "input": self.input,
        }
        if self.expected_error is not None:
            base["expected_error"] = {"code": self.expected_error}
            return base
        if expected is None:
            raise ValueError(f"valid case {self.case_id!r} requires expected")
        base["expected"] = expected
        return base
