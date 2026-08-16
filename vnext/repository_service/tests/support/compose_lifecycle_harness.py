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
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from support.compose_build_harness import (
    CANDIDATE_LABEL,
    inspect_image,
)
from support.snapshot_admin_harness import (
    RestoreProcedureError,
    list_dolt_pids,
    snapshot_check_temp_homes,
)
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
_FAILURE_SUMMARY_KEYS = frozenset({"status", "http_status"})
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
HOLD_PROJECT_LABEL = "com.docker.compose.project"
HOLD_ROLE_LABEL = "gateway.p2r6.role"
HOLD_ROLE_VALUE = "snapshot-hold"
S7_OWNED_HOST_THREAD_PREFIXES: tuple[str, ...] = ()
_HOST_RUNNER_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "TZ",
        "TERM",
        "TMPDIR",
        "TMP",
        "TEMP",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "UV_CACHE_DIR",
        "UV_PYTHON",
        "UV_PYTHON_INSTALL_DIR",
        "UV_TOOL_DIR",
        "UV_PROJECT_ENVIRONMENT",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "NO_PROXY",
        "no_proxy",
    }
)
_DOCKER_CONTROL_ENV = frozenset(
    {
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CERT_PATH",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CONFIG",
        "DOCKER_API_VERSION",
        "DOCKER_TLS_CERTDIR",
        "BUILDX_CONFIG",
        "BUILDKIT_HOST",
        "COMPOSE_DOCKER_CLI_BUILD",
    }
)


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
    hold_containers: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return (
            not self.containers
            and not self.networks
            and not self.volumes
            and not self.hold_containers
        )


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


def compose_stop_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command("stop", SERVICE_NAME, project=project, compose_file=compose_file)


def compose_up_command(*, project: str, compose_file: Path = COMPOSE_FILE) -> list[str]:
    return compose_command(
        "up",
        "-d",
        "--no-build",
        SERVICE_NAME,
        project=project,
        compose_file=compose_file,
    )


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


def parse_client_failure_summary(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped or "\n" in stripped:
        return None
    try:
        payload: object = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    keys = set(payload)
    if "status" not in keys or not keys <= _FAILURE_SUMMARY_KEYS:
        return None
    status = payload.get("status")
    if status not in {"unauthorized", "failed"}:
        return None
    if "http_status" in payload and not isinstance(payload["http_status"], int):
        return None
    return payload


def classify_completed_client(
    completed: subprocess.CompletedProcess[str],
) -> Literal["ok", "unauthorized", "failed"]:
    if completed.returncode == 0:
        return classify_client_auth_failure(
            returncode=0,
            summary=parse_client_summary(completed.stdout),
        )
    failure = parse_client_failure_summary(completed.stdout)
    http_status: int | None = None
    if failure is not None:
        raw_status = failure.get("http_status")
        if isinstance(raw_status, int):
            http_status = raw_status
        elif failure.get("status") == "unauthorized":
            http_status = 401
    return classify_client_auth_failure(
        returncode=completed.returncode,
        summary=None,
        http_status=http_status,
    )


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


def inspect_hold_container_command(project: str) -> list[str]:
    return ["docker", "inspect", "-f", "{{.Id}}", hold_container_name(project)]


def parse_hold_inspect(completed: subprocess.CompletedProcess[str]) -> str | None:
    if completed.returncode != 0:
        return None
    identity = completed.stdout.strip()
    return identity or None


def inspect_hold_container(project: str) -> str | None:
    completed = subprocess.run(
        inspect_hold_container_command(project),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return parse_hold_inspect(completed)


def project_inventory(project: str) -> DockerObjectInventory:
    hold_id = inspect_hold_container(project)
    return DockerObjectInventory(
        containers=tuple(docker_objects(project, "container")),
        networks=tuple(docker_objects(project, "network")),
        volumes=tuple(docker_objects(project, "volume")),
        hold_containers=() if hold_id is None else (hold_id,),
    )


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    completed = run_command_unchecked(
        command,
        env=env,
        timeout=timeout,
        secrets=secrets,
        host_paths=host_paths,
    )
    if completed.returncode != 0:
        stdout = redact_evidence_text(completed.stdout, secrets=secrets, host_paths=host_paths)
        stderr = redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command[:8])}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return completed


