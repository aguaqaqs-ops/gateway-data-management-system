"""HTTP contract tests for internal operator recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.http_workspace_harness import (
    TEST_INTERNAL_BEARER,
    WorkspaceHttpTestEnvironment,
    advance_submit_to_external_step,
    create_workspace_http_environment,
    promote_submit_recovery_target,
    promote_submit_terminal_failed,
    seed_submit_ready_workspace,
)
from tests.test_operation_http import _seed_preview_operation

pytestmark = pytest.mark.unit


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


def _accept_submit(env: WorkspaceHttpTestEnvironment, workspace: dict[str, Any]) -> dict[str, Any]:
    response = env.client.post(
        f"/v1/workspaces/{workspace['workspace_id']}/submit-attempts",
        headers=env.auth_headers(idempotency_key="submit-recovery"),
        json=_submit_body(workspace),
    )
    assert response.status_code == 202
    return cast(dict[str, Any], response.json())


@pytest.fixture
def recovery_env(tmp_path: Path) -> tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]]:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    accepted = _accept_submit(environment, workspace)
    step_id = f"{accepted['operation_id']}-step-1"
    promote_submit_recovery_target(
        environment.db_path,
        operation_id=accepted["operation_id"],
        step_id=step_id,
    )
    return environment, accepted, {"step_id": step_id}


def _recovery_body(
    env: WorkspaceHttpTestEnvironment,
    accepted: dict[str, Any],
    step: dict[str, Any],
    *,
    command: str,
    operation_version: int | None = None,
    step_version: int | None = None,
) -> dict[str, object]:
    if operation_version is None or step_version is None:
        with ControlDbUnitOfWork(env.db_path) as unit_of_work:
            operation = unit_of_work.operations.get_operation(accepted["operation_id"])
            step_record = unit_of_work.operations.get_step(step["step_id"])
        resolved_operation_version = (
            operation_version if operation_version is not None else operation.optimistic_version
        )
        resolved_step_version = (
            step_version if step_version is not None else step_record.optimistic_version
        )
    else:
        resolved_operation_version = operation_version
        resolved_step_version = step_version
    return {
        "operation_id": accepted["operation_id"],
        "step_id": step["step_id"],
        "command": command,
        "expected_operation_optimistic_version": resolved_operation_version,
        "expected_step_optimistic_version": resolved_step_version,
        "reason": "operator recovery test",
    }


def test_operator_recovery_requires_internal_bearer(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        json=_recovery_body(env, accepted, step, command="RETRY_FROM_CHECKPOINT"),
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_operator_recovery_rejects_path_body_mismatch(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    body = _recovery_body(env, accepted, step, command="RETRY_FROM_CHECKPOINT")
    body["operation_id"] = "op-mismatch"
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=body,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RECOVERY_IDENTITY_CONFLICT"


def test_operator_recovery_applies_prepare_retry(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=_recovery_body(env, accepted, step, command="RETRY_FROM_CHECKPOINT"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["command"] == "RETRY_FROM_CHECKPOINT"
    assert body["disposition"] == "APPLY"
    assert TEST_INTERNAL_BEARER not in response.text


def test_operator_recovery_rejects_resume_on_prepare_step(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=_recovery_body(env, accepted, step, command="RESUME_RECONCILE"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RECOVERY_CAPABILITY_CONFLICT"


def test_operator_recovery_rejects_stale_operation_version(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=_recovery_body(
            env,
            accepted,
            step,
            command="RETRY_FROM_CHECKPOINT",
            operation_version=99,
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "OPERATION_VERSION_CONFLICT"


def test_operator_recovery_rejects_abort_without_proof(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=_recovery_body(env, accepted, step, command="ABORT_CONFIRMED_FAILURE"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ABORT_PROOF_NOT_SATISFIED"


def test_operator_recovery_rejects_non_manual_recovery_state(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    accepted = _accept_submit(environment, workspace)
    step_id = f"{accepted['operation_id']}-step-1"
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json=_recovery_body(
            environment,
            accepted,
            {"step_id": step_id},
            command="RETRY_FROM_CHECKPOINT",
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RECOVERY_STATE_CONFLICT"


def test_operator_recovery_rejects_stale_step_version(
    recovery_env: tuple[WorkspaceHttpTestEnvironment, dict[str, Any], dict[str, Any]],
) -> None:
    env, accepted, step = recovery_env
    response = env.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step['step_id']}/recovery",
        headers=env.internal_auth_headers(),
        json=_recovery_body(
            env,
            accepted,
            step,
            command="RETRY_FROM_CHECKPOINT",
            step_version=99,
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STEP_VERSION_CONFLICT"


def test_operator_recovery_returns_not_found_for_missing_operation(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    response = environment.client.post(
        "/internal/v1/operations/op-missing/steps/step-missing/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": "op-missing",
            "step_id": "step-missing",
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 0,
            "expected_step_optimistic_version": 0,
            "reason": "operator recovery test",
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RECOVERY_TARGET_NOT_FOUND"


def test_operator_recovery_returns_not_found_for_missing_step(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    accepted = _accept_submit(environment, _seeded_workspace_dict(seed))
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/step-missing/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": accepted["operation_id"],
            "step_id": "step-missing",
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 0,
            "expected_step_optimistic_version": 0,
            "reason": "operator recovery test",
        },
    )
    assert response.status_code == 404
    assert response.json()["code"] == "RECOVERY_TARGET_NOT_FOUND"


def test_operator_recovery_rejects_preview_operation(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    _, preview = _seed_preview_operation(environment.client, environment.auth_headers())
    step_id = f"{preview['operation_id']}-step-1"
    response = environment.client.post(
        f"/internal/v1/operations/{preview['operation_id']}/steps/{step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": preview["operation_id"],
            "step_id": step_id,
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 0,
            "expected_step_optimistic_version": 0,
            "reason": "operator recovery test",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RECOVERY_IDENTITY_CONFLICT"


def test_operator_recovery_replays_abort_on_terminal_failure(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    accepted = _accept_submit(environment, _seeded_workspace_dict(seed))
    step_id = f"{accepted['operation_id']}-step-1"
    promote_submit_terminal_failed(
        environment.db_path,
        operation_id=accepted["operation_id"],
        step_id=step_id,
    )
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json=_recovery_body(
            environment,
            accepted,
            {"step_id": step_id},
            command="ABORT_CONFIRMED_FAILURE",
        ),
    )
    assert response.status_code == 200
    assert response.json()["disposition"] == "IDEMPOTENT"


def test_operator_recovery_rejects_ijson_version_overflow(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    accepted = _accept_submit(environment, _seeded_workspace_dict(seed))
    step_id = f"{accepted['operation_id']}-step-1"
    promote_submit_recovery_target(
        environment.db_path,
        operation_id=accepted["operation_id"],
        step_id=step_id,
    )
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": accepted["operation_id"],
            "step_id": step_id,
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 2**53,
            "expected_step_optimistic_version": 0,
            "reason": "operator recovery test",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_operator_recovery_rejects_reason_utf8_budget_overflow(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    accepted = _accept_submit(environment, _seeded_workspace_dict(seed))
    step_id = f"{accepted['operation_id']}-step-1"
    promote_submit_recovery_target(
        environment.db_path,
        operation_id=accepted["operation_id"],
        step_id=step_id,
    )
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": accepted["operation_id"],
            "step_id": step_id,
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 0,
            "expected_step_optimistic_version": 0,
            "reason": "é" * 4096,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_operator_recovery_returns_service_not_ready_without_submit_registry(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path, include_submit_registry=False)
    response = environment.client.post(
        "/internal/v1/operations/op-missing/steps/step-missing/recovery",
        headers=environment.internal_auth_headers(),
        json={
            "operation_id": "op-missing",
            "step_id": "step-missing",
            "command": "RETRY_FROM_CHECKPOINT",
            "expected_operation_optimistic_version": 0,
            "expected_step_optimistic_version": 0,
            "reason": "operator recovery test",
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"


def test_operator_recovery_external_step_accepts_resume(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    accepted = _accept_submit(environment, workspace)
    external_step_id = advance_submit_to_external_step(
        environment.db_path,
        accepted["operation_id"],
    )
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{external_step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json=_recovery_body(
            environment,
            accepted,
            {"step_id": external_step_id},
            command="RESUME_RECONCILE",
        ),
    )
    assert response.status_code == 200
    assert response.json()["command"] == "RESUME_RECONCILE"
    assert response.json()["disposition"] == "APPLY"


def test_operator_recovery_rejects_retry_on_external_step(tmp_path: Path) -> None:
    environment = create_workspace_http_environment(tmp_path)
    seed = seed_submit_ready_workspace(environment.db_path, environment.artifact_store)
    workspace = _seeded_workspace_dict(seed)
    accepted = _accept_submit(environment, workspace)
    external_step_id = advance_submit_to_external_step(
        environment.db_path,
        accepted["operation_id"],
    )
    response = environment.client.post(
        f"/internal/v1/operations/{accepted['operation_id']}/steps/{external_step_id}/recovery",
        headers=environment.internal_auth_headers(),
        json=_recovery_body(
            environment,
            accepted,
            {"step_id": external_step_id},
            command="RETRY_FROM_CHECKPOINT",
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RECOVERY_CAPABILITY_CONFLICT"
