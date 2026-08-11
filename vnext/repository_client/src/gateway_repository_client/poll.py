"""Operation polling helpers with monotonic deadline and capped backoff."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeAlias

from gateway_repository_contracts import OperationStatus, VersionedOperation
from gateway_repository_client.deadline import MonotonicDeadline
from gateway_repository_client.retry import Sleeper

Clock: TypeAlias = Callable[[], float]
OperationFetcher: TypeAlias = Callable[[], Awaitable[VersionedOperation]]

DEFAULT_POLL_DEADLINE_SECONDS = 60.0
DEFAULT_POLL_BASE_DELAY_SECONDS = 0.05
DEFAULT_POLL_MAX_DELAY_SECONDS = 1.0

_TERMINAL_STATUSES = frozenset({OperationStatus.SUCCEEDED, OperationStatus.FAILED})


async def wait_for_operation(
    fetch_operation: OperationFetcher,
    *,
    deadline_at: float,
    base_delay_seconds: float = DEFAULT_POLL_BASE_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_POLL_MAX_DELAY_SECONDS,
    clock: Clock | None = None,
    sleeper: Sleeper | None = None,
) -> VersionedOperation:
    """Poll until a terminal operation is observed or the monotonic deadline elapses."""

    monotonic_deadline = MonotonicDeadline.at(deadline_at, clock=clock)
    sleep = sleeper or _default_sleeper
    delay = base_delay_seconds

    while True:
        monotonic_deadline.check()
        operation = await fetch_operation()
        if operation.status in _TERMINAL_STATUSES:
            monotonic_deadline.check()
            return operation
        await monotonic_deadline.sleep_bounded(sleep, min(delay, max_delay_seconds))
        delay = min(delay * 2, max_delay_seconds)


async def _default_sleeper(seconds: float) -> None:
    await asyncio.sleep(seconds)
