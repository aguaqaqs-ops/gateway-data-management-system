"""Request body guards for header-only mutation routes."""

from __future__ import annotations

from fastapi import Request

from gateway_repository_service.http.errors import ServiceError


async def require_empty_body(request: Request) -> None:
    """Reject mutations that must not carry a request body."""

    body = await request.body()
    if body:
        raise ServiceError(
            code="REQUEST_VALIDATION_FAILED",
            message="request body must be empty",
            status_code=422,
        )
