"""Bounded retry helpers for idempotent Repository mutations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

from gateway_repository_client.errors import RepositoryClientError

RETRYABLE_STATUS_CODES = frozenset({502, 503})
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.05

T = TypeVar("T")


async def retry_idempotent_request(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
) -> T:
    """Retry transient network or gateway failures for the same idempotent request."""

    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except httpx.TransportError:
            if attempt >= max_attempts:
                raise
        except httpx.HTTPStatusError:
            if attempt >= max_attempts:
                raise
        except RepositoryClientError as exc:
            if exc.status_code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
        if attempt < max_attempts:
            await asyncio.sleep(base_delay_seconds * (2 ** (attempt - 1)))
