"""HTTP authorization boundary matrix tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
    seed_submit_ready_workspace,
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


def test_submit_permission_matrix(env: WorkspaceHttpTestEnvironment, tmp_path: Path) -> None:
    read_only_root = tmp_path / "submit-read-only"
    read_only_root.mkdir()
    read_only = create_workspace_http_environment(
        read_only_root,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    seed = seed_submit_ready_workspace(read_only.db_path, read_only.artifact_store)
    workspace = seed["workspace"]
    response = read_only.client.post(
        f"/v1/workspaces/{workspace.workspace_id}/submit-attempts",
        headers=read_only.auth_headers(idempotency_key="matrix-submit"),
        json={
            "expected_workspace_version": workspace.optimistic_version,
            "upload_revision_id": seed["upload_revision"].upload_revision_id,
            "preview_result_id": seed["preview_result"].preview_result_id,
            "generation": seed["upload_revision"].generation,
            "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
            "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
            "options": {},
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_archive_permission_matrix(env: WorkspaceHttpTestEnvironment, tmp_path: Path) -> None:
    from tests.support.archive_fixtures import seed_approved_archive_candidate

    read_only_root = tmp_path / "archive-read-only"
    read_only_root.mkdir()
    read_only = create_workspace_http_environment(
        read_only_root,
        identity=make_identity(permissions=frozenset({"workspace_read", "review_submission"})),
    )
    seed = seed_approved_archive_candidate(read_only.db_path)
    response = read_only.client.post(
        "/v1/archive-confirmations",
        headers=read_only.auth_headers(idempotency_key="matrix-archive"),
        json={
            "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
            "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
            "selected": {
                "submission_id": seed.selected_ref.submission_id,
                "expected_candidate_digest": seed.selected_ref.expected_candidate_digest,
            },
            "candidate_set_digest": seed.candidate_set_digest,
            "subject_digest": seed.selection_subject_digest,
            "expected_sequence": 0,
            "action": "CONFIRM",
            "reason": "confirm archive selection",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"
