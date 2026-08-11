"""Owned raw Arrow IPC byte stream for versioned table row reads."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Self

import httpx

from gateway_repository_contracts import MAX_WIRE_ERROR_JSON_BYTES
from gateway_repository_client.errors import (
    RepositoryClientError,
    RepositoryProtocolError,
    RepositoryStreamError,
)
from gateway_repository_client.protocol import (
    peek_request_id,
    raise_for_error_response,
    read_bounded_bytes,
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
        self._close_requested = False
        self._entered = False
        self._attempts_used = 0
        self._byte_iterator_active = False
        self._cleanup_notes: list[str] = []
        self._lifecycle_lock = asyncio.Lock()

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
        async with self._lifecycle_lock:
            if self._closed or self._close_requested:
                raise RuntimeError("Arrow stream is closed")
            if self._byte_iterator_active:
                raise RuntimeError("Arrow stream byte iterator already active")
            if self._response is None:
                raise RuntimeError("Arrow stream must be opened via async context manager")
            self._byte_iterator_active = True

        try:
            while True:
                self._ensure_open()
                response = self._response
                if response is None:
                    raise RuntimeError("Arrow stream is closed")
                try:
                    async for chunk in response.aiter_bytes():
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
                    if self._attempts_used >= self._max_attempts:
                        raise RepositoryStreamError(
                            "Arrow stream read failed before bytes were exposed",
                            request_id=self._request_id,
                        ) from exc
                    await self._open_with_retry(backoff=True)
        finally:
            async with self._lifecycle_lock:
                self._byte_iterator_active = False

    async def aclose(self) -> None:
        client: httpx.AsyncClient | None
        response: httpx.Response | None
        async with self._lifecycle_lock:
            if self._closed:
                return
            self._close_requested = True
            self._closed = True
            client = self._client
            response = self._response
            self._client = None
            self._response = None
        self._record_close_errors(await _close_pair_quiet(client, response))

    async def _open_with_retry(self, *, backoff: bool = False) -> None:
        self._ensure_open()
        if backoff:
            await self._backoff(self._attempts_used)
            self._ensure_open()

        last_error: BaseException | None = None
        while self._attempts_used < self._max_attempts:
            self._ensure_open()
            self._attempts_used += 1
            attempt = self._attempts_used
            client: httpx.AsyncClient | None = None
            response: httpx.Response | None = None
            try:
                try:
                    client, response = await self._open_attempt()
                except httpx.TransportError as exc:
                    last_error = exc
                    if attempt >= self._max_attempts:
                        raise
                    await self._backoff(attempt)
                    self._ensure_open()
                    continue

                try:
                    self._ensure_open()
                    await self._validate_open_response(response)
                    self._client = client
                    self._response = response
                    client = None
                    response = None
                    return
                except (RepositoryClientError, RepositoryProtocolError) as exc:
                    close_errors = await _close_pair_quiet(client, response)
                    client = None
                    response = None
                    self._record_close_errors(close_errors)
                    retryable = isinstance(exc, RepositoryClientError) and (
                        exc.status_code in RETRYABLE_STATUS_CODES
                    ) or (
                        isinstance(exc, RepositoryProtocolError)
                        and exc.status_code in RETRYABLE_STATUS_CODES
                    )
                    if not retryable or attempt >= self._max_attempts:
                        self._reraise_with_cleanup_notes(exc)
                    last_error = exc
                    await self._backoff(attempt)
                    self._ensure_open()
                    continue
                except BaseException as exc:
                    close_errors = await _close_pair_quiet(client, response)
                    client = None
                    response = None
                    self._record_close_errors(close_errors)
                    self._reraise_with_cleanup_notes(exc)
            finally:
                self._record_close_errors(await _close_pair_quiet(client, response))

        if last_error is not None:
            self._reraise_with_cleanup_notes(last_error)
        raise RuntimeError("Arrow stream open exhausted attempts without result")

    async def _validate_open_response(self, response: httpx.Response) -> None:
        request_id = peek_request_id(response)
        if response.status_code != 200:
            read_close_errors: list[Exception] = []
            try:
                body = await read_bounded_bytes(
                    response,
                    limit=MAX_WIRE_ERROR_JSON_BYTES,
                    request_id=request_id,
                    close_errors_out=read_close_errors,
                )
            except (httpx.HTTPError, OSError) as exc:
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RepositoryProtocolError(
                        "failed to read retryable error response body",
                        status_code=response.status_code,
                        request_id=request_id,
                    ) from exc
                raise RepositoryProtocolError(
                    "failed to read Arrow error response body",
                    status_code=response.status_code,
                    request_id=request_id,
                ) from exc
            self._record_close_errors(read_close_errors)
            await raise_for_error_response(response, body=body)
            return

        resolved_request_id = require_request_id(response)
        media_type = require_arrow_media_type(response)
        self._request_id = resolved_request_id
        self._media_type = media_type

    async def _claim_transport(
        self,
    ) -> tuple[httpx.AsyncClient | None, httpx.Response | None]:
        async with self._lifecycle_lock:
            client = self._client
            response = self._response
            self._client = None
            self._response = None
            return client, response

    async def _discard_transport(self) -> None:
        client, response = await self._claim_transport()
        self._record_close_errors(await _close_pair_quiet(client, response))

    async def _backoff(self, attempt: int) -> None:
        delay = self._base_delay_seconds * (2 ** (attempt - 1))
        if self._sleeper is None:
            await asyncio.sleep(delay)
        else:
            await self._sleeper(delay)

    def _ensure_open(self) -> None:
        if self._close_requested or self._closed:
            raise RuntimeError("Arrow stream is closed")

    def _record_close_errors(self, close_errors: list[Exception]) -> None:
        for error in close_errors:
            self._cleanup_notes.append(f"cleanup close failed: {error}")

    def _reraise_with_cleanup_notes(self, exc: BaseException) -> None:
        existing_notes = list(getattr(exc, "__notes__", ()))
        for note in self._cleanup_notes:
            if note not in existing_notes:
                exc.add_note(note)
                existing_notes.append(note)
        raise exc


async def _close_pair_quiet(
    client: httpx.AsyncClient | None,
    response: httpx.Response | None,
) -> list[Exception]:
    cancelled: BaseException | None = None
    close_errors: list[Exception] = []
    if response is not None:
        try:
            await response.aclose()
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                cancelled = exc
            elif isinstance(exc, Exception):
                close_errors.append(exc)
    if client is not None:
        try:
            await client.aclose()
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                cancelled = exc
            elif isinstance(exc, Exception):
                close_errors.append(exc)
    if cancelled is not None:
        raise cancelled
    return close_errors


async def _close_pair(
    client: httpx.AsyncClient | None,
    response: httpx.Response | None,
) -> None:
    close_errors = await _close_pair_quiet(client, response)
    if close_errors:
        if len(close_errors) == 1:
            raise close_errors[0]
        raise ExceptionGroup("failed to close Arrow stream transport", close_errors)
