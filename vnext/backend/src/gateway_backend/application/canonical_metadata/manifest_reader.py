"""Artifact-backed canonicalization manifest reader used by commit metadata resolution."""

from __future__ import annotations

from gateway_backend.artifacts import (
    ArtifactRefLookupPort,
    ArtifactStorePort,
    ManifestVerificationError,
)
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    CanonicalizationManifest,
    PublicationError,
    open_canonicalization_manifest,
)

from gateway_backend.application.canonical_metadata.ports import ManifestArtifactUnavailable


class ArtifactBackedCanonicalizationManifestReader:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStorePort,
        artifact_refs: ArtifactRefLookupPort,
    ) -> None:
        self._artifact_store = artifact_store
        self._artifact_refs = artifact_refs

    def read_manifest(self, artifact_id: str) -> CanonicalizationManifest:
        try:
            ref = self._artifact_refs.get_ref(artifact_id)
            if ref.media_type != CANONICALIZATION_MANIFEST_MEDIA_TYPE:
                raise ManifestArtifactUnavailable("artifact is not a canonicalization manifest")
            return open_canonicalization_manifest(self._artifact_store, ref)
        except ManifestArtifactUnavailable:
            raise
        except (ManifestVerificationError, OSError, ValueError, PublicationError):
            raise ManifestArtifactUnavailable("canonicalization manifest is unavailable") from None


__all__ = ["ArtifactBackedCanonicalizationManifestReader"]
