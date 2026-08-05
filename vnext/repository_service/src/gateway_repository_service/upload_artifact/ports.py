"""Ports and fault injection seams for UploadArtifact."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from gateway_repository_service.publication import FaultPoint


class ArtifactBodySink(Protocol):
    """Incrementally writes upload body bytes to a staging file."""

    def write_chunk(self, chunk: bytes) -> None:
        """Append one chunk and update incremental size/SHA state."""

    def close(self) -> tuple[int, str]:
        """Flush, fsync staging file and return measured size and lowercase SHA-256 hex."""

    def abort(self) -> None:
        """Remove the owned staging file without publishing."""


class ArtifactPublicationPort(Protocol):
    """Publishes a staged artifact file with contract publication barriers."""

    def publish_file(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        """Fsync staged content and atomically rename into place without replacement."""


class UploadArtifactFaultInjector(Protocol):
    """Private fault injection seam for upload recovery tests."""

    def after_pending(self) -> None:
        """Inject a fault immediately after PENDING is durably written."""

    def after_partial_body(self) -> None:
        """Inject a fault after at least one body chunk is written."""

    def after_complete_close(self) -> None:
        """Inject a fault after body close validation and before publication."""

    def publication_fault(self) -> FaultPoint:
        """Return the publication fault point to inject, if any."""

    def after_succeeded_before_response(self) -> None:
        """Inject a fault after SUCCEEDED is durably written and before returning."""


class NoOpUploadArtifactFaultInjector:
    """Default injector that does not inject faults."""

    def after_pending(self) -> None:
        return None

    def after_partial_body(self) -> None:
        return None

    def after_complete_close(self) -> None:
        return None

    def publication_fault(self) -> FaultPoint:
        return FaultPoint.NONE

    def after_succeeded_before_response(self) -> None:
        return None
