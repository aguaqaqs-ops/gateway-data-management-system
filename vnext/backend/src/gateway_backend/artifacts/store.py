"""ArtifactStore port and hermetic minimal-ref implementations."""

from __future__ import annotations

from typing import Protocol

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.validate import validate_artifact_ref_model


class ArtifactStorePort(Protocol):
    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        """Persist bytes and return the exact minimal ref."""

    def locate(self, ref: ArtifactRef) -> bytes:
        """Load bytes only when the supplied exact ref matches stored identity."""


class ManifestVerificationError(ValueError):
    """Artifact ref or raw bytes failed verification."""


class InMemoryArtifactStore:
    """Hermetic store; provider/root never enters artifact identity."""

    def __init__(self) -> None:
        self._artifacts: dict[str, tuple[ArtifactRef, bytes]] = {}

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        self._verify_put(raw_bytes, ref)
        existing = self._artifacts.get(ref.artifact_id)
        if existing is not None and existing[0] != ref:
            raise ManifestVerificationError("artifact_id already identifies a different artifact")
        self._artifacts[ref.artifact_id] = (ref, raw_bytes)
        return ref

    def locate(self, ref: ArtifactRef) -> bytes:
        try:
            stored_ref, raw_bytes = self._artifacts[ref.artifact_id]
        except KeyError as exc:
            raise ManifestVerificationError(f"unknown artifact_id: {ref.artifact_id}") from exc
        if stored_ref != ref:
            raise ManifestVerificationError("stored artifact identity mismatch")
        self._verify_raw(raw_bytes, ref)
        return raw_bytes

    def _verify_put(self, raw_bytes: bytes, ref: ArtifactRef) -> None:
        validate_artifact_ref_model(ref)
        self._verify_raw(raw_bytes, ref)

    @staticmethod
    def _verify_raw(raw_bytes: bytes, ref: ArtifactRef) -> None:
        if ref.size_bytes != len(raw_bytes):
            raise ManifestVerificationError("size_bytes mismatch")
        if raw_blob_digest(raw_bytes).value != ref.raw_sha256.value:
            raise ManifestVerificationError("raw_sha256 mismatch")


def put_with_built_ref(
    store: ArtifactStorePort,
    raw_bytes: bytes,
    *,
    artifact_id: str,
    media_type: str,
) -> ArtifactRef:
    ref = ArtifactRef(
        artifact_id=artifact_id,
        media_type=media_type,
        size_bytes=len(raw_bytes),
        raw_sha256=raw_blob_digest(raw_bytes),
    )
    return store.put(raw_bytes, ref)
