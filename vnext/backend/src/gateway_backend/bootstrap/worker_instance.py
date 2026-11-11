"""Fixed worker ownership for one process lifetime in the cooperative group."""
from __future__ import annotations

import fcntl
import hashlib
import os
import stat

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.deployment_config import DeploymentConfig
from gateway_backend.infrastructure.artifact_store.layout import descriptor_mount_id
from gateway_backend.runtime_preflight import check_configured_root

# Deliberately keep raw descriptors: run() returning does not prove that executor
# threads have exited. Only OS process teardown releases a successful acquisition.
_PROCESS_LOCKS: list[int] = []


class WorkerInstanceConflict(ValueError):
    """The configured instance is already owned by a live cooperating process."""


def worker_id_for(config: DeploymentConfig, instance_index: int) -> str:
    if type(instance_index) is not int or not 1 <= instance_index <= config.resources.worker.count:
        raise ValueError("worker instance index is outside the configured range")
    namespace = canonicalize_json_value([config.storage.environment_id, config.storage.group_id])
    return f"worker-{hashlib.sha256(namespace).hexdigest()}-{instance_index}"


def acquire_worker_instance(config: DeploymentConfig, instance_index: int) -> str:
    """Acquire before kernel/runtime/telemetry; never unlink or release on return."""
    identity = worker_id_for(config, instance_index)
    check_configured_root(config.storage, "be-metadata")
    directory = os.open(config.storage.roots["be-metadata"].path,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor: int | None = None
    try:
        descriptor = os.open(f".gateway-worker-{instance_index}.lock",
                             os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             0o600, dir_fd=directory)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or descriptor_mount_id(descriptor) != descriptor_mount_id(directory)
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError("worker instance lock has invalid file identity or permissions")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkerInstanceConflict("worker instance is already running") from None
        _PROCESS_LOCKS.append(descriptor)
        descriptor = None
        return identity
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)
