"""Private component-first filesystem layout for the durable repository root."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


LAYOUT_FORMAT_VERSION = 1


def repository_key(repository_id: UUID) -> str:
    """Return the only representation allowed in a repository filesystem path."""

    return repository_id.hex


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
    def create_service(cls, data_root: Path) -> "DurableLayout":
        """Activate the R2 service shell namespaces only."""

        return cls._create(data_root, probe_namespaces=False)

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
        self.artifacts.mkdir(parents=True, exist_ok=True)
        base = self.artifacts / key
        staging = base / "staging"
        ready = base / "ready"
        staging.mkdir(parents=True, exist_ok=True)
        ready.mkdir(parents=True, exist_ok=True)
        return staging, ready

    def assert_same_filesystem(self) -> None:
        paths = [self.control, self.versioned, self.service_state, self.provider]
        if self.probe_namespaces:
            paths.extend((self.staging, self.artifacts))
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
