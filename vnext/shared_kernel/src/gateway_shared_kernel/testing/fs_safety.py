"""Symlink and path-safety helpers for candidate generate/validate."""

from __future__ import annotations

import os
from pathlib import Path


def is_symlink(path: Path) -> bool:
    """True if the path is a symlink, including broken symlinks."""
    return path.is_symlink()


def assert_no_symlink_ancestors(path: Path, *, label: str) -> None:
    """Reject if ``path`` or any ancestor is a symlink (including broken)."""
    current = path.expanduser()
    parts: list[Path] = []
    cursor = current
    while True:
        parts.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    for item in reversed(parts):
        # Use lexists so broken symlinks are still detected.
        if os.path.lexists(item) and is_symlink(item):
            raise ValueError(f"refusing {label} that involves symlink path {item}")


def assert_regular_file(path: Path, *, label: str) -> None:
    if is_symlink(path):
        raise ValueError(f"refusing {label} symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is not a regular file: {path}")


def assert_regular_directory(path: Path, *, label: str) -> None:
    if is_symlink(path):
        raise ValueError(f"refusing {label} symlink: {path}")
    if not path.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")
