"""Static contract tests for backend/worker Docker build bootstrap wiring."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = VNEXT_ROOT / "backend" / "Dockerfile"
DEPENDENCY_BASE_DOCKERFILE = VNEXT_ROOT / "backend" / "Dockerfile.dependency-base"
COMPOSE = VNEXT_ROOT / "deploy" / "compose.yaml"


@pytest.mark.unit
def test_backend_dockerfile_declares_bootstrap_args_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runtime_stage = dockerfile.split("FROM python:3.14.6-slim-bookworm", maxsplit=1)[1]
    assert "ARG UV_BOOTSTRAP_INDEX_URL=https://pypi.org/simple" in runtime_stage
    assert "ARG UV_BOOTSTRAP_TRUSTED_HOST" in runtime_stage
    assert re.search(r"uv sync \\\s+--frozen", dockerfile) is not None
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
def test_preloaded_dependency_layers_are_source_ordered_and_offline_after_source_copy() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    builder = dockerfile.split("FROM dependency-base AS builder", maxsplit=1)[1].split(
        "FROM python:3.14.6-slim-bookworm AS runtime", maxsplit=1
    )[0]
    builder_source = builder.index("COPY rust /build/rust")
    builder_after_source = builder[builder_source:]
    assert "COPY shared_kernel /build/shared_kernel" in builder_after_source
    assert "COPY repository_client /build/repository_client" in builder_after_source
    assert "COPY repository_contracts /build/repository_contracts" in builder_after_source
    assert "UV_OFFLINE=1 uv sync" in builder_after_source
    assert "CARGO_NET_OFFLINE=true" in builder_after_source
    assert re.search(r"\bcurl\b|cargo fetch|uv python install", builder_after_source) is None

    runtime = dockerfile.split("FROM python:3.14.6-slim-bookworm AS runtime", maxsplit=1)[1]
    runtime_source = runtime.index("COPY rust /app/rust")
    runtime_after_source = runtime[runtime_source:]
    assert "COPY shared_kernel /app/shared_kernel" in runtime_after_source
    assert "COPY repository_client /app/repository_client" in runtime_after_source
    assert "COPY repository_contracts /app/repository_contracts" in runtime_after_source
    assert "COPY backend/src ./src" in runtime_after_source
    assert "UV_OFFLINE=1 uv sync" in runtime_after_source
    assert "UV_OFFLINE=1 uv pip install" in runtime_after_source
    assert "source=/build/wheels,target=/tmp/backend-wheels" in runtime_after_source
    assert "/tmp/backend-wheels/*.whl" in runtime_after_source
    assert re.search(r"\bcurl\b|cargo fetch|uv python install|pip install --no-cache-dir", runtime_after_source) is None
    assert "COPY --from=builder /root/.cache/uv" not in dockerfile
    assert "COPY --from=builder /build/wheels" not in dockerfile


@pytest.mark.unit
def test_dependency_base_label_is_bound_to_canonical_input_payload() -> None:
    dockerfile = DEPENDENCY_BASE_DOCKERFILE.read_text(encoding="utf-8")
    script = (VNEXT_ROOT / "scripts" / "build-backend-dependency-base.sh").read_text(
        encoding="utf-8"
    )
    assert 'LABEL gateway.backend.dependency-input-sha256="${DEPENDENCY_INPUT_SHA256}"' in dockerfile
    assert '"gateway.backend.dependency-input-sha256"' in script
    assert "sha256sum /usr/local/share/gateway-backend-dependency-base/inputs.json" in dockerfile
    assert 'IMAGE_TAG="gateway-backend-deps:lock-${INPUT_SHA256:0:12}"' in script


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
    assert "DEPENDENCY_BASE_IMAGE: ${GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE:-rust:1.97.0-bookworm}" in block
    assert "USE_PRELOADED_DEPENDENCIES: ${GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES:-0}" in block
    assert "network: ${GATEWAY_DOCKER_BUILD_NETWORK:-}" in block
    environment = block.split("environment:", maxsplit=1)[1].split("volumes:", maxsplit=1)[0]
    assert "UV_BOOTSTRAP" not in environment
    assert "UV_INDEX" not in environment
    assert "GATEWAY_BACKEND_INTERNAL_BEARER_TOKEN_FILE" in environment
    assert "backend-internal-bearer" in block


@pytest.mark.unit
def test_compose_worker_grace_and_backend_internal_bearer_secret() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    worker_block = re.search(
        r"^  worker:\n(.*?)(?=^  repository-probe:)",
        compose,
        re.M | re.S,
    )
    assert worker_block is not None
    block = worker_block.group(1)
    assert "stop_grace_period: 180s" in block
    assert "DEPENDENCY_BASE_IMAGE: ${GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE:-rust:1.97.0-bookworm}" in block
    assert "USE_PRELOADED_DEPENDENCIES: ${GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES:-0}" in block
    backend_block = re.search(
        r"^  backend:\n(.*?)(?=^  worker:)",
        compose,
        re.M | re.S,
    )
    assert backend_block is not None
    assert "- backend-internal-bearer" in backend_block.group(1)
    assert "stop_grace_period: 180s" in backend_block.group(1)
