"""T3 ordered submit bisect control cases on default compose stack."""

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
    assert_running_backend_worker_images_match_build,
    assert_submit_occupancy_cleared_in_compose,
    assert_worker_container_unchanged,
    capture_running_container_provenance,
    capture_worker_container_state,
    compose_auth_headers,
    cleanup_compose_project_artifacts,
    compose_project_name,
    modified_table_upload_files,
    normalize_running_images,
    ordered_syx_vocabulary_upload_files,
    persist_compose_gate_provenance,
    poll_operation,
    read_workspace_row,
    require_docker,
    run_accept_to_submission_read_journey,
    run_compose,
    start_three_container_stack,
)
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.upload_http_packages import upload_files

pytestmark = [pytest.mark.integration, pytest.mark.serial]

ACTOR2_TOKEN = "compose-actor-2-token"
_SUBMIT_STEP_TIMEOUT_SECONDS = 90.0


def _compose_env(tmp_path: Path, *, prefix: str) -> dict[str, str]:
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
        "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix=prefix),
        "GATEWAY_P2R2_BEARER_TOKEN_FILE": str(bearer),
        "GATEWAY_BACKEND_SESSION_FILE": str(session),
        "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE": str(mapping),
        "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE": str(internal_bearer),
        "GATEWAY_REPOSITORY_SERVICE_BEARER_TOKEN_FILE": str(bearer),
    }


def _t3_decimal_upload_files(expected_version: int = 0) -> dict[str, tuple[str, bytes, str]]:
    initial_sql = b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\nINSERT INTO t VALUES (1);\n"
    modified_sql = (
        b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
        b"INSERT INTO t VALUES (1);\n"
        b"CREATE TABLE t3 (id INT NOT NULL PRIMARY KEY, amount DECIMAL(10,2) NOT NULL);\n"
        b"INSERT INTO t3 VALUES (1, 1.00);\n"
    )
    return upload_files(
        expected_version=expected_version,
        initial_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
        modified_bytes=pack_tar_gz({"sql/dbcfg.sql": modified_sql}),
    )


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


def _baseline_only_upload_files(expected_version: int = 0) -> dict[str, tuple[str, bytes, str]]:
    initial_sql = b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\nINSERT INTO t VALUES (1);\n"
    return upload_files(
        expected_version=expected_version,
        initial_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
        modified_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
    )


