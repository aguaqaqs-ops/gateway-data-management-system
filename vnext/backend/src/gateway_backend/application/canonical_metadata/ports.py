"""Application port for resolving canonical provenance for one Repository commit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway_backend.capabilities.storage_projection import CanonicalizationManifest


class CommitCanonicalMetadataCode(StrEnum):
    MISSING = "COMMIT_CANONICAL_METADATA_MISSING"
    DIGEST_MISMATCH = "COMMIT_CANONICAL_METADATA_DIGEST_MISMATCH"


class CommitCanonicalMetadataError(RuntimeError):
    def __init__(self, code: CommitCanonicalMetadataCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostic = message


@dataclass(frozen=True, slots=True)
class CommitCanonicalScope:
    gateway_device_external_key: str
    business_project_id: str

    def __post_init__(self) -> None:
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class CommitCanonicalMetadata:
    repository_id: str
    commit_id: str
    scope: CommitCanonicalScope
    initial: bool
    manifest: CanonicalizationManifest | None = None

    def __post_init__(self) -> None:
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.commit_id) is not str or not self.commit_id:
            raise ValueError("commit_id must be a non-empty string")
        if type(self.scope) is not CommitCanonicalScope:
            raise ValueError("scope must be CommitCanonicalScope")
        if type(self.initial) is not bool:
            raise ValueError("initial must be bool")
        if self.initial:
            if self.manifest is not None:
                raise ValueError("INITIAL metadata must not have a manifest")
        elif type(self.manifest) is not CanonicalizationManifest:
            raise ValueError("Submission metadata requires a CanonicalizationManifest")


@runtime_checkable
class CommitCanonicalMetadataPort(Protocol):
    def resolve(
        self,
        *,
        repository_id: str,
        commit_id: str,
        scope: CommitCanonicalScope,
    ) -> CommitCanonicalMetadata:
        """Resolve manifest provenance or an INITIAL marker inside one frozen scope."""


class CommitCanonicalMetadataMetricsPort(Protocol):
    def increment_digest_mismatch(self) -> None:
        """Increment the bounded digest-mismatch counter."""


class CanonicalizationManifestReadPort(Protocol):
    def read_manifest(self, artifact_id: str) -> CanonicalizationManifest:
        """Read and decode one immutable manifest artifact by opaque artifact id."""


class ManifestArtifactUnavailable(RuntimeError):
    """Manifest artifact could not be resolved, verified, or decoded."""
