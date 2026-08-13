"""Private component-first filesystem layout for the durable repository root."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


LAYOUT_FORMAT_VERSION = 1

_REQUIRED_LAYOUT_COMPONENTS: frozenset[str] = frozenset(
    {
        "control",
        "versioned",
        "staging",
        "artifacts",
        "service-state",
        "provider",
    }
)


def repository_key(repository_id: UUID) -> str:
    """Return the only representation allowed in a repository filesystem path."""

    return repository_id.hex


class LayoutError(RuntimeError):
    """Raised when an existing durable layout cannot be resolved."""


@dataclass(frozen=True)
class DurableLayout:
    root: Path
    control: Path
    versioned: Path
    staging: Path
    staging_versioned: Path
    staging_artifacts: Path
    artifacts: Path
    service_state: Path
    provider: Path
    probe_namespaces: bool = False

    @property
    def layout_marker(self) -> Path:
        return self.control / "layout.json"

    @property
    def service_lock(self) -> Path:
        return self.control / "service.lock"

    @classmethod
    def bind_existing(cls, data_root: Path) -> "DurableLayout":
        """Resolve paths for an already-initialized data root without mutating it."""

        root = data_root.expanduser().resolve()
        if not root.is_dir():
            raise LayoutError("data root does not exist")
        control = root / "control"
        versioned = root / "versioned"
        staging = root / "staging"
        staging_versioned = staging / "versioned"
        staging_artifacts = staging / "artifacts"
        artifacts = root / "artifacts"
        service_state = root / "service-state"
        provider = root / "provider"
        marker = control / "layout.json"
        if not control.is_dir() or not marker.is_file():
            raise LayoutError("control layout is not initialized")
        try:
            raw = marker.read_text(encoding="utf-8")
            loaded = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LayoutError("control layout marker is unreadable") from exc
        if not isinstance(loaded, dict):
            raise LayoutError("control layout marker is invalid")
        if loaded.get("layout_format_version") != LAYOUT_FORMAT_VERSION:
            raise LayoutError("unsupported layout_format_version")
        components = loaded.get("components")
        if not isinstance(components, list):
            raise LayoutError("control layout marker is invalid")
        present_components = {str(item) for item in components}
        missing_components = _REQUIRED_LAYOUT_COMPONENTS.difference(present_components)
        if missing_components:
            raise LayoutError("control layout marker is invalid")
        return cls(
            root=root,
            control=control,
            versioned=versioned,
            staging=staging,
            staging_versioned=staging_versioned,
            staging_artifacts=staging_artifacts,
            artifacts=artifacts,
            service_state=service_state,
            provider=provider,
            probe_namespaces=False,
        )

    @classmethod
    def create_service(cls, data_root: Path) -> "DurableLayout":
        """Activate the service shell and synchronous mutation staging namespaces."""

        layout = cls._create(data_root, probe_namespaces=False)
        for directory in (layout.staging_versioned, layout.staging_artifacts):
            directory.mkdir(parents=True, exist_ok=True)
        layout.assert_same_filesystem()
        return layout

    @classmethod
    def create_for_probe(cls, data_root: Path) -> "DurableLayout":
        """Activate service namespaces plus P2-R1 probe staging/artifact roots."""

        return cls._create(data_root, probe_namespaces=True)

    @classmethod
    def create(cls, data_root: Path) -> "DurableLayout":
        """Backward-compatible alias for probe roots used by P2-R1 workflows."""

        return cls.create_for_probe(data_root)

    @classmethod
    def _create(cls, data_root: Path, *, probe_namespaces: bool) -> "DurableLayout":
        root = data_root.expanduser().resolve()
        control = root / "control"
        versioned = root / "versioned"
        staging = root / "staging"
        staging_versioned = staging / "versioned"
        staging_artifacts = staging / "artifacts"
        artifacts = root / "artifacts"
        service_state = root / "service-state"
        provider = root / "provider"
        for directory in (control, versioned, service_state, provider):
            directory.mkdir(parents=True, exist_ok=True)
        if probe_namespaces:
            for directory in (staging_versioned, staging_artifacts, artifacts):
                directory.mkdir(parents=True, exist_ok=True)

        marker = control / "layout.json"
        if marker.exists():
            loaded = json.loads(marker.read_text(encoding="utf-8"))
            if loaded.get("layout_format_version") != LAYOUT_FORMAT_VERSION:
                raise RuntimeError("unsupported layout_format_version")
        else:
            marker.write_text(
                json.dumps(
                    {
                        "layout_format_version": LAYOUT_FORMAT_VERSION,
                        "components": [
                            "control",
                            "versioned",
                            "staging",
                            "artifacts",
                            "service-state",
                            "provider",
                        ],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            _fsync_file(marker)
            _fsync_directory(control)

        layout = cls(
            root=root,
            control=control,
            versioned=versioned,
            staging=staging,
            staging_versioned=staging_versioned,
            staging_artifacts=staging_artifacts,
            artifacts=artifacts,
            service_state=service_state,
            provider=provider,
            probe_namespaces=probe_namespaces,
        )
        layout.assert_same_filesystem()
        return layout

    def staging_repository(self, key: str, nonce: str) -> Path:
        self.staging_versioned.mkdir(parents=True, exist_ok=True)
        path = self.staging_versioned / f"{key}.{nonce}"
        path.mkdir(parents=False, exist_ok=False)
        return path

    def published_repository(self, key: str) -> Path:
        return self.versioned / key

    def repository_artifact_directories(self, key: str) -> tuple[Path, Path]:
        staging = self.artifacts / key / "staging"
        ready = self.artifacts / key / "ready"
        try:
            staging_st = staging.lstat()
            ready_st = ready.lstat()
        except OSError:
            staging_st = None
            ready_st = None
        if (
            staging_st is not None
            and ready_st is not None
            and stat.S_ISDIR(staging_st.st_mode)
            and stat.S_ISDIR(ready_st.st_mode)
        ):
            return staging, ready

        if not key or "/" in key or key in {".", ".."} or "\x00" in key:
            raise RuntimeError("invalid repository artifact key")

        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        artifacts_fd = os.open(self.artifacts, dir_flags)
        try:
            try:
                os.mkdir(key, 0o750, dir_fd=artifacts_fd)
            except FileExistsError:
                pass
            base_fd = os.open(key, dir_flags, dir_fd=artifacts_fd)
            try:
                for name in ("staging", "ready"):
                    try:
                        os.mkdir(name, 0o750, dir_fd=base_fd)
                    except FileExistsError:
                        pass
            finally:
                os.close(base_fd)
        finally:
            os.close(artifacts_fd)
        return self.artifacts / key / "staging", self.artifacts / key / "ready"

    def assert_same_filesystem(self) -> None:
        paths = [self.control, self.versioned, self.service_state, self.provider]
        if self.probe_namespaces:
            paths.extend((self.staging, self.artifacts))
        elif self.staging_versioned.exists() or self.staging_artifacts.exists():
            paths.append(self.staging)
        devices = {os.stat(path).st_dev for path in paths if path.exists()}
        if len(devices) != 1:
            raise RuntimeError("publication components must share one filesystem")

    def assert_publication_devices(self, staging: Path, target_parent: Path) -> None:
        self.assert_same_filesystem()
        if os.stat(staging).st_dev != os.stat(target_parent).st_dev:
            raise RuntimeError("staging and publication target must share one filesystem")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
