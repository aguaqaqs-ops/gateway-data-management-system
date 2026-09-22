"""Archive candidate integrity closure checks."""

from __future__ import annotations

from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
from gateway_backend.application.archive.ports import ArchiveControlTransaction
from gateway_backend.application.submission.errors import ReviewWorkspaceOccupancyConflict
from gateway_backend.application.submission.review import (
    assert_review_scope,
    assert_review_workspace_bindings,
)
from gateway_backend.domain.submission.errors import (
    ReviewClosureViolation,
    SubmissionBindingConflict,
)
from gateway_backend.domain.submission.models import SubmitAttemptState
from gateway_backend.domain.submission.ports import ArchiveCandidateFacts
from gateway_backend.domain.submission.policies import assert_submission_attempt_binding
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope


def assert_archive_candidate_integrity(
    unit_of_work: ArchiveControlTransaction,
    *,
    context: IdentityContext,
    resolved_scope: ResolvedScope,
    fact: ArchiveCandidateFacts,
) -> None:
    """Validate one approved archive candidate's Workspace and Attempt closure."""

    submission = fact.submission
    workspace = unit_of_work.workspace.get_workspace(submission.workspace_id)
    if workspace is None:
        raise ArchiveIntegrityFailure("candidate workspace is missing")
    occupancy = unit_of_work.submission.get_workspace_occupancy(submission.workspace_id)
    try:
        assert_review_scope(submission, workspace, resolved_scope, context)
        assert_review_workspace_bindings(submission, workspace, occupancy)
    except ReviewClosureViolation as exc:
        raise ArchiveIntegrityFailure(str(exc)) from exc
    except ReviewWorkspaceOccupancyConflict as exc:
        raise ArchiveIntegrityFailure(exc.reason) from exc
    except ScopeForbidden as exc:
        raise ArchiveIntegrityFailure(
            "repository scope does not match candidate workspace"
        ) from exc
    attempt = unit_of_work.submission.get_submit_attempt(submission.submit_attempt_id)
    if attempt is None:
        raise ArchiveIntegrityFailure("submit attempt is missing")
    if attempt.state is not SubmitAttemptState.FINALIZED:
        raise ArchiveIntegrityFailure("submit attempt is not finalized")
    try:
        assert_submission_attempt_binding(attempt=attempt, submission=submission)
    except SubmissionBindingConflict as exc:
        raise ArchiveIntegrityFailure(str(exc)) from exc
