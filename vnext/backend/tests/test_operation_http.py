"""HTTP contract tests for GET /v1/operations/{operation_id}."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
from gateway_backend.http.dependencies import ReadOnlyOperationStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, connect_control_db
from gateway_backend.operations.store import StoreBusy
from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    TEST_BEARER_LIMITED,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
    seed_submit_ready_workspace,
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


@pytest.mark.serial
def test_operation_gets_remain_available_while_control_db_writer_holds_lock(
    env: WorkspaceHttpTestEnvironment,
) -> None:
    operation_id, submit_attempt_id = _accept_submit_operation(env)
    with ControlDbUnitOfWork(env.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        workspace_id = next(ref.value for ref in operation.business_refs if ref.kind == "workspace")
    writer = connect_control_db(env.db_path)
    writer.execute("BEGIN IMMEDIATE")
    lock_started = monotonic()
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            operation_response_future = executor.submit(
                env.client.get,
                f"/v1/operations/{operation_id}",
                headers=env.auth_headers(),
            )
            attempt_response_future = executor.submit(
                env.client.get,
                f"/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}",
                headers=env.auth_headers(),
            )
            submission_response_future = executor.submit(
                env.client.get,
                f"/v1/workspaces/{workspace_id}/submissions/sub-missing-under-write-lock",
                headers=env.auth_headers(),
            )
            operation_response = operation_response_future.result(timeout=2)
            attempt_response = attempt_response_future.result(timeout=2)
            submission_response = submission_response_future.result(timeout=2)
            assert writer.in_transaction
            assert monotonic() - lock_started < 5
            sleep(max(0.0, 5.1 - (monotonic() - lock_started)))
            assert writer.in_transaction
        assert operation_response.status_code == 200
        assert operation_response.json()["operation_id"] == operation_id
        assert attempt_response.status_code == 200
        assert submission_response.status_code == 404
    finally:
        if writer.in_transaction:
            writer.execute("ROLLBACK")
        writer.close()


def test_operation_get_maps_store_busy_to_503(
    env: WorkspaceHttpTestEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_store_busy(_self: ReadOnlyOperationStore, _operation_id: str) -> None:
        raise StoreBusy("synthetic busy")

    monkeypatch.setattr(ReadOnlyOperationStore, "get_operation", raise_store_busy)
    response = env.client.get("/v1/operations/op-busy", headers=env.auth_headers())

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


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


def test_get_operation_without_read_permission_hides_missing_id(tmp_path: Path) -> None:
    limited_identity = make_identity(
        permissions=frozenset({"upload_submit_workspace", "preview_workspace"}),
    )
    env = create_workspace_http_environment(
        tmp_path,
        extra_sessions={TEST_BEARER_LIMITED: limited_identity},
    )
    response = env.client.get(
        "/v1/operations/op-missing",
        headers={"Authorization": f"Bearer {TEST_BEARER_LIMITED}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


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


def test_get_submit_operation_returns_200(env: WorkspaceHttpTestEnvironment) -> None:
    seed = seed_submit_ready_workspace(env.db_path, env.artifact_store)
    workspace = seed["workspace"]
    response = env.client.post(
        f"/v1/workspaces/{workspace.workspace_id}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-op"),
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
    assert response.status_code == 202
    operation_id = response.json()["operation_id"]
    get_response = env.client.get(
        f"/v1/operations/{operation_id}",
        headers=env.auth_headers(),
    )
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["operation_id"] == operation_id
    assert body["job_kind"] == "backend-vnext/submit"
    assert body["status"] == "QUEUED"


def _accept_submit_operation(env: WorkspaceHttpTestEnvironment) -> tuple[str, str]:
    seed = seed_submit_ready_workspace(env.db_path, env.artifact_store)
    workspace = seed["workspace"]
    response = env.client.post(
        f"/v1/workspaces/{workspace.workspace_id}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-op-negative"),
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
    assert response.status_code == 202
    body = response.json()
    return body["operation_id"], body["submit_attempt_id"]


def test_get_submit_operation_hides_missing_submit_attempt_ref(env: WorkspaceHttpTestEnvironment) -> None:
    operation_id, _submit_attempt_id = _accept_submit_operation(env)
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        workspace_id = next(ref.value for ref in operation.business_refs if ref.kind == "workspace")
        business_refs_blob = canonicalize_json_value([{"kind": "workspace", "value": workspace_id}])
        unit_of_work.connection.execute(
            "UPDATE operation_records SET business_refs = ? WHERE operation_id = ?",
            (business_refs_blob, operation_id),
        )
    response = env.client.get(
        f"/v1/operations/{operation_id}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_submit_operation_hides_stale_mapping(env: WorkspaceHttpTestEnvironment) -> None:
    operation_id, _submit_attempt_id = _accept_submit_operation(env)
    env.scope_resolution.resolve_calls = 0
    env.scope_resolution.repository_id = "repo-other"
    response = env.client.get(
        f"/v1/operations/{operation_id}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert env.scope_resolution.resolve_calls >= 1


def test_get_history_compare_operation_returns_200(db_path: Path, tmp_path: Path) -> None:
    del db_path
    env = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY})),
    )
    from tests.support.history_compare_job_harness import seed_archived_baseline_node

    seed_archived_baseline_node(
        env.db_path,
        node_id="bn-op-b",
        commit_id="commit-b",
        created_at_us=2,
    )
    accepted = env.client.post(
        "/v1/history-compares",
        headers=env.auth_headers(idempotency_key="compare-op-http"),
        json={
            "nodes": [
                {"ref_kind": "baseline_node", "ref_id": BASELINE_HEAD.business_baseline_node_id},
                {"ref_kind": "baseline_node", "ref_id": "bn-op-b"},
            ]
        },
    )
    assert accepted.status_code == 202
    operation_id = accepted.json()["operation_id"]
    response = env.client.get(
        f"/v1/operations/{operation_id}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["operation_id"] == operation_id
    assert body["job_kind"] == "backend-vnext/history-compare"
    assert body["status"] == "QUEUED"


def test_get_submit_operation_hides_missing_attempt_record(env: WorkspaceHttpTestEnvironment) -> None:
    operation_id, submit_attempt_id = _accept_submit_operation(env)
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "DELETE FROM submit_idempotency_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        )
        unit_of_work.connection.execute(
            "DELETE FROM workspace_submit_occupancy_records WHERE active_submit_attempt_id = ?",
            (submit_attempt_id,),
        )
        unit_of_work.connection.execute(
            "DELETE FROM repository_submit_occupancy_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        )
        unit_of_work.connection.execute(
            "DELETE FROM submit_attempt_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        )
    response = env.client.get(
        f"/v1/operations/{operation_id}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
