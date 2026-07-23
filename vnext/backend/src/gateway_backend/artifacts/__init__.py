"""Generic, location-independent artifact identity API."""

from gateway_backend.artifacts.contracts import (
    CANONICAL_ROW_HASHES_ARTIFACT,
    CONTENT_CONTRACT_SPECS,
    content_contract_from_spec,
    lookup_content_contract,
)
from gateway_backend.artifacts.digest import build_logical_ref, raw_sha256_from_bytes
from gateway_backend.artifacts.serialize import (
    artifact_manifest_from_dict,
    artifact_manifest_from_json,
    artifact_manifest_to_dict,
    artifact_manifest_to_json,
    artifact_ref_from_dict,
    artifact_ref_from_json,
    artifact_ref_to_dict,
    artifact_ref_to_json,
    build_manifest,
)
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    InMemoryArtifactStore,
    ManifestVerificationError,
    put_with_built_manifest,
)
from gateway_backend.artifacts.types import (
    AccessMetadata,
    ArtifactContentManifest,
    ArtifactManifest,
    ArtifactRef,
    ArtifactResolver,
    ContentContract,
    ContractBinding,
    LOGICAL_REF_PREFIX,
    RetentionClass,
    assert_no_host_path_identity,
)
from gateway_backend.artifacts.validate import validate_artifact_manifest, validate_artifact_ref

__all__ = [
    "CANONICAL_ROW_HASHES_ARTIFACT",
    "CONTENT_CONTRACT_SPECS",
    "LOGICAL_REF_PREFIX",
    "AccessMetadata",
    "ArtifactContentManifest",
    "ArtifactManifest",
    "ArtifactRef",
    "ArtifactResolver",
    "ArtifactStorePort",
    "ContentContract",
    "ContractBinding",
    "InMemoryArtifactStore",
    "ManifestVerificationError",
    "RetentionClass",
    "artifact_manifest_from_dict",
    "artifact_manifest_from_json",
    "artifact_manifest_to_dict",
    "artifact_manifest_to_json",
    "artifact_ref_from_dict",
    "artifact_ref_from_json",
    "artifact_ref_to_dict",
    "artifact_ref_to_json",
    "assert_no_host_path_identity",
    "build_logical_ref",
    "build_manifest",
    "content_contract_from_spec",
    "lookup_content_contract",
    "put_with_built_manifest",
    "raw_sha256_from_bytes",
    "validate_artifact_manifest",
    "validate_artifact_ref",
]
