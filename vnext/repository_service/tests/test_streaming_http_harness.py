"""Unit tests for the duplex ASGI streaming harness."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

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


async def _hanging_midstream_app(
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
    await asyncio.Event().wait()


def test_duplex_transport_raises_when_app_hangs_past_bounded_cleanup_window() -> None:
    original_wait_for = asyncio.wait_for
    long_waits = 0

    async def fast_timeout_wait_for(awaitable: Any, timeout: float) -> Any:
        nonlocal long_waits
        if timeout >= 10.0:
            long_waits += 1
            if long_waits > 1:
                raise TimeoutError()
        return await original_wait_for(awaitable, timeout)

    async def run() -> None:
        transport = DuplexStreamingASGITransport(_hanging_midstream_app, raise_app_exceptions=False)
        request = httpx.Request("GET", "http://testserver/stream")
        response = await transport.handle_async_request(request)
        async for chunk in response.aiter_bytes():
            if chunk:
                break
        with pytest.raises(RuntimeError, match="bounded cleanup observation window"):
            await response.aclose()

    with patch("support.streaming_http_harness.asyncio.wait_for", side_effect=fast_timeout_wait_for):
        asyncio.run(run())
