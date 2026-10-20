"""T3 finalize closure and replay validation."""

from __future__ import annotations

from gateway_backend.application.submission.contracts import (
    FinalizeSubmitCommand,
    FinalizeSubmitResult,
    MatchingFinalizeFacts,
)
from gateway_backend.application.submission.errors import FinalizeBindingMismatch
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    Submission,
)
from gateway_backend.domain.submission.policies import (
    assert_submission_attempt_binding,
    transition_attempt_state,
)


def validate_matching_result_for_finalize(
    *,
    attempt: SubmitAttempt,
    facts: MatchingFinalizeFacts,
) -> None:
    if facts.repository_id != attempt.repository_id:
        raise FinalizeBindingMismatch("repository scope does not match attempt")
    if attempt.repository_operation_id is None:
        raise FinalizeBindingMismatch("attempt repository operation identity is missing")
    if facts.repository_operation_id != attempt.repository_operation_id:
        raise FinalizeBindingMismatch("repository operation identity does not match attempt")
    if facts.target_ref is not SubmitTargetRef.MAIN:
        raise FinalizeBindingMismatch("finalize target ref must be main")
    if facts.completed_verification_policy is not SubmitVerificationPolicy.STRUCTURAL:
        raise FinalizeBindingMismatch("completed verification policy must match request")
    if facts.completed_verification_policy is not attempt.requested_verification_policy:
        raise FinalizeBindingMismatch(
            "completed verification policy must equal requested verification policy"
        )
    if facts.completed_unknown_type_policy is not SubmitUnknownTypePolicy.REJECT:
        raise FinalizeBindingMismatch("completed unknown type policy must match request")
    if facts.completed_unknown_type_policy is not attempt.requested_unknown_type_policy:
        raise FinalizeBindingMismatch(
            "completed unknown type policy must equal requested unknown type policy"
        )
    if facts.canonicalization_manifest_ref != attempt.prepared_canonicalization_manifest_ref:
        raise FinalizeBindingMismatch("manifest ref does not match attempt checkpoint")
    if facts.canonicalization_manifest_digest != attempt.prepared_canonicalization_manifest_digest:
        raise FinalizeBindingMismatch("manifest digest does not match attempt checkpoint")
    if attempt.repository_import_artifact_ref is None:
        raise FinalizeBindingMismatch("attempt backend import artifact ref is missing")
    if facts.repository_import_artifact_raw_sha256 != attempt.repository_import_artifact_ref.raw_sha256:
        raise FinalizeBindingMismatch("package raw sha does not match attempt checkpoint")
    if attempt.repository_artifact_ref is None:
        raise FinalizeBindingMismatch("attempt repository artifact ref is missing")
    if facts.repository_artifact_id != attempt.repository_artifact_ref.artifact_id:
        raise FinalizeBindingMismatch("repository artifact id does not match attempt checkpoint")
    if facts.repository_expected_parent_commit_id != attempt.repository_expected_commit_id:
        raise FinalizeBindingMismatch(
            "repository expected parent commit does not match attempt checkpoint"
        )


def build_submission(*, command: FinalizeSubmitCommand) -> Submission:
    if command.attempt.state is not SubmitAttemptState.EFFECT_PENDING:
        raise FinalizeBindingMismatch("finalize requires EFFECT_PENDING attempt")
    validate_matching_result_for_finalize(attempt=command.attempt, facts=command.facts)
    submission = Submission(
        submission_id=command.submission_id,
        submit_attempt_id=command.attempt.submit_attempt_id,
        workspace_id=command.attempt.workspace_id,
        workspace_generation=command.attempt.workspace_generation,
        upload_revision_id=command.attempt.upload_revision_id,
        preview_result_id=command.attempt.preview_result_id,
        repository_id=command.attempt.repository_id,
        based_on_baseline_node_id=command.attempt.business_baseline_node_id,
        business_baseline_commit_id=command.attempt.business_baseline_commit_id,
        repository_commit_id=command.facts.repository_commit_id,
        canonical_business_digest=command.attempt.canonical_business_digest,
        source_artifact_refs=tuple(command.attempt.source_artifact_refs),
        canonicalization_manifest_ref=command.facts.canonicalization_manifest_ref,
        canonicalization_manifest_digest=command.facts.canonicalization_manifest_digest,
        repository_import_artifact_raw_sha256=command.facts.repository_import_artifact_raw_sha256,
        repository_artifact_id=command.facts.repository_artifact_id,
        requested_verification_policy=command.attempt.requested_verification_policy,
        completed_verification_policy=command.facts.completed_verification_policy,
        requested_unknown_type_policy=command.attempt.requested_unknown_type_policy,
        target_ref=command.facts.target_ref,
        created_by=command.attempt.created_by,
        created_at=command.created_at,
        identity_confirmations=command.attempt.identity_confirmations,
    )
    assert_submission_attempt_binding(attempt=command.attempt, submission=submission)
    return submission


def finalize_submit(
    *,
    command: FinalizeSubmitCommand,
    existing_submission: Submission | None = None,
) -> FinalizeSubmitResult:
    if existing_submission is not None:
        validate_finalize_replay(
            attempt=command.attempt,
            submission=existing_submission,
            facts=command.facts,
        )
        return FinalizeSubmitResult(
            attempt=command.attempt,
            submission=existing_submission,
            replay=True,
        )
    submission = build_submission(command=command)
    finalized_attempt = transition_attempt_state(
        command.attempt,
        target=SubmitAttemptState.FINALIZED,
        submission_id=submission.submission_id,
        finalized_at=command.created_at,
    )
    return FinalizeSubmitResult(
        attempt=finalized_attempt,
        submission=submission,
        replay=False,
    )


def validate_finalize_replay(
    *,
    attempt: SubmitAttempt,
    submission: Submission,
    facts: MatchingFinalizeFacts,
) -> None:
    if attempt.state is not SubmitAttemptState.FINALIZED:
        raise FinalizeBindingMismatch("finalize replay requires FINALIZED attempt")
    if attempt.submission_id != submission.submission_id:
        raise FinalizeBindingMismatch("attempt submission_id must match existing submission")
    validate_matching_result_for_finalize(attempt=attempt, facts=facts)
    assert_submission_attempt_binding(attempt=attempt, submission=submission)
    if submission.repository_commit_id != facts.repository_commit_id:
        raise FinalizeBindingMismatch("existing submission commit does not match finalize facts")
    if submission.repository_artifact_id != facts.repository_artifact_id:
        raise FinalizeBindingMismatch(
            "existing submission repository artifact id does not match finalize facts"
        )
