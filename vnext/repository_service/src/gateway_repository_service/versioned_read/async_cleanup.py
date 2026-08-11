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
    saw_cancel = False
    task = asyncio.current_task()
    with anyio.CancelScope(shield=True):
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                saw_cancel = True
                if task is not None:
                    task.uncancel()
                continue
            break
        result = cleanup.result()
    if saw_cancel or (task is not None and task.cancelling()):
        raise asyncio.CancelledError()
    return result
