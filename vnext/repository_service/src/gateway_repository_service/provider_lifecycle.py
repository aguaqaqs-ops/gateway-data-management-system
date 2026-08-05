"""Selected offline CLI provider capability checks for service startup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner, ProcessBoundaryError
from gateway_repository_service.settings import RepositoryServiceSettings


class ProviderUnavailableError(RuntimeError):
    """Raised when the selected provider fails capability checks."""


@dataclass(frozen=True)
class OfflineCliCapabilityGate:
    settings: RepositoryServiceSettings
    layout: DurableLayout
    verified_version: str

    @classmethod
    def verify(cls, settings: RepositoryServiceSettings, layout: DurableLayout) -> "OfflineCliCapabilityGate":
        if not settings.dolt_binary.is_file():
            raise ProviderUnavailableError("dolt executable is unavailable")
        try:
            DoltRunner(settings, layout.root)
        except ProcessBoundaryError as exc:
            raise ProviderUnavailableError("dolt capability check failed") from exc
        return cls(settings=settings, layout=layout, verified_version=settings.dolt_version)

    def executable_path(self) -> Path:
        return self.settings.dolt_binary
