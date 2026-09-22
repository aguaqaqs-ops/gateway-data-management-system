"""Application-layer errors for Archive use cases."""

from __future__ import annotations

from gateway_backend.application.submission.errors import SubmitApplicationError


class ArchiveApplicationError(SubmitApplicationError):
    """Base error for archive application services."""


class ArchiveIntegrityFailure(ArchiveApplicationError):
    """Archive read or closure integrity is inconsistent."""

    stable_code = "ARCHIVE_INTEGRITY_FAILURE"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ArchiveScopeLimitExceeded(ArchiveApplicationError):
    """Archive candidate or audit reference count exceeds the supported limit."""

    stable_code = "ARCHIVE_SCOPE_LIMIT_EXCEEDED"

    def __init__(self) -> None:
        super().__init__("archive scope limit exceeded")


class CandidateSetConflict(ArchiveApplicationError):
    """Caller candidate-set digest does not match the current snapshot."""

    stable_code = "CANDIDATE_SET_CONFLICT"

    def __init__(self) -> None:
        super().__init__("candidate set digest does not match current snapshot")


class CandidateBindingConflict(ArchiveApplicationError):
    """Selected candidate reference is unknown or stale."""

    stable_code = "CANDIDATE_BINDING_CONFLICT"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ArchiveConfirmationRequired(ArchiveApplicationError):
    """Start is blocked because confirmation audit is missing or invalid."""

    stable_code = "ARCHIVE_CONFIRMATION_REQUIRED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ArchiveAnomalyUnresolved(ArchiveApplicationError):
    """Start is blocked because anomaly resolution audit is missing or invalid."""

    stable_code = "ARCHIVE_ANOMALY_UNRESOLVED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ArchiveAuditVersionConflict(ArchiveApplicationError):
    """Audit append expected sequence does not match the latest subject sequence."""

    stable_code = "ARCHIVE_AUDIT_VERSION_CONFLICT"

    def __init__(self, *, expected: int, actual: int) -> None:
        super().__init__(
            f"audit sequence conflict: expected {expected}, actual {actual}"
        )
        self.expected = expected
        self.actual = actual


class ActiveSubmitAttempt(ArchiveApplicationError):
    """Repository has an active SubmitAttempt that blocks Archive Start."""

    stable_code = "ACTIVE_SUBMIT_ATTEMPT"

    def __init__(self) -> None:
        super().__init__("repository has an active submit attempt")


class ArchiveResultNotFound(ArchiveApplicationError):
    """Archive result is missing or not visible in the current scope."""

    stable_code = "RESOURCE_NOT_FOUND"

    def __init__(self, *, archive_result_id: str) -> None:
        super().__init__(f"archive result {archive_result_id!r} was not found")
        self.archive_result_id = archive_result_id
