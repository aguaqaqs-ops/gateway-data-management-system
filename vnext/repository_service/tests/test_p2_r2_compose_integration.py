"""Static integration assertions for P2-R2 R2-C3 container and Compose wiring."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VNEXT_ROOT = REPO_ROOT.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE = VNEXT_ROOT / "deploy" / "compose.yaml"
UV_LOCK = REPO_ROOT / "uv.lock"
SRC_ROOT = REPO_ROOT / "src" / "gateway_repository_service"


def _uv_lock_sha256() -> str:
    return hashlib.sha256(UV_LOCK.read_bytes()).hexdigest()


def _dockerfile_uv_lock_default() -> str:
    match = re.search(r"^ARG UV_LOCK_SHA256=(.+)$", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert match is not None
    return match.group(1)


def _service_block(compose_text: str, service_name: str) -> str:
    match = re.search(
        rf"^  {re.escape(service_name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|^secrets:|^volumes:|\Z)",
        compose_text,
        re.M | re.S,
    )
    assert match is not None, f"missing service block: {service_name}"
    return match.group(0)


def test_dockerfile_cmd_is_uvicorn_factory() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert 'CMD ["python", "-m", "uvicorn", "gateway_repository_service.app:create_app"' in dockerfile
    assert '"--factory"' in dockerfile
    assert '"--host", "0.0.0.0", "--port", "8000"' in dockerfile
    assert "RepositoryServiceSettings" not in dockerfile


def test_dockerfile_runs_as_gateway_user_with_provenance_labels() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER gateway" in dockerfile
    for label in (
        "org.opencontainers.image.revision=",
        "gateway.p2r1.source-tree-sha256=",
        "gateway.p2r1.dolt-version=",
        "gateway.p2r1.uv-version=",
        "gateway.p2r1.uv-lock-sha256=",
        "gateway.p2r1.cache-policy=",
    ):
        assert label in dockerfile


def test_dockerfile_uv_lock_sha256_matches_lockfile() -> None:
    assert _dockerfile_uv_lock_default() == _uv_lock_sha256()


def test_compose_defines_repository_service_on_p2_r2_profile() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    service = _service_block(compose, "repository-service")
    assert 'profiles: ["p2-r2"]' in service
    assert "repository_service/Dockerfile" in service


def test_compose_repository_probe_unchanged_on_p2_r1_profile() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    probe = _service_block(compose, "repository-probe")
    assert 'profiles: ["p2-r1"]' in probe
    assert 'command: ["python", "-m", "gateway_repository_service.target_gate"]' in probe
    assert "repository-data:/var/lib/gateway/repository" in probe


def test_compose_uses_separate_named_volume_for_repository_service() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    service = _service_block(compose, "repository-service")
    assert "repository-service-data:/var/lib/gateway/repository" in service
    assert "repository-data:/var/lib/gateway/repository" not in service
    assert "repository-service-data:" in compose


def test_compose_repository_service_has_production_env_and_secret_mount() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    service = _service_block(compose, "repository-service")
    assert "GATEWAY_REPOSITORY_PROFILE: production" in service
    assert "GATEWAY_REPOSITORY_DATA_ROOT: /var/lib/gateway/repository" in service
    assert "GATEWAY_REPOSITORY_DOLT_BINARY: /usr/local/bin/dolt" in service
    assert (
        "GATEWAY_REPOSITORY_BEARER_TOKEN_FILE: /run/secrets/repository-bearer-token"
        in service
    )
    assert "repository-bearer-token" in service
    assert "GATEWAY_P2R2_BEARER_TOKEN_FILE" in compose
    assert "repository-bearer-token:" in compose


def test_compose_repository_service_has_no_host_ports() -> None:
    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    assert "ports:" not in service


def test_compose_repository_service_healthcheck_uses_python_readyz() -> None:
    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    assert "healthcheck:" in service
    assert "urllib.request" in service
    assert "http://127.0.0.1:8000/readyz" in service
    assert "curl" not in service
    assert "jq" not in service


def test_production_openapi_only_exposes_allowed_routes() -> None:
    from gateway_repository_service.app import create_app
    from support.http_harness import create_test_client

    client = create_test_client(create_app(enable_lifecycle=False))
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths.keys()) == {
        "/healthz",
        "/readyz",
        "/v1/repositories",
        "/v1/repositories/{repository_id}/artifacts",
    }


ALLOWED_V1_ROUTE_FILES = {
    SRC_ROOT / "http" / "routes" / "repositories.py",
    SRC_ROOT / "http" / "routes" / "artifacts.py",
}


def test_source_tree_only_registers_allowed_v1_routes() -> None:
    v1_pattern = re.compile(r'@.*\.(get|post|put|patch|delete|route)\(\s*["\']/v1/', re.I)
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        if not v1_pattern.search(text):
            continue
        if path not in ALLOWED_V1_ROUTE_FILES:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"found unexpected v1 route registration in: {offenders}"

    repositories = (SRC_ROOT / "http" / "routes" / "repositories.py").read_text(encoding="utf-8")
    assert '/v1/repositories' in repositories
    assert "/v1/repositories/" not in repositories


@pytest.mark.parametrize(
    ("pattern", "description"),
    [
        (r'@.*\.(get|post|put|patch|delete|route)\(\s*["\']/v2/', "v2 route registration"),
        (r'@.*\.(get|post|put|patch|delete|route)\(\s*["\']/_test', "test route registration"),
        (r'add_api_route\(\s*["\']/v2/', "v2 add_api_route"),
        (r'add_api_route\(\s*["\']/_test', "test add_api_route"),
    ],
)
def test_source_tree_has_no_forbidden_route_registrations(pattern: str, description: str) -> None:
    offenders: list[str] = []
    compiled = re.compile(pattern, re.I)
    for path in SRC_ROOT.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        if compiled.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"found forbidden {description} in: {offenders}"
