"""Versioned Repository Service DTOs.

This module contains only the small v1 wire-shaped data models.  It deliberately
does not implement HTTP routes, persistence, JCS, stream framing, or business
verification.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt, model_validator

from gateway_repository_contracts.errors import SimpleError
from gateway_repository_contracts.types import (
    BoundedOpaqueString,
    MainRefLiteral,
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


class VerificationPolicy(StrEnum):
    NONE = "NONE"
    STRUCTURAL = "STRUCTURAL"
    FULL_SCAN = "FULL_SCAN"


class UnknownTypePolicy(StrEnum):
    REJECT = "REJECT"
    STRINGIFY = "STRINGIFY"


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
    target_ref: MainRefLiteral
    expected_commit_id: BoundedOpaqueString
    verification_policy: VerificationPolicy = VerificationPolicy.STRUCTURAL
    unknown_type_policy: UnknownTypePolicy = UnknownTypePolicy.REJECT


class SubmitVersionedImportResponse(_VersionedModel):
    operation_id: UUID


class VersionedImportResult(_VersionedModel):
    commit_id: BoundedOpaqueString
    target_ref: MainRefLiteral
    artifact_id: UUID
    canonicalization_manifest_digest: BoundedOpaqueString
    expected_commit_id: BoundedOpaqueString
    completed_verification_policy: VerificationPolicy
    unknown_type_policy: UnknownTypePolicy


class VersionedOperation(_VersionedModel):
    operation_id: UUID
    status: OperationStatus
    result: VersionedImportResult | None = None
    error: SimpleError | None = None

    @model_validator(mode="after")
    def _validate_result_error_invariant(self) -> Self:
        if self.status in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
            if self.result is not None or self.error is not None:
                raise ValueError("QUEUED and RUNNING operations must not include result or error")
        elif self.status == OperationStatus.SUCCEEDED:
            if self.result is None or self.error is not None:
                raise ValueError("SUCCEEDED operations require result and must not include error")
        elif self.status == OperationStatus.FAILED:
            if self.result is not None or self.error is None:
                raise ValueError("FAILED operations require error and must not include result")
        return self


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
