"""Strict Repository Service wire protocol validation."""

from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from gateway_repository_contracts import (
    MAX_WIRE_ERROR_JSON_BYTES,
    SimpleError,
    VERSIONED_READ_ARROW_MEDIA_TYPE,
)
from gateway_repository_client.errors import RepositoryClientError, RepositoryProtocolError

T = TypeVar("T", bound=BaseModel)

_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 1024
MAX_WIRE_JSON_BYTES = MAX_WIRE_ERROR_JSON_BYTES


def peek_request_id(response: httpx.Response) -> str | None:
    """Return a validated X-Request-ID when present without raising."""

    raw = response.headers.get(_REQUEST_ID_HEADER)
    if raw is None or not isinstance(raw, str):
        return None
    if len(raw) == 0 or len(raw) > _MAX_REQUEST_ID_LENGTH:
        return None
    return raw


def require_request_id(response: httpx.Response) -> str:
    """Return a validated X-Request-ID header value."""

    request_id = peek_request_id(response)
    if request_id is None:
        if response.headers.get(_REQUEST_ID_HEADER) is None:
            raise RepositoryProtocolError(
                "missing X-Request-ID header",
                status_code=response.status_code,
            )
        raise RepositoryProtocolError(
            "illegal X-Request-ID header",
            status_code=response.status_code,
        )
    return request_id


async def read_bounded_bytes(
    response: httpx.Response,
    *,
    limit: int = MAX_WIRE_ERROR_JSON_BYTES,
    request_id: str | None = None,
) -> bytes:
    """Read a response body up to a fixed byte limit."""

    resolved_request_id = request_id if request_id is not None else peek_request_id(response)
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise RepositoryProtocolError(
                    f"response body exceeds {limit} byte limit",
                    status_code=response.status_code,
                    request_id=resolved_request_id,
                )
            chunks.append(chunk)
    except RepositoryProtocolError:
        await response.aclose()
        raise
    return b"".join(chunks)


def _parse_json_bytes(
    body: bytes,
    *,
    response: httpx.Response,
    request_id: str | None = None,
) -> object:
    try:
        return json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise RepositoryProtocolError(
            "response body is not valid JSON",
            status_code=response.status_code,
            request_id=request_id,
        ) from exc


async def parse_success_dto(
    response: httpx.Response,
    *,
    expected_status: int,
    model: type[T],
    body: bytes,
) -> T:
    """Validate success status and decode a Contracts DTO."""

    request_id = require_request_id(response)
    if response.status_code != expected_status:
        raise RepositoryProtocolError(
            f"unexpected HTTP status {response.status_code}; expected {expected_status}",
            status_code=response.status_code,
            request_id=request_id,
        )
    payload = _parse_json_bytes(body, response=response, request_id=request_id)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise RepositoryProtocolError(
            f"success body does not match {model.__name__}",
            status_code=response.status_code,
            request_id=request_id,
        ) from exc


async def raise_for_error_response(
    response: httpx.Response,
    *,
    body: bytes,
) -> None:
    """Parse a SimpleError body and raise RepositoryClientError."""

    request_id = require_request_id(response)
    payload = _parse_json_bytes(body, response=response, request_id=request_id)
    if not isinstance(payload, dict):
        raise RepositoryProtocolError(
            "error body is not a JSON object",
            status_code=response.status_code,
            request_id=request_id,
        )

    body_request_id = payload.get("request_id")
    if body_request_id is None:
        raise RepositoryProtocolError(
            "missing error body request_id",
            status_code=response.status_code,
            request_id=request_id,
        )
    if body_request_id != request_id:
        raise RepositoryProtocolError(
            "error body request_id does not match X-Request-ID",
            status_code=response.status_code,
            request_id=request_id,
        )

    try:
        error = SimpleError.model_validate(payload)
    except ValidationError as exc:
        raise RepositoryProtocolError(
            "error body does not match SimpleError",
            status_code=response.status_code,
            request_id=request_id,
        ) from exc

    raise RepositoryClientError(status_code=response.status_code, error=error)


async def parse_json_response(
    response: httpx.Response,
    *,
    expected_status: int,
    model: type[T],
    max_body_bytes: int = MAX_WIRE_ERROR_JSON_BYTES,
) -> T:
    """Decode a JSON endpoint response or raise typed HTTP/protocol errors."""

    try:
        body = await read_bounded_bytes(response, limit=max_body_bytes)
        if response.status_code == expected_status:
            return await parse_success_dto(
                response,
                expected_status=expected_status,
                model=model,
                body=body,
            )
        if 200 <= response.status_code < 300:
            request_id = require_request_id(response)
            raise RepositoryProtocolError(
                f"unexpected HTTP status {response.status_code}; expected {expected_status}",
                status_code=response.status_code,
                request_id=request_id,
            )
        await raise_for_error_response(response, body=body)
    finally:
        await response.aclose()
    raise AssertionError("raise_for_error_response must raise")


def require_arrow_media_type(response: httpx.Response) -> str:
    """Validate the frozen Arrow IPC stream media type."""

    request_id = require_request_id(response)
    raw = response.headers.get("Content-Type")
    if raw is None:
        raise RepositoryProtocolError(
            "missing Content-Type for Arrow stream",
            status_code=response.status_code,
            request_id=request_id,
        )
    media_type = raw.split(";", 1)[0].strip().lower()
    expected = VERSIONED_READ_ARROW_MEDIA_TYPE.lower()
    if media_type != expected:
        raise RepositoryProtocolError(
            f"unexpected Arrow media type {raw!r}; expected {VERSIONED_READ_ARROW_MEDIA_TYPE}",
            status_code=response.status_code,
            request_id=request_id,
        )
    return VERSIONED_READ_ARROW_MEDIA_TYPE
