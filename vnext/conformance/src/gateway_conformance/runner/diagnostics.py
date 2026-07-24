"""Diagnostic sanitization for runner outputs."""

from __future__ import annotations

from gateway_conformance.runner.types import Diagnostic
from gateway_conformance.sanitize import sanitize_message


def sanitize_diagnostic(diagnostic: Diagnostic) -> Diagnostic:
    return Diagnostic(
        code=diagnostic.code,
        message=sanitize_message(diagnostic.message)[:500],
    )
