"""HTTP contract tests for Review apply and read routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.application.submission.review import PERMISSION_REVIEW_SUBMISSION
from gateway_backend.http.dependencies import ClosableAdmissionGate
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.http_workspace_harness import (
    PendingReviewHttpSeed,
    TEST_BEARER,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
    seed_pending_review_submission,
)
from tests.support.workspace_fixtures import make_identity
from tests.test_submit_transactions import _upsert_provisioned_mapping_row

pytestmark = pytest.mark.unit

REVIEWER_BEARER = "reviewer-session-token"
OTHER_SCOPE_BEARER = "other-scope-session-token"
DENIED_REVIEWER_BEARER = "denied-reviewer-session-token"

REVIEW_HTTP_IDEMPOTENCY_KEY_CASES = (
    ("empty", "", 422),
    ("too_long", "a" * 256, 422),
    ("leading_space", " key", 422),
    ("trailing_space", "key ", 422),
    ("padded", " padded-key ", 422),
    ("control", "key\x1f", 422),
    ("valid_min", "!", 201),
)

REVIEW_MAPPING_DRIFT_CASES = (
    ("mapping_missing", "provisioned mapping is missing"),
    ("mapping_disabled", "provisioned mapping is disabled"),
)


def _review_permissions() -> frozenset[str]:
    return frozenset(
        {
            "workspace_read",
            "upload_submit_workspace",
            "preview_workspace",
            PERMISSION_REVIEW_SUBMISSION,
        }
    )


def _apply_body(
    *,
    expected_review_version: int = 0,
    action: str = "APPROVE",
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "expected_review_version": expected_review_version,
        "action": action,
        "reason": reason,
    }


def _review_env(
    tmp_path: Path,
    *,
    identity: Any | None = None,
    extra_sessions: dict[str, Any] | None = None,
    admission_gate: ClosableAdmissionGate | None = None,
) -> tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed]:
    environment = create_workspace_http_environment(
        tmp_path,
        identity=identity or make_identity(permissions=_review_permissions()),
        extra_sessions=extra_sessions,
        admission_gate=admission_gate,
    )
    seed = seed_pending_review_submission(environment.db_path)
    return environment, seed


def _post_review(
    env: WorkspaceHttpTestEnvironment,
    seed: PendingReviewHttpSeed,
    *,
    idempotency_key: str,
    body: dict[str, object] | None = None,
    bearer: str = TEST_BEARER,
) -> Any:
    return env.client.post(
        f"/v1/submissions/{seed.submission_id}/review-events",
        headers={"Authorization": f"Bearer {bearer}", "Idempotency-Key": idempotency_key},
        json=body or _apply_body(),
    )


def _get_review(env: WorkspaceHttpTestEnvironment, seed: PendingReviewHttpSeed, *, bearer: str = TEST_BEARER) -> Any:
    return env.client.get(
        f"/v1/submissions/{seed.submission_id}/review",
        headers={"Authorization": f"Bearer {bearer}"},
    )


@pytest.fixture
def review_env(tmp_path: Path) -> tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed]:
    return _review_env(tmp_path)


def test_apply_review_returns_201_and_get_returns_facts(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    response = _post_review(env, seed, idempotency_key="review-approve")
    assert response.status_code == 201
    body = response.json()
    assert body["submission_id"] == seed.submission_id
    assert body["status"] == "APPROVED"
    assert body["review_version"] == 1
    assert body["event"]["event_kind"] == "APPROVED"
    assert body["event"]["sequence"] == 1
    assert "repository_id" not in body
    assert str(env.db_path) not in response.text

    facts = _get_review(env, seed)
    assert facts.status_code == 200
    facts_body = facts.json()
    assert facts_body["status"] == "APPROVED"
    assert facts_body["review_version"] == 1
    assert len(facts_body["events"]) == 2
    assert facts_body["events"][0]["event_kind"] == "SUBMISSION_FINALIZED"
    assert facts_body["events"][1]["event_kind"] == "APPROVED"


def test_apply_review_replays_same_key_with_200(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    first = _post_review(env, seed, idempotency_key="review-replay")
    second = _post_review(env, seed, idempotency_key="review-replay")
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()


def test_apply_review_replay_without_permission_returns_403(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        extra_sessions={
            DENIED_REVIEWER_BEARER: make_identity(
                actor_id="reviewer-2",
                permissions=frozenset({"workspace_read", "preview_workspace"}),
            )
        },
    )
    first = _post_review(env, seed, idempotency_key="review-replay-forbidden")
    second = _post_review(
        env,
        seed,
        idempotency_key="review-replay-forbidden",
        bearer=DENIED_REVIEWER_BEARER,
    )
    assert first.status_code == 201
    assert second.status_code == 403
    assert second.json()["code"] == "SCOPE_FORBIDDEN"


def test_apply_review_replays_cross_actor_same_project_key(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        extra_sessions={
            REVIEWER_BEARER: make_identity(
                actor_id="reviewer-2",
                permissions=_review_permissions(),
            )
        },
    )
    first = _post_review(env, seed, idempotency_key="review-cross-actor")
    second = _post_review(
        env,
        seed,
        idempotency_key="review-cross-actor",
        bearer=REVIEWER_BEARER,
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["event"]["actor_id"] == "actor-1"
    assert second.json()["event"]["actor_id"] == "actor-1"


def test_apply_review_requires_idempotency_key(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    response = env.client.post(
        f"/v1/submissions/{seed.submission_id}/review-events",
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
        json=_apply_body(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


@pytest.mark.parametrize(
    ("case_id", "idempotency_key", "expected_status"),
    REVIEW_HTTP_IDEMPOTENCY_KEY_CASES,
    ids=[case[0] for case in REVIEW_HTTP_IDEMPOTENCY_KEY_CASES],
)
def test_apply_review_validates_idempotency_key_contract(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
    case_id: str,
    idempotency_key: str,
    expected_status: int,
) -> None:
    env, seed = review_env
    response = _post_review(env, seed, idempotency_key=idempotency_key)
    assert response.status_code == expected_status
    if expected_status == 422:
        assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_apply_review_does_not_normalize_padded_idempotency_key_into_replay(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    padded = _post_review(env, seed, idempotency_key=" padded-key ")
    assert padded.status_code == 422
    assert padded.json()["code"] == "REQUEST_VALIDATION_FAILED"
    fresh = _post_review(env, seed, idempotency_key="padded-key")
    assert fresh.status_code == 201
    replay = _post_review(env, seed, idempotency_key="padded-key")
    assert replay.status_code == 200
    assert fresh.json() == replay.json()


def test_apply_review_rejects_closed_schema_extra_field(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    response = _post_review(
        env,
        seed,
        idempotency_key="review-extra",
        body={**_apply_body(), "extra": True},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_apply_review_rejects_missing_reason_for_reject(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    response = _post_review(
        env,
        seed,
        idempotency_key="review-reject-missing-reason",
        body=_apply_body(action="REJECT"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_apply_review_requires_review_permission(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    response = _post_review(env, seed, idempotency_key="review-forbidden")
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_get_review_requires_review_permission(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    response = _get_review(env, seed)
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_get_review_without_permission_hides_existing_submission(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        extra_sessions={
            DENIED_REVIEWER_BEARER: make_identity(
                actor_id="reviewer-2",
                permissions=frozenset({"workspace_read", "preview_workspace"}),
            )
        },
    )
    approved = _post_review(env, seed, idempotency_key="review-get-forbidden")
    assert approved.status_code == 201
    response = _get_review(env, seed, bearer=DENIED_REVIEWER_BEARER)
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_apply_review_without_permission_hides_missing_submission(tmp_path: Path) -> None:
    env = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    response = env.client.post(
        "/v1/submissions/sub-missing/review-events",
        headers={"Authorization": f"Bearer {TEST_BEARER}", "Idempotency-Key": "review-missing"},
        json=_apply_body(),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_apply_review_returns_404_for_missing_submission(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, _seed = review_env
    response = env.client.post(
        "/v1/submissions/sub-missing/review-events",
        headers={"Authorization": f"Bearer {TEST_BEARER}", "Idempotency-Key": "review-404"},
        json=_apply_body(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_review_returns_404_for_missing_submission(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, _seed = review_env
    response = env.client.get(
        "/v1/submissions/sub-missing/review",
        headers={"Authorization": f"Bearer {TEST_BEARER}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_apply_review_hides_cross_scope_submission_same_database(tmp_path: Path) -> None:
    env = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=_review_permissions()),
        extra_sessions={
            OTHER_SCOPE_BEARER: make_identity(
                actor_id="actor-2",
                device_key="device-other",
                project_id="project-1",
                permissions=_review_permissions(),
            )
        },
    )
    seed = seed_pending_review_submission(env.db_path)
    _upsert_provisioned_mapping_row(
        env.db_path,
        device_key="device-other",
        project_id=seed.project_id,
        repository_id=seed.repository_id,
    )
    response = env.client.post(
        f"/v1/submissions/{seed.submission_id}/review-events",
        headers={
            "Authorization": f"Bearer {OTHER_SCOPE_BEARER}",
            "Idempotency-Key": "review-cross-scope",
        },
        json=_apply_body(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_review_hides_cross_scope_submission_same_database(tmp_path: Path) -> None:
    env, seed = _review_env(
        tmp_path,
        extra_sessions={
            OTHER_SCOPE_BEARER: make_identity(
                actor_id="actor-2",
                device_key="device-other",
                project_id="project-1",
                permissions=_review_permissions(),
            )
        },
    )
    _upsert_provisioned_mapping_row(
        env.db_path,
        device_key="device-other",
        project_id=seed.project_id,
        repository_id=seed.repository_id,
    )
    approved = _post_review(env, seed, idempotency_key="review-cross-scope-get")
    assert approved.status_code == 201
    response = _get_review(env, seed, bearer=OTHER_SCOPE_BEARER)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_apply_review_rejects_idempotency_conflict(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    first = _post_review(env, seed, idempotency_key="review-idem-conflict")
    assert first.status_code == 201
    conflict = _post_review(
        env,
        seed,
        idempotency_key="review-idem-conflict",
        body=_apply_body(action="REJECT", reason="changed"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_apply_review_rejects_version_conflict(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    response = _post_review(
        env,
        seed,
        idempotency_key="review-version-conflict",
        body=_apply_body(expected_review_version=9),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVIEW_VERSION_CONFLICT"


def test_apply_review_rejects_transition_conflict(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    approved = _post_review(env, seed, idempotency_key="review-approved")
    assert approved.status_code == 201
    response = _post_review(
        env,
        seed,
        idempotency_key="review-transition-conflict",
        body=_apply_body(expected_review_version=1, action="APPROVE"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVIEW_TRANSITION_CONFLICT"


def test_apply_review_rejects_workspace_occupancy_conflict(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(seed.workspace_id)
        assert workspace is not None
        updated = replace(
            workspace,
            current_upload_revision_id="ur-stale",
            optimistic_version=workspace.optimistic_version + 1,
        )
        unit_of_work.workspace.save_workspace(updated, expected_version=workspace.optimistic_version)
    response = _post_review(env, seed, idempotency_key="review-occupancy")
    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_OCCUPANCY_CONFLICT"


def test_apply_review_returns_429_when_admission_closed(tmp_path: Path) -> None:
    gate = ClosableAdmissionGate(limit=1)
    env, seed = _review_env(tmp_path, admission_gate=gate)
    gate.close()
    response = _post_review(env, seed, idempotency_key="review-admission")
    assert response.status_code == 429
    assert response.json()["code"] == "ADMISSION_LIMIT_REACHED"


def test_apply_review_returns_503_when_scope_provider_fails(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    env.scope_resolution.simulate_resolution_error = "provider unavailable"
    response = _post_review(env, seed, idempotency_key="review-provider-fail")
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize(
    ("case_id", "resolution_error"),
    REVIEW_MAPPING_DRIFT_CASES,
    ids=[case[0] for case in REVIEW_MAPPING_DRIFT_CASES],
)
def test_apply_review_hides_mapping_resolution_failures(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
    case_id: str,
    resolution_error: str,
) -> None:
    env, seed = review_env
    env.scope_resolution.simulate_resolution_error = resolution_error
    response = _post_review(env, seed, idempotency_key=f"review-mapping-{case_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_apply_review_hides_stale_mapping_drift(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    env.scope_resolution.repository_id = "repo-other"
    response = _post_review(env, seed, idempotency_key="review-mapping-drift")
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize(
    ("case_id", "resolution_error"),
    REVIEW_MAPPING_DRIFT_CASES,
    ids=[case[0] for case in REVIEW_MAPPING_DRIFT_CASES],
)
def test_get_review_hides_mapping_resolution_failures(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
    case_id: str,
    resolution_error: str,
) -> None:
    env, seed = review_env
    approved = _post_review(env, seed, idempotency_key=f"review-get-mapping-{case_id}")
    assert approved.status_code == 201
    env.scope_resolution.simulate_resolution_error = resolution_error
    response = _get_review(env, seed)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_review_hides_stale_mapping_drift(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    approved = _post_review(env, seed, idempotency_key="review-get-mapping-drift")
    assert approved.status_code == 201
    env.scope_resolution.repository_id = "repo-other"
    response = _get_review(env, seed)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_review_returns_503_on_integrity_failure(
    review_env: tuple[WorkspaceHttpTestEnvironment, PendingReviewHttpSeed],
) -> None:
    env, seed = review_env
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        unit_of_work.connection.execute(
            "UPDATE review_projection_records SET optimistic_version = 99 WHERE submission_id = ?",
            (seed.submission_id,),
        )
    response = _get_review(env, seed)
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"
