"""Durable-root writable and free-disk admission checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings


class CapacityAdmissionError(RuntimeError):
    """Raised when durable-root admission checks fail."""


@dataclass(frozen=True)
class DiskAdmission:
    free_bytes: int
    total_bytes: int
    required_free_bytes: int
    free_inodes: int | None = None

    @property
    def admitted(self) -> bool:
        return self.free_bytes >= self.required_free_bytes and (self.free_inodes is None or self.free_inodes > 0)


def free_disk_threshold_bytes(
    *,
    total_bytes: int,
    min_bytes: int,
    fraction: float,
) -> int:
    return max(min_bytes, int(total_bytes * fraction))


def _capacity_bounds(root: Path, settings: RepositoryServiceSettings) -> tuple[int, float]:
    config = settings.storage_layout_config
    if config is not None:
        for item in config.role_roots("repository_service").values():
            if root.is_relative_to(Path(item.path)):
                policy = config.filesystems[item.filesystem_id]
                return policy.min_free_bytes, policy.min_free_fraction
        raise CapacityAdmissionError("disk path is outside configured RS roots")
    return settings.min_free_disk_bytes, settings.min_free_disk_fraction


def measure_disk_admission(root: Path, settings: RepositoryServiceSettings) -> DiskAdmission:
    stat = os.statvfs(root)
    block_size = stat.f_frsize
    free_bytes = stat.f_bavail * block_size
    total_bytes = stat.f_blocks * block_size
    required = free_disk_threshold_bytes(
        total_bytes=total_bytes,
        min_bytes=_capacity_bounds(root, settings)[0],
        fraction=_capacity_bounds(root, settings)[1],
    )
    return DiskAdmission(
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        required_free_bytes=required,
        free_inodes=stat.f_favail if stat.f_files else None,
    )


def is_durable_root_writable(service_state: Path) -> bool:
    try:
        if not service_state.is_dir():
            return False
        probe = service_state / f".write-probe-{uuid4().hex}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def assert_durable_root_writable(service_state: Path) -> None:
    if not is_durable_root_writable(service_state):
        raise CapacityAdmissionError("durable root is not writable")


def has_free_disk_admission(root: Path, settings: RepositoryServiceSettings) -> bool:
    try:
        return measure_disk_admission(root, settings).admitted
    except OSError:
        return False


def assert_free_disk_admission(root: Path, settings: RepositoryServiceSettings) -> DiskAdmission:
    admission = measure_disk_admission(root, settings)
    if not admission.admitted:
        raise CapacityAdmissionError("durable root free disk is below admission threshold")
    return admission


def measure_upload_disk_admission(
    root: Path,
    settings: RepositoryServiceSettings,
    *,
    declared_size: int,
) -> DiskAdmission:
    if declared_size < 0:
        raise ValueError("declared_size must be non-negative")
    stat = os.statvfs(root)
    block_size = stat.f_frsize
    free_bytes = stat.f_bavail * block_size
    total_bytes = stat.f_blocks * block_size
    required = free_disk_threshold_bytes(
        total_bytes=total_bytes,
        min_bytes=_capacity_bounds(root, settings)[0],
        fraction=_capacity_bounds(root, settings)[1],
    )
    remaining_after_upload = free_bytes - declared_size
    return DiskAdmission(
        free_bytes=remaining_after_upload,
        total_bytes=total_bytes,
        required_free_bytes=required,
        free_inodes=stat.f_favail if stat.f_files else None,
    )


def has_upload_disk_admission(
    root: Path,
    settings: RepositoryServiceSettings,
    *,
    declared_size: int,
) -> bool:
    try:
        return measure_upload_disk_admission(
            root,
            settings,
            declared_size=declared_size,
        ).admitted
    except OSError:
        return False


def assert_upload_disk_admission(
    root: Path,
    settings: RepositoryServiceSettings,
    *,
    declared_size: int,
) -> DiskAdmission:
    try:
        admission = measure_upload_disk_admission(root, settings, declared_size=declared_size)
    except OSError as exc:
        raise CapacityAdmissionError("durable root disk measurement is unavailable") from exc
    if not admission.admitted:
        raise CapacityAdmissionError(
            "durable root free disk after upload would be below admission threshold"
        )
    return admission


def _layout_admissions(
    layout: DurableLayout,
    settings: RepositoryServiceSettings,
    *,
    import_work: bool,
) -> tuple[DiskAdmission, ...]:
    """Measure each actual filesystem once and add simultaneous write demand.

    This is an admission precheck, not a reservation against other writers.
    Extraction and the Dolt write can coexist, including on a shared device.
    """
    config = settings.storage_layout_config
    grouped: dict[int, tuple[Path, int, float, int]] = {}
    for slot, path in zip(("repository", "artifacts", "metadata", "scratch"), layout.roots.paths()):
        minimum, fraction = settings.min_free_disk_bytes, settings.min_free_disk_fraction
        if config is not None:
            policy = config.filesystems[config.roots[f"rs-{slot}"].filesystem_id]
            minimum, fraction = policy.min_free_bytes, policy.min_free_fraction
        demand = 0
        if import_work:
            if slot == "repository":
                demand = settings.import_headroom_bytes
            elif slot == "scratch":
                demand = settings.max_total_expanded_entry_bytes
        device = path.stat().st_dev
        previous = grouped.get(device)
        if previous is not None:
            representative, old_minimum, old_fraction, old_demand = previous
            if (minimum, fraction) != (old_minimum, old_fraction):
                raise CapacityAdmissionError("one filesystem has conflicting capacity policies")
            grouped[device] = representative, minimum, fraction, old_demand + demand
        else:
            grouped[device] = path, minimum, fraction, demand
    admissions = []
    for path, minimum, fraction, demand in grouped.values():
        measured = os.statvfs(path)
        required = free_disk_threshold_bytes(total_bytes=measured.f_blocks * measured.f_frsize,
            min_bytes=minimum, fraction=fraction) + demand
        admissions.append(DiskAdmission(measured.f_bavail * measured.f_frsize,
            measured.f_blocks * measured.f_frsize, required,
            free_inodes=measured.f_favail if measured.f_files else None))
    return tuple(admissions)


def has_layout_disk_admission(layout: DurableLayout, settings: RepositoryServiceSettings) -> bool:
    try:
        return all(item.admitted for item in _layout_admissions(layout, settings, import_work=False))
    except (OSError, CapacityAdmissionError):
        return False


def assert_import_layout_admission(
    layout: DurableLayout, settings: RepositoryServiceSettings,
) -> tuple[DiskAdmission, ...]:
    try:
        admissions = _layout_admissions(layout, settings, import_work=True)
    except OSError as exc:
        raise CapacityAdmissionError("RS disk measurement is unavailable") from exc
    if not all(item.admitted for item in admissions):
        raise CapacityAdmissionError("RS free disk is below import admission threshold")
    return admissions
