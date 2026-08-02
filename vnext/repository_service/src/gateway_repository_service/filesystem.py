"""Small filesystem measurements for disposable P2-R1 roots."""

from __future__ import annotations

import os
import ctypes
import ctypes.util
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
