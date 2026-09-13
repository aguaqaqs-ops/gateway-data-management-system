"""Static contract tests for backend/worker Docker build bootstrap wiring."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = VNEXT_ROOT / "backend" / "Dockerfile"
COMPOSE = VNEXT_ROOT / "deploy" / "compose.yaml"


@pytest.mark.unit
def test_backend_dockerfile_declares_bootstrap_args_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runtime_stage = dockerfile.split("FROM python:3.14.6-slim-bookworm", maxsplit=1)[1]
    assert "ARG UV_BOOTSTRAP_INDEX_URL=https://pypi.org/simple" in runtime_stage
    assert "ARG UV_BOOTSTRAP_TRUSTED_HOST" in runtime_stage
    assert "uv sync --frozen" in dockerfile
    assert re.search(r"^ENV\s+UV_", runtime_stage, re.M) is None
    assert re.search(r"^ENV\s+PIP_", runtime_stage, re.M) is None


@pytest.mark.unit
def test_backend_dockerfile_runtime_env_is_application_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runtime_stage = dockerfile.split("FROM python:3.14.6-slim-bookworm", maxsplit=1)[1]
    runtime_env_lines = [line for line in runtime_stage.splitlines() if line.startswith("ENV ")]
    assert runtime_env_lines == [
        'ENV PATH="/app/backend/.venv/bin:${PATH}" PYTHONPATH="/app/backend/src"',
    ]
    assert "UV_BOOTSTRAP" not in runtime_env_lines[0]
    assert "UV_INDEX" not in runtime_env_lines[0]


@pytest.mark.unit
def test_compose_backend_build_args_and_runtime_separation() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    backend_block = re.search(
        r"^  backend:\n(.*?)(?=^  worker:)",
        compose,
        re.M | re.S,
    )
    assert backend_block is not None
    block = backend_block.group(1)
    assert "UV_BOOTSTRAP_INDEX_URL: ${GATEWAY_BACKEND_UV_BOOTSTRAP_INDEX_URL" in block
    assert "UV_BOOTSTRAP_TRUSTED_HOST: ${GATEWAY_BACKEND_UV_BOOTSTRAP_TRUSTED_HOST" in block
    assert "network: ${GATEWAY_DOCKER_BUILD_NETWORK:-}" in block
    environment = block.split("environment:", maxsplit=1)[1].split("volumes:", maxsplit=1)[0]
    assert "UV_BOOTSTRAP" not in environment
    assert "UV_INDEX" not in environment
