"""Unit tests for upload disk admission."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    assert_upload_disk_admission,
    measure_upload_disk_admission,
)
from gateway_repository_service.settings import RepositoryServiceSettings


def _settings(tmp_path: Path, *, min_free_disk_bytes: int = 1_000) -> RepositoryServiceSettings:
    return RepositoryServiceSettings(
        profile="test",
        data_root=tmp_path / "data-root",
        min_free_disk_bytes=min_free_disk_bytes,
        min_free_disk_fraction=0.10,
    )


def test_upload_disk_admission_passes_on_equality_boundary(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    declared_size = 100
    threshold = 1_000
    free_bytes = threshold + declared_size
    statvfs = type(
        "StatVfs",
        (),
        {"f_frsize": 1, "f_bavail": free_bytes, "f_blocks": 10_000},
    )()
    with patch("gateway_repository_service.capacity.os.statvfs", return_value=statvfs):
        admission = measure_upload_disk_admission(
            tmp_path,
            settings,
            declared_size=declared_size,
        )
        assert admission.required_free_bytes == threshold
        assert admission.free_bytes == threshold
        assert admission.admitted is True
        assert_upload_disk_admission(tmp_path, settings, declared_size=declared_size)


def test_upload_disk_admission_rejects_one_byte_below_threshold(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    declared_size = 100
    threshold = 1_000
    free_bytes = threshold + declared_size - 1
    statvfs = type(
        "StatVfs",
        (),
        {"f_frsize": 1, "f_bavail": free_bytes, "f_blocks": 10_000},
    )()
    with patch("gateway_repository_service.capacity.os.statvfs", return_value=statvfs):
        admission = measure_upload_disk_admission(
            tmp_path,
            settings,
            declared_size=declared_size,
        )
        assert admission.admitted is False
        with pytest.raises(CapacityAdmissionError):
            assert_upload_disk_admission(tmp_path, settings, declared_size=declared_size)


def test_upload_disk_admission_uses_fraction_and_min_bytes(tmp_path: Path) -> None:
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=tmp_path / "data-root",
        min_free_disk_bytes=5_000,
        min_free_disk_fraction=0.10,
    )
    declared_size = 0
    with patch(
        "gateway_repository_service.capacity.os.statvfs",
        return_value=type(
            "StatVfs",
            (),
            {"f_frsize": 1, "f_bavail": 4_999, "f_blocks": 10_000},
        )(),
    ):
        admission = measure_upload_disk_admission(tmp_path, settings, declared_size=declared_size)
    assert admission.required_free_bytes == 5_000
    assert admission.admitted is False


def test_upload_disk_admission_rejects_negative_declared_size(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="declared_size"):
        measure_upload_disk_admission(tmp_path, settings, declared_size=-1)