def _run_preview_and_submit(
    env: dict[str, str],
    *,
    journey_key_prefix: str,
    upload_files_factory: Callable[[int], dict[str, tuple[str, bytes, str]]],
    token: str = ACTOR2_TOKEN,
    retry_upload_files_factory: Callable[[int], dict[str, tuple[str, bytes, str]]] | None = None,
    worker_baseline: dict[str, str] | None = None,
    expected_preview_failure_code: str | None = None,
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
        preview_failure: dict[str, str] | None = None
        if expected_preview_failure_code is not None:
            assert retry_upload_files_factory is not None
            assert preview_terminal["status"] == "FAILED", json.dumps(preview_terminal, indent=2)
            diagnostic = preview_terminal.get("diagnostic")
            assert isinstance(diagnostic, dict)
            assert diagnostic.get("code") == expected_preview_failure_code
            preview_failure = {
                "operation_id": preview_operation_id,
                "status": str(preview_terminal["status"]),
                "diagnostic_code": str(diagnostic["code"]),
                "diagnostic_message": str(diagnostic.get("message", "")),
            }
            if worker_baseline is not None:
                assert_worker_container_unchanged(env, worker_baseline)
            workspace_row = read_workspace_row(env, workspace_id, require_preview_result=False)
            assert workspace_row["current_preview_result_id"] is None
            retry_upload_payload = retry_upload_files_factory(workspace_row["optimistic_version"])
            retry_upload = client.post(
                f"/v1/workspaces/{workspace_id}/upload-revisions",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-retry-upload",
                ),
                files=retry_upload_payload,
            )
            assert retry_upload.status_code == 201, retry_upload.text
            upload_body = retry_upload.json()
            retry_preview = client.post(
                f"/v1/workspaces/{workspace_id}/preview-operations",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-retry-preview",
                ),
                json={
                    "expected_workspace_version": upload_body["optimistic_version"],
                    "upload_revision_id": upload_body["upload_revision_id"],
                    "generation": upload_body["generation"],
                    "expected_baseline_node_id": BASELINE_NODE_ID,
                    "expected_baseline_head_version": 0,
                    "options": {},
                },
            )
            assert retry_preview.status_code == 202, retry_preview.text
            preview_operation_id = retry_preview.json()["operation_id"]
            preview_terminal = poll_operation(
                client,
                preview_operation_id,
                timeout_seconds=_SUBMIT_STEP_TIMEOUT_SECONDS,
            )
            assert preview_terminal["status"] == "SUCCEEDED", json.dumps(preview_terminal, indent=2)
            retry_upload_files_factory = None
        else:
            assert preview_terminal["status"] == "SUCCEEDED", json.dumps(preview_terminal, indent=2)
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
        accepted_body = accepted.json()
        submit_operation_id = accepted_body["operation_id"]
        submit_attempt_id = accepted_body["submit_attempt_id"]
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
        diagnostic = submit_terminal.get("diagnostic") if submit_terminal is not None else None
        result: dict[str, Any] = {
            "workspace_id": workspace_id,
            "submission_id": accepted_body.get("submission_id"),
            "submit_attempt_id": submit_attempt_id,
            "preview_status": preview_terminal["status"],
            "preview_operation_id": preview_operation_id,
            "submit_operation_id": submit_operation_id,
            "submit_status": submit_terminal["status"] if submit_terminal is not None else "TIMEOUT",
            "submit_diagnostic_code": (
                str(diagnostic["code"]) if isinstance(diagnostic, dict) else None
            ),
            "submit_diagnostic_message": (
                str(diagnostic["message"]) if isinstance(diagnostic, dict) else None
            ),
            "worker_tail": worker_tail,
        }
        if preview_failure is not None:
            result["failed_preview_operation_id"] = preview_failure["operation_id"]
            result["failed_preview_status"] = preview_failure["status"]
            result["failed_preview_diagnostic_code"] = preview_failure["diagnostic_code"]
            result["failed_preview_diagnostic_message"] = preview_failure["diagnostic_message"]
        if retry_upload_files_factory is not None:
            if result["submit_status"] == "FAILED":
                assert_submit_occupancy_cleared_in_compose(
                    env,
                    workspace_id=workspace_id,
                    submit_attempt_id=submit_attempt_id,
                )
                if worker_baseline is not None:
                    assert_worker_container_unchanged(env, worker_baseline)
            workspace_row = read_workspace_row(env, workspace_id)
            # Re-accept with stale preview/upload is expected to 409; this is not occupancy proof.
            reaccept = client.post(
                f"/v1/workspaces/{workspace_id}/submit-attempts",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-resubmit-check",
                ),
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
            assert reaccept.status_code == 409, reaccept.text
            reaccept_body = reaccept.json()
            result["resubmit_accept_status"] = reaccept.status_code
            result["resubmit_accept_code"] = reaccept_body.get("code")
            retry_upload_payload = retry_upload_files_factory(workspace_row["optimistic_version"])
            retry_upload = client.post(
                f"/v1/workspaces/{workspace_id}/upload-revisions",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-retry-upload",
                ),
                files=retry_upload_payload,
            )
            assert retry_upload.status_code == 201, retry_upload.text
            retry_upload_body = retry_upload.json()
            retry_preview = client.post(
                f"/v1/workspaces/{workspace_id}/preview-operations",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-retry-preview",
                ),
                json={
                    "expected_workspace_version": retry_upload_body["optimistic_version"],
                    "upload_revision_id": retry_upload_body["upload_revision_id"],
                    "generation": retry_upload_body["generation"],
                    "expected_baseline_node_id": BASELINE_NODE_ID,
                    "expected_baseline_head_version": 0,
                    "options": {},
                },
            )
            assert retry_preview.status_code == 202, retry_preview.text
            retry_preview_operation_id = retry_preview.json()["operation_id"]
            retry_preview_terminal = poll_operation(
                client,
                retry_preview_operation_id,
                timeout_seconds=_SUBMIT_STEP_TIMEOUT_SECONDS,
            )
            workspace_row = read_workspace_row(env, workspace_id)
            retry_accepted = client.post(
                f"/v1/workspaces/{workspace_id}/submit-attempts",
                headers=compose_auth_headers(
                    token=token,
                    idempotency_key=f"{journey_key_prefix}-retry-submit",
                ),
                json={
                    "expected_workspace_version": workspace_row["optimistic_version"],
                    "upload_revision_id": retry_upload_body["upload_revision_id"],
                    "preview_result_id": workspace_row["current_preview_result_id"],
                    "generation": workspace_row["generation"],
                    "expected_baseline_node_id": BASELINE_NODE_ID,
                    "expected_baseline_head_version": 0,
                    "options": {},
                },
            )
            assert retry_accepted.status_code == 202, retry_accepted.text
            retry_submit_operation_id = retry_accepted.json()["operation_id"]
            deadline = time.monotonic() + _SUBMIT_STEP_TIMEOUT_SECONDS
            retry_submit_terminal: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                response = client.get(f"/v1/operations/{retry_submit_operation_id}")
                body = cast(dict[str, Any], response.json())
                if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    retry_submit_terminal = body
                    break
                time.sleep(2.0)
            result["retry_preview_status"] = retry_preview_terminal["status"]
            result["retry_submit_operation_id"] = retry_submit_operation_id
            result["retry_submit_status"] = (
                retry_submit_terminal["status"] if retry_submit_terminal is not None else "TIMEOUT"
            )
            result["retry_submission_id"] = retry_accepted.json().get("submission_id")
        return result


