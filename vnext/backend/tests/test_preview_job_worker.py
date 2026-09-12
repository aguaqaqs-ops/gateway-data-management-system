"""Preview three-step worker composition integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_PUBLISH_HANDLER,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import OperationStatus, StepStatus
from tests.support.preview_job_harness import (
    build_preview_harness,
    claim_next_step,
    insert_preview_operation,
    run_claimed_handler,
    step_id_for,
)

pytestmark = pytest.mark.integration


def test_preview_worker_topology_reaches_succeeded(tmp_path: Path) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = "op-preview-worker"
    harness.seed_workspace()
    insert_preview_operation(harness, operation_id)

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == "materialize_inputs"
    run_claimed_handler(harness, PREVIEW_MATERIALIZE_HANDLER, session, control, operation, step)

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == "assemble_preview"
    run_claimed_handler(harness, PREVIEW_ASSEMBLE_HANDLER, session, control, operation, step)

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == "publish_preview"
    run_claimed_handler(harness, PREVIEW_PUBLISH_HANDLER, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        materialize = unit_of_work.operations.get_step(step_id_for(operation_id, "materialize_inputs"))
        assemble = unit_of_work.operations.get_step(step_id_for(operation_id, "assemble_preview"))
        publish = unit_of_work.operations.get_step(step_id_for(operation_id, "publish_preview"))
        workspace = unit_of_work.workspace.get_workspace(harness.upload_revision.workspace_id)
    assert operation.status is OperationStatus.SUCCEEDED
    assert materialize.status is StepStatus.SUCCEEDED
    assert assemble.status is StepStatus.SUCCEEDED
    assert publish.status is StepStatus.SUCCEEDED
    assert operation.ready_closure_ref is not None
    assert workspace is not None
    assert workspace.current_preview_result_id is not None
