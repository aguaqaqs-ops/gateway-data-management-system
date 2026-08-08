"""Exclusive admission pin for ready artifact bytes."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.upload_artifact.visibility import (
    artifact_ready_path,
    verify_published_artifact_fd,
)


class ArtifactNotReadyForAdmission(RuntimeError):
    """Raised when ready artifact bytes cannot be admitted."""


class ArtifactAdmissionPin:
    def __init__(
        self,
        layout: DurableLayout,
        repository_id: UUID,
        artifact_id: UUID,
        *,
        size_bytes: int,
        raw_sha256: str,
    ) -> None:
        self._ready_path = artifact_ready_path(layout, repository_id, artifact_id)
        self._size_bytes = size_bytes
        self._raw_sha256 = raw_sha256
        self._fd: int | None = None
        self._inode: int | None = None
        self._finalized: bool = False

    @property
    def ready_path(self) -> Path:
        return self._ready_path

    def __enter__(self) -> Self:
        if self._fd is not None:
            raise RuntimeError("artifact admission pin is already held")
        try:
            fd = os.open(self._ready_path, os.O_RDONLY)
        except FileNotFoundError as exc:
            raise ArtifactNotReadyForAdmission("ready artifact file is missing") from exc
        try:
            os.set_inheritable(fd, False)
            fcntl.flock(fd, fcntl.LOCK_EX)
            if not verify_published_artifact_fd(
                fd,
                size_bytes=self._size_bytes,
                raw_sha256=self._raw_sha256,
            ):
                raise ArtifactNotReadyForAdmission("ready artifact bytes do not match binding")
            stat = os.fstat(fd)
            self._inode = stat.st_ino
            self._assert_path_inode_matches(stat)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._fd is None:
            return
        try:
            if exc_type is None and self._finalized:
                self._verify_pinned_bytes_still_linked()
        finally:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None
                self._inode = None
                self._finalized = False

    def assert_unchanged(self) -> None:
        if self._fd is None:
            raise RuntimeError("artifact admission pin is not held")
        self._verify_pinned_bytes_still_linked()

    def finalize_new_admission(self) -> None:
        """Verify ready artifact bytes remain published before returning 202."""

        if self._fd is None:
            raise RuntimeError("artifact admission pin is not held")
        self._verify_pinned_bytes_still_linked()
        self._finalized = True

    def _verify_pinned_bytes_still_linked(self) -> None:
        if self._fd is None:
            raise RuntimeError("artifact admission pin is not held")
        stat = os.fstat(self._fd)
        if stat.st_ino != self._inode:
            raise ArtifactNotReadyForAdmission("ready artifact inode changed under admission pin")
        if stat.st_nlink == 0:
            raise ArtifactNotReadyForAdmission("ready artifact file has no remaining directory links")
        self._assert_path_inode_matches(stat)

    def _assert_path_inode_matches(self, fd_stat: os.stat_result) -> None:
        try:
            path_stat = self._ready_path.stat()
        except FileNotFoundError as exc:
            raise ArtifactNotReadyForAdmission("ready artifact file is missing") from exc
        if path_stat.st_ino != fd_stat.st_ino:
            raise ArtifactNotReadyForAdmission("ready artifact file was replaced or unlinked")


def try_unlink_ready_artifact(ready_path: Path) -> bool:
    """Try to unlink ready artifact bytes when no admission pin is held."""

    try:
        fd = os.open(ready_path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        os.set_inheritable(fd, False)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        ready_path.unlink()
        return True
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
