"""Private adapters for CreateRepository."""

from __future__ import annotations

from pathlib import Path

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.publication import FaultPoint, atomic_publish
from gateway_repository_service.settings import RepositoryServiceSettings


class DoltCreateAdapter:
    """Candidate A offline CLI adapter for repository initialization."""

    def __init__(self, settings: RepositoryServiceSettings, layout: DurableLayout, runner: DoltRunner | None = None) -> None:
        self._runner = runner
        self._settings = settings
        self._layout = layout

    def initialize_and_head(self, staging: Path) -> str:
        runner = self._runner or DoltRunner.for_layout(self._settings, self._layout)
        provider = OfflineCliProvider(self._settings, self._layout, staging, runner)
        provider.initialize_repository()
        return provider.head()


class FilesystemPublicationAdapter:
    """Production-owned adapter over the shared publication primitive."""

    def publish(
        self,
        staging: Path,
        target: Path,
        *,
        fault: FaultPoint = FaultPoint.NONE,
    ) -> None:
        atomic_publish(staging, target, fault=fault)
