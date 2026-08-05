"""Durable-root writable and free-disk admission checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from gateway_repository_service.settings import RepositoryServiceSettings


class CapacityAdmissionError(RuntimeError):
    """Raised when durable-root admission checks fail."""


@dataclass(frozen=True)
class DiskAdmission:
    free_bytes: int
    total_bytes: int
    required_free_bytes: int

    @property
    def admitted(self) -> bool:
        return self.free_bytes >= self.required_free_bytes


def free_disk_threshold_bytes(
    *,
    total_bytes: int,
    min_bytes: int,
    fraction: float,
) -> int:
    return max(min_bytes, int(total_bytes * fraction))


def measure_disk_admission(root: Path, settings: RepositoryServiceSettings) -> DiskAdmission:
    stat = os.statvfs(root)
    block_size = stat.f_frsize
    free_bytes = stat.f_bavail * block_size
    total_bytes = stat.f_blocks * block_size
    required = free_disk_threshold_bytes(
        total_bytes=total_bytes,
        min_bytes=settings.min_free_disk_bytes,
        fraction=settings.min_free_disk_fraction,
    )
    return DiskAdmission(
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        required_free_bytes=required,
    )


def is_durable_root_writable(service_state: Path) -> bool:
    service_state.mkdir(parents=True, exist_ok=True)
    probe = service_state / f".write-probe-{uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def assert_durable_root_writable(service_state: Path) -> None:
    if not is_durable_root_writable(service_state):
        raise CapacityAdmissionError("durable root is not writable")


def has_free_disk_admission(root: Path, settings: RepositoryServiceSettings) -> bool:
    return measure_disk_admission(root, settings).admitted


def assert_free_disk_admission(root: Path, settings: RepositoryServiceSettings) -> DiskAdmission:
    admission = measure_disk_admission(root, settings)
    if not admission.admitted:
        raise CapacityAdmissionError("durable root free disk is below admission threshold")
    return admission
