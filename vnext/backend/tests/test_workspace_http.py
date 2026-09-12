"""HTTP contract tests for POST /v1/workspaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.http_workspace_harness import (
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_create_workspace_returns_201(env: WorkspaceHttpTestEnvironment) -> None:
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "OPEN"
    assert body["generation"] == 0
    assert body["optimistic_version"] == 0


def test_create_workspace_replay_returns_200(env: WorkspaceHttpTestEnvironment) -> None:
    headers = env.auth_headers()
    payload = {
        "gateway_device_external_key": "device-1",
        "business_project_id": "project-1",
    }
    first = env.client.post("/v1/workspaces", headers=headers, json=payload)
    second = env.client.post("/v1/workspaces", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["workspace_id"] == second.json()["workspace_id"]


def test_create_workspace_rejects_idempotency_key(env: WorkspaceHttpTestEnvironment) -> None:
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(idempotency_key="ws-key"),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_create_workspace_requires_permission(tmp_path: Path) -> None:
    env = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"upload_submit_workspace"})),
    )
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_create_workspace_rejects_unknown_fields(env: WorkspaceHttpTestEnvironment) -> None:
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
            "actor_id": "evil",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_create_workspace_requires_authentication(env: WorkspaceHttpTestEnvironment) -> None:
    response = env.client.post(
        "/v1/workspaces",
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_create_workspace_rejects_body_scope_that_does_not_match_session(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "other-device",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_create_workspace_rejects_admission_when_closed(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path, admission_open=False)
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert response.status_code == 429
    assert response.json()["code"] == "ADMISSION_LIMIT_REACHED"
