"""Contract tests for durable artifact bytes eligibility."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
    retention_explains_missing_ready_bytes,
)
from gateway_repository_service.versioned_import.models import ArtifactOperationReference
from support.artifact_cleanup_contract import (
    BASE_NOW,
    CREATED_AT,
    OPERATION_ID,
    ORPHAN_TTL_BOUNDARY_CASES,
    OTHER_ARTIFACT_ID,
    OTHER_OPERATION_ID,
    MALFORMED_REFERENCE_CASES,
    PROTECTED_REFERENCE_CASES,
    REPOSITORY_ID,
    TTL_BOUNDARY_CASES,
    lifecycle,
    succeeded_reference,
)


@pytest.mark.parametrize(
    ("_label", "delta", "eligible", "reason"),
    TTL_BOUNDARY_CASES,
    ids=[case[0] for case in TTL_BOUNDARY_CASES],
)
def test_ordinary_failed_ttl_boundaries(
    _label: str,
    delta: timedelta,
    eligible: bool,
    reason: ArtifactBytesDeletionReason,
) -> None:
    completed_at = "2026-08-01T12:00:00+00:00"
    boundary = datetime.fromisoformat(completed_at)
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[
            ArtifactOperationReference(
                operation_id=OPERATION_ID,
                durable_status=OperationStatus.FAILED.value,
                status=OperationStatus.FAILED,
                is_protected=False,
                completed_at=completed_at,
                error_code="IMPORT_REJECTED",
            )
        ],
        now=boundary + timedelta(seconds=3600) + delta,
        ttl_seconds=3600,
    )
    assert decision.eligible is eligible
    assert decision.reason is reason


@pytest.mark.parametrize(
    ("_label", "delta", "eligible", "reason"),
    ORPHAN_TTL_BOUNDARY_CASES,
    ids=[case[0] for case in ORPHAN_TTL_BOUNDARY_CASES],
)
def test_orphan_ttl_boundaries(
    _label: str,
    delta: timedelta,
    eligible: bool,
    reason: ArtifactBytesDeletionReason,
) -> None:
    created = datetime.fromisoformat(CREATED_AT)
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[],
        now=created + timedelta(seconds=3600) + delta,
        ttl_seconds=3600,
    )
    assert decision.eligible is eligible
    assert decision.reason is reason


@pytest.mark.parametrize(
    ("_label", "reference"),
    PROTECTED_REFERENCE_CASES,
    ids=[case[0] for case in PROTECTED_REFERENCE_CASES],
)
def test_protected_references_are_retained(
    _label: str,
    reference: ArtifactOperationReference,
) -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[reference],
        now=BASE_NOW,
        ttl_seconds=3600,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.PROTECTED


def test_succeeded_matching_consumed_is_immediately_eligible() -> None:
    completed = "2026-08-02T00:00:00+00:00"
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(
            consumed_by_operation_id=OPERATION_ID,
            consumed_at=completed,
        ),
        references=[succeeded_reference(completed_at=completed)],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is True
    assert decision.reason is ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE


def test_succeeded_without_consumption_is_not_eligible() -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[succeeded_reference()],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_succeeded_result_artifact_mismatch_is_not_eligible() -> None:
    completed = "2026-08-02T00:00:00+00:00"
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(
            consumed_by_operation_id=OPERATION_ID,
            consumed_at=completed,
        ),
        references=[
            succeeded_reference(
                completed_at=completed,
                result_artifact_id=OTHER_ARTIFACT_ID,
            )
        ],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_succeeded_invalid_projection_is_not_eligible() -> None:
    completed = "2026-08-02T00:00:00+00:00"
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(
            consumed_by_operation_id=OPERATION_ID,
            consumed_at=completed,
        ),
        references=[
            succeeded_reference(
                completed_at=completed,
                projection_valid=False,
            )
        ],
        now=BASE_NOW,
        ttl_seconds=86400,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_already_deleted_is_not_eligible() -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(bytes_deleted_at="2026-08-03T00:00:00+00:00"),
        references=[],
        now=BASE_NOW,
        ttl_seconds=3600,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.ALREADY_DELETED


def test_malformed_created_at_fails_closed() -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(created_at="not-a-timestamp"),
        references=[],
        now=BASE_NOW,
        ttl_seconds=1,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


@pytest.mark.parametrize(
    ("_label", "reference"),
    MALFORMED_REFERENCE_CASES,
    ids=[case[0] for case in MALFORMED_REFERENCE_CASES],
)
def test_malformed_reference_evidence_fails_closed(
    _label: str,
    reference: ArtifactOperationReference,
) -> None:
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[reference],
        now=BASE_NOW + timedelta(days=30),
        ttl_seconds=1,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.FAIL_CLOSED


def test_multi_ordinary_failed_uses_conservative_latest_completed_at() -> None:
    earlier = "2026-08-01T00:00:00+00:00"
    later = "2026-08-01T12:00:00+00:00"
    references = [
        ArtifactOperationReference(
            operation_id=OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at=earlier,
            error_code="IMPORT_REJECTED",
        ),
        ArtifactOperationReference(
            operation_id=OTHER_OPERATION_ID,
            durable_status=OperationStatus.FAILED.value,
            status=OperationStatus.FAILED,
            is_protected=False,
            completed_at=later,
            error_code="VERIFICATION_FAILED_NOT_PUBLISHED",
        ),
    ]
    before_latest_ttl = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=references,
        now=datetime.fromisoformat(later) + timedelta(seconds=3599),
        ttl_seconds=3600,
    )
    assert before_latest_ttl.eligible is False
    after_latest_ttl = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=references,
        now=datetime.fromisoformat(later) + timedelta(seconds=3600),
        ttl_seconds=3600,
    )
    assert after_latest_ttl.eligible is True
    assert after_latest_ttl.reason is ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL


def test_premature_bytes_deleted_at_does_not_explain_missing_bytes() -> None:
    stamped = lifecycle(bytes_deleted_at="2026-08-01T00:30:00+00:00")
    now = datetime(2026, 8, 2, tzinfo=UTC)
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=stamped,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=3600,
            now=now,
        )
        is False
    )
    decision = decide_artifact_bytes_deletion(
        lifecycle=lifecycle(),
        references=[],
        now=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
        ttl_seconds=3600,
    )
    assert decision.eligible is False
    assert decision.reason is ArtifactBytesDeletionReason.TTL_NOT_ELAPSED


def test_naive_and_future_bytes_deleted_at_fail_closed() -> None:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    naive = lifecycle(bytes_deleted_at="2026-08-02T00:00:00")
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=naive,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=1,
            now=now,
        )
        is False
    )
    future = lifecycle(bytes_deleted_at="2026-08-03T00:00:00+00:00")
    assert (
        retention_explains_missing_ready_bytes(
            lifecycle=future,
            repository_id=REPOSITORY_ID,
            references=[],
            ttl_seconds=1,
            now=now,
        )
        is False
    )
