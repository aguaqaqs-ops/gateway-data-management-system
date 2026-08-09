"""Private typed faults for commit-pinned reads."""

from __future__ import annotations


class VersionedReadError(Exception):
    """Base fault for private versioned read operations."""


class RepositoryNotVisibleError(VersionedReadError):
    """Repository ledger or published tree evidence is missing."""


class MainRefNotFoundError(VersionedReadError):
    """Literal main ref could not be resolved."""


class CommitNotFoundError(VersionedReadError):
    """Opaque commit token could not be located."""


class TableNotFoundError(VersionedReadError):
    """Exact table name is absent from the pinned catalog."""


class ProviderUnavailableError(VersionedReadError):
    """Provider, timeout, or malformed Dolt output made the read unavailable."""


class ReadStreamCancelledError(VersionedReadError):
    """Row stream was cancelled before completion."""
