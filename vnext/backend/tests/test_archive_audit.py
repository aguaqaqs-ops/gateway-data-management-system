"""Archive audit append and idempotency tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.archive.audit import (
    AppendArchiveConfirmationCommand,
    append_archive_confirmation,
)
from gateway_backend.application.submission.errors import IdempotencyConflict
from gateway_backend.domain.archive.models import ArchiveConfirmationAction
from tests.support.archive_fixtures import ArchiveSeed, seed_approved_archive_candidate
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_review_transactions import _uow_factory
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit

AUDIT_IDEMPOTENCY_CONFLICT_SHAPES = (
    pytest.param("selected_submission_id", "sub-other", id="selected-id"),
    pytest.param("expected_candidate_digest", "sha256:" + "1" * 64, id="candidate-digest"),
    pytest.param("candidate_set_digest", "sha256:" + "2" * 64, id="candidate-set-digest"),
)


def _confirmation_command(seed: ArchiveSeed, **overrides: Any) -> AppendArchiveConfirmationCommand:
    command = AppendArchiveConfirmationCommand(
        context=seed.archiver_context,
        idempotency_key="audit-key-1",
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        selected=seed.selected_ref,
        candidate_set_digest=seed.candidate_set_digest,
        subject_digest=seed.selection_subject_digest,
        expected_sequence=0,
        action=ArchiveConfirmationAction.CONFIRM,
        reason="confirm archive selection",
    )
    if overrides:
        return replace(command, **overrides)
    return command


@pytest.mark.parametrize(("field_name", "replacement"), AUDIT_IDEMPOTENCY_CONFLICT_SHAPES)
def test_confirmation_replay_rejects_changed_binding_fields(
    db_path: Path,
    field_name: str,
    replacement: str,
) -> None:
    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    append_archive_confirmation(
        command=_confirmation_command(seed),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    mutated = _confirmation_command(seed)
    if field_name == "selected_submission_id":
        mutated = replace(
            mutated,
            selected=replace(mutated.selected, submission_id=replacement),
        )
    elif field_name == "expected_candidate_digest":
        mutated = replace(
            mutated,
            selected=replace(mutated.selected, expected_candidate_digest=replacement),
        )
    elif field_name == "candidate_set_digest":
        mutated = replace(mutated, candidate_set_digest=replacement)
    else:
        raise AssertionError(field_name)
    with pytest.raises(IdempotencyConflict):
        append_archive_confirmation(
            command=mutated,
            scope_resolution=scope_resolution,
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )


def test_confirmation_replay_returns_original_event_after_subject_expires(db_path: Path) -> None:
    from datetime import UTC, datetime

    seed = seed_approved_archive_candidate(db_path)
    scope_resolution = FixedScopeResolutionPort(
        repository_id=seed.repository_id,
        baseline_head=BASELINE_HEAD,
    )
    first = append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="replay-key"),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    replay = append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="replay-key"),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, 1, tzinfo=UTC),
    )
    assert replay.replay is True
    assert replay.event_id == first.event_id
    assert replay.sequence == first.sequence
