"""History HTTP route tests."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from gateway_backend.application.history.contracts import PERMISSION_READ_PROJECT_HISTORY
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_review_transactions import _apply_command, _apply_review, _seed_pending_review_submission
from gateway_backend.domain.submission.review import ReviewAction

pytestmark = pytest.mark.unit

HISTORY_ZERO_WRITE_TABLES = (
    "submission_records",
    "review_projection_records",
    "review_event_records",
    "baseline_node_records",
    "baseline_head_records",
    "archive_disposition_records",
    "workspace_records",
    "provisioned_scope_mappings",
)

HISTORY_HTTP_QUERY_BOUNDARY_CASES = (
    ("limit_zero", {"limit": 0}, 422),
    ("limit_over_max", {"limit": 501}, 422),
    ("limit_non_int", {"limit": "x"}, 422),
    ("cursor_over_max", {"cursor": "a" * 1025}, 422),
)

HISTORY_HTTP_REF_ID_BOUNDARY_CASES = (
    ("ascii_255", "a" * 255),
    ("chinese_85", "中" * 85),
    ("four_byte_255", "😀" * 63 + "a" * 3),
)


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


def test_list_history_is_read_only(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-readonly"),
    )
    history_env = _history_env(db_path.parent / "history-readonly", db_path=db_path)
    before = _capture_business_table_state(db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    after = _capture_business_table_state(db_path)
    assert before == after


def _corrupt_baseline_created_at_us(db_path: Path, *, node_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE baseline_node_records SET created_at_us = ? WHERE node_id = ?",
            ("not-an-int", node_id),
        )
        connection.commit()


def test_list_history_returns_integrity_failure_for_corrupt_facts(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    _corrupt_baseline_created_at_us(
        db_path,
        node_id=BASELINE_HEAD.business_baseline_node_id,
    )
    history_env = _history_env(db_path.parent / "history-corrupt", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 503
    assert response.json()["code"] == "HISTORY_INTEGRITY_FAILURE"


def test_list_history_ignores_corrupt_submission_heavy_columns_on_page_path(
    db_path: Path,
    tmp_path: Path,
) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE submission_records SET source_artifact_refs = ? WHERE submission_id = ?",
            (b"not-json", review_seed.submission_id),
        )
        connection.commit()
    history_env = _history_env(db_path.parent / "history-heavy-column", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200


def test_list_history_rejects_disabled_mapping_without_stale_scope_reads(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-scope-http"),
    )
    from tests.test_submit_transactions import _upsert_provisioned_mapping_row

    _upsert_provisioned_mapping_row(db_path, baseline_head=None, enabled=False)
    history_env = _history_env(db_path.parent / "history-scope", db_path=db_path)
    stale_scope = history_env.scope_resolution
    assert stale_scope.resolve(history_env.identity).repository_id == "repo-1"
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_list_history_accepts_long_cjk_commit_id(db_path: Path, tmp_path: Path) -> None:
    del tmp_path
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key="approve-cjk-commit"),
    )
    cjk_commit = "中" * 200
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE submission_records SET repository_commit_id = ? WHERE submission_id = ?",
            (cjk_commit, review_seed.submission_id),
        )
    history_env = _history_env(db_path.parent / "history-cjk-commit", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    submission_node = next(item for item in response.json()["nodes"] if item["node_kind"] == "SUBMISSION")
    assert submission_node["commit_id"] == cjk_commit


@pytest.mark.parametrize(("case_id", "params", "expected_status"), HISTORY_HTTP_QUERY_BOUNDARY_CASES)
def test_list_history_rejects_out_of_bounds_query(
    db_path: Path,
    tmp_path: Path,
    case_id: str,
    params: dict[str, object],
    expected_status: int,
) -> None:
    del tmp_path
    _seed_pending_review_submission(db_path)
    history_env = _history_env(db_path.parent / "history-query-boundary", db_path=db_path)
    response = history_env.client.get(
        "/v1/history",
        headers=history_env.auth_headers(),
        params=params,
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


@pytest.mark.parametrize(("case_id", "ref_id"), HISTORY_HTTP_REF_ID_BOUNDARY_CASES)
def test_list_history_returns_nodes_with_bounded_ref_ids(
    db_path: Path,
    tmp_path: Path,
    case_id: str,
    ref_id: str,
) -> None:
    del tmp_path, case_id
    review_seed = _seed_pending_review_submission(db_path)
    _apply_review(
        review_seed,
        _apply_command(review_seed, action=ReviewAction.APPROVE, idempotency_key=f"approve-{len(ref_id)}"),
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, 'repo-1', 'device-1', 'project-1', 'commit-boundary',
                      'ARCHIVED_SUBMISSION', ?, ?, 999)
            """,
            (ref_id, BASELINE_HEAD.business_baseline_node_id, review_seed.submission_id),
        )
    history_env = _history_env(db_path.parent / f"history-ref-{len(ref_id.encode('utf-8'))}", db_path=db_path)
    response = history_env.client.get("/v1/history", headers=history_env.auth_headers())
    assert response.status_code == 200
    assert any(item["ref_id"] == ref_id for item in response.json()["nodes"])


def _capture_business_table_state(db_path: Path) -> dict[str, tuple[int, str]]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        connection = unit_of_work.connection
        return {table: _table_fingerprint(connection, table) for table in HISTORY_ZERO_WRITE_TABLES}


def _table_fingerprint(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    payload = tuple(tuple(row) for row in rows)
    digest = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
    return (count, digest)


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
