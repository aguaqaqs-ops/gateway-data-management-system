"""Filesystem publication barriers used only by the P2-R1 probe."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path


class FaultPoint(StrEnum):
    NONE = "none"
    BEFORE_RENAME = "before_rename"
    AFTER_RENAME = "after_rename"


def fsync_tree(root: Path) -> None:
    directories: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        elif path.is_dir():
            directories.append(path)
    for directory in reversed(directories):
        _fsync_directory(directory)
    _fsync_directory(root)


def atomic_publish(
    staging: Path,
    target: Path,
    *,
    same_filesystem: bool = True,
    fault: FaultPoint = FaultPoint.NONE,
) -> None:
    if target.exists():
        raise FileExistsError(target)
    if same_filesystem and staging.stat().st_dev != target.parent.stat().st_dev:
        raise OSError("staging and target parent are on different filesystems")
    fsync_tree(staging)
    if fault == FaultPoint.BEFORE_RENAME:
        raise RuntimeError("fault injected before publication rename")
    os.rename(staging, target)
    _fsync_directory(target.parent)
    if fault == FaultPoint.AFTER_RENAME:
        raise RuntimeError("fault injected after publication rename")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
