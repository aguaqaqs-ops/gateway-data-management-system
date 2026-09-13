"""SubmitAttempt state machine and field co-presence policies."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from gateway_backend.domain.submission.errors import (
    InvalidSubmitAttemptTransition,
    SubmissionBindingConflict,
    SubmitAttemptInvariantViolation,
)
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
    Submission,
)

_ALLOWED_TRANSITIONS: dict[SubmitAttemptState, frozenset[SubmitAttemptState]] = {
    SubmitAttemptState.PREPARED: frozenset(
        {SubmitAttemptState.EFFECT_PENDING, SubmitAttemptState.ABORTED}
    ),
    SubmitAttemptState.EFFECT_PENDING: frozenset(
        {SubmitAttemptState.FINALIZED, SubmitAttemptState.ABORTED}
    ),
    SubmitAttemptState.FINALIZED: frozenset(),
    SubmitAttemptState.ABORTED: frozenset(),
}


def assert_submit_attempt_invariants(attempt: SubmitAttempt) -> None:
    has_manifest_ref = attempt.canonicalization_manifest_ref is not None
    has_manifest_digest = attempt.canonicalization_manifest_digest is not None
    if has_manifest_ref != has_manifest_digest:
        raise SubmitAttemptInvariantViolation(
            "canonicalization manifest ref and digest must appear together"
        )

    if attempt.repository_import_artifact_ref is not None and not has_manifest_ref:
        raise SubmitAttemptInvariantViolation(
            "repository import artifact requires canonicalization manifest ref/digest"
        )

    if attempt.repository_artifact_ref is not None and attempt.repository_import_artifact_ref is None:
        raise SubmitAttemptInvariantViolation(
            "repository artifact ref requires backend import artifact ref"
        )

    if attempt.repository_operation_id is not None and attempt.repository_artifact_ref is None:
        raise SubmitAttemptInvariantViolation(
            "repository operation identity requires repository artifact ref"
        )

    if attempt.state is SubmitAttemptState.FINALIZED:
        if attempt.submission_id is None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt requires submission_id")
        if attempt.finalized_at is None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt requires finalized_at")
        if attempt.abort_code is not None or attempt.aborted_at is not None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt must not carry abort fields")
    elif attempt.submission_id is not None:
        raise SubmitAttemptInvariantViolation("submission_id is only allowed in FINALIZED state")

    if attempt.state is SubmitAttemptState.ABORTED:
        if attempt.abort_code is None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt requires abort_code")
        if attempt.aborted_at is None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt requires aborted_at")
        if attempt.submission_id is not None or attempt.finalized_at is not None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt must not carry finalize fields")
    elif attempt.abort_code is not None or attempt.aborted_at is not None:
        raise SubmitAttemptInvariantViolation("abort fields are only allowed in ABORTED state")

    if attempt.state is SubmitAttemptState.EFFECT_PENDING and attempt.effect_pending_at is None:
        raise SubmitAttemptInvariantViolation("EFFECT_PENDING attempt requires effect_pending_at")


def transition_attempt_state(
    attempt: SubmitAttempt,
    *,
    target: SubmitAttemptState,
    **changes: Any,
) -> SubmitAttempt:
    allowed = _ALLOWED_TRANSITIONS[attempt.state]
    if target not in allowed:
        raise InvalidSubmitAttemptTransition(current=attempt.state.value, target=target.value)
    return replace(attempt, state=target, **changes)


def assert_submission_attempt_binding(*, attempt: SubmitAttempt, submission: Submission) -> None:
    if submission.submit_attempt_id != attempt.submit_attempt_id:
        raise SubmissionBindingConflict("submission submit_attempt_id must match attempt")
    if submission.workspace_id != attempt.workspace_id:
        raise SubmissionBindingConflict("submission workspace_id must match attempt")
    if submission.workspace_generation != attempt.workspace_generation:
        raise SubmissionBindingConflict("submission workspace_generation must match attempt")
    if submission.upload_revision_id != attempt.upload_revision_id:
        raise SubmissionBindingConflict("submission upload_revision_id must match attempt")
    if submission.preview_result_id != attempt.preview_result_id:
        raise SubmissionBindingConflict("submission preview_result_id must match attempt")
    if submission.repository_id != attempt.repository_id:
        raise SubmissionBindingConflict("submission repository_id must match attempt")
    if submission.based_on_baseline_node_id != attempt.business_baseline_node_id:
        raise SubmissionBindingConflict("submission baseline node must match attempt")
    if submission.business_baseline_commit_id != attempt.business_baseline_commit_id:
        raise SubmissionBindingConflict("submission baseline commit must match attempt")
    if submission.canonical_business_digest != attempt.canonical_business_digest:
        raise SubmissionBindingConflict("submission canonical digest must match attempt")
    if attempt.repository_artifact_ref is not None and (
        submission.repository_artifact_id != attempt.repository_artifact_ref.artifact_id
    ):
        raise SubmissionBindingConflict("submission repository artifact id must match attempt")
    if attempt.repository_import_artifact_ref is not None and (
        submission.repository_import_artifact_raw_sha256
        != attempt.repository_import_artifact_ref.raw_sha256
    ):
        raise SubmissionBindingConflict(
            "submission import package raw sha must match attempt checkpoint"
        )
    if attempt.canonicalization_manifest_ref is not None and (
        submission.canonicalization_manifest_ref != attempt.canonicalization_manifest_ref
    ):
        raise SubmissionBindingConflict("submission manifest ref must match attempt")
    if attempt.canonicalization_manifest_digest is not None and (
        submission.canonicalization_manifest_digest != attempt.canonicalization_manifest_digest
    ):
        raise SubmissionBindingConflict("submission manifest digest must match attempt")
    if submission.completed_verification_policy != submission.requested_verification_policy:
        raise SubmissionBindingConflict(
            "submission completed verification policy must match requested policy"
        )
    if submission.target_ref != attempt.requested_target_ref:
        raise SubmissionBindingConflict("submission target ref must match attempt request")
    if tuple(submission.source_artifact_refs) != tuple(attempt.source_artifact_refs):
        raise SubmissionBindingConflict("submission source artifact refs must match attempt")
