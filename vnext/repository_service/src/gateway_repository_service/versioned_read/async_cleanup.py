"""Async helpers for cleanup that must finish under sustained cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

_T = TypeVar("_T")


async def await_executor_future_under_cancel(awaitable: Awaitable[_T]) -> _T:
    """Wait for an executor future even when the caller receives repeated cancellations."""

    try:
        return await asyncio.shield(awaitable)
    except asyncio.CancelledError:
        task = asyncio.ensure_future(awaitable)
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        _ = task.result()
        raise
