"""Tests for the typed async Repository client."""

from __future__ import annotations

import httpx
import pytest

from gateway_repository_client import (
    RepositoryClient,
    RepositoryClientError,
    RepositoryProtocolError,
)
from gateway_repository_contracts import CreateRepositoryResponse


@pytest.mark.asyncio
async def test_create_repository_retries_same_key_on_503() -> None:
    attempts = {"count": 0}
    repository_id = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
    commit_id = "abc123"

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        assert request.headers["Idempotency-Key"] == "client-retry-key"
        return httpx.Response(
            201,
            json={
                "repository_id": repository_id,
                "default_ref": "main",
                "initial_commit_id": commit_id,
            },
            headers={"X-Request-ID": "req-2"},
        )

    transport = httpx.MockTransport(handler)
    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=transport,
    )

    response = await client.create_repository(idempotency_key="client-retry-key")

    assert attempts["count"] == 2
    assert response == CreateRepositoryResponse.model_validate(
        {
            "repository_id": repository_id,
            "default_ref": "main",
            "initial_commit_id": commit_id,
        }
    )


@pytest.mark.asyncio
async def test_create_repository_surfaces_non_retryable_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "code": "IDEMPOTENCY_CONFLICT",
                "message": "conflict",
                "request_id": "req-409",
            },
            headers={"X-Request-ID": "req-409"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RepositoryClientError) as exc_info:
        await client.create_repository(idempotency_key="conflict-key")

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == "IDEMPOTENCY_CONFLICT"
    assert exc_info.value.error.request_id == "req-409"


@pytest.mark.asyncio
async def test_create_repository_rejects_http_200() -> None:
    attempts = {"count": 0}
    repository_id = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            json={
                "repository_id": repository_id,
                "default_ref": "main",
                "initial_commit_id": "abc123",
            },
            headers={"X-Request-ID": "req-200"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RepositoryProtocolError) as exc_info:
        await client.create_repository(idempotency_key="http-200-key")

    assert attempts["count"] == 1
    assert exc_info.value.status_code == 200


@pytest.mark.asyncio
async def test_retry_idempotent_request_does_not_retry_409() -> None:
    attempts = {"count": 0}

    async def operation() -> None:
        attempts["count"] += 1
        request = httpx.Request("POST", "http://repository.test/v1/repositories")
        response = httpx.Response(
            409,
            json={"code": "IDEMPOTENCY_CONFLICT", "message": "conflict"},
            request=request,
        )
        response.raise_for_status()

    with pytest.raises(httpx.HTTPStatusError):
        from gateway_repository_client.retry import retry_idempotent_request

        await retry_idempotent_request(operation)

    assert attempts["count"] == 1
