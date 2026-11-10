"""Temporary storage capability, explicitly scoped to one request or execution."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import BinaryIO, ContextManager, Protocol

from gateway_backend.artifacts.store import ArtifactFileSourcePort


class ScratchLimitExceeded(MemoryError):
    """The execution's aggregate temporary disk budget was exhausted."""


class ScratchProducerLimitExceeded(ScratchLimitExceeded):
    """One temporary file exceeded its producer's narrower byte limit."""


class ScratchSessionPort(Protocol):
    @property
    def owner(self) -> str: ...

    def file(self, *, byte_limit: int) -> ContextManager[tuple[ArtifactFileSourcePort, BinaryIO]]: ...


class ScratchSpacePort(Protocol):
    def session(self, *, owner: str) -> ContextManager[ScratchSessionPort]: ...


_current: ContextVar[ScratchSessionPort | None] = ContextVar("artifact_scratch", default=None)


def optional_scratch() -> ScratchSessionPort | None:
    return _current.get()


def current_scratch() -> ScratchSessionPort:
    value = _current.get()
    if value is None:
        raise RuntimeError("temporary writer requires an explicit scratch owner")
    return value


@contextmanager
def scratch_scope(session: ScratchSessionPort) -> Iterator[None]:
    token = _current.set(session)
    try:
        yield
    finally:
        _current.reset(token)
