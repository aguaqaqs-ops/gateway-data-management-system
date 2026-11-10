"""Process composition translates the deployment adapter into infrastructure roots."""
from __future__ import annotations

from pathlib import Path

from gateway_backend.artifacts.location import ArtifactLocation
from gateway_backend.deployment_config import DeploymentConfig, StorageLayoutConfig
from gateway_backend.runtime_preflight import check_configured_root, check_write_capacity
from gateway_backend.infrastructure.artifact_store.layout import ArtifactStoreLayout
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.artifact_store.scratch import ScratchSpace


def artifact_layout_from_config(config: StorageLayoutConfig) -> ArtifactStoreLayout:
    for location in ArtifactLocation:
        check_configured_root(config, "be-" + location.value)
    return ArtifactStoreLayout(**{location.value: Path(config.roots[f'be-{location.value}'].path)
        for location in ArtifactLocation})


def maintenance_layout_from_config(config: StorageLayoutConfig) -> ArtifactStoreLayout:
    """Observe every configured slot; an unavailable root remains unusable."""
    return ArtifactStoreLayout.for_maintenance(root_validator=lambda location: check_configured_root(config, "be-" + location.value), **{location.value: Path(config.roots[f'be-{location.value}'].path)
        for location in ArtifactLocation})


def local_store_from_config(config: DeploymentConfig) -> LocalArtifactStore:
    return LocalArtifactStore(artifact_layout_from_config(config.storage),
        staging_max_bytes=config.resources.temporary.staging_max_bytes_per_object,
        capacity_check=lambda location, size: check_write_capacity(config.storage, {"be-" + location.value: size}))


def scratch_space_from_config(config: DeploymentConfig) -> ScratchSpace:
    return ScratchSpace(Path(config.storage.roots["be-scratch"].path),
        max_bytes=config.resources.temporary.scratch_max_bytes_per_attempt,
        capacity_check=lambda size: check_write_capacity(config.storage, {"be-scratch": size}))
