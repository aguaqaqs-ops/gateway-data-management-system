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
    assert "USER root" in dockerfile
    assert "ENTRYPOINT" in dockerfile
    assert "adduser --system --ingroup gateway gateway" in dockerfile
    assert "artifact-broker" not in dockerfile
    for label in (
        "org.opencontainers.image.revision=",
        "gateway.p2r1.build-input-revision=",
        "gateway.p2r1.source-tree-sha256=",
        "gateway.p2r1.dolt-version=",
        "gateway.p2r1.uv-version=",
        "gateway.p2r1.uv-lock-sha256=",
        "gateway.p2r1.cache-policy=",
    ):
        assert label in dockerfile


@pytest.mark.unit
def test_dockerfile_and_compose_emit_three_independent_provenance_fields() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG CANDIDATE_SHA=unknown" in dockerfile
    assert "ARG BUILD_INPUT_REVISION=unknown" in dockerfile
    assert "ARG SOURCE_TREE_SHA256=unknown" in dockerfile
    assert "ARG BUILD_REVISION" not in dockerfile
    assert "BUILD_REVISION" not in dockerfile
    assert 'org.opencontainers.image.revision="${CANDIDATE_SHA}"' in dockerfile
    assert 'gateway.p2r1.build-input-revision="${BUILD_INPUT_REVISION}"' in dockerfile
    assert 'gateway.p2r1.source-tree-sha256="${SOURCE_TREE_SHA256}"' in dockerfile
    assert "grep -Eq '^[0-9a-f]{40}$'" in dockerfile
    assert "grep -Eq '^sha256:[0-9a-f]{64}$'" in dockerfile

    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    assert "CANDIDATE_SHA: ${GATEWAY_P2R1_CANDIDATE_SHA:-unknown}" in service
    assert "BUILD_INPUT_REVISION: ${GATEWAY_P2R1_BUILD_INPUT_REVISION:-unknown}" in service
    assert "SOURCE_TREE_SHA256: ${GATEWAY_P2R1_SOURCE_TREE_SHA256:-unknown}" in service
    assert "BUILD_REVISION:" not in service

    probe = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-probe")
    assert "CANDIDATE_SHA: ${GATEWAY_P2R1_CANDIDATE_SHA:-unknown}" in probe
    assert "BUILD_INPUT_REVISION: ${GATEWAY_P2R1_BUILD_INPUT_REVISION:-unknown}" in probe
    assert "SOURCE_TREE_SHA256: ${GATEWAY_P2R1_SOURCE_TREE_SHA256:-unknown}" in probe
    assert "GATEWAY_P2R1_CANDIDATE_SHA: ${GATEWAY_P2R1_CANDIDATE_SHA:-}" in probe
    assert "GATEWAY_P2R1_BUILD_INPUT_REVISION: ${GATEWAY_P2R1_BUILD_INPUT_REVISION:-}" in probe
    assert "GATEWAY_P2R1_SOURCE_TREE_SHA256: ${GATEWAY_P2R1_SOURCE_TREE_SHA256:-}" in probe
    assert "GATEWAY_P2R1_BUILD_REVISION: ${GATEWAY_P2R1_BUILD_REVISION:-}" in probe


def test_dockerfile_uv_lock_sha256_matches_lockfile() -> None:
    assert _dockerfile_uv_lock_default() == _uv_lock_sha256()


def test_compose_repository_service_is_in_default_reachable_graph() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    service = _service_block(compose, "repository-service")
    assert "profiles:" not in service
    assert "repository_service/Dockerfile" in service
    backend = _service_block(compose, "backend")
    worker = _service_block(compose, "worker")
    assert "depends_on:" in backend
    assert "condition: service_healthy" in backend
    assert "depends_on:" in worker
    assert "condition: service_healthy" in worker
    assert "ports:" not in worker
    assert "GATEWAY_BACKEND_SESSION_FILE" in backend
    assert ":-./config/session.json" not in compose
    assert "file: ${GATEWAY_BACKEND_SESSION_FILE}" in compose
    assert "file: ${GATEWAY_BACKEND_SESSION_FILE:-" not in compose
    assert "backend-session" in backend
    assert "GATEWAY_BACKEND_PROVISIONED_MAPPING_FILE" in backend
    assert "GATEWAY_BACKEND_OPERATION_WORKER_PROVISIONED_MAPPING_FILE" in worker


def test_compose_dev_overlay_points_backend_session_at_local_fixture() -> None:
    overlay = (VNEXT_ROOT / "deploy" / "compose.dev.yaml").read_text(encoding="utf-8")
    assert "backend-session:" in overlay
    assert "file: ./config/session.json" in overlay


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


