"""Three-container compose smoke for backend, worker, and repository-service."""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

import pytest

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    compose_project_name,
    require_docker,
    run_accept_to_submission_read_journey,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

_start_three_container_stack = start_three_container_stack
_run_accept_to_submission_read_journey = run_accept_to_submission_read_journey


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
                        "actor_id": "compose-actor",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                        ],
                    }
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
                        "business_baseline_node_id": "compose-node",
                        "business_baseline_commit_id": "pending-commit-seed",
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
            "GATEWAY_BACKEND_SESSION_FILE": str(session),
            "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
            "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
            "GATEWAY_REPOSITORY_SERVICE_IMAGE": os.environ.get(
                "GATEWAY_REPOSITORY_SERVICE_IMAGE",
                "gateway-repository-service:local",
            ),
            "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="gateway-submit-s8"),
        }
    )
    return env


def test_compose_three_process_submit_stack_smoke_and_backend_restart(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    start_three_container_stack(env, tmp_path)

    try:
        health = urllib.request.urlopen(f"{BACKEND_URL}/healthz", timeout=5.0)
        ready = urllib.request.urlopen(f"{BACKEND_URL}/readyz", timeout=5.0)
        assert health.status == 200
        assert ready.status == 200
        assert BEARER_TOKEN not in health.read().decode("utf-8")

        restart = run_compose(env, "restart", "backend")
        if restart.returncode != 0:
            pytest.fail(f"compose restart backend failed: {restart.stderr}\n{restart.stdout}")
        wait_http_ok(f"{BACKEND_URL}/readyz")

        workspace_request = urllib.request.Request(
            f"{BACKEND_URL}/v1/workspaces",
            data=json.dumps(
                {
                    "gateway_device_external_key": DEVICE_KEY,
                    "business_project_id": PROJECT_ID,
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {SESSION_TOKEN}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(workspace_request, timeout=10.0) as response:
            assert response.status in {200, 201}
            body = json.loads(response.read().decode("utf-8"))
        assert "workspace_id" in body
    finally:
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")


def test_compose_accept_upload_import_poll_t3_read_journey(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    _repository_id, initial_commit_id = start_three_container_stack(env, tmp_path)

    try:
        journey = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
        )
        assert journey["submission_id"]
        assert journey["preview_result_id"].startswith("pr-")
    finally:
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
