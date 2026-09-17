"""Single dolt availability gate for backend integration tests."""

from __future__ import annotations

import shutil
from pathlib import Path


def dolt_available(dolt_binary: Path | None = None) -> bool:
    candidate = dolt_binary or Path("/usr/local/bin/dolt")
    if candidate.is_file():
        return True
    return shutil.which("dolt") is not None


__all__ = ["dolt_available"]
