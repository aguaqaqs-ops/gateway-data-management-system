"""Unit tests for HTTP middleware."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route
from starlette.types import Message, Scope

from gateway_repository_service.http.middleware import RequestIdMiddleware


async def _failing_stream(_request: object) -> StreamingResponse:
    async def body() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("midstream")

    return StreamingResponse(body(), media_type="application/octet-stream")


def _http_scope() -> Scope:
    return {
        "type": "http",
        "asgi": {"spec_version": "2.4", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {},
    }


async def _empty_receive() -> Message:
    return {"type": "http.disconnect"}


@pytest.mark.unit
def test_request_id_middleware_preserves_streaming_abort() -> None:
    inner = Starlette(
        routes=[
            Route("/stream", _failing_stream),
        ],
    )
    app = RequestIdMiddleware(inner)
    sent: list[Message] = []

    async def send_recorder(message: Message) -> None:
        sent.append(message)

    async def exercise() -> None:
        with pytest.raises(RuntimeError, match="midstream"):
            await app(_http_scope(), _empty_receive, send_recorder)

    asyncio.run(exercise())

    start_messages = [message for message in sent if message["type"] == "http.response.start"]
    assert len(start_messages) == 1
    start_headers = dict(start_messages[0].get("headers", []))
    assert start_headers[b"x-request-id"]

    body_messages = [message for message in sent if message["type"] == "http.response.body"]
    assert any(message.get("body") for message in body_messages)
    assert not any(
        message.get("type") == "http.response.body" and not message.get("more_body", False)
        for message in sent
    )
