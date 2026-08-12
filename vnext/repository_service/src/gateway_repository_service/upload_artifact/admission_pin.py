"""Exclusive admission pin for ready artifact bytes."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
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
        self._layout = layout
        self._repository_id = repository_id
        self._artifact_id = artifact_id
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
            opened = open_owned_ready_artifact(
                self._layout,
                self._repository_id,
                self._artifact_id,
            )
        except OwnedPathError as exc:
            raise ArtifactNotReadyForAdmission(str(exc)) from exc
        fd, _ready_dir_fd = opened
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
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
            os.close(_ready_dir_fd)
            raise
        # Admission pin only needs the file fd; close the verified dirfd.
        os.close(_ready_dir_fd)
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
        st = os.fstat(self._fd)
        if st.st_ino != self._inode:
            raise ArtifactNotReadyForAdmission("ready artifact inode changed under admission pin")
        if st.st_nlink == 0:
            raise ArtifactNotReadyForAdmission("ready artifact file has no remaining directory links")
        self._assert_path_inode_matches(st)

    def _assert_path_inode_matches(self, fd_stat: os.stat_result) -> None:
        try:
            path_stat = self._ready_path.lstat()
        except FileNotFoundError as exc:
            raise ArtifactNotReadyForAdmission("ready artifact file is missing") from exc
        if not stat.S_ISREG(path_stat.st_mode):
            raise ArtifactNotReadyForAdmission("ready artifact path is not a regular file")
        if (path_stat.st_dev, path_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
            raise ArtifactNotReadyForAdmission("ready artifact file was replaced or unlinked")


class OwnedPathError(RuntimeError):
    """Raised when a path cannot be opened under the owned durable layout."""


def ready_artifact_entry_absent(ready_path: Path) -> bool:
    """Return True only when the exact directory entry is confirmed absent."""

    try:
        ready_path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _dir_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    return flags


def _file_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    return flags


def open_owned_ready_artifact(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
) -> tuple[int, int]:
    """Open ready artifact via verified dirfds under layout.artifacts.

    Returns ``(file_fd, ready_dir_fd)``. Caller owns both descriptors.
    """

    key = repository_key(repository_id)
    name = artifact_id.hex
    if len(name) != 32 or any(ch not in "0123456789abcdef" for ch in name):
        raise OwnedPathError("artifact id is not an owned ready filename")

    def _open_component(path: str | Path, *, dir_fd: int | None, missing: str, label: str) -> int:
        try:
            if dir_fd is None:
                return os.open(path, _dir_flags() if label != "file" else _file_flags())
            flags = _file_flags() if label == "file" else _dir_flags()
            return os.open(path, flags, dir_fd=dir_fd)
        except FileNotFoundError as exc:
            raise OwnedPathError(missing) from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise OwnedPathError(f"{label} symlink or non-directory") from exc
            raise OwnedPathError(f"{label} is unavailable") from exc

    try:
        artifacts_fd = _open_component(
            layout.artifacts,
            dir_fd=None,
            missing="artifacts root is missing",
            label="artifacts root",
        )
    except OwnedPathError:
        raise
    try:
        os.set_inheritable(artifacts_fd, False)
        art_stat = os.fstat(artifacts_fd)
        if not stat.S_ISDIR(art_stat.st_mode):
            raise OwnedPathError("artifacts root is not a directory")
        repo_fd = _open_component(
            key,
            dir_fd=artifacts_fd,
            missing="repository artifact directory is missing",
            label="repository",
        )
        try:
            os.set_inheritable(repo_fd, False)
            repo_stat = os.fstat(repo_fd)
            if not stat.S_ISDIR(repo_stat.st_mode):
                raise OwnedPathError("repository artifact path is not a directory")
            ready_dir_fd = _open_component(
                "ready",
                dir_fd=repo_fd,
                missing="ready directory is missing",
                label="ready",
            )
            try:
                os.set_inheritable(ready_dir_fd, False)
                ready_stat = os.fstat(ready_dir_fd)
                if not stat.S_ISDIR(ready_stat.st_mode):
                    raise OwnedPathError("ready path is not a directory")
                file_fd = _open_component(
                    name,
                    dir_fd=ready_dir_fd,
                    missing="ready artifact file is missing",
                    label="file",
                )
                os.set_inheritable(file_fd, False)
                file_stat = os.fstat(file_fd)
                if not stat.S_ISREG(file_stat.st_mode):
                    os.close(file_fd)
                    raise OwnedPathError("ready artifact path is not a regular file")
                # Transfer ownership of ready_dir_fd + file_fd to caller.
                kept_ready = ready_dir_fd
                ready_dir_fd = -1
                return file_fd, kept_ready
            finally:
                if ready_dir_fd >= 0:
                    os.close(ready_dir_fd)
        finally:
            os.close(repo_fd)
    finally:
        os.close(artifacts_fd)


def try_unlink_owned_ready_artifact(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    recheck: Callable[[], bool],
    on_deleted: Callable[[], None] | None = None,
) -> str:
    """Delete an owned ready artifact via dirfd renameat/unlinkat.

    When ``on_deleted`` is provided it runs while the flock is still held, after
    the verified inode has been unlinked. Only outcome ``deleted`` means this
    call removed bytes; ``already_absent`` never stamps deletion evidence.
    """

    try:
        file_fd, ready_dir_fd = open_owned_ready_artifact(layout, repository_id, artifact_id)
    except OwnedPathError as exc:
        message = str(exc)
        if "missing" in message:
            return "already_absent"
        if "symlink" in message or "unavailable" in message:
            # Distinguish common failure modes for diagnostics.
            try:
                ready_path = artifact_ready_path(layout, repository_id, artifact_id)
                if stat.S_ISLNK(ready_path.lstat().st_mode):
                    return "symlink"
            except OSError:
                pass
            return "unlink_failed"
        return "unlink_failed"

    quarantine: str | None = None
    try:
        try:
            fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        try:
            fd_stat = os.fstat(file_fd)
            if not stat.S_ISREG(fd_stat.st_mode):
                return "not_regular_file"
            if fd_stat.st_nlink == 0:
                return "already_absent"
            if not recheck():
                return "ineligible"

            name = artifact_id.hex
            quarantine = f".deleting-{fd_stat.st_ino}-{name}"
            try:
                os.rename(name, quarantine, src_dir_fd=ready_dir_fd, dst_dir_fd=ready_dir_fd)
            except FileNotFoundError:
                return "already_absent"
            except OSError:
                return "unlink_failed"

            # Confirm the open fd still names the quarantined inode.
            post_rename = os.fstat(file_fd)
            if (post_rename.st_dev, post_rename.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                return "inode_mismatch"
            try:
                q_stat = os.stat(quarantine, dir_fd=ready_dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                return "inode_mismatch"
            except OSError:
                return "unlink_failed"
            if (q_stat.st_dev, q_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                return "inode_mismatch"
            if not stat.S_ISREG(q_stat.st_mode):
                return "not_regular_file"

            try:
                os.unlink(quarantine, dir_fd=ready_dir_fd)
            except FileNotFoundError:
                return "already_absent"
            except OSError:
                return "unlink_failed"
            quarantine = None

            # Original name must be absent; quarantine must be gone.
            try:
                os.stat(name, dir_fd=ready_dir_fd, follow_symlinks=False)
                return "path_recreated"
            except FileNotFoundError:
                pass
            except OSError:
                return "unlink_failed"

            if on_deleted is not None:
                try:
                    on_deleted()
                except Exception:
                    # Bytes are gone; leave stamp absent for a later verified retry.
                    return "stamp_failed"
            return "deleted"
        finally:
            try:
                fcntl.flock(file_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        if quarantine is not None:
            try:
                os.unlink(quarantine, dir_fd=ready_dir_fd)
            except OSError:
                pass
        os.close(file_fd)
        os.close(ready_dir_fd)


def try_unlink_ready_artifact_with_recheck(
    ready_path: Path,
    *,
    recheck: Callable[[], bool],
    layout: DurableLayout | None = None,
    repository_id: UUID | None = None,
    artifact_id: UUID | None = None,
    on_deleted: Callable[[], None] | None = None,
) -> str:
    """Delete ready bytes; prefer owned layout protocol when ids are provided."""

    if layout is not None and repository_id is not None and artifact_id is not None:
        expected = artifact_ready_path(layout, repository_id, artifact_id)
        if ready_path != expected:
            return "unexpected_path"
        return try_unlink_owned_ready_artifact(
            layout,
            repository_id,
            artifact_id,
            recheck=recheck,
            on_deleted=on_deleted,
        )

    # Legacy pathname path kept for narrow test helpers; still fail closed on symlink.
    open_flags = _file_flags()
    try:
        fd = os.open(ready_path, open_flags)
    except FileNotFoundError:
        return "already_absent"
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
                return "already_absent"
            try:
                path_stat = ready_path.lstat()
            except FileNotFoundError:
                return "already_absent"
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
            parent = ready_path.parent
            quarantine = parent / f".deleting-{fd_stat.st_ino}-{ready_path.name}"
            try:
                os.rename(ready_path, quarantine)
            except FileNotFoundError:
                return "already_absent"
            except OSError:
                return "unlink_failed"
            try:
                q_stat = quarantine.lstat()
                if (q_stat.st_dev, q_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                    return "inode_mismatch"
                quarantine.unlink()
            except FileNotFoundError:
                return "already_absent"
            except OSError:
                return "unlink_failed"
            if not ready_artifact_entry_absent(ready_path):
                return "path_recreated"
            if on_deleted is not None:
                try:
                    on_deleted()
                except Exception:
                    return "stamp_failed"
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
