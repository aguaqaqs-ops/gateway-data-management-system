"""ASGI streaming harness for versioned read integration tests."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import httpx2 as httpx
from fastapi import FastAPI
from httpx2._models import Request, Response
from httpx2._transports.base import AsyncBaseTransport
from httpx2._types import AsyncByteStream

from gateway_repository_contracts import VERSIONED_READ_ARROW_MEDIA_TYPE

_ASGIApp = Callable[
    [
        dict[str, Any],
        Callable[[], Awaitable[dict[str, Any]]],
        Callable[[dict[str, Any]], Awaitable[None]],
    ],
    Awaitable[None],
]
_StreamItem = bytes | None | BaseException


class _DuplexResponseStream(AsyncByteStream):
    def __init__(
        self,
        *,
        chunk_queue: asyncio.Queue[_StreamItem],
        disconnect_event: asyncio.Event,
        app_task: asyncio.Task[None],
        raise_app_exceptions: bool,
        cleanup_barrier: threading.Event | None = None,
    ) -> None:
        self._chunk_queue = chunk_queue
        self._disconnect_event = disconnect_event
        self._app_task = app_task
        self._raise_app_exceptions = raise_app_exceptions
        self._cleanup_barrier = cleanup_barrier
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            item = await self._chunk_queue.get()
            if isinstance(item, BaseException):
                await self._retrieve_app_exception()
                if self._raise_app_exceptions:
                    raise item
                raise httpx.RemoteProtocolError("ASGI streaming app failed") from item
            if item is None:
                await self._retrieve_app_exception()
                break
            yield item
            await self._raise_if_app_failed()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._cleanup_barrier is not None:
            self._cleanup_barrier.set()
        self._disconnect_event.set()
        await self._retrieve_app_exception()

    async def _retrieve_app_exception(self) -> None:
        if not self._app_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._app_task), timeout=10.0)
            except TimeoutError:
                try:
                    await asyncio.wait_for(asyncio.shield(self._app_task), timeout=30.0)
                except TimeoutError as exc:
                    raise RuntimeError(
                        "ASGI app did not finish within bounded cleanup observation window"
                    ) from exc
            except asyncio.CancelledError:
                await asyncio.shield(self._app_task)
                raise
        if self._app_task.cancelled():
            return
        _ = self._app_task.exception()

    async def _raise_if_app_failed(self) -> None:
        if not self._raise_app_exceptions or not self._app_task.done():
            return
        if self._app_task.cancelled():
            return
        exc = self._app_task.exception()
        if exc is not None:
            raise exc


class DuplexStreamingASGITransport(AsyncBaseTransport):
    """Return the HTTP response as soon as headers are sent and stream body chunks."""

    def __init__(
        self,
        app: _ASGIApp,
        *,
        raise_app_exceptions: bool = True,
        root_path: str = "",
        client: tuple[str, int] = ("127.0.0.1", 123),
        cleanup_barrier: threading.Event | None = None,
    ) -> None:
        self.app = app
        self.raise_app_exceptions = raise_app_exceptions
        self.root_path = root_path
        self.client = client
        self.cleanup_barrier = cleanup_barrier

    async def handle_async_request(self, request: Request) -> Response:
        assert isinstance(request.stream, AsyncByteStream)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(key.lower(), value) for (key, value) in request.headers.raw],
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path.split(b"?")[0],
            "query_string": request.url.query,
            "server": (request.url.host, request.url.port),
            "client": self.client,
            "root_path": self.root_path,
        }

        request_body_chunks = request.stream.__aiter__()
        request_complete = False
        disconnect_event = asyncio.Event()
        chunk_queue: asyncio.Queue[_StreamItem] = asyncio.Queue()
        response_ready = asyncio.Event()
        terminal_published = False
        status_code: int | None = None
        response_headers: list[tuple[bytes, bytes]] | None = None

        async def publish_terminal(item: _StreamItem) -> None:
            nonlocal terminal_published
            if terminal_published:
                return
            terminal_published = True
            await chunk_queue.put(item)

        async def receive() -> dict[str, Any]:
            nonlocal request_complete

            if disconnect_event.is_set():
                return {"type": "http.disconnect"}

            if request_complete:
                while not disconnect_event.is_set():
                    await asyncio.sleep(0.01)
                return {"type": "http.disconnect"}

            try:
                body = await request_body_chunks.__anext__()
            except StopAsyncIteration:
                request_complete = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.request", "body": body, "more_body": True}

        async def send(message: dict[str, Any]) -> None:
            nonlocal status_code, response_headers

            if message["type"] == "http.response.start":
                if response_ready.is_set():
                    raise RuntimeError("duplicate http.response.start")
                status_code = message["status"]
                response_headers = message.get("headers", [])
                response_ready.set()
                return

            if message["type"] == "http.response.body":
                body = message.get("body", b"")
                more_body = message.get("more_body", False)
                if body and request.method != "HEAD":
                    await chunk_queue.put(body)
                if not more_body:
                    await publish_terminal(None)
                return

            raise RuntimeError(f"unsupported ASGI message type: {message['type']!r}")

        async def run_app() -> None:
            try:
                await self.app(scope, receive, send)
            except BaseException as exc:
                await publish_terminal(exc)
                raise
            finally:
                if not terminal_published:
                    await publish_terminal(None)

        app_task = asyncio.create_task(run_app())
        try:
            await asyncio.wait_for(response_ready.wait(), timeout=30.0)
        except TimeoutError:
            app_task.cancel()
            try:
                await app_task
            except asyncio.CancelledError:
                pass
            raise

        assert status_code is not None
        assert response_headers is not None
        stream = _DuplexResponseStream(
            chunk_queue=chunk_queue,
            disconnect_event=disconnect_event,
            app_task=app_task,
            raise_app_exceptions=self.raise_app_exceptions,
            cleanup_barrier=self.cleanup_barrier,
        )
        return Response(status_code, headers=response_headers, stream=stream)


def create_async_streaming_client(
    app: FastAPI,
) -> httpx.AsyncClient:
    transport = DuplexStreamingASGITransport(
        app=cast(_ASGIApp, app),
        raise_app_exceptions=False,
    )
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def stream_rows(
    client: httpx.AsyncClient,
    *,
    path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.send(
        client.build_request("GET", path, params=params, headers=headers),
        stream=True,
    )


async def read_first_chunk(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        break
    return b"".join(chunks)


async def read_all_chunks(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
    return b"".join(chunks)


async def stream_until_first_chunk_then_close(
    client: httpx.AsyncClient,
    *,
    path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    on_first_chunk: Callable[[bytes], None] | None = None,
) -> tuple[int, bytes | None, BaseException | None]:
    response: httpx.Response | None = None
    error: BaseException | None = None
    first_chunk: bytes | None = None
    status_code = 0
    try:
        response = await stream_rows(client, path=path, params=params, headers=headers)
        status_code = response.status_code
        assert response.headers.get("content-type", "").startswith(VERSIONED_READ_ARROW_MEDIA_TYPE)
        first_chunk = await read_first_chunk(response)
        if on_first_chunk is not None:
            on_first_chunk(first_chunk)
    except BaseException as exc:
        error = exc
    finally:
        if response is not None:
            await response.aclose()
    return status_code, first_chunk, error


async def read_stream_until_error(
    client: httpx.AsyncClient,
    *,
    path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, BaseException | None]:
    response: httpx.Response | None = None
    error: BaseException | None = None
    chunks: list[bytes] = []
    status_code = 0
    try:
        response = await stream_rows(client, path=path, params=params, headers=headers)
        status_code = response.status_code
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
    except BaseException as exc:
        error = exc
    finally:
        if response is not None:
            await response.aclose()
    return status_code, b"".join(chunks), error


async def collect_stream_error(
    client: httpx.AsyncClient,
    *,
    path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    after_first_chunk: Callable[[], None] | None = None,
) -> tuple[int, bytes | None, BaseException | None]:
    response: httpx.Response | None = None
    error: BaseException | None = None
    first_chunk: bytes | None = None
    status_code = 0
    try:
        response = await stream_rows(client, path=path, params=params, headers=headers)
        status_code = response.status_code
        async for chunk in response.aiter_bytes():
            if first_chunk is None:
                first_chunk = chunk
                if after_first_chunk is not None:
                    after_first_chunk()
                continue
            _ = chunk
    except BaseException as exc:
        error = exc
    finally:
        if response is not None:
            await response.aclose()
    return status_code, first_chunk, error


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


async def drain_stream_with_barrier(
    client: httpx.AsyncClient,
    *,
    path: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    ready: asyncio.Event,
    release: asyncio.Event,
) -> tuple[int, BaseException | None]:
    response: httpx.Response | None = None
    error: BaseException | None = None
    status_code = 0
    try:
        response = await stream_rows(client, path=path, params=params, headers=headers)
        status_code = response.status_code
        ready.set()
        await release.wait()
        async for _chunk in response.aiter_bytes():
            pass
    except BaseException as exc:
        error = exc
    finally:
        if response is not None:
            await response.aclose()
    return status_code, error
