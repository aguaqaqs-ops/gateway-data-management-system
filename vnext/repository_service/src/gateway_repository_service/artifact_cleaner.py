"""Artifact cleaner lifecycle port (S1 seam; retention implemented in S2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ArtifactCleanerLifecycle(Protocol):
    """Instance-scoped stop/join seam owned by ServiceRuntime.

    S1 does not start a background cleaner thread. Concrete retention/sweep
    belongs to P2-R6-S2. Implementations must stop before control DB close and
    durable-root lock release.
    """

    def stop(self, *, timeout: float | None = None) -> None:
        """Stop and join cleaner work. Idempotent."""


class NoOpArtifactCleaner:
    """Default cleaner that performs no background work."""

    def stop(self, *, timeout: float | None = None) -> None:
        del timeout
