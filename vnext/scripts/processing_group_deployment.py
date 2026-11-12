"""Read-only whole-host deployment checks and exact Compose isolation inspection."""
from __future__ import annotations

import hashlib
import os
import ipaddress
from pathlib import Path
import stat
from typing import Any

import host_runtime_config as host
from processing_group_config import DeviceDirectory, ProcessingGroupsConfig
from worker_deployment import _docker, inspect_project, validate_workers, worker_services
import json


def _ordinary(path: Path) -> bytes:
    host.preflight.nofollow_directory(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("deployment file must be a server-owned ordinary file")
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("deployment file exceeds bound")
    return raw


def _overlaps(paths: list[tuple[str, Path]]) -> None:
    for index, (owner, path) in enumerate(paths):
        for other_owner, other in paths[:index]:
            if path == other or path in other.parents or other in path.parents:
                raise ValueError("deployment paths overlap: " + owner + "/" + other_owner)


def _physical_path(path: Path, observed: Any) -> Path:
    info = path.stat()
    mount = max((item for item in observed if Path(item.target) == path or Path(item.target) in path.parents),
        key=lambda item: len(item.target))
    return Path("/device-" + str(info.st_dev)) / mount.root.lstrip("/") / path.relative_to(mount.target)


def check_public_directory(groups: ProcessingGroupsConfig, parent: Path) -> None:
    """A public parent bind must not expose any group's private files or roots."""
    host.preflight.nofollow_directory(parent)
    observed = host.mounts()
    if any(Path(item.target) != parent and parent in Path(item.target).parents for item in observed):
        raise ValueError("public configuration directory must not contain child mounts")
    public = _physical_path(parent, observed)
    for group in groups.groups:
        config = host.DeploymentConfig.load(Path(group.storage_config), Path(group.resource_config))
        paths = [Path(group.session_directory), Path(group.internal_token_file), Path(group.repository_token_file),
            *(Path(root.source) for root in config.storage.roots.values())]
        for private in paths:
            # Reject string nesting before requiring a root's existing inode.
            _overlaps([("public", parent), ("private", private)])
            _overlaps([("public", public), ("private", _physical_path(private, observed))])


def load_configs(groups: ProcessingGroupsConfig) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    memory = groups.entry.memory_limit_bytes + groups.host.shared_memory_reserve_bytes
    cpu = groups.entry.cpu_limit + groups.host.shared_cpu_reserve
    paths: list[tuple[str, Path]] = []
    secrets: set[bytes] = set()
    for group in groups.groups:
        _ordinary(Path(group.storage_config))
        _ordinary(Path(group.resource_config))
        config = host.DeploymentConfig.load(Path(group.storage_config), Path(group.resource_config))
        if (config.storage.environment_id != groups.environment_id or config.storage.group_id != group.group_id
                or config.resources.host_budget != groups.host):
            raise ValueError("group configuration differs from deployment manifest")
        configs[group.group_id] = config
        resources = config.resources
        memory += resources.worker.count * resources.worker.memory_envelope_bytes + resources.backend.memory_limit_bytes + resources.repository_service.memory_limit_bytes
        cpu += resources.worker.count * resources.worker.cpu_limit + resources.backend.cpu_limit + resources.repository_service.cpu_limit
        paths.extend((group.group_id + "/" + slot, Path(root.source)) for slot, root in config.storage.roots.items())
        session = Path(group.session_directory)
        host.preflight.nofollow_directory(session)
        _ordinary(session / "session.json")
        paths.append((group.group_id + "/session", session))
        for filename in (group.internal_token_file, group.repository_token_file):
            raw = _ordinary(Path(filename)).strip()
            if not raw or b"\n" in raw or b"\r" in raw:
                raise ValueError("invalid group credential file")
            digest = hashlib.sha256(raw).digest()
            if digest in secrets:
                raise ValueError("group credentials must be distinct")
            secrets.add(digest)
            paths.append((group.group_id + "/credential", Path(filename)))
    _overlaps(paths)
    observed = host.mounts()
    physical = [(owner, _physical_path(path, observed)) for owner, path in paths]
    _overlaps(physical)
    if memory > groups.host.memory_bytes or cpu > groups.host.cpu_count:
        raise ValueError("all groups and entry exceed host planning budget")
    return configs


def validate_group_containers(config: Any, group: Any, containers: list[dict[str, Any]], *,
                              allowed_states: tuple[str, ...] = ("running",),
                              image_identities: dict[str, dict[str, Any]] | None = None,
                              network_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    workers = validate_workers(config, group.project, containers, allowed_states=allowed_states)
    expected = {"backend", "repository-service", *worker_services(config.resources.worker.count)}
    found: dict[str, Any] = {}
    images = {"backend": group.images.backend, "repository-service": group.images.repository_service}
    for item in containers:
        labels = item["Config"].get("Labels") or {}
        service = labels.get("com.docker.compose.service", "")
        if (labels.get("com.docker.compose.project") != group.project or service not in expected or service in found
                or labels.get("com.docker.compose.container-number") != "1"
                or labels.get("com.docker.compose.oneoff", "False").lower() != "false"
                or item["State"]["Status"] not in allowed_states):
            raise ValueError("unexpected group service identity/state")
        if labels.get("org.opencontainers.image.revision") != group.images.revision:
            raise ValueError("actual group image revision differs")
        role = "worker" if service in workers else "repository_service" if service == "repository-service" else "backend"
        profile = getattr(config.resources, role)
        memory = profile.memory_envelope_bytes if role == "worker" else profile.memory_limit_bytes
        actual = item["HostConfig"]
        if (actual["Memory"] != memory or actual["MemorySwap"] != memory + profile.swap_limit_bytes
                or actual["NanoCpus"] != round(profile.cpu_limit * 1_000_000_000)
                or item["Config"]["Image"] != images.get(service, group.images.worker)):
            raise ValueError("actual group image/resources differ")
        if image_identities is not None:
            expected_image = image_identities[item["Config"]["Image"]]
            if (expected_image["Id"] != item["Image"]
                    or (expected_image["Config"].get("Labels") or {}).get("org.opencontainers.image.revision") != group.images.revision):
                raise ValueError("running image does not match the selected local image/revision")
        if set(item["NetworkSettings"]["Networks"]) != {group.project + "_default"}:
            raise ValueError("group services must use only their private Compose network")
        if network_identity is not None:
            network = item["NetworkSettings"]["Networks"][group.project + "_default"]
            if item["State"]["Status"] == "running" and network.get("NetworkID") != network_identity["Id"]:
                raise ValueError("group service uses an unexpected actual network identity")
        environment = dict(value.split("=", 1) for value in item["Config"]["Env"])
        if role != "repository_service":
            prefix = "GATEWAY_BACKEND_" if role == "backend" else "GATEWAY_BACKEND_OPERATION_WORKER_"
            if (environment.get(prefix + "REPOSITORY_BASE_URL") != "http://repository-service:8000"
                    or environment.get(prefix + "REPOSITORY_BEARER_TOKEN_FILE") != "/run/secrets/repository-bearer-token"):
                raise ValueError("group repository endpoint/credential wiring differs")
        bindings = actual.get("PortBindings") or {}
        if role == "backend":
            if bindings != {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(group.backend_port)}]}:
                raise ValueError("backend must publish only its configured loopback port")
        elif bindings:
            raise ValueError("worker and Repository Service must not publish host ports")
        expected_mounts = {root.path: (root.source, True) for root in config.storage.role_roots(role).values()}
        expected_mounts.update({"/run/gateway/storage-layout.json": (group.storage_config, False),
            "/run/gateway/resource-profile.json": (group.resource_config, False),
            "/run/secrets/repository-bearer-token": (group.repository_token_file, False)})
        if role == "backend":
            expected_mounts.update({"/run/gateway/session": (group.session_directory, False),
                "/run/secrets/backend-internal-bearer": (group.internal_token_file, False)})
        mounts = {entry["Destination"]: entry for entry in item["Mounts"]}
        for target, (source, writable) in expected_mounts.items():
            actual_mount = mounts.get(target)
            if actual_mount is None or actual_mount["Type"] != "bind" or actual_mount["Source"] != source or actual_mount["RW"] != writable:
                raise ValueError("actual group bind mount differs: " + service)
        allowed_extra = {"/run/gateway/groups", "/run/gateway/provisioned-mapping.json"} if role != "repository_service" else set()
        if set(mounts) - set(expected_mounts) - allowed_extra:
            raise ValueError("unexpected mount in group container")
        if role != "repository_service":
            directory = mounts.get("/run/gateway/groups")
            if directory is None or directory["Type"] != "bind" or directory["RW"]:
                raise ValueError("group directory must be a read-only parent bind")
            environment = dict(value.split("=", 1) for value in item["Config"]["Env"])
            prefix = "GATEWAY_BACKEND_" if role == "backend" else "GATEWAY_BACKEND_OPERATION_WORKER_"
            source = Path(directory["Source"])
            documents: dict[str, Path] = {}
            for suffix in ("PROCESSING_GROUPS_FILE", "DEVICE_DIRECTORY_FILE"):
                configured = Path(environment.get(prefix + suffix, ""))
                if configured.parent != Path("/run/gateway/groups"):
                    raise ValueError("group document must use the bound parent directory")
                documents[suffix] = source / configured.name
            manifest = ProcessingGroupsConfig.from_bytes(_ordinary(documents["PROCESSING_GROUPS_FILE"]))
            if manifest.environment_id != config.storage.environment_id or group not in manifest.groups:
                raise ValueError("mounted group manifest differs from selected group")
            check_public_directory(manifest, source)
            manifest.require_directory(DeviceDirectory.load(documents["DEVICE_DIRECTORY_FILE"], known_groups=manifest.group_ids))
            seed = mounts.get("/run/gateway/provisioned-mapping.json")
            if seed is None or seed["Type"] != "bind" or seed["RW"]:
                raise ValueError("seed must be a read-only bind")
            if role == "backend" and environment.get("GATEWAY_BACKEND_SESSION_FILE") != "/run/gateway/session/session.json":
                raise ValueError("session must use its live parent-directory bind")
        found[service] = {"container_id": item["Id"], "image": item["Image"], "state": item["State"]["Status"]}
    if set(found) != expected:
        raise ValueError("missing group services")
    return found


