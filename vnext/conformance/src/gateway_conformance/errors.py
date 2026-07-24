"""Conformance validation errors with sanitized messages."""

from __future__ import annotations


class ConformanceValidationError(ValueError):
    """Fixture/schema validation failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
