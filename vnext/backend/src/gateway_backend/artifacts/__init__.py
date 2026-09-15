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
from gateway_backend.artifacts.nominal_refs import (
    NominalArtifactRefError,
    assert_backend_ref_not_repository_ref,
    assert_repository_ref_not_backend_ref,
    backend_artifact_ref_from_store_ref,
    repository_artifact_ref_from_upload_response,
    store_ref_from_backend_artifact_ref,
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
    "NominalArtifactRefError",
    "VerifyReadableResult",
    "assert_backend_ref_not_repository_ref",
    "assert_repository_ref_not_backend_ref",
    "artifact_ref_from_dict",
    "artifact_ref_from_json",
    "artifact_ref_to_dict",
    "artifact_ref_to_json",
    "backend_artifact_ref_from_store_ref",
    "assert_no_host_path_identity",
    "build_artifact_id",
    "put_with_built_ref",
    "raw_sha256_from_bytes",
    "repository_artifact_ref_from_upload_response",
    "store_ref_from_backend_artifact_ref",
    "validate_artifact_id",
    "validate_artifact_ref",
]
