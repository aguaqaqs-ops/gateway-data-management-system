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

    def publication_fault(self) -> FaultPoint:
        """Return the publication fault point to inject, if any."""


class NoOpCreateRepositoryFaultInjector:
    """Default injector that does not inject faults."""

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.NONE
