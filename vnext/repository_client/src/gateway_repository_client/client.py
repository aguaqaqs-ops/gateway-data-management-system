"""Typed async client for the Gateway Repository Service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from gateway_repository_contracts import CreateRepositoryResponse, SimpleError
from gateway_repository_client.errors import RepositoryClientError
from gateway_repository_client.retry import retry_idempotent_request


class RepositoryClient:
    """Async facade for synchronous Repository mutations."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    async def create_repository(self, *, idempotency_key: str) -> CreateRepositoryResponse:
        async def _send() -> CreateRepositoryResponse:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/v1/repositories",
                    headers={
                        "Authorization": f"Bearer {self._bearer_token}",
                        "Idempotency-Key": idempotency_key,
                    },
                )
                return _parse_create_response(response)

        return await retry_idempotent_request(_send)


def _parse_create_response(response: httpx.Response) -> CreateRepositoryResponse:
    if response.is_success:
        return CreateRepositoryResponse.model_validate(response.json())

    error = _parse_simple_error(response)
    raise RepositoryClientError(status_code=response.status_code, error=error)


def _parse_simple_error(response: httpx.Response) -> SimpleError:
    payload: Mapping[str, Any]
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    request_id = response.headers.get("X-Request-ID")
    if "request_id" not in payload and request_id is not None:
        payload = {**payload, "request_id": request_id}
    return SimpleError.model_validate(
        {
            "code": payload.get("code", "HTTP_ERROR"),
            "message": payload.get("message", "request failed"),
            "details": payload.get("details"),
            "request_id": payload.get("request_id"),
        }
    )
