"""Async helpers for cleanup that must finish under sustained cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

import anyio

_T = TypeVar("_T")


async def await_executor_future_under_cancel(awaitable: Awaitable[_T]) -> _T:
    """Wait for an executor future even when the caller receives repeated cancellations."""

    future = asyncio.ensure_future(awaitable)

    def _wait_in_thread() -> _T:
        return future.result()

    result: _T
    try:
        with anyio.CancelScope(shield=True):
            result = await asyncio.wrap_future(future)
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            _ = await anyio.to_thread.run_sync(_wait_in_thread)
        raise
    return result
