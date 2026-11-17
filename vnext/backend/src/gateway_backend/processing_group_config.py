"""Bounded, typed host directory and processing-group deployment documents.

Pure parsing and append checks only. Filesystem ownership/mounts and aggregate
resource validation are performed by the deployment preflight owner.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from .deployment_config import HostBudget, _integer, _number, _object, _pairs, _path
from .device_identity import device_route_key, validate_deployment_identity, validate_scope_identity

MAX_DIRECTORY_BYTES = 8 * 1024 * 1024
MAX_DIRECTORY_DEVICES = 10000
MAX_GROUPS_BYTES = 1024 * 1024
MAX_GROUPS = 32
_IMAGE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._/:-]*(?:@sha256:[0-9a-f]{64})?\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_PROJECT = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}\Z")


def _document(raw: bytes, limit: int) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > limit:
        raise ValueError("processing-group document exceeds byte limit")

    def invalid_constant(value: str) -> object:
        raise ValueError("non-finite JSON constant")

    try:
        value: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid_constant
        )
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("processing-group document is invalid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ValueError("processing-group document must be an object")
    return cast(dict[str, object], value)


def _header(doc: dict[str, object]) -> str:
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise ValueError("unsupported processing-group schema_version")
    return validate_deployment_identity(doc["environment_id"])


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def _serialize(model: DeviceDirectory | ProcessingGroupsConfig) -> bytes:
    return (
        json.dumps(
            asdict(model),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class DeviceDirectoryEntry:
    gateway_device_external_key: str
    group_id: str
    enabled: bool

    @property
    def route_key(self) -> str:
        return device_route_key(self.gateway_device_external_key)


@dataclass(frozen=True, slots=True)
class DeviceDirectory:
    schema_version: int
    environment_id: str
    devices: tuple[DeviceDirectoryEntry, ...]

    @classmethod
    def from_bytes(cls, raw: bytes, *, known_groups: set[str] | frozenset[str]) -> DeviceDirectory:
        doc = _object(
            _document(raw, MAX_DIRECTORY_BYTES), {"schema_version", "environment_id", "devices"}
        )
        environment = _header(doc)
        rows = doc["devices"]
        if type(rows) is not list or len(rows) > MAX_DIRECTORY_DEVICES:
            raise ValueError("device directory must contain at most 10000 devices")
        entries: list[DeviceDirectoryEntry] = []
        devices: set[str] = set()
        keys: set[str] = set()
        for row in rows:
            item = _object(row, {"gateway_device_external_key", "group_id", "enabled"})
            device = validate_scope_identity(item["gateway_device_external_key"])
            group = validate_deployment_identity(item["group_id"])
            if group not in known_groups:
                raise ValueError("device directory references unknown group")
            enabled = item["enabled"]
            if type(enabled) is not bool:
                raise ValueError("device directory enabled must be boolean")
            entry = DeviceDirectoryEntry(device, group, enabled)
            if device in devices or entry.route_key in keys:
                raise ValueError("device directory has duplicate device or colliding route key")
            devices.add(device)
            keys.add(entry.route_key)
            entries.append(entry)
        return cls(1, environment, tuple(entries))

    @classmethod
    def load(cls, path: Path, *, known_groups: set[str] | frozenset[str]) -> DeviceDirectory:
        return cls.from_bytes(_read(path, MAX_DIRECTORY_BYTES), known_groups=known_groups)

    def to_bytes(self) -> bytes:
        return _serialize(self)

    def require_append_only(self, previous: DeviceDirectory) -> None:
        if self.environment_id != previous.environment_id:
            raise ValueError("device directory environment cannot change")
        current = {item.gateway_device_external_key: item for item in self.devices}
        for old in previous.devices:
            new = current.get(old.gateway_device_external_key)
            if new is None or new.group_id != old.group_id or (old.enabled and not new.enabled):
                raise ValueError(
                    "existing device reservation cannot be removed, rebound or disabled"
                )

    def require_reservation(self, device: str, group: str) -> DeviceDirectoryEntry:
        validate_scope_identity(device)
        for entry in self.devices:
            if entry.gateway_device_external_key == device and entry.group_id == group:
                return entry
        raise ValueError("device has no reservation in this group")


@dataclass(frozen=True, slots=True)
class EntryDeployment:
    listen_address: str
    listen_port: int
    management_port: int
    image: str
    memory_limit_bytes: int
    cpu_limit: float


@dataclass(frozen=True, slots=True)
class GroupImages:
    backend: str
    worker: str
    repository_service: str
    revision: str


@dataclass(frozen=True, slots=True)
class GroupDeployment:
    group_id: str
    project: str
    backend_port: int
    storage_config: str
    resource_config: str
    session_directory: str
    internal_token_file: str
    repository_token_file: str
    images: GroupImages

    @property
    def backend_endpoint(self) -> str:
        # Caller input never becomes a URL. Linux host-network entry uses this loopback endpoint.
        return f"http://127.0.0.1:{self.backend_port}"


def _image(value: object) -> str:
    if (
        type(value) is not str
        or len(value) > 255
        or "://" in value
        or _IMAGE.fullmatch(value) is None
    ):
        raise ValueError("image must be an explicit image reference")
    if "@sha256:" not in value:
        tag = value.rsplit("/", 1)[-1].split(":")
        if len(tag) != 2 or not tag[1] or tag[1].lower() == "latest":
            raise ValueError("image requires a fixed non-latest tag or digest")
    return value


def _port(value: object) -> int:
    return _integer(value, maximum=65535)


def _controlled_path(value: object) -> str:
    value = _path(value)
    if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("configuration path contains invalid characters")
    return value


@dataclass(frozen=True, slots=True)
class ProcessingGroupsConfig:
    schema_version: int
    environment_id: str
    host: HostBudget
    entry: EntryDeployment
    groups: tuple[GroupDeployment, ...]

    @classmethod
    def from_bytes(cls, raw: bytes) -> ProcessingGroupsConfig:
        doc = _object(
            _document(raw, MAX_GROUPS_BYTES),
            {"schema_version", "environment_id", "host", "entry", "groups"},
        )
        environment = _header(doc)
        host_raw = _object(
            doc["host"],
            {"memory_bytes", "cpu_count", "shared_memory_reserve_bytes", "shared_cpu_reserve"},
        )
        host = HostBudget(
            _integer(host_raw["memory_bytes"]),
            _integer(host_raw["cpu_count"]),
            _integer(host_raw["shared_memory_reserve_bytes"], minimum=0),
            _number(host_raw["shared_cpu_reserve"], allow_zero=True),
        )
        row = _object(
            doc["entry"],
            {
                "listen_address",
                "listen_port",
                "management_port",
                "image",
                "memory_limit_bytes",
                "cpu_limit",
            },
        )
        # Bind literals are deliberately finite; no Nginx, shell or caller URL interpolation.
        address = row["listen_address"]
        if type(address) is not str or address not in {"0.0.0.0", "127.0.0.1", "::", "::1"}:
            raise ValueError("entry listen_address must be a supported IP bind literal")
        entry = EntryDeployment(
            address,
            _port(row["listen_port"]),
            _port(row["management_port"]),
            _image(row["image"]),
            _integer(row["memory_limit_bytes"]),
            _number(row["cpu_limit"]),
        )
        rows = doc["groups"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_GROUPS:
            raise ValueError("groups must contain 1..32 groups")
        groups: list[GroupDeployment] = []
        for row in rows:
            item = _object(
                row,
                {
                    "group_id",
                    "project",
                    "backend_port",
                    "storage_config",
                    "resource_config",
                    "session_directory",
                    "internal_token_file",
                    "repository_token_file",
                    "images",
                },
            )
            project = item["project"]
            if type(project) is not str or _PROJECT.fullmatch(project) is None:
                raise ValueError("compose project is invalid")
            images_raw = _object(
                item["images"], {"backend", "worker", "repository_service", "revision"}
            )
            revision = images_raw["revision"]
            if type(revision) is not str or _REVISION.fullmatch(revision) is None:
                raise ValueError("image revision must be a complete lowercase Git SHA")
            images = GroupImages(
                _image(images_raw["backend"]),
                _image(images_raw["worker"]),
                _image(images_raw["repository_service"]),
                revision,
            )
            groups.append(
                GroupDeployment(
                    validate_deployment_identity(item["group_id"]),
                    project,
                    _port(item["backend_port"]),
                    _controlled_path(item["storage_config"]),
                    _controlled_path(item["resource_config"]),
                    _controlled_path(item["session_directory"]),
                    _controlled_path(item["internal_token_file"]),
                    _controlled_path(item["repository_token_file"]),
                    images,
                )
            )
        if len({group.group_id for group in groups}) != len(groups) or len(
            {group.project for group in groups}
        ) != len(groups):
            raise ValueError("group identities and projects must be unique")
        ports = [
            entry.listen_port,
            entry.management_port,
            *(group.backend_port for group in groups),
        ]
        if len(set(ports)) != len(ports):
            raise ValueError("entry and backend ports must be distinct")
        secret_files = [
            path
            for group in groups
            for path in (group.internal_token_file, group.repository_token_file)
        ]
        if len(set(secret_files)) != len(secret_files):
            raise ValueError("group token files must be distinct")
        if len({group.session_directory for group in groups}) != len(groups):
            raise ValueError("group session directories must be distinct")
        return cls(1, environment, host, entry, tuple(groups))

    @classmethod
    def load(cls, path: Path) -> ProcessingGroupsConfig:
        return cls.from_bytes(_read(path, MAX_GROUPS_BYTES))

    def to_bytes(self) -> bytes:
        return _serialize(self)

    @property
    def group_ids(self) -> frozenset[str]:
        return frozenset(group.group_id for group in self.groups)

    def require_directory(self, directory: DeviceDirectory) -> None:
        if directory.environment_id != self.environment_id or any(
            item.group_id not in self.group_ids for item in directory.devices
        ):
            raise ValueError("directory deployment does not match groups configuration")
