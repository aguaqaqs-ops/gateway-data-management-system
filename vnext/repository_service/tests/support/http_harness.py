"""Test-only ASGI harness for HTTP shell behavior that must not ship in production."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, field_validator

from gateway_repository_service.app import create_app
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.http.readiness import ReadinessPort
from gateway_repository_service.settings import RepositoryServiceSettings


class _ValidationProbeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_field: str


class _CustomValidatorBody(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def reject_value(cls, value: str) -> str:
        del cls
        raise ValueError("rejected")


class _NestedInnerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inner_field: str


class _NestedOuterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nested: _NestedInnerBody


def create_test_client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def create_test_http_app(
    settings: RepositoryServiceSettings | None = None,
    *,
    readiness: ReadinessPort | None = None,
) -> FastAPI:
    app = create_app(settings, readiness=readiness, enable_lifecycle=False)

    @app.post("/_test/validate")
    def validation_probe(body: _ValidationProbeBody) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_test/auth-required")
    def auth_required_probe(_token: Annotated[str, Depends(require_bearer_token)]) -> dict[str, str]:
        return {"status": "authorized"}

    @app.get("/_test/service-error")
    def service_error_probe() -> dict[str, str]:
        raise ServiceError(
            code="TEST_SERVICE_ERROR",
            message="deliberate service error",
            status_code=418,
            details={"probe": True},
        )

    @app.get("/_test/unhandled-error")
    def unhandled_error_probe() -> dict[str, str]:
        raise RuntimeError("probe")

    @app.post("/_test/custom-validator")
    def custom_validator_probe(body: _CustomValidatorBody) -> dict[str, str]:
        return {"status": "ok", "value": body.value}

    @app.post("/_test/nested-validate")
    def nested_validation_probe(body: _NestedOuterBody) -> dict[str, str]:
        return {"status": "ok", "inner": body.nested.inner_field}

    return app


def assert_request_id_header(response: Any) -> str:
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != ""
    return str(request_id)
