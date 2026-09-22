"""Shared helpers for backend compose integration gates."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from tests.support.submit_job_harness import _repository_service_build_package_bytes
from tests.support.upload_http_packages import upload_files

VNEXT_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = VNEXT_ROOT / "deploy"
COMPOSE_FILE = DEPLOY_ROOT / "compose.yaml"
BUILD_REPOSITORY_SCRIPT = VNEXT_ROOT / "scripts" / "build-repository-service-image.sh"
BACKEND_URL = "http://127.0.0.1:8000"
GATE_PROJECT_ENV = "GATEWAY_COMPOSE_GATE_PROJECT_NAME"
PREBUILT_ENV = "GATEWAY_COMPOSE_GATE_PREBUILT"
COMPOSE_GATE_PROVENANCE_PATH = (
    Path(__file__).resolve().parent / ".last_compose_gate_provenance.json"
)


def require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for compose e2e gate")


def compose_project_name(tmp_path: Path, *, default_prefix: str) -> str:
    fixed = os.environ.get(GATE_PROJECT_ENV, "").strip()
    if fixed:
        return fixed
    return f"{default_prefix}-{tmp_path.name}"


def repository_service_image() -> str:
    return os.environ.get("GATEWAY_REPOSITORY_SERVICE_IMAGE", "gateway-repository-service:local")


def compose_gate_prebuilt() -> bool:
    return os.environ.get(PREBUILT_ENV, "").strip() in {"1", "true", "yes"}


def run_compose(env: dict[str, str], *args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=DEPLOY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def ensure_repository_service_image() -> None:
    image = repository_service_image()
    inspect = subprocess.run(
        ["docker", "image", "inspect", image],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if inspect.returncode == 0:
        return
    if not BUILD_REPOSITORY_SCRIPT.is_file():
        pytest.fail(f"missing repository-service build script: {BUILD_REPOSITORY_SCRIPT}")
    completed = subprocess.run(
        [str(BUILD_REPOSITORY_SCRIPT)],
        cwd=VNEXT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=1800.0,
    )
    if completed.returncode != 0:
        pytest.fail(
            "repository-service image build failed; "
            f"stdout={completed.stdout[-500:]} stderr={completed.stderr[-500:]}"
        )


def build_compose_stack_images(env: dict[str, str]) -> None:
    ensure_repository_service_image()
    if compose_gate_prebuilt():
        return
    build = run_compose(env, "build", "backend", "worker")
    if build.returncode != 0:
        pytest.fail(f"compose backend/worker build failed: {build.stderr}\n{build.stdout}")


def build_backend_image(env: dict[str, str]) -> None:
    ensure_repository_service_image()
    if compose_gate_prebuilt():
        return
    build = run_compose(env, "build", "backend")
    if build.returncode != 0:
        pytest.fail(f"backend image build failed: {build.stderr}\n{build.stdout}")


def _inspect_image(image_ref: str) -> dict[str, Any]:
    completed = subprocess.run(
        ["docker", "image", "inspect", image_ref],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if completed.returncode != 0:
        return {"image_ref": image_ref, "missing": True}
    payload = json.loads(completed.stdout)
    image = payload[0]
    return {
        "image_ref": image_ref,
        "id": image.get("Id"),
        "labels": image.get("Config", {}).get("Labels", {}),
    }


def compose_image_ids(env: dict[str, str]) -> dict[str, dict[str, Any]]:
    project = env["COMPOSE_PROJECT_NAME"]
    repo_image = repository_service_image()
    return {
        "repository_service": _inspect_image(repo_image),
        "backend": _inspect_image(f"{project}-backend"),
        "worker": _inspect_image(f"{project}-worker"),
    }


def wait_http_ok(url: str, *, timeout_seconds: float = 180.0) -> None:
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(2.0)
    raise RuntimeError(f"endpoint did not become ready: {url}")


def resolve_main_commit_id(
    env: dict[str, str],
    repository_id: str,
    *,
    bearer_token: str,
) -> str:
    script = f"""
