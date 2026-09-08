"""Application-layer errors for workspace use cases."""

from __future__ import annotations


class WorkspaceApplicationError(Exception):
    """Base error for workspace application services."""


class IdempotencyConflict(WorkspaceApplicationError):
    """Same idempotency key was reused with a different request fingerprint."""

    stable_code = "IDEMPOTENCY_CONFLICT"

    def __init__(self, *, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key {idempotency_key!r} conflicts with a different request fingerprint"
        )
        self.idempotency_key = idempotency_key


class PreviewBindingConflict(WorkspaceApplicationError):
    """Preview start request does not match frozen workspace or baseline binding."""

    stable_code = "PREVIEW_BINDING_CONFLICT"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
