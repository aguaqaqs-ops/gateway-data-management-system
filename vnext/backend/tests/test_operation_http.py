"""HTTP contract tests for GET /v1/operations/{operation_id}."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    TEST_BEARER_LIMITED,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.upload_http_packages import upload_files
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit


def _seed_preview_operation(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    workspace = client.post(
        "/v1/workspaces",
        headers=headers,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    ).json()
    upload = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers={**headers, "Idempotency-Key": "upload-op"},
        files=upload_files(),
    ).json()
    preview = client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers={**headers, "Idempotency-Key": "preview-op"},
        json={
            "expected_workspace_version": upload["optimistic_version"],
            "upload_revision_id": upload["upload_revision_id"],
            "generation": upload["generation"],
            "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
            "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
            "options": {},
        },
    ).json()
    return workspace, preview


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_get_operation_returns_200(env: WorkspaceHttpTestEnvironment) -> None:
    _, preview = _seed_preview_operation(env.client, env.auth_headers())
    response = env.client.get(
        f"/v1/operations/{preview['operation_id']}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation_id"] == preview["operation_id"]
    assert body["status"] == "QUEUED"
    assert body["job_kind"] == "backend-vnext/preview"


def test_get_operation_requires_authentication(env: WorkspaceHttpTestEnvironment) -> None:
    _, preview = _seed_preview_operation(env.client, env.auth_headers())
    response = env.client.get(f"/v1/operations/{preview['operation_id']}")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_get_operation_hides_cross_scope_workspace(tmp_path: Path) -> None:
    owner_env = create_workspace_http_environment(tmp_path)
    _, preview = _seed_preview_operation(owner_env.client, owner_env.auth_headers())
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_env = create_workspace_http_environment(
        other_root,
        identity=make_identity(actor_id="actor-2", device_key="device-2", project_id="project-2"),
    )
    response = other_env.client.get(
        f"/v1/operations/{preview['operation_id']}",
        headers=other_env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_operation_requires_workspace_read_permission(tmp_path: Path) -> None:
    limited_identity = make_identity(
        permissions=frozenset({"upload_submit_workspace", "preview_workspace"}),
    )
    env = create_workspace_http_environment(
        tmp_path,
        extra_sessions={TEST_BEARER_LIMITED: limited_identity},
    )
    _, preview = _seed_preview_operation(env.client, env.auth_headers())
    response = env.client.get(
        f"/v1/operations/{preview['operation_id']}",
        headers={"Authorization": f"Bearer {TEST_BEARER_LIMITED}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"
