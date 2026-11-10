"""Service-owned ordinary scratch files; producers retain ownership after import."""
from __future__ import annotations

import fcntl
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass(frozen=True)
class ScratchFile:
    """Only yielded by ScratchSpace.file; invalid after its context closes."""
    _path: Path
    _identity: tuple[int, int]
    _owner_descriptor: int

    @contextmanager
    def open_read(self) -> Iterator[BinaryIO]:
        os.fstat(self._owner_descriptor)
        descriptor = os.open(self._path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != self._identity:
                raise ValueError('scratch source must be the owned ordinary file')
            yield handle


class ScratchSpace:
    def __init__(self, root: Path) -> None:
        from gateway_backend.infrastructure.artifact_store.layout import _directory_identity
        self._root = root
        self._identity = _directory_identity(root)

    @contextmanager
    def file(self, *, owner: str) -> Iterator[tuple[ScratchFile, BinaryIO]]:
        from gateway_backend.infrastructure.artifact_store.layout import _directory_identity
        if not owner or len(owner) > 128:
            raise ValueError('scratch owner is required')
        if _directory_identity(self._root) != self._identity:
            raise ValueError('scratch root identity changed')
        directory = Path(tempfile.mkdtemp(prefix='scratch-', dir=self._root))
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            with (directory / 'payload').open('w+b') as handle:
                info = os.fstat(handle.fileno())
                yield ScratchFile(directory / 'payload', (info.st_dev, info.st_ino), descriptor), handle
        finally:
            os.close(descriptor)
            shutil.rmtree(directory)
