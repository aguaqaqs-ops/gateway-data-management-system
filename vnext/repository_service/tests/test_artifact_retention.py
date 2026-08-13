"""Contract tests for durable artifact bytes eligibility."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.artifact_retention import (
    ArtifactBytesDeletionReason,
    decide_artifact_bytes_deletion,
)
from gateway_repository_service.versioned_import.models import ArtifactOperationReference
from support.artifact_cleanup_contract import (
    BASE_NOW,
    CREATED_AT,
    OPERATION_ID,
    ORPHAN_TTL_BOUNDARY_CASES,
    OTHER_ARTIFACT_ID,
    PROTECTED_REFERENCE_CASES,
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
