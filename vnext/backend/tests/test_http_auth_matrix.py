"""HTTP authorization boundary matrix tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.http_workspace_harness import (
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.upload_http_packages import upload_files
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_permission_matrix_for_mutations(env: WorkspaceHttpTestEnvironment, tmp_path: Path) -> None:
    read_only_root = tmp_path / "read-only"
    read_only_root.mkdir()
    read_only = create_workspace_http_environment(
        read_only_root,
        identity=make_identity(permissions=frozenset({"workspace_read"})),
    )
    create_response = read_only.client.post(
        "/v1/workspaces",
        headers=read_only.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert create_response.status_code == 201
    workspace = create_response.json()
    upload_response = read_only.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=read_only.auth_headers(idempotency_key="matrix-upload"),
        files=upload_files(include_initial=False, completeness="MODIFIED_ONLY"),
    )
    assert upload_response.status_code == 403
    assert upload_response.json()["code"] == "SCOPE_FORBIDDEN"


def test_session_identity_cannot_be_overridden_by_body(env: WorkspaceHttpTestEnvironment) -> None:
    response = env.client.post(
        "/v1/workspaces",
        headers=env.auth_headers(),
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
            "permissions": ["preview_workspace"],
        },
    )
    assert response.status_code == 422
