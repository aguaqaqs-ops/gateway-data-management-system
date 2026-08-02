"""Small filesystem measurements for disposable P2-R1 roots."""

from __future__ import annotations

import os
from pathlib import Path


def tree_storage_bytes(root: Path) -> tuple[int, int]:
    logical = 0
    allocated = 0
    if not root.exists():
        return 0, 0
    for path in root.rglob("*"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if path.is_file():
            logical += stat.st_size
            allocated += stat.st_blocks * 512
    return logical, allocated


def same_device(*paths: Path) -> bool:
    return len({os.stat(path).st_dev for path in paths}) == 1
