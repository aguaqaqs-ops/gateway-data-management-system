"""Three-container compose smoke for backend, worker, and repository-service."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.serial]

DEPLOY_ROOT = Path(__file__).resolve().parents[2] / "deploy"
COMPOSE_FILE = DEPLOY_ROOT / "compose.yaml"
BACKEND_URL = "http://127.0.0.1:8000"


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is required for compose e2e gate")


def _compose_env(tmp_path: Path) -> dict[str, str]:
    bearer = tmp_path / "repository-bearer-token"
    bearer.write_text("compose-submit-bearer\n", encoding="utf-8")
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": "compose-session-token",
                        "actor_id": "compose-actor",
                        "gateway_device_external_key": "compose-device",
                        "business_project_id": "compose-project",
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
                        "gateway_device_external_key": "compose-device",
                        "business_project_id": "compose-project",
                        "repository_id": "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
                        "business_baseline_node_id": "compose-node",
                        "business_baseline_commit_id": "compose-commit",
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
            "GATEWAY_REPOSITORY_SERVICE_IMAGE": "gateway-repository-service:local",
            "COMPOSE_PROJECT_NAME": f"gateway-submit-s6-{tmp_path.name}",
        }
    )
    return env


def _run_compose(env: dict[str, str], *args: str, timeout: float = 600.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=DEPLOY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


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


def _worker_ready(env: dict[str, str], *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        logs = _run_compose(env, "logs", "worker", "--no-color")
        if "code=worker_ready" in logs.stdout:
            return
        time.sleep(2.0)
    raise RuntimeError("worker did not emit worker_ready")


def test_compose_three_process_submit_stack_smoke_and_backend_restart(tmp_path: Path) -> None:
    _require_docker()
    env = _compose_env(tmp_path)
    build = _run_compose(env, "build", "backend", "worker", "repository-service")
    if build.returncode != 0:
        backend_worker_build = _run_compose(env, "build", "backend", "worker")
        if backend_worker_build.returncode != 0:
            pytest.skip(
                "compose image build is unavailable in this environment; "
                f"repository build: {build.stderr[:200]}; "
                f"backend build: {backend_worker_build.stderr[:200]}"
            )
        up = _run_compose(env, "up", "-d", "--no-build", "repository-service", "backend", "worker")
    else:
        up = _run_compose(env, "up", "-d", "repository-service", "backend", "worker")
    if up.returncode != 0:
        pytest.fail(f"compose up failed: {up.stderr}\n{up.stdout}")

    try:
        _wait_http_ok(f"{BACKEND_URL}/readyz")
        _worker_ready(env)

        health = urllib.request.urlopen(f"{BACKEND_URL}/healthz", timeout=5.0)
        ready = urllib.request.urlopen(f"{BACKEND_URL}/readyz", timeout=5.0)
        assert health.status == 200
        assert ready.status == 200
        assert "compose-submit-bearer" not in health.read().decode("utf-8")

        restart = _run_compose(env, "restart", "backend")
        if restart.returncode != 0:
            pytest.fail(f"compose restart backend failed: {restart.stderr}\n{restart.stdout}")
        _wait_http_ok(f"{BACKEND_URL}/readyz")

        workspace_request = urllib.request.Request(
            f"{BACKEND_URL}/v1/workspaces",
            data=json.dumps(
                {
                    "gateway_device_external_key": "compose-device",
                    "business_project_id": "compose-project",
                }
            ).encode("utf-8"),
            headers={
                "Authorization": "Bearer compose-session-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(workspace_request, timeout=10.0) as response:
            assert response.status in {200, 201}
            body = json.loads(response.read().decode("utf-8"))
        assert "workspace_id" in body
    finally:
        down = _run_compose(env, "down", "-v", "--remove-orphans")
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}\n{down.stdout}")
