"""Unit tests for bounded empty-body request guards."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest
from starlette.requests import Request

from gateway_repository_service.http.body_guard import require_empty_body
from gateway_repository_service.http.errors import ServiceError

ReceiveCallable = Callable[[], Awaitable[dict[str, object]]]


def _request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    receive: ReceiveCallable | None = None,
) -> Request:
    scope: dict[str, object] = {
        "type": "http",
        "method": "POST",
        "path": "/v1/repositories",
        "headers": headers or [],
    }

    async def default_receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    return Request(scope, receive or default_receive)


def test_rejects_positive_content_length_without_streaming() -> None:
    receive_calls = 0

    async def receive() -> dict[str, object]:
        nonlocal receive_calls
        receive_calls += 1
        return {"type": "http.request", "body": b"should-not-read", "more_body": False}

    request = _request(headers=[(b"content-length", b"1048576")], receive=receive)

    with pytest.raises(ServiceError) as exc_info:
        asyncio.run(require_empty_body(request))

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "REQUEST_VALIDATION_FAILED"
    assert receive_calls == 0


def test_allows_zero_content_length() -> None:
    request = _request(headers=[(b"content-length", b"0")])

    asyncio.run(require_empty_body(request))


def test_rejects_first_non_empty_chunk() -> None:
    receive_calls = 0

    async def receive() -> dict[str, object]:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {"type": "http.request", "body": b"abc", "more_body": True}
        raise AssertionError("must not read beyond first non-empty chunk")

    request = _request(receive=receive)

    with pytest.raises(ServiceError) as exc_info:
        asyncio.run(require_empty_body(request))

    assert exc_info.value.status_code == 422
    assert receive_calls == 1


def test_allows_empty_chunks_only() -> None:
    receive_calls = 0

    async def receive() -> dict[str, object]:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 1:
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    request = _request(receive=receive)

    asyncio.run(require_empty_body(request))
    assert receive_calls == 1
