"""Fd-rooted, no-follow filesystem access for scenario closure."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from gateway_conformance.errors import ConformanceValidationError

_O_RDONLY = os.O_RDONLY
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_DIR_FLAGS = _O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY
_FILE_FLAGS = _O_RDONLY | _O_NOFOLLOW


def _posix_parts(relative: str) -> list[str]:
    parts = [part for part in Path(relative).as_posix().split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ConformanceValidationError("relative path must not contain parent segments")
    if not parts:
        raise ConformanceValidationError("relative path must not be empty")
    return parts


def _read_fd(fd: int, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65_536, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ConformanceValidationError("file exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _openat_relative(
    root_fd: int,
    relative: str,
    *,
    label: str,
    want_dir: bool,
) -> int:
    """Open relative path under root_fd; close intermediate fds; return leaf fd only."""
    parts = _posix_parts(relative)
    current_fd = root_fd
    try:
        for index, part in enumerate(parts):
            is_last = index == len(parts) - 1
            flags = _FILE_FLAGS if (is_last and not want_dir) else _DIR_FLAGS
            try:
                next_fd = os.open(part, flags, dir_fd=current_fd)
            except OSError as exc:
                raise ConformanceValidationError(f"{label} cannot be opened safely") from exc
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except Exception:
        if current_fd != root_fd:
            os.close(current_fd)
        raise


def _absolute_parts(path: Path) -> list[str]:
    absolute = path.expanduser()
    if not absolute.is_absolute():
        absolute = Path.cwd() / absolute
    parts = [part for part in absolute.as_posix().split("/") if part]
    if not parts:
        raise ConformanceValidationError("path must not be filesystem root")
    return parts


def _open_absolute_nofollow(path: Path, *, label: str) -> int:
    """Open an absolute directory via openat from '/', refusing any symlink component."""
    parts = _absolute_parts(path)
    try:
        current_fd = os.open("/", _DIR_FLAGS)
    except OSError as exc:
        raise ConformanceValidationError(f"{label} cannot open filesystem root") from exc
    for part in parts:
        try:
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=current_fd)
        except OSError as exc:
            os.close(current_fd)
            raise ConformanceValidationError(f"{label} cannot be opened safely") from exc
        os.close(current_fd)
        current_fd = next_fd
    return current_fd


class SecureRoot:
    """Root directory held open via component-wise O_NOFOLLOW openat from '/'."""

    def __init__(self, root: Path, *, label: str) -> None:
        self.label = label
        self.root = root.expanduser()
        self._fd = _open_absolute_nofollow(self.root, label=label)

    @classmethod
    def open_path(cls, root: Path, *, label: str) -> SecureRoot:
        return cls(root, label=label)

    def close(self) -> None:
        os.close(self._fd)

    def __enter__(self) -> SecureRoot:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def assert_path_unchanged(self) -> None:
        """Re-open path from '/' with O_NOFOLLOW; reject if inode changed or symlink."""
        probe = _open_absolute_nofollow(self.root, label=self.label)
        try:
            held = os.fstat(self._fd)
            other = os.fstat(probe)
            if (held.st_dev, held.st_ino) != (other.st_dev, other.st_ino):
                raise ConformanceValidationError(f"{self.label} path changed during validation")
        finally:
            os.close(probe)

    def read_regular_file(self, relative: str, *, label: str, max_bytes: int) -> bytes:
        fd = _openat_relative(self._fd, relative, label=label, want_dir=False)
        try:
            return _read_fd(fd, max_bytes=max_bytes)
        finally:
            os.close(fd)

    def iter_regular_files(self) -> Iterator[str]:
        """Yield POSIX relative paths for regular files under this root."""

        def walk(dir_fd: int, prefix: str) -> Iterator[str]:
            with os.scandir(dir_fd) as entries:
                for entry in entries:
                    name = entry.name
                    rel = f"{prefix}/{name}" if prefix else name
                    if entry.is_symlink():
                        raise ConformanceValidationError(
                            f"refusing symlink in scenario closure: {rel}"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        sub_fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
                        try:
                            yield from walk(sub_fd, rel)
                        finally:
                            os.close(sub_fd)
                    elif entry.is_file(follow_symlinks=False):
                        yield rel

        yield from walk(self._fd, "")

    def iter_top_level_names(self) -> list[str]:
        with os.scandir(self._fd) as entries:
            return sorted(entry.name for entry in entries)


def read_under_root(
    root: Path,
    relative: str,
    *,
    label: str,
    max_bytes: int,
) -> bytes:
    with SecureRoot.open_path(root, label=label) as secure:
        return secure.read_regular_file(relative, label=label, max_bytes=max_bytes)


def enumerate_regular_files(root: Path, *, label: str) -> list[str]:
    with SecureRoot.open_path(root, label=label) as secure:
        return sorted(secure.iter_regular_files())
