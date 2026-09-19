"""Review domain models, transition policy and fingerprint contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from gateway_backend.application.submission.review_contracts import (
    REVIEW_APPLY_FINGERPRINT_GOLDEN,
    ApplyReviewCommand,
    compute_review_apply_request_fingerprint,
    validate_apply_review_command,
)
from gateway_backend.domain.submission.errors import (
    InvalidReviewIdempotencyKey,
    InvalidReviewReason,
    InvalidReviewTransition,
)
from gateway_backend.domain.submission.review import (
    ReviewAction,
    ReviewEvent,
    ReviewEventKind,
    ReviewProjection,
    ReviewStatus,
    build_seed_projection,
    resolve_review_transition,
    review_allowed_transitions,
    validate_review_idempotency_key,
    validate_review_reason,
)
from gateway_backend.domain.workspace.models import IdentityContext

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

IDENTITY = IdentityContext(
    actor_id="actor-1",
    gateway_device_external_key="device-1",
    business_project_id="project-1",
    permissions=frozenset({"review_submission"}),
)

FINGERPRINT_BASE = {
    "action": ReviewAction.APPROVE,
    "business_project_id": "project-1",
    "expected_review_version": 0,
    "gateway_device_external_key": "device-1",
    "reason": None,
    "repository_id": "repository-1",
    "submission_id": "submission-1",
    "workspace_id": "workspace-1",
}

REVIEW_ALLOWED_TRANSITIONS = (
    (ReviewStatus.PENDING, ReviewAction.APPROVE, ReviewEventKind.APPROVED, ReviewStatus.APPROVED),
    (ReviewStatus.PENDING, ReviewAction.REJECT, ReviewEventKind.REJECTED, ReviewStatus.REJECTED),
    (
        ReviewStatus.PENDING,
        ReviewAction.RETURN_FOR_REVISION,
        ReviewEventKind.RETURNED_FOR_REVISION,
        ReviewStatus.RETURNED_FOR_REVISION,
    ),
    (ReviewStatus.PENDING, ReviewAction.WITHDRAW, ReviewEventKind.WITHDRAWN, ReviewStatus.WITHDRAWN),
    (
        ReviewStatus.APPROVED,
        ReviewAction.RETURN_FOR_REVISION,
        ReviewEventKind.RETURNED_FOR_REVISION,
        ReviewStatus.RETURNED_FOR_REVISION,
    ),
)

REVIEW_DENIED_TRANSITIONS = (
    (ReviewStatus.APPROVED, ReviewAction.APPROVE),
    (ReviewStatus.APPROVED, ReviewAction.REJECT),
    (ReviewStatus.APPROVED, ReviewAction.WITHDRAW),
    (ReviewStatus.REJECTED, ReviewAction.APPROVE),
    (ReviewStatus.REJECTED, ReviewAction.REJECT),
    (ReviewStatus.REJECTED, ReviewAction.RETURN_FOR_REVISION),
    (ReviewStatus.REJECTED, ReviewAction.WITHDRAW),
    (ReviewStatus.RETURNED_FOR_REVISION, ReviewAction.APPROVE),
    (ReviewStatus.RETURNED_FOR_REVISION, ReviewAction.REJECT),
    (ReviewStatus.RETURNED_FOR_REVISION, ReviewAction.RETURN_FOR_REVISION),
    (ReviewStatus.RETURNED_FOR_REVISION, ReviewAction.WITHDRAW),
    (ReviewStatus.WITHDRAWN, ReviewAction.APPROVE),
    (ReviewStatus.WITHDRAWN, ReviewAction.REJECT),
    (ReviewStatus.WITHDRAWN, ReviewAction.RETURN_FOR_REVISION),
    (ReviewStatus.WITHDRAWN, ReviewAction.WITHDRAW),
)

REVIEW_REASON_CASES = (
    ("approve_null", ReviewAction.APPROVE, None, None),
    ("withdraw_null", ReviewAction.WITHDRAW, None, None),
    ("reject_valid", ReviewAction.REJECT, "needs changes", "needs changes"),
    ("return_valid", ReviewAction.RETURN_FOR_REVISION, "revise section 2", "revise section 2"),
    ("approve_optional", ReviewAction.APPROVE, "looks good", "looks good"),
    ("reject_required_missing", ReviewAction.REJECT, None, InvalidReviewReason),
    ("return_required_missing", ReviewAction.RETURN_FOR_REVISION, None, InvalidReviewReason),
    ("approve_whitespace_only", ReviewAction.APPROVE, "   ", InvalidReviewReason),
    ("reject_whitespace_only", ReviewAction.REJECT, "\t\n", InvalidReviewReason),
    ("reason_control_char", ReviewAction.REJECT, "bad\x00reason", InvalidReviewReason),
    ("reason_del_char", ReviewAction.REJECT, "bad\x7freason", InvalidReviewReason),
    ("reason_surrogate", ReviewAction.REJECT, "bad\ud800reason", InvalidReviewReason),
    ("reason_noncharacter", ReviewAction.REJECT, "bad\uffffreason", InvalidReviewReason),
    ("reason_too_large", ReviewAction.REJECT, "x" * 4097, InvalidReviewReason),
)

REVIEW_IDEMPOTENCY_KEY_CASES = (
    ("valid_min", "!", "!"),
    ("valid_max_printable", "~" * 255, "~" * 255),
    ("empty", "", InvalidReviewIdempotencyKey),
    ("too_long", "a" * 256, InvalidReviewIdempotencyKey),
    ("space", " key", InvalidReviewIdempotencyKey),
    ("non_ascii", "キー", InvalidReviewIdempotencyKey),
    ("control", "key\x1f", InvalidReviewIdempotencyKey),
)

FINGERPRINT_SENSITIVITY_CASES = (
    ("action", ReviewAction.APPROVE, ReviewAction.REJECT),
    ("business_project_id", "project-1", "project-2"),
    ("expected_review_version", 0, 1),
    ("gateway_device_external_key", "device-1", "device-2"),
    ("reason", None, "note"),
    ("repository_id", "repository-1", "repository-2"),
    ("submission_id", "submission-1", "submission-2"),
    ("workspace_id", "workspace-1", "workspace-2"),
)


def _pending_projection() -> ReviewProjection:
    return ReviewProjection(
        submission_id="submission-1",
        status=ReviewStatus.PENDING,
        optimistic_version=0,
        latest_sequence=0,
        updated_by="actor-1",
        updated_at=TS0,
    )


def _apply_command(**overrides: Any) -> ApplyReviewCommand:
    base = ApplyReviewCommand(
        context=IDENTITY,
        submission_id="submission-1",
        expected_review_version=0,
        action=ReviewAction.APPROVE,
        reason=None,
        idempotency_key="review-key-1",
    )
    if not overrides:
        return base
    return ApplyReviewCommand(
        context=overrides.get("context", base.context),
        submission_id=overrides.get("submission_id", base.submission_id),
        expected_review_version=overrides.get("expected_review_version", base.expected_review_version),
        action=overrides.get("action", base.action),
        reason=overrides.get("reason", base.reason),
        idempotency_key=overrides.get("idempotency_key", base.idempotency_key),
    )


@pytest.mark.parametrize(
    ("current", "action", "expected_kind", "expected_status"),
    REVIEW_ALLOWED_TRANSITIONS,
)
def test_resolve_review_transition_allows_matrix(
    current: ReviewStatus,
    action: ReviewAction,
    expected_kind: ReviewEventKind,
    expected_status: ReviewStatus,
) -> None:
    event_kind, target = resolve_review_transition(current, action)
    assert event_kind is expected_kind
    assert target is expected_status


@pytest.mark.parametrize(("current", "action"), REVIEW_DENIED_TRANSITIONS)
def test_resolve_review_transition_denies_matrix(
    current: ReviewStatus,
    action: ReviewAction,
) -> None:
    with pytest.raises(InvalidReviewTransition) as exc_info:
        resolve_review_transition(current, action)
    assert exc_info.value.current == current.value
    assert exc_info.value.action == action.value


def test_review_transition_matrix_inventory_matches_policy_module() -> None:
    inventory = review_allowed_transitions()
    assert inventory[ReviewStatus.PENDING] == {
        ReviewAction.APPROVE: ReviewStatus.APPROVED,
        ReviewAction.REJECT: ReviewStatus.REJECTED,
        ReviewAction.RETURN_FOR_REVISION: ReviewStatus.RETURNED_FOR_REVISION,
        ReviewAction.WITHDRAW: ReviewStatus.WITHDRAWN,
    }
    assert inventory[ReviewStatus.APPROVED] == {
        ReviewAction.RETURN_FOR_REVISION: ReviewStatus.RETURNED_FOR_REVISION,
    }
    assert inventory[ReviewStatus.REJECTED] == {}
    assert inventory[ReviewStatus.RETURNED_FOR_REVISION] == {}
    assert inventory[ReviewStatus.WITHDRAWN] == {}


def test_build_seed_projection_maps_null_to_pending_only() -> None:
    event, projection = build_seed_projection(
        submission_id="submission-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    assert event.sequence == 0
    assert event.event_kind is ReviewEventKind.SUBMISSION_FINALIZED
    assert event.from_status is None
    assert event.to_status is ReviewStatus.PENDING
    assert projection.status is ReviewStatus.PENDING
    assert projection.optimistic_version == 0
    assert projection.latest_sequence == 0


def test_review_event_rejects_non_seed_submission_finalized() -> None:
    with pytest.raises(ValueError, match="from_status"):
        ReviewEvent(
            submission_id="submission-1",
            sequence=1,
            event_kind=ReviewEventKind.SUBMISSION_FINALIZED,
            from_status=ReviewStatus.PENDING,
            to_status=ReviewStatus.PENDING,
            reason=None,
            actor_id="actor-1",
            occurred_at=TS0,
        )


@pytest.mark.parametrize(("case_id", "action", "reason", "expected"), REVIEW_REASON_CASES)
def test_validate_review_reason_contract(
    case_id: str,
    action: ReviewAction,
    reason: str | None,
    expected: str | type[Exception] | None,
) -> None:
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            validate_review_reason(action, reason)
        return
    assert validate_review_reason(action, reason) == expected


def test_validate_review_reason_preserves_leading_and_trailing_whitespace() -> None:
    reason = "  keep spaces  "
    assert validate_review_reason(ReviewAction.REJECT, reason) == reason


@pytest.mark.parametrize(("case_id", "key", "expected"), REVIEW_IDEMPOTENCY_KEY_CASES)
def test_validate_review_idempotency_key_contract(
    case_id: str,
    key: str,
    expected: str | type[Exception],
) -> None:
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            validate_review_idempotency_key(key)
        return
    assert validate_review_idempotency_key(key) == expected


def test_compute_review_apply_request_fingerprint_golden() -> None:
    fingerprint = compute_review_apply_request_fingerprint(**cast(Any, FINGERPRINT_BASE))
    assert fingerprint == REVIEW_APPLY_FINGERPRINT_GOLDEN
    assert fingerprint.startswith("sha256:")


def test_compute_review_apply_request_fingerprint_is_deterministic() -> None:
    first = compute_review_apply_request_fingerprint(**cast(Any, FINGERPRINT_BASE))
    second = compute_review_apply_request_fingerprint(**cast(Any, FINGERPRINT_BASE))
    assert first == second


@pytest.mark.parametrize(("field_name", "baseline_value", "other_value"), FINGERPRINT_SENSITIVITY_CASES)
def test_compute_review_apply_request_fingerprint_changes_when_closed_object_changes(
    field_name: str,
    baseline_value: object,
    other_value: object,
) -> None:
    baseline = compute_review_apply_request_fingerprint(**cast(Any, FINGERPRINT_BASE))
    changed_payload = dict(FINGERPRINT_BASE)
    changed_payload[field_name] = other_value
    if field_name == "action" and other_value is ReviewAction.REJECT:
        changed_payload["reason"] = "needs work"
    changed = compute_review_apply_request_fingerprint(**cast(Any, changed_payload))
    assert changed != baseline


def test_validate_apply_review_command_accepts_valid_command() -> None:
    command = _apply_command(action=ReviewAction.REJECT, reason="needs work")
    assert validate_apply_review_command(command) is command


def test_validate_apply_review_command_rejects_invalid_transition_inputs() -> None:
    with pytest.raises(InvalidReviewReason):
        validate_apply_review_command(_apply_command(action=ReviewAction.REJECT, reason=None))


def test_review_facts_shape_uses_projection_and_ordered_events() -> None:
    projection = _pending_projection()
    event, _ = build_seed_projection(
        submission_id="submission-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    facts_projection = projection
    facts_events = (event,)
    assert facts_projection.status is ReviewStatus.PENDING
    assert facts_events[0].sequence == 0
