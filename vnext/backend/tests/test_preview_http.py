"""HTTP contract tests for preview operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.upload_http_packages import upload_files
from tests.support.workspace_fixtures import make_identity
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

pytestmark = pytest.mark.unit


def _seed_workspace_with_upload(
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
        headers={**headers, "Idempotency-Key": "upload-preview"},
        files=upload_files(),
    ).json()
    return workspace, upload


def _preview_body(workspace: dict[str, Any], upload: dict[str, Any]) -> dict[str, object]:
    return {
        "expected_workspace_version": upload["optimistic_version"],
        "upload_revision_id": upload["upload_revision_id"],
        "generation": upload["generation"],
        "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
        "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
        "options": {},
    }


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_start_preview_returns_202_with_operation_body(env: WorkspaceHttpTestEnvironment) -> None:
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-1"),
        json=_preview_body(workspace, upload),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["operation_id"].startswith("op-")
    assert body["workspace_id"] == workspace["workspace_id"]
    assert body["upload_revision_id"] == upload["upload_revision_id"]
    assert body["generation"] == upload["generation"]
    with ControlDbUnitOfWork(env.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(body["operation_id"])
    assert operation.job_payload is not None
    assert json.loads(operation.job_payload)["comparison_ruleset_digest"] == _runtime_comparison_ruleset_digest()


def test_start_preview_requires_registry(env: WorkspaceHttpTestEnvironment, tmp_path: Path) -> None:
    no_registry = create_workspace_http_environment(tmp_path, include_preview_registry=False)
    workspace, upload = _seed_workspace_with_upload(no_registry.client, no_registry.auth_headers())
    response = no_registry.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=no_registry.auth_headers(idempotency_key="preview-registry"),
        json=_preview_body(workspace, upload),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_start_preview_binding_conflict_on_stale_generation(env: WorkspaceHttpTestEnvironment) -> None:
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    body = _preview_body(workspace, upload)
    body["generation"] = 99
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-binding"),
        json=body,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_BINDING_CONFLICT"


def test_start_preview_requires_preview_permission(tmp_path: Path) -> None:
    env = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "upload_submit_workspace"})),
    )
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-forbidden"),
        json=_preview_body(workspace, upload),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_start_preview_replays_queued_operation_with_live_clock(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path, now=lambda: datetime.now(UTC))
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    url = f"/v1/workspaces/{workspace['workspace_id']}/preview-operations"
    headers = env.auth_headers(idempotency_key="preview-replay")
    body = _preview_body(workspace, upload)
    first = env.client.post(url, headers=headers, json=body)
    second = env.client.post(url, headers=headers, json=body)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["operation_id"] == second.json()["operation_id"]
    acceptance = env.repository.find_preview_idempotency(workspace["workspace_id"], "preview-replay")
    assert acceptance is not None
    assert acceptance.operation_id == first.json()["operation_id"]


def test_start_preview_rejects_unknown_options_keys(env: WorkspaceHttpTestEnvironment) -> None:
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    body = _preview_body(workspace, upload)
    body["options"] = {"unexpected": True}
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-options"),
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_start_preview_rejects_oversized_idempotency_key(env: WorkspaceHttpTestEnvironment) -> None:
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="k" * 256),
        json=_preview_body(workspace, upload),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_start_preview_rejects_unreadable_source_before_queueing(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    import sqlite3

    from gateway_shared_kernel import DigestRef

    from gateway_backend.artifacts.types import ArtifactRef

    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    revision = env.repository.get_upload_revision(upload["upload_revision_id"])
    assert revision is not None
    for binding in revision.source_artifacts.values():
        env.artifact_store.drop(
            ArtifactRef(
                artifact_id=binding.artifact_id,
                media_type=binding.media_type,
                size_bytes=binding.size_bytes,
                raw_sha256=DigestRef(binding.raw_sha256),
            )
        )
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-unreadable"),
        json=_preview_body(workspace, upload),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    connection = sqlite3.connect(env.db_path)
    try:
        operations = connection.execute("SELECT COUNT(*) FROM operation_records").fetchone()
        acceptances = connection.execute(
            "SELECT COUNT(*) FROM preview_idempotency_records"
        ).fetchone()
    finally:
        connection.close()
    assert operations is not None and operations[0] == 0
    assert acceptances is not None and acceptances[0] == 0


def test_start_preview_replays_after_new_upload_generation(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    workspace, upload = _seed_workspace_with_upload(env.client, env.auth_headers())
    url = f"/v1/workspaces/{workspace['workspace_id']}/preview-operations"
    headers = env.auth_headers(idempotency_key="preview-generation-replay")
    body = _preview_body(workspace, upload)
    first = env.client.post(url, headers=headers, json=body)
    assert first.status_code == 202
    second_upload = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-after-preview"),
        files=upload_files(expected_version=upload["optimistic_version"]),
    )
    assert second_upload.status_code == 201
    replay = env.client.post(url, headers=headers, json=body)
    assert replay.status_code == 202
    assert replay.json()["operation_id"] == first.json()["operation_id"]
    conflict = env.client.post(
        url,
        headers=headers,
        json=_preview_body(workspace, second_upload.json()),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
