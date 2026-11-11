"""Best effort execution hook, separate from the existing worker observer."""
from __future__ import annotations
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from gateway_backend.operations.worker import ClaimedWork


class TelemetrySink(Protocol):
    def begin_execution(self, work: ClaimedWork) -> None: ...
    def end_execution(self, work: ClaimedWork) -> None: ...


class NullTelemetrySink:
    def begin_execution(self, work: ClaimedWork) -> None:
        pass

    def end_execution(self, work: ClaimedWork) -> None:
        pass
