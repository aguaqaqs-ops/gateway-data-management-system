"""The offline component report counts only its explicitly owned artifact roots."""
from __future__ import annotations

from pathlib import Path

from benchmarks.s2b_c_capacity import artifact_disk_bytes
from gateway_backend.artifacts.location import ArtifactLocation
from tests.support.artifact_layout import make_artifact_layout


def test_component_report_sums_all_four_artifact_roots_and_excludes_siblings(tmp_path: Path) -> None:
    layout = make_artifact_layout(tmp_path / 'objects')
    for index, location in enumerate(ArtifactLocation, start=1):
        (layout.root(location) / 'payload').write_bytes(b'x' * index)
        (layout.root(location) / 'ref.jcs').write_bytes(b'{}')
    (tmp_path / 'control.sqlite').write_bytes(b'ignored database')
    assert artifact_disk_bytes(layout) == 18
