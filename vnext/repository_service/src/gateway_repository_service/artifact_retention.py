"""Durable eligibility rules for artifact bytes retention and cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from gateway_repository_contracts import OperationStatus

from gateway_repository_service.mutation_store import ArtifactLifecycleRecord
from gateway_repository_service.versioned_import.models import (
    IMPORT_ADMISSION_PENDING_STATUS,
    MANUAL_RECOVERY_REQUIRED_CODE,
    ORDINARY_TERMINAL_ERROR_CODES,
    ArtifactOperationReference,
)


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


@dataclass(frozen=True, slots=True)
class ArtifactRetentionBoundary:
    """Retention boundary ignoring any existing bytes_deleted_at stamp."""

    reason: ArtifactBytesDeletionReason
    earliest_eligible_at: datetime | None = None
    immediate: bool = False


def parse_durable_timestamp(value: str | None) -> datetime | None:
    """Parse a durable ISO timestamp; naive/malformed values fail closed."""

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
        # Durable evidence must carry an explicit timezone.
        return None
    return parsed.astimezone(UTC)


def _normalize_now(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def compute_retention_boundary(
    *,
    lifecycle: ArtifactLifecycleRecord | None,
    references: list[ArtifactOperationReference],
    ttl_seconds: int,
) -> ArtifactRetentionBoundary:
    """Compute the earliest legal deletion boundary, ignoring bytes_deleted_at."""

    if ttl_seconds < 0:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
    if lifecycle is None:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    created_at = parse_durable_timestamp(lifecycle.created_at)
    if created_at is None:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    consumed_at = parse_durable_timestamp(lifecycle.consumed_at)
    has_consumed_operation = lifecycle.consumed_by_operation_id is not None
    has_consumed_timestamp = lifecycle.consumed_at is not None
    if has_consumed_operation != has_consumed_timestamp:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
    if has_consumed_timestamp and consumed_at is None:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    try:
        operation_ids: set[UUID] = set()
        for reference in references:
            if reference.operation_id in operation_ids:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            operation_ids.add(reference.operation_id)
            if reference.durable_status == IMPORT_ADMISSION_PENDING_STATUS:
                if (
                    reference.status is not None
                    or not reference.is_protected
                    or reference.completed_at is not None
                    or reference.error_code is not None
                ):
                    return ArtifactRetentionBoundary(
                        reason=ArtifactBytesDeletionReason.FAIL_CLOSED
                    )
                continue
            status = reference.status
            if status is None or reference.durable_status != status.value:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            if status in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
                if (
                    not reference.is_protected
                    or reference.completed_at is not None
                    or reference.error_code is not None
                ):
                    return ArtifactRetentionBoundary(
                        reason=ArtifactBytesDeletionReason.FAIL_CLOSED
                    )
                continue
            completed_at = parse_durable_timestamp(reference.completed_at)
            if completed_at is None or completed_at < created_at:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            if status == OperationStatus.SUCCEEDED:
                if (
                    reference.is_protected
                    or reference.error_code is not None
                    or not reference.projection_valid
                    or reference.result_artifact_id is None
                ):
                    return ArtifactRetentionBoundary(
                        reason=ArtifactBytesDeletionReason.FAIL_CLOSED
                    )
                continue
            if status != OperationStatus.FAILED:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            if reference.error_code == MANUAL_RECOVERY_REQUIRED_CODE:
                if not reference.is_protected:
                    return ArtifactRetentionBoundary(
                        reason=ArtifactBytesDeletionReason.FAIL_CLOSED
                    )
                continue
            if (
                reference.is_protected
                or reference.error_code not in ORDINARY_TERMINAL_ERROR_CODES
            ):
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
    except Exception:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    if any(reference.is_protected for reference in references):
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.PROTECTED)

    if not references:
        if has_consumed_operation:
            return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
        earliest = created_at + timedelta(seconds=ttl_seconds)
        return ArtifactRetentionBoundary(
            reason=ArtifactBytesDeletionReason.ORPHAN_TTL,
            earliest_eligible_at=earliest,
        )

    has_succeeded = False
    succeeded_completed: list[datetime] = []
    ordinary_failed_completed: list[datetime] = []
    for reference in references:
        status = reference.status
        if status is None:
            return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
        if status == OperationStatus.SUCCEEDED:
            has_succeeded = True
            completed_at = parse_durable_timestamp(reference.completed_at)
            if completed_at is None:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            succeeded_completed.append(completed_at)
            continue
        if status == OperationStatus.FAILED:
            completed_at = parse_durable_timestamp(reference.completed_at)
            if completed_at is None:
                return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
            ordinary_failed_completed.append(completed_at)
            continue
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    if has_succeeded:
        if not has_consumed_operation or consumed_at is None:
            return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
        matching_consumed = [
            reference
            for reference in references
            if reference.operation_id == lifecycle.consumed_by_operation_id
        ]
        if (
            len(matching_consumed) != 1
            or matching_consumed[0].status != OperationStatus.SUCCEEDED
            or not matching_consumed[0].projection_valid
            or matching_consumed[0].result_artifact_id != lifecycle.artifact_id
        ):
            return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)
        earliest = max(succeeded_completed)
        earliest = max(earliest, consumed_at)
        return ArtifactRetentionBoundary(
            reason=ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE,
            earliest_eligible_at=earliest,
            immediate=True,
        )

    if has_consumed_operation:
        # Consumption without a valid SUCCEEDED projection is contradictory.
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    if not ordinary_failed_completed:
        return ArtifactRetentionBoundary(reason=ArtifactBytesDeletionReason.FAIL_CLOSED)

    boundary = max(ordinary_failed_completed)
    earliest = boundary + timedelta(seconds=ttl_seconds)
    return ArtifactRetentionBoundary(
        reason=ArtifactBytesDeletionReason.ORDINARY_FAILED_TTL,
        earliest_eligible_at=earliest,
    )


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

    now = _normalize_now(now)
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

    boundary = compute_retention_boundary(
        lifecycle=lifecycle,
        references=references,
        ttl_seconds=ttl_seconds,
    )
    if boundary.reason in {
        ArtifactBytesDeletionReason.FAIL_CLOSED,
        ArtifactBytesDeletionReason.PROTECTED,
    }:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=boundary.reason,
            earliest_eligible_at=boundary.earliest_eligible_at,
        )
    if boundary.immediate:
        if boundary.earliest_eligible_at is not None and now < boundary.earliest_eligible_at:
            return ArtifactBytesDeletionDecision(
                eligible=False,
                reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
                earliest_eligible_at=boundary.earliest_eligible_at,
            )
        return ArtifactBytesDeletionDecision(
            eligible=True,
            reason=ArtifactBytesDeletionReason.SUCCEEDED_IMMEDIATE,
        )
    earliest = boundary.earliest_eligible_at
    if earliest is None:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.FAIL_CLOSED,
        )
    if now < earliest:
        return ArtifactBytesDeletionDecision(
            eligible=False,
            reason=ArtifactBytesDeletionReason.TTL_NOT_ELAPSED,
            earliest_eligible_at=earliest,
        )
    return ArtifactBytesDeletionDecision(
        eligible=True,
        reason=boundary.reason,
        earliest_eligible_at=earliest,
    )


def retention_explains_missing_ready_bytes(
    *,
    lifecycle: ArtifactLifecycleRecord | None,
    repository_id: UUID,
    references: list[ArtifactOperationReference],
    ttl_seconds: int,
    now: datetime | None = None,
    consumed_operation_artifact_id: UUID | None = None,
) -> bool:
    """Return True when missing ready bytes are explained by recorded legal deletion."""

    if lifecycle is None:
        return False
    if lifecycle.repository_id != repository_id:
        return False
    if lifecycle.bytes_deleted_at is None:
        return False

    deleted_at = parse_durable_timestamp(lifecycle.bytes_deleted_at)
    if deleted_at is None:
        return False

    clock = _normalize_now(now if now is not None else datetime.now(UTC))
    if deleted_at > clock:
        return False

    if any(reference.is_protected for reference in references):
        return False

    has_succeeded_reference = any(
        reference.status == OperationStatus.SUCCEEDED for reference in references
    )
    if has_succeeded_reference:
        if (
            lifecycle.consumed_by_operation_id is None
            or lifecycle.consumed_at is None
            or consumed_operation_artifact_id != lifecycle.artifact_id
        ):
            return False
    elif lifecycle.consumed_by_operation_id is not None or lifecycle.consumed_at is not None:
        return False

    boundary = compute_retention_boundary(
        lifecycle=lifecycle,
        references=references,
        ttl_seconds=ttl_seconds,
    )
    if boundary.reason in {
        ArtifactBytesDeletionReason.FAIL_CLOSED,
        ArtifactBytesDeletionReason.PROTECTED,
    }:
        return False
    if boundary.immediate:
        earliest = boundary.earliest_eligible_at
        return earliest is not None and deleted_at >= earliest
    earliest = boundary.earliest_eligible_at
    if earliest is None:
        return False
    return deleted_at >= earliest
