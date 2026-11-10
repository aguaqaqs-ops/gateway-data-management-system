"""Capacity checks account for simultaneous writes on the actual filesystem."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    assert_import_layout_admission,
    has_layout_disk_admission,
)
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.storage_roots import RepositoryRoots


@pytest.mark.parametrize("remaining,free_inodes,admitted", [(0, 1, True), (-1, 1, False), (0, 0, False)])
def test_import_shared_filesystem_adds_repository_and_extraction_demand_once(
    tmp_path: Path, remaining: int, free_inodes: int, admitted: bool,
) -> None:
    settings = RepositoryServiceSettings(roots=RepositoryRoots.under(tmp_path),
        min_free_disk_bytes=1000, min_free_disk_fraction=0.1,
        import_headroom_bytes=500, max_total_expanded_entry_bytes=700)
    layout = DurableLayout.create_for_probe(settings.storage_roots)
    required = 1000 + 500 + 700
    measured = SimpleNamespace(f_frsize=1, f_bavail=required + remaining,
        f_blocks=10_000, f_files=1000, f_favail=free_inodes)
    with patch("gateway_repository_service.capacity.os.statvfs", return_value=measured) as probe:
        if admitted:
            values = assert_import_layout_admission(layout, settings)
            assert len(values) == 1
            assert values[0].required_free_bytes == required
        else:
            with pytest.raises(CapacityAdmissionError, match="below import"):
                assert_import_layout_admission(layout, settings)
        assert probe.call_count == 1
        assert has_layout_disk_admission(layout, settings) is bool(free_inodes)


def test_import_disk_measurement_failure_rejects_admission(tmp_path: Path) -> None:
    roots = RepositoryRoots.under(tmp_path)
    layout = DurableLayout.create_for_probe(roots)
    with patch("gateway_repository_service.capacity.os.statvfs", side_effect=OSError("unavailable")):
        with pytest.raises(CapacityAdmissionError, match="measurement is unavailable"):
            assert_import_layout_admission(layout, RepositoryServiceSettings(roots=roots))
        assert not has_layout_disk_admission(layout, RepositoryServiceSettings(roots=roots))
