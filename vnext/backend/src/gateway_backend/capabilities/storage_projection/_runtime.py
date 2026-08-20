"""Cooperative cancel and deadline checkpoints for storage projection."""

from __future__ import annotations

import time

from gateway_backend.capabilities.storage_projection.contracts import (
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
    ProjectionInvocationContext,
)


def runtime_failure(context: ProjectionInvocationContext) -> ProjectionDiagnostic | None:
    if context.cancel_requested.is_set():
        return ProjectionDiagnostic(
            code=ProjectionDiagnosticCode.PROJECTION_CANCELLED,
            severity=ProjectionDiagnosticSeverity.ERROR,
            message="projection cancelled",
        )
    if context.deadline_monotonic is not None and time.monotonic() >= context.deadline_monotonic:
        return ProjectionDiagnostic(
            code=ProjectionDiagnosticCode.PROJECTION_TIMEOUT,
            severity=ProjectionDiagnosticSeverity.ERROR,
            message="projection deadline expired",
        )
    return None
