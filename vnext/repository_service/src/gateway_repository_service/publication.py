"""Filesystem publication barriers for durable repository and artifact effects."""

from __future__ import annotations

import os
import ctypes
import errno
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


def prepare_directory_publish(staging: Path) -> None:
    """Durably sync a staged directory tree before atomic rename."""

    fsync_tree(staging)
    _fsync_directory(staging.parent)


def prepare_file_publish(staging: Path) -> None:
    """Durably sync a staged file before atomic rename."""

    with staging.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_directory(staging.parent)


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
    prepare_directory_publish(staging)
    if fault == FaultPoint.BEFORE_RENAME:
        raise RuntimeError("fault injected before publication rename")
    _rename_noreplace(staging, target)
    _fsync_directory(staging.parent)
    _fsync_directory(target.parent)
    if fault == FaultPoint.AFTER_RENAME:
        raise RuntimeError("fault injected after publication rename")


def atomic_publish_file(
    staging: Path,
    target: Path,
    *,
    fault: FaultPoint = FaultPoint.NONE,
) -> None:
    """Publish one already-written file without replacing an existing target."""

    if target.exists():
        raise FileExistsError(target)
    prepare_file_publish(staging)
    if fault == FaultPoint.BEFORE_RENAME:
        raise RuntimeError("fault injected before publication rename")
    _rename_noreplace(staging, target)
    _fsync_directory(staging.parent)
    _fsync_directory(target.parent)
    if fault == FaultPoint.AFTER_RENAME:
        raise RuntimeError("fault injected after publication rename")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, target: Path) -> None:
    """Perform Linux atomic rename with an in-kernel no-replace check."""

    renameat2_noreplace(
        -100,  # AT_FDCWD
        os.fsencode(source),
        -100,
        os.fsencode(target),
    )


def renameat2_noreplace(
    src_dir_fd: int,
    src_name: str | bytes,
    dst_dir_fd: int,
    dst_name: str | bytes,
) -> None:
    """``renameat2(..., RENAME_NOREPLACE)`` using directory file descriptors."""

    if os.name != "posix":
        raise OSError("atomic no-replace rename is unavailable on this platform")
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise OSError("renameat2 is unavailable; refusing non-atomic rename") from exc
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    src_bytes = src_name if isinstance(src_name, bytes) else os.fsencode(src_name)
    dst_bytes = dst_name if isinstance(dst_name, bytes) else os.fsencode(dst_name)
    result = renameat2(
        int(src_dir_fd),
        src_bytes,
        int(dst_dir_fd),
        dst_bytes,
        1,  # RENAME_NOREPLACE
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(errno.EEXIST, os.strerror(error), os.fsdecode(dst_bytes))
        raise OSError(error, os.strerror(error), os.fsdecode(dst_bytes))
