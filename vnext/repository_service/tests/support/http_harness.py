"""Test-only ASGI harness for HTTP shell behavior that must not ship in production."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from gateway_repository_service.app import create_app
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.http.readiness import ReadinessPort
from gateway_repository_service.settings import RepositoryServiceSettings


class _ValidationProbeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_field: str


def create_test_http_app(
    settings: RepositoryServiceSettings | None = None,
    *,
    readiness: ReadinessPort | None = None,
) -> FastAPI:
    app = create_app(settings, readiness=readiness)

    @app.post("/_test/validate")
    def validation_probe(body: _ValidationProbeBody) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_test/service-error")
    def service_error_probe() -> dict[str, str]:
        raise ServiceError(
            code="TEST_SERVICE_ERROR",
            message="deliberate service error",
            status_code=418,
            details={"probe": True},
        )

    return app


def assert_request_id_header(response: Any) -> str:
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != ""
    return str(request_id)
