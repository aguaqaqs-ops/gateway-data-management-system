"""Application-facing workspace port aliases."""

from gateway_backend.domain.workspace.ports import (
    BaselineHeadReadPort,
    ScopeResolutionPort,
    WorkspaceRepository,
)

__all__ = [
    "BaselineHeadReadPort",
    "ScopeResolutionPort",
    "WorkspaceRepository",
]
