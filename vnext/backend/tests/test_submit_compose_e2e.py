"""Three-container compose smoke for backend, worker, and repository-service."""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
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
    cleanup_compose_project_artifacts,
    compose_auth_headers,
    compose_project_name,
    read_repository_catalog,
    require_docker,
    resolve_main_commit_id,
    run_accept_to_submission_read_journey,
    run_compose,
    start_three_container_stack,
    wait_http_ok,
)
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.upload_http_packages import upload_files

pytestmark = [pytest.mark.integration, pytest.mark.serial]
ARCHIVER_TOKEN = "compose-archiver-token"

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
                            "review_submission",
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
            "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="gateway-submit-s8"),
        }
    )
    return env


def _source_package(tables: tuple[str, ...]) -> bytes:
    statements = {
        "t": (
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);",
            "INSERT INTO t VALUES (1);",
        ),
        "com_cfg": (
            "CREATE TABLE com_cfg (`index` INT NOT NULL, `no` INT NOT NULL, `value` VARCHAR(8), PRIMARY KEY (`index`));",
            "INSERT INTO com_cfg VALUES (1, 10, 'a');",
        ),
        "net_cfg": (
            "CREATE TABLE net_cfg (board INT NOT NULL, link_no INT NOT NULL, `no` INT NOT NULL, PRIMARY KEY (board, link_no));",
            "INSERT INTO net_cfg VALUES (1, 1, 10);",
        ),
    }
    sql = "\n".join(statement for table in tables for statement in statements[table]) + "\n"
    return pack_tar_gz({"sql/dbcfg.sql": sql.encode()})


def _upload_transition(
    before: tuple[str, ...],
    after: tuple[str, ...],
) -> Callable[[int], dict[str, tuple[str, bytes, str]]]:
    initial_bytes = _source_package(before)
    modified_bytes = _source_package(after)

    def build(expected_version: int) -> dict[str, tuple[str, bytes, str]]:
        return upload_files(
            expected_version=expected_version,
            initial_bytes=initial_bytes,
            modified_bytes=modified_bytes,
        )

    return build


def _archive_single_submission(client: httpx.Client, submission_id: str) -> dict[str, Any]:
    candidates = client.get("/v1/archive-candidates")
    assert candidates.status_code == 200, candidates.text
    selected = next(
        item for item in candidates.json()["candidates"] if item["submission_id"] == submission_id
    )
    preview = client.post("/v1/archive-plan-preview", json={"selected": selected})
    assert preview.status_code == 200, preview.text
    preview_body = cast(dict[str, Any], preview.json())
    assert preview_body["can_start"] is True
    head = cast(dict[str, Any], preview_body["head"])
    confirmation = client.post(
        "/v1/archive-confirmations",
        headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="removed-tables-confirm"),
        json={
            "expected_baseline_node_id": head["business_baseline_node_id"],
            "expected_baseline_head_version": head["baseline_head_version"],
            "selected": selected,
            "candidate_set_digest": preview_body["candidate_set_digest"],
            "subject_digest": preview_body["selection_subject_digest"],
            "expected_sequence": 0,
            "action": "CONFIRM",
            "reason": "archive removal test baseline",
        },
    )
    assert confirmation.status_code == 201, confirmation.text
    started = client.post(
        "/v1/archives",
        headers=compose_auth_headers(token=ARCHIVER_TOKEN, idempotency_key="removed-tables-start"),
        json={
            "expected_baseline_node_id": head["business_baseline_node_id"],
            "expected_baseline_head_version": head["baseline_head_version"],
            "candidate_set_digest": preview_body["candidate_set_digest"],
            "selected": selected,
            "confirmation_refs": [
                {
                    "subject_digest": preview_body["selection_subject_digest"],
                    "sequence": confirmation.json()["sequence"],
                }
            ],
        },
    )
    assert started.status_code == 201, started.text
    return cast(dict[str, Any], started.json())


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


def test_compose_submit_removes_deleted_user_and_sibling_tables(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    repository_id, initial_commit_id = start_three_container_stack(env, tmp_path)

    try:
        archived_submission = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
            journey_key_prefix="removed-tables-baseline",
            upload_files_factory=_upload_transition(("t", "com_cfg"), ("t", "com_cfg")),
        )
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            timeout=120.0,
        ) as archiver:
            approval = archiver.post(
                f"/v1/submissions/{archived_submission['submission_id']}/review-events",
                headers=compose_auth_headers(
                    token=ARCHIVER_TOKEN,
                    idempotency_key="removed-tables-review-baseline",
                ),
                json={"expected_review_version": 0, "action": "APPROVE"},
            )
            assert approval.status_code == 201, approval.text
            archived = _archive_single_submission(
                archiver,
                str(archived_submission["submission_id"]),
            )

        baseline_commit_id = str(archived["baseline_commit_id"])
        baseline_node_id = str(archived["baseline_node_id"])
        baseline_version = int(archived["baseline_head_version"])
        sibling = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=baseline_commit_id,
            journey_key_prefix="removed-tables-sibling-addition",
            expected_baseline_node_id=baseline_node_id,
            expected_baseline_head_version=baseline_version,
            upload_files_factory=_upload_transition(
                ("t", "com_cfg"),
                ("t", "com_cfg", "net_cfg"),
            ),
        )
        sibling_commit_id = resolve_main_commit_id(
            env,
            repository_id,
            bearer_token=BEARER_TOKEN,
        )
        sibling_catalog = read_repository_catalog(
            env,
            repository_id=repository_id,
            commit_id=sibling_commit_id,
        )
        assert {table["name"] for table in sibling_catalog["tables"]} == {
            "t",
            "com_cfg",
            "net_cfg",
        }
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ARCHIVER_TOKEN),
            timeout=60.0,
        ) as reviewer:
            sibling_approval = reviewer.post(
                f"/v1/submissions/{sibling['submission_id']}/review-events",
                headers=compose_auth_headers(
                    token=ARCHIVER_TOKEN,
                    idempotency_key="removed-tables-review-sibling",
                ),
                json={"expected_review_version": 0, "action": "APPROVE"},
            )
            assert sibling_approval.status_code == 201, sibling_approval.text

        deleted = run_accept_to_submission_read_journey(
            env,
            initial_commit_id=baseline_commit_id,
            journey_key_prefix="removed-tables-user-deletion",
            expected_baseline_node_id=baseline_node_id,
            expected_baseline_head_version=baseline_version,
            upload_files_factory=_upload_transition(
                ("t", "com_cfg"),
                ("com_cfg",),
            ),
        )
        assert deleted["submission_id"]
        final_commit_id = resolve_main_commit_id(
            env,
            repository_id,
            bearer_token=BEARER_TOKEN,
        )
        final_catalog = read_repository_catalog(
            env,
            repository_id=repository_id,
            commit_id=final_commit_id,
        )
        assert {table["name"] for table in final_catalog["tables"]} == {"com_cfg"}
    finally:
        cleanup_compose_project_artifacts(env)
