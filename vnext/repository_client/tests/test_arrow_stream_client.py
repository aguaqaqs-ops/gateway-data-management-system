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
    RepositoryClientError,
    RepositoryProtocolError,
    RepositoryStreamError,
)
from gateway_repository_client.arrow_stream import _close_pair
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
    assert len(closed_responses) >= 2


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


@pytest.mark.asyncio
async def test_concurrent_aclose_during_pre_byte_retry_does_not_reopen_transport() -> None:
    attempts = {"count": 0}
    sleeper_entered = asyncio.Event()
    release_sleeper = asyncio.Event()

    async def sleeper(_seconds: float) -> None:
        sleeper_entered.set()
        await release_sleeper.wait()

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        attempts["count"] += 1
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=_PreByteFailingStream(fail=True),
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt, sleeper=sleeper)
    async with stream:

        async def consume() -> None:
            async for _chunk in stream.aiter_bytes():
                return None

        read_task = asyncio.create_task(consume())
        await sleeper_entered.wait()
        await stream.aclose()
        release_sleeper.set()
        with pytest.raises(RuntimeError, match="closed"):
            await read_task

    assert attempts["count"] == 1
    assert stream._client is None
    assert stream._response is None


@pytest.mark.asyncio
async def test_close_pair_raises_when_both_resources_fail_to_close() -> None:
    class FailingClient:
        async def aclose(self) -> None:
            raise OSError("client close failed")

    class FailingResponse:
        async def aclose(self) -> None:
            raise OSError("response close failed")

    with pytest.raises(ExceptionGroup):
        await _close_pair(FailingClient(), FailingResponse())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_concurrent_aclose_during_in_flight_open_closes_transport() -> None:
    open_started = asyncio.Event()
    release_open = asyncio.Event()
    client_closed = {"value": False}
    response_closed = {"value": False}

    class BlockingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"payload"

        async def aclose(self) -> None:
            response_closed["value"] = True

    class BlockingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            open_started.set()
            await release_open.wait()
            return httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=BlockingStream(),
            )

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(
            base_url="http://repository.test",
            transport=BlockingTransport(),
        )
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        original_client_close = client.aclose

        async def track_client_close() -> None:
            client_closed["value"] = True
            await original_client_close()

        client.aclose = track_client_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)

    async def enter_stream() -> None:
        async with stream:
            pass

    enter_task = asyncio.create_task(enter_stream())
    await open_started.wait()
    await stream.aclose()
    release_open.set()

    with pytest.raises(RuntimeError, match="closed"):
        await enter_task

    assert client_closed["value"] is True
    assert response_closed["value"] is True
    assert stream._client is None
    assert stream._response is None


@pytest.mark.asyncio
async def test_wrong_media_type_preserves_protocol_error_when_close_fails() -> None:
    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={
                    "X-Request-ID": "req-bad",
                    "Content-Type": "application/json",
                },
                content=b"{}",
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)

        async def failing_close() -> None:
            raise OSError("response close failed")

        response.aclose = failing_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)
    with pytest.raises(RepositoryProtocolError, match="Arrow media type") as exc_info:
        async with stream:
            pass

    assert exc_info.value.request_id == "req-bad"
    assert any("cleanup close failed" in note for note in exc_info.value.__notes__)


@pytest.mark.asyncio
async def test_retryable_503_preserves_error_when_close_fails() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        attempts["count"] += 1
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                503,
                request=request,
                json={"code": "SERVICE_NOT_READY", "message": "not ready", "request_id": "req-503"},
                headers={"X-Request-ID": "req-503"},
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)

        async def failing_close() -> None:
            raise OSError("response close failed")

        response.aclose = failing_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(
        open_attempt=open_attempt,
        max_attempts=2,
        sleeper=sleeper,
    )
    with pytest.raises(RepositoryClientError) as exc_info:
        async with stream:
            pass

    assert exc_info.value.status_code == 503
    assert attempts["count"] == 2
    assert any("cleanup close failed" in note for note in exc_info.value.__notes__)


