"""SubmitAttempt state machine and Submission binding domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from dataclasses import replace

from gateway_backend.domain.submission.errors import (
    InvalidSubmitAttemptTransition,
    SubmissionBindingConflict,
    SubmitAttemptInvariantViolation,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    Submission,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.submission.policies import (
    assert_submission_attempt_binding,
    transition_attempt_state,
)

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)

BACKEND_REF = BackendArtifactRef(
    artifact_id="backend-pkg-1",
    media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
    size_bytes=10,
    raw_sha256="sha256:package",
)
REPOSITORY_REF = RepositoryArtifactRef(
    artifact_id="repo-artifact-1",
    media_type="application/octet-stream",
    size_bytes=10,
    raw_sha256="sha256:repo",
)


def _prepared_attempt(**overrides: Any) -> SubmitAttempt:
    base = SubmitAttempt(
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=1,
        repository_expected_commit_id="commit-main",
        canonical_business_digest="sha256:canonical",
        source_digest="d-source",
        snapshot_digest="d-snapshot",
        source_artifact_refs=("source-1",),
        canonical_table_set_closure_ref="canonical-table-closure-1",
        canonical_table_set_closure_digest="sha256:canonical-table-closure",
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest="d-closure",
        canonicalization_manifest_ref="canonical-manifest-1",
        canonicalization_manifest_digest="sha256:canonical-manifest",
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.ADAPTIVE_PATCH,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:fp",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id="op-1",
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by="actor-1",
        created_at=TS0,
    )
    return replace(base, **overrides) if overrides else base


def _effect_pending_attempt() -> SubmitAttempt:
    return _prepared_attempt(
        state=SubmitAttemptState.EFFECT_PENDING,
        effect_pending_at=TS1,
        prepared_canonicalization_manifest_ref="manifest-1",
        prepared_canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_ref=BACKEND_REF,
        repository_artifact_ref=REPOSITORY_REF,
        repository_operation_id="repo-op-1",
    )


def _finalized_attempt() -> SubmitAttempt:
    return replace(
        _effect_pending_attempt(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )


def _aborted_attempt() -> SubmitAttempt:
    return _prepared_attempt(
        state=SubmitAttemptState.ABORTED,
        abort_code="IMPORT_REJECTED",
        aborted_at=TS1,
    )


def _submission(**overrides: Any) -> Submission:
    base = Submission(
        submission_id="sub-1",
        submit_attempt_id="sa-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        based_on_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        repository_commit_id="commit-new",
        canonical_business_digest="sha256:canonical",
        source_artifact_refs=("source-1",),
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_raw_sha256="sha256:package",
        repository_artifact_id="repo-artifact-1",
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
        created_by="actor-1",
        created_at=TS1,
    )
    return replace(base, **overrides) if overrides else base


LEGAL_TRANSITIONS = (
    (SubmitAttemptState.PREPARED, SubmitAttemptState.EFFECT_PENDING),
    (SubmitAttemptState.PREPARED, SubmitAttemptState.ABORTED),
    (SubmitAttemptState.EFFECT_PENDING, SubmitAttemptState.FINALIZED),
    (SubmitAttemptState.EFFECT_PENDING, SubmitAttemptState.ABORTED),
)


@pytest.mark.parametrize(("current", "target"), LEGAL_TRANSITIONS)
def test_transition_attempt_state_allows_legal_edges(
    current: SubmitAttemptState,
    target: SubmitAttemptState,
) -> None:
    if current is SubmitAttemptState.PREPARED:
        attempt = _prepared_attempt(state=current)
    else:
        attempt = _effect_pending_attempt()
    changes: dict[str, Any] = {}
    if target is SubmitAttemptState.EFFECT_PENDING:
        changes = {"effect_pending_at": TS1}
    if target is SubmitAttemptState.FINALIZED:
        changes = {"submission_id": "sub-1", "finalized_at": TS1}
    if target is SubmitAttemptState.ABORTED:
        changes = {"abort_code": "IMPORT_REJECTED", "aborted_at": TS1}

    updated = transition_attempt_state(attempt, target=target, **changes)

    assert updated.state is target


ILLEGAL_TRANSITION_CASES = (
    (SubmitAttemptState.PREPARED, SubmitAttemptState.FINALIZED),
    (SubmitAttemptState.EFFECT_PENDING, SubmitAttemptState.PREPARED),
    (SubmitAttemptState.FINALIZED, SubmitAttemptState.ABORTED),
    (SubmitAttemptState.ABORTED, SubmitAttemptState.PREPARED),
)


@pytest.mark.parametrize(("current", "target"), ILLEGAL_TRANSITION_CASES)
def test_transition_attempt_state_rejects_illegal_edges(
    current: SubmitAttemptState,
    target: SubmitAttemptState,
) -> None:
    if current is SubmitAttemptState.PREPARED:
        attempt = _prepared_attempt(state=current)
    elif current is SubmitAttemptState.EFFECT_PENDING:
        attempt = _effect_pending_attempt()
    elif current is SubmitAttemptState.FINALIZED:
        attempt = _finalized_attempt()
    else:
        attempt = _aborted_attempt()
    changes: dict[str, Any] = {}
    if target is SubmitAttemptState.FINALIZED:
        changes = {"submission_id": "sub-1", "finalized_at": TS1}
    if target is SubmitAttemptState.ABORTED:
        changes = {"abort_code": "IMPORT_REJECTED", "aborted_at": TS1}

    with pytest.raises(InvalidSubmitAttemptTransition):
        transition_attempt_state(attempt, target=target, **changes)


FIELD_CO_PRESENCE_FAULTS = (
    (
        {
            "repository_artifact_ref": REPOSITORY_REF,
            "repository_import_artifact_ref": None,
        },
        "repository artifact ref requires backend import artifact ref",
    ),
    (
        {
            "repository_operation_id": "repo-op-1",
            "repository_artifact_ref": None,
        },
        "repository operation identity requires repository artifact ref",
    ),
    (
        {
            "state": SubmitAttemptState.FINALIZED,
            "submission_id": None,
            "finalized_at": TS1,
        },
        "FINALIZED attempt requires submission_id",
    ),
    (
        {
            "state": SubmitAttemptState.ABORTED,
            "abort_code": None,
            "aborted_at": TS1,
        },
        "ABORTED attempt requires abort_code",
    ),
)


REQUIRED_CANONICAL_BINDING_FAULTS = (
    ({"canonical_table_set_closure_ref": ""}, "canonical_table_set_closure_ref must be a non-empty string"),
    (
        {"canonical_table_set_closure_digest": ""},
        "canonical_table_set_closure_digest must be a non-empty string",
    ),
    ({"canonicalization_manifest_ref": ""}, "canonicalization_manifest_ref must be a non-empty string"),
    (
        {"canonicalization_manifest_digest": ""},
        "canonicalization_manifest_digest must be a non-empty string",
    ),
)


@pytest.mark.parametrize(("overrides", "message"), FIELD_CO_PRESENCE_FAULTS)
def test_submit_attempt_rejects_field_co_presence_violations(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(SubmitAttemptInvariantViolation, match=message):
        _prepared_attempt(**overrides)


@pytest.mark.parametrize(("overrides", "message"), REQUIRED_CANONICAL_BINDING_FAULTS)
def test_submit_attempt_requires_frozen_canonical_bindings(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _prepared_attempt(**overrides)


def test_workspace_submit_occupancy_requires_exactly_one_active_pointer() -> None:
    WorkspaceSubmitOccupancy(
        workspace_id="ws-1",
        active_submit_attempt_id="sa-1",
        active_submission_id=None,
    )
    WorkspaceSubmitOccupancy(
        workspace_id="ws-1",
        active_submit_attempt_id=None,
        active_submission_id="sub-1",
    )
    with pytest.raises(ValueError, match="exactly one active pointer"):
        WorkspaceSubmitOccupancy(
            workspace_id="ws-1",
            active_submit_attempt_id=None,
            active_submission_id=None,
        )
    with pytest.raises(ValueError, match="exactly one active pointer"):
        WorkspaceSubmitOccupancy(
            workspace_id="ws-1",
            active_submit_attempt_id="sa-1",
            active_submission_id="sub-1",
        )


def test_assert_submission_attempt_binding_accepts_matching_facts() -> None:
    assert_submission_attempt_binding(attempt=_finalized_attempt(), submission=_submission())


def test_assert_submission_attempt_binding_rejects_mismatched_attempt_id() -> None:
    with pytest.raises(SubmissionBindingConflict, match="submit_attempt_id"):
        assert_submission_attempt_binding(
            attempt=_finalized_attempt(),
            submission=_submission(submit_attempt_id="sa-other"),
        )
