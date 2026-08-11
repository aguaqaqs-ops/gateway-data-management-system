"""Strict Repository Service wire protocol validation."""

from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from gateway_repository_contracts import SimpleError, VERSIONED_READ_ARROW_MEDIA_TYPE
from gateway_repository_client.errors import RepositoryClientError, RepositoryProtocolError

T = TypeVar("T", bound=BaseModel)

_REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 1024


def require_request_id(response: httpx.Response) -> str:
    """Return a validated X-Request-ID header value."""

    raw = response.headers.get(_REQUEST_ID_HEADER)
    if raw is None or not isinstance(raw, str):
        raise RepositoryProtocolError(
            "missing X-Request-ID header",
            status_code=response.status_code,
        )
    if len(raw) == 0 or len(raw) > _MAX_REQUEST_ID_LENGTH:
        raise RepositoryProtocolError(
            "illegal X-Request-ID header",
            status_code=response.status_code,
        )
    return raw


def parse_json_object(response: httpx.Response) -> object:
    """Parse a JSON response body, raising protocol error on malformed payloads."""

    try:
        return response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise RepositoryProtocolError(
            "response body is not valid JSON",
            status_code=response.status_code,
        ) from exc


def parse_success_dto(
    response: httpx.Response,
    *,
    expected_status: int,
    model: type[T],
) -> T:
    """Validate success status and decode a Contracts DTO."""

    require_request_id(response)
    if response.status_code != expected_status:
        raise RepositoryProtocolError(
            f"unexpected HTTP status {response.status_code}; expected {expected_status}",
            status_code=response.status_code,
        )
    payload = parse_json_object(response)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise RepositoryProtocolError(
            f"success body does not match {model.__name__}",
            status_code=response.status_code,
        ) from exc


def raise_for_error_response(response: httpx.Response) -> None:
    """Parse a SimpleError body and raise RepositoryClientError."""

    request_id = require_request_id(response)
    payload = parse_json_object(response)
    if not isinstance(payload, dict):
        raise RepositoryProtocolError(
            "error body is not a JSON object",
            status_code=response.status_code,
        )

    body_request_id = payload.get("request_id")
    if body_request_id is None:
        raise RepositoryProtocolError(
            "missing error body request_id",
            status_code=response.status_code,
        )
    if body_request_id != request_id:
        raise RepositoryProtocolError(
            "error body request_id does not match X-Request-ID",
            status_code=response.status_code,
        )

    try:
        error = SimpleError.model_validate(payload)
    except ValidationError as exc:
        raise RepositoryProtocolError(
            "error body does not match SimpleError",
            status_code=response.status_code,
        ) from exc

    raise RepositoryClientError(status_code=response.status_code, error=error)


def parse_json_response(
    response: httpx.Response,
    *,
    expected_status: int,
    model: type[T],
) -> T:
    """Decode a JSON endpoint response or raise typed HTTP/protocol errors."""

    if response.status_code == expected_status:
        return parse_success_dto(response, expected_status=expected_status, model=model)
    if 200 <= response.status_code < 300:
        require_request_id(response)
        raise RepositoryProtocolError(
            f"unexpected HTTP status {response.status_code}; expected {expected_status}",
            status_code=response.status_code,
        )
    raise_for_error_response(response)
    raise AssertionError("raise_for_error_response must raise")


def require_arrow_media_type(response: httpx.Response) -> str:
    """Validate the frozen Arrow IPC stream media type."""

    raw = response.headers.get("Content-Type")
    if raw is None:
        raise RepositoryProtocolError(
            "missing Content-Type for Arrow stream",
            status_code=response.status_code,
        )
    media_type = raw.split(";", 1)[0].strip().lower()
    expected = VERSIONED_READ_ARROW_MEDIA_TYPE.lower()
    if media_type != expected:
        raise RepositoryProtocolError(
            f"unexpected Arrow media type {raw!r}; expected {VERSIONED_READ_ARROW_MEDIA_TYPE}",
            status_code=response.status_code,
        )
    return VERSIONED_READ_ARROW_MEDIA_TYPE
