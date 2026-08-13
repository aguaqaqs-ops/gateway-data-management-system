"""Exclusive admission pin for ready artifact bytes."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.publication import renameat2_noreplace
from gateway_repository_service.upload_artifact.visibility import (
    artifact_ready_path,
    verify_published_artifact_fd,
)

_HEX32 = frozenset("0123456789abcdef")


class StageDirStatus(StrEnum):
    OPENED = "opened"
    ABSENT = "absent"
    BUSY = "busy"
    MISMATCH = "mismatch"
    IO_ERROR = "io_error"


@dataclass(frozen=True, slots=True)
class StageDirLookup:
    status: StageDirStatus
    fd: int | None = None


def _is_single_path_component(name: str) -> bool:
    return bool(name) and "/" not in name and name not in {".", ".."} and "\x00" not in name


def _is_hex32(name: str) -> bool:
    return len(name) == 32 and all(ch in _HEX32 for ch in name)


def _is_stage_child_name(name: str) -> bool:
    return name == "victim" or name.startswith("final-") or name.startswith("doom-")


def link_from_fd(dir_fd: int, name: str, src_fd: int) -> None:
    if not _is_single_path_component(name):
        raise OSError("link name rejected")
    os.link(f"/proc/self/fd/{src_fd}", name, dst_dir_fd=dir_fd)


def _unlink_if_match_fd(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, open_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return False
        if int(st.st_dev) != int(expected_dev) or int(st.st_ino) != int(expected_ino):
            return False
    except OSError:
        return False
    finally:
        os.close(fd)
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def unlink_if_match(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    """Unlink ``name`` when fstat identity matches. Refuses hex32 ready names."""

    if not _is_single_path_component(name) or _is_hex32(name):
        return False
    return _unlink_if_match_fd(
        dir_fd,
        name,
        expected_dev=expected_dev,
        expected_ino=expected_ino,
    )


def rmdir_if_empty(dir_fd: int, name: str) -> bool:
    if not _is_single_path_component(name):
        return False
    try:
        os.rmdir(name, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def reclaim_stage_dir(
    ready_dir_fd: int,
    name: str,
    *,
    children: list[tuple[str, int, int]] | None = None,
) -> bool:
    """Unlink proof-backed stage children then rmdir if empty.

    ``children`` is ``(name, expected_dev, expected_ino)``. Without proofs no
    child is unlinked; empty stages may still rmdir. Live fstat is not proof.
    """

    if parse_unlink_stage_dir_name(name) is None:
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        stage_fd = os.open(name, flags, dir_fd=ready_dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        try:
            fcntl.flock(stage_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        try:
            for child_name, expected_dev, expected_ino in children or ():
                if not _is_stage_child_name(child_name):
                    continue
                _unlink_if_match_fd(
                    stage_fd,
                    child_name,
                    expected_dev=int(expected_dev),
                    expected_ino=int(expected_ino),
                )
            os.rmdir(name, dir_fd=ready_dir_fd)
            return True
        except OSError:
            return False
        finally:
            try:
                fcntl.flock(stage_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(stage_fd)


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


def open_owned_ready_dir(
    layout: DurableLayout,
    repository_id: UUID,
) -> int:
    """Open the owned ready directory via verified dirfds. Caller owns the fd."""

    key = repository_key(repository_id)

    def _open_component(path: str | Path, *, dir_fd: int | None, missing: str, label: str) -> int:
        try:
            if dir_fd is None:
                return os.open(path, _dir_flags())
            return os.open(path, _dir_flags(), dir_fd=dir_fd)
        except FileNotFoundError as exc:
            raise OwnedPathError(missing) from exc
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise OwnedPathError(f"{label} symlink or non-directory") from exc
            raise OwnedPathError(f"{label} is unavailable") from exc

    artifacts_fd = _open_component(
        layout.artifacts,
        dir_fd=None,
        missing="artifacts root is missing",
        label="artifacts root",
    )
    try:
        os.set_inheritable(artifacts_fd, False)
        repo_fd = _open_component(
            key,
            dir_fd=artifacts_fd,
            missing="repository artifact directory is missing",
            label="repository",
        )
        try:
            os.set_inheritable(repo_fd, False)
            ready_dir_fd = _open_component(
                "ready",
                dir_fd=repo_fd,
                missing="ready directory is missing",
                label="ready",
            )
            os.set_inheritable(ready_dir_fd, False)
            ready_stat = os.fstat(ready_dir_fd)
            if not stat.S_ISDIR(ready_stat.st_mode):
                os.close(ready_dir_fd)
                raise OwnedPathError("ready path is not a directory")
            kept = ready_dir_fd
            return kept
        finally:
            os.close(repo_fd)
    finally:
        os.close(artifacts_fd)


def _validate_generation(generation: str) -> None:
    if not generation:
        raise ValueError("generation must be non-empty")
    if "-" in generation:
        raise ValueError("generation must not contain '-'")


def quarantine_name_for(*, inode: int, artifact_id: UUID, generation: str) -> str:
    """Return the durable quarantine directory entry for an owned ready inode."""

    _validate_generation(generation)
    return f".deleting-{inode}-{generation}-{artifact_id.hex}"


def detach_name_for(*, inode: int, artifact_id: UUID, generation: str) -> str:
    """Return the transient rename target used to detach a ready directory entry."""

    _validate_generation(generation)
    return f".detach-{inode}-{generation}-{artifact_id.hex}"


def verify_sidecar_name_for(*, inode: int, generation: str, artifact_id: UUID, token: str) -> str:
    """Return the private verify sidecar used during rename-verify-unlink.

    Verify names are inventory-recoverable via ``parse_unlink_verify_name`` but
    must not match ``.deleting-`` / ``.detach-`` inventory parsers.
    """

    _validate_generation(generation)
    if not token:
        raise ValueError("token must be non-empty")
    if "-" in token:
        raise ValueError("token must not contain '-'")
    return f".unlink-verify-{inode}-{generation}-{artifact_id.hex}-{token}"


def _parse_sidecar_name(name: str, *, prefix: str) -> tuple[int, UUID, str | None] | None:
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix) :]
    if "-" not in rest:
        return None
    artifact_hex = rest.rsplit("-", 1)[1]
    if len(artifact_hex) != 32 or any(ch not in "0123456789abcdef" for ch in artifact_hex):
        return None
    remainder = rest[: -(len(artifact_hex) + 1)]
    if not remainder:
        return None
    if "-" in remainder:
        ino_text, generation = remainder.split("-", 1)
        if not generation or "-" in generation:
            return None
    elif remainder.isdigit():
        ino_text = remainder
        generation = None
    else:
        return None
    if not ino_text.isdigit():
        return None
    try:
        return int(ino_text), UUID(hex=artifact_hex), generation
    except ValueError:
        return None


def parse_quarantine_name(name: str) -> tuple[int, UUID, str | None] | None:
    """Parse quarantine sidecar names; return None when malformed."""

    return _parse_sidecar_name(name, prefix=".deleting-")


def parse_detach_name(name: str) -> tuple[int, UUID, str | None] | None:
    """Parse detach sidecar names; return None when malformed."""

    return _parse_sidecar_name(name, prefix=".detach-")


STAGE_VICTIM = "victim"


def unlink_stage_dir_name(*, artifact_id: UUID, token: str) -> str:
    """Return the private staging directory used during rename-verify-unlink."""

    if not token:
        raise ValueError("token must be non-empty")
    if "-" in token:
        raise ValueError("token must not contain '-'")
    return f".unlink-stage-{artifact_id.hex}-{token}"


def parse_unlink_stage_dir_name(name: str) -> tuple[UUID, str] | None:
    """Parse ``.unlink-stage-{artifact_hex}-{token}``."""

    prefix = ".unlink-stage-"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix) :]
    if "-" not in rest:
        return None
    token = rest.rsplit("-", 1)[1]
    if not token or "-" in token:
        return None
    artifact_hex = rest[: -(len(token) + 1)]
    if len(artifact_hex) != 32 or any(ch not in "0123456789abcdef" for ch in artifact_hex):
        return None
    try:
        return UUID(hex=artifact_hex), token
    except ValueError:
        return None


def list_unlink_stage_dir_names(ready_dir_fd: int) -> list[str]:
    """Return parsed ``.unlink-stage-*`` directory names under ``ready_dir_fd``."""

    try:
        names = os.listdir(ready_dir_fd)
    except OSError:
        return []
    result: list[str] = []
    for name in names:
        if parse_unlink_stage_dir_name(name) is not None:
            result.append(name)
    return result


def parse_unlink_verify_name(name: str) -> tuple[int, UUID, str, str] | None:
    """Parse ``.unlink-verify-{ino}-{generation}-{artifact_hex}-{token}``."""

    prefix = ".unlink-verify-"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix) :]
    if "-" not in rest:
        return None
    token = rest.rsplit("-", 1)[1]
    if not token or "-" in token:
        return None
    rest = rest[: -(len(token) + 1)]
    if "-" not in rest:
        return None
    artifact_hex = rest.rsplit("-", 1)[1]
    if len(artifact_hex) != 32 or any(ch not in "0123456789abcdef" for ch in artifact_hex):
        return None
    remainder = rest[: -(len(artifact_hex) + 1)]
    if "-" not in remainder:
        return None
    ino_text, generation = remainder.split("-", 1)
    if not ino_text.isdigit() or not generation or "-" in generation:
        return None
    try:
        return int(ino_text), UUID(hex=artifact_hex), generation, token
    except ValueError:
        return None


def parse_any_recoverable_sidecar(name: str) -> tuple[int, UUID, str | None, str] | None:
    """Return (ino, artifact_id, generation, kind) where kind in quarantine|detach|unlink_verify.

    For unlink_verify generation is always str (never None).
    Legacy deleting/detach may have generation=None.
    """

    parsed_verify = parse_unlink_verify_name(name)
    if parsed_verify is not None:
        ino, artifact_id, generation, _token = parsed_verify
        return ino, artifact_id, generation, "unlink_verify"
    parsed_quarantine = parse_quarantine_name(name)
    if parsed_quarantine is not None:
        ino, artifact_id, quarantine_generation = parsed_quarantine
        return ino, artifact_id, quarantine_generation, "quarantine"
    parsed_detach = parse_detach_name(name)
    if parsed_detach is not None:
        ino, artifact_id, detach_generation = parsed_detach
        return ino, artifact_id, detach_generation, "detach"
    return None


def _open_stage_dir(ready_dir_fd: int, stage_name: str) -> int:
    return os.open(stage_name, _dir_flags(), dir_fd=ready_dir_fd)


def lookup_unlink_stage_dir(ready_dir_fd: int, stage_name: str) -> StageDirLookup:
    """Classify a ``.unlink-stage-*`` name without following symlinks."""

    try:
        stage_dir_fd = _open_stage_dir(ready_dir_fd, stage_name)
    except FileNotFoundError:
        return StageDirLookup(StageDirStatus.ABSENT)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            return StageDirLookup(StageDirStatus.MISMATCH)
        if exc.errno in {errno.EAGAIN, errno.EBUSY}:
            return StageDirLookup(StageDirStatus.BUSY)
        if exc.errno in {errno.EIO, errno.EPERM, errno.EACCES}:
            return StageDirLookup(StageDirStatus.IO_ERROR)
        if exc.errno == errno.ENOENT:
            return StageDirLookup(StageDirStatus.ABSENT)
        return StageDirLookup(StageDirStatus.IO_ERROR)
    try:
        stage_stat = os.fstat(stage_dir_fd)
    except OSError as exc:
        os.close(stage_dir_fd)
        if exc.errno in {errno.EIO, errno.EPERM, errno.EACCES}:
            return StageDirLookup(StageDirStatus.IO_ERROR)
        return StageDirLookup(StageDirStatus.IO_ERROR)
    if not stat.S_ISDIR(stage_stat.st_mode):
        os.close(stage_dir_fd)
        return StageDirLookup(StageDirStatus.MISMATCH)
    if (int(stage_stat.st_mode) & 0o777) not in {0o700, 0o750}:
        os.close(stage_dir_fd)
        return StageDirLookup(StageDirStatus.MISMATCH)
    return StageDirLookup(StageDirStatus.OPENED, fd=stage_dir_fd)


def open_owned_unlink_stage_dir(ready_dir_fd: int, stage_name: str) -> int | None:
    """Open a ``.unlink-stage-*`` dir without following symlinks.

    Returns a directory fd for a real directory with mode ``0700`` or ``0750``.
    Caller owns the returned fd. Non-opened lookups return ``None``.
    """

    lookup = lookup_unlink_stage_dir(ready_dir_fd, stage_name)
    return lookup.fd


def lock_unlink_stage_dir(stage_dir_fd: int) -> bool:
    """Acquire exclusive non-blocking flock on an owned stage directory fd."""

    try:
        fcntl.flock(stage_dir_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    except OSError:
        return False
    return True


def unlock_unlink_stage_dir(stage_dir_fd: int) -> None:
    try:
        fcntl.flock(stage_dir_fd, fcntl.LOCK_UN)
    except OSError:
        pass


def normalize_unlink_stage_victim_via_fd(
    stage_dir_fd: int,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    """Ensure owned ``victim`` exists inside an already-locked stage directory fd.

    Promotes a unique leftover ``final-*`` / ``doom-*`` regular file to ``victim``
    only after open+fstat proves ``(dev,ino) == expected``. Caller must hold
    ``LOCK_EX`` on ``stage_dir_fd``. Foreign entries are left untouched.
    """

    def _matches(st: os.stat_result) -> bool:
        return (
            stat.S_ISREG(st.st_mode)
            and int(st.st_dev) == int(expected_dev)
            and int(st.st_ino) == int(expected_ino)
        )

    try:
        victim_fd = os.open(STAGE_VICTIM, _file_flags(), dir_fd=stage_dir_fd)
    except FileNotFoundError:
        victim_fd = None
    except OSError:
        return False
    if victim_fd is not None:
        try:
            return _matches(os.fstat(victim_fd))
        except OSError:
            return False
        finally:
            os.close(victim_fd)

    try:
        children = os.listdir(stage_dir_fd)
    except OSError:
        return False
    candidates: list[str] = []
    for name in children:
        if not (name.startswith("final-") or name.startswith("doom-")):
            continue
        try:
            child_fd = os.open(name, _file_flags(), dir_fd=stage_dir_fd)
        except OSError:
            continue
        try:
            child_stat = os.fstat(child_fd)
        except OSError:
            os.close(child_fd)
            continue
        os.close(child_fd)
        if _matches(child_stat):
            candidates.append(name)
    if len(candidates) != 1:
        return False
    try:
        renameat2_noreplace(stage_dir_fd, candidates[0], stage_dir_fd, STAGE_VICTIM)
    except OSError:
        return False
    try:
        after_fd = os.open(STAGE_VICTIM, _file_flags(), dir_fd=stage_dir_fd)
    except OSError:
        return False
    try:
        return _matches(os.fstat(after_fd))
    except OSError:
        return False
    finally:
        os.close(after_fd)


def remove_empty_stage_dir_if_same_inode(
    ready_dir_fd: int,
    stage_name: str,
    stage_dir_fd: int,
) -> None:
    """Remove empty stage directory when safe.

    Caller must hold ``stage_dir_fd``. rmdir fails closed if non-empty.
    """

    del stage_dir_fd
    rmdir_if_empty(ready_dir_fd, stage_name)


def prove_size0_owned_name_terminal(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    """Prove ``name`` is absent or an owned size-0 regular tombstone.

    Never pathname-unlinks. Same-euid actors can replace a name between fstat and
    unlink; under that threat model the only safe terminal proofs are absence or
    a currently observed owned size-0 regular file.
    """

    open_flags = _file_flags()
    try:
        fd = os.open(name, open_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        st = os.fstat(fd)
    except OSError:
        return False
    finally:
        os.close(fd)
    if not stat.S_ISREG(st.st_mode):
        return False
    if int(st.st_dev) != int(expected_dev) or int(st.st_ino) != int(expected_ino):
        return False
    if int(st.st_size) != 0:
        return False
    # Fresh re-open/fstat so a racing replacement is observed before success.
    try:
        fd = os.open(name, open_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        return (
            stat.S_ISREG(st.st_mode)
            and int(st.st_dev) == int(expected_dev)
            and int(st.st_ino) == int(expected_ino)
            and int(st.st_size) == 0
        )
    except OSError:
        return False
    finally:
        os.close(fd)


def reclaim_size0_owned_name(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
    artifact_id: UUID | None = None,
) -> bool:
    """Prove size-0/absent then unlink the owned tombstone name."""

    del artifact_id
    if not prove_size0_owned_name_terminal(
        dir_fd,
        name,
        expected_dev=expected_dev,
        expected_ino=expected_ino,
    ):
        return False
    return unlink_if_match(
        dir_fd,
        name,
        expected_dev=expected_dev,
        expected_ino=expected_ino,
    )


def destroy_owned_bytes_and_reclaim_names(
    ready_dir_fd: int,
    inode_fd: int,
    expected: os.stat_result,
    names: list[str],
    *,
    artifact_id: UUID,
    generation: str | None = None,
    held_stage_dir_fd: int | None = None,
    held_stage_name: str | None = None,
) -> bool:
    """fd-truncate owned bytes, prove size-0, then unlink/rmdir tombs.

    Enumerates ``.unlink-stage-*`` only for ``artifact_id``. When
    ``held_stage_name`` matches, reuses ``held_stage_dir_fd`` without re-locking.
    Foreign artifact stages are skipped and do not fail the operation.
    """

    del generation  # reserved for future generation-scoped verify filtering
    if not _ftruncate_inode_to_empty(inode_fd, expected):
        return False
    expected_dev = int(expected.st_dev)
    expected_ino = int(expected.st_ino)
    for name in names:
        if not name:
            continue
        if not reclaim_size0_owned_name(
            ready_dir_fd,
            name,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            artifact_id=artifact_id,
        ):
            return False
    # Historical Round12 verify/stage tombstones for this inode must also reclaim.
    try:
        entries = os.listdir(ready_dir_fd)
    except OSError:
        return False
    for entry_name in entries:
        parsed_verify = parse_unlink_verify_name(entry_name)
        if parsed_verify is not None:
            ino, verify_artifact_id, _generation, _token = parsed_verify
            if verify_artifact_id != artifact_id:
                continue
            if int(ino) == expected_ino:
                if not reclaim_size0_owned_name(
                    ready_dir_fd,
                    entry_name,
                    expected_dev=expected_dev,
                    expected_ino=expected_ino,
                    artifact_id=artifact_id,
                ):
                    return False
            continue
        parsed_stage = parse_unlink_stage_dir_name(entry_name)
        if parsed_stage is None:
            continue
        stage_artifact_id, _token = parsed_stage
        if stage_artifact_id != artifact_id:
            continue
        owned_stage_fd = False
        stage_fd: int | None = None
        stage_locked_here = False
        try:
            if held_stage_name is not None and entry_name == held_stage_name:
                if held_stage_dir_fd is None:
                    return False
                stage_fd = held_stage_dir_fd
            else:
                stage_fd = open_owned_unlink_stage_dir(ready_dir_fd, entry_name)
                if stage_fd is None:
                    return False
                owned_stage_fd = True
                if not lock_unlink_stage_dir(stage_fd):
                    return False
                stage_locked_here = True
            assert stage_fd is not None
            try:
                children = os.listdir(stage_fd)
            except OSError:
                return False
            for child in children:
                open_flags = _file_flags()
                try:
                    child_fd = os.open(child, open_flags, dir_fd=stage_fd)
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
                try:
                    cst = os.fstat(child_fd)
                except OSError:
                    return False
                finally:
                    os.close(child_fd)
                if not stat.S_ISREG(cst.st_mode):
                    return False
                if int(cst.st_dev) != expected_dev or int(cst.st_ino) != expected_ino:
                    # Foreign inode inside our stage: skip, do not fail batch.
                    continue
                if int(cst.st_size) != 0:
                    return False
                if not reclaim_size0_owned_name(
                    stage_fd,
                    child,
                    expected_dev=expected_dev,
                    expected_ino=expected_ino,
                    artifact_id=artifact_id,
                ):
                    return False
            if stage_locked_here or (
                held_stage_name is not None and entry_name == held_stage_name
            ):
                if stage_locked_here:
                    unlock_unlink_stage_dir(stage_fd)
                    stage_locked_here = False
                if not rmdir_if_empty(ready_dir_fd, entry_name):
                    # Non-empty residual: leave for next sweep; do not fail destroy.
                    pass
        finally:
            if stage_locked_here and stage_fd is not None:
                unlock_unlink_stage_dir(stage_fd)
            if owned_stage_fd and stage_fd is not None:
                os.close(stage_fd)
    return True


def _ftruncate_inode_to_empty(inode_fd: int, expected: os.stat_result) -> bool:
    """Zero file content via a writable fd reopen of ``inode_fd`` (fd-stable)."""

    try:
        live = os.fstat(inode_fd)
    except OSError:
        return False
    if (live.st_dev, live.st_ino) != (expected.st_dev, expected.st_ino):
        return False
    wr_fd: int | None = None
    after: os.stat_result | None = None
    try:
        wr_fd = os.open(f"/proc/self/fd/{inode_fd}", os.O_RDWR)
        os.ftruncate(wr_fd, 0)
        after = os.fstat(inode_fd)
    except OSError:
        return False
    finally:
        if wr_fd is not None:
            os.close(wr_fd)
    if after is None:
        return False
    return (
        after.st_size == 0
        and (after.st_dev, after.st_ino) == (expected.st_dev, expected.st_ino)
    )
