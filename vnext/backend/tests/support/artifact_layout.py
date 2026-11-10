"""Explicit test deployments. Creation belongs to fixtures, never to the store."""
from __future__ import annotations

import json
from pathlib import Path

from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore


def make_artifact_layout(base: Path) -> ArtifactStoreLayout:
    roots = {location.value: base / location.value for location in ArtifactLocation}
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    return ArtifactStoreLayout(**roots)


def open_test_store(base: Path) -> LocalArtifactStore:
    return LocalArtifactStore(make_artifact_layout(base), staging_max_bytes=4 * 1024**3)


def write_deployment_files(base: Path, *, prepare: bool = True) -> tuple[Path, Path]:
    fixtures = Path(__file__).resolve().parents[3] / 'fixtures/runtime-config/v1'
    storage = json.loads((fixtures / 'storage-layout.json').read_bytes())
    resources = json.loads((fixtures / 'resource-profile.json').read_bytes())
    for slot, root in storage['roots'].items():
        path = base / (slot.removeprefix('be-') if slot.startswith('be-') else slot)
        root['path'] = root['source'] = str(path)
        if prepare:
            path.mkdir(parents=True, exist_ok=True)
    from gateway_backend.runtime_preflight import mounts, marker_document
    from gateway_backend.deployment_config import StorageLayoutConfig
    containing = max((item for item in mounts() if Path(item.target) == base or Path(item.target) in base.parents),
                     key=lambda item: len(item.target))
    storage['filesystems']['local'].update(mountpoint=containing.target, expected_source=containing.source,
        min_free_bytes=1, min_free_fraction=0.000001)
    base.parent.mkdir(parents=True, exist_ok=True)
    storage_path = base.parent / (base.name + '-storage-layout.json')
    resource_path = base.parent / (base.name + '-resource-profile.json')
    storage_path.write_text(json.dumps(storage))
    resource_path.write_text(json.dumps(resources))
    if prepare:
        parsed = StorageLayoutConfig.load(storage_path)
        for slot, root in parsed.roots.items():
            (Path(root.path) / '.gateway-storage.json').write_text(json.dumps(marker_document(parsed, slot)))
    return storage_path, resource_path
