"""Service-owned scratch, with one aggregate budget and lock per live owner."""
from __future__ import annotations

import fcntl
import io
import json
import os
import secrets
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO, cast

from gateway_backend.artifacts.scratch import ScratchLimitExceeded, ScratchSessionPort
from gateway_backend.artifacts.store import ArtifactFileSourcePort
from gateway_backend.infrastructure.artifact_store.layout import directory_identity


@dataclass(frozen=True)
class ScratchFile:
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


class _BudgetedFile(io.BufferedRandom):
    def __init__(self, path: Path, session: ScratchSession, byte_limit: int) -> None:
        super().__init__(io.FileIO(path, 'x+'))
        self._session = session
        self._limit = byte_limit
        self._extent = 0

    def _grow(self, extent: int) -> None:
        if extent > self._limit:
            raise ScratchLimitExceeded('temporary file exceeds producer byte limit')
        increase = max(0, extent - self._extent)
        self._session.reserve(increase)
        self._extent += increase

    def write(self, buffer: object) -> int:
        # Native writers use this Python file interface; no pathname/fileno is
        # handed to them that could bypass the aggregate byte check.
        view = memoryview(buffer)  # type: ignore[arg-type]
        self._grow(self.tell() + view.nbytes)
        return super().write(view)

    def truncate(self, size: int | None = None) -> int:
        self._grow(self.tell() if size is None else size)
        return super().truncate(size)

    def fileno(self) -> int:
        raise io.UnsupportedOperation('scratch writers must use bounded write')


class ScratchSession:
    def __init__(self, directory: Path, descriptor: int, cap: int, owner: str) -> None:
        self.directory = directory
        self.owner = owner
        self._descriptor = descriptor
        self._cap = cap
        self._used = 0
        self._mutex = Lock()

    def reserve(self, size: int) -> None:
        with self._mutex:
            if self._used + size > self._cap:
                raise ScratchLimitExceeded('aggregate scratch byte limit exceeded')
            self._used += size

    @contextmanager
    def file(self, *, byte_limit: int) -> Iterator[tuple[ArtifactFileSourcePort, BinaryIO]]:
        if type(byte_limit) is not int or byte_limit <= 0:
            raise ValueError('scratch producer byte limit must be positive')
        os.fstat(self._descriptor)
        path = self.directory / ('file-' + secrets.token_hex(16))
        handle = _BudgetedFile(path, self, byte_limit)
        info = path.stat()
        try:
            yield ScratchFile(path, (info.st_dev, info.st_ino), self._descriptor), cast(BinaryIO, handle)
        finally:
            try:
                handle.close()
            finally:
                path.unlink(missing_ok=True)
                # Charge until the file is removed, including when a writer
                # closed early. Failed writes may conservatively overcharge.
                with self._mutex:
                    self._used -= handle._extent


class ScratchSpace:
    def __init__(self, root: Path, *, max_bytes: int) -> None:
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError('scratch aggregate byte limit must be positive')
        self._root = root
        self._identity = directory_identity(root)
        self._max_bytes = max_bytes

    @contextmanager
    def session(self, *, owner: str) -> Iterator[ScratchSessionPort]:
        if type(owner) is not str or not owner or len(owner) > 512:
            raise ValueError('scratch owner is required')
        if directory_identity(self._root) != self._identity:
            raise ValueError('scratch root identity changed')
        directory = Path(tempfile.mkdtemp(prefix='scratch-', dir=self._root))
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            (directory / 'owner.json').write_text(json.dumps({'version': 1, 'owner': owner}), encoding='utf-8')
            yield ScratchSession(directory, descriptor, self._max_bytes, owner)
        finally:
            # Keep the owner lock until all owned paths are gone.
            try:
                shutil.rmtree(directory)
            finally:
                os.close(descriptor)

    @contextmanager
    def file(self, *, owner: str) -> Iterator[tuple[ScratchFile, BinaryIO]]:
        with self.session(owner=owner) as session, session.file(byte_limit=self._max_bytes) as (source, handle):
            yield cast(ScratchFile, source), handle
