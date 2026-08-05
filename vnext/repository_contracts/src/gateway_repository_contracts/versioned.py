"""Versioned Repository Service DTOs.

This module contains only the small v1 wire-shaped data models.  It deliberately
does not implement HTTP routes, persistence, JCS, stream framing, or business
verification.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt

from gateway_repository_contracts.errors import SimpleError
from gateway_repository_contracts.types import (
    BoundedOpaqueString,
    MediaTypeString,
    RefNameString,
    Sha256String,
    TableNameString,
)


class _VersionedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RepositoryArtifactRef(_VersionedModel):
    """Repository-owned artifact identity and raw transport integrity."""

    artifact_id: UUID
    media_type: MediaTypeString
    size_bytes: NonNegativeInt
    raw_sha256: Sha256String


class CreateRepositoryResponse(_VersionedModel):
    repository_id: UUID
    default_ref: RefNameString
    initial_commit_id: BoundedOpaqueString


class UploadArtifactResponse(_VersionedModel):
    artifact_ref: RepositoryArtifactRef


class SubmitVersionedImportRequest(_VersionedModel):
    repository_id: UUID
    artifact_ref: RepositoryArtifactRef
    target_ref: RefNameString
    expected_commit_id: BoundedOpaqueString
    idempotency_key: BoundedOpaqueString


class SubmitVersionedImportResponse(_VersionedModel):
    operation_id: UUID


class VersionedImportResult(_VersionedModel):
    commit_id: BoundedOpaqueString
    target_ref: RefNameString
    artifact_id: UUID
    canonicalization_manifest_digest: BoundedOpaqueString


class VersionedOperation(_VersionedModel):
    operation_id: UUID
    status: OperationStatus
    result: VersionedImportResult | None = None
    error: SimpleError | None = None


class GetOperationResponse(_VersionedModel):
    operation: VersionedOperation


class ResolveVersionedRefRequest(_VersionedModel):
    repository_id: UUID
    ref_name: RefNameString


class ResolveVersionedRefResponse(_VersionedModel):
    ref_name: RefNameString
    commit_id: BoundedOpaqueString


class VersionedColumn(_VersionedModel):
    name: TableNameString
    sql_type: BoundedOpaqueString
    nullable: bool


class VersionedTable(_VersionedModel):
    name: TableNameString
    columns: tuple[VersionedColumn, ...]
    primary_key: tuple[TableNameString, ...]
    row_count: NonNegativeInt


class VersionedCatalog(_VersionedModel):
    commit_id: BoundedOpaqueString
    tables: tuple[VersionedTable, ...]


class GetVersionedCatalogResponse(_VersionedModel):
    catalog: VersionedCatalog


class StreamVersionedTableRowsRequest(_VersionedModel):
    repository_id: UUID
    commit_id: BoundedOpaqueString
    table_name: TableNameString
