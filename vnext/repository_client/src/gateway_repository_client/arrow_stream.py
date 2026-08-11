"""Owned raw Arrow IPC byte stream for versioned table row reads."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Self

import httpx

from gateway_repository_client.errors import (
    RepositoryClientError,
    RepositoryProtocolError,
    RepositoryStreamError,
)
from gateway_repository_client.protocol import (
    raise_for_error_response,
    require_arrow_media_type,
    require_request_id,
)
from gateway_repository_client.retry import (
    DEFAULT_BASE_DELAY_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    RETRYABLE_STATUS_CODES,
    Sleeper,
)

OpenAttempt = Callable[[], Awaitable[tuple[httpx.AsyncClient, httpx.Response]]]


class ArrowIpcByteStream:
    """Async context-managed raw Arrow IPC byte stream.

    Owns the HTTP response and the AsyncClient created for this stream. Production
    code does not parse Arrow and does not depend on PyArrow.
    """

    def __init__(
        self,
        *,
        open_attempt: OpenAttempt,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._open_attempt = open_attempt
        self._max_attempts = max_attempts
        self._base_delay_seconds = base_delay_seconds
        self._sleeper = sleeper
        self._client: httpx.AsyncClient | None = None
        self._response: httpx.Response | None = None
        self._request_id: str | None = None
        self._media_type: str | None = None
        self._bytes_exposed = False
        self._closed = False
        self._entered = False

    @property
    def request_id(self) -> str:
        if self._request_id is None:
            raise RuntimeError("Arrow stream has not been opened")
        return self._request_id

    @property
    def media_type(self) -> str:
        if self._media_type is None:
            raise RuntimeError("Arrow stream has not been opened")
        return self._media_type

    async def __aenter__(self) -> Self:
        if self._entered:
            raise RuntimeError("Arrow stream context already entered")
        self._entered = True
        await self._open_with_retry()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        if self._response is None:
            raise RuntimeError("Arrow stream must be opened via async context manager")
        if self._closed:
            raise RuntimeError("Arrow stream is closed")

        while True:
            assert self._response is not None
            try:
                async for chunk in self._response.aiter_bytes():
                    if chunk:
                        self._bytes_exposed = True
                        yield chunk
                return
            except httpx.HTTPError as exc:
                if self._bytes_exposed:
                    raise RepositoryStreamError(
                        "Arrow stream read failed after bytes were exposed",
                        request_id=self._request_id,
                    ) from exc
                await self._discard_transport()
                await self._open_with_retry()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._discard_transport()

    async def _open_with_retry(self) -> None:
        if self._closed:
            raise RuntimeError("Arrow stream is closed")

        attempt = 0
        last_error: BaseException | None = None
        while attempt < self._max_attempts:
            attempt += 1
            try:
                client, response = await self._open_attempt()
            except httpx.TransportError as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    raise
                await self._backoff(attempt)
                continue

            try:
                await self._validate_open_response(client, response)
            except RepositoryClientError as exc:
                await _close_pair(client, response)
                if exc.status_code not in RETRYABLE_STATUS_CODES or attempt >= self._max_attempts:
                    raise
                last_error = exc
                await self._backoff(attempt)
                continue
            except RepositoryProtocolError:
                await _close_pair(client, response)
                raise
            except BaseException:
                await _close_pair(client, response)
                raise

            self._client = client
            self._response = response
            return

        if last_error is not None:
            raise last_error
        raise RuntimeError("Arrow stream open exhausted attempts without result")

    async def _validate_open_response(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
    ) -> None:
        del client  # ownership decided by caller after validation
        if response.status_code != 200:
            # Error bodies are JSON; must read before raise_for_error_response.
            await response.aread()
            raise_for_error_response(response)

        request_id = require_request_id(response)
        media_type = require_arrow_media_type(response)
        self._request_id = request_id
        self._media_type = media_type

    async def _discard_transport(self) -> None:
        client = self._client
        response = self._response
        self._client = None
        self._response = None
        await _close_pair(client, response)

    async def _backoff(self, attempt: int) -> None:
        delay = self._base_delay_seconds * (2 ** (attempt - 1))
        if self._sleeper is None:
            await asyncio.sleep(delay)
        else:
            await self._sleeper(delay)



async def _close_pair(
    client: httpx.AsyncClient | None,
    response: httpx.Response | None,
) -> None:
    if response is not None:
        try:
            await response.aclose()
        except Exception:
            pass
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            pass
