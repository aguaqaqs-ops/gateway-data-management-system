"""Bounded retry helpers for idempotent Repository requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

import httpx

from gateway_repository_client.deadline import MonotonicDeadline
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


def _is_retryable_protocol_error(exc: RepositoryProtocolError) -> bool:
    return exc.status_code in RETRYABLE_STATUS_CODES


async def retry_idempotent_request(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    sleeper: Sleeper | None = None,
    deadline_at: float | None = None,
    clock: Clock | None = None,
) -> T:
    """Retry transient network or gateway failures for the same idempotent request."""

    sleep = sleeper or _default_sleeper
    monotonic_deadline = (
        MonotonicDeadline.at(deadline_at, clock=clock) if deadline_at is not None else None
    )
    attempt = 0
    while True:
        if monotonic_deadline is not None:
            monotonic_deadline.check()
        attempt += 1
        try:
            if monotonic_deadline is not None:
                remaining = monotonic_deadline.remaining()
                if remaining <= 0:
                    monotonic_deadline.check()
                return await asyncio.wait_for(operation(), timeout=remaining)
            return await operation()
        except asyncio.TimeoutError as exc:
            raise RepositoryClientTimeoutError() from exc
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
            delay = base_delay_seconds * (2 ** (attempt - 1))
            if monotonic_deadline is not None:
                await monotonic_deadline.sleep_bounded(sleep, delay)
            else:
                await sleep(delay)
