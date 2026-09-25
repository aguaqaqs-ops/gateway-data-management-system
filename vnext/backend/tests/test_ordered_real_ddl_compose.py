"""F2 blocked ordered real DDL compose journey."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BASELINE_NODE_ID,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_project_name,
    ordered_syx_sized_upload_files,
    poll_operation,
    read_workspace_row,
    require_docker,
    start_three_container_stack,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ACTOR2_TOKEN = "compose-actor-2-token"
_SUBMIT_STEP_TIMEOUT_SECONDS = 90.0


def _compose_env(tmp_path: Path) -> dict[str, str]:
    bearer = tmp_path / "repository-bearer-token"
    bearer.write_text(f"{BEARER_TOKEN}\n", encoding="utf-8")
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": SESSION_TOKEN,
                        "actor_id": "compose-actor-1",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                        ],
                    },
                    {
                        "token": ACTOR2_TOKEN,
                        "actor_id": "compose-actor-2",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    internal_bearer = tmp_path / "internal-bearer-token"
    internal_bearer.write_text("compose-internal-bearer\n", encoding="utf-8")
    mapping = tmp_path / "provisioned-mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "repository_id": "pending-repository-seed",
                        "business_baseline_node_id": BASELINE_NODE_ID,
                        "business_baseline_commit_id": "pending-commit-seed",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="ordered-real-ddl"),
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
        "GATEWAY_BACKEND_SESSION_FILE": str(session),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
        "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(bearer),
    }


def _worker_log_tail(env: dict[str, str]) -> str:
    project = env["COMPOSE_PROJECT_NAME"]
    completed = subprocess.run(
        ["docker", "logs", f"{project}-worker-1"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    return (completed.stdout or "") + (completed.stderr or "")


def _run_preview_and_submit(
    env: dict[str, str],
    *,
    journey_key_prefix: str,
    upload_files_factory: Callable[[int], dict[str, tuple[str, bytes, str]]],
    token: str = ACTOR2_TOKEN,
) -> dict[str, Any]:
    with httpx.Client(
        base_url=BACKEND_URL,
        headers=compose_auth_headers(token=token),
        timeout=60.0,
    ) as client:
        workspace = client.post(
            "/v1/workspaces",
            json={
                "gateway_device_external_key": DEVICE_KEY,
                "business_project_id": PROJECT_ID,
            },
        )
        assert workspace.status_code in {200, 201}, workspace.text
        workspace_body = workspace.json()
        workspace_id = workspace_body["workspace_id"]
        upload_payload = upload_files_factory(workspace_body["optimistic_version"])
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/upload-revisions",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-upload"),
            files=upload_payload,
        )
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()
        preview = client.post(
            f"/v1/workspaces/{workspace_id}/preview-operations",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-preview"),
            json={
                "expected_workspace_version": upload_body["optimistic_version"],
                "upload_revision_id": upload_body["upload_revision_id"],
                "generation": upload_body["generation"],
                "expected_baseline_node_id": BASELINE_NODE_ID,
                "expected_baseline_head_version": 0,
                "options": {},
            },
        )
        assert preview.status_code == 202, preview.text
        preview_operation_id = preview.json()["operation_id"]
        preview_terminal = poll_operation(
            client,
            preview_operation_id,
            timeout_seconds=_SUBMIT_STEP_TIMEOUT_SECONDS,
        )
        workspace_row = read_workspace_row(env, workspace_id)
        accepted = client.post(
            f"/v1/workspaces/{workspace_id}/submit-attempts",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-submit"),
            json={
                "expected_workspace_version": workspace_row["optimistic_version"],
                "upload_revision_id": upload_body["upload_revision_id"],
                "preview_result_id": workspace_row["current_preview_result_id"],
                "generation": workspace_row["generation"],
                "expected_baseline_node_id": BASELINE_NODE_ID,
                "expected_baseline_head_version": 0,
                "options": {},
            },
        )
        assert accepted.status_code == 202, accepted.text
        submit_operation_id = accepted.json()["operation_id"]
        deadline = time.monotonic() + _SUBMIT_STEP_TIMEOUT_SECONDS
        submit_terminal: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            response = client.get(f"/v1/operations/{submit_operation_id}")
            body = cast(dict[str, Any], response.json())
            if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                submit_terminal = body
                break
            time.sleep(2.0)
        worker_tail = _worker_log_tail(env)
        return {
            "preview_status": preview_terminal["status"],
            "submit_status": submit_terminal["status"] if submit_terminal is not None else "TIMEOUT",
            "worker_tail": worker_tail,
        }


@pytest.mark.xfail(
    strict=True,
    reason="F2 blocked until storage projection type normalization",
)
def test_ordered_real_ddl_pair_blocked_pending_type_normalization(tmp_path: Path) -> None:
    env = _compose_env(tmp_path)
    require_docker(compose_project_name=env["COMPOSE_PROJECT_NAME"])
    try:
        start_three_container_stack(env, tmp_path, import_baseline=True)
        result = _run_preview_and_submit(
            env,
            journey_key_prefix="ordered-real-ddl",
            upload_files_factory=lambda version: ordered_syx_sized_upload_files(
                t_rows=(1,),
                before_ordered_rows=(),
                after_ordered_rows=((5, 1, "y"), (7, 2, "z")),
                expected_version=version,
            ),
        )
        assert result["preview_status"] == "SUCCEEDED"
        assert result["submit_status"] == "SUCCEEDED"
        assert "UNSUPPORTED_TABLE" not in result["worker_tail"]
    finally:
        cleanup_compose_project_artifacts(env)
