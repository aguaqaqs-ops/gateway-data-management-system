"""Review domain models, transition policy and fingerprint contract tests."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from gateway_backend.application.submission.review_contracts import (
    REVIEW_APPLY_FINGERPRINT_GOLDEN,
    ApplyReviewCommand,
    ApplyReviewResult,
    ReviewFacts,
    build_apply_review_request_fingerprint_from_command,
    compute_review_apply_request_fingerprint,
    validate_apply_review_command,
)
from gateway_backend.domain.submission.errors import (
    InvalidReviewIdempotencyKey,
    InvalidReviewReason,
    InvalidReviewTransition,
    ReviewClosureViolation,
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
    validate_review_closure,
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

_NFC_E_ACUTE = "\u00e9"
_NFD_E_ACUTE = "e\u0301"
REVIEW_REASON_NORMALIZATION_CASES = (
    ("nfc_form", f"caf{_NFC_E_ACUTE}"),
    ("nfd_form", f"caf{_NFD_E_ACUTE}"),
)

INVALID_APPLY_REVIEW_COMMAND_CASES = (
    ("negative_version", {"expected_review_version": -1}, ValueError),
    ("empty_submission_id", {"submission_id": ""}, ValueError),
    ("invalid_key", {"idempotency_key": " "}, InvalidReviewIdempotencyKey),
    ("missing_reason", {"action": ReviewAction.REJECT, "reason": None}, InvalidReviewReason),
)

REVIEW_FACTS_CASES = (
    ("seed_only", (0,)),
    ("seed_and_approve", (0, 1)),
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


def _seed_event() -> ReviewEvent:
    event, _ = build_seed_projection(
        submission_id="submission-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    return event


def _approve_event(sequence: int) -> ReviewEvent:
    return _user_event(
        sequence,
        from_status=ReviewStatus.PENDING,
        to_status=ReviewStatus.APPROVED,
    )


def _user_event(
    sequence: int,
    *,
    from_status: ReviewStatus,
    to_status: ReviewStatus,
    event_kind: ReviewEventKind = ReviewEventKind.APPROVED,
) -> ReviewEvent:
    return ReviewEvent(
        submission_id="submission-1",
        sequence=sequence,
        event_kind=event_kind,
        from_status=from_status,
        to_status=to_status,
        reason=None,
        actor_id="actor-1",
        occurred_at=TS0,
    )


REVIEW_CLOSURE_VIOLATION_CASES: tuple[
    tuple[str, str, ReviewProjection | None, tuple[ReviewEvent, ...]],
    ...,
] = (
    (
        "missing_projection",
        "review projection is missing",
        None,
        (_seed_event(),),
    ),
    (
        "empty_events",
        "review event stream is empty",
        _pending_projection(),
        (),
    ),
    (
        "submission_id_mismatch",
        "review projection submission_id does not match events",
        _pending_projection(),
        (
            ReviewEvent(
                submission_id="submission-2",
                sequence=0,
                event_kind=ReviewEventKind.SUBMISSION_FINALIZED,
                from_status=None,
                to_status=ReviewStatus.PENDING,
                reason=None,
                actor_id="actor-1",
                occurred_at=TS0,
            ),
        ),
    ),
    (
        "missing_seed_event",
        "review event stream has no seed",
        _pending_projection(),
        (_approve_event(1),),
    ),
    (
        "from_status_chain_break",
        "review event from_status does not match previous to_status",
        _pending_projection(),
        (
            _seed_event(),
            _user_event(
                1,
                from_status=ReviewStatus.REJECTED,
                to_status=ReviewStatus.APPROVED,
            ),
        ),
    ),
    (
        "invalid_transition",
        "review event to_status does not match transition policy",
        _pending_projection(),
        (
            _seed_event(),
            _user_event(
                1,
                from_status=ReviewStatus.PENDING,
                to_status=ReviewStatus.REJECTED,
            ),
        ),
    ),
    (
        "optimistic_version_mismatch",
        "review projection optimistic_version does not match events",
        _pending_projection(),
        (_seed_event(), _approve_event(1)),
    ),
    (
        "sequence_gap",
        "review event sequence has a gap or duplicate",
        _pending_projection(),
        (_seed_event(), _approve_event(2)),
    ),
    (
        "latest_sequence_mismatch",
        "review projection latest_sequence does not match events",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.PENDING,
            optimistic_version=0,
            latest_sequence=5,
            updated_by="actor-1",
            updated_at=TS0,
        ),
        (_seed_event(),),
    ),
    (
        "status_mismatch",
        "review projection status does not match latest event",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.APPROVED,
            optimistic_version=0,
            latest_sequence=0,
            updated_by="actor-1",
            updated_at=TS0,
        ),
        (_seed_event(),),
    ),
    (
        "updated_by_mismatch",
        "review projection updated_by does not match latest event",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.PENDING,
            optimistic_version=0,
            latest_sequence=0,
            updated_by="actor-2",
            updated_at=TS0,
        ),
        (_seed_event(),),
    ),
    (
        "updated_at_mismatch",
        "review projection updated_at does not match latest event",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.PENDING,
            optimistic_version=0,
            latest_sequence=0,
            updated_by="actor-1",
            updated_at=datetime(2024, 6, 2, 12, 0, 0, tzinfo=UTC),
        ),
        (_seed_event(),),
    ),
    (
        "reject_required_missing",
        "review event reason violates action contract",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.REJECTED,
            optimistic_version=1,
            latest_sequence=1,
            updated_by="actor-1",
            updated_at=TS0,
        ),
        (
            _seed_event(),
            ReviewEvent(
                submission_id="submission-1",
                sequence=1,
                event_kind=ReviewEventKind.REJECTED,
                from_status=ReviewStatus.PENDING,
                to_status=ReviewStatus.REJECTED,
                reason=None,
                actor_id="actor-1",
                occurred_at=TS0,
            ),
        ),
    ),
    (
        "return_whitespace_only",
        "review event reason violates action contract",
        ReviewProjection(
            submission_id="submission-1",
            status=ReviewStatus.RETURNED_FOR_REVISION,
            optimistic_version=1,
            latest_sequence=1,
            updated_by="actor-1",
            updated_at=TS0,
        ),
        (
            _seed_event(),
            ReviewEvent(
                submission_id="submission-1",
                sequence=1,
                event_kind=ReviewEventKind.RETURNED_FOR_REVISION,
                from_status=ReviewStatus.PENDING,
                to_status=ReviewStatus.RETURNED_FOR_REVISION,
                reason="   ",
                actor_id="actor-1",
                occurred_at=TS0,
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    ("case_id", "expected_reason", "projection", "events"),
    REVIEW_CLOSURE_VIOLATION_CASES,
    ids=[case[0] for case in REVIEW_CLOSURE_VIOLATION_CASES],
)
def test_validate_review_closure_rejects_violations(
    case_id: str,
    expected_reason: str,
    projection: ReviewProjection | None,
    events: tuple[ReviewEvent, ...],
) -> None:
    with pytest.raises(ReviewClosureViolation, match=expected_reason):
        validate_review_closure(projection, events)


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


@pytest.mark.parametrize(("case_id", "overrides", "expected_error"), INVALID_APPLY_REVIEW_COMMAND_CASES)
def test_validate_apply_review_command_rejects_invalid_inputs(
    case_id: str,
    overrides: dict[str, Any],
    expected_error: type[Exception],
) -> None:
    with pytest.raises(expected_error):
        validate_apply_review_command(_apply_command(**overrides))


def test_validate_apply_review_command_rejects_wrong_action_type() -> None:
    command = ApplyReviewCommand(
        context=IDENTITY,
        submission_id="submission-1",
        expected_review_version=0,
        action=cast(ReviewAction, "APPROVE"),
        reason=None,
        idempotency_key="review-key-1",
    )
    with pytest.raises(ValueError, match="action must be ReviewAction"):
        validate_apply_review_command(command)


def test_validate_apply_review_command_accepts_valid_command() -> None:
    command = _apply_command(action=ReviewAction.REJECT, reason="needs work")
    assert validate_apply_review_command(command) is command


@pytest.mark.parametrize(("case_id", "reason"), REVIEW_REASON_NORMALIZATION_CASES)
def test_validate_review_reason_preserves_unicode_normalization_form(
    case_id: str,
    reason: str,
) -> None:
    assert validate_review_reason(ReviewAction.REJECT, reason) == reason


def test_compute_review_apply_request_fingerprint_does_not_normalize_reason() -> None:
    nfc_reason = f"needs {_NFC_E_ACUTE} review"
    nfd_reason = f"needs {_NFD_E_ACUTE} review"
    assert unicodedata.normalize("NFC", nfc_reason) == unicodedata.normalize("NFC", nfd_reason)
    nfc_fingerprint = compute_review_apply_request_fingerprint(
        **cast(
            Any,
            {**FINGERPRINT_BASE, "action": ReviewAction.REJECT, "reason": nfc_reason},
        )
    )
    nfd_fingerprint = compute_review_apply_request_fingerprint(
        **cast(
            Any,
            {**FINGERPRINT_BASE, "action": ReviewAction.REJECT, "reason": nfd_reason},
        )
    )
    assert nfc_fingerprint != nfd_fingerprint


def test_build_apply_review_request_fingerprint_from_command_matches_scope_closure() -> None:
    command = _apply_command(action=ReviewAction.REJECT, reason="needs work")
    fingerprint = build_apply_review_request_fingerprint_from_command(
        command=command,
        workspace_id="workspace-1",
        repository_id="repository-1",
    )
    expected = compute_review_apply_request_fingerprint(
        action=ReviewAction.REJECT,
        business_project_id="project-1",
        expected_review_version=0,
        gateway_device_external_key="device-1",
        reason="needs work",
        repository_id="repository-1",
        submission_id="submission-1",
        workspace_id="workspace-1",
    )
    assert fingerprint == expected


def test_apply_review_result_carries_request_fingerprint() -> None:
    event, projection = build_seed_projection(
        submission_id="submission-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    result = ApplyReviewResult(
        event=event,
        projection=projection,
        request_fingerprint=REVIEW_APPLY_FINGERPRINT_GOLDEN,
        replay=False,
    )
    assert result.request_fingerprint == REVIEW_APPLY_FINGERPRINT_GOLDEN


@pytest.mark.parametrize(("case_id", "sequences"), REVIEW_FACTS_CASES)
def test_review_facts_preserves_projection_and_event_tuple(
    case_id: str,
    sequences: tuple[int, ...],
) -> None:
    projection = _pending_projection()
    seed_event, _ = build_seed_projection(
        submission_id="submission-1",
        actor_id="actor-1",
        occurred_at=TS0,
    )
    events: list[ReviewEvent] = [seed_event]
    if 1 in sequences:
        event_kind, to_status = resolve_review_transition(
            ReviewStatus.PENDING,
            ReviewAction.APPROVE,
        )
        events.append(
            ReviewEvent(
                submission_id="submission-1",
                sequence=1,
                event_kind=event_kind,
                from_status=ReviewStatus.PENDING,
                to_status=to_status,
                reason=None,
                actor_id="actor-1",
                occurred_at=TS0,
            )
        )
    facts = ReviewFacts(projection=projection, events=tuple(events))
    assert facts.projection is projection
    assert tuple(event.sequence for event in facts.events) == sequences
    # Ascending event order is enforced by ReviewReadPort.list_events, not ReviewFacts.
