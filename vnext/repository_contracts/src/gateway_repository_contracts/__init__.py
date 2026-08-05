"""Thin Versioned Repository Service DTOs."""

from gateway_repository_contracts.errors import SimpleError
from gateway_repository_contracts.headers import (
    DEFAULT_MAX_UPLOAD_BYTES,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    IdempotencyKeyString,
    UploadRequestHeaders,
    validate_upload_content_length,
)
from gateway_repository_contracts.versioned import (
    CreateRepositoryResponse,
    GetOperationResponse,
    GetVersionedCatalogResponse,
    OperationStatus,
    RepositoryArtifactRef,
    ResolveVersionedRefRequest,
    ResolveVersionedRefResponse,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
    StreamVersionedTableRowsRequest,
    UploadArtifactResponse,
    VersionedCatalog,
    VersionedColumn,
    VersionedImportResult,
    VersionedOperation,
    VersionedTable,
)

__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "REPOSITORY_IMPORT_MEDIA_TYPE",
    "CreateRepositoryResponse",
    "GetOperationResponse",
    "GetVersionedCatalogResponse",
    "IdempotencyKeyString",
    "OperationStatus",
    "RepositoryArtifactRef",
    "ResolveVersionedRefRequest",
    "ResolveVersionedRefResponse",
    "SimpleError",
    "SubmitVersionedImportRequest",
    "SubmitVersionedImportResponse",
    "StreamVersionedTableRowsRequest",
    "UploadArtifactResponse",
    "UploadRequestHeaders",
    "VersionedCatalog",
    "VersionedColumn",
    "VersionedImportResult",
    "VersionedOperation",
    "VersionedTable",
    "validate_upload_content_length",
]
