"""Non-rewindable upload source errors."""

from __future__ import annotations


class NonRewindableUploadSourceError(RuntimeError):
    """Raised when a retryable upload failure cannot be retried without spooling."""

    def __init__(self, *, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)
