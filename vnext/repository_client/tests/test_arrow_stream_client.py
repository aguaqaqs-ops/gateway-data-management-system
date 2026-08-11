"""ArrowIpcByteStream ownership, retry, and media-type tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from gateway_repository_client import (
    ArrowIpcByteStream,
    RepositoryClient,
    RepositoryProtocolError,
    RepositoryStreamError,
)
from gateway_repository_contracts import VERSIONED_READ_ARROW_MEDIA_TYPE

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
COMMIT_ID = "commit-c1"
ARROW_HEADERS = {
    "X-Request-ID": "req-arrow",
    "Content-Type": VERSIONED_READ_ARROW_MEDIA_TYPE,
}


@pytest.mark.asyncio
async def test_stream_retries_before_first_byte_on_503() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            200,
            headers=ARROW_HEADERS,
            content=b"arrow-bytes",
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]

    assert attempts["count"] == 2
    assert b"".join(chunks) == b"arrow-bytes"
    assert stream.request_id == "req-arrow"
    assert stream.media_type == VERSIONED_READ_ARROW_MEDIA_TYPE


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_first_byte_exposed() -> None:
    attempts = {"count": 0}

    class FailingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first"
            raise httpx.ReadError("midstream failure")

        async def aclose(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            request=request,
            headers={
                "X-Request-ID": f"req-{attempts['count']}",
                "Content-Type": VERSIONED_READ_ARROW_MEDIA_TYPE,
            },
            stream=FailingStream(),
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    with pytest.raises(RepositoryStreamError):
        async with stream:
            async for _chunk in stream.aiter_bytes():
                pass

    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_stream_context_exit_and_repeated_aclose_release_resources() -> None:
    closed: list[str] = []

    class TrackingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            response = httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                content=b"payload",
            )
            original = response.aclose

            async def tracked_aclose() -> None:
                closed.append("response")
                await original()

            response.aclose = tracked_aclose  # type: ignore[method-assign]
            return response

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=TrackingTransport(),
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        assert [chunk async for chunk in stream.aiter_bytes()] == [b"payload"]

    assert "response" in closed
    await stream.aclose()
    await stream.aclose()
    assert closed.count("response") == 1


@pytest.mark.asyncio
async def test_stream_early_context_exit_closes_without_full_consume() -> None:
    closed = {"response": 0}

    class TrackingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            response = httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                content=b"abcdefghijklmnopqrstuvwxyz",
            )
            original = response.aclose

            async def tracked_aclose() -> None:
                closed["response"] += 1
                await original()

            response.aclose = tracked_aclose  # type: ignore[method-assign]
            return response

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=TrackingTransport(),
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        pass

    assert closed["response"] == 1


@pytest.mark.asyncio
async def test_stream_retry_closes_failed_attempt_resources() -> None:
    closed_clients: list[int] = []
    closed_responses: list[int] = []
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        attempts["count"] += 1
        transport = httpx.MockTransport(
            lambda _request: (
                httpx.Response(
                    503,
                    json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                    headers={"X-Request-ID": "req-fail"},
                )
                if attempts["count"] == 1
                else httpx.Response(
                    200,
                    headers=ARROW_HEADERS,
                    content=b"ok",
                )
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        client_id = id(client)
        response_id = id(response)
        original_client_close = client.aclose
        original_response_close = response.aclose

        async def track_client_close() -> None:
            closed_clients.append(client_id)
            await original_client_close()

        async def track_response_close() -> None:
            closed_responses.append(response_id)
            await original_response_close()

        client.aclose = track_client_close  # type: ignore[method-assign]
        response.aclose = track_response_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt, sleeper=sleeper)
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]

    assert chunks == [b"ok"]
    assert attempts["count"] == 2
    assert len(closed_clients) == 2
    assert len(closed_responses) == 2


@pytest.mark.asyncio
async def test_stream_wrong_media_type_raises_protocol_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "X-Request-ID": "req-bad",
                "Content-Type": "application/json",
            },
            content=b"{}",
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    with pytest.raises(RepositoryProtocolError, match="Arrow media type"):
        async with stream:
            pass


class _PreByteFailingStream(httpx.AsyncByteStream):
    def __init__(self, *, fail: bool) -> None:
        self._fail = fail

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._fail:
            raise httpx.ReadError("pre-byte failure")
        yield b"payload"

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_stream_pre_byte_read_error_can_retry_once() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            request=request,
            headers=ARROW_HEADERS,
            stream=_PreByteFailingStream(fail=attempts["count"] == 1),
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]

    assert attempts["count"] == 2
    assert chunks == [b"payload"]


@pytest.mark.asyncio
async def test_stream_pre_byte_read_error_shares_attempt_budget() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            request=request,
            headers={
                "X-Request-ID": f"req-{attempts['count']}",
                "Content-Type": VERSIONED_READ_ARROW_MEDIA_TYPE,
            },
            stream=_PreByteFailingStream(fail=True),
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    with pytest.raises(RepositoryStreamError, match="before bytes were exposed"):
        async with stream:
            async for _chunk in stream.aiter_bytes():
                pass

    assert attempts["count"] == 3


class _ErrorBodyReadFailureStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise httpx.ReadError("error body read failed")
        yield b""  # pragma: no cover

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_stream_retries_error_body_read_on_503() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                503,
                request=request,
                headers={"X-Request-ID": f"req-{attempts['count']}"},
                stream=_ErrorBodyReadFailureStream(),
            )
        return httpx.Response(
            200,
            headers=ARROW_HEADERS,
            content=b"recovered",
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]

    assert attempts["count"] == 3
    assert chunks == [b"recovered"]


@pytest.mark.asyncio
async def test_stream_pre_byte_read_error_backoff_increases_delay() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            request=request,
            headers=ARROW_HEADERS,
            stream=_PreByteFailingStream(fail=attempts["count"] == 1),
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
        table_name="items",
    )
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]

    assert chunks == [b"payload"]
    assert sleeps == [pytest.approx(0.05)]


@pytest.mark.asyncio
async def test_close_pair_closes_client_when_response_cancelled() -> None:
    closed: list[str] = []

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                content=b"payload",
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        original_client_close = client.aclose

        async def cancel_response_close() -> None:
            closed.append("response")
            raise asyncio.CancelledError()

        async def track_client_close() -> None:
            closed.append("client")
            await original_client_close()

        client.aclose = track_client_close  # type: ignore[method-assign]
        response.aclose = cancel_response_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)
    with pytest.raises(asyncio.CancelledError):
        async with stream:
            pass
    assert closed == ["response", "client"]
