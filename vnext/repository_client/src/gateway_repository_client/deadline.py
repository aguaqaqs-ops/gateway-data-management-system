"""Monotonic deadline helpers for bounded client waits."""

from __future__ import annotations

import math
import time
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

from gateway_repository_client.errors import RepositoryClientTimeoutError

Clock: TypeAlias = Callable[[], float]
Sleeper: TypeAlias = Callable[[float], Awaitable[None]]
CancelRequested: TypeAlias = Callable[[], bool]
_T = TypeVar("_T")


def validate_deadline_seconds(value: float) -> float:
    """Reject non-positive or non-finite poll/retry deadline values."""

    if not math.isfinite(value) or value <= 0:
        raise ValueError("deadline_seconds must be a positive finite number")
    return value


class MonotonicDeadline:
    """Absolute monotonic deadline with bounded sleep support."""

    def __init__(
        self,
        *,
        seconds: float,
        clock: Clock | None = None,
    ) -> None:
        validate_deadline_seconds(seconds)
        self._clock = clock or time.monotonic
        self._deadline_at = self._clock() + seconds

    @classmethod
    def at(cls, deadline_at: float, *, clock: Clock | None = None) -> MonotonicDeadline:
        if not math.isfinite(deadline_at):
            raise ValueError("deadline_at must be a finite number")
        instance = cls.__new__(cls)
        instance._clock = clock or time.monotonic
        instance._deadline_at = deadline_at
        return instance

    @property
    def deadline_at(self) -> float:
        return self._deadline_at

    def remaining(self) -> float:
        return max(0.0, self._deadline_at - self._clock())

    def check(self) -> None:
        if self._clock() >= self._deadline_at:
            raise RepositoryClientTimeoutError()

    async def sleep_bounded(self, sleeper: Sleeper, delay: float) -> None:
        self.check()
        bounded = min(delay, self.remaining())
        if bounded <= 0:
            self.check()
            return
        await sleeper(bounded)


class RequestControl:
    """Optional caller controls for one request, without owning its retry policy."""

    def __init__(
        self, *, cancel_requested: CancelRequested | None = None,
        deadline_at: float | None = None, clock: Clock | None = None,
    ) -> None:
        self._cancel_requested = cancel_requested
        self._deadline = None if deadline_at is None else MonotonicDeadline.at(deadline_at, clock=clock)

    def check(self) -> None:
        if self._cancel_requested is not None and self._cancel_requested():
            raise InterruptedError("repository request cancelled")
        if self._deadline is not None:
            self._deadline.check()

    async def run(
        self, operation: Callable[[], Awaitable[_T]], *,
        abandon: Callable[[_T], Awaitable[None]] | None = None,
    ) -> _T:
        """Cancel a pending attempt/read when its caller stops waiting.

        Return a completed result to its transport owner before another control
        check: a newly opened response must remain reachable for that cleanup.
        """
        self.check()
        if self._cancel_requested is None and self._deadline is None:
            return await operation()
        pending = asyncio.ensure_future(operation())
        try:
            while not pending.done():
                interval = 0.05
                if self._deadline is not None:
                    remaining = self._deadline.remaining()
                    interval = remaining if self._cancel_requested is None else min(interval, remaining)
                await asyncio.wait((pending,), timeout=interval)
                if not pending.done():
                    self.check()
            return pending.result()
        except BaseException as exc:
            if not pending.done():
                pending.cancel()
            try:
                abandoned = await pending
                if abandon is not None:
                    await abandon(abandoned)
            except asyncio.CancelledError:
                pass
            except BaseException as cleanup:
                if cleanup is not exc:
                    exc.add_note(f"request cancellation cleanup raised {type(cleanup).__name__}")
            raise

    async def sleep(self, sleeper: Sleeper, delay: float) -> None:
        self.check()
        if self._deadline is not None:
            delay = min(delay, self._deadline.remaining())
        await self.run(lambda: sleeper(delay))
        self.check()
