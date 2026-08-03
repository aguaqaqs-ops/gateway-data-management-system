"""Typed launcher-provided storage provenance for target measurements."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from gateway_repository_service.filesystem import storage_root_identity


class StorageLayoutError(RuntimeError):
    """Raised when target storage provenance is absent or inconsistent."""


@dataclass(frozen=True)
class StorageLayout:
    storage_layout_version: str
    data_root: Path
    destination: Path
    mount_type: str
    read_write: bool
    volume_name: str
    volume_project: str
    storage_root_identity: str
    filesystem_type: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "StorageLayout":
        def text(name: str) -> str:
            item = value.get(name)
            if not isinstance(item, str) or not item:
                raise StorageLayoutError(f"storage layout field {name} is missing")
            return item

        data_root = Path(text("data_root"))
        destination = Path(text("destination"))
        if not data_root.is_absolute() or not destination.is_absolute():
            raise StorageLayoutError("storage layout paths must be absolute")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", text("storage_root_identity")):
            raise StorageLayoutError("storage root identity is invalid")
        read_write = value.get("read_write")
        if not isinstance(read_write, bool):
            raise StorageLayoutError("storage layout read_write is invalid")
        return cls(
            storage_layout_version=text("storage_layout_version"),
            data_root=data_root,
            destination=destination,
            mount_type=text("mount_type"),
            read_write=read_write,
            volume_name=text("volume_name"),
            volume_project=text("volume_project"),
            storage_root_identity=text("storage_root_identity"),
            filesystem_type=text("filesystem_type"),
        )

    @classmethod
    def load(cls, path: Path) -> "StorageLayout":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageLayoutError("storage layout manifest is unavailable") from exc
        if not isinstance(value, dict):
            raise StorageLayoutError("storage layout manifest is not an object")
        return cls.from_dict(value)

    def validate_root(self, root: Path, *, project: str | None = None) -> None:
        if self.storage_layout_version != "p2-r1-storage-layout-v1":
            raise StorageLayoutError("storage layout version is invalid")
        if root.resolve() != self.data_root.resolve() or self.destination != self.data_root:
            raise StorageLayoutError("storage layout data root does not match settings")
        if self.mount_type != "volume" or not self.read_write:
            raise StorageLayoutError("target storage mount is not a writable named volume")
        if project is None:
            raise StorageLayoutError("target Compose project identity is missing")
        if self.volume_project != project:
            raise StorageLayoutError("target storage volume belongs to another Compose project")
        if self.filesystem_type in {"", "unknown", "overlayfs"}:
            raise StorageLayoutError("target storage filesystem is unavailable or overlayfs")
        if storage_root_identity(root) != self.storage_root_identity:
            raise StorageLayoutError("target storage root identity does not match manifest")
