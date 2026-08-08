"""HTTP shell tests for health, readiness, request ID, errors and OpenAPI."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.http.readiness import ReadinessPort
from gateway_repository_service.settings import RepositoryServiceSettings
from support.http_harness import (
    PRODUCTION_OPENAPI_PATHS,
    assert_request_id_header,
    create_test_client,
    create_test_http_app,
)


@dataclass(frozen=True, slots=True)
class _ReadyReadiness:
    def is_ready(self) -> bool:
        return True

    def not_ready_message(self) -> str:
        return "service is not ready"


def _shell_app(
    *,
    settings: RepositoryServiceSettings | None = None,
    readiness: ReadinessPort | None = None,
) -> FastAPI:
    return create_app(settings, readiness=readiness, enable_lifecycle=False)


def test_healthz_returns_200() -> None:
    response = create_test_client(_shell_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_request_id_header(response)


def test_readyz_default_returns_503() -> None:
    response = create_test_client(_shell_app()).get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_NOT_READY"
    assert body["message"]
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_readyz_injected_ready_returns_200() -> None:
    response = create_test_client(_shell_app(readiness=_ReadyReadiness())).get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert_request_id_header(response)


def test_request_id_on_success_and_error() -> None:
    client = create_test_client(create_test_http_app())

    health = client.get("/healthz")
    ready = client.get("/readyz")
    validation = client.post("/_test/validate", json={})

    for response in (health, ready, validation):
        assert_request_id_header(response)


def test_validation_maps_to_simple_error() -> None:
    response = create_test_client(create_test_http_app()).post("/_test/validate", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["message"]
    assert isinstance(body.get("details"), dict)
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_service_error_maps_to_simple_error() -> None:
    response = create_test_client(create_test_http_app()).get("/_test/service-error")

    assert response.status_code == 418
    body = response.json()
    assert body["code"] == "TEST_SERVICE_ERROR"
    assert body["message"] == "deliberate service error"
    assert body["details"] == {"probe": True}
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_unhandled_exception_returns_internal_error() -> None:
    response = create_test_client(create_test_http_app()).get("/_test/unhandled-error")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message"] == "internal server error"
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id
    assert response.headers["content-type"].startswith("application/json")


def test_unhandled_exception_propagates_when_raise_server_exceptions_true() -> None:
    client = TestClient(create_test_http_app(), raise_server_exceptions=True)

    with pytest.raises(RuntimeError, match="probe"):
        client.get("/_test/unhandled-error")


def test_unhandled_exception_propagates_with_default_test_client() -> None:
    client = TestClient(create_test_http_app())

    with pytest.raises(RuntimeError, match="probe"):
        client.get("/_test/unhandled-error")


def test_custom_validator_failure_returns_422_not_500() -> None:
    response = create_test_client(create_test_http_app()).post(
        "/_test/custom-validator",
        json={"value": "anything"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    errors = body["details"]["errors"]
    assert len(errors) >= 1
    for item in errors:
        assert set(item.keys()) == {"loc", "type", "msg"}
        assert "ctx" not in item
        assert "input" not in item
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_invalid_json_returns_422_with_request_id() -> None:
    response = create_test_client(create_test_http_app()).post(
        "/_test/validate",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert_request_id_header(response)


def test_nested_validation_errors_are_sanitized() -> None:
    response = create_test_client(create_test_http_app()).post("/_test/nested-validate", json={})

    assert response.status_code == 422
    body = response.json()
    errors = body["details"]["errors"]
    assert any("nested" in error["loc"] for error in errors)
    for item in errors:
        assert set(item.keys()) == {"loc", "type", "msg"}
    assert_request_id_header(response)


def test_openapi_only_health_and_create_routes() -> None:
    response = create_test_client(_shell_app()).get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths.keys()) == PRODUCTION_OPENAPI_PATHS


def test_docs_and_redoc_disabled() -> None:
    client = create_test_client(_shell_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_production_app_has_no_forbidden_routes() -> None:
    response = create_test_client(_shell_app()).get("/openapi.json")
    paths = response.json()["paths"]

    for path in paths:
        if path.startswith("/v1/"):
            assert path in PRODUCTION_OPENAPI_PATHS
            continue
        assert not path.startswith("/v2/")
        assert "/_test" not in path
