"""Test-only Compose lifecycle helpers for P2-R6-S7.

These helpers own unique project/volume/token naming, rendered p2-r2 boundary
checks, Linux-bridge discovery, ephemeral client identity, typed summary parsing,
and scoped Docker inventory. They do not change production Compose topology.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
from uuid import UUID, uuid4

from support.compose_build_harness import (
    CANDIDATE_LABEL,
    inspect_image,
)
from support.snapshot_admin_harness import RestoreProcedureError
from support.versioned_fixture_consumer_harness import parse_consumer_summary

VNEXT_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = VNEXT_ROOT / "deploy" / "compose.yaml"
CLIENT_PROJECT = VNEXT_ROOT / "repository_client"
CLIENT_DOCKERFILE = CLIENT_PROJECT / "tests" / "Dockerfile"
CLIENT_UV_LOCK_PATH = CLIENT_PROJECT / "uv.lock"
CONSUMER_SCRIPT = CLIENT_PROJECT / "tests" / "support" / "versioned_fixture_consumer.py"
FIXTURE_ROOT = CLIENT_PROJECT / "tests" / "fixtures" / "versioned_v1"
DEFAULT_CLIENT_IMAGE = "gateway-repository-client-e2e:local"
CLIENT_UV_LOCK_LABEL = "gateway.p2r6.client-uv-lock-sha256"
COMPOSE_PROFILE = "p2-r2"
SERVICE_NAME = "repository-service"
INSIDE_SERVICE_ENDPOINT = "http://repository-service:8000"
CLIENT_BUILD_TIMEOUT_SECONDS = 1800
_PROJECT_ROLE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_SUFFIX = re.compile(r"^[0-9a-f]{12}$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_LOCK_SHA = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_IPV4 = re.compile(r"^(?:25[0-5]|2[0-4]\d|1?\d{1,2})(?:\.(?:25[0-5]|2[0-4]\d|1?\d{1,2})){3}$")
_SUMMARY_ALLOWED_KEYS = frozenset({"status", "repository_id", "c0", "c1", "c2", "main_commit"})
_RESIDENT_CLIENT_NAMES = frozenset(
    {
        "client",
        "remote-client",
        "repository-client",
        "snapshot",
        "snapshot-helper",
        "snapshot-operator",
    }
)
_HOST_PORT_MARKERS = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]", "::1")


@dataclass(frozen=True, slots=True)
class ComposeResourceNames:
    role: str
    suffix: str
    project: str
    data_volume: str
    restore_volume: str
    token_filename: str

    @property
    def network_name(self) -> str:
        return f"{self.project}_default"

    @property
    def allowed_names(self) -> frozenset[str]:
        return frozenset(
            {
                self.project,
                self.data_volume,
                self.restore_volume,
                self.network_name,
            }
        )


@dataclass(frozen=True, slots=True)
class RenderedServiceBoundary:
    name: str
    published_ports: tuple[str, ...]
    has_docker_socket: bool
    has_host_root_mount: bool


@dataclass(frozen=True, slots=True)
class RenderedComposeConfig:
    services: tuple[str, ...]
    repository_service: RenderedServiceBoundary
    resident_client_services: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServiceNetworkDiscovery:
    project: str
    network_name: str
    network_id: str
    gateway_ipv4: str
    service_ipv4: str
    inside_endpoint: str
    gate_host_endpoint: str


@dataclass(frozen=True, slots=True)
class ClientIdentity:
    kind: Literal["image", "host-runner"]
    candidate_sha: str
    client_uv_lock_sha256: str
    image_id: str | None = None

    def evidence_id(self) -> str:
        if self.kind == "image":
            if self.image_id is None or not _IMAGE_ID.fullmatch(self.image_id):
                raise ValueError("image client identity requires sha256:<64 hex>")
            return self.image_id
        return (
            "host-runner:"
            f"candidate={self.candidate_sha};"
            f"client_uv_lock_sha256={self.client_uv_lock_sha256}"
        )


@dataclass(frozen=True, slots=True)
class DockerObjectInventory:
    containers: tuple[str, ...]
    networks: tuple[str, ...]
    volumes: tuple[str, ...]

    def is_empty(self) -> bool:
        return not self.containers and not self.networks and not self.volumes


def current_client_uv_lock_sha256() -> str:
    return hashlib.sha256(CLIENT_UV_LOCK_PATH.read_bytes()).hexdigest()


def allocate_compose_resources(role: str, *, suffix: str | None = None) -> ComposeResourceNames:
    if not _PROJECT_ROLE.fullmatch(role):
        raise ValueError("role must be a lowercase hyphenated token")
    resolved = uuid4().hex[:12] if suffix is None else suffix
    if not _SUFFIX.fullmatch(resolved):
        raise ValueError("suffix must be 12 lowercase hex characters")
    project = f"gateway-p2r6-s7-{role}-{resolved}"
    return ComposeResourceNames(
        role=role,
        suffix=resolved,
        project=project,
        data_volume=f"{project}_repository-service-data",
        restore_volume=f"{project}_restore",
        token_filename=f"{project}.token",
    )


def write_token_file(path: Path, token: str) -> Path:
    path.write_text(token, encoding="utf-8")
    path.chmod(0o400)
    return path


def compose_command(*args: str, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(compose_file),
        "--profile",
        COMPOSE_PROFILE,
        *args,
    ]


def compose_config_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command("config", "--format", "json", project=project, compose_file=compose_file)


def force_recreate_service_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command(
        "up",
        "-d",
        "--no-build",
        "--force-recreate",
        SERVICE_NAME,
        project=project,
        compose_file=compose_file,
    )


def compose_down_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command(
        "down",
        "-v",
        "--remove-orphans",
        project=project,
        compose_file=compose_file,
    )


def compose_ps_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command("ps", "-q", SERVICE_NAME, project=project, compose_file=compose_file)


def _require_mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _published_ports(service: Mapping[str, Any]) -> tuple[str, ...]:
    ports = service.get("ports")
    if ports is None:
        return ()
    if not isinstance(ports, list):
        raise ValueError("service.ports must be a list when present")
    published: list[str] = []
    for item in ports:
        if isinstance(item, str) and item.strip():
            published.append(item.strip())
            continue
        if isinstance(item, dict):
            published_port = item.get("published")
            if published_port is None:
                continue
            if isinstance(published_port, (str, int)) and str(published_port):
                published.append(str(published_port))
    return tuple(published)


def _volume_entries(service: Mapping[str, Any]) -> tuple[object, ...]:
    volumes = service.get("volumes")
    if volumes is None:
        return ()
    if not isinstance(volumes, list):
        raise ValueError("service.volumes must be a list when present")
    return tuple(volumes)


def _entry_source_target(entry: object) -> tuple[str | None, str | None]:
    if isinstance(entry, str):
        source, _, target = entry.partition(":")
        return source or None, target or None
    if isinstance(entry, dict):
        raw_source = entry.get("source")
        raw_target = entry.get("target")
        return (
            raw_source if isinstance(raw_source, str) else None,
            raw_target if isinstance(raw_target, str) else None,
        )
    return None, None


def _has_docker_socket(service: Mapping[str, Any]) -> bool:
    for entry in _volume_entries(service):
        source, target = _entry_source_target(entry)
        for value in (source, target):
            if value is not None and value.endswith("docker.sock"):
                return True
    return False


def _has_host_root_mount(service: Mapping[str, Any]) -> bool:
    for entry in _volume_entries(service):
        source, _target = _entry_source_target(entry)
        if source == "/":
            return True
    return False


def _is_resident_client_service(name: str) -> bool:
    normalized = name.lower().replace("_", "-")
    if normalized in _RESIDENT_CLIENT_NAMES:
        return True
    return normalized.endswith("-client") or normalized.startswith("client-")


def parse_rendered_compose_config(payload: object) -> RenderedComposeConfig:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("rendered Compose config is not valid JSON") from exc
    root = _require_mapping(payload, field="compose")
    services_raw = _require_mapping(root.get("services"), field="services")
    service_names = tuple(str(name) for name in services_raw)
    repository = services_raw.get(SERVICE_NAME)
    if not isinstance(repository, dict):
        raise ValueError("rendered config is missing repository-service")
    resident = tuple(name for name in service_names if _is_resident_client_service(name))
    return RenderedComposeConfig(
        services=service_names,
        repository_service=RenderedServiceBoundary(
            name=SERVICE_NAME,
            published_ports=_published_ports(repository),
            has_docker_socket=_has_docker_socket(repository),
            has_host_root_mount=_has_host_root_mount(repository),
        ),
        resident_client_services=resident,
    )


def assert_p2r2_compose_boundary(config: RenderedComposeConfig) -> None:
    service = config.repository_service
    if service.published_ports:
        raise AssertionError("repository-service must not publish host ports")
    if service.has_docker_socket:
        raise AssertionError("repository-service must not mount the Docker socket")
    if service.has_host_root_mount:
        raise AssertionError("repository-service must not mount the host root")
    if config.resident_client_services:
        raise AssertionError(
            "rendered Compose must not include a resident client or snapshot service: "
            f"{config.resident_client_services!r}"
        )


def parse_service_network_discovery(
    networks_payload: object,
    *,
    project: str,
) -> ServiceNetworkDiscovery:
    networks = _require_mapping(networks_payload, field="networks")
    if not networks:
        raise ValueError("container networks payload must not be empty")
    chosen_name: str | None = None
    chosen: dict[str, Any] | None = None
    for name, body in networks.items():
        if not isinstance(name, str) or not isinstance(body, dict):
            raise ValueError("network entries must map names to objects")
        if project in name:
            chosen_name = name
            chosen = body
            break
    if chosen is None or chosen_name is None:
        if len(networks) != 1:
            raise ValueError("unable to select the compose network for the project")
        chosen_name, chosen_body = next(iter(networks.items()))
        if not isinstance(chosen_name, str) or not isinstance(chosen_body, dict):
            raise ValueError("network entries must map names to objects")
        chosen = chosen_body
    network_id = chosen.get("NetworkID")
    gateway = chosen.get("Gateway")
    address = chosen.get("IPAddress")
    if not isinstance(network_id, str) or not network_id:
        raise ValueError("network is missing NetworkID")
    if not isinstance(gateway, str) or not _IPV4.fullmatch(gateway):
        raise ValueError("network Gateway must be an IPv4 address")
    if not isinstance(address, str) or not _IPV4.fullmatch(address):
        raise ValueError("service IPAddress must be an IPv4 address")
    if address in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("service address must not be a host-port loopback")
    gate_host_endpoint = f"http://{address}:8000"
    assert_not_host_port_endpoint(INSIDE_SERVICE_ENDPOINT)
    assert_not_host_port_endpoint(gate_host_endpoint)
    if INSIDE_SERVICE_ENDPOINT == gate_host_endpoint:
        raise ValueError("inside-network and gate-host endpoints must differ")
    return ServiceNetworkDiscovery(
        project=project,
        network_name=chosen_name,
        network_id=network_id,
        gateway_ipv4=gateway,
        service_ipv4=address,
        inside_endpoint=INSIDE_SERVICE_ENDPOINT,
        gate_host_endpoint=gate_host_endpoint,
    )


def assert_not_host_port_endpoint(endpoint: str) -> None:
    lowered = endpoint.strip().lower()
    if not lowered.startswith("http://") and not lowered.startswith("https://"):
        raise ValueError("endpoint must be an absolute HTTP URL")
    hostport = lowered.split("://", 1)[1].split("/", 1)[0]
    if hostport.startswith("["):
        closing = hostport.find("]")
        host = hostport[1:closing] if closing != -1 else hostport
    else:
        host = hostport.split(":", 1)[0]
    if host in _HOST_PORT_MARKERS:
        raise ValueError("host-port endpoint is forbidden")


def classify_readiness(health_status: str) -> Literal["ready", "not_ready"]:
    if health_status.strip() == "healthy":
        return "ready"
    return "not_ready"


def classify_client_auth_failure(
    *,
    returncode: int,
    summary: Mapping[str, Any] | None,
    http_status: int | None = None,
) -> Literal["ok", "unauthorized", "failed"]:
    if summary is not None:
        return "ok"
    if http_status == 401 or returncode != 0:
        return "unauthorized" if http_status == 401 else "failed"
    return "failed"


def assert_restore_volume_listing_empty(names: Sequence[str]) -> None:
    leftover = {name for name in names if name and name != "lost+found"}
    if leftover:
        raise RestoreProcedureError("restore target is not empty")


def redact_evidence_text(
    text: str,
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    for path in sorted(host_paths, key=len, reverse=True):
        if path:
            redacted = redacted.replace(path, "<redacted-path>")
    return redacted


def assert_no_secret_or_path_leak(
    text: str,
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> None:
    for secret in secrets:
        if secret and secret in text:
            raise AssertionError("text leaked secret material")
    for path in host_paths:
        if path and path in text:
            raise AssertionError("text leaked a host path")


def parse_client_summary(stdout: str) -> dict[str, Any] | None:
    summary = parse_consumer_summary(stdout)
    if summary is None:
        return None
    if set(summary) != _SUMMARY_ALLOWED_KEYS:
        return None
    return summary


def assert_client_stdout_safe(
    stdout: str,
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> dict[str, Any]:
    assert_no_secret_or_path_leak(stdout, secrets=secrets, host_paths=host_paths)
    summary = parse_client_summary(stdout)
    if summary is None:
        raise AssertionError("client stdout is not a typed consumer summary")
    repository_id = summary["repository_id"]
    UUID(str(repository_id))
    return summary


def ephemeral_client_env(
    *,
    base_url: str,
    bearer_token: str,
    fixture_root: Path,
) -> dict[str, str]:
    assert_not_host_port_endpoint(base_url)
    return {
        "GATEWAY_REPOSITORY_BASE_URL": base_url,
        "GATEWAY_REPOSITORY_BEARER_TOKEN": bearer_token,
        "GATEWAY_VERSIONED_FIXTURE_ROOT": str(fixture_root),
    }


def host_runner_command() -> list[str]:
    return [
        "uv",
        "run",
        "--project",
        str(CLIENT_PROJECT),
        "--locked",
        "--offline",
        "python",
        str(CONSUMER_SCRIPT),
    ]


def write_client_env_file(
    path: Path,
    *,
    base_url: str,
    bearer_token: str,
    fixture_root_in_container: str = "/fixtures",
) -> Path:
    assert_not_host_port_endpoint(base_url)
    path.write_text(
        "GATEWAY_REPOSITORY_BASE_URL="
        f"{base_url}\nGATEWAY_REPOSITORY_BEARER_TOKEN={bearer_token}\n"
        f"GATEWAY_VERSIONED_FIXTURE_ROOT={fixture_root_in_container}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def ephemeral_client_docker_command(
    *,
    image: str,
    fixture_root: Path,
    env_file: Path,
    network: str | None,
) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--mount",
        f"type=bind,src={fixture_root},dst=/fixtures,readonly",
        "--env-file",
        str(env_file),
    ]
    if network is not None:
        command.extend(["--network", network])
    command.append(image)
    return command


def client_image_identity(
    *,
    candidate_sha: str,
    client_uv_lock_sha256: str,
    image_id: str,
) -> ClientIdentity:
    if not _FULL_SHA.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase hex digest")
    if not _LOCK_SHA.fullmatch(client_uv_lock_sha256):
        raise ValueError("client_uv_lock_sha256 must be a 64-character lowercase hex digest")
    if not _IMAGE_ID.fullmatch(image_id):
        raise ValueError("client_image_id must be sha256:<64 hex>")
    return ClientIdentity(
        kind="image",
        candidate_sha=candidate_sha,
        client_uv_lock_sha256=client_uv_lock_sha256,
        image_id=image_id,
    )


def host_runner_identity(*, candidate_sha: str, client_uv_lock_sha256: str) -> ClientIdentity:
    if not _FULL_SHA.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase hex digest")
    if not _LOCK_SHA.fullmatch(client_uv_lock_sha256):
        raise ValueError("client_uv_lock_sha256 must be a 64-character lowercase hex digest")
    return ClientIdentity(
        kind="host-runner",
        candidate_sha=candidate_sha,
        client_uv_lock_sha256=client_uv_lock_sha256,
        image_id=None,
    )


def client_image_matches(
    image: str,
    *,
    candidate_sha: str,
    client_uv_lock_sha256: str,
) -> bool:
    digest, labels = inspect_image(image)
    if not _IMAGE_ID.fullmatch(digest) or not labels:
        return False
    return (
        labels.get(CANDIDATE_LABEL) == candidate_sha
        and labels.get(CLIENT_UV_LOCK_LABEL) == client_uv_lock_sha256
    )


def _run_client_build(
    image: str,
    *,
    candidate_sha: str,
    client_uv_lock_sha256: str,
) -> None:
    if not CLIENT_DOCKERFILE.is_file():
        raise RuntimeError(f"missing client Dockerfile: {CLIENT_DOCKERFILE}")
    env = os.environ.copy()
    try:
        completed = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(CLIENT_DOCKERFILE),
                "--build-arg",
                f"CANDIDATE_SHA={candidate_sha}",
                "--build-arg",
                f"UV_LOCK_SHA256={client_uv_lock_sha256}",
                "-t",
                image,
                str(VNEXT_ROOT),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=VNEXT_ROOT,
            timeout=CLIENT_BUILD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"repository-client image build timed out after {CLIENT_BUILD_TIMEOUT_SECONDS}s"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            "repository-client image build failed\n"
            f"stdout:\n{redact_evidence_text(completed.stdout, secrets=(client_uv_lock_sha256,))}\n"
            f"stderr:\n{redact_evidence_text(completed.stderr, secrets=(client_uv_lock_sha256,))}"
        )


def ensure_client_image(
    *,
    candidate_sha: str,
    image: str = DEFAULT_CLIENT_IMAGE,
    force_rebuild: bool = False,
) -> str:
    lock_sha = current_client_uv_lock_sha256()
    if not force_rebuild and client_image_matches(
        image,
        candidate_sha=candidate_sha,
        client_uv_lock_sha256=lock_sha,
    ):
        return image
    _run_client_build(image, candidate_sha=candidate_sha, client_uv_lock_sha256=lock_sha)
    if not client_image_matches(
        image,
        candidate_sha=candidate_sha,
        client_uv_lock_sha256=lock_sha,
    ):
        digest, labels = inspect_image(image)
        raise RuntimeError(
            "repository-client image provenance does not match current candidate\n"
            f"image_id={digest}\n"
            f"expected candidate_sha={candidate_sha}\n"
            f"actual candidate_sha={labels.get(CANDIDATE_LABEL)}\n"
            f"expected client_uv_lock_sha256={lock_sha}\n"
            f"actual client_uv_lock_sha256={labels.get(CLIENT_UV_LOCK_LABEL)}"
        )
    return image


def refuse_unscoped_deletion(targets: Sequence[str], allowed: Sequence[str] | set[str] | frozenset[str]) -> tuple[str, ...]:
    allowed_set = frozenset(allowed)
    extra = [item for item in targets if item not in allowed_set]
    if extra:
        raise RuntimeError(
            "refusing to delete Docker objects outside the generated project/volume set"
        )
    return tuple(targets)


def docker_objects(project: str, kind: str) -> list[str]:
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


def project_inventory(project: str) -> DockerObjectInventory:
    return DockerObjectInventory(
        containers=tuple(docker_objects(project, "container")),
        networks=tuple(docker_objects(project, "network")),
        volumes=tuple(docker_objects(project, "volume")),
    )


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=VNEXT_ROOT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout}s: {' '.join(command[:6])}") from exc
    if completed.returncode != 0:
        stdout = redact_evidence_text(completed.stdout, secrets=secrets, host_paths=host_paths)
        stderr = redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command[:8])}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return completed


def wait_healthy(
    container_id: str,
    *,
    timeout: float = 180.0,
    poll_interval: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        completed = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode == 0 and classify_readiness(completed.stdout) == "ready":
            return
        time.sleep(poll_interval)
    raise TimeoutError(f"container {container_id} did not become healthy")


def cleanup_compose_project(
    names: ComposeResourceNames,
    env: dict[str, str],
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> None:
    completed = subprocess.run(
        compose_down_command(project=names.project),
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "docker compose down failed "
            f"({completed.returncode}): "
            f"{redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)}"
        )
    leftover = project_inventory(names.project)
    if not leftover.is_empty():
        raise AssertionError(
            f"project {names.project} still has Docker objects: "
            f"containers={leftover.containers!r} networks={leftover.networks!r} "
            f"volumes={leftover.volumes!r}"
        )
    restore_ls = subprocess.run(
        ["docker", "volume", "inspect", names.restore_volume],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if restore_ls.returncode == 0:
        refuse_unscoped_deletion((names.restore_volume,), names.allowed_names)
        removed = subprocess.run(
            ["docker", "volume", "rm", names.restore_volume],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if removed.returncode != 0:
            raise RuntimeError(
                "failed to remove restore volume "
                f"{names.restore_volume}: {removed.stderr.strip()}"
            )
