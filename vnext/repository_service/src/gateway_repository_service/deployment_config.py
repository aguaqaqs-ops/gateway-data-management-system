"""Strict deployment document adapter. Runtime mount/cgroup checks belong to bootstrap."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping, TypeGuard, cast

import rfc8785

MAX_CONFIG_BYTES = 256 * 1024
MAX_FILESYSTEMS = 10
SLOTS = frozenset({"be-durable", "be-canonical", "be-comparison", "be-export", "be-scratch",
    "be-metadata", "rs-repository", "rs-artifacts", "rs-scratch", "rs-metadata"})
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_STORAGE_ID = re.compile(r"[0-9a-f]{32}\Z")
_GIB = 1024 ** 3


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("configuration has missing or unknown fields")
    return cast(dict[str, object], value)


def _integer(value: object, *, minimum: int = 1, maximum: int = 2**53 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("configuration integer outside supported bounds")
    return value


def _number(value: object, *, allow_zero: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError("configuration number must be finite")
    try:
        result = float(cast(int | float, value))
    except OverflowError as exc:
        raise ValueError("configuration number exceeds supported bounds") from exc
    if not math.isfinite(result) or result < 0 or (not allow_zero and result == 0):
        raise ValueError("configuration number must be finite and positive")
    return result


def _identity(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError("configuration identity is invalid")
    return value


def _path(value: object, *, allow_root: bool = False) -> str:
    if type(value) is not str or not value.startswith("/") or value.startswith("//") or "\x00" in value or "\\" in value:
        raise ValueError("configuration path must be absolute POSIX")
    path = PurePosixPath(value)
    if ".." in path.parts or str(path) != value or (value == "/" and not allow_root):
        raise ValueError("configuration path must be normalized and non-root")
    return value


def _distinct_paths(paths: list[str]) -> None:
    for index, path in enumerate(paths):
        for other in paths[index + 1:]:
            left, right = PurePosixPath(path), PurePosixPath(other)
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("storage roots must be distinct and non-nested")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate configuration key")
        result[key] = value
    return result


def _document(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("configuration exceeds 256 KiB")
    def invalid_constant(value: str) -> object:
        raise ValueError("non-finite JSON constant")
    value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=invalid_constant)
    if type(value) is not dict:
        raise ValueError("configuration must be an object")
    return cast(dict[str, object], value)


type _JcsValue = bool | int | float | str | None | list[_JcsValue] | dict[str, _JcsValue]


def _validate_jcs_domain(value: object) -> TypeGuard[_JcsValue]:
    # Keep the deployment format's I-JSON/Unicode gates independent of other services.
    if isinstance(value, str):
        for codepoint in map(ord, value):
            if (0xD800 <= codepoint <= 0xDFFF or 0xFDD0 <= codepoint <= 0xFDEF
                    or (codepoint & 0xFFFE) == 0xFFFE):
                raise ValueError("configuration contains invalid Unicode")
    elif type(value) is int:
        if not -(2**53) + 1 <= value <= 2**53 - 1:
            raise ValueError("configuration integer outside I-JSON bounds")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("configuration number must be finite")
    elif isinstance(value, list):
        for item in value:
            _validate_jcs_domain(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("configuration object key must be a string")
            _validate_jcs_domain(key)
            _validate_jcs_domain(item)
    elif value is not None and not isinstance(value, bool):
        raise ValueError("configuration contains a non-JSON value")
    return True


def _validate_jcs_domain(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF or 0xFDD0 <= ord(char) <= 0xFDEF
               or ord(char) & 0xFFFF in (0xFFFE, 0xFFFF) for char in value):
            raise ValueError("configuration is outside the JCS/I-JSON domain")
    elif type(value) in (int, float):
        if abs(value) > 2**53 - 1 or not math.isfinite(value):
            raise ValueError("configuration is outside the JCS/I-JSON domain")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_jcs_domain(key)
            _validate_jcs_domain(item)
    elif isinstance(value, list):
        for item in value:
            _validate_jcs_domain(item)


def _configuration_digest(document: dict[str, object]) -> str:
    # The host renderer needs only stdlib structural validation; services compute
    # stable observations with the existing owning JCS implementation on demand.
    from gateway_shared_kernel import raw_blob_digest
    from gateway_shared_kernel.jcs import canonicalize_json_value
    return raw_blob_digest(canonicalize_json_value(document)).value


def _header(document: dict[str, object]) -> tuple[str, str]:
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("unsupported configuration schema_version")
    return _identity(document["environment_id"]), _identity(document["group_id"])


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    return raw


@dataclass(frozen=True, slots=True)
class FilesystemPolicy:
    mountpoint: str
    expected_source: str
    min_free_bytes: int
    min_free_fraction: float


@dataclass(frozen=True, slots=True)
class StorageRoot:
    source: str
    path: str
    filesystem_id: str
    storage_id: str
    mount_mode: str


@dataclass(frozen=True, slots=True)
class StorageLayoutConfig:
    environment_id: str
    group_id: str
    filesystems: Mapping[str, FilesystemPolicy]
    roots: Mapping[str, StorageRoot]
    _canonical_document: dict[str, object]

    @property
    def digest(self) -> str:
        return _configuration_digest(self._canonical_document)

    @classmethod
    def from_bytes(cls, raw: bytes) -> StorageLayoutConfig:
        doc = _object(_document(raw), {"schema_version", "environment_id", "group_id", "filesystems", "roots"})
        _validate_jcs_domain(doc)
        environment_id, group_id = _header(doc)
        fs_raw = doc["filesystems"]
        if type(fs_raw) is not dict or not 1 <= len(fs_raw) <= MAX_FILESYSTEMS:
            raise ValueError("filesystems must have 1–10 entries")
        filesystems: dict[str, FilesystemPolicy] = {}
        for key, value in fs_raw.items():
            key = _identity(key)
            item = _object(value, {"mountpoint", "expected_source", "min_free_bytes", "min_free_fraction"})
            expected_source = item["expected_source"]
            if type(expected_source) is not str or not expected_source or "\x00" in expected_source:
                raise ValueError("filesystem expected_source must be explicit")
            fraction = _number(item["min_free_fraction"])
            if fraction > 1:
                raise ValueError("filesystem free fraction must be at most one")
            filesystems[key] = FilesystemPolicy(_path(item["mountpoint"], allow_root=True), expected_source,
                _integer(item["min_free_bytes"]), fraction)
        if len({policy.mountpoint for policy in filesystems.values()}) != len(filesystems):
            raise ValueError("one filesystem mountpoint must have one policy")
        source_policies: dict[str, tuple[int, float]] = {}
        for policy in filesystems.values():
            bounds = (policy.min_free_bytes, policy.min_free_fraction)
            previous = source_policies.setdefault(policy.expected_source, bounds)
            if previous != bounds:
                raise ValueError("one filesystem source must have one capacity policy")
        roots: dict[str, StorageRoot] = {}
        for slot, value in _object(doc["roots"], set(SLOTS)).items():
            item = _object(value, {"source", "path", "filesystem_id", "storage_id", "mount_mode"})
            filesystem_id = _identity(item["filesystem_id"])
            if filesystem_id not in filesystems or item["mount_mode"] != "bind":
                raise ValueError("storage root requires a known filesystem and bind mode")
            storage_id = item["storage_id"]
            if type(storage_id) is not str or _STORAGE_ID.fullmatch(storage_id) is None:
                raise ValueError("storage_id must be 32 lowercase hex digits")
            source = _path(item["source"])
            mount = PurePosixPath(filesystems[filesystem_id].mountpoint)
            if PurePosixPath(source) != mount and mount not in PurePosixPath(source).parents:
                raise ValueError("storage source is outside its filesystem mountpoint")
            roots[slot] = StorageRoot(source, _path(item["path"]), filesystem_id, storage_id, "bind")
        if len({root.storage_id for root in roots.values()}) != len(roots):
            raise ValueError("storage root identities must be distinct")
        if {root.filesystem_id for root in roots.values()} != set(filesystems):
            raise ValueError("filesystem policies must be used by a root")
        _distinct_paths([root.source for root in roots.values()])
        _distinct_paths([root.path for root in roots.values()])
        return cls(environment_id, group_id, MappingProxyType(filesystems), MappingProxyType(roots),
            doc)

    @classmethod
    def load(cls, path: Path) -> StorageLayoutConfig:
        return cls.from_bytes(_read(path))

    def role_roots(self, role: str) -> Mapping[str, StorageRoot]:
        if role not in {"backend", "worker", "repository_service"}:
            raise ValueError("unknown storage role")
        prefix = "rs-" if role == "repository_service" else "be-"
        return MappingProxyType({slot: root for slot, root in self.roots.items() if slot.startswith(prefix)})


@dataclass(frozen=True, slots=True)
class ServiceResources:
    memory_limit_bytes: int
    cpu_limit: float
    swap_limit_bytes: int


def _service(value: object) -> ServiceResources:
    item = _object(value, {"memory_limit_bytes", "cpu_limit", "swap_limit_bytes"})
    return ServiceResources(_integer(item["memory_limit_bytes"]), _number(item["cpu_limit"]),
        _integer(item["swap_limit_bytes"], minimum=0))


@dataclass(frozen=True, slots=True)
class WorkerResources:
    count: int
    active_limit: int
    kernel_threads: int
    kernel_memory_bytes: int
    memory_envelope_bytes: int
    memory_reserve_bytes: int
    cpu_limit: float
    swap_limit_bytes: int


@dataclass(frozen=True, slots=True)
class HostBudget:
    memory_bytes: int
    cpu_count: int
    shared_memory_reserve_bytes: int
    shared_cpu_reserve: float


@dataclass(frozen=True, slots=True)
class TemporaryLimits:
    scratch_max_bytes_per_attempt: int
    staging_max_bytes_per_object: int


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    environment_id: str
    group_id: str
    worker: WorkerResources
    backend: ServiceResources
    repository_service: ServiceResources
    host_budget: HostBudget
    temporary: TemporaryLimits
    _canonical_document: dict[str, object]

    @property
    def digest(self) -> str:
        return _configuration_digest(self._canonical_document)

    @classmethod
    def from_bytes(cls, raw: bytes) -> ResourceProfile:
        doc = _object(_document(raw), {"schema_version", "environment_id", "group_id", "worker",
            "backend", "repository_service", "host_budget", "temporary"})
        _validate_jcs_domain(doc)
        environment_id, group_id = _header(doc)
        item = _object(doc["worker"], {"count", "active_limit", "kernel_threads", "kernel_memory_bytes",
            "memory_envelope_bytes", "memory_reserve_bytes", "cpu_limit", "swap_limit_bytes"})
        worker = WorkerResources(_integer(item["count"], maximum=1), _integer(item["active_limit"], maximum=1),
            _integer(item["kernel_threads"], maximum=256), _integer(item["kernel_memory_bytes"], maximum=40 * _GIB),
            _integer(item["memory_envelope_bytes"], maximum=48 * _GIB),
            _integer(item["memory_reserve_bytes"], minimum=8 * _GIB), _number(item["cpu_limit"]),
            _integer(item["swap_limit_bytes"], minimum=0))
        if (worker.memory_reserve_bytes >= worker.memory_envelope_bytes
                or worker.kernel_memory_bytes > worker.memory_envelope_bytes - worker.memory_reserve_bytes
                or worker.kernel_threads > math.floor(worker.cpu_limit)):
            raise ValueError("worker kernel exceeds its resource envelope")
        backend, repository_service = _service(doc["backend"]), _service(doc["repository_service"])
        host_raw = _object(doc["host_budget"], {"memory_bytes", "cpu_count", "shared_memory_reserve_bytes", "shared_cpu_reserve"})
        host = HostBudget(_integer(host_raw["memory_bytes"]), _integer(host_raw["cpu_count"]),
            _integer(host_raw["shared_memory_reserve_bytes"], minimum=0),
            _number(host_raw["shared_cpu_reserve"], allow_zero=True))
        if (worker.count * worker.memory_envelope_bytes + backend.memory_limit_bytes
                + repository_service.memory_limit_bytes + host.shared_memory_reserve_bytes > host.memory_bytes
                or worker.count * worker.cpu_limit + backend.cpu_limit + repository_service.cpu_limit
                + host.shared_cpu_reserve > host.cpu_count):
            raise ValueError("group services exceed host planning budget")
        temp = _object(doc["temporary"], {"scratch_max_bytes_per_attempt", "staging_max_bytes_per_object"})
        temporary = TemporaryLimits(_integer(temp["scratch_max_bytes_per_attempt"]),
            _integer(temp["staging_max_bytes_per_object"]))
        return cls(environment_id, group_id, worker, backend, repository_service, host, temporary,
            doc)

    @classmethod
    def load(cls, path: Path) -> ResourceProfile:
        return cls.from_bytes(_read(path))


@dataclass(frozen=True, slots=True)
class DeploymentConfig:
    storage: StorageLayoutConfig
    resources: ResourceProfile

    def __post_init__(self) -> None:
        if ((self.storage.environment_id, self.storage.group_id)
                != (self.resources.environment_id, self.resources.group_id)):
            raise ValueError("storage/resource environment and group must match")

    @classmethod
    def load(cls, storage_path: Path, resources_path: Path) -> DeploymentConfig:
        return cls(StorageLayoutConfig.load(storage_path), ResourceProfile.load(resources_path))
