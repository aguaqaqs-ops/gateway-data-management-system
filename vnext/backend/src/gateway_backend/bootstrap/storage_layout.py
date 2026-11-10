"""Process composition translates the deployment adapter into infrastructure roots."""
from __future__ import annotations

from pathlib import Path

from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.deployment_config import StorageLayoutConfig
from gateway_backend.runtime_preflight import check_configured_root
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout


def artifact_layout_from_config(config: StorageLayoutConfig) -> ArtifactStoreLayout:
    return ArtifactStoreLayout(root_validator=lambda location: check_configured_root(config, "be-" + location.value), **{location.value: Path(config.roots[f'be-{location.value}'].path)
        for location in ArtifactLocation})


def maintenance_layout_from_config(config: StorageLayoutConfig) -> ArtifactStoreLayout:
    """Observe every configured slot; an unavailable root remains unusable."""
    return ArtifactStoreLayout.for_maintenance(root_validator=lambda location: check_configured_root(config, "be-" + location.value), **{location.value: Path(config.roots[f'be-{location.value}'].path)
        for location in ArtifactLocation})
