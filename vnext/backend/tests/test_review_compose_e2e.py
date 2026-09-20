"""Compose smoke for Submit finalize through Review approve on deployed backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from tests.support.compose_gate_harness import BACKEND_URL, compose_project_name, require_docker, run_compose
from tests.test_submit_compose_e2e import (
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    _run_accept_to_submission_read_journey,
    _start_three_container_stack,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]


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
                            "review_submission",
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
            "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="gateway-review-s5"),
        }
    )
    return env


def _resolve_main_commit_id(env: dict[str, str], repository_id: str) -> str:
    script = f"""
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/repositories/{repository_id}/versioned/refs/main",
    headers={{"Authorization": "Bearer {BEARER_TOKEN}"}},
)
with urllib.request.urlopen(req, timeout=30) as response:
    print(json.loads(response.read().decode())["commit_id"])
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to resolve repository main ref: {result.stderr}\n{result.stdout}")
    commit_id = result.stdout.strip()
    if not commit_id:
        pytest.fail("repository main resolve returned empty commit_id")
    return commit_id


def _auth_headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def test_compose_submit_to_review_approve_journey(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    repository_id, initial_commit_id = _start_three_container_stack(env, tmp_path)

    try:
        journey = _run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
        )
        submission_id = str(journey["submission_id"])
        main_before_review = _resolve_main_commit_id(env, repository_id)

        with httpx.Client(base_url=BACKEND_URL, headers=_auth_headers(), timeout=60.0) as client:
            approve = client.post(
                f"/v1/submissions/{submission_id}/review-events",
                headers=_auth_headers(idempotency_key="compose-review-approve"),
                json={
                    "expected_review_version": 0,
                    "action": "APPROVE",
                },
            )
            assert approve.status_code == 201, approve.text
            approve_body = cast(dict[str, Any], approve.json())
            assert approve_body["status"] == "APPROVED"
            assert approve_body["review_version"] == 1
            assert approve_body["event"]["event_kind"] == "APPROVED"
            assert SESSION_TOKEN not in approve.text
            assert BEARER_TOKEN not in approve.text

            facts = client.get(f"/v1/submissions/{submission_id}/review")
            assert facts.status_code == 200, facts.text
            facts_body = cast(dict[str, Any], facts.json())
            assert facts_body["status"] == "APPROVED"
            assert facts_body["review_version"] == 1
            assert len(facts_body["events"]) == 2
            assert facts_body["events"][0]["event_kind"] == "SUBMISSION_FINALIZED"
            assert facts_body["events"][1]["event_kind"] == "APPROVED"
            assert facts_body["events"][1]["sequence"] == 1

        main_after_review = _resolve_main_commit_id(env, repository_id)
        assert main_after_review == main_before_review
    finally:
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
