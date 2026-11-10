"""Process composition translates the deployment adapter into infrastructure roots."""
from __future__ import annotations

from pathlib import Path

from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.deployment_config import StorageLayoutConfig
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout


def artifact_layout_from_config(config: StorageLayoutConfig) -> ArtifactStoreLayout:
    return ArtifactStoreLayout(**{location.value: Path(config.roots[f'be-{location.value}'].path)
        for location in ArtifactLocation})
