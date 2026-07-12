from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..submissions import SubmissionRecord, SubmissionStatus
from .digests import compute_candidate_set_hash, compute_workspace_confirmation_set_hash
from .models import (
    ArchiveAnomalyResolutionRecord,
    BaselineBatchArchiveGateStatus,
    BaselineBatchStatus,
    ArchiveBatchRecord,
    ArchiveCandidateRecord,
    ArchiveCandidateRole,
    ArchiveCandidateStatus,
    WorkspaceArchiveConfirmationRecord,
)
from .policy import initial_history_resolution_failure


class ArchiveExecuteCommandProtocol(Protocol):
    workspace_confirmation_set_hash: str
    candidate_set_hash: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchiveBatchSnapshot:
    batch: ArchiveBatchRecord
    confirmations: tuple[WorkspaceArchiveConfirmationRecord, ...]
    candidates: tuple[ArchiveCandidateRecord, ...]
    anomaly_resolutions: tuple[ArchiveAnomalyResolutionRecord, ...]
    selected_modified_candidate_id: str | None
    selected_initial_candidate_ids: tuple[str, ...]
    workspace_confirmation_set_hash: str
    candidate_set_hash: str
    eligible_for_execute: bool
    failure_reasons: tuple[str, ...]


def build_batch_snapshot(
    *,
    batch: ArchiveBatchRecord,
    confirmations: tuple[WorkspaceArchiveConfirmationRecord, ...],
    candidates: tuple[ArchiveCandidateRecord, ...],
    anomaly_resolutions: tuple[ArchiveAnomalyResolutionRecord, ...],
    active_workspace_ids: set[str],
    require_submission: Callable[[str | None], SubmissionRecord],
) -> ArchiveBatchSnapshot:
    failure_reasons: list[str] = []
    if batch.status != BaselineBatchStatus.OPEN:
        failure_reasons.append("batch not open")
    if batch.archive_gate_status == BaselineBatchArchiveGateStatus.ARCHIVING:
        failure_reasons.append("archive in progress")
    if batch.archive_gate_status == BaselineBatchArchiveGateStatus.ARCHIVE_FROZEN:
        failure_reasons.append("archive gate frozen")

    confirmed_workspace_ids = {confirmation.workspace_id for confirmation in confirmations}
    if active_workspace_ids and not active_workspace_ids <= confirmed_workspace_ids:
        failure_reasons.append("unconfirmed workspace exists")

    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    for confirmation in confirmations:
        if (
            confirmation.status == confirmation.status.__class__.CONFIRMED_WITH_CANDIDATE
            and (
                confirmation.archive_candidate_id is None
                or confirmation.archive_candidate_id not in candidate_by_id
            )
        ):
            failure_reasons.append("candidate set incomplete")
            break

    modified_candidates = [
        candidate
        for candidate in candidates
        if candidate.selected_for_archive
        and candidate.role == ArchiveCandidateRole.MAINLINE_MODIFIED
        and candidate.status == ArchiveCandidateStatus.NOT_ARCHIVED
    ]
    selected_modified_candidate_id = batch.selected_modified_candidate_id if len(modified_candidates) == 1 else None
    selected_initial_candidate_ids = batch.selected_initial_candidate_ids
    if len(modified_candidates) == 0:
        failure_reasons.append("no modified candidate selected")
    elif len(modified_candidates) > 1:
        failure_reasons.append("multiple modified candidates selected")
    selected_modified_candidate = modified_candidates[0] if len(modified_candidates) == 1 else None
    if selected_modified_candidate is not None:
        try:
            selected_modified_submission = require_submission(selected_modified_candidate.source_submission_id)
        except Exception as exc:  # pragma: no cover - defensive guard
            failure_reasons.append(str(exc))
        else:
            if (
                selected_modified_submission.status is not SubmissionStatus.APPROVED
                and not selected_modified_candidate.override_reason
            ):
                failure_reasons.append("selected modified candidate requires override reason")

    initial_failure = initial_history_resolution_failure(
        candidates=candidates,
        anomaly_resolutions=anomaly_resolutions,
    )
    if initial_failure is not None:
        failure_reasons.append(initial_failure)

    workspace_confirmation_set_hash = compute_workspace_confirmation_set_hash(confirmations)
    candidate_set_hash = compute_candidate_set_hash(candidates)
    return ArchiveBatchSnapshot(
        batch=batch,
        confirmations=confirmations,
        candidates=candidates,
        anomaly_resolutions=anomaly_resolutions,
        selected_modified_candidate_id=selected_modified_candidate_id,
        selected_initial_candidate_ids=selected_initial_candidate_ids,
        workspace_confirmation_set_hash=workspace_confirmation_set_hash,
        candidate_set_hash=candidate_set_hash,
        eligible_for_execute=len(failure_reasons) == 0,
        failure_reasons=tuple(dict.fromkeys(reason for reason in failure_reasons if reason)),
    )


def ensure_snapshot_matches_command(
    snapshot: ArchiveBatchSnapshot,
    command: ArchiveExecuteCommandProtocol,
) -> None:
    if snapshot.workspace_confirmation_set_hash != command.workspace_confirmation_set_hash:
        raise ValueError("workspace confirmation set hash is stale")
    if snapshot.candidate_set_hash != command.candidate_set_hash:
        raise ValueError("candidate set hash is stale")
    if snapshot.selected_modified_candidate_id != command.selected_modified_candidate_id:
        raise ValueError("selected modified candidate does not match the dry-run snapshot")
    if snapshot.selected_initial_candidate_ids != tuple(command.selected_initial_candidate_ids):
        raise ValueError("selected initial candidate ids do not match the dry-run snapshot")
