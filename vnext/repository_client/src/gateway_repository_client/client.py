"""Typed async client for the Gateway Repository Service."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import UUID

import httpx

from gateway_repository_contracts import CreateRepositoryResponse, SimpleError, UploadArtifactResponse
from gateway_repository_client.errors import RepositoryClientError
from gateway_repository_client.retry import RETRYABLE_STATUS_CODES, retry_idempotent_request
from gateway_repository_client.upload import (
    NonRewindableBody,
    NonRewindableUploadSourceError,
    RewindableBody,
    UploadBodySource,
    coerce_upload_body_source,
)


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

    async def upload_artifact(
        self,
        *,
        repository_id: UUID | str,
        idempotency_key: str,
        media_type: str,
        raw_sha256: str,
        body: bytes | RewindableBody | NonRewindableBody,
    ) -> UploadArtifactResponse:
        source = coerce_upload_body_source(body)
        resolved_repository_id = UUID(str(repository_id))

        async def _send() -> UploadArtifactResponse:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"/v1/repositories/{resolved_repository_id}/artifacts",
                    headers={
                        "Authorization": f"Bearer {self._bearer_token}",
                        "Content-Type": media_type,
                        "Content-Length": str(source.declared_size),
                        "Idempotency-Key": idempotency_key,
                        "X-Artifact-SHA256": raw_sha256,
                    },
                    content=_async_chunk_stream(source),
                )
                return _parse_upload_response(response)

        if source.rewindable:
            return await retry_idempotent_request(_send)
        try:
            return await _send()
        except (httpx.TransportError, httpx.HTTPStatusError, RepositoryClientError) as exc:
            status_code = _retryable_status_code(exc)
            if status_code is not None:
                raise NonRewindableUploadSourceError(
                    status_code=status_code,
                    message="upload source is not rewindable for retry",
                ) from exc
            raise


async def _async_chunk_stream(source: UploadBodySource) -> AsyncIterator[bytes]:
    for chunk in source.open_chunks():
        yield chunk


def _retryable_status_code(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in RETRYABLE_STATUS_CODES:
            return exc.response.status_code
        return None
    if isinstance(exc, RepositoryClientError):
        if exc.status_code in RETRYABLE_STATUS_CODES:
            return exc.status_code
        return None
    if isinstance(exc, httpx.TransportError):
        return 503
    return None


def _parse_create_response(response: httpx.Response) -> CreateRepositoryResponse:
    if response.status_code == 201:
        return CreateRepositoryResponse.model_validate(response.json())

    error = _parse_simple_error(response)
    raise RepositoryClientError(status_code=response.status_code, error=error)


def _parse_upload_response(response: httpx.Response) -> UploadArtifactResponse:
    if response.status_code == 201:
        return UploadArtifactResponse.model_validate(response.json())

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
