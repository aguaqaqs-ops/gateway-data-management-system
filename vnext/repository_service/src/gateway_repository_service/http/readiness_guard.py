"""Require service readiness before accepting mutation traffic."""

from __future__ import annotations

from fastapi import Request

from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.http.readiness import DefaultReadiness, ReadinessPort


def require_service_ready(request: Request) -> None:
    readiness = _readiness_from_state(request)
    try:
        if readiness.is_ready():
            return
        message = readiness.not_ready_message()
    except Exception:
        message = "readiness check failed"
    raise ServiceError(
        code="SERVICE_NOT_READY",
        message=message,
        status_code=503,
    )


def _readiness_from_state(request: Request) -> ReadinessPort:
    readiness: ReadinessPort | None = getattr(request.app.state, "readiness", None)
    if readiness is None:
        return DefaultReadiness()
    return readiness
