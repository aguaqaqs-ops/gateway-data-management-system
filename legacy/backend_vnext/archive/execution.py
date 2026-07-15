from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..contracts.repository import (
    PromoteMainlineInitialHistoryCandidate,
    PromoteMainlineRequest,
    RefKind,
    RefPurpose,
    RefRetentionOwnerKind,
    RepositoryRefSnapshot,
)

from ..submissions import SubmissionRecord
from .models import ArchiveBatchRecord, ArchiveCandidateRecord


def build_repository_ref_snapshot(
    *,
    batch: ArchiveBatchRecord,
    submission: SubmissionRecord,
    candidate_id: str,
    operation_id: str,
) -> RepositoryRefSnapshot:
    repository_ref = submission.repository_target_ref
    if repository_ref is None:
        raise ValueError("submission is missing repository_target_ref")
    commit_hash = submission.repository_commit_hash
    if commit_hash is None:
        raise ValueError("submission is missing repository_commit_hash")
    return RepositoryRefSnapshot(
        repository_id=batch.repository_id,
        ref=repository_ref,
        kind=RefKind.BRANCH,
        purpose=RefPurpose.ARCHIVE_CANDIDATE,
        owner_kind=RefRetentionOwnerKind.ARCHIVE_CANDIDATE,
        owner_id=candidate_id,
        commit_hash=commit_hash,
        created_by_operation_id=operation_id,
        created_at=datetime.now(timezone.utc),
    )


def build_promote_mainline_request(
    *,
    batch: ArchiveBatchRecord,
    selected_modified: ArchiveCandidateRecord,
    selected_initial_candidates: list[ArchiveCandidateRecord],
    require_submission: Callable[[str | None], SubmissionRecord],
    idempotency_key: str,
    request_hash: str,
    override_reason: str | None,
) -> PromoteMainlineRequest:
    selected_modified_submission = require_submission(selected_modified.source_submission_id)
    selected_modified_snapshot = build_repository_ref_snapshot(
        batch=batch,
        submission=selected_modified_submission,
        candidate_id=selected_modified.candidate_id,
        operation_id=f"archive-promote-{batch.batch_id}",
    )
    initial_candidates: list[PromoteMainlineInitialHistoryCandidate] = []
    for candidate in selected_initial_candidates:
        submission = require_submission(candidate.source_submission_id)
        snapshot = build_repository_ref_snapshot(
            batch=batch,
            submission=submission,
            candidate_id=candidate.candidate_id,
            operation_id=f"archive-promote-{batch.batch_id}",
        )
        initial_candidates.append(
            PromoteMainlineInitialHistoryCandidate(
                candidate_id=candidate.candidate_id,
                ref_snapshot=snapshot,
                history_commit_hash=submission.repository_commit_hash or "",
            )
        )
    return PromoteMainlineRequest(
        repository_id=batch.repository_id,
        batch_id=batch.batch_id,
        expected_base_main_hash=batch.base_main_hash,
        selected_modified_candidate_id=selected_modified.candidate_id,
        selected_modified_ref_snapshot=selected_modified_snapshot,
        selected_modified_commit_hash=selected_modified_submission.repository_commit_hash or "",
        selected_initial_history_candidates=tuple(initial_candidates),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )


def mark_archive_statuses(
    *,
    batch: ArchiveBatchRecord,
    selected_modified_candidate: ArchiveCandidateRecord,
    selected_initial_candidates: list[ArchiveCandidateRecord],
    archive_store,
    submission_store,
    workspace_store,
) -> ArchiveBatchRecord:
    selected_initial_ids = {candidate.candidate_id for candidate in selected_initial_candidates}
    selected_initial_submission_ids = {
        candidate.source_submission_id
        for candidate in selected_initial_candidates
        if candidate.source_submission_id is not None
    }
    modified_submission_id = selected_modified_candidate.source_submission_id
    for candidate in archive_store.list_candidates_by_batch(batch.batch_id):
        if candidate.candidate_id == selected_modified_candidate.candidate_id:
            updated = candidate.mark_archived_as_mainline()
        elif candidate.candidate_id in selected_initial_ids:
            updated = candidate.mark_archived_as_history()
        else:
            updated = candidate.mark_closed_not_archived()
        archive_store.save_candidate(updated, expected_version=candidate.version)
    for submission in submission_store.list_by_batch(batch.batch_id):
        if submission.submission_id == modified_submission_id:
            updated_submission = submission.mark_archived_as_mainline()
        elif submission.submission_id in selected_initial_submission_ids:
            updated_submission = submission.mark_archived_as_history()
        else:
            updated_submission = submission.mark_closed_not_archived()
        submission_store.save(updated_submission, expected_version=submission.version)
    for workspace in workspace_store.list_by_batch(batch.batch_id):
        closed = workspace.close()
        workspace_store.save(closed, expected_version=workspace.version)
    return batch