def default_gateway(raw: str) -> str:
    """Read the same kernel default-route fact used by the internal HTTP boundary."""
    if len(raw) > 65536:
        raise ValueError("group network route observation exceeds bound")
    gateways = []
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 8 and fields[1] == "00000000" and fields[7] == "00000000" and int(fields[3], 16) & 3 == 3:
            gateways.append(str(ipaddress.IPv4Address(bytes.fromhex(fields[2])[::-1])))
    if len(gateways) != 1 or gateways[0] == "0.0.0.0":
        raise ValueError("group must have one active IPv4 host gateway")
    return gateways[0]


def inspect_group(config: Any, group: Any, *, allowed_states: tuple[str, ...] = ("running",),
                  containers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    refs = (group.images.backend, group.images.worker, group.images.repository_service)
    images = json.loads(_docker("image", "inspect", *refs))
    identities = dict(zip(refs, images, strict=True))
    networks = json.loads(_docker("network", "inspect", group.project + "_default"))
    if len(networks) != 1:
        raise ValueError("missing unique group Compose network")
    network = networks[0]
    labels = network.get("Labels") or {}
    if (network["Name"] != group.project + "_default" or network["Driver"] != "bridge"
            or labels.get("com.docker.compose.project") != group.project
            or labels.get("com.docker.compose.network") != "default"):
        raise ValueError("group network is not owned by the selected Compose project")
    selected = inspect_project(group.project) if containers is None else containers
    expected_peers = {item["Id"] for item in selected if item["State"]["Status"] == "running"}
    if set(network.get("Containers") or {}) != expected_peers:
        raise ValueError("group network has an unexpected attached peer")
    result = validate_group_containers(config, group, selected,
        allowed_states=allowed_states, image_identities=identities, network_identity=network)
    backend = next(item for item in selected if item["Config"]["Labels"]["com.docker.compose.service"] == "backend")
    if backend["State"]["Status"] == "running":
        gateway = default_gateway(_docker("exec", backend["Id"], "cat", "/proc/net/route"))
        configured = [row["Gateway"] for row in network["IPAM"]["Config"]
            if row.get("Gateway") and isinstance(ipaddress.ip_address(row["Gateway"]), ipaddress.IPv4Address)]
        if configured != [gateway]:
            raise ValueError("backend default route differs from its controlled host gateway")
        result["backend"]["host_gateway"] = gateway
    return result


def check_groups(groups: ProcessingGroupsConfig, *, markers: bool = True, inspect: bool = False) -> dict[str, object]:
    configs = load_configs(groups)
    physical_paths: list[tuple[str, Path]] = []
    filesystems: dict[int, dict[str, object]] = {}
    observed = host.mounts()
    result: dict[str, object] = {}
    for group in groups.groups:
        config = configs[group.group_id]
        host.check_host(config, markers=markers)
        for slot, root in config.storage.roots.items():
            path = Path(root.source)
            info = path.stat()
            mount = max((item for item in observed if Path(item.target) == path or Path(item.target) in path.parents), key=lambda item: len(item.target))
            physical_paths.append((group.group_id + "/" + slot, Path("/" + mount.device) / mount.root.lstrip("/") / path.relative_to(mount.target)))
            policy = config.storage.filesystems[root.filesystem_id]
            bounds = (policy.min_free_bytes, policy.min_free_fraction)
            if info.st_dev in filesystems:
                if filesystems[info.st_dev]["capacity_policy"] != bounds:
                    raise ValueError("same physical filesystem has conflicting capacity policies")
            else:
                free = os.statvfs(path)
                filesystems[info.st_dev] = {"available_bytes": free.f_bavail * free.f_frsize,
                    "available_inodes": free.f_favail, "capacity_policy": bounds}
        result[group.group_id] = (inspect_group(config, group) if inspect
            else {"storage_digest": config.storage.digest, "resource_digest": config.resources.digest})
    _overlaps(physical_paths)
    return {"groups": result, "filesystems": {str(key): value for key, value in filesystems.items()}}
