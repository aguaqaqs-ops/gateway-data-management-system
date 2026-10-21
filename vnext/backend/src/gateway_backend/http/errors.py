"""Unified error mapping for 5A HTTP responses."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway_backend.application.archive.errors import (
    ArchiveApplicationError,
    ArchiveAuditVersionConflict,
    ArchiveIntegrityFailure,
)
from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    ArchiveClosed,
    BaselineVersionConflict,
    FinalizeBindingMismatch,
    FinalizeRecoveryRequired,
    IdempotencyConflict as SubmitIdempotencyConflict,
    NoCanonicalChange,
    ProjectIdentityConfirmationMismatch,
    ProjectIdentityConfirmationRequired,
    PreviewBindingConflict as SubmitPreviewBindingConflict,
    PreviewDerivedStale,
    ReviewIntegrityFailure,
    ReviewWorkspaceOccupancyConflict,
    SubmitApplicationError,
)
from gateway_backend.application.history.errors import (
    HistoryApplicationError,
    HistoryCompareAcceptanceUnavailable,
    HistoryCompareBindingConflict,
    HistoryCompareIdempotencyConflict,
    HistoryCompareJobNotRegistered,
    HistoryCompareNodeNotFound,
    HistoryIntegrityFailure,
    HistoryRequestValidation,
)
from gateway_backend.application.workspace.errors import (
    IdempotencyConflict,
    PreviewArtifactUnavailable,
    PreviewBindingConflict,
    PreviewJobNotRegistered,
    WorkspaceApplicationError,
)
from gateway_backend.domain.submission.errors import (
    InvalidReviewIdempotencyKey,
    InvalidReviewReason,
    InvalidReviewTransition,
    ReviewVersionConflict,
    SubmissionDomainError,
    SubmitOccupancyConflict,
)
from gateway_backend.domain.workspace.errors import (
    PermissionDenied,
    ScopeForbidden,
    ScopeResolutionError,
    UploadClosureInvalid,
    WorkspaceDomainError,
    WorkspaceVersionConflict,
)
from gateway_backend.http.schemas.errors import ErrorResponse
from gateway_backend.operations.store import StoreBusy

INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
INTERNAL_ERROR_MESSAGE = "internal server error"

_MAPPING_NOT_FOUND_REASONS = frozenset(
    {
        "provisioned mapping is missing",
        "provisioned mapping is disabled",
    }
)


class ApiError(Exception):
    """Expected HTTP error mapped to the frozen 5A error family."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def sanitize_validation_errors(errors: Sequence[Any]) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        loc = error.get("loc", ())
        if isinstance(loc, (list, tuple)):
            normalized_loc: list[str | int] = [
                item if isinstance(item, int) else str(item) for item in loc
            ]
        else:
            normalized_loc = [str(loc)]
        sanitized.append(
            {
                "loc": normalized_loc,
                "type": str(error.get("type", "value_error")),
                "msg": str(error.get("msg", "validation error")),
            }
        )
    return sanitized


