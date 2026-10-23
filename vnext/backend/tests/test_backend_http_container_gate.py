"""Backend image build and container entrypoint gate for http_server bootstrap."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.support.compose_gate_harness import (
    BACKEND_URL,
    build_backend_image,
    capture_running_container_provenance,
    compose_image_ids,
    compose_project_name,
    ensure_repository_service_image,
    persist_compose_gate_provenance,
    require_docker,
    run_compose,
)
from tests.support.container_input_files import write_container_readable_text

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def _compose_env(tmp_path: Path) -> dict[str, str]:
    bearer = tmp_path / "repository-bearer-token"
    write_container_readable_text(bearer, "container-gate-bearer\n", encoding="utf-8")
    session = tmp_path / "session.json"
    write_container_readable_text(
        session,
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
    write_container_readable_text(internal_bearer, "container-gate-internal\n", encoding="utf-8")
    mapping = tmp_path / "provisioned-mapping.json"
    write_container_readable_text(
        mapping,
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
            "GATEWAY_REPOSITORY_SERVICE_IMAGE": os.environ.get(
                "GATEWAY_REPOSITORY_SERVICE_IMAGE",
                "gateway-repository-service:local",
            ),
            "COMPOSE_PROJECT_NAME": compose_project_name(tmp_path, default_prefix="gateway-backend-gate"),
        }
    )
    return env


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
    require_docker()
    env = _compose_env(tmp_path)
    build_backend_image(env)

    image_ref = f"{env['COMPOSE_PROJECT_NAME']}-backend"
    config = subprocess.run(
        ["docker", "inspect", image_ref, "--format", "{{json .Config.Cmd}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert config.stdout.strip() == '["python","-m","gateway_backend.bootstrap.http_server"]'


def test_backend_container_ready_and_stops_cleanly_with_repository_service(tmp_path: Path) -> None:
    require_docker()
    env = _compose_env(tmp_path)
    ensure_repository_service_image()
    build_backend_image(env)

    up_repo = run_compose(env, "up", "-d", "--no-build", "repository-service")
    if up_repo.returncode != 0:
        pytest.fail(f"compose up repository-service failed: {up_repo.stderr}\n{up_repo.stdout}")

    up_backend = run_compose(env, "up", "-d", "--no-build", "backend")
    if up_backend.returncode != 0:
        pytest.fail(f"compose up backend failed: {up_backend.stderr}\n{up_backend.stdout}")

    try:
        _wait_http_ok(f"{BACKEND_URL}/readyz")
        running = capture_running_container_provenance(env)
        built = compose_image_ids(env)
        backend_project = f"{env['COMPOSE_PROJECT_NAME']}-backend-1"
        backend_running = running.get(backend_project, {}).get("image")
        backend_built = built["backend"].get("id")
        if backend_running is None or backend_built is None:
            pytest.fail("container gate missing backend running or built image id")
        if backend_running != backend_built:
            pytest.fail(
                "running backend image does not match fresh gate build: "
                f"{backend_running} != {backend_built}"
            )
        persist_compose_gate_provenance(env, running)
        stop = run_compose(env, "stop", "-t", "5", "backend")
        if stop.returncode != 0:
            pytest.fail(f"compose stop backend failed: {stop.stderr}\n{stop.stdout}")
        status = run_compose(env, "ps", "backend", "--status", "exited", "--format", "{{.State}}")
        assert status.returncode == 0
        assert "exited" in status.stdout.lower()
    finally:
        run_compose(env, "down", "-v", "--remove-orphans")
