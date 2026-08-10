"""Shared OpenAPI fragments for Repository Service HTTP routes."""

from __future__ import annotations

from typing import Any

from gateway_repository_contracts import VERSIONED_READ_ARROW_MEDIA_TYPE

SIMPLE_ERROR_CONTENT: dict[str, dict[str, Any]] = {
    "application/json": {
        "schema": {"$ref": "#/components/schemas/SimpleError"},
    }
}

REQUEST_ID_HEADER: dict[str, dict[str, Any]] = {
    "X-Request-ID": {
        "description": "Server-generated opaque request identifier",
        "schema": {"type": "string"},
    }
}


def simple_error_response(status_code: int, *, description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": SIMPLE_ERROR_CONTENT,
        "headers": REQUEST_ID_HEADER,
    }


def versioned_read_error_responses() -> dict[int | str, dict[str, Any]]:
    return {
        401: simple_error_response(401, description="Authentication failed"),
        404: simple_error_response(404, description="Repository, ref, commit, or table not found"),
        422: simple_error_response(422, description="Request validation failed"),
        503: simple_error_response(503, description="Service not ready"),
    }


def versioned_read_json_responses(*, success_description: str) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": success_description,
            "headers": REQUEST_ID_HEADER,
        },
        **versioned_read_error_responses(),
    }


def versioned_read_arrow_stream_response() -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": "Arrow IPC stream",
            "content": {
                VERSIONED_READ_ARROW_MEDIA_TYPE: {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
            "headers": REQUEST_ID_HEADER,
        },
        **versioned_read_error_responses(),
    }
