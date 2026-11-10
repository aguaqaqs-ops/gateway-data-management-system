"""Current evidence tooling imports and reads the actual named storage locations."""
from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.settings import RepositoryServiceSettings


def test_current_evidence_tool_import_and_named_storage_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    namespace = runpy.run_path(str(scripts / "run_r6_s6_evidence.py"), run_name="evidence_import_probe")
    assert callable(namespace["main"])
    import r6_s6_lib  # type: ignore[import-not-found]

    query_count = cast(Callable[[DurableLayout], int], r6_s6_lib.query_temp_count)
    disk_view = cast(Callable[[DurableLayout, RepositoryServiceSettings], dict[str, int]],
        r6_s6_lib.disk_admission_view)
    layout = DurableLayout.create_for_probe(tmp_path / "roots")
    settings = RepositoryServiceSettings(roots=layout.roots, min_free_disk_bytes=1,
        min_free_disk_fraction=0.000001, import_headroom_bytes=1, max_total_expanded_entry_bytes=1)
    query = layout.query_directory / "query-live.sql"
    query.write_text("SELECT 1;")
    (layout.staging_artifacts / "query-unrelated.sql").write_text("SELECT 2;")
    assert query_count(layout) == 1
    query.unlink()
    assert query_count(layout) == 0
    measured = disk_view(layout, settings)
    assert measured["filesystem_count"] == 1
    assert measured["admitted"] == 1
    assert measured["free_bytes"] >= measured["required_free_bytes"]
