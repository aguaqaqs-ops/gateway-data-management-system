"""Scoped canonical content identity, independent of physical export layout."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts.types import ArtifactRef

CANONICAL_IPC_MEDIA_TYPE = "application/vnd.apache.arrow.file"
CANONICAL_MAPPING_VERSION = 1
CANONICAL_TABLE_TTL_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class CanonicalTableKey:
    repository_id: str
    storage_projection_version: str
    business_schema_digest: DigestRef
    row_count: int
    table_digest: DigestRef
    canonical_mapping_version: int = CANONICAL_MAPPING_VERSION

    def __post_init__(self) -> None:
        if type(self.repository_id) is not str or not self.repository_id or len(self.repository_id) > 255:
            raise ValueError("repository_id must be a bounded scope identity")
        if type(self.storage_projection_version) is not str or not self.storage_projection_version:
            raise ValueError("storage projection version must be its owning string")
        if type(self.canonical_mapping_version) is not int or self.canonical_mapping_version < 1:
            raise ValueError("canonical mapping version must be a positive integer")
        if type(self.row_count) is not int or not 0 <= self.row_count <= 2**53 - 1:
            raise ValueError("row_count must be a non-negative I-JSON integer")
        if type(self.business_schema_digest) is not DigestRef or type(self.table_digest) is not DigestRef:
            raise ValueError("canonical digests must be DigestRef")

    @property
    def artifact_id(self) -> str:
        payload = canonicalize_json_value([
            self.repository_id, self.storage_projection_version,
            self.business_schema_digest.value, self.row_count,
            self.table_digest.value, self.canonical_mapping_version,
        ])
        return "canonical-table:" + hashlib.sha256(payload).hexdigest()


class CanonicalTableIndexPort(Protocol):
    def lookup(self, key: CanonicalTableKey) -> ArtifactRef | None: ...
    def register(self, key: CanonicalTableKey, ref: ArtifactRef) -> None: ...
    def bind_commit(self, *, repository_id: str, commit_id: str, refs: tuple[ArtifactRef, ...]) -> None: ...
