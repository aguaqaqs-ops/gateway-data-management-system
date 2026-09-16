"""HTTP contract tests for submit attempt and submission reads."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from gateway_backend.domain.submission.models import (
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.http_workspace_harness import (
    TS1,
    WorkspaceHttpTestEnvironment,
    _PREVIEW_CANONICAL_DIGEST,
    create_workspace_http_environment,
    seed_submit_ready_workspace,
)
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit

_SHA_MANIFEST = "sha256:" + "f" * 64


def _submit_body(workspace: dict[str, Any]) -> dict[str, object]:
    from tests.support.http_workspace_harness import BASELINE_HEAD

    return {
        "expected_workspace_version": workspace["optimistic_version"],
        "upload_revision_id": workspace["upload_revision_id"],
        "preview_result_id": workspace["preview_result_id"],
        "generation": workspace["generation"],
        "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
        "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
        "options": {},
    }


def _seeded_workspace_dict(seed: dict[str, Any]) -> dict[str, Any]:
    workspace = seed["workspace"]
    upload = seed["upload_revision"]
    preview = seed["preview_result"]
    return {
        "workspace_id": workspace.workspace_id,
        "optimistic_version": workspace.optimistic_version,
        "upload_revision_id": upload.upload_revision_id,
        "preview_result_id": preview.preview_result_id,
        "generation": upload.generation,
    }


def _accept_submit(env: WorkspaceHttpTestEnvironment, workspace: dict[str, Any], *, key: str) -> dict[str, Any]:
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key=key),
        json=_submit_body(workspace),
    )
    assert response.status_code == 202
    return cast(dict[str, Any], response.json())


@pytest.fixture
def seeded_env(tmp_path: Path) -> tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    return environment, _seeded_workspace_dict(seed)


def test_get_submit_attempt_returns_redacted_attempt(seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]) -> None:
    env, workspace = seeded_env
    accepted = _accept_submit(env, workspace, key="submit-read")
    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["submit_attempt_id"] == accepted["submit_attempt_id"]
    assert body["state"] == "PREPARED"
    assert "repository_artifact_id" not in body
    assert str(env.db_path) not in response.text


def test_get_submit_attempt_hides_cross_scope(tmp_path: Path) -> None:
    owner_env = create_workspace_http_environment(tmp_path)
    owner_seed = seed_submit_ready_workspace(owner_env.db_path, owner_env.artifact_store)
    owner_workspace = _seeded_workspace_dict(owner_seed)
    accepted = _accept_submit(owner_env, owner_workspace, key="submit-owner")
    other_root = tmp_path / "other"
    other_root.mkdir()
    other_env = create_workspace_http_environment(
        other_root,
        identity=make_identity(actor_id="actor-2", device_key="device-2", project_id="project-2"),
    )
    response = other_env.client.get(
        f"/v1/workspaces/{owner_workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}",
        headers=other_env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_get_submit_attempt_requires_workspace_read(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"upload_submit_workspace"})),
    )
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    accepted = _accept_submit(environment, workspace, key="submit-read-forbidden")
    response = environment.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}",
        headers=environment.auth_headers(),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_get_submit_attempt_hides_stale_mapping(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    accepted = _accept_submit(env, workspace, key="submit-mapping-stale")
    env.scope_resolution.resolve_calls = 0
    env.scope_resolution.repository_id = "repo-other"
    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts/{accepted['submit_attempt_id']}",
        headers=env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert env.scope_resolution.resolve_calls >= 1


def test_get_submission_returns_redacted_submission(seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]) -> None:
    env, workspace = seeded_env
    accepted = _accept_submit(env, workspace, key="submit-submission-read")
    from gateway_backend.domain.submission.models import Submission

    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted["submit_attempt_id"])
        assert attempt is not None
        finalized_attempt = replace(
            attempt,
            state=SubmitAttemptState.FINALIZED,
            submission_id="sub-1",
            finalized_at=TS1,
        )
        unit_of_work.submission.cas_update_attempt(
            finalized_attempt,
            expected_version=attempt.optimistic_version,
        )
        submission = Submission(
            submission_id="sub-1",
            submit_attempt_id=attempt.submit_attempt_id,
            workspace_id=attempt.workspace_id,
            workspace_generation=attempt.workspace_generation,
            upload_revision_id=attempt.upload_revision_id,
            preview_result_id=attempt.preview_result_id,
            repository_id=attempt.repository_id,
            based_on_baseline_node_id=attempt.business_baseline_node_id,
            business_baseline_commit_id=attempt.business_baseline_commit_id,
            repository_commit_id="commit-final",
            canonical_business_digest=attempt.canonical_business_digest,
            source_artifact_refs=attempt.source_artifact_refs,
            canonicalization_manifest_ref="manifest-1",
            canonicalization_manifest_digest=_SHA_MANIFEST,
            repository_import_artifact_raw_sha256="sha256:" + "e" * 64,
            repository_artifact_id="repo-artifact-1",
            requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
            completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
            requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
            target_ref=SubmitTargetRef.MAIN,
            created_by=attempt.created_by,
            created_at=TS1,
        )
        unit_of_work.submission.insert_submission(submission)

    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/submissions/sub-1",
        headers=env.auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["submission_id"] == "sub-1"
    assert body["canonical_business_digest"] == _PREVIEW_CANONICAL_DIGEST
    assert "repository_artifact_id" not in body
    assert "repository_import_artifact_raw_sha256" not in body


def test_get_submission_hides_stale_mapping(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    accepted = _accept_submit(env, workspace, key="submission-mapping-stale")
    from gateway_backend.domain.submission.models import Submission, SubmitTargetRef, SubmitUnknownTypePolicy, SubmitVerificationPolicy

    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted["submit_attempt_id"])
        assert attempt is not None
        finalized_attempt = replace(
            attempt,
            state=SubmitAttemptState.FINALIZED,
            submission_id="sub-mapping",
            finalized_at=TS1,
        )
        unit_of_work.submission.cas_update_attempt(
            finalized_attempt,
            expected_version=attempt.optimistic_version,
        )
        submission = Submission(
            submission_id="sub-mapping",
            submit_attempt_id=attempt.submit_attempt_id,
            workspace_id=attempt.workspace_id,
            workspace_generation=attempt.workspace_generation,
            upload_revision_id=attempt.upload_revision_id,
            preview_result_id=attempt.preview_result_id,
            repository_id=attempt.repository_id,
            based_on_baseline_node_id=attempt.business_baseline_node_id,
            business_baseline_commit_id=attempt.business_baseline_commit_id,
            repository_commit_id="commit-final",
            canonical_business_digest=attempt.canonical_business_digest,
            source_artifact_refs=attempt.source_artifact_refs,
            canonicalization_manifest_ref="manifest-1",
            canonicalization_manifest_digest=_SHA_MANIFEST,
            repository_import_artifact_raw_sha256="sha256:" + "e" * 64,
            repository_artifact_id="repo-artifact-1",
            requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
            completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
            requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
            target_ref=SubmitTargetRef.MAIN,
            created_by=attempt.created_by,
            created_at=TS1,
        )
        unit_of_work.submission.insert_submission(submission)

    env.scope_resolution.resolve_calls = 0
    env.scope_resolution.repository_id = "repo-other"
    response = env.client.get(
        f"/v1/workspaces/{workspace['workspace_id']}/submissions/sub-mapping",
        headers=env.auth_headers(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert env.scope_resolution.resolve_calls >= 1
