"""Health and readiness probe routes."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gateway_repository_service.http.errors import simple_error_response
from gateway_repository_service.http.readiness import DefaultReadiness, ReadinessPort


def register_probe_routes(app: FastAPI) -> None:
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=None)
    def readyz(request: Request) -> JSONResponse:
        readiness = _readiness_from_state(request)
        if readiness.is_ready():
            return JSONResponse(content={"status": "ready"})

        message = readiness.not_ready_message()
        return simple_error_response(
            request,
            code="SERVICE_NOT_READY",
            message=message,
            status_code=503,
        )


def _readiness_from_state(request: Request) -> ReadinessPort:
    readiness: ReadinessPort | None = getattr(request.app.state, "readiness", None)
    if readiness is None:
        return DefaultReadiness()
    return readiness
