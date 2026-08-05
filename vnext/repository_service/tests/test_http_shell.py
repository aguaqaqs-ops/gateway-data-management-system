"""HTTP shell tests for health, readiness, request ID, errors and OpenAPI."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from support.http_harness import assert_request_id_header, create_test_http_app


@dataclass(frozen=True, slots=True)
class _ReadyReadiness:
    def is_ready(self) -> bool:
        return True


def test_healthz_returns_200() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_request_id_header(response)


def test_readyz_default_returns_503() -> None:
    response = TestClient(create_app()).get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_NOT_READY"
    assert body["message"]
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_readyz_injected_ready_returns_200() -> None:
    response = TestClient(create_app(readiness=_ReadyReadiness())).get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert_request_id_header(response)


def test_request_id_on_success_and_error() -> None:
    client = TestClient(create_test_http_app())

    health = client.get("/healthz")
    ready = client.get("/readyz")
    validation = client.post("/_test/validate", json={})

    for response in (health, ready, validation):
        assert_request_id_header(response)


def test_validation_maps_to_simple_error() -> None:
    response = TestClient(create_test_http_app()).post("/_test/validate", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["message"]
    assert isinstance(body.get("details"), dict)
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_service_error_maps_to_simple_error() -> None:
    response = TestClient(create_test_http_app()).get("/_test/service-error")

    assert response.status_code == 418
    body = response.json()
    assert body["code"] == "TEST_SERVICE_ERROR"
    assert body["message"] == "deliberate service error"
    assert body["details"] == {"probe": True}
    request_id = assert_request_id_header(response)
    assert body["request_id"] == request_id


def test_openapi_only_health_routes() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths.keys()) == {"/healthz", "/readyz"}


def test_docs_and_redoc_disabled() -> None:
    client = TestClient(create_app())

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_production_app_has_no_forbidden_routes() -> None:
    response = TestClient(create_app()).get("/openapi.json")
    paths = response.json()["paths"]

    for path in paths:
        assert not path.startswith("/v1/")
        assert not path.startswith("/v2/")
        assert "/_test" not in path
