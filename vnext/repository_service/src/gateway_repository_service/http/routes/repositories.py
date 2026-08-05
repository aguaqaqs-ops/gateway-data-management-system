"""Versioned repository mutation routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request

from gateway_repository_contracts import CreateRepositoryResponse
from gateway_repository_service.create_repository.command import CreateRepositoryCommand
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.readiness_guard import require_service_ready
from gateway_repository_service.runtime import ServiceRuntime


def register_repository_routes(app: FastAPI) -> None:
    @app.post(
        "/v1/repositories",
        response_model=CreateRepositoryResponse,
        status_code=201,
        responses={
            401: {"description": "Authentication failed"},
            409: {"description": "Idempotency conflict"},
            422: {"description": "Request validation failed"},
            503: {"description": "Service not ready"},
        },
    )
    def create_repository(
        request: Request,
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    ) -> CreateRepositoryResponse:
        runtime = _runtime_from_state(request)
        command = CreateRepositoryCommand(
            settings=runtime.settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
        )
        return command.execute(idempotency_key)


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime
