"""History application errors."""


class HistoryApplicationError(Exception):
    """Base class for History application failures."""


class HistoryRequestValidation(HistoryApplicationError):
    """Raised when list query parameters are invalid."""


class HistoryIntegrityFailure(HistoryApplicationError):
    """Raised when derived history facts are inconsistent."""


class HistoryCompareIdempotencyConflict(HistoryApplicationError):
    def __init__(self, *, idempotency_key: str) -> None:
        super().__init__("history compare idempotency conflict")
        self.idempotency_key = idempotency_key


class HistoryCompareBindingConflict(HistoryApplicationError):
    """Raised when replay preconditions do not match durable acceptance facts."""


class HistoryCompareNodeNotFound(HistoryApplicationError):
    """Raised when a node ref cannot be resolved in the authorized scope."""


class HistoryIntegrityUnresolved(HistoryApplicationError):
    """Raised when a pending integrity incident blocks a new compare accept."""


class HistoryCompareIntegrityAckConflict(HistoryApplicationError):
    """Raised when integrity acknowledgement resolution_reference conflicts."""
