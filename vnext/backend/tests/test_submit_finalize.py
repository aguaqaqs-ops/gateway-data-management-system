"""Finalize transaction replay tests unique to the S5 finalize owner."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gateway_backend.application.submission.contracts import MatchingFinalizeFacts
from gateway_backend.application.submission.errors import FinalizeBindingMismatch
from gateway_backend.artifacts.computation_cache import CacheOperationOwner, ComputationCacheEntry
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.infrastructure.control_db.sqlite_workspace import preview_result_to_row
from gateway_backend.operations import OperationStatus
from tests.support.configuration_facts import replace_preview_with_facts
from tests.test_computation_cache import _value
from tests.test_submit_transactions import (
    SubmitSeed, _seed_effect_pending_attempt, seed_submit_ready_workspace,
)

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


def _request(db_path: Path, seed: SubmitSeed, attempt: SubmitAttempt) -> FinalizeSubmitTransactionRequest:
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
    return FinalizeSubmitTransactionRequest(
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


def _cache_entry(seed: SubmitSeed, suffix: str) -> ComputationCacheEntry:
    entry, _blobs = _value(suffix, task=suffix.encode())
    return replace(entry, key=replace(entry.key, repository_id=seed.workspace.repository_id))


def _finalize_time(db_path: Path, attempt: SubmitAttempt) -> datetime:
    # The original transaction fixture owns a real-clock 60-second await lease.
    # Keep T3 inside it; only the optional cache seed is twelve hours older.
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        steps, _cursor = unit_of_work.operations.list_steps(attempt.operation_id)
        step = next(step for step in steps if step.step_name == "await_import_result")
        return step.updated_at + timedelta(seconds=1)


def _cache_snapshot(db_path: Path) -> tuple[tuple[tuple[object, ...], ...], ...]:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        return tuple(tuple(tuple(row) for row in unit_of_work.connection.execute(query)) for query in (
            "SELECT * FROM computation_cache_entries ORDER BY repository_id,kind,task_digest",
            "SELECT * FROM computation_cache_uses ORDER BY producer_operation_id,repository_id,kind,task_digest",
            "SELECT * FROM artifact_protection_intents WHERE intent='ttl-cache' ORDER BY artifact_id,owner_kind,owner_id",
        ))


def _assert_effect_pending(db_path: Path, attempt: SubmitAttempt) -> None:
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        current = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
        assert current is not None and current.state is SubmitAttemptState.EFFECT_PENDING
        assert unit_of_work.submission.get_submission_by_attempt(attempt.submit_attempt_id) is None
        occupancy = unit_of_work.submission.get_workspace_occupancy(attempt.workspace_id)
        assert occupancy is not None and occupancy.active_submit_attempt_id == attempt.submit_attempt_id
        assert unit_of_work.review.get_projection("sub-1") is None


def test_finalize_submit_transaction_replay_does_not_insert_second_submission(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
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


def test_finalize_touches_real_preview_producer_in_its_transaction_and_replay_does_not_renew(
    db_path: Path,
) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    entry = _cache_entry(seed, "preview-task")
    unrelated = _cache_entry(seed, "another-preview-task")
    transaction_time = _finalize_time(db_path, attempt)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time - timedelta(hours=12)) as unit_of_work:
        unit_of_work.computation_cache.store(
            entry, CacheOperationOwner("preview-operation", seed.preview_result.operation_id),
        )
        # The accepted fixture's historical pin owner differs from the actual
        # result producer. T3 must not use that pin owner or the Submit operation.
        assert seed.preview_operation_id != seed.preview_result.operation_id
        unit_of_work.computation_cache.store(
            unrelated, CacheOperationOwner("preview-operation", seed.preview_operation_id),
        )
    before = _cache_snapshot(db_path)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time) as unit_of_work:
        result = finalize_submit_transaction(request=request, unit_of_work=unit_of_work)
    assert not result.replay
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        entries = dict(unit_of_work.connection.execute(
            "SELECT manifest_artifact_id,expires_at_us FROM computation_cache_entries",
        ))
        uses = dict(unit_of_work.connection.execute(
            "SELECT manifest_artifact_id,expires_at_us FROM computation_cache_uses",
        ))
        expiry = ((transaction_time + timedelta(days=1) - datetime(1970, 1, 1, tzinfo=UTC))
                  // timedelta(microseconds=1))
        assert entries[entry.manifest_ref.artifact_id] == expiry
        assert uses[entry.manifest_ref.artifact_id] == expiry
        assert entries[unrelated.manifest_ref.artifact_id] < expiry
        assert uses[unrelated.manifest_ref.artifact_id] < expiry
        for ref in entry.refs:
            assert unit_of_work.connection.execute(
                "SELECT expires_at_us FROM artifact_protection_intents "
                "WHERE artifact_id=? AND intent='ttl-cache'", (ref.artifact_id,),
            ).fetchone()[0] == expiry
    after = _cache_snapshot(db_path)
    assert after != before
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time + timedelta(hours=6)) as unit_of_work:
        assert finalize_submit_transaction(request=request, unit_of_work=unit_of_work).replay
    assert _cache_snapshot(db_path) == after


def test_missing_temporary_preview_does_not_add_a_new_finalize_precondition(db_path: Path) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    transaction_time = _finalize_time(db_path, attempt)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time - timedelta(hours=12)) as unit_of_work:
        unit_of_work.computation_cache.store(
            _cache_entry(seed, "unresolved-producer"),
            CacheOperationOwner("preview-operation", seed.preview_result.operation_id),
        )
        unit_of_work.connection.execute(
            "DELETE FROM preview_result_records WHERE preview_result_id=?", (attempt.preview_result_id,),
        )
    before = _cache_snapshot(db_path)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time) as unit_of_work:
        assert not finalize_submit_transaction(request=request, unit_of_work=unit_of_work).replay
    assert _cache_snapshot(db_path) == before


def test_malformed_optional_cache_rolls_back_its_touch_prefix_and_keeps_finalize(
    db_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    entries = sorted((_cache_entry(seed, "healthy"), _cache_entry(seed, "bad")),
                     key=lambda entry: entry.key.task_digest.value)
    transaction_time = _finalize_time(db_path, attempt)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time - timedelta(hours=12)) as unit_of_work:
        for entry in entries:
            unit_of_work.computation_cache.store(
                entry, CacheOperationOwner("preview-operation", seed.preview_result.operation_id),
            )
        unit_of_work.connection.execute(
            "UPDATE computation_cache_entries SET member_refs_json=? WHERE manifest_artifact_id=?",
            ('{"private-business-payload":"do-not-log"}', entries[-1].manifest_ref.artifact_id),
        )
    before = _cache_snapshot(db_path)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time) as unit_of_work:
        assert not finalize_submit_transaction(request=request, unit_of_work=unit_of_work).replay
    assert _cache_snapshot(db_path) == before
    assert "skipped malformed optional computation cache" in caplog.text
    assert "private-business-payload" not in caplog.text


@pytest.mark.parametrize("fault", ("workspace", "repository", "producer", "workspace-repository"))
def test_conflicting_preview_scope_is_not_an_optional_cache_miss(db_path: Path, fault: str) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    scope_changes = {
        "repository": {"repository_id": "foreign-repository"},
        "producer": {"operation_id": "another-preview-operation"},
    }
    if fault == "workspace":
        other_seed = seed_submit_ready_workspace(db_path, actor_id="another-actor")
        scope_changes["workspace"] = {"workspace_id": other_seed.workspace.workspace_id}
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        if fault == "workspace-repository":
            current = unit_of_work.workspace.get_workspace(attempt.workspace_id)
            assert current is not None
            unit_of_work.workspace.save_workspace(
                replace(current, repository_id="foreign-repository",
                        optimistic_version=current.optimistic_version + 1),
                expected_version=current.optimistic_version,
            )
        else:
            preview = replace_preview_with_facts(seed.preview_result, **scope_changes[fault])
            row = preview_result_to_row(preview)
            unit_of_work.connection.execute(
                "UPDATE preview_result_records SET workspace_id=?,repository_id=?,binding=?,operation_id=? "
                "WHERE preview_result_id=?", (row[1], row[4], row[5], row[6], row[0]),
            )
    with pytest.raises(FinalizeBindingMismatch, match="scope"):
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            finalize_submit_transaction(request=request, unit_of_work=unit_of_work)
    _assert_effect_pending(db_path, attempt)


@pytest.mark.parametrize("fault", ("sql", "constraint"))
def test_unknown_cache_sql_failure_rolls_back_the_original_finalize(db_path: Path, fault: str) -> None:
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    transaction_time = _finalize_time(db_path, attempt)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time - timedelta(hours=12)) as unit_of_work:
        unit_of_work.computation_cache.store(
            _cache_entry(seed, "sql-failure"),
            CacheOperationOwner("preview-operation", seed.preview_result.operation_id),
        )
        action = ("SELECT no_such_cache_function();" if fault == "sql" else
                  "SELECT RAISE(ABORT,'unknown cache constraint');")
        unit_of_work.connection.execute(
            "CREATE TRIGGER fail_optional_touch BEFORE INSERT ON computation_cache_uses "
            f"BEGIN {action} END",
        )
    before = _cache_snapshot(db_path)
    error = sqlite3.OperationalError if fault == "sql" else sqlite3.IntegrityError
    with pytest.raises(error):
        with ControlDbUnitOfWork(db_path, now=lambda: transaction_time) as unit_of_work:
            finalize_submit_transaction(request=request, unit_of_work=unit_of_work)
    _assert_effect_pending(db_path, attempt)
    assert _cache_snapshot(db_path) == before


def test_attempt_cas_failure_rolls_back_optional_cache_renewal(db_path: Path) -> None:
    from gateway_backend.domain.submission.errors import SubmitAttemptVersionConflict

    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    request = _request(db_path, seed, attempt)
    transaction_time = _finalize_time(db_path, attempt)
    with ControlDbUnitOfWork(db_path, now=lambda: transaction_time - timedelta(hours=12)) as unit_of_work:
        unit_of_work.computation_cache.store(
            _cache_entry(seed, "cas-failure"),
            CacheOperationOwner("preview-operation", seed.preview_result.operation_id),
        )
    before = _cache_snapshot(db_path)
    with pytest.raises(SubmitAttemptVersionConflict):
        with ControlDbUnitOfWork(db_path, now=lambda: transaction_time) as unit_of_work:
            finalize_submit_transaction(
                request=replace(request, expected_attempt_version=request.expected_attempt_version + 1),
                unit_of_work=unit_of_work,
            )
    _assert_effect_pending(db_path, attempt)
    assert _cache_snapshot(db_path) == before
