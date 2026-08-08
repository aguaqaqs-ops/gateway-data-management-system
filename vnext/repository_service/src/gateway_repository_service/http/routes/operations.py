"""Versioned import operation polling routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request

from gateway_repository_contracts import GetOperationResponse
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.versioned_import.submission import ImportSubmissionService


def register_operation_routes(app: FastAPI) -> None:
    @app.get(
        "/v1/repositories/{repository_id}/operations/{operation_id}",
        response_model=GetOperationResponse,
        status_code=200,
        responses={
            401: {"description": "Authentication failed"},
            404: {"description": "Operation not found"},
            422: {"description": "Request validation failed"},
            503: {"description": "Service not ready"},
        },
    )
    def get_operation(
        request: Request,
        repository_id: UUID,
        operation_id: UUID,
        _authorized: Annotated[None, Depends(require_bearer_token)],
    ) -> GetOperationResponse:
        runtime = _runtime_from_state(request)
        service = ImportSubmissionService(runtime)
        return service.get_operation(repository_id, operation_id)


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime
