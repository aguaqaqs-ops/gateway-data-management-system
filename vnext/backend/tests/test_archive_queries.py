"""Archive candidate query and preview tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.archive.contracts import (
    ArchiveSelectedRef,
    compute_candidate_digest,
    review_status_to_archive_value,
)
from gateway_backend.application.archive.errors import CandidateBindingConflict
from gateway_backend.application.archive.queries import get_archive_candidates, preview_archive_plan
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.archive_fixtures import seed_approved_archive_candidate
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_review_transactions import _seed_pending_review_submission, _uow_factory
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit


def test_archive_candidates_include_only_approved_current_base_submissions(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    result = get_archive_candidates(
        context=seed.archiver_context,
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].submission_id == seed.submission_id
    assert result.candidate_set_digest.startswith("sha256:")
    assert result.blockers == ()


def test_pending_review_submission_is_not_a_candidate(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    from tests.support.archive_fixtures import _archiver_context

    archiver = _archiver_context(
        review_seed.reviewer_context.gateway_device_external_key,
        review_seed.reviewer_context.business_project_id,
    )
    scope_resolution = FixedScopeResolutionPort(
        repository_id=review_seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    result = get_archive_candidates(
        context=archiver,
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert result.candidates == ()


def test_preview_archive_plan_rejects_unknown_selected_ref(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with pytest.raises(CandidateBindingConflict):
        preview_archive_plan(
            context=seed.archiver_context,
            selected_ref=ArchiveSelectedRef(
                submission_id=seed.submission_id,
                expected_candidate_digest="sha256:" + "0" * 64,
            ),
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
        )


def test_preview_archive_plan_does_not_write_rows(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        before_plans = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        before_events = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    preview_archive_plan(
        context=seed.archiver_context,
        selected_ref=seed.selected_ref,
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        after_plans = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_plan_records"
        ).fetchone()[0]
        after_events = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    assert before_plans == after_plans == 0
    assert before_events == after_events == 0


def test_candidate_digest_changes_when_review_sequence_changes(db_path: Path) -> None:
    review_seed = _seed_pending_review_submission(db_path)
    submission = review_seed.submission
    digest_v0 = compute_candidate_digest(
        repository_id=submission.repository_id,
        gateway_device_external_key=review_seed.reviewer_context.gateway_device_external_key,
        business_project_id=review_seed.reviewer_context.business_project_id,
        workspace_id=submission.workspace_id,
        workspace_generation=submission.workspace_generation,
        submission_id=submission.submission_id,
        submit_attempt_id=submission.submit_attempt_id,
        upload_revision_id=submission.upload_revision_id,
        preview_result_id=submission.preview_result_id,
        based_on_baseline_node_id=submission.based_on_baseline_node_id,
        business_baseline_commit_id=submission.business_baseline_commit_id,
        repository_commit_id=submission.repository_commit_id,
        canonical_business_digest=submission.canonical_business_digest,
        canonicalization_manifest_ref=submission.canonicalization_manifest_ref,
        canonicalization_manifest_digest=submission.canonicalization_manifest_digest,
        source_artifact_refs=submission.source_artifact_refs,
        requested_verification_policy=submission.requested_verification_policy.value,
        completed_verification_policy=submission.completed_verification_policy.value,
        review_status=review_status_to_archive_value(ReviewStatus.PENDING),
        review_sequence=0,
    )
    digest_v1 = compute_candidate_digest(
        repository_id=submission.repository_id,
        gateway_device_external_key=review_seed.reviewer_context.gateway_device_external_key,
        business_project_id=review_seed.reviewer_context.business_project_id,
        workspace_id=submission.workspace_id,
        workspace_generation=submission.workspace_generation,
        submission_id=submission.submission_id,
        submit_attempt_id=submission.submit_attempt_id,
        upload_revision_id=submission.upload_revision_id,
        preview_result_id=submission.preview_result_id,
        based_on_baseline_node_id=submission.based_on_baseline_node_id,
        business_baseline_commit_id=submission.business_baseline_commit_id,
        repository_commit_id=submission.repository_commit_id,
        canonical_business_digest=submission.canonical_business_digest,
        canonicalization_manifest_ref=submission.canonicalization_manifest_ref,
        canonicalization_manifest_digest=submission.canonicalization_manifest_digest,
        source_artifact_refs=submission.source_artifact_refs,
        requested_verification_policy=submission.requested_verification_policy.value,
        completed_verification_policy=submission.completed_verification_policy.value,
        review_status=review_status_to_archive_value(ReviewStatus.APPROVED),
        review_sequence=1,
    )
    assert digest_v0 != digest_v1
