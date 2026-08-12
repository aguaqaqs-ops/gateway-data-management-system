"""Exclusive admission pin for ready artifact bytes."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Callable
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
        open_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if nofollow:
            open_flags |= nofollow
        try:
            fd = os.open(self._ready_path, open_flags)
        except OSError as exc:
            raise ArtifactNotReadyForAdmission("ready artifact file is unavailable") from exc
        try:
            os.set_inheritable(fd, False)
            fcntl.flock(fd, fcntl.LOCK_EX)
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                raise ArtifactNotReadyForAdmission("ready artifact path is not a regular file")
            if not verify_published_artifact_fd(
                fd,
                size_bytes=self._size_bytes,
                raw_sha256=self._raw_sha256,
            ):
                raise ArtifactNotReadyForAdmission("ready artifact bytes do not match binding")
            fd_stat = os.fstat(fd)
            self._inode = fd_stat.st_ino
            self._assert_path_inode_matches(fd_stat)
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
            path_stat = self._ready_path.lstat()
        except FileNotFoundError as exc:
            raise ArtifactNotReadyForAdmission("ready artifact file is missing") from exc
        if not stat.S_ISREG(path_stat.st_mode):
            raise ArtifactNotReadyForAdmission("ready artifact path is not a regular file")
        if (path_stat.st_dev, path_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
            raise ArtifactNotReadyForAdmission("ready artifact file was replaced or unlinked")


def ready_artifact_entry_absent(ready_path: Path) -> bool:
    """Return True only when the exact directory entry is confirmed absent."""

    try:
        ready_path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def try_unlink_ready_artifact_with_recheck(
    ready_path: Path,
    *,
    recheck: Callable[[], bool],
) -> str:
    """Acquire the admission flock, recheck eligibility, and unlink an exact regular file."""

    open_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        open_flags |= nofollow

    try:
        fd = os.open(ready_path, open_flags)
    except FileNotFoundError:
        return "already_absent" if recheck() else "ineligible"
    except OSError:
        try:
            if stat.S_ISLNK(ready_path.lstat().st_mode):
                return "symlink"
        except OSError:
            pass
        return "unlink_failed"
    try:
        os.set_inheritable(fd, False)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        try:
            fd_stat = os.fstat(fd)
            if not stat.S_ISREG(fd_stat.st_mode):
                return "not_regular_file"
            if fd_stat.st_nlink == 0:
                return "already_absent" if recheck() else "ineligible"
            try:
                path_stat = ready_path.lstat()
            except FileNotFoundError:
                return "already_absent" if recheck() else "ineligible"
            except OSError:
                return "unlink_failed"
            if stat.S_ISLNK(path_stat.st_mode):
                return "symlink"
            if not stat.S_ISREG(path_stat.st_mode):
                return "not_regular_file"
            if (path_stat.st_dev, path_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                return "inode_mismatch"
            if not recheck():
                return "ineligible"
            try:
                path_stat = ready_path.lstat()
                if not stat.S_ISREG(path_stat.st_mode):
                    return "not_regular_file"
                if (path_stat.st_dev, path_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                    return "inode_mismatch"
                if path_stat.st_nlink == 0:
                    return "inode_mismatch"
                ready_path.unlink()
            except FileNotFoundError:
                return "already_absent" if recheck() else "ineligible"
            except OSError:
                return "unlink_failed"
            if not ready_artifact_entry_absent(ready_path):
                return "path_recreated"
            return "deleted"
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)


def try_unlink_ready_artifact(ready_path: Path) -> bool:
    """Compatibility wrapper for cooperative callers that only need a bool outcome."""

    return (
        try_unlink_ready_artifact_with_recheck(ready_path, recheck=lambda: True)
        == "deleted"
    )
