"""Review domain models and transition policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gateway_backend.domain.submission.errors import (
    InvalidReviewIdempotencyKey,
    InvalidReviewReason,
    InvalidReviewTransition,
    ReviewClosureViolation,
)

_REVIEW_REASON_MAX_BYTES = 4096
_REVIEW_IDEMPOTENCY_KEY_MIN_CHARS = 1
_REVIEW_IDEMPOTENCY_KEY_MAX_CHARS = 255
_REVIEW_IDEMPOTENCY_KEY_MIN_CODEPOINT = 0x0021
_REVIEW_IDEMPOTENCY_KEY_MAX_CODEPOINT = 0x007E


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED_FOR_REVISION = "RETURNED_FOR_REVISION"
    WITHDRAWN = "WITHDRAWN"


class ReviewEventKind(StrEnum):
    SUBMISSION_FINALIZED = "SUBMISSION_FINALIZED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED_FOR_REVISION = "RETURNED_FOR_REVISION"
    WITHDRAWN = "WITHDRAWN"


class ReviewAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN_FOR_REVISION = "RETURN_FOR_REVISION"
    WITHDRAW = "WITHDRAW"


_ACTION_TO_EVENT_KIND: dict[ReviewAction, ReviewEventKind] = {
    ReviewAction.APPROVE: ReviewEventKind.APPROVED,
    ReviewAction.REJECT: ReviewEventKind.REJECTED,
    ReviewAction.RETURN_FOR_REVISION: ReviewEventKind.RETURNED_FOR_REVISION,
    ReviewAction.WITHDRAW: ReviewEventKind.WITHDRAWN,
}

_ALLOWED_TRANSITIONS: dict[ReviewStatus, dict[ReviewAction, ReviewStatus]] = {
    ReviewStatus.PENDING: {
        ReviewAction.APPROVE: ReviewStatus.APPROVED,
        ReviewAction.REJECT: ReviewStatus.REJECTED,
        ReviewAction.RETURN_FOR_REVISION: ReviewStatus.RETURNED_FOR_REVISION,
        ReviewAction.WITHDRAW: ReviewStatus.WITHDRAWN,
    },
    ReviewStatus.APPROVED: {
        ReviewAction.RETURN_FOR_REVISION: ReviewStatus.RETURNED_FOR_REVISION,
    },
    ReviewStatus.REJECTED: {},
    ReviewStatus.RETURNED_FOR_REVISION: {},
    ReviewStatus.WITHDRAWN: {},
}

_TERMINAL_STATUSES = frozenset(
    {
        ReviewStatus.REJECTED,
        ReviewStatus.RETURNED_FOR_REVISION,
        ReviewStatus.WITHDRAWN,
    }
)


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    submission_id: str
    sequence: int
    event_kind: ReviewEventKind
    from_status: ReviewStatus | None
    to_status: ReviewStatus
    reason: str | None
    actor_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if type(self.submission_id) is not str or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if type(self.event_kind) is not ReviewEventKind:
            raise ValueError("event_kind must be ReviewEventKind")
        if self.from_status is not None and type(self.from_status) is not ReviewStatus:
            raise ValueError("from_status must be ReviewStatus or None")
        if type(self.to_status) is not ReviewStatus:
            raise ValueError("to_status must be ReviewStatus")
        if self.reason is not None and type(self.reason) is not str:
            raise ValueError("reason must be a string or None")
        if type(self.actor_id) is not str or not self.actor_id:
            raise ValueError("actor_id must be a non-empty string")
        if type(self.occurred_at) is not datetime:
            raise ValueError("occurred_at must be a datetime")
        if self.event_kind is ReviewEventKind.SUBMISSION_FINALIZED:
            if self.from_status is not None:
                raise ValueError("SUBMISSION_FINALIZED event requires from_status to be null")
            if self.to_status is not ReviewStatus.PENDING:
                raise ValueError("SUBMISSION_FINALIZED event must target PENDING")
            if self.sequence != 0:
                raise ValueError("SUBMISSION_FINALIZED event must use sequence 0")
        elif self.from_status is None:
            raise ValueError("user review events require from_status")
        if self.reason is not None:
            _assert_review_reason_scalar_contract(self.reason)


@dataclass(frozen=True, slots=True)
class ReviewProjection:
    submission_id: str
    status: ReviewStatus
    optimistic_version: int
    latest_sequence: int
    updated_by: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if type(self.submission_id) is not str or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if type(self.status) is not ReviewStatus:
            raise ValueError("status must be ReviewStatus")
        if type(self.optimistic_version) is not int or self.optimistic_version < 0:
            raise ValueError("optimistic_version must be a non-negative integer")
        if type(self.latest_sequence) is not int or self.latest_sequence < 0:
            raise ValueError("latest_sequence must be a non-negative integer")
        if type(self.updated_by) is not str or not self.updated_by:
            raise ValueError("updated_by must be a non-empty string")
        if type(self.updated_at) is not datetime:
            raise ValueError("updated_at must be a datetime")


@dataclass(frozen=True, slots=True)
class ReviewIdempotencyRecord:
    business_project_id: str
    submission_id: str
    idempotency_key: str
    request_fingerprint: str
    event_sequence: int

    def __post_init__(self) -> None:
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")
        if type(self.submission_id) is not str or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if type(self.idempotency_key) is not str or not self.idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if type(self.request_fingerprint) is not str or not self.request_fingerprint:
            raise ValueError("request_fingerprint must be a non-empty string")
        if type(self.event_sequence) is not int or self.event_sequence < 0:
            raise ValueError("event_sequence must be a non-negative integer")


def review_allowed_transitions() -> dict[ReviewStatus, dict[ReviewAction, ReviewStatus]]:
    """Return the frozen review transition matrix for inventory tests."""

    return {
        current: dict(actions) for current, actions in _ALLOWED_TRANSITIONS.items()
    }


def is_terminal_review_status(status: ReviewStatus) -> bool:
    return status in _TERMINAL_STATUSES


def resolve_review_transition(
    current: ReviewStatus,
    action: ReviewAction,
) -> tuple[ReviewEventKind, ReviewStatus]:
    """Resolve one allowed review transition or raise InvalidReviewTransition."""

    if type(current) is not ReviewStatus:
        raise ValueError("current must be ReviewStatus")
    if type(action) is not ReviewAction:
        raise ValueError("action must be ReviewAction")
    allowed = _ALLOWED_TRANSITIONS.get(current, {})
    target = allowed.get(action)
    if target is None:
        raise InvalidReviewTransition(current=current.value, action=action.value)
    return _ACTION_TO_EVENT_KIND[action], target


def validate_review_closure(
    projection: ReviewProjection | None,
    events: tuple[ReviewEvent, ...],
) -> None:
    """Validate projection/event closure or raise ReviewClosureViolation."""

    if projection is None:
        raise ReviewClosureViolation("review projection is missing")
    if not events:
        raise ReviewClosureViolation("review event stream is empty")
    if projection.submission_id != events[0].submission_id:
        raise ReviewClosureViolation("review projection submission_id does not match events")
    for index, event in enumerate(events):
        if event.submission_id != projection.submission_id:
            raise ReviewClosureViolation("review event submission_id does not match projection")
        if event.sequence != index:
            raise ReviewClosureViolation("review event sequence has a gap or duplicate")
    latest_event = events[-1]
    latest_sequence = latest_event.sequence
    if projection.optimistic_version != latest_sequence:
        raise ReviewClosureViolation("review projection optimistic_version does not match events")
    if projection.latest_sequence != latest_sequence:
        raise ReviewClosureViolation("review projection latest_sequence does not match events")
    if projection.status is not latest_event.to_status:
        raise ReviewClosureViolation("review projection status does not match latest event")
    if projection.updated_by != latest_event.actor_id:
        raise ReviewClosureViolation("review projection updated_by does not match latest event")
    if projection.updated_at != latest_event.occurred_at:
        raise ReviewClosureViolation("review projection updated_at does not match latest event")


def build_seed_projection(
    *,
    submission_id: str,
    actor_id: str,
    occurred_at: datetime,
) -> tuple[ReviewEvent, ReviewProjection]:
    """Build the immutable seed event and initial PENDING projection."""

    event = ReviewEvent(
        submission_id=submission_id,
        sequence=0,
        event_kind=ReviewEventKind.SUBMISSION_FINALIZED,
        from_status=None,
        to_status=ReviewStatus.PENDING,
        reason=None,
        actor_id=actor_id,
        occurred_at=occurred_at,
    )
    projection = ReviewProjection(
        submission_id=submission_id,
        status=ReviewStatus.PENDING,
        optimistic_version=0,
        latest_sequence=0,
        updated_by=actor_id,
        updated_at=occurred_at,
    )
    return event, projection


def validate_review_reason(action: ReviewAction, reason: str | None) -> str | None:
    """Validate review reason for one action and return the unchanged value."""

    if type(action) is not ReviewAction:
        raise ValueError("action must be ReviewAction")
    if reason is None:
        if action in {ReviewAction.REJECT, ReviewAction.RETURN_FOR_REVISION}:
            raise InvalidReviewReason("reason is required for reject and return actions")
        return None
    if type(reason) is not str:
        raise InvalidReviewReason("reason must be a string or null")
    _assert_review_reason_scalar_contract(reason)
    if not any(not char.isspace() for char in reason):
        raise InvalidReviewReason("reason must contain at least one non-whitespace character")
    return reason


def validate_review_idempotency_key(key: str) -> str:
    """Validate Idempotency-Key and return the unchanged value."""

    if type(key) is not str:
        raise InvalidReviewIdempotencyKey("idempotency key must be a string")
    if not _REVIEW_IDEMPOTENCY_KEY_MIN_CHARS <= len(key) <= _REVIEW_IDEMPOTENCY_KEY_MAX_CHARS:
        raise InvalidReviewIdempotencyKey("idempotency key length is out of bounds")
    for char in key:
        codepoint = ord(char)
        if (
            codepoint < _REVIEW_IDEMPOTENCY_KEY_MIN_CODEPOINT
            or codepoint > _REVIEW_IDEMPOTENCY_KEY_MAX_CODEPOINT
        ):
            raise InvalidReviewIdempotencyKey(
                "idempotency key must use printable ASCII characters only"
            )
    return key


def _assert_review_reason_scalar_contract(reason: str) -> None:
    for char in reason:
        codepoint = ord(char)
        if codepoint <= 0x001F or 0x007F <= codepoint <= 0x009F:
            raise InvalidReviewReason("reason contains forbidden control characters")
        if 0xD800 <= codepoint <= 0xDFFF:
            raise InvalidReviewReason("reason contains surrogate code points")
        if _is_unicode_noncharacter(codepoint):
            raise InvalidReviewReason("reason contains noncharacter code points")
    encoded = reason.encode("utf-8")
    if not 1 <= len(encoded) <= _REVIEW_REASON_MAX_BYTES:
        raise InvalidReviewReason("reason exceeds bounded size")


def _is_unicode_noncharacter(codepoint: int) -> bool:
    if 0xFDD0 <= codepoint <= 0xFDEF:
        return True
    low = codepoint & 0xFFFF
    return low in {0xFFFE, 0xFFFF}
