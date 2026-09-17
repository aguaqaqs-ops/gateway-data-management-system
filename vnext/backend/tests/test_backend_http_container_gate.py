"""Backend image build and container entrypoint gate for http_server bootstrap."""

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
        pytest.skip("docker is required for backend container gate")


def _compose_env(tmp_path: Path) -> dict[str, str]:
    bearer = tmp_path / "repository-bearer-token"
    bearer.write_text("container-gate-bearer\n", encoding="utf-8")
    session = tmp_path / "session.json"
    session.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "token": "container-gate-session",
                        "actor_id": "container-gate-actor",
                        "gateway_device_external_key": "container-device",
                        "business_project_id": "container-project",
                        "permissions": ["workspace_read"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    internal_bearer = tmp_path / "internal-bearer-token"
    internal_bearer.write_text("container-gate-internal\n", encoding="utf-8")
    mapping = tmp_path / "provisioned-mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "gateway_device_external_key": "container-device",
                        "business_project_id": "container-project",
                        "repository_id": "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
                        "business_baseline_node_id": "container-node",
                        "business_baseline_commit_id": "container-commit",
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
            "COMPOSE_PROJECT_NAME": f"gateway-backend-gate-{tmp_path.name}",
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


def _wait_http_ok(url: str, *, timeout_seconds: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, ConnectionResetError):
            time.sleep(2.0)
    raise RuntimeError(f"endpoint did not become ready: {url}")


def test_backend_image_builds_with_http_server_entrypoint(tmp_path: Path) -> None:
    _require_docker()
    env = _compose_env(tmp_path)
    build = _run_compose(env, "build", "backend")
    if build.returncode != 0:
        pytest.fail(f"backend image build failed: {build.stderr}\n{build.stdout}")

    image_ref = f"{env['COMPOSE_PROJECT_NAME']}-backend"
    config = subprocess.run(
        ["docker", "inspect", image_ref, "--format", "{{json .Config.Cmd}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert config.stdout.strip() == '["python","-m","gateway_backend.bootstrap.http_server"]'


def test_backend_container_ready_and_stops_cleanly_with_repository_service(tmp_path: Path) -> None:
    _require_docker()
    env = _compose_env(tmp_path)
    repository_build = _run_compose(env, "build", "repository-service")
    if repository_build.returncode != 0:
        pytest.skip(
            "repository-service build unavailable for backend container readiness gate: "
            f"{repository_build.stderr[:200]}"
        )

    backend_build = _run_compose(env, "build", "backend")
    if backend_build.returncode != 0:
        pytest.fail(f"backend image build failed: {backend_build.stderr}\n{backend_build.stdout}")

    up = _run_compose(env, "up", "-d", "repository-service", "backend")
    if up.returncode != 0:
        pytest.fail(f"compose up failed: {up.stderr}\n{up.stdout}")

    try:
        _wait_http_ok(f"{BACKEND_URL}/readyz")
        stop = _run_compose(env, "stop", "-t", "5", "backend")
        if stop.returncode != 0:
            pytest.fail(f"compose stop backend failed: {stop.stderr}\n{stop.stdout}")
        status = _run_compose(env, "ps", "backend", "--status", "exited", "--format", "{{.State}}")
        assert status.returncode == 0
        assert "exited" in status.stdout.lower()
    finally:
        _run_compose(env, "down", "-v", "--remove-orphans")
