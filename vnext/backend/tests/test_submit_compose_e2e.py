"""Three-container compose smoke for backend, worker, and repository-service."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    build_compose_stack_images,
    compose_project_name,
    require_docker,
    run_compose,
)
from tests.support.submit_job_harness import _repository_service_build_package_bytes
from tests.support.upload_http_packages import upload_files

pytestmark = [pytest.mark.integration, pytest.mark.serial]

SESSION_TOKEN = "compose-session-token"
BEARER_TOKEN = "compose-submit-bearer"
BASELINE_NODE_ID = "compose-node"
BASELINE_MANIFEST_DIGEST = "sha256:" + "a" * 64
BASELINE_REPLAY_SQL = b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
DEVICE_KEY = "compose-device"
PROJECT_ID = "compose-project"


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


def _auth_headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _wait_http_ok(url: str, *, timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(2.0)
    raise RuntimeError(f"endpoint did not become ready: {url}")


def _wait_repository_service_ready(env: dict[str, str], *, timeout_seconds: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    probe = (
        "import urllib.request; "
        "urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5.0)"
    )
    while time.monotonic() < deadline:
        result = run_compose(
            env,
            "exec",
            "-T",
            "repository-service",
            "python",
            "-c",
            probe,
        )
        if result.returncode == 0:
            return
        time.sleep(2.0)
    raise RuntimeError("repository-service did not become ready")


def _worker_ready(env: dict[str, str], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        logs = run_compose(env, "logs", "worker", "--no-color")
        if "code=worker_ready" in logs.stdout:
            return
        time.sleep(2.0)
    raise RuntimeError("worker did not emit worker_ready")


def _build_baseline_import_package() -> bytes:
    manifest: dict[str, object] = {
        "package_version": 1,
        "canonicalization_manifest_digest": BASELINE_MANIFEST_DIGEST,
        "tables": [
            {
                "name": "t",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 0,
            }
        ],
    }
    return _repository_service_build_package_bytes(manifest=manifest, replay_sql=BASELINE_REPLAY_SQL)


def _import_baseline_into_repository(
    env: dict[str, str],
    tmp_path: Path,
    *,
    repository_id: str,
    expected_commit_id: str,
) -> str:
    package_path = tmp_path / "baseline-import.tar.zst"
    package_path.write_bytes(_build_baseline_import_package())
    container_id = run_compose(
        env,
        "ps",
        "repository-service",
        "--format",
        "{{.ID}}",
    ).stdout.strip()
    if not container_id:
        pytest.fail("repository-service container is not running for baseline import")
    copy = subprocess.run(
        ["docker", "cp", str(package_path), f"{container_id}:/tmp/baseline-import.tar.zst"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if copy.returncode != 0:
        pytest.fail(f"failed to copy baseline import package: {copy.stderr}\n{copy.stdout}")
    script = f"""
import json, time, urllib.request, hashlib
base = "http://127.0.0.1:8000"
repo_id = "{repository_id}"
expected_commit = "{expected_commit_id}"
token = "{BEARER_TOKEN}"
payload = open("/tmp/baseline-import.tar.zst", "rb").read()
digest = hashlib.sha256(payload).hexdigest()
upload_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/artifacts",
    data=payload,
    method="POST",
    headers={{
        "Authorization": f"Bearer {{token}}",
        "Idempotency-Key": "compose-baseline-artifact",
        "Content-Type": "application/vnd.gateway.repository-import.v1+tar+zstd",
        "Content-Length": str(len(payload)),
        "X-Artifact-SHA256": digest,
    }},
)
with urllib.request.urlopen(upload_req, timeout=60) as response:
    uploaded = json.loads(response.read().decode())
artifact = uploaded["artifact_ref"]
import_body = json.dumps({{
    "repository_id": repo_id,
    "artifact_ref": {{
        "artifact_id": artifact["artifact_id"],
        "media_type": artifact["media_type"],
        "size_bytes": artifact["size_bytes"],
        "raw_sha256": artifact["raw_sha256"],
    }},
    "target_ref": "main",
    "expected_commit_id": expected_commit,
    "verification_policy": "STRUCTURAL",
    "unknown_type_policy": "REJECT",
}}).encode()
import_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/versioned/imports",
    data=import_body,
    method="POST",
    headers={{
        "Authorization": f"Bearer {{token}}",
        "Idempotency-Key": "compose-baseline-import",
        "Content-Type": "application/json",
    }},
)
with urllib.request.urlopen(import_req, timeout=60) as response:
    operation = json.loads(response.read().decode())