@pytest.mark.asyncio
async def test_streaming_503_eof_close_failure_retries_and_preserves_typed_error() -> None:
    import json

    attempts = {"count": 0}
    response_closes = {"count": 0}
    client_closes = {"count": 0}
    error_body = json.dumps(
        {
            "code": "SERVICE_NOT_READY",
            "message": "not ready",
            "request_id": "req-503",
        }
    ).encode()

    class EofCloseFailingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield error_body

        async def aclose(self) -> None:
            response_closes["count"] += 1
            raise OSError("EOF close failed")

    class StreamingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                503,
                request=request,
                headers={
                    "X-Request-ID": "req-503",
                    "Content-Length": str(len(error_body)),
                },
                stream=EofCloseFailingStream(),
            )

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(
            base_url="http://repository.test",
            transport=StreamingTransport(),
        )
        original_client_close = client.aclose

        async def track_client_close() -> None:
            client_closes["count"] += 1
            await original_client_close()

        client.aclose = track_client_close  # type: ignore[method-assign]
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    async def sleeper(_seconds: float) -> None:
        return None

    stream = ArrowIpcByteStream(open_attempt=open_attempt, max_attempts=2, sleeper=sleeper)
    with pytest.raises(RepositoryClientError) as exc_info:
        async with stream:
            pass

    assert attempts["count"] == 2
    assert exc_info.value.status_code == 503
    assert exc_info.value.error is not None
    assert exc_info.value.error.code == "SERVICE_NOT_READY"
    assert exc_info.value.error.request_id == "req-503"
    notes = getattr(exc_info.value, "__notes__", ())
    assert any("cleanup close failed" in note for note in notes)
    assert response_closes["count"] >= 1
    assert client_closes["count"] >= 1


@pytest.mark.asyncio
async def test_streaming_503_iterator_oserror_with_aclose_failure_preserves_both_notes() -> (
    None
):
    import json

    attempts = {"count": 0}
    response_closes = {"count": 0}
    error_body = json.dumps(
        {
            "code": "SERVICE_NOT_READY",
            "message": "not ready",
            "request_id": "req-503",
        }
    ).encode()

    class IteratorOSErrorStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield error_body
            raise OSError("arrow iterator failed after complete error body")
            yield b""  # pragma: no cover

        async def aclose(self) -> None:
            response_closes["count"] += 1
            raise OSError("aclose sentinel")

    class StreamingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                503,
                request=request,
                headers={
                    "X-Request-ID": "req-503",
                    "Content-Length": str(len(error_body)),
                },
                stream=IteratorOSErrorStream(),
            )

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(
            base_url="http://repository.test",
            transport=StreamingTransport(),
        )
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    async def sleeper(_seconds: float) -> None:
        return None

    stream = ArrowIpcByteStream(open_attempt=open_attempt, max_attempts=2, sleeper=sleeper)
    with pytest.raises(RepositoryClientError) as exc_info:
        async with stream:
            pass

    assert attempts["count"] == 2
    assert exc_info.value.status_code == 503
    notes = getattr(exc_info.value, "__notes__", ())
    assert any("arrow iterator failed after complete error body" in note for note in notes)
    assert any("aclose sentinel" in note for note in notes)
    assert response_closes["count"] == 2


@pytest.mark.asyncio
async def test_streaming_502_eof_close_failure_retries() -> None:
    import json

    attempts = {"count": 0}
    error_body = json.dumps(
        {
            "code": "SERVICE_NOT_READY",
            "message": "bad gateway",
            "request_id": "req-502",
        }
    ).encode()

    class EofCloseFailingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield error_body

        async def aclose(self) -> None:
            raise OSError("EOF close failed")

    class StreamingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                502,
                request=request,
                headers={
                    "X-Request-ID": "req-502",
                    "Content-Length": str(len(error_body)),
                },
                stream=EofCloseFailingStream(),
            )

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(
            base_url="http://repository.test",
            transport=StreamingTransport(),
        )
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    async def sleeper(_seconds: float) -> None:
        return None

    stream = ArrowIpcByteStream(
        open_attempt=open_attempt,
        max_attempts=2,
        sleeper=sleeper,
    )
    with pytest.raises(RepositoryClientError) as exc_info:
        async with stream:
            pass

    assert attempts["count"] == 2
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_streaming_502_iterator_oserror_with_aclose_failure_preserves_both_notes() -> (
    None
):
    import json

    attempts = {"count": 0}
    response_closes = {"count": 0}
    error_body = json.dumps(
        {
            "code": "SERVICE_NOT_READY",
            "message": "bad gateway",
            "request_id": "req-502",
        }
    ).encode()

    class IteratorOSErrorStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield error_body
            raise OSError("arrow iterator failed after complete error body")
            yield b""  # pragma: no cover

        async def aclose(self) -> None:
            response_closes["count"] += 1
            raise OSError("aclose sentinel")

    class StreamingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                502,
                request=request,
                headers={
                    "X-Request-ID": "req-502",
                    "Content-Length": str(len(error_body)),
                },
                stream=IteratorOSErrorStream(),
            )

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(
            base_url="http://repository.test",
            transport=StreamingTransport(),
        )
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    async def sleeper(_seconds: float) -> None:
        return None

    stream = ArrowIpcByteStream(open_attempt=open_attempt, max_attempts=2, sleeper=sleeper)
    with pytest.raises(RepositoryClientError) as exc_info:
        async with stream:
            pass

    assert attempts["count"] == 2
    assert exc_info.value.status_code == 502
    notes = getattr(exc_info.value, "__notes__", ())
    assert any("arrow iterator failed after complete error body" in note for note in notes)
    assert any("aclose sentinel" in note for note in notes)
    assert response_closes["count"] == 2


