"""Preview three-step worker composition integration tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from gateway_shared_kernel import DigestRef

from gateway_backend.application.preview_jobs import (
    PREVIEW_ASSEMBLE_HANDLER,
    PREVIEW_MATERIALIZE_HANDLER,
    PREVIEW_PUBLISH_HANDLER,
    PREVIEW_STEP_ASSEMBLE,
    PREVIEW_STEP_MATERIALIZE,
    PREVIEW_STEP_PUBLISH,
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

RULESET_MISMATCH_STEPS = (
    (PREVIEW_STEP_MATERIALIZE, PREVIEW_MATERIALIZE_HANDLER, ()),
    (PREVIEW_STEP_ASSEMBLE, PREVIEW_ASSEMBLE_HANDLER, (PREVIEW_MATERIALIZE_HANDLER,)),
    (
        PREVIEW_STEP_PUBLISH,
        PREVIEW_PUBLISH_HANDLER,
        (PREVIEW_MATERIALIZE_HANDLER, PREVIEW_ASSEMBLE_HANDLER),
    ),
)


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


@pytest.mark.parametrize(
    ("step_name", "handler_identity", "prior_handlers"),
    RULESET_MISMATCH_STEPS,
    ids=("materialize", "assemble", "publish"),
)
def test_preview_rejects_ruleset_change_before_each_step(
    tmp_path: Path,
    step_name: str,
    handler_identity: str,
    prior_handlers: tuple[str, ...],
) -> None:
    harness = build_preview_harness(tmp_path)
    operation_id = f"op-preview-ruleset-{step_name}"
    harness.seed_workspace()
    insert_preview_operation(harness, operation_id)

    for prior_handler in prior_handlers:
        session, control, operation, step = claim_next_step(harness)
        run_claimed_handler(harness, prior_handler, session, control, operation, step)

    session, control, operation, step = claim_next_step(harness)
    assert step.step_name == step_name
    with patch(
        "gateway_backend.application.preview_jobs.comparison_rule_set",
        return_value=SimpleNamespace(ruleset_digest=DigestRef("sha256:" + "cd" * 32)),
    ):
        run_claimed_handler(harness, handler_identity, session, control, operation, step)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        failed_operation = unit_of_work.operations.get_operation(operation_id)
        failed_step = unit_of_work.operations.get_step(step_id_for(operation_id, step_name))
    assert failed_operation.status is OperationStatus.FAILED
    assert failed_operation.diagnostic is not None
    assert failed_operation.diagnostic.code == "PREVIEW_RULESET_VERSION_MISMATCH"
    assert failed_step.status is StepStatus.FAILED
