"""Request body guards for header-only mutation routes."""

from __future__ import annotations

from fastapi import Request

from gateway_repository_service.http.errors import ServiceError


async def require_empty_body(request: Request) -> None:
    """Reject mutations that must not carry a request body."""

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            raise _empty_body_error() from None
        if parsed_length > 0:
            raise _empty_body_error()
        if parsed_length == 0:
            return

    async for chunk in request.stream():
        if chunk:
            raise _empty_body_error()


def _empty_body_error() -> ServiceError:
    return ServiceError(
        code="REQUEST_VALIDATION_FAILED",
        message="request body must be empty",
        status_code=422,
    )
