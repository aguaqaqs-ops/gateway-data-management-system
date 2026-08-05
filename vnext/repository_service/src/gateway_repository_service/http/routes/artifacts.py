"""Artifact upload routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from pydantic import ValidationError

from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UploadArtifactResponse,
    UploadRequestHeaders,
)
from gateway_repository_service.http.auth import require_bearer_token
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.http.readiness_guard import require_service_ready
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact.command import UploadArtifactCommand


def register_artifact_routes(app: FastAPI) -> None:
    @app.post(
        "/v1/repositories/{repository_id}/artifacts",
        response_model=UploadArtifactResponse,
        status_code=201,
        responses={
            401: {"description": "Authentication failed"},
            404: {"description": "Repository not found"},
            409: {"description": "Idempotency conflict"},
            413: {"description": "Payload too large"},
            415: {"description": "Unsupported media type"},
            422: {"description": "Request validation failed"},
            503: {"description": "Service not ready or disk admission denied"},
        },
    )
    async def upload_artifact(
        request: Request,
        repository_id: UUID,
        _authorized: Annotated[None, Depends(require_bearer_token)],
        _ready: Annotated[None, Depends(require_service_ready)],
        content_type: Annotated[str, Header(alias="Content-Type")],
        content_length: Annotated[int, Header(alias="Content-Length")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
        artifact_sha256: Annotated[str, Header(alias="X-Artifact-SHA256")],
    ) -> UploadArtifactResponse:
        _reject_multipart_content_type(content_type)
        if content_type != REPOSITORY_IMPORT_MEDIA_TYPE:
            raise _unsupported_media_type()

        try:
            headers = UploadRequestHeaders(
                content_type=content_type,
                content_length=content_length,
                idempotency_key=idempotency_key,
                artifact_sha256=artifact_sha256,
            )
        except ValidationError as exc:
            raise _request_validation_failed(exc) from exc

        runtime = _runtime_from_state(request)
        command = UploadArtifactCommand(
            settings=runtime.settings,
            layout=runtime.layout,
            mutation_store=runtime.mutation_store,
        )

        async def body_stream() -> AsyncIterator[bytes]:
            async for chunk in request.stream():
                yield chunk

        response = await command.execute(repository_id, headers, body_stream())
        artifact_ref = response.artifact_ref
        runtime.register_succeeded_upload(
            repository_id,
            UUID(str(artifact_ref.artifact_id)),
            artifact_ref.size_bytes,
        )
        return response


def _runtime_from_state(request: Request) -> ServiceRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ServiceRuntime):
        raise RuntimeError("service runtime is not initialized")
    return runtime


def _reject_multipart_content_type(content_type: str) -> None:
    lowered = content_type.lower()
    if "multipart/" in lowered or "boundary=" in lowered:
        raise _unsupported_media_type()


def _unsupported_media_type() -> ServiceError:
    return ServiceError(
        code="UNSUPPORTED_MEDIA_TYPE",
        message="Content-Type must be the repository import media type",
        status_code=415,
    )


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
