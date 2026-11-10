"""Linux deployment preflight; no mount creation, fallback, or cgroup mutation."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .deployment_config import DeploymentConfig, StorageLayoutConfig, _document

MARKER = ".gateway-storage.json"


def _bounded(path: Path, limit: int = 1024 * 1024) -> str:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("deployment observation exceeds its bound")
    return raw.decode("utf-8")


def _unescape(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


@dataclass(frozen=True)
class Mount:
    mount_id: int
    device: str
    root: str
    target: str
    source: str
    writable: bool


def mounts(path: Path = Path("/proc/self/mountinfo")) -> tuple[Mount, ...]:
    result = []
    for line in _bounded(path).splitlines():
        before, after = line.split(" - ", 1)
        left, right = before.split(), after.split()
        result.append(Mount(int(left[0]), left[2], _unescape(left[3]), _unescape(left[4]),
                            _unescape(right[1]), "rw" in left[5].split(",") and "rw" in right[2].split(",")))
    return tuple(result)


def nofollow_directory(path: Path) -> os.stat_result:
    # Every existing component must be a directory, never a symlink.
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("storage directory is missing or traverses a symlink")
    return info


def marker_document(config: StorageLayoutConfig, slot: str) -> dict[str, object]:
    return {"schema_version": 1, "environment_id": config.environment_id,
            "group_id": config.group_id, "slot": slot, "storage_id": config.roots[slot].storage_id}


def check_marker(config: StorageLayoutConfig, slot: str, path: Path) -> None:
    descriptor = os.open(path / MARKER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("storage marker must be an ordinary file")
        raw = os.read(descriptor, 4097)
        document = _document(raw)
        if (len(raw) > 4096 or type(document.get("schema_version")) is not int
                or document != marker_document(config, slot)):
            raise ValueError("storage marker identity mismatch")
    finally:
        os.close(descriptor)


def check_database_files(metadata: Path) -> None:
    info = nofollow_directory(metadata)
    present = (metadata / "control.sqlite3").exists()
    for name in ("control.sqlite3", "control.sqlite3-wal", "control.sqlite3-shm", "control.sqlite3-journal"):
        path = metadata / name
        try:
            entry = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(entry.st_mode) or entry.st_dev != info.st_dev:
            raise ValueError("control database file is redirected or not ordinary")
        if name != "control.sqlite3" and not present:
            raise ValueError("control database journal has no owning database")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        directory = os.open(metadata, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            def mount_id(fd: int) -> str:
                return next(line for line in _bounded(Path(f"/proc/self/fdinfo/{fd}"), 4096).splitlines()
                            if line.startswith("mnt_id:"))
            if mount_id(descriptor) != mount_id(directory):
                raise ValueError("control database file is on an unexpected mount")
        finally:
            os.close(descriptor)
            os.close(directory)


def check_capacity(path: Path, minimum: int, fraction: float) -> tuple[int, int]:
    info = os.statvfs(path)
    available = info.f_bavail * info.f_frsize
    if (available < max(minimum, math.ceil(info.f_blocks * info.f_frsize * fraction))
            or info.f_favail == 0 or info.f_flag & os.ST_RDONLY):
        raise ValueError("storage filesystem is read-only or below its capacity threshold")
    return available, info.f_favail


def check_host(config: DeploymentConfig, *, markers: bool = True) -> None:
    observed = mounts()
    seen: dict[str, tuple[int, float]] = {}
    for slot, root in config.storage.roots.items():
        path = Path(root.source)
        nofollow_directory(path)
        policy = config.storage.filesystems[root.filesystem_id]
        candidates = [mount for mount in observed if mount.target == policy.mountpoint]
        if len(candidates) != 1 or candidates[0].source != policy.expected_source or not candidates[0].writable:
            raise ValueError(f"{slot}: host filesystem source/mount mismatch")
        mount = candidates[0]
        containing = max((item for item in observed if Path(item.target) == path or Path(item.target) in path.parents),
                         key=lambda item: len(item.target))
        if containing.mount_id != mount.mount_id:
            raise ValueError(f"{slot}: unexpected nested host mount")
        bounds = (policy.min_free_bytes, policy.min_free_fraction)
        if mount.device in seen and seen[mount.device] != bounds:
            raise ValueError("same filesystem has conflicting capacity policies")
        if mount.device not in seen:
            check_capacity(path, *bounds)
            seen[mount.device] = bounds
        if markers:
            check_marker(config.storage, slot, path)
    check_host_budget(config)


def initialize_host(config: DeploymentConfig) -> None:
    check_host(config, markers=False)
    # Validate every root before writing the first marker. No directories are created.
    missing = []
    for slot, root in config.storage.roots.items():
        path = Path(root.source)
        if (path / MARKER).exists() or (path / MARKER).is_symlink():
            check_marker(config.storage, slot, path)
        else:
            if next(path.iterdir(), None) is not None:
                raise ValueError(f"{slot}: initialization requires an empty directory")
            missing.append((slot, path))
    for slot, path in missing:
        descriptor = os.open(path / MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
        try:
            payload = json.dumps(marker_document(config.storage, slot), sort_keys=True).encode()
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _cgroup_chain() -> tuple[Path, ...]:
    values = [line[3:] for line in _bounded(Path("/proc/self/cgroup")).splitlines() if line.startswith("0::")]
    candidates = [item for item in mounts() if item.source == "cgroup" or item.source == "cgroup2"]
    if len(values) != 1 or not candidates:
        raise ValueError("cgroup v2 is required for deployment resource verification")
    mount = max(candidates, key=lambda item: len(item.root))
    relative = Path(values[0]).relative_to(mount.root)
    if ".." in relative.parts:
        raise ValueError("cgroup hierarchy is not visible")
    base = Path(mount.target)
    current = base / relative
    return (current, *(parent for parent in current.parents if parent == base or base in parent.parents))


def _limit(path: Path) -> int | None:
    value = _bounded(path, 256).strip()
    return None if value == "max" else int(value)


def _cpus(value: str) -> int:
    count = 0
    for part in value.strip().split(","):
        left, separator, right = part.partition("-")
        start, end = int(left), int(right) if separator else int(left)
        if end < start:
            raise ValueError("invalid effective cpuset")
        count += end - start + 1
    return count


def check_host_budget(config: DeploymentConfig) -> None:
    physical = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    cpu = float(len(os.sched_getaffinity(0)))
    for group in _cgroup_chain():
        memory = _limit(group / "memory.max")
        if memory is not None:
            physical = min(physical, memory)
        quota, period = _bounded(group / "cpu.max", 256).split()
        if quota != "max":
            cpu = min(cpu, int(quota) / int(period))
        effective = _bounded(group / "cpuset.cpus.effective", 4096).strip()
        if effective:
            cpu = min(cpu, _cpus(effective))
    budget = config.resources.host_budget
    if budget.memory_bytes > physical or budget.cpu_count > cpu:
        raise ValueError("host planning budget exceeds actual host/ancestor cgroup capacity")


def check_resources(config: DeploymentConfig, role: str) -> None:
    resources = config.resources
    if role == "worker":
        memory, cpu, swap = resources.worker.memory_envelope_bytes, resources.worker.cpu_limit, resources.worker.swap_limit_bytes
    else:
        service = resources.backend if role == "backend" else resources.repository_service
        memory, cpu, swap = service.memory_limit_bytes, service.cpu_limit, service.swap_limit_bytes
    chain = _cgroup_chain()
    if _limit(chain[0] / "memory.max") != memory or _limit(chain[0] / "memory.swap.max") != swap:
        raise ValueError("actual memory/swap cgroup does not match resource profile")
    quota, period = _bounded(chain[0] / "cpu.max", 256).split()
    if quota == "max" or not math.isclose(int(quota) / int(period), cpu, rel_tol=0, abs_tol=0.000000001):
        raise ValueError("actual CPU quota does not match resource profile")
    effective_cpu = float(len(os.sched_getaffinity(0)))
    for group in chain:
        ancestor_swap = _limit(group / "memory.swap.max")
        if ancestor_swap is not None and ancestor_swap < swap:
            raise ValueError("ancestor swap policy is below role profile")
        maximum = _limit(group / "memory.max")
        if maximum is not None and maximum < memory:
            raise ValueError("ancestor memory limit is below role envelope")
        quota, period = _bounded(group / "cpu.max", 256).split()
        if quota != "max":
            effective_cpu = min(effective_cpu, int(quota) / int(period))
        effective = _bounded(group / "cpuset.cpus.effective", 4096).strip()
        if effective:
            effective_cpu = min(effective_cpu, _cpus(effective))
    if effective_cpu + 0.00001 < cpu or (role == "worker" and resources.worker.kernel_threads > math.floor(effective_cpu)):
        raise ValueError("effective ancestor CPU/cpuset is below role profile")


class RuntimePreflight:
    """Bounded role-local observations; identity loss remains latched until restart."""

    def __init__(self, config: DeploymentConfig, role: str, *, container: bool = True) -> None:
        if not container and (Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()):
            raise ValueError("host mode is unavailable inside a deployment container")
        self.config = config
        self.role = role
        self.container = container
        self._identities: dict[str, tuple[int, int, int]] = {}
        self._failed = False
        self.check()
        logging.getLogger(__name__).info("deployment preflight %s", json.dumps(self.observations(), sort_keys=True))

    def check(self, *, capacity: bool = True) -> None:
        if self._failed:
            raise ValueError("deployment identity was lost; restart and preflight required")
        try:
            observed = mounts()
            seen: dict[int, tuple[int, float]] = {}
            if self.container:
                check_resources(self.config, self.role)
            for slot, root in self.config.storage.role_roots(self.role).items():
                path = Path(root.path)
                info = nofollow_directory(path)
                entries = [item for item in observed if item.target == root.path]
                policy = self.config.storage.filesystems[root.filesystem_id]
                relative = str(Path(root.source).relative_to(policy.mountpoint))
                if self.container and (len(entries) != 1 or entries[0].source != policy.expected_source or not entries[0].writable
                        or (relative != "." and not entries[0].root.endswith("/" + relative))):
                    raise ValueError(f"{slot}: actual bind mount does not match configuration")
                identity = (info.st_dev, info.st_ino, entries[0].mount_id if self.container else 0)
                if slot in self._identities and self._identities[slot] != identity:
                    raise ValueError(f"{slot}: storage mount identity changed")
                check_marker(self.config.storage, slot, path)
                if not os.access(path, os.R_OK | os.W_OK | os.X_OK, effective_ids=True):
                    raise ValueError(f"{slot}: role lacks storage permissions")
                bounds = (policy.min_free_bytes, policy.min_free_fraction)
                if info.st_dev in seen and seen[info.st_dev] != bounds:
                    raise ValueError("same filesystem has conflicting capacity policies")
                if capacity and info.st_dev not in seen:
                    check_capacity(path, *bounds)
                seen[info.st_dev] = bounds
                if slot == "be-metadata":
                    check_database_files(path)
                self._identities[slot] = identity
        except OSError:
            self._failed = True
            raise ValueError("deployment storage root unavailable") from None
        except ValueError:
            self._failed = True
            raise

    def observations(self) -> dict[str, object]:
        """S1b input: fixed slot count, no recursive object scan or durable telemetry."""
        self.check()
        result: dict[str, object] = {"environment_id": self.config.storage.environment_id,
            "group_id": self.config.storage.group_id, "storage_digest": self.config.storage.digest,
            "resource_digest": self.config.resources.digest, "role": self.role, "hard_envelope": self.container, "slots": {}}
        slots: dict[str, object] = {}
        filesystems: dict[str, object] = {}
        for slot, root in self.config.storage.role_roots(self.role).items():
            info = os.stat(root.path)
            key = str(info.st_dev)
            if key not in filesystems:
                free = os.statvfs(root.path)
                filesystems[key] = {"available_bytes": free.f_bavail * free.f_frsize,
                                    "available_inodes": free.f_favail}
            slots[slot] = {"filesystem_id": root.filesystem_id, "device": info.st_dev,
                "inode": info.st_ino, "storage_id": root.storage_id}
        result["slots"] = slots
        result["filesystems"] = filesystems
        return result