def test_ordered_submit_bisect_control_cases(tmp_path: Path) -> None:
    provenance: dict[str, dict[str, str]] = {}
    empty_root = tmp_path / "empty-baseline"
    empty_root.mkdir(parents=True, exist_ok=True)
    empty_env = _compose_env(empty_root, prefix="ordered-bisect-c")
    require_docker(compose_project_name=empty_env["COMPOSE_PROJECT_NAME"])
    try:
        _, empty_initial_commit_id = start_three_container_stack(
            empty_env,
            empty_root,
        )
        case_c = run_accept_to_submission_read_journey(
            empty_env,
            initial_commit_id=empty_initial_commit_id,
            journey_key_prefix="bisect-empty-t",
            token=SESSION_TOKEN,
            upload_files_factory=lambda version: modified_table_upload_files(
                insert_value=2,
                expected_version=version,
            ),
        )
        print("case_c_empty_baseline", json.dumps(case_c, indent=2))
        assert case_c["submission_id"]
    finally:
        cleanup_compose_project_artifacts(empty_env)

    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir(parents=True, exist_ok=True)
    baseline_env = _compose_env(baseline_root, prefix="ordered-bisect-b")
    require_docker(compose_project_name=baseline_env["COMPOSE_PROJECT_NAME"])
    try:
        start_three_container_stack(
            baseline_env,
            baseline_root,
        )
        assert_running_backend_worker_images_match_build(baseline_env)
        provenance = capture_running_container_provenance(baseline_env)
        worker_baseline = capture_worker_container_state(baseline_env)
        case_b = _run_preview_and_submit(
            baseline_env,
            journey_key_prefix="bisect-t3-decimal",
            token=SESSION_TOKEN,
            upload_files_factory=_t3_decimal_upload_files,
            retry_upload_files_factory=_baseline_only_upload_files,
            worker_baseline=worker_baseline,
            expected_preview_failure_code="UNSUPPORTED_TABLE",
        )
        print(
            "case_b_prime_t3_decimal",
            json.dumps({k: v for k, v in case_b.items() if k != "worker_tail"}, indent=2),
        )
        assert case_b["failed_preview_status"] == "FAILED"
        assert case_b["failed_preview_diagnostic_code"] == "UNSUPPORTED_TABLE"
        assert "column scalar_type is not supported" in case_b["failed_preview_diagnostic_message"]
        assert case_b["preview_status"] == "SUCCEEDED"
        assert case_b["submit_status"] == "SUCCEEDED"
        assert case_b["failed_preview_operation_id"] != case_b["preview_operation_id"]
    finally:
        if provenance:
            normalized = normalize_running_images(provenance, baseline_env["COMPOSE_PROJECT_NAME"])
            provenance_path = persist_compose_gate_provenance(baseline_env, provenance)
            print(
                "ordered_bisect_gate_running_images="
                f"{json.dumps(normalized, indent=2)}"
            )
            print(f"compose gate provenance written to {provenance_path}")
        cleanup_compose_project_artifacts(baseline_env)

    ordered_root = tmp_path / "ordered-vocabulary"
    ordered_root.mkdir(parents=True, exist_ok=True)
    ordered_env = _compose_env(ordered_root, prefix="ordered-bisect-a")
    require_docker(compose_project_name=ordered_env["COMPOSE_PROJECT_NAME"])
    try:
        start_three_container_stack(
            ordered_env,
            ordered_root,
        )
        case_a = _run_preview_and_submit(
            ordered_env,
            journey_key_prefix="bisect-ordered-vocabulary",
            token=ACTOR2_TOKEN,
            upload_files_factory=lambda version: ordered_syx_vocabulary_upload_files(
                t_rows=(1,),
                before_ordered_rows=(),
                after_ordered_rows=((5, 1), (7, 2)),
                expected_version=version,
            ),
        )
        print(
            "case_a_prime_ordered_vocabulary",
            json.dumps({k: v for k, v in case_a.items() if k != "worker_tail"}, indent=2),
        )
        assert case_a["preview_status"] == "SUCCEEDED"
        assert case_a["submit_status"] == "SUCCEEDED"
    finally:
        cleanup_compose_project_artifacts(ordered_env)


