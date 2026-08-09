"""Private typed faults for commit-pinned reads."""

from __future__ import annotations

import re

_REDACT_PATTERNS = (
    re.compile(r"SELECT\b", re.IGNORECASE),
    re.compile(r"/"),
    re.compile(r"\\"),
)


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


class ReadStreamCancelledError(ProviderUnavailableError):
    """Row stream was cancelled before completion."""


def redact_provider_message(message: str) -> str:
    if any(pattern.search(message) for pattern in _REDACT_PATTERNS):
        return "versioned read provider is unavailable"
    return message
