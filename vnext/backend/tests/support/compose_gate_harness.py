"""Shared helpers for backend compose integration gates."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[3]
DEPLOY_ROOT = VNEXT_ROOT / "deploy"
COMPOSE_FILE = DEPLOY_ROOT / "compose.yaml"
BUILD_REPOSITORY_SCRIPT = VNEXT_ROOT / "scripts" / "build-repository-service-image.sh"
BACKEND_URL = "http://127.0.0.1:8000"
GATE_PROJECT_ENV = "GATEWAY_COMPOSE_GATE_PROJECT_NAME"
PREBUILT_ENV = "GATEWAY_COMPOSE_GATE_PREBUILT"


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