import json, time, urllib.error, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/repositories/{repository_id}/versioned/refs/main",
    headers={{"Authorization": "Bearer {bearer_token}"}},
)
for attempt in range(15):
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print(json.loads(response.read().decode())["commit_id"])
            break
    except urllib.error.HTTPError as exc:
        if exc.code == 503 and attempt < 14:
            time.sleep(2.0)
            continue
        raise
else:
    raise RuntimeError("repository main resolve timed out")
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to resolve repository main ref: {result.stderr}\n{result.stdout}")
    commit_id = result.stdout.strip()
    if not commit_id:
        pytest.fail("repository main resolve returned empty commit_id")
    return commit_id


def list_repository_commit_ids(
    env: dict[str, str],
    repository_id: str,
    *,
    bearer_token: str,
) -> set[str]:
    script = f"""
import json, os, re, subprocess, uuid
repo_hex = uuid.UUID("{repository_id}").hex
repo_path = f"/var/lib/gateway/repository/versioned/{{repo_hex}}"
pager_env = {{
    **os.environ,
    "PAGER": "",
    "GIT_PAGER": "",
    "NO_COLOR": "1",
    "DOLT_CLI_NO_COLOR": "1",
}}
log = subprocess.run(
    ["dolt", "log", "-n", "200", "--oneline", "--decorate=no"],
    cwd=repo_path,
    check=False,
    capture_output=True,
    text=True,
    env=pager_env,
)
if log.returncode != 0:
    raise RuntimeError(log.stderr or log.stdout)
ansi = re.compile(r"\\x1b\\[[0-9;]*m")
commits = [
    ansi.sub("", line.split()[0])
    for line in log.stdout.splitlines()
    if line.strip()
]
print(json.dumps(sorted(commits)))
"""
    result = run_compose(env, "exec", "-T", "repository-service", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to list repository commits: {result.stderr}\n{result.stdout}")
    payload = json.loads(result.stdout.strip() or "[]")
    return set(str(item) for item in payload)


def count_backend_operations(env: dict[str, str]) -> int:
    script = (
        "import sqlite3; "
        "conn = sqlite3.connect('/var/lib/gateway/control/control.sqlite3'); "
        "print(conn.execute('SELECT COUNT(*) FROM operation_records').fetchone()[0])"
    )
    result = run_compose(env, "exec", "-T", "backend", "python", "-c", script)
    if result.returncode != 0:
        pytest.fail(f"failed to count operations: {result.stderr}\n{result.stdout}")
    return int(result.stdout.strip())


def _inspect_container_image_id(container_id: str) -> str:
    completed = subprocess.run(
        ["docker", "inspect", "--format", "{{.Image}}", container_id],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"docker inspect failed for {container_id}: "
            f"{completed.stderr}\n{completed.stdout}"
        )
    image_id = completed.stdout.strip()
    if not image_id.startswith("sha256:"):
        pytest.fail(f"expected immutable image id for {container_id}, got {image_id!r}")
    return image_id


def capture_running_container_provenance(env: dict[str, str]) -> dict[str, dict[str, str]]:
    result = run_compose(
        env,
        "ps",
        "--format",
        "{{.Name}}\t{{.ID}}",
    )
    if result.returncode != 0:
        pytest.fail(f"compose ps failed: {result.stderr}\n{result.stdout}")
    captured: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        name, container_id = line.split("\t", 1)
        captured[name] = {
            "container_id": container_id,
            "image": _inspect_container_image_id(container_id),
        }
    return captured


def persist_compose_gate_provenance(
    env: dict[str, str],
    provenance: dict[str, dict[str, str]],
) -> Path:
    payload = {
        "compose_project_name": env["COMPOSE_PROJECT_NAME"],
        "containers": provenance,
    }
    COMPOSE_GATE_PROVENANCE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return COMPOSE_GATE_PROVENANCE_PATH


def assert_running_backend_worker_images_match_build(env: dict[str, str]) -> None:
    built = compose_image_ids(env)
    running = capture_running_container_provenance(env)
    project = env["COMPOSE_PROJECT_NAME"]
    for service in ("backend", "worker"):
        running_key = f"{project}-{service}-1"
        running_image = running.get(running_key, {}).get("image")
        built_image = built[service].get("id")
        if running_image is None or built_image is None:
            pytest.fail(f"missing running or built image for {service}")
        if running_image != built_image:
            pytest.fail(
                f"running image for {service} does not match fresh build: "
                f"{running_image} != {built_image}"
            )


SESSION_TOKEN = "compose-session-token"
BEARER_TOKEN = "compose-submit-bearer"
BASELINE_NODE_ID = "compose-node"
BASELINE_MANIFEST_DIGEST = "sha256:" + "a" * 64
BASELINE_REPLAY_SQL = b"CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
DEVICE_KEY = "compose-device"
PROJECT_ID = "compose-project"


def compose_auth_headers(
    *,
    token: str = SESSION_TOKEN,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def wait_repository_service_ready(env: dict[str, str], *, timeout_seconds: float = 180.0) -> None:
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


def worker_ready(env: dict[str, str], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        logs = run_compose(env, "logs", "worker", "--no-color")
        if "code=worker_ready" in logs.stdout:
            return
        time.sleep(2.0)
    raise RuntimeError("worker did not emit worker_ready")


def build_baseline_import_package() -> bytes:
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


def import_baseline_into_repository(
    env: dict[str, str],
    tmp_path: Path,
    *,
    repository_id: str,
    expected_commit_id: str,
) -> str:
    package_path = tmp_path / "baseline-import.tar.zst"
    package_path.write_bytes(build_baseline_import_package())
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


def seed_repository_and_mapping(env: dict[str, str], tmp_path: Path) -> tuple[str, str]:
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
    baseline_commit_id = import_baseline_into_repository(
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


def start_three_container_stack(env: dict[str, str], tmp_path: Path) -> tuple[str, str]:
    build_compose_stack_images(env)
    up_repo = run_compose(env, "up", "-d", "--no-build", "repository-service")
    if up_repo.returncode != 0:
        pytest.fail(f"compose up repository-service failed: {up_repo.stderr}\n{up_repo.stdout}")
    wait_repository_service_ready(env)
    repository_id, initial_commit_id = seed_repository_and_mapping(env, tmp_path)
    up_stack = run_compose(env, "up", "-d", "--no-build", "backend", "worker")
    if up_stack.returncode != 0:
        pytest.fail(f"compose up backend/worker failed: {up_stack.stderr}\n{up_stack.stdout}")
    wait_http_ok(f"{BACKEND_URL}/readyz")
    worker_ready(env)
    return repository_id, initial_commit_id


def poll_operation(
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


def read_workspace_row(env: dict[str, str], workspace_id: str) -> dict[str, Any]:
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


def poll_submit_attempt(
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


def run_accept_to_submission_read_journey(
    env: dict[str, str],
    *,
    initial_commit_id: str,
    journey_key_prefix: str = "compose",
    token: str = SESSION_TOKEN,
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

        upload = client.post(
            f"/v1/workspaces/{workspace_id}/upload-revisions",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-upload"),
            files=upload_files(expected_version=workspace_body["optimistic_version"]),
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
        preview_operation = preview.json()
        preview_terminal = poll_operation(client, preview_operation["operation_id"])
        assert preview_terminal["status"] == "SUCCEEDED", preview_terminal

        workspace_row = read_workspace_row(env, workspace_id)
        preview_result_id = str(workspace_row["current_preview_result_id"])
        preview_read = client.get(
            f"/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}",
        )
        assert preview_read.status_code == 200, preview_read.text
        assert preview_read.json()["business_baseline_commit_id"] == initial_commit_id

        accepted = client.post(
            f"/v1/workspaces/{workspace_id}/submit-attempts",
            headers=compose_auth_headers(token=token, idempotency_key=f"{journey_key_prefix}-submit"),
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
        submit_operation = poll_operation(client, accepted_body["operation_id"])
        assert submit_operation["status"] == "SUCCEEDED", submit_operation

        attempt = poll_submit_attempt(
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
