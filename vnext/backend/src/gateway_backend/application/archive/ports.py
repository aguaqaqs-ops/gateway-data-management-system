"""Archive application ports."""

from __future__ import annotations

from gateway_backend.application.submission.ports import (
    WorkspaceControlTransaction,
    WorkspaceControlUnitOfWorkFactory,
)

ArchiveControlTransaction = WorkspaceControlTransaction
ArchiveControlUnitOfWorkFactory = WorkspaceControlUnitOfWorkFactory
