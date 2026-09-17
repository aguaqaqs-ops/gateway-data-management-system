"""Finalize matching closure and transaction replay tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.application.submission.contracts import (
    FinalizeSubmitCommand,
    MatchingFinalizeFacts,
)
from gateway_backend.application.submission.errors import FinalizeBindingMismatch
from gateway_backend.application.submission.finalize import (
    finalize_submit,
    validate_finalize_replay,
    validate_matching_result_for_finalize,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
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
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import OperationStatus
from tests.test_submit_transactions import _seed_effect_pending_attempt, seed_submit_ready_workspace

pytestmark = pytest.mark.unit

TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def _effect_pending_attempt_for_finalize() -> SubmitAttempt:
    backend_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256="sha256:package",
    )
    repository_ref = RepositoryArtifactRef(
        artifact_id="repo-artifact-1",
        media_type="application/octet-stream",
        size_bytes=10,
        raw_sha256="sha256:repo",
    )
    return SubmitAttempt(
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
        snapshot_table_artifact_refs=("snap-1",),
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest="d-closure",
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        repository_import_artifact_ref=backend_ref,
        repository_artifact_ref=repository_ref,
        repository_operation_id="repo-op-1",
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:fp",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id="op-1",
        state=SubmitAttemptState.EFFECT_PENDING,
        submission_id=None,
        optimistic_version=1,
        created_by="actor-1",
        created_at=TS0,
        effect_pending_at=TS0,
    )


def _matching_finalize_facts(**overrides: Any) -> MatchingFinalizeFacts:
    base = MatchingFinalizeFacts(
        repository_id="repo-1",
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256="sha256:package",
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:manifest",
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )
    return replace(base, **overrides) if overrides else base


def _finalized_submission() -> Submission:
    return Submission(
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


FINALIZE_MATCHING_FAULTS = (
    ({"repository_operation_id": "repo-op-other"}, "repository operation identity does not match attempt"),
    ({"repository_id": "repo-other"}, "repository scope does not match attempt"),
    ({"repository_artifact_id": "repo-artifact-other"}, "repository artifact id does not match attempt checkpoint"),
)


def test_validate_matching_result_for_finalize_rejects_non_effect_pending_attempt() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    facts = _matching_finalize_facts()

    with pytest.raises(FinalizeBindingMismatch, match="finalize requires EFFECT_PENDING attempt"):
        finalize_submit(
            command=FinalizeSubmitCommand(
                attempt=attempt,
                facts=facts,
                submission_id="sub-new",
                created_at=TS1,
            ),
            existing_submission=None,
        )


@pytest.mark.parametrize(("fact_overrides", "message"), FINALIZE_MATCHING_FAULTS)
def test_validate_matching_result_for_finalize_rejects_binding_faults(
    fact_overrides: dict[str, object],
    message: str,
) -> None:
    attempt = _effect_pending_attempt_for_finalize()
    facts = _matching_finalize_facts(**fact_overrides)

    with pytest.raises(FinalizeBindingMismatch, match=message):
        validate_matching_result_for_finalize(attempt=attempt, facts=facts)


def test_validate_matching_result_for_finalize_rejects_missing_operation_id() -> None:
    attempt = replace(_effect_pending_attempt_for_finalize(), repository_operation_id=None)
    facts = _matching_finalize_facts()

    with pytest.raises(FinalizeBindingMismatch, match="repository operation identity is missing"):
        validate_matching_result_for_finalize(attempt=attempt, facts=facts)


def test_validate_finalize_replay_rejects_mismatched_artifact_id() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    submission = _finalized_submission()
    facts = _matching_finalize_facts(repository_artifact_id="repo-artifact-other")

    with pytest.raises(FinalizeBindingMismatch, match="repository artifact id does not match attempt checkpoint"):
        validate_finalize_replay(attempt=attempt, submission=submission, facts=facts)


def test_finalize_submit_replay_returns_existing_submission() -> None:
    attempt = replace(
        _effect_pending_attempt_for_finalize(),
        state=SubmitAttemptState.FINALIZED,
        submission_id="sub-1",
        finalized_at=TS1,
    )
    submission = _finalized_submission()
    facts = _matching_finalize_facts()

    result = finalize_submit(
        command=FinalizeSubmitCommand(
            attempt=attempt,
            facts=facts,
            submission_id="sub-1",
            created_at=TS1,
        ),
        existing_submission=submission,
    )

    assert result.replay is True
    assert result.submission is submission


def _read_finalize_versions(
    db_path: Path,
    attempt: SubmitAttempt,
) -> tuple[int, int, int]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        current = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
        assert current is not None
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
        await_step = next(step for step in steps if step.step_name == "await_import_result")
        return (
            current.optimistic_version,
            await_step.optimistic_version,
            operation.optimistic_version,
        )


def test_finalize_submit_transaction_replay_does_not_insert_second_submission(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    attempt_version, await_version, operation_version = _read_finalize_versions(db_path, attempt)
    facts = _matching_finalize_facts(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        repository_import_artifact_raw_sha256="sha256:" + "e" * 64,
        canonicalization_manifest_digest="sha256:" + "f" * 64,
    )
    request = FinalizeSubmitTransactionRequest(
        submit_attempt_id=attempt.submit_attempt_id,
        facts=facts,
        submission_id="sub-1",
        created_at=TS1,
        expected_attempt_version=attempt_version,
        expected_await_step_version=await_version,
        expected_operation_version=operation_version,
        worker_id="worker-test",
        lease_token="lease-test",
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        first = finalize_submit_transaction(request=request, unit_of_work=unit_of_work)
    assert first.replay is False

    finalized_attempt_version, _, _ = _read_finalize_versions(db_path, attempt)
    replay_request = replace(request, expected_attempt_version=finalized_attempt_version)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        replay = finalize_submit_transaction(request=replay_request, unit_of_work=unit_of_work)
    assert replay.replay is True

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (attempt.submit_attempt_id,),
        ).fetchone()[0]
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert rows == 1
    assert operation.status is OperationStatus.SUCCEEDED
