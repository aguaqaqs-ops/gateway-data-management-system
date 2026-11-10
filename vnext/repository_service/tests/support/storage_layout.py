"""Canonical deployment documents for isolated RS fixtures."""
from __future__ import annotations

import json
from pathlib import Path

from gateway_repository_service.deployment_config import SLOTS, StorageLayoutConfig
from gateway_repository_service.runtime_preflight import mounts, marker_document
from gateway_repository_service.storage_roots import RepositoryRoots


def write_storage_layout(roots: RepositoryRoots) -> Path:
    parent = roots.metadata.parent
    path = parent.parent / f"{parent.name}-storage-layout.json"
    paths = {"rs-repository": roots.repository, "rs-artifacts": roots.artifacts,
        "rs-metadata": roots.metadata, "rs-scratch": roots.scratch}
    for slot in SLOTS - paths.keys():
        paths[slot] = parent.parent / f"{parent.name}-unused-{slot}"
    observed = mounts()
    filesystems = {}
    filesystem_ids = {}
    for slot, root in paths.items():
        containing = max((item for item in observed if Path(item.target) == root or Path(item.target) in root.parents),
                         key=lambda item: len(item.target))
        key = "fs-" + str(containing.mount_id)
        filesystem_ids[slot] = key
        filesystems[key] = {"mountpoint": containing.target, "expected_source": containing.source,
                            "min_free_bytes": 1, "min_free_fraction": 0.000001}
    doc = {"schema_version": 1, "environment_id": "test", "group_id": "test",
        "filesystems": filesystems,
        "roots": {slot: {"source": str(root), "path": str(root), "filesystem_id": filesystem_ids[slot],
            "storage_id": f"{index + 1:032x}", "mount_mode": "bind"}
            for index, (slot, root) in enumerate(sorted(paths.items()))}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    config = StorageLayoutConfig.load(path)
    for slot, root in paths.items():
        if root.is_dir() and not root.is_symlink():
            (root / ".gateway-storage.json").write_text(json.dumps(marker_document(config, slot)))
    return path


def local_storage_layout(base: Path) -> Path:
    return write_storage_layout(RepositoryRoots.under(base))
