"""Repository-scoped identity and port for cached Snapshot Table Parquet rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef

PARQUET_MEDIA_TYPE = "application/vnd.apache.parquet"
PARQUET_WRITER_CONTRACT_VERSION = 1
SNAPSHOT_EXPORT_CACHE_TTL_SECONDS = 86_400


@dataclass(frozen=True, slots=True)
class SnapshotTableArtifactCacheKey:
    row_layout_digest: DigestRef
    repository_id: str
    parquet_writer_contract_version: int = PARQUET_WRITER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.row_layout_digest) is not DigestRef:
            raise ValueError("row_layout_digest must be DigestRef")
        if type(self.repository_id) is not str or self.repository_id == "":
            raise ValueError("repository_id must be a non-empty string")
        if (
            self.repository_id.startswith("/")
            or "\\" in self.repository_id
            or "\x00" in self.repository_id
        ):
            raise ValueError("repository_id must not be a path-shaped identity")
        if (
            type(self.parquet_writer_contract_version) is not int
            or self.parquet_writer_contract_version < 1
        ):
            raise ValueError("parquet_writer_contract_version must be a positive int")


class SnapshotTableExportCachePort(Protocol):
    def lookup_many(
        self,
        keys: tuple[SnapshotTableArtifactCacheKey, ...],
    ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
        """Return unexpired row-file refs for exact repository/layout/writer keys."""

    def store_many(
        self,
        entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...],
    ) -> None:
        """Register row-file refs and extend their bounded cache protection."""

    def discard_many(self, keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> None:
        """Remove stale cache entries and release their cache protection."""
