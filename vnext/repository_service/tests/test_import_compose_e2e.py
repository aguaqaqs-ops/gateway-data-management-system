"""Production Compose end-to-end tests for Versioned import delivery."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

from support.compose_build_harness import ensure_repository_service_image
from support.import_admission_crash_harness import build_import_package_bytes
from test_import_package import write_artifact

REPO_ROOT = Path(__file__).resolve().parents[3]
VNEXT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = VNEXT_ROOT / "deploy" / "compose.yaml"
RUNNER = Path(__file__).resolve().parent / "support" / "import_compose_http_runner.py"


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _docker_objects(project: str, kind: str) -> list[str]:
    command = ["docker", kind, "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"]
    if kind == "container":
        command.insert(3, "-a")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"docker {kind} ls failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def _cleanup_compose(project: str, env: dict[str, str]) -> None:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(COMPOSE_FILE),
            "--profile",
            "p2-r2",
            "down",
            "-v",
            "--remove-orphans",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"docker compose down failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    assert _docker_objects(project, "container") == []
    assert _docker_objects(project, "network") == []
    assert _docker_objects(project, "volume") == []


def _wait_healthy(container_id: str, *, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        completed = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode == 0 and completed.stdout.strip() == "healthy":
            return
        time.sleep(2.0)
    raise TimeoutError(f"container {container_id} did not become healthy")


def _container_token_path() -> str:
    return "/run/secrets/repository-bearer-token"


@pytest.mark.integration
@pytest.mark.serial
def test_compose_repository_service_import_restart_replay(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker is required for compose e2e gate")

    project = f"gateway-p2r4-s10-{uuid4().hex[:12]}"
    token_file = tmp_path / "repository-bearer-token"
    token_file.write_text("compose-e2e-bearer-token", encoding="utf-8")
    token_file.chmod(0o400)
    payload_path = tmp_path / "import-package.tar.zst"
    size_bytes, _ = write_artifact(payload_path, build_import_package_bytes())
    assert size_bytes > 0
    state_path = tmp_path / "compose-state.json"
    runner_in_container = "/tmp/import_compose_http_runner.py"
    payload_in_container = "/tmp/import-package.tar.zst"
    state_in_container = "/tmp/compose-state.json"

    env = os.environ.copy()
    env["GATEWAY_P2R2_BEARER_TOKEN_FILE"] = str(token_file)
    service_image = ensure_repository_service_image()
    env["GATEWAY_REPOSITORY_SERVICE_IMAGE"] = service_image

    try:
        _run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(COMPOSE_FILE),
                "--profile",
                "p2-r2",
                "config",
            ],
            env=env,
        )
        image = service_image
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if inspect.returncode != 0:
            raise RuntimeError(f"prebuilt image not present after cache build: {image}")
        gateway_uid = int(
            _run(["docker", "run", "--rm", "--entrypoint", "id", image, "-u", "gateway"]).stdout.strip()
        )
        gateway_gid = int(
            _run(["docker", "run", "--rm", "--entrypoint", "id", image, "-g", "gateway"]).stdout.strip()
        )
        os.chown(token_file, gateway_uid, gateway_gid)

        _run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(COMPOSE_FILE),
                "--profile",
                "p2-r2",
                "up",
                "-d",
                "--no-build",
                "repository-service",
            ],
            env=env,
        )
        container_id = _run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(COMPOSE_FILE),
                "--profile",
                "p2-r2",
                "ps",
                "-q",
                "repository-service",
            ],
            env=env,
        ).stdout.strip()
        assert container_id
        _wait_healthy(container_id)
        mkdir_probe = subprocess.run(
            [
                "docker",
                "exec",
                "-u",
                "gateway",
                container_id,
                "mkdir",
                "/var/lib/gateway/repository/artifacts/.gateway-write-probe",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert mkdir_probe.returncode == 0
        _run(
            [
                "docker",
                "exec",
                "-u",
                "gateway",
                container_id,
                "rmdir",
                "/var/lib/gateway/repository/artifacts/.gateway-write-probe",
            ]
        )

        _run(["docker", "cp", str(RUNNER), f"{container_id}:{runner_in_container}"])
        _run(["docker", "cp", str(payload_path), f"{container_id}:{payload_in_container}"])

        flow = _run(
            [
                "docker",
                "exec",
                container_id,
                "python",
                runner_in_container,
                "flow",
                "--token-file",
                _container_token_path(),
                "--payload-path",
                payload_in_container,
                "--idempotency-prefix",
                project,
            ]
        )
        state_path.write_text(flow.stdout.strip(), encoding="utf-8")
        _run(["docker", "cp", str(state_path), f"{container_id}:{state_in_container}"])

        _run(
            [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(COMPOSE_FILE),
                "--profile",
                "p2-r2",
                "restart",
                "repository-service",
            ],
            env=env,
        )
        _wait_healthy(container_id)

        verify = _run(
            [
                "docker",
                "exec",
                container_id,
                "python",
                runner_in_container,
                "verify",
                "--token-file",
                _container_token_path(),
                "--state-path",
                state_in_container,
                "--idempotency-prefix",
                project,
            ]
        )
        verify_body = json.loads(verify.stdout.strip())
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert verify_body["operation_id"] == saved["operation_id"]
        assert verify_body["status"] == "SUCCEEDED"
        tombs = _run(
            [
                "docker",
                "exec",
                container_id,
                "sh",
                "-c",
                "find /var/lib/gateway/repository/artifacts -name '.deleting-*' "
                "-o -name '.detach-*' -o -name '.unlink-verify-*' "
                "-o -name '.unlink-stage-*' | wc -l",
            ]
        )
        assert tombs.stdout.strip() == "0"
        print(f"compose_project={project}", flush=True)
    finally:
        _cleanup_compose(project, env)
