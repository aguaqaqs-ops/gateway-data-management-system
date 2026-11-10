"""Explicit Repository Service roots and local atomic publication pairs."""

from __future__ import annotations

import errno
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from gateway_repository_service.artifact_root import ArtifactRootError, assert_no_symlink_ancestors, open_dir_nofollow, same_mount
from gateway_repository_service.storage_roots import RepositoryRoots


LAYOUT_FORMAT_VERSION = 2
_REQUIRED_LAYOUT_COMPONENTS = frozenset({"control", "versioned", "staging_versioned",
    "staging_artifacts", "artifacts", "service-state", "provider"})


def repository_key(repository_id: UUID) -> str:
    """Return the only representation allowed in a repository filesystem path."""
    return repository_id.hex


class LayoutError(RuntimeError):
    """Raised when an explicit owned layout cannot be resolved."""


@dataclass(frozen=True)
class DurableLayout:
    roots: RepositoryRoots
    probe_namespaces: bool = False

    @property
    def repository_root(self) -> Path:
        return self.roots.repository

    @property
    def artifacts(self) -> Path:
        return self.roots.artifacts

    @property
    def metadata_root(self) -> Path:
        return self.roots.metadata

    @property
    def scratch_root(self) -> Path:
        return self.roots.scratch

    @property
    def control(self) -> Path:
        return self.metadata_root / "control"

    @property
    def versioned(self) -> Path:
        return self.repository_root / "versioned"

    @property
    def staging_versioned(self) -> Path:
        return self.repository_root / ".staging" / "versioned"

    @property
    def staging_artifacts(self) -> Path:
        return self.scratch_root / "import"

    @property
    def query_directory(self) -> Path:
        return self.scratch_root / "query"

    @property
    def service_state(self) -> Path:
        return self.metadata_root / "service-state"

    @property
    def provider(self) -> Path:
        return self.metadata_root / "provider"

    @property
    def provider_scratch(self) -> Path:
        return self.scratch_root / "provider"

    @property
    def layout_marker(self) -> Path:
        return self.control / "layout.json"

    @property
    def service_lock(self) -> Path:
        return self.control / "service.lock"

    def components(self) -> tuple[tuple[Path, Path], ...]:
        return ((self.control, self.metadata_root), (self.versioned, self.repository_root),
            (self.staging_versioned, self.repository_root),
            (self.staging_artifacts, self.scratch_root), (self.query_directory, self.scratch_root),
            (self.service_state, self.metadata_root), (self.provider, self.metadata_root),
            (self.provider_scratch, self.scratch_root))

    @classmethod
    def bind_existing(cls, roots: RepositoryRoots) -> DurableLayout:
        """Bind the complete stopped-service set without creating missing members."""
        layout = cls(roots)
        layout.validate_components()
        try:
            metadata = layout.layout_marker.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise LayoutError("control layout marker is not a regular file")
            loaded = json.loads(layout.layout_marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LayoutError("control layout marker is unreadable") from exc
        if (not isinstance(loaded, dict)
                or loaded.get("layout_format_version") != LAYOUT_FORMAT_VERSION
                or not isinstance(loaded.get("components"), list)
                or not all(isinstance(item, str) for item in loaded["components"])
                or set(loaded["components"]) != _REQUIRED_LAYOUT_COMPONENTS):
            raise LayoutError("control layout marker is invalid or unsupported")
        return layout

    @classmethod
    def create_service(cls, roots: RepositoryRoots) -> DurableLayout:
        return cls._create(roots, probe_namespaces=False)

    @classmethod
    def create_for_probe(cls, roots: RepositoryRoots | Path) -> DurableLayout:
        """Use explicit sibling roots for an isolated historical host probe."""
        if isinstance(roots, Path):
            roots = RepositoryRoots.under(roots)
        return cls._create(roots, probe_namespaces=True)

    @classmethod
    def _create(cls, roots: RepositoryRoots, *, probe_namespaces: bool) -> DurableLayout:
        layout = cls(roots, probe_namespaces)
        for root in roots.paths():
            assert_no_symlink_ancestors(root)
            root.mkdir(parents=True, exist_ok=True)
        for directory, root in layout.components():
            assert_no_symlink_ancestors(directory)
            directory.mkdir(parents=True, exist_ok=True)
            _assert_owned_directory(directory, root)
        if layout.layout_marker.exists() or layout.layout_marker.is_symlink():
            cls.bind_existing(roots)
        else:
            layout.layout_marker.write_text(json.dumps({
                "layout_format_version": LAYOUT_FORMAT_VERSION,
                "components": sorted(_REQUIRED_LAYOUT_COMPONENTS)},
                sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            _fsync_file(layout.layout_marker)
            _fsync_directory(layout.control)
        layout.validate_components()
        return layout

    def validate_components(self) -> None:
        try:
            for root in self.roots.paths():
                assert_no_symlink_ancestors(root)
                if not root.is_dir():
                    raise LayoutError("configured RS root is unavailable")
            for directory, root in self.components():
                _assert_owned_directory(directory, root)
            self.assert_publication_devices(self.staging_versioned, self.versioned)
        except ArtifactRootError as exc:
            raise LayoutError("configured RS layout is unavailable or redirected") from exc

    def staging_repository(self, key: str, nonce: str) -> Path:
        _assert_owned_directory(self.staging_versioned, self.repository_root)
        path = self.staging_versioned / f"{key}.{nonce}"
        path.mkdir(parents=False, exist_ok=False)
        return path

    def published_repository(self, key: str) -> Path:
        return self.versioned / key

    def repository_artifact_directories(self, key: str) -> tuple[Path, Path]:
        if not key or "/" in key or key in {".", ".."} or "\x00" in key:
            raise LayoutError("invalid repository artifact key")

        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            artifacts_fd = os.open(self.artifacts, dir_flags)
        except OSError as exc:
            raise LayoutError("artifacts root is a symlink, non-directory, or unavailable") from exc
        try:
            try:
                os.mkdir(key, 0o750, dir_fd=artifacts_fd)
            except FileExistsError:
                pass
            except OSError as exc:
                raise LayoutError("repository artifact directory is unavailable") from exc
            try:
                base_fd = os.open(key, dir_flags, dir_fd=artifacts_fd)
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise LayoutError(
                        "repository artifact path is a symlink or non-directory"
                    ) from exc
                raise LayoutError("repository artifact directory is unavailable") from exc
            try:
                if not same_mount(artifacts_fd, base_fd):
                    raise LayoutError("repository artifact directory crosses root mount")
                for name in ("staging", "ready"):
                    try:
                        os.mkdir(name, 0o750, dir_fd=base_fd)
                    except FileExistsError:
                        pass
                    except OSError as exc:
                        raise LayoutError(f"{name} directory is unavailable") from exc
                    try:
                        child_fd = os.open(name, dir_flags, dir_fd=base_fd)
                    except OSError as exc:
                        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                            raise LayoutError(
                                f"{name} is a symlink or non-directory"
                            ) from exc
                        raise LayoutError(f"{name} directory is unavailable") from exc
                    try:
                        if not same_mount(base_fd, child_fd):
                            raise LayoutError(f"{name} crosses artifact root mount")
                    finally:
                        os.close(child_fd)
            finally:
                os.close(base_fd)
        finally:
            os.close(artifacts_fd)
        return self.artifacts / key / "staging", self.artifacts / key / "ready"

    def assert_publication_devices(self, staging: Path, target_parent: Path) -> None:
        if os.stat(staging).st_dev != os.stat(target_parent).st_dev:
            raise LayoutError("staging and publication target must share one filesystem")


def _assert_owned_directory(path: Path, root: Path) -> None:
    assert_no_symlink_ancestors(path)
    root_fd = open_dir_nofollow(root)
    descriptor = -1
    try:
        descriptor = open_dir_nofollow(path)
        if not path.is_relative_to(root) or not same_mount(root_fd, descriptor):
            raise LayoutError("layout component crosses its configured root mount")
    except OSError as exc:
        raise LayoutError("layout component is unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(root_fd)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
