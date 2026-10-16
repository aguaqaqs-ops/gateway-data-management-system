"""Preview publish_preview integration and serial publication tests."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from gateway_backend.application.checkpoints import load_ready_closure
from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_PUBLISH_HANDLER,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.state import WritePrecondition
from tests.support.preview_job_harness import (
    BASELINE_HEAD,
    IDEMPOTENCY_KEY,
    REPOSITORY_ID,
    PreviewJobHarness,
    build_preview_harness,
    claim_next_step,
    insert_preview_operation,
    run_claimed_handler,
)
from tests.support.workspace_fixtures import make_baseline_head

pytestmark = pytest.mark.integration


def _run_through_assemble(harness: PreviewJobHarness, operation_id: str) -> None:
    insert_preview_operation(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)


def test_publish_succeeds_and_updates_workspace_pointer(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-publish-success"
    harness.seed_workspace()
    _run_through_assemble(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assemble_step = unit_of_work.operations.get_step(f"{operation_id}-step-2")
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_operation.ready_closure_ref is not None
    assert workspace is not None
    assert workspace.current_preview_result_id is not None
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert unit_of_work.protection.is_protected(
            persisted_operation.ready_closure_ref.artifact_id
        )
        closure = load_ready_closure(harness.artifact_store, persisted_operation.ready_closure_ref)
        for ref in closure.artifact_refs():
            assert unit_of_work.protection.is_protected(ref.artifact_id)
        if assemble_step.checkpoint_ref is not None:
            assert not unit_of_work.protection.is_protected(
                assemble_step.checkpoint_ref.artifact_id
            )


def test_publish_supersedes_when_generation_drifts(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-publish-superseded"
    harness.seed_workspace()
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None
        bumped = dataclasses.replace(workspace, generation=workspace.generation + 1, optimistic_version=workspace.optimistic_version + 1)
        unit_of_work.workspace.save_workspace(bumped, expected_version=workspace.optimistic_version)
    _run_through_assemble(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assemble_step = unit_of_work.operations.get_step(f"{operation_id}-step-2")
        materialize_step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    assert persisted_operation.status is OperationStatus.SUPERSEDED
    assert workspace is not None
    assert workspace.current_preview_result_id is None
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        if assemble_step.checkpoint_ref is not None:
            assert not unit_of_work.protection.is_protected(
                assemble_step.checkpoint_ref.artifact_id
            )
        if materialize_step.checkpoint_ref is not None:
            assert not unit_of_work.protection.is_protected(
                materialize_step.checkpoint_ref.artifact_id
            )


def test_publish_cancel_before_publication_leaves_workspace_unchanged(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-publish-cancel"
    harness.seed_workspace()
    _run_through_assemble(harness, operation_id)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(f"{operation_id}-step-2")
        materialize_step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
        assemble_checkpoint = assemble_step.checkpoint_ref
        materialize_checkpoint = materialize_step.checkpoint_ref
        assert assemble_checkpoint is not None
        assert materialize_checkpoint is not None
        assert unit_of_work.protection.is_protected(assemble_checkpoint.artifact_id)
        assert unit_of_work.protection.is_protected(materialize_checkpoint.artifact_id)
    session, control, operation, step = claim_next_step(harness)
    worker_id = "worker-preview-1"
    lease_token = "lease-preview-1"
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        store = unit_of_work.operations
        transaction_now = store.transaction_now
        operation_after = dataclasses.replace(
            store.get_operation(operation_id),
            cancel_requested=True,
            optimistic_version=store.get_operation(operation_id).optimistic_version + 1,
            updated_at=transaction_now,
        )
        step_after = dataclasses.replace(
            store.get_step(step.step_id),
            cancel_requested=True,
            optimistic_version=store.get_step(step.step_id).optimistic_version + 1,
            updated_at=transaction_now,
        )
        OperationLifecycleActions(store, transaction_now=transaction_now).cancel_intent(
            operation_after,
            WritePrecondition(expected_optimistic_version=operation.optimistic_version, worker_id=None, lease_token=None),
            step_after,
            WritePrecondition(expected_optimistic_version=step.optimistic_version, worker_id=worker_id, lease_token=lease_token),
        )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step.step_id)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert not unit_of_work.protection.is_protected(assemble_checkpoint.artifact_id)
        assert not unit_of_work.protection.is_protected(materialize_checkpoint.artifact_id)
    assert persisted_operation.status is OperationStatus.CANCELLED
    assert workspace is not None
    assert workspace.current_preview_result_id is None


def test_publish_supersedes_when_baseline_head_drifts(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-publish-baseline-drift"
    harness.seed_workspace()
    _run_through_assemble(harness, operation_id)
    harness.baseline_head_read.heads[REPOSITORY_ID] = make_baseline_head(
        version=BASELINE_HEAD.baseline_head_version + 1,
        commit_id="commit-drift",
    )
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.status is OperationStatus.SUPERSEDED


def test_successful_publish_does_not_insert_preview_idempotency(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-publish-idempotency"
    harness.seed_workspace()
    _run_through_assemble(harness, operation_id)
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        replay = unit_of_work.workspace.find_preview_idempotency(
            harness.upload_revision.workspace_id,
            IDEMPOTENCY_KEY,
        )
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
    assert replay is None
    assert workspace is not None
    assert workspace.current_preview_result_id is not None
