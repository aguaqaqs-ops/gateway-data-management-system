"""Ports and fault injection seams for CreateRepository."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gateway_repository_service.publication import FaultPoint


class RepositoryCreatePort(Protocol):
    """Initializes a Dolt repository in a staging directory."""

    def initialize_and_head(self, staging: Path) -> str:
        """Initialize Dolt with main and return the opaque initial commit id."""


class RepositoryPublicationPort(Protocol):
    """Publishes a staged directory with contract publication barriers."""

    def publish(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        """Fsync staged content and atomically rename into place without replacement."""


class CreateRepositoryFaultInjector(Protocol):
    """Private fault injection seam for create recovery tests."""

    def after_pending(self) -> None:
        """Inject a fault immediately after PENDING is durably written."""

    def after_staging(self) -> None:
        """Inject a fault after the staging directory is created."""

    def after_dolt_init(self) -> None:
        """Inject a fault after Dolt initialization completes."""

    def publication_fault(self) -> FaultPoint:
        """Return the publication fault point to inject, if any."""

    def after_succeeded_before_response(self) -> None:
        """Inject a fault after SUCCEEDED is durably written and before returning."""


class NoOpCreateRepositoryFaultInjector:
    """Default injector that does not inject faults."""

    def after_pending(self) -> None:
        return None

    def after_staging(self) -> None:
        return None

    def after_dolt_init(self) -> None:
        return None

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.NONE

    def after_succeeded_before_response(self) -> None:
        return None
