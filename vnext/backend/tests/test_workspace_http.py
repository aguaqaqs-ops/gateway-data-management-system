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
    assert body["active_submit_attempt_id"] is None
    assert body["active_submission_id"] is None


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


def _workspace_response(env: WorkspaceHttpTestEnvironment) -> dict[str, object]:
    response = env.client.post("/v1/workspaces", headers=env.auth_headers(), json={
        "gateway_device_external_key": "device-1", "business_project_id": "project-1",
    })
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


@pytest.mark.parametrize("action", ["APPROVE", "REJECT", "WITHDRAW", "ARCHIVE"])
def test_workspace_submission_pointer_follows_review_and_archive_lifecycle(tmp_path: Path, action: str) -> None:
    from gateway_backend.domain.submission.review import ReviewAction
    from tests.test_review_transactions import _seed_pending_review_submission, _apply_review, _apply_command
    from tests.support.archive_fixtures import archive_seed_from_review_seed, append_selection_confirmation, start_archive_for_seed
    env = create_workspace_http_environment(tmp_path)
    seed = _seed_pending_review_submission(env.db_path)
    pending = _workspace_response(env)
    assert pending["active_submit_attempt_id"] is None
    assert pending["active_submission_id"] == seed.submission_id
    review_action = ReviewAction.APPROVE if action == "ARCHIVE" else ReviewAction(action)
    _apply_review(seed, _apply_command(seed, action=review_action, reason="review reason"))
    reviewed = _workspace_response(env)
    if action in {"APPROVE", "ARCHIVE"}:
        assert reviewed["active_submission_id"] == seed.submission_id
        assert reviewed["optimistic_version"] == pending["optimistic_version"]
    else:
        assert reviewed["active_submission_id"] is None
        assert reviewed["active_submit_attempt_id"] is None
        assert reviewed["optimistic_version"] == pending["optimistic_version"] + 1
        assert reviewed["current_upload_revision_id"] is None
        assert reviewed["current_preview_result_id"] is None
    if action == "ARCHIVE":
        archive = archive_seed_from_review_seed(seed)
        sequence = append_selection_confirmation(archive)
        start_archive_for_seed(archive, confirmation_sequence=sequence)
        released = _workspace_response(env)
        assert released["active_submission_id"] is None
        assert released["active_submit_attempt_id"] is None
        assert released["optimistic_version"] == pending["optimistic_version"] + 1


def test_workspace_attempt_pointer_survives_operation_failure_until_confirmed_abort(tmp_path: Path) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.test_submit_transactions import seed_submit_ready_workspace, _seed_effect_pending_attempt
    env = create_workspace_http_environment(tmp_path)
    ready = seed_submit_ready_workspace(env.db_path)
    unoccupied = _workspace_response(env)
    assert unoccupied["active_submission_id"] is None
    assert unoccupied["active_submit_attempt_id"] is None
    attempt = _seed_effect_pending_attempt(env.db_path, ready)
    occupied = _workspace_response(env)
    assert occupied["active_submit_attempt_id"] == attempt.submit_attempt_id
    assert occupied["active_submission_id"] is None
    assert occupied["optimistic_version"] == unoccupied["optimistic_version"] + 1
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        unit_of_work.connection.execute("UPDATE operation_records SET status = 'FAILED', completed_at_us = updated_at_us WHERE operation_id = ?", (attempt.operation_id,))
    assert _workspace_response(env) == occupied


def test_workspace_projection_reads_occupancy_and_version_from_one_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.application.workspace.services import create_or_get_workspace
    from gateway_backend.domain.submission.review import ReviewAction
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from gateway_backend.infrastructure.control_db.sqlite_workspace import SQLiteWorkspaceRepository
    from tests.test_review_transactions import _seed_pending_review_submission, _apply_review, _apply_command
    env = create_workspace_http_environment(tmp_path)
    seed = _seed_pending_review_submission(env.db_path)
    before = _workspace_response(env)
    original = SQLiteWorkspaceRepository.find_open_by_scope
    def find_then_release(self: SQLiteWorkspaceRepository, scope: object) -> object:
        workspace = original(self, scope)  # type: ignore[arg-type]
        _apply_review(seed, _apply_command(seed, action=ReviewAction.WITHDRAW, idempotency_key="snapshot-release"))
        return workspace
    with monkeypatch.context() as patch:
        patch.setattr(SQLiteWorkspaceRepository, "find_open_by_scope", find_then_release)
        with ControlDbUnitOfWork(env.db_path, read_only=True) as transaction:
            result = create_or_get_workspace(context=make_identity(), scope_resolution=env.scope_resolution,
                                             transaction=transaction, created_at=transaction.transaction_now)
    assert result.occupancy is not None
    assert result.occupancy.active_submission_id == seed.submission_id
    assert result.workspace.optimistic_version == before["optimistic_version"]
    after = _workspace_response(env)
    assert after["active_submission_id"] is None
    assert after["optimistic_version"] == before["optimistic_version"] + 1
