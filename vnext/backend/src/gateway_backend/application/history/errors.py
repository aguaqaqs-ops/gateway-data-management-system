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


class HistoryCompareJobNotRegistered(HistoryApplicationError):
    """History compare processing is not available in the active job registry."""


class HistoryCompareAcceptanceUnavailable(HistoryApplicationError):
    """History compare acceptance could not be formed from validated bindings."""


class HistoryCompareRequestExpired(HistoryApplicationError):
    """An original key or still-recorded alias refers to an expired success."""


class HistoryCompareAliasLimit(HistoryApplicationError):
    def __init__(self, operation_id: str) -> None:
        super().__init__("history compare alias limit reached")
        self.operation_id = operation_id


class HistoryComparePreflightFailure(HistoryApplicationError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(str(cause))
        self.cause = cause


class HistoryCompareScopeLimit(HistoryApplicationError):
    def __init__(self, operation_ids: tuple[str, ...]) -> None:
        super().__init__("history compare scope limit reached")
        self.operation_ids = operation_ids
