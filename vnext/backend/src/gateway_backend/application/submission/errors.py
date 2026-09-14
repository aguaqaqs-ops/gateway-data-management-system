"""Application-layer errors for submit use cases."""

from __future__ import annotations

from gateway_backend.domain.submission.errors import (
    SubmitAttemptVersionConflict as SubmitAttemptVersionConflict,
)
from gateway_backend.domain.submission.errors import (
    SubmitOccupancyConflict as SubmitOccupancyConflict,
)


class SubmitApplicationError(Exception):
    """Base error for submission application services."""


class IdempotencyConflict(SubmitApplicationError):
    """Same idempotency key was reused with a different request fingerprint."""

    stable_code = "IDEMPOTENCY_CONFLICT"

    def __init__(self, *, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key {idempotency_key!r} conflicts with a different request fingerprint"
        )
        self.idempotency_key = idempotency_key


class PreviewBindingConflict(SubmitApplicationError):
    """Accept request does not match frozen workspace or preview binding."""

    stable_code = "PREVIEW_BINDING_CONFLICT"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PreviewDerivedStale(SubmitApplicationError):
    """Preview binding is derived-stale relative to current BaselineHead."""

    stable_code = "PREVIEW_DERIVED_STALE"

    def __init__(self) -> None:
        super().__init__("preview result is derived-stale relative to current BaselineHead")


class BaselineVersionConflict(SubmitApplicationError):
    """Expected baseline node or head version does not match current BaselineHead."""

    stable_code = "BASELINE_VERSION_CONFLICT"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class NoCanonicalChange(SubmitApplicationError):
    """Preview canonical digest equals current business base; zero writes allowed."""

    stable_code = "NO_CANONICAL_CHANGE"

    def __init__(self) -> None:
        super().__init__(
            "preview canonical business digest equals current business base"
        )


class FinalizeBindingMismatch(SubmitApplicationError):
    """Matching finalize facts do not satisfy SubmitAttempt checkpoint bindings."""

    stable_code = "SUBMIT_RESULT_BINDING_MISMATCH"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AbortProofNotSatisfied(SubmitApplicationError):
    """Repository stable abort proof is missing or not allowed."""

    stable_code = "ABORT_PROOF_NOT_SATISFIED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FinalizeRecoveryRequired(SubmitApplicationError):
    """T3 replay found a FINALIZED attempt without a matching T3 closure."""

    stable_code = "FINALIZE_RECOVERY_REQUIRED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
