"""Submit checkpoint artifact protection release."""

from __future__ import annotations

from gateway_backend.application.submission.ports import SubmitControlTransaction
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)


def _successor_step_id(operation_id: str, step_name: str) -> str:
    suffix = {
        SUBMIT_STEP_PREPARE: "1",
        SUBMIT_STEP_SUBMIT: "2",
        SUBMIT_STEP_AWAIT: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


def release_submit_checkpoint_protection(
    unit_of_work: SubmitControlTransaction,
    *,
    operation_id: str,
) -> None:
    for step_name in (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT):
        unit_of_work.clear_artifact_protection(
            owner_kind="submit-checkpoint",
            owner_id=_successor_step_id(operation_id, step_name),
        )
