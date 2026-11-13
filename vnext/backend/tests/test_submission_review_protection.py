"""Finalization commits the complete immutable review owner or rolls it all back."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.application.submission.errors import FinalizeBindingMismatch, FinalizeRecoveryRequired
from gateway_backend.application.submission.finalize_transaction import finalize_submit_transaction
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from tests.support.review_result_fixtures import review_artifact_refs
from tests.test_submit_transactions import seed_submit_ready_workspace, _seed_effect_pending_attempt
from tests.test_submit_finalize import _request, _assert_effect_pending

pytestmark = pytest.mark.unit
_CLOSURE_FAULTS = ("omitted-output", "wrong-ref", "extra-ref", "missing-pin")


@pytest.mark.parametrize("fault", _CLOSURE_FAULTS)
def test_finalize_rejects_changed_or_unprotected_review_closure_atomically(tmp_path: Path, fault: str) -> None:
    db = tmp_path / "control.db"
    initialize_control_db(db)
    seed = seed_submit_ready_workspace(db)
    attempt = _seed_effect_pending_attempt(db, seed)
    request = _request(db, seed, attempt)
    refs = request.review_artifact_refs
    output = next(ref for ref in refs if ref.artifact_id != seed.preview_result.ready_closure_artifact_id)
    if fault == "omitted-output":
        request = replace(request, review_artifact_refs=tuple(ref for ref in refs if ref != output))
    elif fault == "wrong-ref":
        request = replace(request, review_artifact_refs=tuple(
            replace(ref, size_bytes=ref.size_bytes + 1) if ref == output else ref for ref in refs))
    elif fault == "extra-ref":
        request = replace(request, review_artifact_refs=(*refs, seed.protected_refs[0]))
    else:
        with ControlDbUnitOfWork(db) as uow:
            uow.connection.execute("DELETE FROM artifact_protection_intents WHERE owner_kind='submit-attempt' AND owner_id=? AND artifact_id=?",
                (attempt.submit_attempt_id, output.artifact_id))
    with pytest.raises(FinalizeBindingMismatch):
        with ControlDbUnitOfWork(db) as uow:
            finalize_submit_transaction(request=request, unit_of_work=uow)
    _assert_effect_pending(db, attempt)
    with ControlDbUnitOfWork(db, read_only=True) as uow:
        assert not uow.list_artifact_protection_for_owner(owner_kind="submission-review", owner_id="sub-1")


def test_finalize_rolls_back_new_review_pins_if_transfer_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "control.db"
    initialize_control_db(db)
    seed = seed_submit_ready_workspace(db)
    attempt = _seed_effect_pending_attempt(db, seed)
    request = _request(db, seed, attempt)
    original = ControlDbUnitOfWork.set_artifact_protection
    def fail_after_pin(self: ControlDbUnitOfWork, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if kwargs.get("owner_kind") == "submission-review":
            raise RuntimeError("injected transfer failure")
        return result
    with monkeypatch.context() as patch:
        patch.setattr(ControlDbUnitOfWork, "set_artifact_protection", fail_after_pin)
        with pytest.raises(RuntimeError, match="injected transfer failure"):
            with ControlDbUnitOfWork(db) as uow:
                finalize_submit_transaction(request=request, unit_of_work=uow)
    _assert_effect_pending(db, attempt)
    with ControlDbUnitOfWork(db, read_only=True) as uow:
        assert not uow.list_artifact_protection_for_owner(owner_kind="submission-review", owner_id="sub-1")
        held = uow.list_artifact_protection_for_owner(owner_kind="submit-attempt", owner_id=attempt.submit_attempt_id)
        assert {ref.artifact_id for ref in review_artifact_refs(seed)}.issubset(held)
    with ControlDbUnitOfWork(db) as uow:
        assert not finalize_submit_transaction(request=request, unit_of_work=uow).replay
    with ControlDbUnitOfWork(db) as uow:
        assert finalize_submit_transaction(request=request, unit_of_work=uow).replay
    with ControlDbUnitOfWork(db) as uow:
        lost = next(ref for ref in request.review_artifact_refs if ref.artifact_id != seed.preview_result.ready_closure_artifact_id)
        uow.connection.execute("DELETE FROM artifact_protection_intents WHERE owner_kind='submission-review' AND owner_id='sub-1' AND artifact_id=?", (lost.artifact_id,))
    with pytest.raises(FinalizeRecoveryRequired, match="review protection"):
        with ControlDbUnitOfWork(db) as uow:
            finalize_submit_transaction(request=request, unit_of_work=uow)


@pytest.mark.parametrize("terminal", ("archive", "close-not-archived"))
def test_archive_and_manual_close_preserve_submission_review_owner(tmp_path: Path, terminal: str) -> None:
    from gateway_backend.application.archive.manual_close import close_submission
    from tests.support.archive_fixtures import (
        seed_approved_archive_candidate, append_selection_confirmation, start_archive_for_seed, close_command,
    )
    from tests.test_review_transactions import _uow_factory
    from tests.test_archive_transactions import TS_ARCHIVE
    db = tmp_path / "control.db"
    initialize_control_db(db)
    seed = seed_approved_archive_candidate(db)
    with ControlDbUnitOfWork(db, read_only=True) as uow:
        before = uow.list_artifact_protection_for_owner(owner_kind="submission-review", owner_id=seed.submission_id)
        assert before
    if terminal == "archive":
        sequence = append_selection_confirmation(seed)
        start_archive_for_seed(seed, confirmation_sequence=sequence, now=TS_ARCHIVE)
    else:
        close_submission(command=close_command(seed), unit_of_work_factory=_uow_factory(db), now=TS_ARCHIVE)
    with ControlDbUnitOfWork(db, read_only=True) as uow:
        assert uow.list_artifact_protection_for_owner(owner_kind="submission-review", owner_id=seed.submission_id) == before
        submission = uow.submission.get_submission(seed.submission_id)
        assert submission is not None and uow.workspace.get_preview_result(submission.preview_result_id) is not None
        assert uow.submission.get_workspace_occupancy(submission.workspace_id) is None
