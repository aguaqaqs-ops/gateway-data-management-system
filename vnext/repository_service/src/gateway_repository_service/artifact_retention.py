"""Durable eligibility rules for artifact bytes retention and cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from gateway_repository_contracts import OperationStatus

from gateway_repository_service.mutation_store import ArtifactLifecycleRecord
from gateway_repository_service.versioned_import.models import ArtifactOperationReference


class ArtifactBytesDeletionReason(str, Enum):
    ALREADY_DELETED = "already_deleted"
    PROTECTED = "protected"
    SUCCEEDED_IMMEDIATE = "succeeded_immediate"
    ORDINARY_FAILED_TTL = "ordinary_failed_ttl"
    ORPHAN_TTL = "orphan_ttl"
    TTL_NOT_ELAPSED = "ttl_not_elapsed"
    FAIL_CLOSED = "fail_closed"


@dataclass(frozen=True, slots=True)
class ArtifactBytesDeletionDecision:
    eligible: bool
    reason: ArtifactBytesDeletionReason
    earliest_eligible_at: datetime | None = None


def parse_durable_timestamp(value: str | None) -> datetime | None:
    """Parse a durable ISO timestamp; return None when missing or malformed."""

    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = datetime.fromisoformat(stripped.replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def decide_artifact_bytes_deletion(
    *,
    lifecycle: ArtifactLifecycleRecord | None,
    references: list[ArtifactOperationReference],
    now: datetime,
    ttl_seconds: int,
) -> ArtifactBytesDeletionDecision:
    """Return whether artifact ready bytes may be deleted under retention rules.

    Fail closed on missing/illegal timestamps, unparseable references, or
    contradictory durable evidence. Never deletes operations or metadata.
    """

    if ttl_seconds < 0:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    if lifecycle is None:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )
    if lifecycle.bytes_deleted_at is not None:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.ALREADY_DELETED,
        )

    try:
        for reference in references:
            _ = reference.operation_id
            _ = reference.durable_status
            _ = reference.is_protected
    except Exception:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )

    if any(reference.is_protected for reference in references):
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.PROTECTED,
        )

    if not references:
        created_at = parse_durable_timestamp(lifecycle.created_at)
        if created_at is None:
            return ArtifactBytesDeletionDecision(
                eligible=False,
                reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
            )
        earliest = created_at + timedelta(seconds=ttl_seconds)
        if now < earliest:
            return ArtifactBytesDeletionDecision(
                eligible=False,
                reason=ArtifactBytesDeletionReason.TTL_NOT_ELAPSED,
                earliest_eligible_at=earliest,
            )
        return ArtifactBytesDeletionDecision(
            eligible=True,
            reason=ArtifactBytesDeletionReason.ORPHAN_TTL,
            earliest_eligible_at=earliest,
        )

    has_succeeded = False
    ordinary_failed_completed: list[datetime] = []
    for reference in references:
        status = reference.status
        if status is None:
            # ADMISSION_PENDING is protected; any other unmapped status fails closed.
            return ArtifactBytesDeletionDecision(
                eligible=False,
                reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
            )
        if status == OperationStatus.SUCCEEDED:
            has_succeeded = True
            continue
        if status == OperationStatus.FAILED:
            completed_at = parse_durable_timestamp(reference.completed_at)
            if completed_at is None:
                return ArtifactBytesDeletionDecision(
                    eligible=False,
                    reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
                )
            ordinary_failed_completed.append(completed_at)
            continue
        # QUEUED/RUNNING should already be protected; anything else fails closed.
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )

    if has_succeeded:
        return ArtifactBytesDeletionDecision(
            eligible=True,
            reason=ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE,
        )

    if not ordinary_failed_completed:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )

    # Conservative boundary: wait until the latest ordinary failure's TTL elapses.
    boundary = max(ordinary_failed_completed)
    earliest = boundary + timedelta(seconds=ttl_seconds)
    if now < earliest:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.TTL_NOT_ELAPSED,
            earliest_eligible_at=earliest,
        )
    return ArtifactBytesDeletionDecision(
        eligible=True,
        reason=ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL,
        earliest_eligible_at=earliest,
    )


def retention_explains_missing_ready_bytes(
    *,
    lifecycle: ArtifactLifecycleRecord | None,
    repository_id: UUID,
    references: list[ArtifactOperationReference],
    consumed_operation_artifact_id: UUID | None = None,
) -> bool:
    """Return True when missing ready bytes are explained by recorded legal deletion."""

    if lifecycle is None:
        return False
    if lifecycle.repository_id != repository_id:
        return False
    if lifecycle.bytes_deleted_at is None:
        return False
    if parse_durable_timestamp(lifecycle.bytes_deleted_at) is None:
        return False
    if any(reference.is_protected for reference in references):
        return False
    if lifecycle.consumed_by_operation_id is not None:
        if consumed_operation_artifact_id != lifecycle.artifact_id:
            return False
        return True
    for reference in references:
        if reference.status is None:
            return False
        if reference.status not in {OperationStatus.FAILED, OperationStatus.SUCCEEDED}:
            return False
    return True
