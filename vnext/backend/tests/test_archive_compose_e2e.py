"""Compose smoke for Submit/Review through Archive on deployed backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from tests.support.compose_gate_harness import BACKEND_URL, compose_project_name, require_docker, run_compose
from tests.test_review_compose_e2e import _resolve_main_commit_id
from tests.test_submit_compose_e2e import (
    BASELINE_NODE_ID,
    BEARER_TOKEN,
    DEVICE_KEY,
    PROJECT_ID,
    SESSION_TOKEN,
    _run_accept_to_submission_read_journey,
    _start_three_container_stack,
    _wait_http_ok,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ARCHIVER_TOKEN = "compose-archiver-token"
REVIEWER_TOKEN = "compose-reviewer-token"


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
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": ARCHIVER_TOKEN,
                        "actor_id": "compose-archiver",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "review_submission",
                            "archive_submission",
                        ],
                    },
                    {
                        "token": REVIEWER_TOKEN,
                        "actor_id": "compose-actor-2",
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "permissions": [
                            "workspace_read",
                            "upload_submit_workspace",
                            "preview_workspace",
                            "review_submission",
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
            "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="gateway-archive-5d"),
        }
    )
    return env


def _auth_headers(
    *,
    token: str = SESSION_TOKEN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _approve_submission(client: httpx.Client, submission_id: str, *, idempotency_key: str) -> None:
    response = client.post(
        f"/v1/submissions/{submission_id}/review-events",
        headers=_auth_headers(idempotency_key=idempotency_key),
        json={"expected_review_version": 0, "action": "APPROVE"},
    )
    assert response.status_code == 201, response.text


def test_compose_archive_single_submission_journey_restart_and_head_persistence(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    repository_id, initial_commit_id = _start_three_container_stack(env, tmp_path)

    try:
        journey = _run_accept_to_submission_read_journey(env, initial_commit_id=initial_commit_id)
        main_after_submit = _resolve_main_commit_id(env, repository_id)
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=REVIEWER_TOKEN),
            timeout=60.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey["submission_id"]),
                idempotency_key="compose-review-first",
            )

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=60.0,
        ) as archiver:
            candidates = archiver.get("/v1/archive-candidates")
            assert candidates.status_code == 200, candidates.text
            candidates_body = cast(dict[str, Any], candidates.json())
            assert len(candidates_body["candidates"]) == 1
            selected = candidates_body["candidates"][0]
            preview = archiver.post(
                "/v1/archive-plan-preview",
                json={"selected": selected},
            )
            assert preview.status_code == 200, preview.text
            preview_body = cast(dict[str, Any], preview.json())
            assert preview_body["can_start"] is False

            confirm = archiver.post(
                "/v1/archive-confirmations",
                headers=_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="compose-archive-confirm"),
                json={
                    "expected_baseline_node_id": preview_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": preview_body["head"]["baseline_head_version"],
                    "selected": selected,
                    "candidate_set_digest": preview_body["candidate_set_digest"],
                    "subject_digest": preview_body["selection_subject_digest"],
                    "expected_sequence": 0,
                    "action": "CONFIRM",
                    "reason": "confirm archive selection",
                },
            )
            assert confirm.status_code == 201, confirm.text
            assert preview_body["anomalies"] == []

            preview_ready = archiver.post("/v1/archive-plan-preview", json={"selected": selected})
            assert preview_ready.status_code == 200, preview_ready.text
            ready_body = cast(dict[str, Any], preview_ready.json())
            assert ready_body["can_start"] is True

            main_before_archive = _resolve_main_commit_id(env, repository_id)
            start = archiver.post(
                "/v1/archives",
                headers=_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="compose-archive-start"),
                json={
                    "expected_baseline_node_id": ready_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": ready_body["head"]["baseline_head_version"],
                    "candidate_set_digest": ready_body["candidate_set_digest"],
                    "selected": selected,
                    "confirmation_refs": [
                        {
                            "subject_digest": ready_body["selection_subject_digest"],
                            "sequence": confirm.json()["sequence"],
                        }
                    ],
                    "anomaly_resolution_refs": [],
                },
            )
            assert start.status_code == 201, start.text
            started = cast(dict[str, Any], start.json())
            assert started["selected_submission_id"] == journey["submission_id"]
            main_after_archive = _resolve_main_commit_id(env, repository_id)
            assert main_after_archive == main_before_archive
            assert main_after_archive == main_after_submit

            result = archiver.get(f"/v1/archives/{started['archive_result_id']}")
            assert result.status_code == 200, result.text

            post_archive_candidates = archiver.get("/v1/archive-candidates")
            assert post_archive_candidates.status_code == 200, post_archive_candidates.text
            post_head = cast(dict[str, Any], post_archive_candidates.json())["head"]
            assert post_head["baseline_head_version"] == ready_body["head"]["baseline_head_version"] + 1

            restart = run_compose(env, "restart", "backend", "worker")
            if restart.returncode != 0:
                pytest.fail(f"compose restart failed: {restart.stderr}\n{restart.stdout}")
            _wait_http_ok(f"{BACKEND_URL}/readyz")

            with httpx.Client(
                base_url=BACKEND_URL,
                headers=_auth_headers(token=ARCHIVER_TOKEN),
                timeout=60.0,
            ) as archiver_after_restart:
                restarted_candidates = archiver_after_restart.get("/v1/archive-candidates")
                assert restarted_candidates.status_code == 200, restarted_candidates.text
                restarted_head = cast(dict[str, Any], restarted_candidates.json())["head"]
                assert restarted_head == post_head
                restarted_result = archiver_after_restart.get(
                    f"/v1/archives/{started['archive_result_id']}"
                )
                assert restarted_result.status_code == 200, restarted_result.text
    finally:
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