def run_command_unchecked(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 180.0,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    del secrets, host_paths
    try:
        return subprocess.run(
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


def _raise_cleanup_errors(errors: list[Exception]) -> None:
    if not errors:
        return
    if len(errors) == 1:
        raise errors[0]
    raise ExceptionGroup("compose project cleanup failures", errors)


def cleanup_compose_project(
    names: ComposeResourceNames,
    env: dict[str, str],
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
    service_image: str | None = None,
    work_root: Path | None = None,
    dolt_baseline: frozenset[int] | None = None,
    check_temp_baseline: frozenset[str] | None = None,
    client_pid_baseline: frozenset[int] | None = None,
    thread_baseline: frozenset[int] | None = None,
) -> None:
    errors: list[Exception] = []
    query_temps: tuple[str, ...] = ()
    container_dolt: tuple[str, ...] = ()
    try:
        query_temps = collect_project_query_temps(names, image=service_image)
    except Exception as exc:
        errors.append(exc)
    try:
        container_dolt = list_project_container_dolt(names.project)
    except Exception as exc:
        errors.append(exc)
    try:
        remove_hold_container(names.project)
    except Exception as exc:
        errors.append(exc)
    try:
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
            errors.append(
                RuntimeError(
                    "docker compose down failed "
                    f"({completed.returncode}): "
                    f"{redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)}"
                )
            )
    except Exception as exc:
        errors.append(exc)
    try:
        leftover = project_inventory(names.project)
        if not leftover.is_empty():
            errors.append(
                AssertionError(
                    f"project {names.project} still has Docker objects: "
                    f"containers={leftover.containers!r} networks={leftover.networks!r} "
                    f"volumes={leftover.volumes!r} hold={leftover.hold_containers!r}"
                )
            )
    except Exception as exc:
        errors.append(exc)
    try:
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
                errors.append(
                    RuntimeError(
                        "failed to remove restore volume "
                        f"{names.restore_volume}: {removed.stderr.strip()}"
                    )
                )
    except Exception as exc:
        errors.append(exc)
    if container_dolt:
        errors.append(
            AssertionError(
                f"project {names.project} still has container dolt processes: {container_dolt!r}"
            )
        )
    if query_temps:
        errors.append(
            AssertionError(f"project {names.project} still has query temps: {query_temps!r}")
        )
    print(
        format_teardown_scan(
            project=names.project,
            container_dolt=container_dolt,
            query_temps=query_temps,
        ),
        flush=True,
    )
    try:
        assert_node_residuals_cleared(
            names,
            work_root=work_root,
            dolt_baseline=dolt_baseline,
            check_temp_baseline=check_temp_baseline,
            client_pid_baseline=client_pid_baseline,
            thread_baseline=thread_baseline,
        )
    except Exception as exc:
        errors.append(exc)
    _raise_cleanup_errors(errors)


@dataclass(frozen=True, slots=True)
class StartedP2R2Service:
    names: ComposeResourceNames
    env: dict[str, str]
    token: str
    token_file: Path
    service_image: str
    container_id: str
    host_paths: tuple[str, ...]


def inspect_networks_command(container_id: str) -> list[str]:
    return ["docker", "inspect", "-f", "{{json .NetworkSettings.Networks}}", container_id]


def parse_inspect_networks(stdout: str, *, project: str) -> ServiceNetworkDiscovery:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("container network inspect output is not valid JSON") from exc
    return parse_service_network_discovery(payload, project=project)


def hold_container_name(project: str) -> str:
    return f"{project}-hold"


def snapshot_hold_command(*, image: str, volume: str, project: str) -> list[str]:
    return [
        "docker",
        "run",
        "-d",
        "--name",
        hold_container_name(project),
        "--label",
        f"{HOLD_PROJECT_LABEL}={project}",
        "--label",
        f"{HOLD_ROLE_LABEL}={HOLD_ROLE_VALUE}",
        "--entrypoint",
        "python",
        "--user",
        "gateway",
        "--env",
        "GATEWAY_REPOSITORY_PROFILE=production",
        "--env",
        "GATEWAY_REPOSITORY_DATA_ROOT=/var/lib/gateway/repository",
        "-v",
        f"{volume}:/var/lib/gateway/repository",
        image,
        "-m",
        "gateway_repository_service.snapshot_admin",
        "hold",
    ]


def docker_logs_command(container: str) -> list[str]:
    return ["docker", "logs", container]


def docker_container_running_command(container: str) -> list[str]:
    return ["docker", "inspect", "-f", "{{.State.Running}}", container]


def docker_stop_signal_command(container: str, *, signal_name: str = "SIGTERM") -> list[str]:
    return ["docker", "stop", "--signal", signal_name, "--time", "5", container]


def docker_inspect_exit_code_command(container: str) -> list[str]:
    return ["docker", "inspect", "-f", "{{.State.ExitCode}}", container]


def parse_hold_ready_json(raw: str) -> dict[str, Any]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise ValueError("hold produced no JSON")
    seen_json = False
    last_error: ValueError | None = None
    for line in lines:
        try:
            payload: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        seen_json = True
        try:
            mapping = _require_mapping(payload, field="hold")
        except ValueError as exc:
            last_error = exc
            continue
        if mapping.get("action") == "hold" and mapping.get("status") == "ready":
            return mapping
        last_error = ValueError("hold JSON is not a complete ready summary")
    if not seen_json:
        raise ValueError("hold stdout is not valid JSON")
    if last_error is not None:
        raise last_error
    raise ValueError("hold JSON is not a complete ready summary")


def volume_create_command(volume: str) -> list[str]:
    return ["docker", "volume", "create", volume]


def query_temp_listing_command(*, image: str, volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "find",
        "--user",
        "root",
        "-v",
        f"{volume}:/data:ro",
        image,
        "/data",
        "-name",
        "query-*.sql",
    ]


def seed_volume_marker_command(*, image: str, volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        "--user",
        "root",
        "-v",
        f"{volume}:/data",
        image,
        "-c",
        "mkdir -p /data && echo seed > /data/overlay.marker",
    ]


def inspect_health_command(container_id: str) -> list[str]:
    return ["docker", "inspect", "-f", "{{.State.Health.Status}}", container_id]


def volume_listing_command(*, image: str, volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "find",
        "--user",
        "root",
        "-v",
        f"{volume}:/data:ro",
        image,
        "/data",
        "-mindepth",
        "1",
        "!",
        "-name",
        "lost+found",
    ]


def parse_volume_listing(stdout: str) -> tuple[str, ...]:
    names: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped in {"/data", "/data/lost+found"}:
            continue
        names.append(Path(stripped).name)
    return tuple(names)


def copy_volume_command(*, image: str, source_volume: str, dest_volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "sh",
        "--user",
        "root",
        "-v",
        f"{source_volume}:/from:ro",
        "-v",
        f"{dest_volume}:/to",
        image,
        "-c",
        "tar -C /from -cf - . | tar -C /to -xf -",
    ]


def chown_volume_command(*, image: str, volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "chown",
        "--user",
        "root",
        "-v",
        f"{volume}:/var/lib/gateway/repository",
        image,
        "-R",
        "gateway:gateway",
        "/var/lib/gateway/repository",
    ]


def snapshot_check_command(*, image: str, volume: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "python",
        "--user",
        "gateway",
        "--env",
        "GATEWAY_REPOSITORY_PROFILE=production",
        "--env",
        "GATEWAY_REPOSITORY_DATA_ROOT=/var/lib/gateway/repository",
        "-v",
        f"{volume}:/var/lib/gateway/repository",
        image,
        "-m",
        "gateway_repository_service.snapshot_admin",
        "check",
    ]


def parse_check_passed_json(raw: str) -> dict[str, Any]:
    line = raw.strip()
    if not line or "\n" in line:
        raise ValueError("check stdout must be one JSON line")
    try:
        payload: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("check stdout is not valid JSON") from exc
    mapping = _require_mapping(payload, field="check")
    if mapping.get("action") != "check" or mapping.get("status") != "passed":
        raise ValueError("check JSON is not a passed summary")
    return mapping


def assert_pinned_consumer_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("status") != "ok":
        raise AssertionError("consumer status must be ok")
    c0 = summary.get("c0")
    c1 = summary.get("c1")
    c2 = summary.get("c2")
    main = summary.get("main_commit")
    if not isinstance(c0, str) or not isinstance(c1, str) or not isinstance(c2, str):
        raise AssertionError("consumer commits must be strings")
    if not c0 or not c1 or not c2:
        raise AssertionError("consumer commits must be non-empty")
    if len({c0, c1, c2}) != 3:
        raise AssertionError("c0, c1 and c2 must be distinct")
    if main != c2:
        raise AssertionError("main must resolve to c2")


def p2r2_compose_env(*, token_file: Path, service_image: str) -> dict[str, str]:
    env = os.environ.copy()
    env["GATEWAY_P2R2_BEARER_TOKEN_FILE"] = str(token_file)
    env["GATEWAY_REPOSITORY_SERVICE_IMAGE"] = service_image
    return env


def host_runner_env(
    *,
    base_url: str,
    bearer_token: str,
    fixture_root: Path = FIXTURE_ROOT,
) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in _DOCKER_CONTROL_ENV or key.startswith("DOCKER_"):
            continue
        if key in _HOST_RUNNER_ENV_ALLOWLIST or key.startswith("UV_"):
            env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(
        ephemeral_client_env(
            base_url=base_url,
            bearer_token=bearer_token,
            fixture_root=fixture_root,
        )
    )
    return env


def start_p2r2_service(
    names: ComposeResourceNames,
    *,
    token_file: Path,
    token: str,
    service_image: str,
    host_paths: Sequence[str],
    env: dict[str, str] | None = None,
    wait: bool = True,
) -> StartedP2R2Service:
    resolved_env = (
        env
        if env is not None
        else p2r2_compose_env(token_file=token_file, service_image=service_image)
    )
    secrets = (token,)
    paths = tuple(host_paths)
    rendered = run_command(
        compose_config_command(project=names.project),
        env=resolved_env,
        secrets=secrets,
        host_paths=paths,
    )
    assert_p2r2_compose_boundary(parse_rendered_compose_config(rendered.stdout))
    gateway_uid = int(
        run_command(
            ["docker", "run", "--rm", "--entrypoint", "id", service_image, "-u", "gateway"],
            secrets=secrets,
            host_paths=paths,
        ).stdout.strip()
    )
    gateway_gid = int(
        run_command(
            ["docker", "run", "--rm", "--entrypoint", "id", service_image, "-g", "gateway"],
            secrets=secrets,
            host_paths=paths,
        ).stdout.strip()
    )
    os.chown(token_file, gateway_uid, gateway_gid)
    run_command(
        compose_up_command(project=names.project),
        env=resolved_env,
        secrets=secrets,
        host_paths=paths,
    )
    container_id = run_command(
        compose_ps_command(project=names.project),
        env=resolved_env,
        secrets=secrets,
        host_paths=paths,
    ).stdout.strip()
    if not container_id:
        raise RuntimeError("repository-service container id is empty")
    if wait:
        wait_healthy(container_id)
    return StartedP2R2Service(
        names=names,
        env=resolved_env,
        token=token,
        token_file=token_file,
        service_image=service_image,
        container_id=container_id,
        host_paths=paths,
    )


def discover_started_service_network(started: StartedP2R2Service) -> ServiceNetworkDiscovery:
    inspected = run_command(
        inspect_networks_command(started.container_id),
        secrets=(started.token,),
        host_paths=started.host_paths,
    )
    return parse_inspect_networks(inspected.stdout, project=started.names.project)


def recreate_started_service(started: StartedP2R2Service) -> StartedP2R2Service:
    run_command(
        force_recreate_service_command(project=started.names.project),
        env=started.env,
        secrets=(started.token,),
        host_paths=started.host_paths,
    )
    container_id = run_command(
        compose_ps_command(project=started.names.project),
        env=started.env,
        secrets=(started.token,),
        host_paths=started.host_paths,
    ).stdout.strip()
    if not container_id:
        raise RuntimeError("repository-service container id is empty after recreate")
    wait_healthy(container_id)
    return StartedP2R2Service(
        names=started.names,
        env=started.env,
        token=started.token,
        token_file=started.token_file,
        service_image=started.service_image,
        container_id=container_id,
        host_paths=started.host_paths,
    )


def run_inside_network_consumer(
    *,
    client_image: str,
    discovery: ServiceNetworkDiscovery,
    token: str,
    env_file: Path,
    secrets: Sequence[str],
    host_paths: Sequence[str],
) -> dict[str, Any]:
    completed = run_inside_network_consumer_unchecked(
        client_image=client_image,
        network=discovery.network_name,
        base_url=discovery.inside_endpoint,
        token=token,
        env_file=env_file,
        secrets=secrets,
        host_paths=host_paths,
    )
    if completed.returncode != 0:
        stdout = redact_evidence_text(completed.stdout, secrets=secrets, host_paths=host_paths)
        stderr = redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)
        raise RuntimeError(
            f"inside-network consumer failed ({completed.returncode})\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    summary = assert_client_stdout_safe(
        completed.stdout,
        secrets=secrets,
        host_paths=host_paths,
    )
    assert_pinned_consumer_summary(summary)
    return summary


def run_inside_network_consumer_unchecked(
    *,
    client_image: str,
    network: str | None,
    base_url: str,
    token: str,
    env_file: Path,
    secrets: Sequence[str],
    host_paths: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    write_client_env_file(
        env_file,
        base_url=base_url,
        bearer_token=token,
    )
    return run_command_unchecked(
        ephemeral_client_docker_command(
            image=client_image,
            fixture_root=FIXTURE_ROOT,
            env_file=env_file,
            network=network,
        ),
        timeout=180.0,
        secrets=secrets,
        host_paths=host_paths,
    )


def run_gate_host_consumer(
    *,
    discovery: ServiceNetworkDiscovery,
    token: str,
    secrets: Sequence[str],
    host_paths: Sequence[str],
) -> dict[str, Any]:
    completed = run_gate_host_consumer_unchecked(
        base_url=discovery.gate_host_endpoint,
        token=token,
        secrets=secrets,
        host_paths=host_paths,
    )
    if completed.returncode != 0:
        stdout = redact_evidence_text(completed.stdout, secrets=secrets, host_paths=host_paths)
        stderr = redact_evidence_text(completed.stderr, secrets=secrets, host_paths=host_paths)
        raise RuntimeError(
            f"gate-host consumer failed ({completed.returncode})\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    summary = assert_client_stdout_safe(
        completed.stdout,
        secrets=secrets,
        host_paths=host_paths,
    )
    assert_pinned_consumer_summary(summary)
    return summary


def run_gate_host_consumer_unchecked(
    *,
    base_url: str,
    token: str,
    secrets: Sequence[str],
    host_paths: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return run_command_unchecked(
        host_runner_command(),
        env=host_runner_env(base_url=base_url, bearer_token=token),
        timeout=180.0,
        secrets=secrets,
        host_paths=host_paths,
    )


def wait_hold_container_ready(
    container: str,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.1,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_logs = ""
    while time.monotonic() < deadline:
        logs = subprocess.run(
            docker_logs_command(container),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        last_logs = logs.stdout
        if logs.returncode == 0 and last_logs.strip():
            try:
                payload = parse_hold_ready_json(last_logs)
            except ValueError:
                payload = None
            if payload is not None:
                running = subprocess.run(
                    docker_container_running_command(container),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if running.returncode == 0 and running.stdout.strip() == "true":
                    return payload
        time.sleep(poll_interval)
    raise TimeoutError(
        "hold container did not become ready: "
        f"{redact_evidence_text(last_logs, secrets=secrets, host_paths=host_paths)}"
    )


def stop_hold_container(
    container: str,
    *,
    project: str,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
) -> None:
    expected = hold_container_name(project)
    if container != expected:
        raise RuntimeError("refusing to signal a hold helper outside the generated project")
    run_command(
        docker_stop_signal_command(container),
        secrets=secrets,
        host_paths=host_paths,
    )
    exit_code = run_command(
        docker_inspect_exit_code_command(container),
        secrets=secrets,
        host_paths=host_paths,
    ).stdout.strip()
    if exit_code != "0":
        raise RuntimeError(f"hold helper exited {exit_code}, expected 0")


def remove_hold_container(project: str) -> None:
    name = hold_container_name(project)
    existing = inspect_hold_container(project)
    if existing is None:
        return
    completed = subprocess.run(
        ["docker", "rm", "-f", name],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"failed to remove hold container {name}: {completed.stderr.strip()}")
    if inspect_hold_container(project) is not None:
        raise AssertionError(f"hold container {name} still exists after removal")


def collect_volume_query_temps(*, image: str, volume: str) -> tuple[str, ...]:
    inspect = subprocess.run(
        ["docker", "volume", "inspect", volume],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if inspect.returncode != 0:
        return ()
    completed = subprocess.run(
        query_temp_listing_command(image=image, volume=volume),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.lower()
        if "no such file" in stderr:
            return ()
        raise RuntimeError(
            f"query-temp listing failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    found: list[str] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if stripped.endswith(".sql") and Path(stripped).name.startswith("query-"):
            found.append(stripped)
    return tuple(found)


def collect_project_query_temps(
    names: ComposeResourceNames,
    *,
    image: str | None,
) -> tuple[str, ...]:
    if image is None:
        return ()
    found: list[str] = []
    for volume in (names.data_volume, names.restore_volume):
        found.extend(collect_volume_query_temps(image=image, volume=volume))
    return tuple(found)


def container_has_dolt(container: str) -> bool:
    running = subprocess.run(
        docker_container_running_command(container),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if running.returncode != 0 or running.stdout.strip() != "true":
        return False
    for extra in (["-eo", "comm"], []):
        completed = subprocess.run(
            ["docker", "top", container, *extra],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            continue
        for line in completed.stdout.splitlines():
            if re.search(r"(^|\s)dolt(\s|$)", line):
                return True
        return False
    return False


def list_project_container_dolt(project: str) -> tuple[str, ...]:
    return tuple(
        container
        for container in docker_objects(project, "container")
        if container_has_dolt(container)
    )


def list_host_client_pids() -> frozenset[int]:
    marker = str(CONSUMER_SCRIPT)
    proc = Path("/proc")
    if not proc.is_dir():
        return frozenset()
    pids: set[int] = set()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                "utf-8",
                "replace",
            )
        except OSError:
            continue
        if marker in cmdline:
            pids.add(int(entry.name))
    return frozenset(pids)


def list_work_root_project_dirs(work_root: Path | None, *, project: str) -> tuple[str, ...]:
    found: list[str] = []
    roots = [Path("/tmp")]
    if work_root is not None:
        roots.append(work_root)
    for root in roots:
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name.startswith(project):
                found.append(str(child))
    return tuple(sorted(set(found)))


def list_host_thread_idents() -> frozenset[int]:
    main = threading.main_thread()
    idents: set[int] = set()
    for thread in threading.enumerate():
        ident = thread.ident
        if ident is None or thread is main:
            continue
        idents.add(ident)
    return frozenset(idents)


def format_teardown_scan(
    *,
    project: str,
    container_dolt: Sequence[str],
    query_temps: Sequence[str],
) -> str:
    return (
        f"teardown_scan project={project} "
        f"container_dolt={len(container_dolt)} query_temps={len(query_temps)}"
    )


def format_residual_inventory(
    *,
    project: str,
    leftover: DockerObjectInventory,
    dolt_delta: int | None,
    check_temp_homes: int | None,
    client_pids: int | None,
    host_threads: int | None,
    work_root_dirs: int | None,
) -> str:
    def _count(value: int | None) -> str:
        return "unchecked" if value is None else str(value)

    return (
        f"residual_inventory project={project} "
        f"containers={len(leftover.containers)} "
        f"networks={len(leftover.networks)} "
        f"volumes={len(leftover.volumes)} "
        f"hold={len(leftover.hold_containers)} "
        f"dolt_delta={_count(dolt_delta)} "
        f"check_temp_homes={_count(check_temp_homes)} "
        f"client_pids={_count(client_pids)} "
        f"host_threads={_count(host_threads)} "
        f"work_root_dirs={_count(work_root_dirs)}"
    )


def assert_node_residuals_cleared(
    names: ComposeResourceNames,
    *,
    work_root: Path | None = None,
    dolt_baseline: frozenset[int] | None = None,
    check_temp_baseline: frozenset[str] | None = None,
    client_pid_baseline: frozenset[int] | None = None,
    thread_baseline: frozenset[int] | None = None,
) -> None:
    leftover = project_inventory(names.project)
    if not leftover.is_empty():
        raise AssertionError(
            f"project {names.project} still has Docker objects: "
            f"containers={leftover.containers!r} networks={leftover.networks!r} "
            f"volumes={leftover.volumes!r} hold={leftover.hold_containers!r}"
        )
    dolt_delta: int | None = None
    if dolt_baseline is not None:
        extra_dolt = frozenset(list_dolt_pids()) - dolt_baseline
        if extra_dolt:
            raise AssertionError(f"dolt children remain: {sorted(extra_dolt)}")
        dolt_delta = 0
    check_temp_homes: int | None = None
    if check_temp_baseline is not None:
        extra_homes = {str(path) for path in snapshot_check_temp_homes()} - check_temp_baseline
        if extra_homes:
            raise AssertionError(f"snapshot check temp homes remain: {sorted(extra_homes)}")
        check_temp_homes = 0
    work_root_dirs: int | None = None
    if work_root is not None:
        project_dirs = list_work_root_project_dirs(work_root, project=names.project)
        if project_dirs:
            raise AssertionError(f"work-root project dirs remain: {project_dirs}")
        work_root_dirs = 0
    client_pids: int | None = None
    if client_pid_baseline is not None:
        extra_clients = list_host_client_pids() - client_pid_baseline
        if extra_clients:
            raise AssertionError(f"client processes remain: {sorted(extra_clients)}")
        client_pids = 0
    host_threads: int | None = None
    if thread_baseline is not None:
        extra_threads = list_host_thread_idents() - thread_baseline
        if extra_threads:
            raise AssertionError(f"host threads remain: {sorted(extra_threads)}")
        host_threads = 0
    print(
        format_residual_inventory(
            project=names.project,
            leftover=leftover,
            dolt_delta=dolt_delta,
            check_temp_homes=check_temp_homes,
            client_pids=client_pids,
            host_threads=host_threads,
            work_root_dirs=work_root_dirs,
        ),
        flush=True,
    )


@contextmanager
def p2r2_project_session(
    names: ComposeResourceNames,
    env: dict[str, str],
    *,
    secrets: Sequence[str] = (),
    host_paths: Sequence[str] = (),
    service_image: str | None = None,
    work_root: Path | None = None,
    dolt_baseline: frozenset[int] | None = None,
    check_temp_baseline: frozenset[str] | None = None,
    client_pid_baseline: frozenset[int] | None = None,
    thread_baseline: frozenset[int] | None = None,
) -> Iterator[None]:
    try:
        yield
    finally:
        cleanup_compose_project(
            names,
            env,
            secrets=secrets,
            host_paths=host_paths,
            service_image=service_image,
            work_root=work_root,
            dolt_baseline=dolt_baseline,
            check_temp_baseline=check_temp_baseline,
            client_pid_baseline=client_pid_baseline,
            thread_baseline=thread_baseline,
        )


def create_scoped_volume(volume: str, *, allowed: frozenset[str]) -> None:
    refuse_unscoped_deletion((volume,), allowed)
    run_command(volume_create_command(volume))


def assert_named_volume_empty(*, image: str, volume: str, allowed: frozenset[str]) -> None:
    refuse_unscoped_deletion((volume,), allowed)
    listing = run_command(volume_listing_command(image=image, volume=volume))
    assert_restore_volume_listing_empty(parse_volume_listing(listing.stdout))


def copy_named_volume(
    *,
    image: str,
    source_volume: str,
    dest_volume: str,
    allowed: frozenset[str],
) -> None:
    refuse_unscoped_deletion((source_volume, dest_volume), allowed)
    run_command(
        copy_volume_command(image=image, source_volume=source_volume, dest_volume=dest_volume)
    )
    run_command(chown_volume_command(image=image, volume=dest_volume))


def check_named_volume(*, image: str, volume: str, allowed: frozenset[str]) -> dict[str, Any]:
    refuse_unscoped_deletion((volume,), allowed)
    completed = run_command(snapshot_check_command(image=image, volume=volume))
    return parse_check_passed_json(completed.stdout)


def create_repository_via_http(*, base_url: str, token: str, idempotency_key: str) -> str:
    assert_not_host_port_endpoint(base_url)
    request = Request(
        f"{base_url.rstrip('/')}/v1/repositories",
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": idempotency_key,
            "Content-Length": "0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload: object = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("create repository over HTTP failed") from exc
    mapping = _require_mapping(payload, field="create_repository")
    repository_id = mapping.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id:
        raise RuntimeError("create repository response is missing repository_id")
    UUID(repository_id)
    return repository_id


def versioned_ref_status(*, base_url: str, token: str, repository_id: str) -> int:
    assert_not_host_port_endpoint(base_url)
    request = Request(
        f"{base_url.rstrip('/')}/v1/repositories/{repository_id}/versioned/refs/main",
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("versioned ref request failed") from exc
