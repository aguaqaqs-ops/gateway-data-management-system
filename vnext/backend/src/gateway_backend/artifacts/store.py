"""ArtifactStore port and a hermetic in-memory contract implementation."""

from __future__ import annotations

from typing import Protocol

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.serialize import (
    artifact_manifest_to_dict,
    build_manifest,
)
from gateway_backend.artifacts.types import (
    AccessMetadata,
    ArtifactContentManifest,
    ArtifactManifest,
    ArtifactRef,
    RetentionClass,
)
from gateway_backend.artifacts.validate import validate_artifact_manifest


class ArtifactStorePort(Protocol):
    def put(self, raw_bytes: bytes, manifest: ArtifactManifest) -> ArtifactRef:
        """Persist bytes and return the location-independent envelope."""

    def locate(self, ref: ArtifactRef) -> bytes:
        """Load bytes only when the supplied exact ref matches stored identity."""

    def verify_manifest(self, manifest: ArtifactManifest) -> None:
        """Validate generic envelope/content binding."""


class ManifestVerificationError(ValueError):
    """Artifact manifest or ref failed verification."""


class InMemoryArtifactStore:
    """Hermetic contract store; no provider/root enters artifact identity."""

    def __init__(self) -> None:
        self._artifacts: dict[str, tuple[ArtifactRef, bytes]] = {}

    def put(self, raw_bytes: bytes, manifest: ArtifactManifest) -> ArtifactRef:
        self.verify_manifest(manifest)
        if manifest.size_bytes != len(raw_bytes):
            raise ManifestVerificationError("size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != manifest.raw_sha256.value:
            raise ManifestVerificationError("raw_sha256 mismatch")
        ref = manifest.to_envelope()
        existing = self._artifacts.get(ref.logical_ref)
        if existing is not None and existing[0] != ref:
            raise ManifestVerificationError("logical_ref already identifies a different artifact")
        self._artifacts[ref.logical_ref] = (ref, raw_bytes)
        return ref

    def locate(self, ref: ArtifactRef) -> bytes:
        try:
            stored_ref, raw_bytes = self._artifacts[ref.logical_ref]
        except KeyError as exc:
            raise ManifestVerificationError(f"unknown logical_ref: {ref.logical_ref}") from exc
        if stored_ref != ref:
            raise ManifestVerificationError("stored artifact identity mismatch")
        if len(raw_bytes) != ref.size_bytes:
            raise ManifestVerificationError("stored size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != ref.raw_sha256.value:
            raise ManifestVerificationError("stored raw_sha256 mismatch")
        return raw_bytes

    def verify_manifest(self, manifest: ArtifactManifest) -> None:
        validate_artifact_manifest(artifact_manifest_to_dict(manifest))
        _ = manifest.to_envelope()


def put_with_built_manifest(
    store: ArtifactStorePort,
    raw_bytes: bytes,
    *,
    logical_ref: str,
    content_manifest: ArtifactContentManifest,
    retention_class: RetentionClass,
    access_metadata: AccessMetadata = AccessMetadata(),
) -> ArtifactRef:
    manifest = build_manifest(
        logical_ref=logical_ref,
        raw_bytes=raw_bytes,
        content=content_manifest,
        retention_class=retention_class,
        access_metadata=access_metadata,
    )
    return store.put(raw_bytes, manifest)
