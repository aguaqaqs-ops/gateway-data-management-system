from __future__ import annotations

from pathlib import Path


def resolve_benchmark_path(value: Path | str) -> Path:
    """Return an absolute benchmark path with user home expansion."""
    path = value if isinstance(value, Path) else Path(value)
    return path.expanduser().resolve()
