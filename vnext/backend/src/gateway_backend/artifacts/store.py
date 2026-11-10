"""ArtifactStore port and hermetic minimal-ref implementations."""

from __future__ import annotations

from collections.abc import Iterator, Callable
from contextlib import contextmanager
from typing import ContextManager, Protocol

import pyarrow as pa

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts.types import ArtifactRef, validate_artifact_id
from gateway_backend.artifacts.validate import validate_artifact_ref_model


class ArtifactStorePort(Protocol):
    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        """Persist bytes and return the exact minimal ref."""

    def locate(self, ref: ArtifactRef) -> bytes:
        """Load bytes only when the supplied exact ref matches stored identity."""


class ArtifactRefLookupPort(Protocol):
    def get_ref(self, artifact_id: str) -> ArtifactRef:
        """Resolve the stored minimal ref for one opaque artifact id."""


class ArtifactBufferStorePort(ArtifactStorePort, Protocol):
    def open_buffer(self, ref: ArtifactRef, *, checkpoint: Callable[[], None] | None = None) -> ContextManager[pa.Buffer]:
        """Borrow verified immutable bytes; the provider owns their lifetime."""


class ManifestVerificationError(ValueError):
    """Artifact ref or raw bytes failed verification."""


class ArtifactUnavailableError(ManifestVerificationError):
    """An exact stored artifact is missing or cannot be read."""


class ArtifactStreamingStorePort(ArtifactRefLookupPort, Protocol):
    def read_exact(self, ref: ArtifactRef) -> Iterator[bytes]:
        """Read one safe ordinary file in bounded chunks, verifying exact identity."""

    def read_session(self) -> ContextManager[None]:
        """Keep cooperative cleanup out until the caller closes its read session."""


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

    def get_ref(self, artifact_id: str) -> ArtifactRef:
        validate_artifact_id(artifact_id)
        try:
            return self._artifacts[artifact_id][0]
        except KeyError as exc:
            raise ManifestVerificationError(f"unknown artifact_id: {artifact_id}") from exc

    @contextmanager
    def open_buffer(self, ref: ArtifactRef, *, checkpoint: Callable[[], None] | None = None) -> Iterator[pa.Buffer]:
        if checkpoint is not None:
            checkpoint()
        buffer = pa.py_buffer(self.locate(ref))
        if checkpoint is not None:
            checkpoint()
        yield buffer

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
