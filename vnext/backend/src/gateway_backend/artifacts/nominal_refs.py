"""Nominal Backend and Repository artifact ref conversions."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import BackendArtifactRef, RepositoryArtifactRef


class NominalArtifactRefError(ValueError):
    """Raised when a nominal artifact ref conversion is invalid."""


def backend_artifact_ref_from_store_ref(ref: ArtifactRef) -> BackendArtifactRef:
    if type(ref) is not ArtifactRef:
        raise NominalArtifactRefError("ref must be ArtifactRef")
    return BackendArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )


def store_ref_from_backend_artifact_ref(ref: BackendArtifactRef) -> ArtifactRef:
    if type(ref) is not BackendArtifactRef:
        raise NominalArtifactRefError("ref must be BackendArtifactRef")
    return ArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=DigestRef(ref.raw_sha256),
    )


def repository_artifact_ref_from_upload_response(
    *,
    artifact_id: str,
    media_type: str,
    size_bytes: int,
    raw_sha256: str,
) -> RepositoryArtifactRef:
    return RepositoryArtifactRef(
        artifact_id=artifact_id,
        media_type=media_type,
        size_bytes=size_bytes,
        raw_sha256=raw_sha256,
    )


def assert_backend_ref_not_repository_ref(ref: object) -> None:
    if type(ref) is RepositoryArtifactRef:
        raise NominalArtifactRefError("RepositoryArtifactRef cannot substitute BackendArtifactRef")


def assert_repository_ref_not_backend_ref(ref: object) -> None:
    if type(ref) is BackendArtifactRef:
        raise NominalArtifactRefError("BackendArtifactRef cannot substitute RepositoryArtifactRef")
