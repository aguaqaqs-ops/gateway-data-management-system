"""Versioned import submission routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from pydantic import ValidationError

from gateway_repository_contracts import (
    ImportRequestHeaders,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
)
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.versioned_import.submission import ImportSubmissionService


def register_import_routes(app: FastAPI) -> None:
    @app.post(
        "/v1/repositories/{repository_id}/versioned/imports",
        response_model=SubmitVersionedImportResponse,
        status_code=202,
        responses={
            401: {"description": "Authentication failed"},
            404: {"description": "Repository or artifact not found"},
            409: {"description": "Idempotency conflict or manual recovery required"},
            422: {"description": "Request validation failed"},
            429: {"description": "Import queue is full"},
            503: {"description": "Service not ready or disk admission denied"},
        },
    )
    def submit_versioned_import(
        request: Request,
        repository_id: UUID,
        body: SubmitVersionedImportRequest,
        _authorized: Annotated[None, Depends(require_bearer_token)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    ) -> SubmitVersionedImportResponse:
        try:
            headers = ImportRequestHeaders(idempotency_key=idempotency_key)
        except ValidationError as exc:
            raise _request_validation_failed(exc) from exc

        runtime = _runtime_from_state(request)
        service = ImportSubmissionService(runtime)
        request_id = getattr(request.state, "request_id", None)
        return service.submit(
            repository_id,
            headers,
            body,
            request_id=str(request_id) if request_id is not None else None,
        )


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime


def _request_validation_failed(exc: ValidationError) -> ServiceError:
    return ServiceError(
        code="REQUEST_VALIDATION_FAILED",
        message="request headers are invalid",
        status_code=422,
        details={"errors": _sanitize_header_validation_errors(exc)},
    )


def _sanitize_header_validation_errors(exc: ValidationError) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for error in exc.errors():
        loc = error.get("loc", ())
        if isinstance(loc, (list, tuple)):
            normalized_loc = [item if isinstance(item, int) else str(item) for item in loc]
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
