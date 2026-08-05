"""Injectable readiness port for probe routes."""

from __future__ import annotations

from typing import Protocol

from gateway_repository_service.runtime import ServiceRuntime


class ReadinessPort(Protocol):
    """Reports whether the service may accept public workload."""

    def is_ready(self) -> bool:
        """Return True when durable lifecycle checks have passed."""

    def not_ready_message(self) -> str:
        """Return a sanitized reason when the service is not ready."""


class DefaultReadiness:
    """Production-default readiness that remains not-ready until lifecycle is wired."""

    def is_ready(self) -> bool:
        return False

    def not_ready_message(self) -> str:
        return "durable lifecycle is not initialized"


class LifecycleReadiness:
    """Readiness backed by the service runtime durable lifecycle checks."""

    def __init__(self, runtime: ServiceRuntime) -> None:
        self._runtime = runtime

    def is_ready(self) -> bool:
        return self._runtime.is_ready()

    def not_ready_message(self) -> str:
        return self._runtime.not_ready_message()
