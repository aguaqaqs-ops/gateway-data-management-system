"""HTTP contract tests for upload revisions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gateway_backend.infrastructure.control_db.sqlite_workspace import SQLiteWorkspaceRepository
from tests.support.http_workspace_harness import (
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.upload_http_packages import (
    INITIAL_BYTES,
    INITIAL_DIGEST,
    MODIFIED_BYTES,
    MODIFIED_DIGEST,
    upload_files,
    upload_manifest,
)

pytestmark = pytest.mark.unit


def _create_workspace(client: TestClient, headers: dict[str, str]) -> Any:
    return client.post(
        "/v1/workspaces",
        headers=headers,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)


def test_accept_upload_returns_201(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-1"),
        files=upload_files(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["generation"] == 1
    assert set(body["source_artifacts"]) == {"INITIAL", "MODIFIED"}


def test_accept_upload_requires_idempotency_key(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(),
        files=upload_files(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_upload_replays_same_bytes_and_key(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    headers = env.auth_headers(idempotency_key="upload-replay")
    url = f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions"
    first = env.client.post(url, headers=headers, files=upload_files())
    second = env.client.post(url, headers=headers, files=upload_files())
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["upload_revision_id"] == second.json()["upload_revision_id"]


def test_accept_upload_conflicts_on_reused_key_with_different_body(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    headers = env.auth_headers(idempotency_key="upload-conflict")
    url = f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions"
    first = env.client.post(url, headers=headers, files=upload_files())
    second = env.client.post(
        url,
        headers=headers,
        files=upload_files(expected_version=1),
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_accept_upload_rejects_stale_workspace_version(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-stale"),
        files=upload_files(expected_version=99),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_VERSION_CONFLICT"


def test_accept_upload_rejects_missing_file_part(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    files = {
        "manifest": (
            "manifest",
            json.dumps(upload_manifest()).encode("utf-8"),
            "application/json",
        ),
        "modified": ("modified", MODIFIED_BYTES, "application/gzip"),
    }
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-missing"),
        files=files,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_upload_rejects_modified_only_with_initial(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    manifest = {
        "expected_workspace_version": 0,
        "input_completeness": "MODIFIED_ONLY",
        "artifacts": {
            "INITIAL": {
                "part_name": "initial",
                "media_type": "application/gzip",
                "size_bytes": len(INITIAL_BYTES),
                "raw_sha256": INITIAL_DIGEST,
            },
            "MODIFIED": {
                "part_name": "modified",
                "media_type": "application/gzip",
                "size_bytes": len(MODIFIED_BYTES),
                "raw_sha256": MODIFIED_DIGEST,
            },
        },
    }
    files = {
        "manifest": ("manifest", json.dumps(manifest).encode("utf-8"), "application/json"),
        "modified": ("modified", MODIFIED_BYTES, "application/gzip"),
    }
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-closure"),
        files=files,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_CLOSURE_INVALID"


def test_accept_upload_rejects_oversized_idempotency_key_without_workspace_pointer(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="k" * 256),
        files=upload_files(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    persisted = env.repository.get_workspace(workspace["workspace_id"])
    assert persisted is not None
    assert persisted.current_upload_revision_id is None


def test_accept_upload_rejects_non_archive_payload(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    junk = b"init!"
    manifest = upload_manifest(initial_bytes=junk, modified_bytes=junk)
    files = {
        "manifest": ("manifest", json.dumps(manifest).encode("utf-8"), "application/json"),
        "initial": ("initial", junk, "application/gzip"),
        "modified": ("modified", junk, "application/gzip"),
    }
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-media"),
        files=files,
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UPLOAD_MEDIA_UNSUPPORTED"
    persisted = env.repository.get_workspace(workspace["workspace_id"])
    assert persisted is not None
    assert persisted.current_upload_revision_id is None


def test_accept_upload_rejects_archive_missing_required_sql(env: WorkspaceHttpTestEnvironment) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()
    empty = pack_tar_gz({"readme.txt": b"no sql"})
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-missing-sql"),
        files=upload_files(initial_bytes=empty, modified_bytes=empty),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_CLOSURE_INVALID"


def test_failed_revision_insert_rolls_back_workspace_pointer(
    env: WorkspaceHttpTestEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _create_workspace(env.client, env.auth_headers()).json()

    def boom(self: SQLiteWorkspaceRepository, revision: object) -> None:
        del self, revision
        raise sqlite3.IntegrityError("forced revision insert failure")

    monkeypatch.setattr(SQLiteWorkspaceRepository, "save_upload_revision", boom)
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-rollback"),
        files=upload_files(),
    )
    assert response.status_code == 500
    persisted = env.repository.get_workspace(workspace["workspace_id"])
    assert persisted is not None
    assert persisted.current_upload_revision_id is None
    assert persisted.generation == 0


def test_accept_upload_supersedes_queued_preview_for_previous_generation(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from gateway_backend.operations import OperationStatus, StepStatus

    workspace = _create_workspace(env.client, env.auth_headers()).json()
    first_upload = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-before-preview"),
        files=upload_files(),
    ).json()
    preview = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-queued"),
        json={
            "expected_workspace_version": first_upload["optimistic_version"],
            "upload_revision_id": first_upload["upload_revision_id"],
            "generation": first_upload["generation"],
            "expected_baseline_node_id": "node-1",
            "expected_baseline_head_version": 3,
            "options": {},
        },
    )
    assert preview.status_code == 202
    operation_id = preview.json()["operation_id"]
    second = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-supersede"),
        files=upload_files(expected_version=first_upload["optimistic_version"]),
    )
    assert second.status_code == 201
    with ControlDbUnitOfWork(env.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        candidates, _next = unit_of_work.operations.list_claim_candidates(
            unit_of_work.operations.transaction_now
        )
    assert operation.status is OperationStatus.SUPERSEDED
    assert steps[0].status is StepStatus.CANCELLED
    assert all(candidate.operation_id != operation_id for candidate in candidates)


def test_accept_upload_sets_cancel_intent_on_running_preview(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from gateway_backend.operations.persistence import OperationLifecycleActions

    workspace = _create_workspace(env.client, env.auth_headers()).json()
    first_upload = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-before-running"),
        files=upload_files(),
    ).json()
    preview = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/preview-operations",
        headers=env.auth_headers(idempotency_key="preview-running"),
        json={
            "expected_workspace_version": first_upload["optimistic_version"],
            "upload_revision_id": first_upload["upload_revision_id"],
            "generation": first_upload["generation"],
            "expected_baseline_node_id": "node-1",
            "expected_baseline_head_version": 3,
            "options": {},
        },
    )
    assert preview.status_code == 202
    operation_id = preview.json()["operation_id"]
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        actions = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=unit_of_work.transaction_now,
        )
        claimed = actions.claim_one("worker-1", "lease-running-1")
        assert claimed is not None
        assert claimed[0].operation_id == operation_id
    second = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/upload-revisions",
        headers=env.auth_headers(idempotency_key="upload-cancel-running"),
        files=upload_files(expected_version=first_upload["optimistic_version"]),
    )
    assert second.status_code == 201
    with ControlDbUnitOfWork(env.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
    assert operation.status.value == "RUNNING"
    assert operation.cancel_requested is True
    assert steps[0].cancel_requested is True
    assert steps[0].status.value == "RUNNING"
