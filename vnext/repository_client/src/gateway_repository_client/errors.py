"""Repository client errors."""

from __future__ import annotations

from gateway_repository_contracts import SimpleError


class RepositoryClientError(RuntimeError):
    """Raised when the Repository Service returns a non-retryable error."""

    def __init__(
        self,
        *,
        status_code: int,
        error: SimpleError,
    ) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(error.message)
