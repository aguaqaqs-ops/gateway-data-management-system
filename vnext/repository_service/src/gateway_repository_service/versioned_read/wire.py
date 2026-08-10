"""Wire mapping between private read models and public contracts."""

from __future__ import annotations

from collections.abc import Iterator
from typing import NoReturn

import pyarrow as pa  # type: ignore[import-untyped]
from pydantic import ValidationError

from gateway_repository_contracts import (
    COMMIT_NOT_FOUND_CODE,
    GetVersionedCatalogResponse,
    REF_NOT_FOUND_CODE,
    REPOSITORY_NOT_FOUND_CODE,
    REQUEST_VALIDATION_FAILED_CODE,
    ResolveVersionedRefResponse,
    SERVICE_NOT_READY_CODE,
    TABLE_NOT_FOUND_CODE,
    UNKNOWN_SQL_TYPE_CODE,
    VersionedCatalog,
    VersionedColumn,
    VersionedTable,
)
from gateway_repository_service.arrow_mapping import TableCatalog, UnknownSqlTypeError
from gateway_repository_service.http.errors import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    ServiceError,
    sanitize_validation_errors,
)
from gateway_repository_service.versioned_read.errors import (
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    ReadStreamCancelledError,
    RepositoryNotVisibleError,
    TableNotFoundError,
    VersionedReadError,
)

_SERVICE_NOT_READY_MESSAGE = "service is not ready"
_REPOSITORY_NOT_FOUND_MESSAGE = "repository was not found"
_REF_NOT_FOUND_MESSAGE = "versioned ref was not found"
_COMMIT_NOT_FOUND_MESSAGE = "versioned commit was not found"
_TABLE_NOT_FOUND_MESSAGE = "versioned table was not found"
_UNKNOWN_SQL_TYPE_MESSAGE = "catalog contains an unknown SQL type"
_REQUEST_VALIDATION_MESSAGE = "request validation failed"


def build_resolve_response(commit_id: str) -> ResolveVersionedRefResponse:
    try:
        return ResolveVersionedRefResponse(ref_name="main", commit_id=commit_id)
    except ValidationError as exc:
        raise _catalog_wire_unavailable(exc) from exc


def build_catalog_response(commit_id: str, tables: tuple[TableCatalog, ...]) -> GetVersionedCatalogResponse:
    try:
        return GetVersionedCatalogResponse(
            catalog=VersionedCatalog(
                commit_id=commit_id,
                tables=tuple(_table_catalog_to_wire(table) for table in tables),
            )
        )
    except ValidationError as exc:
        raise _catalog_wire_unavailable(exc) from exc


def _table_catalog_to_wire(table: TableCatalog) -> VersionedTable:
    return VersionedTable(
        name=table.name,
        columns=tuple(
            VersionedColumn(
                name=column.name,
                sql_type=column.sql_type,
                nullable=column.nullable,
            )
            for column in table.columns
        ),
        primary_key=table.primary_key,
        row_count=table.row_count,
    )


def map_read_error(exc: BaseException) -> ServiceError:
    if isinstance(exc, ServiceError):
        return exc
    if isinstance(exc, RepositoryNotVisibleError):
        return ServiceError(
            code=REPOSITORY_NOT_FOUND_CODE,
            message=_REPOSITORY_NOT_FOUND_MESSAGE,
            status_code=404,
        )
    if isinstance(exc, MainRefNotFoundError):
        return ServiceError(
            code=REF_NOT_FOUND_CODE,
            message=_REF_NOT_FOUND_MESSAGE,
            status_code=404,
        )
    if isinstance(exc, CommitNotFoundError):
        return ServiceError(
            code=COMMIT_NOT_FOUND_CODE,
            message=_COMMIT_NOT_FOUND_MESSAGE,
            status_code=404,
        )
    if isinstance(exc, TableNotFoundError):
        return ServiceError(
            code=TABLE_NOT_FOUND_CODE,
            message=_TABLE_NOT_FOUND_MESSAGE,
            status_code=404,
        )
    if isinstance(exc, UnknownSqlTypeError):
        return ServiceError(
            code=UNKNOWN_SQL_TYPE_CODE,
            message=_UNKNOWN_SQL_TYPE_MESSAGE,
            status_code=422,
        )
    if isinstance(exc, ProviderUnavailableError):
        return ServiceError(
            code=SERVICE_NOT_READY_CODE,
            message=_SERVICE_NOT_READY_MESSAGE,
            status_code=503,
        )
    if isinstance(exc, ValidationError):
        return request_validation_failed(exc)
    if isinstance(exc, ReadStreamCancelledError):
        return ServiceError(
            code=INTERNAL_ERROR_CODE,
            message=INTERNAL_ERROR_MESSAGE,
            status_code=500,
        )
    if isinstance(exc, VersionedReadError):
        return ServiceError(
            code=INTERNAL_ERROR_CODE,
            message=INTERNAL_ERROR_MESSAGE,
            status_code=500,
        )
    return ServiceError(
        code=INTERNAL_ERROR_CODE,
        message=INTERNAL_ERROR_MESSAGE,
        status_code=500,
    )


def request_validation_failed(exc: ValidationError) -> ServiceError:
    return ServiceError(
        code=REQUEST_VALIDATION_FAILED_CODE,
        message=_REQUEST_VALIDATION_MESSAGE,
        status_code=422,
        details={"errors": sanitize_validation_errors(exc.errors())},
    )


def _catalog_wire_unavailable(exc: ValidationError) -> ServiceError:
    del exc
    return ServiceError(
        code=SERVICE_NOT_READY_CODE,
        message=_SERVICE_NOT_READY_MESSAGE,
        status_code=503,
    )


def close_row_iterator(iterator: Iterator[pa.RecordBatch]) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()
        return
    throw = getattr(iterator, "throw", None)
    if callable(throw):
        try:
            throw(GeneratorExit())
        except GeneratorExit:
            pass
        except Exception:
            pass


def raise_read_error(exc: BaseException) -> NoReturn:
    raise map_read_error(exc) from None
