"""Minimal Backend artifact identity API."""

from gateway_backend.artifacts.bounded_store import (
    BoundedArtifactStorePort,
    CleanupClassification,
    CleanupDecision,
    DeleteDisposition,
    VerifyReadableResult,
)
from gateway_backend.artifacts.digest import build_artifact_id, raw_sha256_from_bytes
from gateway_backend.artifacts.serialize import (
    artifact_ref_from_dict,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
)
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    InMemoryArtifactStore,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.types import (
    ArtifactRef,
    assert_no_host_path_identity,
    validate_artifact_id,
)
from gateway_backend.artifacts.validate import validate_artifact_ref

__all__ = [
    "ArtifactRef",
    "ArtifactStorePort",
    "BoundedArtifactStorePort",
    "CleanupClassification",
    "CleanupDecision",
    "DeleteDisposition",
    "InMemoryArtifactStore",
    "ManifestVerificationError",
    "VerifyReadableResult",
    "artifact_ref_from_dict",
    "artifact_ref_from_json",
    "artifact_ref_to_dict",
    "artifact_ref_to_json",
    "assert_no_host_path_identity",
    "build_artifact_id",
    "put_with_built_ref",
    "raw_sha256_from_bytes",
    "validate_artifact_id",
    "validate_artifact_ref",
]
