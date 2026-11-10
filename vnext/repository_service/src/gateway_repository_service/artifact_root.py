"""Open artifacts-root without following symlinks or crossing mounts."""

from __future__ import annotations

import os
import stat
from pathlib import Path

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)


class ArtifactRootError(RuntimeError):
    """Raised when artifacts-root cannot be frozen fail-closed."""


def mnt_id_for_fd(fd: int) -> int:
    statx = getattr(os, "statx", None)
    statx_mnt = getattr(os, "STATX_MNT_ID", None)
    at_empty = getattr(os, "AT_EMPTY_PATH", 0)
    if statx is not None and statx_mnt is not None:
        try:
            result = statx(fd, statx_mnt, flags=at_empty)
            mnt_id = getattr(result, "mnt_id", None)
            if mnt_id is not None:
                return int(mnt_id)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    try:
        text = Path(f"/proc/self/fdinfo/{fd}").read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactRootError("mount id unavailable") from exc
    for line in text.splitlines():
        if line.startswith("mnt_id:"):
            return int(line.split()[1])
    raise ArtifactRootError("mount id unavailable")


def lstat_is_symlink(path: Path) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def assert_no_symlink_ancestors(path: Path) -> None:
    current = path
    seen: set[str] = set()
    while True:
        key = str(current)
        if key in seen:
            return
        seen.add(key)
        if lstat_is_symlink(current):
            raise ArtifactRootError(f"symlink in artifacts path: {current}")
        parent = current.parent
        if parent == current:
            return
        current = parent


def open_dir_nofollow(path: Path) -> int:
    if lstat_is_symlink(path):
        raise ArtifactRootError(f"refusing symlink directory: {path}")
    try:
        return os.open(path, _DIR_FLAGS)
    except OSError as exc:
        raise ArtifactRootError(f"cannot open directory without following: {path}") from exc


def same_mount(parent_fd: int, child_fd: int) -> bool:
    try:
        return mnt_id_for_fd(parent_fd) == mnt_id_for_fd(child_fd)
    except ArtifactRootError:
        return False


def open_owned_directory(
    root: Path, path: Path, *, create: bool = False, allow_missing: bool = False,
    mode: int = 0o750,
) -> int | None:
    """Walk from the configured root; validate each existing prefix before writes."""
    if not path.is_relative_to(root):
        raise ArtifactRootError("directory escapes its configured root")
    assert_no_symlink_ancestors(root)
    root_fd = open_dir_nofollow(root)
    current_fd = os.dup(root_fd)
    try:
        for name in path.relative_to(root).parts:
            try:
                child_fd = os.open(name, _DIR_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                if create:
                    try:
                        os.mkdir(name, mode, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    child_fd = os.open(name, _DIR_FLAGS, dir_fd=current_fd)
                elif allow_missing:
                    return None
                else:
                    raise
            if not same_mount(root_fd, child_fd):
                os.close(child_fd)
                raise ArtifactRootError("directory crosses its configured root mount")
            os.close(current_fd)
            current_fd = child_fd
        result, current_fd = current_fd, -1
        return result
    except OSError as exc:
        raise ArtifactRootError("owned directory is unavailable or redirected") from exc
    finally:
        if current_fd >= 0:
            os.close(current_fd)
        os.close(root_fd)
