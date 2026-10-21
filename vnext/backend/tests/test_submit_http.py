"""HTTP contract tests for submit attempts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.http.dependencies import ClosableAdmissionGate
from tests.support.http_workspace_harness import (
    BASELINE_HEAD,
    FailingMainResolvePort,
    RecordingMainResolvePort,
    WorkspaceHttpTestEnvironment,
    create_workspace_http_environment,
    seed_submit_ready_workspace,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit


def _submit_body(workspace: dict[str, Any]) -> dict[str, object]:
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


@pytest.fixture
def seeded_env(tmp_path: Path) -> tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    return environment, _seeded_workspace_dict(seed)


def test_accept_submit_returns_202_with_attempt_body(seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]) -> None:
    env, workspace = seeded_env
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-1"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "PREPARED"
    assert body["operation_id"].startswith("op-")
    assert body["submit_attempt_id"].startswith("sa-")
    assert body["workspace_id"] == workspace["workspace_id"]


def test_accept_submit_requires_idempotency_key(seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]) -> None:
    env, workspace = seeded_env
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(),
        json=_submit_body(workspace),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_submit_requires_registry(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path, include_submit_registry=False)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-registry"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_accept_submit_replays_same_attempt(seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]]) -> None:
    env, workspace = seeded_env
    url = f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts"
    headers = env.auth_headers(idempotency_key="submit-replay")
    body = _submit_body(workspace)
    first = env.client.post(url, headers=headers, json=body)
    second = env.client.post(url, headers=headers, json=body)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["submit_attempt_id"] == second.json()["submit_attempt_id"]


IDENTITY_CONFIRMATION_HTTP_FAILURES = (
    pytest.param(
        [
            {"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "ok"},
            {"action": "ACCEPT_UNVERIFIABLE_DETAILED_RESULT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "ok"},
            {"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "ok"},
        ],
        id="more-than-two-confirmations",
    ),
    pytest.param(
        [
            {"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "ok"},
            {"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "b" * 64, "reason": "ok"},
        ],
        id="duplicate-action",
    ),
    pytest.param(
        [{"action": "UNKNOWN", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "ok"}],
        id="unknown-action",
    ),
    pytest.param(
        [{"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:not-a-digest", "reason": "ok"}],
        id="malformed-digest",
    ),
    pytest.param(
        [{"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": ""}],
        id="empty-reason",
    ),
    pytest.param(
        [{"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "x" * 4097}],
        id="reason-over-byte-limit",
    ),
    pytest.param(
        [{"action": "ACCEPT_DATASET_REPLACEMENT", "assessment_set_digest": "sha256:" + "a" * 64, "reason": "bad\x00reason"}],
        id="forbidden-control-character",
    ),
)


@pytest.mark.parametrize("identity_confirmations", IDENTITY_CONFIRMATION_HTTP_FAILURES)
def test_accept_submit_rejects_invalid_identity_confirmation_input(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
    identity_confirmations: list[dict[str, str]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["identity_confirmations"] = identity_confirmations
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-invalid-identity-confirmation"),
        json=body,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_submit_identity_confirmation_reason_accepts_multiline_domain_text(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["identity_confirmations"] = [
        {
            "action": "ACCEPT_DATASET_REPLACEMENT",
            "assessment_set_digest": "sha256:" + "a" * 64,
            "reason": "first line\rsecond line\nthird\tline",
        }
    ]
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-multiline-identity-reason"),
        json=body,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PROJECT_IDENTITY_CONFIRMATION_MISMATCH"


def test_accept_submit_requires_submit_permission(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-forbidden"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_accept_submit_returns_404_when_preview_missing(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["preview_result_id"] = "pr-missing"
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-missing-preview"),
        json=body,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_accept_submit_returns_404_when_upload_revision_missing(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["upload_revision_id"] = "ur-missing"
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-missing-upload"),
        json=body,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


def test_accept_submit_rejects_idempotency_conflict(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    url = f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts"
    headers = env.auth_headers(idempotency_key="submit-idem-conflict")
    first = env.client.post(url, headers=headers, json=_submit_body(workspace))
    assert first.status_code == 202
    conflict_body = _submit_body(workspace)
    conflict_body["generation"] = workspace["generation"] + 99
    conflict = env.client.post(url, headers=headers, json=conflict_body)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_accept_submit_rejects_workspace_version_conflict(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["expected_workspace_version"] = workspace["optimistic_version"] + 99
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-ws-version"),
        json=body,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "WORKSPACE_VERSION_CONFLICT"


def test_accept_submit_rejects_preview_derived_stale(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row

    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        preview = unit_of_work.workspace.get_preview_result(workspace["preview_result_id"])
        assert preview is not None
        stale_preview = replace(
            preview,
            baseline_head_version=preview.baseline_head_version - 1,
            business_baseline_commit_id="commit-stale",
        )
        binding_blob = preview_result_to_row(stale_preview)[5]
        unit_of_work.connection.execute(
            "UPDATE preview_result_records SET binding = ? WHERE preview_result_id = ?",
            (binding_blob, stale_preview.preview_result_id),
        )
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-stale-preview"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PREVIEW_DERIVED_STALE"


def test_accept_submit_rejects_workspace_occupancy(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    url = f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts"
    first = env.client.post(
        url,
        headers=env.auth_headers(idempotency_key="submit-occupy-first"),
        json=_submit_body(workspace),
    )
    assert first.status_code == 202
    with ControlDbUnitOfWork(env.db_path) as unit_of_work:
        refreshed_workspace = unit_of_work.workspace.get_workspace(workspace["workspace_id"])
        assert refreshed_workspace is not None
        workspace = {
            **workspace,
            "optimistic_version": refreshed_workspace.optimistic_version,
        }
    second = env.client.post(
        url,
        headers=env.auth_headers(idempotency_key="submit-occupy-second"),
        json=_submit_body(workspace),
    )
    assert second.status_code == 409
    assert second.json()["code"] == "SUBMIT_OCCUPANCY_CONFLICT"


def test_accept_submit_rejects_unreadable_artifacts(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    upload = seed["upload_revision"]
    for binding in upload.source_artifacts.values():
        environment.artifact_store.drop(
            ArtifactRef(
                artifact_id=binding.artifact_id,
                media_type=binding.media_type,
                size_bytes=binding.size_bytes,
                raw_sha256=DigestRef(binding.raw_sha256),
            )
        )
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-artifact"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "ARTIFACT_UNAVAILABLE"


def test_accept_submit_rejects_unavailable_main_resolve(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path, main_resolve_port=FailingMainResolvePort())
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-main-resolve"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_UNAVAILABLE"


def test_accept_submit_without_permission_hides_missing_preview(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(
        tmp_path,
        identity=make_identity(permissions=frozenset({"workspace_read", "preview_workspace"})),
    )
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    body = _submit_body(workspace)
    body["preview_result_id"] = "pr-missing"
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-forbidden-missing"),
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "SCOPE_FORBIDDEN"


def test_accept_submit_rejects_empty_preview_result_id(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["preview_result_id"] = ""
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-empty-preview-id"),
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_submit_rejects_string_workspace_version(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    body = _submit_body(workspace)
    body["expected_workspace_version"] = "0"
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-string-version"),
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_accept_submit_prefers_artifact_unavailable_over_main_resolve(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path, main_resolve_port=FailingMainResolvePort())
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    upload = seed["upload_revision"]
    for binding in upload.source_artifacts.values():
        environment.artifact_store.drop(
            ArtifactRef(
                artifact_id=binding.artifact_id,
                media_type=binding.media_type,
                size_bytes=binding.size_bytes,
                raw_sha256=DigestRef(binding.raw_sha256),
            )
        )
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-artifact-before-main"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 503
    assert response.json()["code"] == "ARTIFACT_UNAVAILABLE"


def test_accept_submit_replays_without_current_closure_metadata(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    url = f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts"
    headers = env.auth_headers(idempotency_key="submit-replay-frozen")
    body = _submit_body(workspace)
    first = env.client.post(url, headers=headers, json=body)
    assert first.status_code == 202
    closure_ref = env.artifact_store._registered_refs["closure-1"]
    env.artifact_store.drop(closure_ref)
    second = env.client.post(url, headers=headers, json=body)
    assert second.status_code == 202
    assert second.json()["submit_attempt_id"] == first.json()["submit_attempt_id"]


def test_accept_submit_resolves_main_once(
    seeded_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any]],
) -> None:
    env, workspace = seeded_env
    assert isinstance(env.main_resolve, RecordingMainResolvePort)
    env.main_resolve.resolve_calls = 0
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-main-once"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 202
    assert env.main_resolve.resolve_calls == 1


def test_accept_submit_rejects_admission_limit(tmp_path: Path) -> None:
    gate = ClosableAdmissionGate(limit=1)
    assert gate.try_acquire()
    environment = create_workspace_http_environment(tmp_path, admission_gate=gate)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    response = environment.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=environment.auth_headers(idempotency_key="submit-admission"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 429
    assert response.json()["code"] == "ADMISSION_LIMIT_REACHED"
