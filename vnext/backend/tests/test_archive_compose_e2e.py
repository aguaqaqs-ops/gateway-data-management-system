"""Compose smoke for dual-actor Submit/Review through Archive on deployed backend."""

from __future__ import annotations

import json
import os
from pathlib import Path
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
    assert_running_backend_worker_images_match_build,
    capture_running_container_provenance,
    compose_project_name,
    count_backend_operations,
    list_repository_commit_ids,
    persist_compose_gate_provenance,
    require_docker,
    resolve_main_commit_id,
    run_accept_to_submission_read_journey,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ARCHIVER_TOKEN = "compose-archiver-token"
ACTOR2_TOKEN = "compose-actor-2-token"


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
                        "token": ACTOR2_TOKEN,
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
            "COMPOSE_PROJECT_NAME": compose_project_name(
                tmp_path,
                default_prefix="gateway-archive-5d",
            ),
        }
    )
    return env


def _auth_headers(
    *,
    token: str = ARCHIVER_TOKEN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _approve_submission(
    client: httpx.Client,
    submission_id: str,
    *,
    idempotency_key: str,
) -> None:
    response = client.post(
        f"/v1/submissions/{submission_id}/review-events",
        headers=_auth_headers(idempotency_key=idempotency_key),
        json={"expected_review_version": 0, "action": "APPROVE"},
    )
    assert response.status_code == 201, response.text


def _candidate_for_submission(candidates_body: dict[str, Any], submission_id: str) -> dict[str, Any]:
    for candidate in candidates_body["candidates"]:
        if candidate["submission_id"] == submission_id:
            return cast(dict[str, Any], candidate)
    raise AssertionError(f"candidate not found for submission {submission_id}")


def test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect(
    tmp_path: Path,
) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    repository_id, initial_commit_id = start_three_container_stack(env, tmp_path)
    assert_running_backend_worker_images_match_build(env)
    provenance = capture_running_container_provenance(env)

    try:
        journey_a = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="compose-a",
            token=SESSION_TOKEN,
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=60.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_a["submission_id"]),
                idempotency_key="compose-review-a",
            )
        main_after_a = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)

        journey_b = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="compose-b",
            token=ACTOR2_TOKEN,
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=60.0,
        ) as reviewer:
            _approve_submission(
                reviewer,
                str(journey_b["submission_id"]),
                idempotency_key="compose-review-b",
            )
        main_after_both = resolve_main_commit_id(env, repository_id, bearer_token=BEARER_TOKEN)
        assert main_after_a != initial_commit_id
        assert main_after_both != main_after_a
        assert main_after_both != initial_commit_id
        assert journey_a["workspace_id"] != journey_b["workspace_id"]

        with httpx.Client(
            base_url=BACKEND_URL,
            headers=_auth_headers(token=ARCHIVER_TOKEN),
            timeout=60.0,
        ) as archiver:
            candidates = archiver.get("/v1/archive-candidates")
            assert candidates.status_code == 200, candidates.text
            candidates_body = cast(dict[str, Any], candidates.json())
            assert len(candidates_body["candidates"]) == 2
            selected = _candidate_for_submission(
                candidates_body,
                str(journey_a["submission_id"]),
            )
            sibling = _candidate_for_submission(
                candidates_body,
                str(journey_b["submission_id"]),
            )

            preview = archiver.post("/v1/archive-plan-preview", json={"selected": selected})
            assert preview.status_code == 200, preview.text
            preview_body = cast(dict[str, Any], preview.json())
            assert preview_body["can_start"] is False
            assert len(preview_body["anomalies"]) == 1
            anomaly = preview_body["anomalies"][0]
            assert anomaly["issue_code"] == "APPROVED_SIBLING_EXCLUDED"
            assert anomaly["sibling_submission_id"] == journey_b["submission_id"]
            assert len(preview_body["workspace_releases"]) == 2

            confirm = archiver.post(
                "/v1/archive-confirmations",
                headers=_auth_headers(idempotency_key="compose-archive-confirm"),
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
            resolve = archiver.post(
                "/v1/archive-anomaly-resolutions",
                headers=_auth_headers(idempotency_key="compose-archive-resolve"),
                json={
                    "expected_baseline_node_id": preview_body["head"]["business_baseline_node_id"],
                    "expected_baseline_head_version": preview_body["head"]["baseline_head_version"],
                    "selected": selected,
                    "candidate_set_digest": preview_body["candidate_set_digest"],
                    "subject_digest": anomaly["subject_digest"],
                    "expected_sequence": 0,
                    "action": "ACKNOWLEDGE_EXCLUSION",
                    "reason": "acknowledge sibling exclusion",
                    "issue_code": "APPROVED_SIBLING_EXCLUDED",
                    "sibling_submission_id": sibling["submission_id"],
                    "sibling_candidate_digest": sibling["expected_candidate_digest"],
                },
            )
            assert resolve.status_code == 201, resolve.text

            ready_preview = archiver.post(
                "/v1/archive-plan-preview",
                json={"selected": selected},
            )
            assert ready_preview.status_code == 200, ready_preview.text
            ready_body = cast(dict[str, Any], ready_preview.json())
            assert ready_body["can_start"] is True

            operation_count_before = count_backend_operations(env)
            main_before_archive = resolve_main_commit_id(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            commits_before = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )

            start = archiver.post(
                "/v1/archives",
                headers=_auth_headers(idempotency_key="compose-archive-start"),
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
                    "anomaly_resolution_refs": [
                        {
                            "subject_digest": anomaly["subject_digest"],
                            "sequence": resolve.json()["sequence"],
                        }
                    ],
                },
            )
            assert start.status_code == 201, start.text
            started = cast(dict[str, Any], start.json())
            assert started["selected_submission_id"] == journey_a["submission_id"]
            assert started["baseline_commit_id"] == main_after_a
            assert started["baseline_head_version"] == ready_body["head"]["baseline_head_version"] + 1
            disposition_map = {
                item["submission_id"]: item["disposition"] for item in started["dispositions"]
            }
            assert disposition_map[journey_a["submission_id"]] == "ARCHIVED_BASELINE"
            assert disposition_map[journey_b["submission_id"]] == "CLOSED_NOT_ARCHIVED"
            assert set(started["released_workspace_ids"]) == {
                journey_a["workspace_id"],
                journey_b["workspace_id"],
            }

            main_after_archive = resolve_main_commit_id(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            commits_after = list_repository_commit_ids(
                env,
                repository_id,
                bearer_token=BEARER_TOKEN,
            )
            assert commits_before
            assert main_before_archive in commits_before
            assert main_after_archive == main_before_archive
            assert commits_after == commits_before
            assert count_backend_operations(env) == operation_count_before

            post_archive_candidates = archiver.get("/v1/archive-candidates")
            assert post_archive_candidates.status_code == 200, post_archive_candidates.text
            post_head = cast(dict[str, Any], post_archive_candidates.json())["head"]
            assert post_head["baseline_head_version"] == started["baseline_head_version"]

            new_base_preview = archiver.post("/v1/archive-plan-preview", json={"selected": None})
            assert new_base_preview.status_code == 200, new_base_preview.text
            assert new_base_preview.json()["head"]["baseline_head_version"] == post_head[
                "baseline_head_version"
            ]

            result = archiver.get(f"/v1/archives/{started['archive_result_id']}")
            assert result.status_code == 200, result.text
            audit = archiver.get(
                "/v1/archive-audit-events",
                params={
                    "subject_kind": "CONFIRM_SELECTION",
                    "subject_digest": ready_body["selection_subject_digest"],
                    "after_sequence": 0,
                    "limit": 100,
                },
            )
            assert audit.status_code == 200, audit.text

            restart = run_compose(env, "restart", "backend", "worker")
            if restart.returncode != 0:
                pytest.fail(f"compose restart failed: {restart.stderr}\n{restart.stdout}")
            wait_http_ok(f"{BACKEND_URL}/readyz")

            restarted_candidates = archiver.get("/v1/archive-candidates")
            assert restarted_candidates.status_code == 200, restarted_candidates.text
            restarted_head = cast(dict[str, Any], restarted_candidates.json())["head"]
            assert restarted_head == post_head
            restarted_result = archiver.get(f"/v1/archives/{started['archive_result_id']}")
            assert restarted_result.status_code == 200, restarted_result.text
            restarted_audit = archiver.get(
                "/v1/archive-audit-events",
                params={
                    "subject_kind": "CONFIRM_SELECTION",
                    "subject_digest": ready_body["selection_subject_digest"],
                    "after_sequence": 0,
                    "limit": 100,
                },
            )
            assert restarted_audit.status_code == 200, restarted_audit.text
    finally:
        provenance_path = persist_compose_gate_provenance(env, provenance)
        print(f"compose gate provenance written to {provenance_path}")
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
