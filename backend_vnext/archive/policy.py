from __future__ import annotations

from ..submissions import SubmissionStatus
from .models import (
    ArchiveAnomalyResolutionRecord,
    ArchiveCandidateRecord,
    ArchiveCandidateRole,
    ArchiveCandidateSourceKind,
    BaselineBatchArchiveGateStatus,
    BaselineBatchStatus,
)


def candidate_source_kind_from_submission(status: SubmissionStatus) -> ArchiveCandidateSourceKind:
    if status is SubmissionStatus.APPROVED:
        return ArchiveCandidateSourceKind.APPROVED_SUBMISSION
    if status is SubmissionStatus.REJECTED:
        return ArchiveCandidateSourceKind.REJECTED_SUBMISSION
    if status is SubmissionStatus.WITHDRAWN:
        return ArchiveCandidateSourceKind.WITHDRAWN_SUBMISSION
    return ArchiveCandidateSourceKind.WORKSPACE_PREVIEW


def require_batch_open(batch, *, action: str) -> None:
    if batch.status != BaselineBatchStatus.OPEN:
        raise ValueError(f"{action} requires OPEN batch")
    if batch.archive_gate_status in {
        BaselineBatchArchiveGateStatus.ARCHIVING,
        BaselineBatchArchiveGateStatus.ARCHIVE_FROZEN,
        BaselineBatchArchiveGateStatus.ARCHIVED,
    }:
        raise ValueError(f"{action} requires an unfrozen archive gate")


def validate_mainline_candidate(candidate: ArchiveCandidateRecord) -> None:
    if candidate.selected_for_archive and candidate.role == ArchiveCandidateRole.MAINLINE_MODIFIED:
        candidate.ensure_selectable_as_mainline()


def initial_history_resolution_failure(
    *,
    candidates: tuple[ArchiveCandidateRecord, ...],
    anomaly_resolutions: tuple[ArchiveAnomalyResolutionRecord, ...],
) -> str | None:
    resolution_by_candidate = {
        resolution.candidate_id: resolution for resolution in anomaly_resolutions
    }
    for candidate in candidates:
        if (
            candidate.selected_for_archive
            and candidate.role == ArchiveCandidateRole.BASELINE_INITIAL_HISTORY
            and candidate.anomaly_resolution_required
            and candidate.candidate_id not in resolution_by_candidate
        ):
            return "selected initial history missing anomaly resolution"
    return None
