"""ASGI streaming harness for versioned read integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
from fastapi import FastAPI

from gateway_repository_contracts import VERSIONED_READ_ARROW_MEDIA_TYPE


def create_async_streaming_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
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
