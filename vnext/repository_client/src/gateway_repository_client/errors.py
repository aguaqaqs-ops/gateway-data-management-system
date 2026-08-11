"""Repository client errors."""

from __future__ import annotations

from gateway_repository_contracts import SimpleError


class RepositoryClientError(RuntimeError):
    """Raised when the Repository Service returns a non-retryable HTTP error."""

    def __init__(
        self,
        *,
        status_code: int,
        error: SimpleError,
    ) -> None:
        self.status_code = status_code
        self.error = error
        super().__init__(error.message)


class RepositoryProtocolError(RuntimeError):
    """Raised when a wire response violates the Repository HTTP/protocol contract."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.request_id = request_id
        super().__init__(message)


class RepositoryStreamError(RuntimeError):
    """Raised when an owned Arrow byte stream fails after bytes were exposed."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.message = message
        super().__init__(message)


class RepositoryClientTimeoutError(RuntimeError):
    """Raised when wait_operation exceeds its monotonic poll deadline."""

    def __init__(self, message: str = "operation poll deadline exceeded") -> None:
        self.message = message
        super().__init__(message)
