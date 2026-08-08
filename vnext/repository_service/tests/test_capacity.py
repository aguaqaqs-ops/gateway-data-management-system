"""Unit tests for import disk admission."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    assert_import_disk_admission,
    measure_import_disk_admission,
)
from gateway_repository_service.settings import RepositoryServiceSettings


def _settings(tmp_path: Path, *, min_free_disk_bytes: int = 1_000) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=tmp_path / "data-root",
        min_free_disk_bytes=min_free_disk_bytes,
        min_free_disk_fraction=0.10,
        import_headroom_bytes=500,
    )


def test_import_disk_admission_passes_on_equality_boundary(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    baseline = 1_000
    required = baseline + settings.import_headroom_bytes
    statvfs = type(
        "StatVfs",
        (),
        {"f_frsize": 1, "f_bavail": required, "f_blocks": 10_000},
    )()
    with patch("gateway_repository_service.capacity.os.statvfs", return_value=statvfs):
        admission = measure_import_disk_admission(tmp_path, settings)
        assert admission.required_free_bytes == required
        assert admission.free_bytes == required
        assert admission.admitted is True
        assert_import_disk_admission(tmp_path, settings)


def test_import_disk_admission_rejects_one_byte_below_threshold(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    baseline = 1_000
    required = baseline + settings.import_headroom_bytes
    statvfs = type(
        "StatVfs",
        (),
        {"f_frsize": 1, "f_bavail": required - 1, "f_blocks": 10_000},
    )()
    with patch("gateway_repository_service.capacity.os.statvfs", return_value=statvfs):
        admission = measure_import_disk_admission(tmp_path, settings)
        assert admission.admitted is False
        with pytest.raises(CapacityAdmissionError):
            assert_import_disk_admission(tmp_path, settings)


def test_import_disk_admission_uses_fraction_and_min_bytes(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=tmp_path / "data-root",
        min_free_disk_bytes=5_000,
        min_free_disk_fraction=0.10,
        import_headroom_bytes=0,
    )
    with patch(
        "gateway_repository_service.capacity.os.statvfs",
        return_value=type(
            "StatVfs",
            (),
            {"f_frsize": 1, "f_bavail": 4_999, "f_blocks": 10_000},
        )(),
    ):
        admission = measure_import_disk_admission(tmp_path, settings)
    assert admission.required_free_bytes == 5_000
    assert admission.admitted is False


def test_assert_import_disk_admission_maps_statvfs_oserror(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with patch(
        "gateway_repository_service.capacity.os.statvfs",
        side_effect=OSError("disk measurement failed"),
    ):
        with pytest.raises(CapacityAdmissionError, match="disk measurement is unavailable"):
            assert_import_disk_admission(tmp_path, settings)
