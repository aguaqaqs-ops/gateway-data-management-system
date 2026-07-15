from __future__ import annotations

from pathlib import PurePosixPath


def require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


def ensure_bundle_relative_path(value: str, field_name: str) -> None:
    require_non_empty(value, field_name)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be relative to the bundle root")