def test_preview_worker_restart_takes_over_expired_running_operation(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path, prefix="preview-worker-restart")
    start_three_container_stack(env, tmp_path)

    initial_sql = (
        b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
        b"INSERT INTO t VALUES (1);\n"
    )
    modified_sql = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
        "INSERT INTO t VALUES "
        + ",".join(f"({index})" for index in range(50_000))
        + ";\n"
    ).encode("utf-8")

    try:
        with httpx.Client(
            base_url=BACKEND_URL,
            headers=compose_auth_headers(token=ACTOR2_TOKEN),
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
            upload = client.post(
                f"/v1/workspaces/{workspace_body['workspace_id']}/upload-revisions",
                headers=compose_auth_headers(
                    token=ACTOR2_TOKEN,
                    idempotency_key="preview-worker-restart-upload",
                ),
                files=upload_files(
                    expected_version=int(workspace_body["optimistic_version"]),
                    initial_bytes=pack_tar_gz({"sql/dbcfg.sql": initial_sql}),
                    modified_bytes=pack_tar_gz({"sql/dbcfg.sql": modified_sql}),
                ),
            )
            assert upload.status_code == 201, upload.text
            upload_body = upload.json()
            preview = client.post(
                f"/v1/workspaces/{workspace_body['workspace_id']}/preview-operations",
                headers=compose_auth_headers(
                    token=ACTOR2_TOKEN,
                    idempotency_key="preview-worker-restart-preview",
                ),
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
            operation_id = str(preview.json()["operation_id"])

            deadline = time.monotonic() + 30.0
            observed_running = False
            while time.monotonic() < deadline:
                operation = client.get(f"/v1/operations/{operation_id}")
                assert operation.status_code == 200, operation.text
                status = operation.json()["status"]
                if status == "RUNNING":
                    observed_running = True
                    break
                assert status not in {"SUCCEEDED", "FAILED", "CANCELLED"}, operation.text
                time.sleep(0.05)
            assert observed_running, "Preview never entered RUNNING before its worker was terminated"

            killed = run_compose(env, "kill", "--signal", "SIGKILL", "worker")
            assert killed.returncode == 0, f"worker kill failed: {killed.stderr}\n{killed.stdout}"
            restarted = run_compose(env, "up", "-d", "--no-deps", "worker")
            assert restarted.returncode == 0, (
                f"worker restart failed: {restarted.stderr}\n{restarted.stdout}"
            )
            terminal = poll_operation(client, operation_id, timeout_seconds=240.0)

            assert terminal["status"] == "SUCCEEDED", json.dumps(terminal, indent=2)
    finally:
        cleanup_compose_project_artifacts(env)