operation_id = operation["operation_id"]
deadline = time.monotonic() + 120.0
while time.monotonic() < deadline:
    poll_req = urllib.request.Request(
        f"{{base}}/v1/repositories/{{repo_id}}/operations/{{operation_id}}",
        headers={{"Authorization": f"Bearer {{token}}"}},
    )
    with urllib.request.urlopen(poll_req, timeout=30) as response:
        body = json.loads(response.read().decode())
    operation = body["operation"]
    if operation["status"] in {{"SUCCEEDED", "FAILED", "CANCELLED"}}:
        if operation["status"] != "SUCCEEDED":
            raise RuntimeError(operation)
        break
    time.sleep(1.0)
else:
    raise RuntimeError("baseline import timed out")
resolve_req = urllib.request.Request(
    f"{{base}}/v1/repositories/{{repo_id}}/versioned/refs/main",
    headers={{"Authorization": f"Bearer {{token}}"}},
)
with urllib.request.urlopen(resolve_req, timeout=30) as response:
    resolved = json.loads(response.read().decode())
print(resolved["commit_id"])
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"baseline import failed: {result.stderr}\n{result.stdout}")
    commit_id = result.stdout.strip()
    if not commit_id:
        pytest.fail("baseline import did not return commit_id")
    return commit_id


def _seed_repository_and_mapping(env: dict[str, str], tmp_path: Path) -> tuple[str, str]:
    script = (
        "import json, urllib.request; "
        "req = urllib.request.Request("
        "'http://127.0.0.1:8000/v1/repositories', "
        "method='POST', "
        f"headers={{'Authorization': 'Bearer {BEARER_TOKEN}', 'Idempotency-Key': 'compose-seed-repo'}}); "
        "print(urllib.request.urlopen(req, timeout=30.0).read().decode())"
    )
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"repository seed failed: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip())
    repository_id = str(payload["repository_id"])
    initial_commit_id = str(payload["initial_commit_id"])
    baseline_commit_id = _import_baseline_into_repository(
        env,
        tmp_path,
        repository_id=repository_id,
        expected_commit_id=initial_commit_id,
    )
    mapping_path = Path(env["GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE"])
    mapping_path.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": DEVICE_KEY,
                        "business_project_id": PROJECT_ID,
                        "repository_id": repository_id,
                        "business_baseline_node_id": BASELINE_NODE_ID,
                        "business_baseline_commit_id": baseline_commit_id,
                        "baseline_head_version": 0,
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return repository_id, baseline_commit_id


def _start_three_container_stack(env: dict[str, str], tmp_path: Path) -> tuple[str, str]:
    build_compose_stack_images(env)
    up_repo = run_compose(env, "up", "-d", "--no-build", "repository-service")
    if up_repo.returncode != 0:
        pytest.fail(f"compose up repository-service failed: {up_repo.stderr}\n{up_repo.stdout}")
    _wait_repository_service_ready(env)
    repository_id, initial_commit_id = _seed_repository_and_mapping(env, tmp_path)
    up_stack = run_compose(env, "up", "-d", "--no-build", "backend", "worker")
    if up_stack.returncode != 0:
        pytest.fail(f"compose up backend/worker failed: {up_stack.stderr}\n{up_stack.stdout}")
    _wait_http_ok(f"{BACKEND_URL}/readyz")
    _worker_ready(env)
    return repository_id, initial_commit_id


