"""History application errors."""


class HistoryApplicationError(Exception):
    """Base class for History application failures."""


class HistoryRequestValidation(HistoryApplicationError):
    """Raised when list query parameters are invalid."""


class HistoryIntegrityFailure(HistoryApplicationError):
    """Raised when derived history facts are inconsistent."""
