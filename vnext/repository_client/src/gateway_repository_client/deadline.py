"""Monotonic deadline helpers for bounded client waits."""

from __future__ import annotations

import math
import time
from collections.abc import Awaitable, Callable
from typing import TypeAlias

from gateway_repository_client.errors import RepositoryClientTimeoutError

Clock: TypeAlias = Callable[[], float]
Sleeper: TypeAlias = Callable[[float], Awaitable[None]]


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
        now = (clock or time.monotonic)()
        return cls(seconds=max(0.0, deadline_at - now), clock=clock)

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
