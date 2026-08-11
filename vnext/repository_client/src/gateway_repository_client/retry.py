"""Bounded retry helpers for idempotent Repository requests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

import httpx

from gateway_repository_client.errors import (
    RepositoryClientError,
    RepositoryClientTimeoutError,
    RepositoryProtocolError,
)

RETRYABLE_STATUS_CODES = frozenset({502, 503})
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.05

T = TypeVar("T")
Sleeper = Callable[[float], Awaitable[None]]
Clock: TypeAlias = Callable[[], float]


async def _default_sleeper(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _check_deadline(*, deadline: float | None, clock: Clock | None) -> None:
    if deadline is None:
        return
    now = clock or time.monotonic
    if now() >= deadline:
        raise RepositoryClientTimeoutError()


def _is_retryable_protocol_error(exc: RepositoryProtocolError) -> bool:
    return exc.status_code in RETRYABLE_STATUS_CODES


async def retry_idempotent_request(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    sleeper: Sleeper | None = None,
    deadline: float | None = None,
    clock: Clock | None = None,
) -> T:
    """Retry transient network or gateway failures for the same idempotent request."""

    sleep = sleeper or _default_sleeper
    attempt = 0
    while True:
        _check_deadline(deadline=deadline, clock=clock)
        attempt += 1
        try:
            return await operation()
        except httpx.TransportError:
            if attempt >= max_attempts:
                raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
        except RepositoryClientError as exc:
            if exc.status_code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
        except RepositoryProtocolError as exc:
            if not _is_retryable_protocol_error(exc) or attempt >= max_attempts:
                raise
        if attempt < max_attempts:
            _check_deadline(deadline=deadline, clock=clock)
            await sleep(base_delay_seconds * (2 ** (attempt - 1)))
