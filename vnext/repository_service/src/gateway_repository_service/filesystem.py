"""Small filesystem measurements for disposable P2-R1 roots."""

from __future__ import annotations

import os
import ctypes
import ctypes.util
import hashlib
import stat as stat_module
from pathlib import Path
from typing import TypedDict


class StorageFile(TypedDict):
    relative_path: str
    inode: int
    st_size: int
    st_blocks: int
    link_count: int


class StorageSnapshot(TypedDict):
    complete: bool
    logical_bytes: int
    allocated_bytes: int
    files: list[StorageFile]
    storage_root_identity: str


def storage_root_identity(root: Path) -> str:
    """Return an opaque identity for the measured filesystem root."""

    metadata = os.lstat(root)
    value = f"{metadata.st_dev}:{metadata.st_ino}".encode("ascii")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def storage_snapshot(root: Path) -> StorageSnapshot:
    """Take a path-safe, hard-link-aware storage snapshot.

    ``lstat`` is intentional: symlinks are excluded and hard-linked files are
    counted once, so the totals and the file evidence describe the same set of
    physical file objects.
    """

    files: list[StorageFile] = []
    seen_inodes: set[tuple[int, int]] = set()
    logical = 0
    allocated = 0
    complete = True
    if not root.exists():
        return {
            "complete": False,
            "logical_bytes": 0,
            "allocated_bytes": 0,
            "files": [],
            "storage_root_identity": "",
        }
    try:
        root_identity = storage_root_identity(root)
    except OSError:
        root_identity = ""
        complete = False
    try:
        paths = sorted(root.rglob("*"), key=lambda path: path.as_posix())
    except OSError:
        paths = []
        complete = False
    for path in paths:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            complete = False
            continue
        except OSError:
            complete = False
            continue
        if stat_module.S_ISLNK(metadata.st_mode) or not stat_module.S_ISREG(metadata.st_mode):
            continue
        identity = (metadata.st_dev, metadata.st_ino)
        if identity in seen_inodes:
            continue
        seen_inodes.add(identity)
        relative = path.relative_to(root).as_posix()
        entry: StorageFile = {
            "relative_path": relative,
            "inode": int(metadata.st_ino),
            "st_size": int(metadata.st_size),
            "st_blocks": int(metadata.st_blocks),
            "link_count": int(metadata.st_nlink),
        }
        files.append(entry)
        logical += entry["st_size"]
        allocated += entry["st_blocks"] * 512
    return {
        "complete": complete,
        "logical_bytes": logical,
        "allocated_bytes": allocated,
        "files": files,
        "storage_root_identity": root_identity,
    }


def tree_storage_bytes(root: Path) -> tuple[int, int]:
    snapshot = storage_snapshot(root)
    return snapshot["logical_bytes"], snapshot["allocated_bytes"]


def same_device(*paths: Path) -> bool:
    return len({os.stat(path).st_dev for path in paths}) == 1


def filesystem_quiesce(root: Path) -> None:
    """Flush a probe filesystem before taking its storage measurement.

    ``syncfs`` is preferred because it scopes the flush to the mounted
    filesystem containing the probe root.  The directory fsync fallback keeps
    the ordering useful on platforms without libc's syncfs symbol.
    """

    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        libc_name = ctypes.util.find_library("c")
        if libc_name:
            libc = ctypes.CDLL(libc_name, use_errno=True)
            syncfs = getattr(libc, "syncfs", None)
            if syncfs is not None:
                syncfs.argtypes = [ctypes.c_int]
                syncfs.restype = ctypes.c_int
                if syncfs(descriptor) == 0:
                    return
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