OPERATIONAL_COMPOSE_ENV_DEFAULTS = {
    "GATEWAY_REPOSITORY_ARTIFACT_TTL_SECONDS": "86400",
    "GATEWAY_REPOSITORY_ARTIFACT_CLEANUP_INTERVAL_SECONDS": "300",
    "GATEWAY_REPOSITORY_MAX_CONCURRENT_UPLOADS": "8",
    "GATEWAY_REPOSITORY_MAX_IMPORT_WORKERS": "4",
    "GATEWAY_REPOSITORY_MAX_QUEUED_IMPORTS": "64",
    "GATEWAY_REPOSITORY_MAX_CONCURRENT_ROW_STREAMS": "8",
    "GATEWAY_REPOSITORY_FULL_SCAN_TIMEOUT_SECONDS": "3600",
    "GATEWAY_REPOSITORY_MIN_FREE_DISK_BYTES": "5368709120",
    "GATEWAY_REPOSITORY_MIN_FREE_DISK_FRACTION": "0.10",
    "GATEWAY_REPOSITORY_IMPORT_HEADROOM_BYTES": "1073741824",
}


def test_compose_repository_service_maps_operational_env_allowlist() -> None:
    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    for key, default in OPERATIONAL_COMPOSE_ENV_DEFAULTS.items():
        expected = f"{key}: ${{{key}:-{default}}}"
        assert expected in service, f"missing compose mapping: {expected}"


def test_compose_services_wire_docker_build_network() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for service_name in ("backend", "worker", "repository-service", "repository-probe"):
        service = _service_block(compose, service_name)
        assert "network: ${GATEWAY_DOCKER_BUILD_NETWORK:-}" in service


def test_compose_repository_service_runtime_has_no_bootstrap_index_env() -> None:
    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    environment = service.split("environment:", maxsplit=1)[1].split("secrets:", maxsplit=1)[0]
    assert "UV_BOOTSTRAP" not in environment
    assert "UV_INDEX" not in environment
    assert "PIP_INDEX" not in environment


def test_readme_documents_env_file_and_force_recreate() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "--env-file" in readme
    assert "up --no-build --force-recreate" in readme or "--force-recreate" in readme
    assert "docker restart" in readme
    assert "不会" in readme or "will not" in readme.lower()
    for key in OPERATIONAL_COMPOSE_ENV_DEFAULTS:
        assert key in readme


def test_compose_repository_service_has_no_host_ports() -> None:
    service = _service_block(COMPOSE.read_text(encoding="utf-8"), "repository-service")
    assert "ports:" not in service


def test_compose_has_no_resident_client_or_client_dockerfile() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"^  repository-client:", compose, re.M) is None
    assert re.search(r"^  snapshot-operator:", compose, re.M) is None
    assert "repository_client/tests/Dockerfile" not in compose
    assert "gateway-repository-client-e2e" not in compose
    service = _service_block(compose, "repository-service")
    assert "docker.sock" not in service


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
        "/v1/repositories/{repository_id}/versioned/imports",
        "/v1/repositories/{repository_id}/operations/{operation_id}",
        "/v1/repositories/{repository_id}/versioned/refs/{ref_name}",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/catalog",
        "/v1/repositories/{repository_id}/versioned/commits/{commit_id}/rows",
    }


ALLOWED_V1_ROUTE_FILES = {
    SRC_ROOT / "http" / "routes" / "repositories.py",
    SRC_ROOT / "http" / "routes" / "artifacts.py",
    SRC_ROOT / "http" / "routes" / "imports.py",
    SRC_ROOT / "http" / "routes" / "operations.py",
    SRC_ROOT / "http" / "routes" / "versioned_read.py",
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


def test_dockerfile_prepares_gateway_owned_artifacts() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "/var/lib/gateway/repository/artifacts" in dockerfile
    assert "chown gateway:gateway /var/lib/gateway /var/lib/gateway/repository /var/lib/gateway/repository/artifacts" in dockerfile
    assert "chmod 0750 /var/lib/gateway/repository/artifacts" in dockerfile
    assert "artifact-broker" not in dockerfile
    assert "USER root" in dockerfile


def test_entrypoint_prepares_layout_then_drops_to_gateway() -> None:
    entrypoint = (REPO_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert "|| true" not in entrypoint
    assert "chown -R" not in entrypoint
    assert "find " not in entrypoint
    assert "artifact_layout" in entrypoint
    assert "artifact-broker" not in entrypoint
    assert "artifact-broker.sock" not in entrypoint
    assert "--peer-gid" not in entrypoint
    assert "GATEWAY_REPOSITORY_ARTIFACT_BROKER" not in entrypoint
    assert "runuser -u" in entrypoint
    assert "unlink-stage" not in entrypoint
