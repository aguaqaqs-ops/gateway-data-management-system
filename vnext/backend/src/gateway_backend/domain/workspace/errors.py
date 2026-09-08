"""Workspace domain errors."""

from __future__ import annotations


class WorkspaceDomainError(Exception):
    """Base error for workspace domain invariants."""


class ScopeForbidden(WorkspaceDomainError):
    """Actor or scope does not match the workspace owner scope."""


class ScopeResolutionError(WorkspaceDomainError):
    """Current session scope cannot be resolved to a provisioned repository."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PermissionDenied(WorkspaceDomainError):
    """Required permission is missing from the current session."""

    def __init__(self, permission: str) -> None:
        super().__init__(f"missing permission {permission!r}")
        self.permission = permission


class OpenWorkspaceConflict(WorkspaceDomainError):
    """An OPEN workspace already exists for the exact scope."""


class WorkspaceNotOpen(WorkspaceDomainError):
    """Workspace is not in OPEN state."""


class WorkspaceVersionConflict(WorkspaceDomainError):
    """Expected workspace optimistic version does not match the current value."""

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(f"expected workspace version {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class UploadClosureInvalid(WorkspaceDomainError):
    """Upload role map does not satisfy input completeness closure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
