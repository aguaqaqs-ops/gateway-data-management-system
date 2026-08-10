"""Unit tests for the duplex ASGI streaming harness."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx2 as httpx
import pytest

from support.streaming_http_harness import DuplexStreamingASGITransport

pytestmark = pytest.mark.unit


async def _failing_midstream_app(
    scope: dict[str, Any],
    receive: Any,
    send: Any,
) -> None:
    del scope, receive
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/octet-stream")],
        }
    )
    await send({"type": "http.response.body", "body": b"first", "more_body": True})
    raise RuntimeError("midstream")


async def _exercise_failing_transport(*, raise_app_exceptions: bool) -> tuple[list[bytes], BaseException | None]:
    transport = DuplexStreamingASGITransport(_failing_midstream_app, raise_app_exceptions=raise_app_exceptions)
    request = httpx.Request("GET", "http://testserver/stream")
    response = await transport.handle_async_request(request)
    chunks: list[bytes] = []
    error: BaseException | None = None
    try:
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
    except BaseException as exc:
        error = exc
    await response.aclose()
    return chunks, error


def test_duplex_transport_surfaces_post_header_app_failure_without_hanging() -> None:
    chunks, error = asyncio.run(_exercise_failing_transport(raise_app_exceptions=False))
    assert chunks == [b"first"]
    assert error is not None
    assert not isinstance(error, TimeoutError)


def test_duplex_transport_reraises_post_header_app_failure_when_configured() -> None:
    async def run() -> None:
        transport = DuplexStreamingASGITransport(_failing_midstream_app, raise_app_exceptions=True)
        request = httpx.Request("GET", "http://testserver/stream")
        response = await transport.handle_async_request(request)
        with pytest.raises(RuntimeError, match="midstream"):
            async for _chunk in response.aiter_bytes():
                pass
        await response.aclose()

    asyncio.run(run())
