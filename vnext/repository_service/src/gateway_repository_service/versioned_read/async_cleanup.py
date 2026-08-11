"""Async helpers for cleanup that must finish under sustained cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

import anyio

_T = TypeVar("_T")


async def await_executor_future_under_cancel(awaitable: Awaitable[_T]) -> _T:
    """Wait for an executor future even when the caller receives repeated cancellations."""

    cleanup = awaitable if asyncio.isfuture(awaitable) else asyncio.ensure_future(awaitable)
    try:
        with anyio.CancelScope(shield=True):
            return await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        task = asyncio.current_task()
        if task is not None:
            task.uncancel()
        with anyio.CancelScope(shield=True):
            await asyncio.shield(cleanup)
        raise
    raise AssertionError("unreachable")
