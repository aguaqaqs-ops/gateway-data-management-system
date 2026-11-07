"""Archive audit append and idempotency tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.archive.audit import (
    AppendArchiveAnomalyResolutionCommand,
    AppendArchiveConfirmationCommand,
    append_archive_anomaly_resolution,
    append_archive_confirmation,
)
from gateway_backend.application.archive.contracts import ArchiveAuditReferenceInput
from gateway_backend.application.archive.errors import (
    ArchiveAuditVersionConflict,
    ArchiveConfirmationRequired,
    ArchiveRequestValidation,
)
from gateway_backend.application.archive.start import StartArchiveCommand, start_archive
from gateway_backend.application.submission.errors import IdempotencyConflict
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
    ArchiveSubjectKind,
)
from tests.support.archive_fixtures import (
    ArchiveSeed,
    append_selection_confirmation,
    seed_approved_archive_candidate,
    seed_approved_dual_sibling_archive,
    start_archive_for_seed,
)
from tests.test_review_transactions import _uow_factory
from tests.test_submit_transactions import BASELINE_HEAD

pytestmark = pytest.mark.unit

CONFIRMATION_IDEMPOTENCY_CONFLICT_SHAPES = (
    pytest.param("selected_submission_id", "sub-other", id="selected-id"),
    pytest.param("expected_candidate_digest", "sha256:" + "1" * 64, id="candidate-digest"),
    pytest.param("candidate_set_digest", "sha256:" + "2" * 64, id="candidate-set-digest"),
)

RESOLUTION_IDEMPOTENCY_CONFLICT_SHAPES = (
    pytest.param("target_submission_id", "sub-other", id="sibling-id"),
    pytest.param("target_candidate_digest", "sha256:" + "3" * 64, id="sibling-digest"),
    pytest.param("candidate_set_digest", "sha256:" + "4" * 64, id="candidate-set-digest"),
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


@pytest.mark.parametrize(("field_name", "replacement"), CONFIRMATION_IDEMPOTENCY_CONFLICT_SHAPES)
def test_confirmation_replay_rejects_changed_binding_fields(
    db_path: Path,
    field_name: str,
    replacement: str,
) -> None:
    seed = seed_approved_archive_candidate(db_path)
    append_archive_confirmation(
        command=_confirmation_command(seed),
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
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )


def test_confirmation_rejects_unknown_selected_candidate(db_path: Path) -> None:
    from dataclasses import replace as dc_replace

    from gateway_backend.application.archive.contracts import (
        ArchiveSelectedRef,
        compute_selection_subject_digest,
    )
    from gateway_backend.application.submission.errors import BaselineVersionConflict

    seed = seed_approved_archive_candidate(db_path)
    bogus_selected = ArchiveSelectedRef(
        submission_id="nonexistent-submission",
        expected_candidate_digest=seed.selected_ref.expected_candidate_digest,
    )
    bogus_subject = compute_selection_subject_digest(
        candidate_set_digest=seed.candidate_set_digest,
        selected_submission_id=bogus_selected.submission_id,
        expected_candidate_digest=bogus_selected.expected_candidate_digest,
    )
    with pytest.raises(BaselineVersionConflict, match="unknown or stale"):
        append_archive_confirmation(
            command=dc_replace(
                _confirmation_command(seed),
                selected=bogus_selected,
                subject_digest=bogus_subject,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )


def test_resolution_rejects_selected_as_sibling(db_path: Path) -> None:
    from gateway_backend.application.archive.contracts import compute_anomaly_subject_digest
    from gateway_backend.application.submission.errors import BaselineVersionConflict

    seed = seed_approved_archive_candidate(db_path)
    subject_digest = compute_anomaly_subject_digest(
        selection_subject_digest=seed.selection_subject_digest,
        issue_code="APPROVED_SIBLING_EXCLUDED",
        target_submission_id=seed.selected_ref.submission_id,
        target_candidate_digest=seed.selected_ref.expected_candidate_digest,
    )
    with pytest.raises(BaselineVersionConflict, match="does not match current snapshot"):
        append_archive_anomaly_resolution(
            command=AppendArchiveAnomalyResolutionCommand(
                context=seed.archiver_context,
                idempotency_key="invalid-sibling-resolution",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                selected=seed.selected_ref,
                candidate_set_digest=seed.candidate_set_digest,
                subject_digest=subject_digest,
                expected_sequence=0,
                action=ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION,
                reason="invalid sibling",
                subject_kind=ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED,
                issue_code="APPROVED_SIBLING_EXCLUDED",
                target_submission_id=seed.selected_ref.submission_id,
                target_candidate_digest=seed.selected_ref.expected_candidate_digest,
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )


def test_confirmation_replay_returns_original_event_after_subject_expires(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    first = append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="replay-key"),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    confirmation_sequence = first.sequence
    start_archive_for_seed(seed, confirmation_sequence=confirmation_sequence, now=datetime(2024, 7, 1, 1, tzinfo=UTC))
    replay = append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="replay-key"),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, 2, tzinfo=UTC),
    )
    assert replay.replay is True
    assert replay.event_id == first.event_id
    assert replay.sequence == first.sequence


def test_resolution_revoke_on_empty_stream_is_rejected(db_path: Path) -> None:
    dual_seed = seed_approved_dual_sibling_archive(db_path)
    with pytest.raises(ArchiveAuditVersionConflict):
        append_archive_anomaly_resolution(
            command=_resolution_command(
                dual_seed,
                action=ArchiveAnomalyResolutionAction.REVOKE,
                reason="revoke without stream",
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )


def test_confirmation_revoke_on_empty_stream_is_rejected(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    with pytest.raises(ArchiveAuditVersionConflict):
        append_archive_confirmation(
            command=_confirmation_command(
                seed,
                action=ArchiveConfirmationAction.REVOKE,
                reason="revoke without stream",
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )


def test_confirmation_revoke_invalidates_affirmative_state(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    confirm = append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="confirm-then-revoke"),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    append_archive_confirmation(
        command=_confirmation_command(
            seed,
            idempotency_key="revoke-key",
            expected_sequence=confirm.sequence,
            action=ArchiveConfirmationAction.REVOKE,
            reason="revoke selection",
        ),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(ArchiveConfirmationRequired):
        start_archive(
            command=StartArchiveCommand(
                context=seed.archiver_context,
                idempotency_key="start-after-revoke",
                expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
                expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
                candidate_set_digest=seed.candidate_set_digest,
                selected_ref=seed.selected_ref,
                confirmation_refs=(
                    ArchiveAuditReferenceInput(
                        subject_digest=seed.selection_subject_digest,
                        sequence=confirm.sequence,
                    ),
                ),
                anomaly_resolution_refs=(),
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 2, tzinfo=UTC),
        )


INVALID_CONFIRMATION_SEQUENCE_SHAPES = (
    pytest.param(True, id="bool-true"),
    pytest.param(False, id="bool-false"),
    pytest.param(1.0, id="float"),
)


@pytest.mark.parametrize("expected_sequence", INVALID_CONFIRMATION_SEQUENCE_SHAPES)
def test_confirmation_rejects_non_integer_expected_sequence(
    db_path: Path,
    expected_sequence: object,
) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    seed = seed_approved_archive_candidate(db_path)
    with pytest.raises(ArchiveRequestValidation, match="expected_sequence must be a non-negative integer"):
        append_archive_confirmation(
            command=_confirmation_command(seed, expected_sequence=expected_sequence),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        event_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    assert event_count == 0


def test_confirmation_rejects_non_integer_expected_baseline_head_version(db_path: Path) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    seed = seed_approved_archive_candidate(db_path)
    with pytest.raises(
        ArchiveRequestValidation,
        match="expected_baseline_head_version must be a non-negative integer",
    ):
        append_archive_confirmation(
            command=_confirmation_command(seed, expected_baseline_head_version=True),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        event_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    assert event_count == 0


def test_confirmation_accepts_null_reason_for_confirm_action(db_path: Path) -> None:
    import json

    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    seed = seed_approved_archive_candidate(db_path)
    result = append_archive_confirmation(
        command=_confirmation_command(seed, reason=None),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    assert result.replay is False
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        row = unit_of_work.connection.execute(
            """
            SELECT reason, request_payload_json
            FROM archive_confirmation_events
            WHERE event_id = ?
            """,
            (result.event_id,),
        ).fetchone()
        assert row is not None
        assert row[0] is None
        payload = json.loads(row[1])
        assert payload["reason"] is None


def test_confirmation_rejects_null_reason_for_revoke_action(db_path: Path) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    seed = seed_approved_archive_candidate(db_path)
    append_archive_confirmation(
        command=_confirmation_command(seed),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    with pytest.raises(ArchiveRequestValidation, match="reason must be a string"):
        append_archive_confirmation(
            command=_confirmation_command(
                seed,
                expected_sequence=1,
                action=ArchiveConfirmationAction.REVOKE,
                reason=None,
                idempotency_key="revoke-null-reason",
            ),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        event_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_confirmation_events"
        ).fetchone()[0]
    assert event_count == 1


def test_resolution_rejects_null_reason(db_path: Path) -> None:
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork

    dual_seed = seed_approved_dual_sibling_archive(db_path)
    append_selection_confirmation(dual_seed.primary, idempotency_key="confirm-before-null-resolution")
    with pytest.raises(ArchiveRequestValidation, match="reason must be a string"):
        append_archive_anomaly_resolution(
            command=_resolution_command(dual_seed, reason=None),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        event_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM archive_anomaly_resolution_events"
        ).fetchone()[0]
    assert event_count == 0


def test_confirmation_rejects_stale_expected_sequence(db_path: Path) -> None:
    seed = seed_approved_archive_candidate(db_path)
    with pytest.raises(ArchiveAuditVersionConflict):
        append_archive_confirmation(
            command=_confirmation_command(seed, expected_sequence=99),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, tzinfo=UTC),
        )


def test_confirmation_rejects_same_key_different_actor(db_path: Path) -> None:
    from dataclasses import replace as dc_replace

    seed = seed_approved_archive_candidate(db_path)
    append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="actor-key"),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    other_actor_command = _confirmation_command(seed, idempotency_key="actor-key")
    other_actor_command = dc_replace(
        other_actor_command,
        context=dc_replace(other_actor_command.context, actor_id="archiver-2"),
    )
    with pytest.raises(IdempotencyConflict):
        append_archive_confirmation(
            command=other_actor_command,
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )


def _resolution_command(
    dual_seed: object,
    **overrides: Any,
) -> AppendArchiveAnomalyResolutionCommand:
    from tests.support.archive_fixtures import DualSiblingArchiveSeed

    assert isinstance(dual_seed, DualSiblingArchiveSeed)
    command = AppendArchiveAnomalyResolutionCommand(
        context=dual_seed.primary.archiver_context,
        idempotency_key="resolution-key-1",
        expected_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        expected_baseline_head_version=BASELINE_HEAD.baseline_head_version,
        selected=dual_seed.primary.selected_ref,
        candidate_set_digest=dual_seed.primary.candidate_set_digest,
        subject_digest=dual_seed.anomaly_subject_digest,
        expected_sequence=0,
        action=ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION,
        reason="acknowledge sibling exclusion",
        subject_kind=ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED,
        issue_code="APPROVED_SIBLING_EXCLUDED",
        target_submission_id=dual_seed.target_submission_id,
        target_candidate_digest=dual_seed.target_candidate_digest,
    )
    if overrides:
        return replace(command, **overrides)
    return command


def test_confirmation_replay_requires_transaction_fresh_enabled_mapping(db_path: Path) -> None:
    from gateway_backend.domain.workspace.errors import ScopeResolutionError
    from tests.support.baseline_fixtures import upsert_provisioned_mapping_row

    seed = seed_approved_archive_candidate(db_path)
    append_archive_confirmation(
        command=_confirmation_command(seed, idempotency_key="mapping-replay-key"),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    upsert_provisioned_mapping_row(
        seed.db_path,
        device_key=seed.archiver_context.gateway_device_external_key,
        project_id=seed.archiver_context.business_project_id,
        repository_id=seed.repository_id,
        enabled=False,
    )
    with pytest.raises(ScopeResolutionError):
        append_archive_confirmation(
            command=_confirmation_command(seed, idempotency_key="mapping-replay-key"),
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )


@pytest.mark.parametrize(("field_name", "replacement"), RESOLUTION_IDEMPOTENCY_CONFLICT_SHAPES)
def test_resolution_replay_rejects_changed_binding_fields(
    db_path: Path,
    field_name: str,
    replacement: str,
) -> None:
    dual_seed = seed_approved_dual_sibling_archive(db_path)
    append_selection_confirmation(dual_seed.primary, idempotency_key="confirm-before-resolution")
    append_archive_anomaly_resolution(
        command=_resolution_command(dual_seed),
        unit_of_work_factory=_uow_factory(db_path),
        now=datetime(2024, 7, 1, tzinfo=UTC),
    )
    mutated = _resolution_command(dual_seed)
    if field_name == "target_submission_id":
        mutated = replace(mutated, target_submission_id=replacement)
    elif field_name == "target_candidate_digest":
        mutated = replace(mutated, target_candidate_digest=replacement)
    elif field_name == "candidate_set_digest":
        mutated = replace(mutated, candidate_set_digest=replacement)
    else:
        raise AssertionError(field_name)
    with pytest.raises(IdempotencyConflict):
        append_archive_anomaly_resolution(
            command=mutated,
            unit_of_work_factory=_uow_factory(db_path),
            now=datetime(2024, 7, 1, 1, tzinfo=UTC),
        )


def test_time_acceptance_and_revoke_preserve_detected_facts_and_subject_changes_expire_acceptance(db_path: Path) -> None:
    from gateway_backend.application.archive.queries import preview_archive_plan
    from gateway_backend.domain.archive.models import affirmative_resolution_action
    from gateway_backend.domain.configuration_facts import ConfigurationGeneratedTime, CONFIGURATION_TIME_RULE
    from tests.support.archive_fixtures import replace_archive_configuration, refresh_archive_seed
    seed = seed_approved_archive_candidate(db_path)
    missing = ConfigurationGeneratedTime(CONFIGURATION_TIME_RULE, "TABLE_ABSENT", None, None, 0, 0, 0, None, None, False)
    replace_archive_configuration(db_path, seed.submission_id,
        lambda facts: replace(facts, modified=replace(facts.modified, generated_time=missing)))
    seed = refresh_archive_seed(seed)
    def preview() -> Any:
        return preview_archive_plan(context=seed.archiver_context, selected_ref=seed.selected_ref, unit_of_work_factory=_uow_factory(db_path))
    anomaly = preview().anomalies[0]
    command = AppendArchiveAnomalyResolutionCommand(seed.archiver_context, "accept-time", BASELINE_HEAD.business_baseline_node_id,
        BASELINE_HEAD.baseline_head_version, seed.selected_ref, seed.candidate_set_digest, anomaly.subject_digest,
        0, affirmative_resolution_action(anomaly.subject_kind), "source has no generation time; verified independently",
        anomaly.subject_kind, anomaly.issue_code, anomaly.target_submission_id, anomaly.target_candidate_digest)
    first = append_archive_anomaly_resolution(command=command, unit_of_work_factory=_uow_factory(db_path), now=datetime(2024, 7, 1, tzinfo=UTC))
    accepted = preview().anomalies[0]
    assert accepted.detected_status == anomaly.detected_status and accepted.details == anomaly.details
    assert accepted.resolution_status == "ACCEPTED" and accepted.latest_sequence == first.sequence
    with pytest.raises(IdempotencyConflict):
        append_archive_anomaly_resolution(command=replace(command, context=replace(command.context, actor_id="another-archiver")), unit_of_work_factory=_uow_factory(db_path), now=datetime(2024, 7, 1, tzinfo=UTC))
    revoke = replace(command, idempotency_key="revoke-time", expected_sequence=first.sequence,
        action=ArchiveAnomalyResolutionAction.REVOKE, reason="withdraw the prior acceptance")
    append_archive_anomaly_resolution(command=revoke, unit_of_work_factory=_uow_factory(db_path), now=datetime(2024, 7, 1, tzinfo=UTC))
    assert preview().anomalies[0].resolution_status == "REVOKED"
    replace_archive_configuration(db_path, seed.submission_id,
        lambda facts: replace(facts, modified=replace(facts.modified, sql_source_digest="sha256:" + "f" * 64)))
    seed = refresh_archive_seed(seed)
    fresh = preview().anomalies[0]
    assert fresh.subject_digest != anomaly.subject_digest and fresh.resolution_status == "UNRESOLVED"
    # Old successful append is a replay, without rerunning new snapshot gates.
    assert append_archive_anomaly_resolution(command=command, unit_of_work_factory=_uow_factory(db_path), now=datetime(2024, 7, 1, tzinfo=UTC)).replay


@pytest.mark.parametrize("column", ["subject_payload_json", "issue_code", "target_candidate_digest"])
def test_stored_resolution_corruption_is_rejected_by_replay_and_start(db_path: Path, column: str) -> None:
    import json
    from gateway_backend.application.archive.errors import ArchiveIntegrityFailure
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.support.archive_fixtures import append_anomaly_resolution, prepare_dual_sibling_start
    dual = seed_approved_dual_sibling_archive(db_path)
    confirmation, resolution = prepare_dual_sibling_start(dual)
    with ControlDbUnitOfWork(db_path) as uow:
        value = json.dumps({}) if column == "subject_payload_json" else "altered" if column == "issue_code" else "sha256:" + "0" * 64
        uow.connection.execute(f"UPDATE archive_anomaly_resolution_events SET {column} = ?", (value,))
    with pytest.raises(ArchiveIntegrityFailure):
        append_anomaly_resolution(dual.primary, anomaly_subject_digest=dual.anomaly_subject_digest,
            target_submission_id=dual.target_submission_id, target_candidate_digest=dual.target_candidate_digest)
    with pytest.raises(ArchiveIntegrityFailure):
        start_archive_for_seed(dual.primary, confirmation_sequence=confirmation,
            anomaly_resolution_sequences=((dual.anomaly_subject_digest, resolution),))


def test_unknown_source_acceptance_freezes_all_group_members_and_does_not_explain_them(db_path: Path) -> None:
    import json
    from gateway_shared_kernel.jcs import canonicalize_json_value
    from gateway_backend.application.archive.queries import get_archive_candidates, preview_archive_plan
    from gateway_backend.application.archive.contracts import ArchiveSelectedRef
    from gateway_backend.domain.submission.review import ReviewAction
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.support.archive_fixtures import TS_ARCHIVE
    from tests.test_review_transactions import _seed_additional_pending_review_submission, _apply_review, _apply_command
    seed = seed_approved_archive_candidate(db_path)
    first = start_archive_for_seed(seed, confirmation_sequence=append_selection_confirmation(seed))
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        source = uow.submission.get_submission(seed.submission_id)
    assert source is not None
    for sid, modified_digit in (("source-a", "7"), ("source-b", "9")):
        # Stage the original small fixture before binding it to the archived Head.
        with ControlDbUnitOfWork(db_path) as uow:
            uow.connection.execute("UPDATE baseline_head_records SET node_id = ?, optimistic_version = ? WHERE repository_id = ?",
                (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.baseline_head_version, seed.repository_id))
        pending = _seed_additional_pending_review_submission(db_path, submission_id=sid,
            device_key="device-1", repository_id=seed.repository_id, project_id="project-1")
        with ControlDbUnitOfWork(db_path) as uow:
            submission = uow.submission.get_submission(sid)
            assert submission is not None
            facts = submission.configuration_facts
            facts = replace(facts, baseline_is_initial=False, baseline_source_submission_id=seed.submission_id,
                business_baseline_node_id=first.baseline_node_id, business_baseline_commit_id=first.baseline_commit_id,
                baseline_head_version=first.baseline_head_version, initial_origin="UPLOADED",
                baseline_content_identity=source.configuration_facts.modified.content_identity,
                initial=replace(facts.initial, content_identity=replace(facts.initial.content_identity, canonical_state_digest="sha256:" + "8" * 64)),
                modified=replace(facts.modified, content_identity=replace(facts.modified.content_identity, canonical_state_digest="sha256:" + modified_digit * 64)))
            blob = canonicalize_json_value(facts.to_document())
            uow.connection.execute("UPDATE baseline_head_records SET node_id = ?, optimistic_version = ? WHERE repository_id = ?",
                (first.baseline_node_id, first.baseline_head_version, seed.repository_id))
            uow.connection.execute("""UPDATE submission_records SET based_on_baseline_node_id = ?, business_baseline_commit_id = ?,
                canonical_business_digest = ?, configuration_facts = ? WHERE submission_id = ?""",
                (first.baseline_node_id, first.baseline_commit_id, facts.modified.content_identity.canonical_state_digest, blob, sid))
            uow.connection.execute("""UPDATE submit_attempt_records SET business_baseline_node_id = ?, business_baseline_commit_id = ?,
                baseline_head_version = ?, canonical_business_digest = ?, configuration_facts = ? WHERE submit_attempt_id = ?""",
                (first.baseline_node_id, first.baseline_commit_id, first.baseline_head_version,
                    facts.modified.content_identity.canonical_state_digest, blob, submission.submit_attempt_id))
        _apply_review(pending, _apply_command(pending, action=ReviewAction.APPROVE, idempotency_key="approve-" + sid))
    candidates = get_archive_candidates(context=seed.archiver_context, unit_of_work_factory=_uow_factory(db_path))
    selected = ArchiveSelectedRef(candidates.candidates[0].submission_id, candidates.candidates[0].expected_candidate_digest)
    preview = preview_archive_plan(context=seed.archiver_context, selected_ref=selected, unit_of_work_factory=_uow_factory(db_path))
    anomaly = next(item for item in preview.anomalies if item.subject_kind is ArchiveSubjectKind.CONFIGURATION_SOURCE)
    assert anomaly.affected_submission_ids == ("source-a", "source-b")
    command = AppendArchiveAnomalyResolutionCommand(seed.archiver_context, "source-group-accept", first.baseline_node_id,
        first.baseline_head_version, selected, candidates.candidate_set_digest, anomaly.subject_digest, 0,
        ArchiveAnomalyResolutionAction.ACKNOWLEDGE_SOURCE_EXCEPTION, "the shared initial source is externally documented and accepted",
        anomaly.subject_kind, anomaly.issue_code, anomaly.target_submission_id, anomaly.target_candidate_digest)
    accepted = append_archive_anomaly_resolution(command=command, unit_of_work_factory=_uow_factory(db_path), now=TS_ARCHIVE)
    current = preview_archive_plan(context=seed.archiver_context, selected_ref=selected, unit_of_work_factory=_uow_factory(db_path))
    issue = next(item for item in current.anomalies if item.subject_kind is ArchiveSubjectKind.CONFIGURATION_SOURCE)
    assert issue.detected_status == "UNEXPLAINED" and issue.resolution_status == "ACCEPTED"
    assert all(item["detected_status"] == "UNEXPLAINED" for item in current.business_validation.source_diagnostics)
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        event = uow.archive.get_resolution_event(seed.repository_id, anomaly.subject_digest, accepted.sequence)
        assert event is not None
        body = json.loads(event.subject_payload_json)
        assert body["affected_submission_ids"] == ["source-a", "source-b"]
        assert len(body["details"]["states"]) == 3 and len(body["details"]["edges"]) == 2
        assert len(body["affected_candidates"]) == 2


def test_audit_sequence_at_safe_integer_limit_rejects_increment_without_append(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.infrastructure.control_db.sqlite_archive import SQLiteArchiveRepository
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    seed = seed_approved_archive_candidate(db_path)
    monkeypatch.setattr(SQLiteArchiveRepository, "get_latest_confirmation_sequence", lambda *args: 9007199254740991)
    with pytest.raises(ArchiveRequestValidation, match="I-JSON"):
        append_archive_confirmation(command=_confirmation_command(seed, expected_sequence=9007199254740991),
            unit_of_work_factory=_uow_factory(db_path), now=datetime(2024, 7, 1, tzinfo=UTC))
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        assert uow.connection.execute("SELECT COUNT(*) FROM archive_confirmation_events").fetchone()[0] == 0
