"""Typed protocol-error coverage for Repository Client wire validation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from gateway_repository_client import (
    RepositoryClient,
    RepositoryClientError,
    RepositoryProtocolError,
)

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OP_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c22")


@pytest.mark.asyncio
async def test_malformed_success_body_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"X-Request-ID": "req-1", "Content-Type": "application/json"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="valid JSON"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_success_body_wrong_shape_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"unexpected": True},
            headers={"X-Request-ID": "req-1"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="GetOperationResponse"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_malformed_simple_error_body_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"message": "missing code", "request_id": "req-1"},
            headers={"X-Request-ID": "req-1"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="SimpleError"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_missing_request_id_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"code": "OPERATION_NOT_FOUND", "message": "missing"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="missing X-Request-ID"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_illegal_request_id_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"code": "OPERATION_NOT_FOUND", "message": "missing"},
            headers={"X-Request-ID": ""},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="illegal X-Request-ID"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_error_body_request_id_mismatch_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "OPERATION_NOT_FOUND",
                "message": "missing",
                "request_id": "body-id",
            },
            headers={"X-Request-ID": "header-id"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="does not match"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_http_status_contract_mismatch_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"operation_id": str(OP_ID)},
            headers={"X-Request-ID": "req-1"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="unexpected HTTP status"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_missing_error_body_request_id_is_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"code": "OPERATION_NOT_FOUND", "message": "missing"},
            headers={"X-Request-ID": "req-1"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError, match="missing error body request_id"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)


@pytest.mark.asyncio
async def test_request_id_preserves_opaque_whitespace() -> None:
    request_id = " abc "

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "OPERATION_NOT_FOUND",
                "message": "missing",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryClientError) as exc_info:
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert exc_info.value.error.request_id == request_id


@pytest.mark.asyncio
async def test_valid_http_error_preserves_status_and_simple_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "code": "OPERATION_NOT_FOUND",
                "message": "missing",
                "details": {"operation_id": str(OP_ID)},
                "request_id": "req-404",
            },
            headers={"X-Request-ID": "req-404"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryClientError) as exc_info:
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert exc_info.value.status_code == 404
    assert exc_info.value.error.code == "OPERATION_NOT_FOUND"
    assert exc_info.value.error.request_id == "req-404"
    assert exc_info.value.error.details == {"operation_id": str(OP_ID)}


@pytest.mark.asyncio
async def test_malformed_success_body_includes_request_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
            headers={"X-Request-ID": "req-malformed", "Content-Type": "application/json"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError) as exc_info:
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert exc_info.value.request_id == "req-malformed"


@pytest.mark.asyncio
async def test_success_body_wrong_shape_includes_request_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"unexpected": True},
            headers={"X-Request-ID": "req-shape"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RepositoryProtocolError) as exc_info:
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert exc_info.value.request_id == "req-shape"


@pytest.mark.asyncio
async def test_oversized_json_body_raises_protocol_error_and_closes_transport() -> None:
    from gateway_repository_client.protocol import MAX_WIRE_JSON_BYTES

    closed = {"count": 0}

    class ChunkedTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            del request

            class ChunkedBody(httpx.AsyncByteStream):
                async def __aiter__(self) -> AsyncIterator[bytes]:
                    chunk = b"x" * 4096
                    for _ in range((MAX_WIRE_JSON_BYTES // 4096) + 2):
                        yield chunk

                async def aclose(self) -> None:
                    closed["count"] += 1

            return httpx.Response(
                200,
                headers={"X-Request-ID": "req-big", "Content-Type": "application/json"},
                stream=ChunkedBody(),
            )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=ChunkedTransport(),
    )
    with pytest.raises(RepositoryProtocolError, match="exceeds") as exc_info:
        await client.resolve_versioned_ref(repository_id=REPO_ID)

    assert exc_info.value.request_id == "req-big"
    assert closed["count"] >= 1