def map_domain_exception(exc: BaseException) -> ApiError | None:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, PermissionDenied):
        return ApiError(
            code="SCOPE_FORBIDDEN",
            message=str(exc),
            status_code=403,
            details={"permission": exc.permission},
        )
    if isinstance(exc, ScopeForbidden):
        return ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    if isinstance(exc, ScopeResolutionError):
        if exc.reason in _MAPPING_NOT_FOUND_REASONS:
            return ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        return ApiError(
            code="DEPENDENCY_UNAVAILABLE",
            message=str(exc),
            status_code=503,
            details={"reason": exc.reason},
        )
    if isinstance(exc, IdempotencyConflict):
        return ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            status_code=409,
            details={"idempotency_key": exc.idempotency_key},
        )
    if isinstance(exc, WorkspaceVersionConflict):
        return ApiError(
            code="WORKSPACE_VERSION_CONFLICT",
            message=str(exc),
            status_code=409,
            details={"expected": exc.expected, "actual": exc.actual},
        )
    if isinstance(exc, PreviewBindingConflict):
        return ApiError(
            code="PREVIEW_BINDING_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, PreviewJobNotRegistered):
        return ApiError(
            code="SERVICE_NOT_READY",
            message="preview job definition is not registered",
            status_code=503,
        )
    if isinstance(exc, PreviewArtifactUnavailable):
        return ApiError(
            code="DEPENDENCY_UNAVAILABLE",
            message="source artifact is not readable",
            status_code=503,
        )
    if isinstance(exc, SubmitIdempotencyConflict):
        return ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            status_code=409,
            details={"idempotency_key": exc.idempotency_key},
        )
    if isinstance(exc, SubmitPreviewBindingConflict):
        return ApiError(
            code="PREVIEW_BINDING_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, PreviewDerivedStale):
        return ApiError(
            code="PREVIEW_DERIVED_STALE",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, BaselineVersionConflict):
        return ApiError(
            code="BASELINE_VERSION_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, NoCanonicalChange):
        return ApiError(
            code="NO_CANONICAL_CHANGE",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, ProjectIdentityConfirmationRequired):
        return ApiError(
            code=exc.stable_code,
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, ProjectIdentityConfirmationMismatch):
        return ApiError(
            code=exc.stable_code,
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, SubmitOccupancyConflict):
        return ApiError(
            code="SUBMIT_OCCUPANCY_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, AbortProofNotSatisfied):
        return ApiError(
            code="ABORT_PROOF_NOT_SATISFIED",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, FinalizeBindingMismatch):
        return ApiError(
            code="SUBMIT_RESULT_BINDING_MISMATCH",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, FinalizeRecoveryRequired):
        return ApiError(
            code="FINALIZE_RECOVERY_REQUIRED",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, ReviewIntegrityFailure):
        return ApiError(
            code="SERVICE_NOT_READY",
            message="service not ready",
            status_code=503,
        )
    if isinstance(exc, ReviewWorkspaceOccupancyConflict):
        return ApiError(
            code="WORKSPACE_OCCUPANCY_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, HistoryIntegrityFailure):
        return ApiError(
            code="HISTORY_INTEGRITY_FAILURE",
            message=str(exc),
            status_code=503,
        )
    if isinstance(exc, HistoryRequestValidation):
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message=str(exc),
            status_code=422,
        )
    if isinstance(exc, HistoryCompareNodeNotFound):
        return ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    if isinstance(exc, HistoryCompareIdempotencyConflict):
        return ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="idempotency conflict",
            status_code=409,
            details={"idempotency_key": exc.idempotency_key},
        )
    if isinstance(exc, HistoryCompareBindingConflict):
        return ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, HistoryCompareJobNotRegistered | HistoryCompareAcceptanceUnavailable):
        return ApiError(
            code="SERVICE_NOT_READY",
            message="history compare service is not ready",
            status_code=503,
        )
    if isinstance(exc, HistoryApplicationError):
        return ApiError(
            code="HISTORY_INTEGRITY_FAILURE",
            message=str(exc),
            status_code=503,
        )
    if isinstance(exc, ArchiveIntegrityFailure):
        return ApiError(
            code="ARCHIVE_INTEGRITY_FAILURE",
            message=str(exc),
            status_code=503,
        )
    if isinstance(exc, ArchiveApplicationError):
        stable_code = getattr(exc, "stable_code", None)
        if stable_code == "RESOURCE_NOT_FOUND":
            return ApiError(
                code="RESOURCE_NOT_FOUND",
                message=str(exc),
                status_code=404,
            )
        if isinstance(exc, ArchiveAuditVersionConflict):
            return ApiError(
                code="ARCHIVE_AUDIT_VERSION_CONFLICT",
                message=str(exc),
                status_code=409,
                details={"expected": exc.expected, "actual": exc.actual},
            )
        if stable_code in {
            "ARCHIVE_SCOPE_LIMIT_EXCEEDED",
            "CANDIDATE_SET_CONFLICT",
            "CANDIDATE_BINDING_CONFLICT",
            "ARCHIVE_CONFIRMATION_REQUIRED",
            "ARCHIVE_ANOMALY_UNRESOLVED",
            "ACTIVE_SUBMIT_ATTEMPT",
        }:
            return ApiError(
                code=stable_code,
                message=str(exc),
                status_code=409,
            )
    if isinstance(exc, ArchiveClosed):
        return ApiError(
            code="ARCHIVE_CLOSED",
            message=str(exc),
            status_code=409,
        )
    if isinstance(exc, ReviewVersionConflict):
        return ApiError(
            code="REVIEW_VERSION_CONFLICT",
            message=str(exc),
            status_code=409,
            details={"expected": exc.expected, "actual": exc.actual},
        )
    if isinstance(exc, InvalidReviewTransition):
        return ApiError(
            code="REVIEW_TRANSITION_CONFLICT",
            message=str(exc),
            status_code=409,
            details={"current": exc.current, "action": exc.action},
        )
    if isinstance(exc, InvalidReviewReason):
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="request validation failed",
            status_code=422,
        )
    if isinstance(exc, InvalidReviewIdempotencyKey):
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="request validation failed",
            status_code=422,
        )
    if isinstance(exc, SubmitApplicationError):
        stable_code = getattr(exc, "stable_code", None)
        if stable_code == "IDEMPOTENCY_CONFLICT":
            return ApiError(
                code="IDEMPOTENCY_CONFLICT",
                message=str(exc),
                status_code=409,
                details={"idempotency_key": getattr(exc, "idempotency_key", None)},
            )
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message=str(exc),
            status_code=422,
        )
    if isinstance(exc, UploadClosureInvalid):
        return ApiError(
            code="UPLOAD_CLOSURE_INVALID",
            message=str(exc),
            status_code=422,
            details={"reason": exc.reason},
        )
    if isinstance(exc, WorkspaceDomainError) or isinstance(exc, WorkspaceApplicationError):
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message=str(exc),
            status_code=422,
        )
    return None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(WorkspaceDomainError)
    async def workspace_domain_error_handler(
        _request: Request,
        exc: WorkspaceDomainError,
    ) -> JSONResponse:
        mapped = map_domain_exception(exc)
        if mapped is None:
            return error_response(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
                status_code=500,
            )
        return error_response(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
            details=mapped.details,
        )

    @app.exception_handler(WorkspaceApplicationError)
    async def workspace_application_error_handler(
        _request: Request,
        exc: WorkspaceApplicationError,
    ) -> JSONResponse:
        mapped = map_domain_exception(exc)
        if mapped is None:
            return error_response(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
                status_code=500,
            )
        return error_response(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
            details=mapped.details,
        )

    @app.exception_handler(SubmitApplicationError)
    async def submit_application_error_handler(
        _request: Request,
        exc: SubmitApplicationError,
    ) -> JSONResponse:
        mapped = map_domain_exception(exc)
        if mapped is None:
            return error_response(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
                status_code=500,
            )
        return error_response(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
            details=mapped.details,
        )

    @app.exception_handler(SubmissionDomainError)
    async def submission_domain_error_handler(
        _request: Request,
        exc: SubmissionDomainError,
    ) -> JSONResponse:
        mapped = map_domain_exception(exc)
        if mapped is None:
            return error_response(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
                status_code=500,
            )
        return error_response(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
            details=mapped.details,
        )

    @app.exception_handler(HistoryApplicationError)
    async def history_application_error_handler(
        _request: Request,
        exc: HistoryApplicationError,
    ) -> JSONResponse:
        mapped = map_domain_exception(exc)
        if mapped is None:
            return error_response(
                code=INTERNAL_ERROR_CODE,
                message=INTERNAL_ERROR_MESSAGE,
                status_code=500,
            )
        return error_response(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
            details=mapped.details,
        )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(StoreBusy)
    async def store_busy_error_handler(_request: Request, _exc: StoreBusy) -> JSONResponse:
        return error_response(
            code="SERVICE_NOT_READY",
            message="service not ready",
            status_code=503,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            code="REQUEST_VALIDATION_FAILED",
            message="request validation failed",
            status_code=422,
            details={"errors": sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        if exc.status_code == 401:
            return error_response(
                code="AUTHENTICATION_REQUIRED",
                message="authentication required",
                status_code=401,
            )
        return error_response(
            code=INTERNAL_ERROR_CODE,
            message=INTERNAL_ERROR_MESSAGE,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return error_response(
            code=INTERNAL_ERROR_CODE,
            message=INTERNAL_ERROR_MESSAGE,
            status_code=500,
        )
