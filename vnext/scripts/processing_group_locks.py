"""Cooperative host configuration locks; publication always precedes group lock."""
from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Iterator
from pathlib import Path
import fcntl
import os
import re
import stat


@contextmanager
def _lock(directory: Path, name: str) -> Iterator[None]:
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("configuration directory must exist and be absolute")
    descriptor = os.open(directory / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("configuration lock must be an ordinary file")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def publication_lock(directory: Path) -> AbstractContextManager[None]:
    return _lock(directory, ".gateway-publication.lock")


def group_management_lock(directory: Path, group_id: str) -> AbstractContextManager[None]:
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", group_id) is None:
        raise ValueError("invalid processing group identity")
    return _lock(directory, ".gateway-group-" + group_id + ".lock")