def _poll_operation(
    client: httpx.Client,
    operation_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/v1/operations/{operation_id}")
        if response.status_code != 200:
            time.sleep(2.0)
            continue
        body = response.json()
        if body["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return cast(dict[str, Any], body)
        time.sleep(2.0)
    raise RuntimeError(f"operation did not reach terminal status: {operation_id}")


def _read_workspace_row(env: dict[str, str], workspace_id: str) -> dict[str, Any]:
    script = (
        "import json, sqlite3, sys; "
        "conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3'); "
        "row = conn.execute("
        "'SELECT optimistic_version, generation, current_preview_result_id "
        "FROM workspace_records WHERE workspace_id = ?', "
        f"('{workspace_id}',)"
        ").fetchone(); "
        "sys.stdout.write(json.dumps("
        "{'optimistic_version': row[0], 'generation': row[1], 'current_preview_result_id': row[2]} "
        "if row else {})"
        ")"
    )
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to read workspace row: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "{}")
    if not payload.get("current_preview_result_id"):
        pytest.fail("workspace current_preview_result_id is empty after preview")
    return cast(dict[str, Any], payload)


def _poll_submit_attempt(
    client: httpx.Client,
    workspace_id: str,
    submit_attempt_id: str,
    *,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(
            f"/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}",
        )
        if response.status_code != 200:
            time.sleep(2.0)
            continue
        body = response.json()
        if body["state"] in {"FINALIZED", "ABORTED"}:
            return cast(dict[str, Any], body)
        time.sleep(2.0)
    raise RuntimeError(f"submit attempt did not reach terminal state: {submit_attempt_id}")


def _run_accept_to_submission_read_journey(
    env: dict[str, str],
    *,
    initial_commit_id: str,
) -> dict[str, Any]:
    with httpx.Client(base_url=BACKEND_URL, headers=_auth_headers(), timeout=60.0) as client:
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

        upload = client.post(
            f"/v1/workspaces/{workspace_id}/upload-revisions",
            headers=_auth_headers(idempotency_key="compose-upload"),
            files=upload_files(expected_version=workspace_body["optimistic_version"]),
        )
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()

        preview = client.post(
            f"/v1/workspaces/{workspace_id}/preview-operations",
            headers=_auth_headers(idempotency_key="compose-preview"),
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
        preview_operation = preview.json()
        preview_terminal = _poll_operation(client, preview_operation["operation_id"])
        assert preview_terminal["status"] == "SUCCEEDED", preview_terminal

        workspace_row = _read_workspace_row(env, workspace_id)
        preview_result_id = str(workspace_row["current_preview_result_id"])
        preview_read = client.get(
            f"/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}",
        )
        assert preview_read.status_code == 200, preview_read.text
        assert preview_read.json()["business_baseline_commit_id"] == initial_commit_id

        accepted = client.post(
            f"/v1/workspaces/{workspace_id}/submit-attempts",
            headers=_auth_headers(idempotency_key="compose-submit"),
            json={
                "expected_workspace_version": workspace_row["optimistic_version"],
                "upload_revision_id": upload_body["upload_revision_id"],
                "preview_result_id": preview_result_id,
                "generation": workspace_row["generation"],
                "expected_baseline_node_id": BASELINE_NODE_ID,
                "expected_baseline_head_version": 0,
                "options": {},
            },
        )
        assert accepted.status_code == 202, accepted.text
        accepted_body = accepted.json()
        submit_operation = _poll_operation(client, accepted_body["operation_id"])
        assert submit_operation["status"] == "SUCCEEDED", submit_operation

        attempt = _poll_submit_attempt(
            client,
            workspace_id,
            accepted_body["submit_attempt_id"],
        )
        assert attempt["state"] == "FINALIZED", attempt
        assert attempt.get("submission_id")

        submission = client.get(
            f"/v1/workspaces/{workspace_id}/submissions/{attempt['submission_id']}",
        )
        assert submission.status_code == 200, submission.text
        submission_body = submission.json()
        assert submission_body["submit_attempt_id"] == accepted_body["submit_attempt_id"]
        assert BEARER_TOKEN not in submission.text
        assert SESSION_TOKEN not in submission.text
        return {
            "workspace_id": workspace_id,
            "submit_attempt_id": accepted_body["submit_attempt_id"],
            "submission_id": attempt["submission_id"],
            "preview_result_id": preview_result_id,
        }


def test_compose_three_process_submit_stack_smoke_and_backend_restart(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    _start_three_container_stack(env, tmp_path)

    try:
        health = urllib.request.urlopen(f"{BACKEND_URL}/healthz", timeout=5.0)
        ready = urllib.request.urlopen(f"{BACKEND_URL}/readyz", timeout=5.0)
        assert health.status == 200
        assert ready.status == 200
        assert BEARER_TOKEN not in health.read().decode("utf-8")

        restart = run_compose(env, "restart", "backend")
        if restart.returncode != 0:
            pytest.fail(f"compose restart backend failed: {restart.stderr}\n{restart.stdout}")
        _wait_http_ok(f"{BACKEND_URL}/readyz")

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
    _repository_id, initial_commit_id = _start_three_container_stack(env, tmp_path)

    try:
        journey = _run_accept_to_submission_read_journey(
            env,
            initial_commit_id=initial_commit_id,
        )
        assert journey["submission_id"]
        assert journey["preview_result_id"].startswith("pr-")
    finally:
        down = run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
