"""Finalize transaction replay tests unique to the S5 finalize owner."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.submission.contracts import MatchingFinalizeFacts
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import OperationStatus
from tests.test_submit_transactions import _seed_effect_pending_attempt, seed_submit_ready_workspace

pytestmark = pytest.mark.unit

TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


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
    facts = MatchingFinalizeFacts(
        repository_id=seed.workspace.repository_id,
        repository_operation_id="repo-op-1",
        repository_commit_id="commit-new",
        repository_expected_parent_commit_id="commit-main",
        repository_artifact_id="repo-artifact-1",
        repository_import_artifact_raw_sha256="sha256:" + "e" * 64,
        canonicalization_manifest_ref="manifest-1",
        canonicalization_manifest_digest="sha256:" + "f" * 64,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
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