@pytest.mark.asyncio
async def test_concurrent_aclose_during_iterator_discard_closes_once() -> None:
    response_closes = {"count": 0}
    client_closes = {"count": 0}
    discard_started = asyncio.Event()
    release_discard = asyncio.Event()

    class SlowClosingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            raise httpx.ReadError("pre-byte failure")
            yield b""  # pragma: no cover

        async def aclose(self) -> None:
            discard_started.set()
            await release_discard.wait()
            response_closes["count"] += 1

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=SlowClosingStream(),
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        original_client_close = client.aclose

        async def track_client_close() -> None:
            client_closes["count"] += 1
            await original_client_close()

        client.aclose = track_client_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt, max_attempts=1)

    async def consume() -> None:
        async for _chunk in stream.aiter_bytes():
            return None

    async with stream:
        read_task = asyncio.create_task(consume())
        await discard_started.wait()
        await stream.aclose()
        release_discard.set()
        with pytest.raises((RepositoryStreamError, RuntimeError)):
            await read_task

    assert response_closes["count"] == 1
    assert client_closes["count"] == 1


@pytest.mark.asyncio
async def test_second_byte_iterator_rejected_without_extra_request() -> None:
    attempts = {"count": 0}
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class PausingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            first_started.set()
            await release_first.wait()
            yield b"first"

        async def aclose(self) -> None:
            return None

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        attempts["count"] += 1
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=PausingStream(),
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)

    async def collect_first() -> list[bytes]:
        return [chunk async for chunk in stream.aiter_bytes()]

    async with stream:
        first_task = asyncio.create_task(collect_first())
        await first_started.wait()
        with pytest.raises(RuntimeError, match="already active"):
            async for _chunk in stream.aiter_bytes():
                pass
        release_first.set()
        chunks = await first_task

    assert chunks == [b"first"]
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_aclose_raises_when_response_close_fails_without_consuming() -> None:
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

        async def failing_close() -> None:
            raise OSError("arrow close failed")

        response.aclose = failing_close  # type: ignore[method-assign]
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)
    with pytest.raises(OSError, match="arrow close failed"):
        async with stream:
            pass


@pytest.mark.asyncio
async def test_context_body_error_preserves_primary_with_cleanup_note() -> None:
    class FailingAfterByteStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first"
            raise httpx.ReadError("midstream failure")

        async def aclose(self) -> None:
            raise OSError("cleanup close failed")

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=FailingAfterByteStream(),
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)
    with pytest.raises(RepositoryStreamError, match="after bytes were exposed") as exc_info:
        async with stream:
            async for _chunk in stream.aiter_bytes():
                pass

    notes = getattr(exc_info.value, "__notes__", ())
    assert any("cleanup close failed" in note for note in notes)


@pytest.mark.asyncio
async def test_post_byte_eof_close_failure_raises_stream_error() -> None:
    attempts = {"count": 0}

    class EofCloseAfterByteStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"first"
            raise OSError("arrow close failed")

        async def aclose(self) -> None:
            raise OSError("arrow close failed")

    async def open_attempt() -> tuple[httpx.AsyncClient, httpx.Response]:
        attempts["count"] += 1
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers=ARROW_HEADERS,
                stream=EofCloseAfterByteStream(),
            )
        )
        client = httpx.AsyncClient(base_url="http://repository.test", transport=transport)
        request = client.build_request("GET", "/rows")
        response = await client.send(request, stream=True)
        return client, response

    stream = ArrowIpcByteStream(open_attempt=open_attempt)
    with pytest.raises(RepositoryStreamError, match="after bytes were exposed") as exc_info:
        async with stream:
            async for _chunk in stream.aiter_bytes():
                pass

    assert exc_info.value.request_id == "req-arrow"
    assert attempts["count"] == 1
