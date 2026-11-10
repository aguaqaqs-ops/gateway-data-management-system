"""Explicit RS-owned locations; no shared-ancestor runtime layout."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gateway_repository_service.deployment_config import StorageLayoutConfig


@dataclass(frozen=True, slots=True)
class RepositoryRoots:
    repository: Path
    artifacts: Path
    metadata: Path
    scratch: Path

    def __post_init__(self) -> None:
        paths = self.paths()
        for index, path in enumerate(paths):
            if not path.is_absolute() or path == Path("/") or ".." in path.parts:
                raise ValueError("RS roots must be absolute and non-root")
            for other in paths[index + 1:]:
                if path == other or path in other.parents or other in path.parents:
                    raise ValueError("RS roots must be distinct and non-nested")

    def paths(self) -> tuple[Path, ...]:
        return self.repository, self.artifacts, self.metadata, self.scratch

    @classmethod
    def under(cls, base: Path) -> RepositoryRoots:
        """Explicit isolated locations for host probes and test fixtures."""
        base = base.absolute()
        return cls(*(base / name for name in ("repository", "artifacts", "metadata", "scratch")))

    @classmethod
    def from_config(cls, config: StorageLayoutConfig) -> RepositoryRoots:
        return cls(*(Path(config.roots[f"rs-{name}"].path)
                     for name in ("repository", "artifacts", "metadata", "scratch")))
