"""Preview materialize_inputs integration tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.preview_jobs import (
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_STEP_ASSEMBLE,
    PreviewJobError,
    decode_preview_payload,
)
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactRole
from gateway_backend.application.workspace.preview import build_preview_job_payload
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import StepStatus
from tests.support.preview_job_harness import (
    IDEMPOTENCY_KEY,
    REPOSITORY_ID,
    WORKSPACE_ID,
    build_preview_harness,
    claim_next_step,
    decode_payload_object,
    insert_preview_operation,
    run_claimed_handler,
    step_id_for,
    store_source_package,
)
from tests.support.table_rules import _runtime_comparison_ruleset_digest

pytestmark = pytest.mark.integration


def test_materialize_uses_frozen_baseline_exact_commit(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    payload = decode_preview_payload(decode_payload_object(harness))
    from gateway_backend.application.preview_jobs import _materialize_all_sides

    _materialize_all_sides(payload, harness.deps)
    assert harness.baseline_provider.last_session is not None
    assert harness.baseline_provider.last_session.pinned_commit_hash() == "commit-base"


def test_full_materialize_publishes_checkpoint_and_assemble_successor(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.FULL)
    operation_id = "op-materialize-full"
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
        assemble_step = unit_of_work.operations.get_step(step_id_for(operation_id, PREVIEW_STEP_ASSEMBLE))
    assert materialize_step.status is StepStatus.SUCCEEDED
    assert materialize_step.checkpoint_ref is not None
    assert assemble_step.status is StepStatus.PENDING
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = envelope.job_state["sides"]
    assert isinstance(sides, dict)
    assert {"BASELINE", "INITIAL", "MODIFIED"}.issubset(sides)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.protection.is_protected(materialize_step.checkpoint_ref.artifact_id)


def test_modified_only_reuses_baseline_for_effective_initial(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    operation_id = "op-materialize-modified-only"
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        materialize_step = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
    assert materialize_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, materialize_step.checkpoint_ref)
    sides = envelope.job_state["sides"]
    assert isinstance(sides, dict)
    assert sides.get("initial_reuses_baseline") is True
    assert sides["BASELINE"]["snapshot_digest"] == sides["INITIAL"]["snapshot_digest"]


def test_materialize_fails_when_upload_package_is_invalid(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path, input_completeness=InputCompleteness.MODIFIED_ONLY)
    bad_binding = store_source_package(
        harness.artifact_store,
        b"not-a-valid-package",
        artifact_id="bad-package",
    )
    upload_revision = replace(
        harness.upload_revision,
        source_artifacts={SourceArtifactRole.MODIFIED: bad_binding},
    )
    harness.upload_revision = upload_revision
    harness.job_payload = build_preview_job_payload(
        workspace_id=WORKSPACE_ID,
        upload_revision=upload_revision,
        repository_id=REPOSITORY_ID,
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=3,
        idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    payload = decode_preview_payload(decode_payload_object(harness))
    from gateway_backend.application.preview_jobs import _materialize_all_sides

    with pytest.raises(PreviewJobError, match="uploaded"):
        _materialize_all_sides(payload, harness.deps)
