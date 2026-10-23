"""Tests for container-readable test input files."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from tests.support.container_input_files import write_container_readable_text


def test_container_readable_file_mode_does_not_depend_on_umask(tmp_path: Path) -> None:
    previous_umask = os.umask(0o077)
    try:
        path = write_container_readable_text(tmp_path / "bearer-token", "test-token\n")
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert path.read_text(encoding="utf-8") == "test-token\n"
