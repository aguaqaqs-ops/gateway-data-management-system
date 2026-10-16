"""Application-owned workspace ports and control transactions."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from gateway_backend.application.control_transactions import ControlTransaction
from gateway_backend.application.canonical_metadata.ports import CommitCanonicalMetadataPort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.ports import (
    BaselineHeadReadPort,
    ScopeResolutionPort,
    WorkspaceRepository,
)
from gateway_backend.operations import OperationStore


class WorkspaceControlTransaction(ControlTransaction, Protocol):
    @property
    def commit_canonical_metadata(self) -> CommitCanonicalMetadataPort: ...

    @property
    def operations(self) -> OperationStore: ...

    @property
    def workspace(self) -> WorkspaceRepository: ...

    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool: ...

    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int: ...


class WorkspaceControlUnitOfWorkFactory(Protocol):
    def __call__(
        self,
        *,
        read_only: bool = False,
    ) -> AbstractContextManager[WorkspaceControlTransaction]: ...

__all__ = [
    "BaselineHeadReadPort",
    "ScopeResolutionPort",
    "WorkspaceControlTransaction",
    "WorkspaceControlUnitOfWorkFactory",
    "WorkspaceRepository",
]
