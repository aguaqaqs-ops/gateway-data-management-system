"""Unit tests for HTTP middleware."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx2 as httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route

from gateway_repository_service.http.middleware import RequestIdMiddleware

HTTP_CHUNKED_TERMINATOR = b"0\r\n\r\n"


async def _failing_stream(_request: object) -> StreamingResponse:
    async def body() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("midstream")

    return StreamingResponse(body(), media_type="application/octet-stream")


@pytest.mark.unit
def test_request_id_middleware_preserves_streaming_abort() -> None:
    app = RequestIdMiddleware(
        Starlette(
            routes=[
                Route("/stream", _failing_stream),
            ],
        ),
    )

    async def exercise() -> tuple[bytes, BaseException | None]:
        transport_error: BaseException | None = None
        body = b""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        ) as client:
            async with client.stream("GET", "http://testserver/stream") as response:
                assert response.status_code == 200
                assert response.headers.get("X-Request-ID")
                try:
                    async for chunk in response.aiter_bytes():
                        body += chunk
                except (httpx.RemoteProtocolError, httpx.ReadError, RuntimeError) as exc:
                    transport_error = exc
        return body, transport_error

    body, transport_error = asyncio.run(exercise())
    assert body == b"partial"
    assert transport_error is None or isinstance(
        transport_error,
        (httpx.RemoteProtocolError, httpx.ReadError, RuntimeError),
    )
