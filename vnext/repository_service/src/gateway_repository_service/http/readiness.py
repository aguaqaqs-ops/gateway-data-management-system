"""Injectable readiness port for probe routes."""

from __future__ import annotations

from typing import Protocol


class ReadinessPort(Protocol):
    """Reports whether the service may accept public workload."""

    def is_ready(self) -> bool:
        """Return True when durable lifecycle checks have passed."""


class DefaultReadiness:
    """Production-default readiness that remains not-ready until lifecycle is wired."""

    def is_ready(self) -> bool:
        return False

    @staticmethod
    def not_ready_message() -> str:
        return "durable lifecycle is not initialized"
