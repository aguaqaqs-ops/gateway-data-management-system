"""Helpers for files mounted as container inputs in backend tests."""

from __future__ import annotations

from pathlib import Path


def write_container_readable_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Write a container input with read permission independent of umask."""

    path.write_text(content, encoding=encoding)
    path.chmod(0o644)
    return path
