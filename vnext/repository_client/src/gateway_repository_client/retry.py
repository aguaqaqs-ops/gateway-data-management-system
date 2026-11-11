"""Bounded retry helpers for idempotent Repository requests."""

from __future__ import annotations

import asyncio
import time

from gateway_repository_contracts import REPOSITORY_BUSY_CODE
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

import httpx

from gateway_repository_client.deadline import CancelRequested, RequestControl
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


def is_repository_busy(exc: BaseException) -> bool:
    return isinstance(exc, RepositoryClientError) and exc.status_code == 503 and exc.error.code == REPOSITORY_BUSY_CODE


class ReadAdmissionControl(RequestControl):
    """One finite admission window, shared by all attempts of a logical read."""

    def __init__(self, *, cancel_requested: CancelRequested | None = None,
                 deadline_at: float | None = None, clock: Clock | None = None) -> None:
        admission_end = (clock or time.monotonic)() + 300.0
        super().__init__(cancel_requested=cancel_requested,
            deadline_at=min(deadline_at, admission_end) if deadline_at is not None else admission_end,
            clock=clock)


async def retry_idempotent_request(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    sleeper: Sleeper | None = None,
    deadline_at: float | None = None,
    clock: Clock | None = None,
    cancel_requested: CancelRequested | None = None,
    read_admission: bool = False,
) -> T:
    """Retry transient network or gateway failures for the same idempotent request."""

    sleep = sleeper or _default_sleeper
    control = RequestControl(cancel_requested=cancel_requested, deadline_at=deadline_at, clock=clock)
    admission = ReadAdmissionControl(cancel_requested=cancel_requested, deadline_at=deadline_at, clock=clock) if read_admission else control
    attempt = 0
    while True:
        admission.check()
        attempt += 1
        try:
            result = await admission.run(operation)
            # A completed observation belongs to the polling owner, which may
            # return a terminal result at its boundary. New explicit caller
            # cancellation remains checked before returning its request.
            if cancel_requested is not None:
                control.check()
            return result
        except asyncio.TimeoutError as exc:
            raise RepositoryClientTimeoutError() from exc
        except httpx.TransportError:
            if attempt >= max_attempts:
                raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
        except RepositoryClientError as exc:
            if read_admission and is_repository_busy(exc):
                attempt -= 1
                await admission.sleep(sleep, 1.0)
                continue
            if exc.status_code not in RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
        except RepositoryProtocolError as exc:
            if not _is_retryable_protocol_error(exc) or attempt >= max_attempts:
                raise
        if attempt < max_attempts:
            delay = base_delay_seconds * (2 ** (attempt - 1))
            await admission.sleep(sleep, delay)
