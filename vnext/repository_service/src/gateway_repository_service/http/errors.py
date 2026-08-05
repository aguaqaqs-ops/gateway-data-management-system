"""Unified SimpleError mapping for HTTP exceptions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway_repository_contracts import SimpleError

INTERNAL_ERROR_CODE = "INTERNAL_ERROR"
INTERNAL_ERROR_MESSAGE = "internal server error"

ValidationErrorDetail = dict[str, str | list[str | int]]


class ServiceError(Exception):
    """Internal expected error mapped to a SimpleError response."""

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


def _request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    if request_id is None:
        return None
    return str(request_id)


def sanitize_validation_errors(errors: Sequence[Any]) -> list[ValidationErrorDetail]:
    """Return JSON-safe validation details without input, ctx or url."""

    sanitized: list[ValidationErrorDetail] = []
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


def simple_error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    error = SimpleError(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
    )
    response = JSONResponse(
        status_code=status_code,
        content=error.model_dump(mode="json", exclude_none=True),
    )
    if request_id is not None:
        response.headers["X-Request-ID"] = request_id
    return response


def internal_error_response(request: Request) -> JSONResponse:
    return simple_error_response(
        request,
        code=INTERNAL_ERROR_CODE,
        message=INTERNAL_ERROR_MESSAGE,
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return simple_error_response(
            request,
            code="REQUEST_VALIDATION_FAILED",
            message="request validation failed",
            status_code=422,
            details={"errors": sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(ServiceError)
    async def service_error_exception_handler(
        request: Request,
        exc: ServiceError,
    ) -> JSONResponse:
        return simple_error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        return simple_error_response(
            request,
            code="HTTP_ERROR",
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        del exc
        return internal_error_response(request)
