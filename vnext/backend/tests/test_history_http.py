"""History HTTP route tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
from tests.support.http_workspace_harness import WorkspaceHttpTestEnvironment, create_workspace_http_environment
from tests.support.workspace_fixtures import make_identity
from tests.test_review_transactions import _apply_command, _apply_review, _seed_pending_review_submission
from gateway_backend.domain.submission.review import ReviewAction

pytestmark = pytest.mark.unit


def test_list_history_requires_authentication(env: object, tmp_path: Path) -> None:
    del env
    history_env = _history_env(tmp_path / "history-auth")
    response = history_env.client.get("/v1/history")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_list_history_requires_read_project_history_permission(tmp_path: Path) -> None:
    history_env = _history_env(
        tmp_path / "history-forbidden",
        permissions=frozenset({"workspace_read"}),
    )
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_list_history_returns_projection_shape(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(review_seed, _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-history"))
    history_env = _history_env(db_path.parent / "history-http", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"head", "nodes", "next_cursor"}
    assert set(body["head"]) == {"node_id", "commit_id", "version"}
    assert len(body["nodes"]) >= 2
    node = next(item for item in body["nodes"] if item["node_kind"] == "SUBMISSION")
    assert node["review_status"] == "APPROVED"
    assert node["parent"]["ref_kind"] == "baseline_node"


def test_list_history_rejects_invalid_cursor(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    history_env = _history_env(db_path.parent / "history-cursor", db_path=db_path)
    response = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"cursor": "not-valid"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_list_history_supports_cursor_pagination(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-page"),
    )
    history_env = _history_env(db_path.parent / "history-page", db_path=db_path)
    first = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"limit": 1},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["nodes"]) == 1
    assert first_body["next_cursor"] is not None
    second = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params={"limit": 1, "cursor": first_body["next_cursor"]},
    )
    assert second.status_code == 200
    assert second.json()["nodes"][0]["ref_id"] != first_body["nodes"][0]["ref_id"]


def _history_env(
    root: Path,
    *,
    db_path: Path | None = None,
    permissions: frozenset[str] | None = None,
) -> WorkspaceHttpTestEnvironment:
    root.mkdir(parents=True, exist_ok=True)
    resolved_db = db_path or (root / "control.sqlite3")
    if db_path is None:
        from gateway_backend.infrastructure.control_db.database import initialize_control_db
        from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
        from tests.support.http_workspace_harness import BASELINE_HEAD

        initialize_control_db(resolved_db)
        seed_provisioned_mapping_with_head(resolved_db, baseline_head=BASELINE_HEAD)
    identity = make_identity(
        permissions=permissions
        or frozenset({"workspace_read", PERMISSION_READ_PROJECT_HISTORY}),
    )
    return create_workspace_http_environment(root, identity=identity, db_path=resolved_db)


@pytest.fixture
def env(tmp_path: Path) -> WorkspaceHttpTestEnvironment:
    return create_workspace_http_environment(tmp_path)
