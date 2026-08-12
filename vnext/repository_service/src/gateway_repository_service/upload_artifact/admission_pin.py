"""Exclusive admission pin for ready artifact bytes."""

from __future__ import annotations

import errno
import fcntl
import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.publication import renameat2_noreplace
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


def _find_matching_quarantine(
    ready_dir_fd: int,
    *,
    inode: int,
    artifact_id: UUID,
) -> tuple[str, str] | None:
    """Reuse an existing generation-bound quarantine for the same inode+artifact."""

    try:
        names = os.listdir(ready_dir_fd)
    except OSError:
        return None
    for name in names:
        parsed = parse_quarantine_name(name)
        if parsed is None:
            continue
        parsed_ino, parsed_artifact_id, generation = parsed
        if (
            generation is None
            or parsed_ino != int(inode)
            or parsed_artifact_id != artifact_id
        ):
            continue
        try:
            st = os.stat(name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except OSError:
            continue
        if int(st.st_ino) != int(inode) or not stat.S_ISREG(st.st_mode):
            continue
        return name, generation
    return None


def find_unlink_verify_sidecar_name(
    ready_dir_fd: int,
    *,
    inode: int,
    artifact_id: UUID,
    generation: str,
) -> str | None:
    """Return a private ``.unlink-verify-*`` entry matching inode/generation/artifact."""

    prefix = f".unlink-verify-{inode}-{generation}-{artifact_id.hex}-"
    try:
        names = os.listdir(ready_dir_fd)
    except OSError:
        return None
    for name in names:
        if not name.startswith(prefix):
            continue
        if parse_unlink_verify_name(name) is None:
            continue
        return name
    return None


def _open_stage_dir(ready_dir_fd: int, stage_name: str) -> int:
    return os.open(stage_name, _dir_flags(), dir_fd=ready_dir_fd)


def open_owned_unlink_stage_dir(ready_dir_fd: int, stage_name: str) -> int | None:
    """Open a ``.unlink-stage-*`` dir without following symlinks.

    Returns a directory fd whose ``fstat`` proves a real directory owned by the
    current euid with mode ``0o700``, or ``None`` when unusable. Caller owns
    the returned fd.
    """

    try:
        stage_dir_fd = _open_stage_dir(ready_dir_fd, stage_name)
    except OSError:
        return None
    try:
        stage_stat = os.fstat(stage_dir_fd)
    except OSError:
        os.close(stage_dir_fd)
        return None
    if not stat.S_ISDIR(stage_stat.st_mode):
        os.close(stage_dir_fd)
        return None
    if int(stage_stat.st_uid) != int(os.geteuid()):
        os.close(stage_dir_fd)
        return None
    if (int(stage_stat.st_mode) & 0o777) != 0o700:
        os.close(stage_dir_fd)
        return None
    return stage_dir_fd


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
    """Diagnose-only: never rename/rmdir re-resolved stage pathnames.

    Empty stage directories may remain as residuals. Pathname trash-rename/rmdir
    is unsafe against same-euid directory-entry replacement.
    """

    del ready_dir_fd, stage_name, stage_dir_fd


def reclaim_size0_owned_name(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    """Best-effort unlink of a size-0 owned tombstone name.

    Opens and fstats immediately before unlink; non-empty or inode mismatch skips
    so foreign content is never destroyed. Absent name counts as success.
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
    # Re-open and re-check immediately before unlink (fresh fstat, not a stale gate).
    try:
        fd = os.open(name, open_flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if (
            not stat.S_ISREG(st.st_mode)
            or int(st.st_dev) != int(expected_dev)
            or int(st.st_ino) != int(expected_ino)
            or int(st.st_size) != 0
        ):
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


def destroy_owned_bytes_and_reclaim_names(
    ready_dir_fd: int,
    inode_fd: int,
    expected: os.stat_result,
    names: list[str],
) -> bool:
    """fd-truncate owned bytes, then best-effort reclaim size-0 directory names.

    Does not create ``.unlink-stage-*`` / ``.unlink-verify-*`` entries.
    """

    if not _ftruncate_inode_to_empty(inode_fd, expected):
        return False
    expected_dev = int(expected.st_dev)
    expected_ino = int(expected.st_ino)
    for name in names:
        if name:
            reclaim_size0_owned_name(
                ready_dir_fd,
                name,
                expected_dev=expected_dev,
                expected_ino=expected_ino,
            )
    # Reclaim historical Round12 verify/stage tombstones for this inode.
    try:
        entries = os.listdir(ready_dir_fd)
    except OSError:
        return True
    for entry_name in entries:
        parsed_verify = parse_unlink_verify_name(entry_name)
        if parsed_verify is not None:
            ino, _artifact_id, _generation, _token = parsed_verify
            if int(ino) == expected_ino:
                reclaim_size0_owned_name(
                    ready_dir_fd,
                    entry_name,
                    expected_dev=expected_dev,
                    expected_ino=expected_ino,
                )
            continue
        parsed_stage = parse_unlink_stage_dir_name(entry_name)
        if parsed_stage is None:
            continue
        stage_fd = open_owned_unlink_stage_dir(ready_dir_fd, entry_name)
        if stage_fd is None:
            continue
        try:
            if not lock_unlink_stage_dir(stage_fd):
                continue
            try:
                try:
                    children = os.listdir(stage_fd)
                except OSError:
                    continue
                for child in children:
                    reclaim_size0_owned_name(
                        stage_fd,
                        child,
                        expected_dev=expected_dev,
                        expected_ino=expected_ino,
                    )
                # Leave empty stage dir in place (no pathname rmdir).
            finally:
                unlock_unlink_stage_dir(stage_fd)
        finally:
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


def _reanchor_inode_to_verify_sidecar(
    ready_dir_fd: int,
    inode_fd: int,
    *,
    expected: os.stat_result,
    artifact_id: UUID,
    generation: str,
) -> str | None:
    """Hard-link ``inode_fd`` to a generation-bound ``.unlink-verify-*`` under ready."""

    try:
        live = os.fstat(inode_fd)
    except OSError:
        return None
    if (live.st_dev, live.st_ino) != (expected.st_dev, expected.st_ino):
        return None
    for _ in range(8):
        token = secrets.token_hex(8)
        name = verify_sidecar_name_for(
            inode=int(expected.st_ino),
            generation=generation,
            artifact_id=artifact_id,
            token=token,
        )
        try:
            os.link(
                f"/proc/self/fd/{inode_fd}",
                name,
                dst_dir_fd=ready_dir_fd,
            )
        except FileExistsError:
            continue
        except OSError:
            return None
        return name
    return None


def _restore_staged_victim_best_effort(
    ready_dir_fd: int,
    stage_dir_fd: int,
    *,
    source_name: str | None,
    stage_name: str,
    expected: os.stat_result,
    artifact_id: UUID,
    generation: str,
) -> None:
    """Rename ``victim`` out of a staging directory to a recoverable ready entry.

    Never pathname-rmdir the stage directory: empty stages may remain as residuals.
    """

    parsed = parse_unlink_stage_dir_name(stage_name)
    token = parsed[1] if parsed is not None else secrets.token_hex(8)
    restore_names: list[str] = []
    if source_name is not None:
        restore_names.append(source_name)
    restore_names.append(
        verify_sidecar_name_for(
            inode=int(expected.st_ino),
            generation=generation,
            artifact_id=artifact_id,
            token=token,
        )
    )
    for restore_name in restore_names:
        try:
            os.stat(restore_name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                renameat2_noreplace(stage_dir_fd, STAGE_VICTIM, ready_dir_fd, restore_name)
                break
            except OSError:
                continue
        except OSError:
            continue


def unlink_verified_inode_via_staging(
    ready_dir_fd: int,
    *,
    source_name: str | None,
    stage_name: str | None,
    inode_fd: int,
    expected: os.stat_result,
    artifact_id: UUID,
    generation: str,
    stage_dir_fd: int | None = None,
) -> bool:
    """Destroy artifact bytes via exclusive staging + mandatory linkat + fd truncate.

    When ``source_name`` is set, create a fresh ``.unlink-stage-*`` directory and
    rename the ready entry into ``victim`` inside it. When ``stage_name`` is set
    instead, the victim is already staged.

    When ``stage_dir_fd`` is provided with ``stage_name``, the caller already holds
    ``LOCK_EX`` on that fd; this function will not close or unlock it.

    Success path: linkat to ``.unlink-verify-*`` (fail-closed if None), then
    ``ftruncate`` via ``/proc/self/fd`` so foreign pathname replacements are never
    unlinked. Tombstone names (final/verify) may remain at size 0.
    """

    if (source_name is None) == (stage_name is None):
        return False
    if stage_dir_fd is not None and stage_name is None:
        return False
    if stage_dir_fd is not None and source_name is not None:
        return False

    try:
        live = os.fstat(inode_fd)
    except OSError:
        return False
    if (live.st_dev, live.st_ino) != (expected.st_dev, expected.st_ino):
        return False

    active_stage_name = stage_name
    owned_stage_fd = stage_dir_fd is None
    stage_locked = stage_dir_fd is not None
    victim_fd: int | None = None
    close_stage_fd = stage_dir_fd

    try:
        if source_name is not None:
            created = False
            for _ in range(8):
                token = secrets.token_hex(8)
                candidate = unlink_stage_dir_name(artifact_id=artifact_id, token=token)
                try:
                    os.mkdir(candidate, 0o700, dir_fd=ready_dir_fd)
                except FileExistsError:
                    continue
                except OSError:
                    return False
                active_stage_name = candidate
                created = True
                break
            if not created or active_stage_name is None:
                return False

            close_stage_fd = open_owned_unlink_stage_dir(ready_dir_fd, active_stage_name)
            if close_stage_fd is None:
                return False
            if not lock_unlink_stage_dir(close_stage_fd):
                os.close(close_stage_fd)
                close_stage_fd = None
                return False
            stage_locked = True
            try:
                renameat2_noreplace(ready_dir_fd, source_name, close_stage_fd, STAGE_VICTIM)
            except OSError:
                return False
        else:
            assert active_stage_name is not None
            if close_stage_fd is None:
                close_stage_fd = open_owned_unlink_stage_dir(ready_dir_fd, active_stage_name)
                if close_stage_fd is None:
                    return False
                if not lock_unlink_stage_dir(close_stage_fd):
                    os.close(close_stage_fd)
                    close_stage_fd = None
                    return False
                stage_locked = True
                owned_stage_fd = True
            if not normalize_unlink_stage_victim_via_fd(
                close_stage_fd,
                expected_dev=int(expected.st_dev),
                expected_ino=int(expected.st_ino),
            ):
                return False

        assert close_stage_fd is not None and active_stage_name is not None
        try:
            victim_fd = os.open(STAGE_VICTIM, _file_flags(), dir_fd=close_stage_fd)
        except OSError:
            return False

        try:
            victim_stat = os.fstat(victim_fd)
        except OSError:
            return False

        if (victim_stat.st_dev, victim_stat.st_ino) != (expected.st_dev, expected.st_ino):
            _restore_staged_victim_best_effort(
                ready_dir_fd,
                close_stage_fd,
                source_name=source_name,
                stage_name=active_stage_name,
                expected=expected,
                artifact_id=artifact_id,
                generation=generation,
            )
            return False

        final_name = f"final-{secrets.token_hex(8)}"
        try:
            renameat2_noreplace(close_stage_fd, STAGE_VICTIM, close_stage_fd, final_name)
        except OSError:
            _restore_staged_victim_best_effort(
                ready_dir_fd,
                close_stage_fd,
                source_name=source_name,
                stage_name=active_stage_name,
                expected=expected,
                artifact_id=artifact_id,
                generation=generation,
            )
            return False

        final_fd: int | None = None
        try:
            try:
                final_fd = os.open(final_name, _file_flags(), dir_fd=close_stage_fd)
            except OSError:
                try:
                    renameat2_noreplace(close_stage_fd, final_name, close_stage_fd, STAGE_VICTIM)
                except OSError:
                    pass
                _restore_staged_victim_best_effort(
                    ready_dir_fd,
                    close_stage_fd,
                    source_name=source_name,
                    stage_name=active_stage_name,
                    expected=expected,
                    artifact_id=artifact_id,
                    generation=generation,
                )
                return False
            try:
                final_stat = os.fstat(final_fd)
            except OSError:
                try:
                    renameat2_noreplace(close_stage_fd, final_name, close_stage_fd, STAGE_VICTIM)
                except OSError:
                    pass
                _restore_staged_victim_best_effort(
                    ready_dir_fd,
                    close_stage_fd,
                    source_name=source_name,
                    stage_name=active_stage_name,
                    expected=expected,
                    artifact_id=artifact_id,
                    generation=generation,
                )
                return False
            if (final_stat.st_dev, final_stat.st_ino) != (expected.st_dev, expected.st_ino):
                try:
                    renameat2_noreplace(close_stage_fd, final_name, close_stage_fd, STAGE_VICTIM)
                except OSError:
                    pass
                _restore_staged_victim_best_effort(
                    ready_dir_fd,
                    close_stage_fd,
                    source_name=source_name,
                    stage_name=active_stage_name,
                    expected=expected,
                    artifact_id=artifact_id,
                    generation=generation,
                )
                return False

            # Fail-closed: durable verify link is mandatory before content destroy.
            anchor_name = _reanchor_inode_to_verify_sidecar(
                ready_dir_fd,
                inode_fd,
                expected=expected,
                artifact_id=artifact_id,
                generation=generation,
            )
            if anchor_name is None:
                try:
                    renameat2_noreplace(close_stage_fd, final_name, close_stage_fd, STAGE_VICTIM)
                except OSError:
                    pass
                else:
                    _restore_staged_victim_best_effort(
                        ready_dir_fd,
                        close_stage_fd,
                        source_name=source_name,
                        stage_name=active_stage_name,
                        expected=expected,
                        artifact_id=artifact_id,
                        generation=generation,
                    )
                return False

            if not _ftruncate_inode_to_empty(inode_fd, expected):
                return False
            return True
        finally:
            if final_fd is not None:
                os.close(final_fd)
    except OSError:
        if close_stage_fd is not None and active_stage_name is not None:
            try:
                os.stat(STAGE_VICTIM, dir_fd=close_stage_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            else:
                _restore_staged_victim_best_effort(
                    ready_dir_fd,
                    close_stage_fd,
                    source_name=source_name,
                    stage_name=active_stage_name,
                    expected=expected,
                    artifact_id=artifact_id,
                    generation=generation,
                )
        return False
    finally:
        if victim_fd is not None:
            os.close(victim_fd)
        if owned_stage_fd and close_stage_fd is not None:
            if stage_locked:
                unlock_unlink_stage_dir(close_stage_fd)
            os.close(close_stage_fd)



def unlink_sidecar_rename_verify(
    ready_dir_fd: int,
    sidecar_name: str,
    q_fd: int,
    expected: os.stat_result,
    *,
    artifact_id: UUID,
    generation: str,
) -> bool:
    """Destroy sidecar bytes via fd-truncate and reclaim the size-0 name.

    Does not create staging/verify tombstones. ``artifact_id`` / ``generation``
    retained for call-site compatibility.
    """

    del artifact_id, generation
    return destroy_owned_bytes_and_reclaim_names(
        ready_dir_fd,
        q_fd,
        expected,
        [sidecar_name],
    )


def try_detach_ready_directory_entry(
    *,
    ready_dir_fd: int,
    file_fd: int,
    ready_name: str,
    fd_stat: os.stat_result,
    artifact_id: UUID,
    generation: str,
) -> tuple[str, str | None]:
    """Rename ``ready_name`` to ``.detach-*`` without destroying bytes.

    Pre-stamp detach must preserve package payload. Destruction happens only
    after the second eligibility recheck and durable receipt stamp.
    """

    try:
        before = os.fstat(file_fd)
    except OSError:
        return "unlink_failed", None
    if before.st_nlink < 2:
        return "replaced", None
    original_size = int(before.st_size)

    detach = detach_name_for(
        inode=int(fd_stat.st_ino),
        artifact_id=artifact_id,
        generation=generation,
    )
    try:
        renameat2_noreplace(ready_dir_fd, ready_name, ready_dir_fd, detach)
    except FileNotFoundError:
        if os.fstat(file_fd).st_nlink != 1:
            return "replaced", None
        return "ok", None
    except FileExistsError:
        return "unlink_failed", None
    except OSError:
        return "unlink_failed", None

    try:
        det_stat = os.stat(detach, dir_fd=ready_dir_fd, follow_symlinks=False)
    except OSError:
        return "unlink_failed", detach

    if (det_stat.st_dev, det_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
        try:
            os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                renameat2_noreplace(ready_dir_fd, detach, ready_dir_fd, ready_name)
                return "replaced", None
            except (FileExistsError, OSError):
                return "replaced", None
        except OSError:
            return "replaced", None
        return "replaced", None

    open_flags = _file_flags()
    det_fd: int | None = None
    try:
        try:
            det_fd = os.open(detach, open_flags, dir_fd=ready_dir_fd)
        except OSError:
            return "unlink_failed", detach
        try:
            det_fd_stat = os.fstat(det_fd)
        except OSError:
            return "unlink_failed", detach
        if (det_fd_stat.st_dev, det_fd_stat.st_ino) != (det_stat.st_dev, det_stat.st_ino):
            return "unlink_failed", detach
        if not stat.S_ISREG(det_fd_stat.st_mode):
            return "unlink_failed", detach
    finally:
        if det_fd is not None:
            os.close(det_fd)

    try:
        after = os.fstat(file_fd)
    except OSError:
        return "unlink_failed", detach
    if int(after.st_size) != original_size:
        return "unlink_failed", detach
    if (after.st_dev, after.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
        return "unlink_failed", detach
    try:
        os.stat(ready_name, dir_fd=ready_dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "ok", detach
    except OSError:
        return "unlink_failed", detach
    return "unlink_failed", detach


def try_unlink_owned_ready_artifact(
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    *,
    recheck: Callable[[], bool],
    on_deleted: Callable[[int, int, str], None] | None = None,
    on_intent: Callable[[int, int, str], None] | None = None,
    on_clear_intent: Callable[[int, int, str], None] | None = None,
    on_clear_receipt: Callable[[int, int, str], None] | None = None,
) -> str:
    """Delete an owned ready artifact via fd-stable linkat quarantine.

    Protocol (while flock is held):
    1. linkat quarantine for the locked inode
    2. durable delete intent (phase quarantined)
    3. recheck eligibility
    4. rename-only detach of ready (bytes preserved)
    5. recheck again, then stamp, then fd-truncate + reclaim size-0 names

    Replacement at the ready name never stamps and never returns ``deleted``.
    """

    try:
        file_fd, ready_dir_fd = open_owned_ready_artifact(layout, repository_id, artifact_id)
    except OwnedPathError as exc:
        message = str(exc)
        if "missing" in message:
            return "already_absent"
        if "symlink" in message or "unavailable" in message:
            try:
                ready_path = artifact_ready_path(layout, repository_id, artifact_id)
                if stat.S_ISLNK(ready_path.lstat().st_mode):
                    return "symlink"
            except OSError:
                pass
            return "unlink_failed"
        return "unlink_failed"

    owned_detach: str | None = None
    keep_quarantine_on_abort = False
    intent_written = False
    locked_dev: int | None = None
    locked_ino: int | None = None
    locked_generation: str | None = None

    def _clear_intent_best_effort() -> None:
        nonlocal intent_written
        if not intent_written or on_clear_intent is None:
            return
        if locked_dev is None or locked_ino is None or locked_generation is None:
            return
        try:
            on_clear_intent(locked_dev, locked_ino, locked_generation)
            intent_written = False
        except Exception:
            pass

    def _abort_replaced() -> str:
        _clear_intent_best_effort()
        return "replaced"

    def _cleanup_owned_sidecars_under_lock() -> None:
        # Abort/ineligible: never pathname-unlink or truncate. Leave full-byte
        # sidecars as diagnose tombstones; clear intent when safe to abandon.
        if keep_quarantine_on_abort:
            return
        _clear_intent_best_effort()

    try:
        try:
            fcntl.flock(file_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        try:
            try:
                fd_stat = os.fstat(file_fd)
                if not stat.S_ISREG(fd_stat.st_mode):
                    return "not_regular_file"
                if fd_stat.st_nlink == 0:
                    return "already_absent"

                name = artifact_id.hex
                try:
                    name_stat = os.stat(name, dir_fd=ready_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return "already_absent"
                except OSError:
                    return "unlink_failed"
                if (name_stat.st_dev, name_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                    return "inode_mismatch"

                locked_dev = int(fd_stat.st_dev)
                locked_ino = int(fd_stat.st_ino)
                reused = _find_matching_quarantine(
                    ready_dir_fd,
                    inode=int(fd_stat.st_ino),
                    artifact_id=artifact_id,
                )
                if reused is not None:
                    quarantine, generation = reused
                    locked_generation = generation
                else:
                    generation = uuid4().hex
                    locked_generation = generation
                    quarantine = quarantine_name_for(
                        inode=fd_stat.st_ino,
                        artifact_id=artifact_id,
                        generation=generation,
                    )
                    try:
                        os.link(
                            f"/proc/self/fd/{file_fd}",
                            quarantine,
                            dst_dir_fd=ready_dir_fd,
                        )
                    except FileExistsError:
                        try:
                            existing = os.stat(
                                quarantine, dir_fd=ready_dir_fd, follow_symlinks=False
                            )
                        except OSError:
                            return "unlink_failed"
                        if (existing.st_dev, existing.st_ino) != (
                            fd_stat.st_dev,
                            fd_stat.st_ino,
                        ):
                            return "inode_mismatch"
                    except OSError:
                        try:
                            # Re-verify name still matches before pathname link fallback.
                            name_stat = os.stat(
                                name, dir_fd=ready_dir_fd, follow_symlinks=False
                            )
                            if (name_stat.st_dev, name_stat.st_ino) != (
                                fd_stat.st_dev,
                                fd_stat.st_ino,
                            ):
                                return "inode_mismatch"
                            os.link(
                                name,
                                quarantine,
                                src_dir_fd=ready_dir_fd,
                                dst_dir_fd=ready_dir_fd,
                                follow_symlinks=False,
                            )
                        except FileExistsError:
                            try:
                                existing = os.stat(
                                    quarantine, dir_fd=ready_dir_fd, follow_symlinks=False
                                )
                            except OSError:
                                return "unlink_failed"
                            if (existing.st_dev, existing.st_ino) != (
                                fd_stat.st_dev,
                                fd_stat.st_ino,
                            ):
                                return "inode_mismatch"
                        except OSError:
                            return "unlink_failed"

                try:
                    q_stat = os.stat(quarantine, dir_fd=ready_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return "inode_mismatch"
                except OSError:
                    return "unlink_failed"
                if (q_stat.st_dev, q_stat.st_ino) != (fd_stat.st_dev, fd_stat.st_ino):
                    # Never unlink an unproven quarantine directory entry.
                    return "inode_mismatch"
                if not stat.S_ISREG(q_stat.st_mode):
                    return "not_regular_file"

                if on_intent is not None:
                    try:
                        on_intent(locked_dev, locked_ino, generation)
                        intent_written = True
                    except Exception:
                        return "intent_failed"

                if not recheck():
                    _clear_intent_best_effort()
                    return "ineligible"

                # nlink gate: quarantine + ready must both still link our inode.
                live = os.fstat(file_fd)
                if live.st_nlink < 2:
                    return _abort_replaced()

                post_name_stat: os.stat_result | None
                try:
                    post_name_stat = os.stat(name, dir_fd=ready_dir_fd, follow_symlinks=False)
                except FileNotFoundError:
                    post_name_stat = None
                except OSError:
                    return "unlink_failed"

                if post_name_stat is None:
                    # Ready name already absent; require quarantine-only nlink.
                    if os.fstat(file_fd).st_nlink != 1:
                        keep_quarantine_on_abort = True
                        return "unlink_failed"
                elif (post_name_stat.st_dev, post_name_stat.st_ino) != (
                    fd_stat.st_dev,
                    fd_stat.st_ino,
                ):
                    return _abort_replaced()
                else:
                    detach_outcome, owned_detach = try_detach_ready_directory_entry(
                        ready_dir_fd=ready_dir_fd,
                        file_fd=file_fd,
                        ready_name=name,
                        fd_stat=fd_stat,
                        artifact_id=artifact_id,
                        generation=generation,
                    )
                    if detach_outcome == "replaced":
                        return _abort_replaced()
                    if detach_outcome != "ok":
                        keep_quarantine_on_abort = True
                        return "unlink_failed"

                if not recheck():
                    # Detached but no longer eligible: keep quarantine+intent for recovery.
                    keep_quarantine_on_abort = True
                    return "ineligible"

                if on_deleted is not None:
                    try:
                        assert (
                            locked_dev is not None
                            and locked_ino is not None
                            and locked_generation is not None
                        )
                        on_deleted(locked_dev, locked_ino, locked_generation)
                        intent_written = False  # stamp clears intent
                    except Exception:
                        keep_quarantine_on_abort = True
                        return "stamp_failed"

                reclaim_names = [quarantine]
                if owned_detach is not None:
                    reclaim_names.append(owned_detach)
                if not destroy_owned_bytes_and_reclaim_names(
                    ready_dir_fd,
                    file_fd,
                    fd_stat,
                    reclaim_names,
                ):
                    keep_quarantine_on_abort = True
                    return "unlink_failed"
                owned_detach = None
                if on_clear_receipt is not None:
                    try:
                        assert (
                            locked_dev is not None
                            and locked_ino is not None
                            and locked_generation is not None
                        )
                        on_clear_receipt(locked_dev, locked_ino, locked_generation)
                    except Exception:
                        pass
                return "deleted"
            finally:
                _cleanup_owned_sidecars_under_lock()
        finally:
            try:
                fcntl.flock(file_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(file_fd)
        os.close(ready_dir_fd)


def try_unlink_ready_artifact_with_recheck(
    ready_path: Path,
    *,
    recheck: Callable[[], bool],
    layout: DurableLayout | None = None,
    repository_id: UUID | None = None,
    artifact_id: UUID | None = None,
    on_deleted: Callable[[int, int, str], None] | None = None,
    on_intent: Callable[[int, int, str], None] | None = None,
    on_clear_intent: Callable[[int, int, str], None] | None = None,
    on_clear_receipt: Callable[[int, int, str], None] | None = None,
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
            on_intent=on_intent,
            on_clear_intent=on_clear_intent,
            on_clear_receipt=on_clear_receipt,
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
                    on_deleted(int(fd_stat.st_dev), int(fd_stat.st_ino), uuid4().hex)
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
