"""HTTP tests for POST /v1/repositories."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.settings import RepositoryServiceSettings
from support.http_harness import (
    assert_request_id_header,
    create_create_route_test_app,
    create_test_client,
)
from support.lifecycle_harness import dolt_available, lifecycle_settings

ALLOWED_OPENAPI_PATHS = {
    "/healthz",
    "/readyz",
    "/v1/repositories",
    "/v1/repositories/{repository_id}/artifacts",
}


def _auth_headers(*, token: str = "test-bearer-token", idempotency_key: str = "create-key-1") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_create_repository_happy_path(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/repositories", headers=_auth_headers())

    assert response.status_code == 201
    body = response.json()
    assert body["default_ref"] == "main"
    assert body["initial_commit_id"]
    assert body["repository_id"]
    assert_request_id_header(response)
    assert body.get("request_id") is None


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_create_repository_accepts_empty_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/repositories", headers=_auth_headers(idempotency_key="empty-body"))

    assert response.status_code == 201


def test_create_repository_rejects_non_empty_json_body(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = create_test_client(create_create_route_test_app(settings))
    with patch.object(
        CreateRepositoryCommand,
        "execute",
        side_effect=AssertionError("create command must not run"),
    ):
        response = client.post(
            "/v1/repositories",
            headers=_auth_headers(idempotency_key="reject-body"),
            json={"ignored": "value"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["message"] == "request body must be empty"
    assert_request_id_header(response)


def test_create_repository_rejects_large_content_length_without_side_effects(
    tmp_path: Path,
) -> None:
    settings = lifecycle_settings(tmp_path)
    client = create_test_client(create_create_route_test_app(settings))
    with patch.object(
        CreateRepositoryCommand,
        "execute",
        side_effect=AssertionError("create command must not run"),
    ):
        response = client.post(
            "/v1/repositories",
            headers={
                **_auth_headers(idempotency_key="reject-large-content-length"),
                "Content-Length": "10000000",
            },
            content=b"",
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert_request_id_header(response)


def test_create_repository_rejects_chunked_body_on_first_chunk(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = create_test_client(create_create_route_test_app(settings))

    with patch.object(
        CreateRepositoryCommand,
        "execute",
        side_effect=AssertionError("create command must not run"),
    ):
        response = client.post(
            "/v1/repositories",
            headers=_auth_headers(idempotency_key="reject-chunked-body"),
            content=iter([b"part1", b"part2"]),
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert_request_id_header(response)


def test_create_repository_missing_idempotency_key_returns_422(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/repositories",
            headers={"Authorization": "Bearer test-bearer-token"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert_request_id_header(response)


def test_create_repository_invalid_idempotency_key_returns_422(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/repositories",
            headers=_auth_headers(idempotency_key=""),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_create_repository_missing_auth_returns_401(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/repositories",
            headers={"Idempotency-Key": "create-key-1"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_create_repository_not_ready_returns_503(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    client = create_test_client(create_app(settings, enable_lifecycle=False))
    response = client.post("/v1/repositories", headers=_auth_headers())

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_openapi_includes_create_route() -> None:
    settings = RepositoryServiceSettings(profile="test", bearer_token="test-token")
    client = create_test_client(create_app(settings, enable_lifecycle=False))
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths.keys()) == ALLOWED_OPENAPI_PATHS
    create = paths["/v1/repositories"]["post"]
    assert create["responses"]["201"]["content"]["application/json"]["schema"]["$ref"]
    assert "Idempotency-Key" in create["parameters"][0]["name"] or any(
        parameter.get("name") == "Idempotency-Key" for parameter in create.get("parameters", [])
    )
