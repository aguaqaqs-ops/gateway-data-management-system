from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ..operations import (
    OperationCallerType,
    OperationKind,
    OperationParallelPolicy,
    OperationPlan,
    OperationRecord,
    OperationRuntime,
    OperationRunResult,
    OperationStepContext,
    OperationStepOutcome,
    OperationStepPlan,
)
from ..core.digests import DigestRef
from ..submissions.review import (
    SubmissionReviewCommand,
    SubmissionReviewResult,
    SubmissionReviewService,
)


class SubmissionReviewAction(StrEnum):
    START_REVIEW = "START_REVIEW"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    WITHDRAW = "WITHDRAW"


@dataclass(frozen=True, slots=True)
class SubmissionReviewFlowInput:
    submission_review_service: SubmissionReviewService
    review_command: SubmissionReviewCommand
    review_action: SubmissionReviewAction | str
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "submission-review-worker"
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.submission_review_service, SubmissionReviewService):
            raise TypeError("submission_review_service must be a SubmissionReviewService")
        if not isinstance(self.review_command, SubmissionReviewCommand):
            raise TypeError("review_command must be a SubmissionReviewCommand")
        object.__setattr__(self, "review_action", SubmissionReviewAction(self.review_action))
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")


@dataclass(frozen=True, slots=True)
class SubmissionReviewFlowResult:
    operation: OperationRecord
    run_result: OperationRunResult
    review_result: SubmissionReviewResult
    review_action: SubmissionReviewAction | str

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.run_result, OperationRunResult):
            raise TypeError("run_result must be an OperationRunResult")
        if not isinstance(self.review_result, SubmissionReviewResult):
            raise TypeError("review_result must be a SubmissionReviewResult")
        object.__setattr__(self, "review_action", SubmissionReviewAction(self.review_action))


@dataclass(frozen=True, slots=True)
class SubmissionReviewWorker:
    def start_or_resume(self, flow_input: SubmissionReviewFlowInput) -> SubmissionReviewFlowResult:
        return run_submission_review(flow_input)


def run_submission_review(flow_input: SubmissionReviewFlowInput) -> SubmissionReviewFlowResult:
    if not isinstance(flow_input, SubmissionReviewFlowInput):
        raise TypeError("flow_input must be a SubmissionReviewFlowInput")

    review_result: SubmissionReviewResult | None = None
    plan = OperationPlan(
        operation_kind=OperationKind.SUBMISSION_REVIEW,
        caller_type=OperationCallerType.FINALIZE_WRITE_CALLER,
        parallel_policy=OperationParallelPolicy.SERIAL,
        request_payload=_submission_review_request_payload(flow_input),
        steps=(
            OperationStepPlan(step_name="LOAD_INPUT"),
            OperationStepPlan(step_name="APPLY_REVIEW_ACTION", retryable=True),
            OperationStepPlan(step_name="PUBLISH_RESULT"),
            OperationStepPlan(step_name="CLEANUP"),
        ),
    )
    operation = flow_input.operation_runtime.create_operation(
        plan,
        operation_id=flow_input.operation_id,
    )

    def load_input(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(
            value={
                "submission_id": flow_input.review_command.submission_id,
                "actor_id": flow_input.review_command.actor_id,
                "review_action": flow_input.review_action.value,
            }
        )

    def apply_review_action(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal review_result
        if flow_input.review_action is SubmissionReviewAction.START_REVIEW:
            review_result = flow_input.submission_review_service.start_review(flow_input.review_command)
        elif flow_input.review_action is SubmissionReviewAction.APPROVE:
            review_result = flow_input.submission_review_service.approve(flow_input.review_command)
        elif flow_input.review_action is SubmissionReviewAction.REJECT:
            review_result = flow_input.submission_review_service.reject(flow_input.review_command)
        elif flow_input.review_action is SubmissionReviewAction.WITHDRAW:
            review_result = flow_input.submission_review_service.withdraw(flow_input.review_command)
        else:  # pragma: no cover - exhaustive guard
            raise ValueError(f"unsupported review action: {flow_input.review_action}")
        return OperationStepOutcome.success(
            value={
                "submission_id": review_result.submission.submission_id,
                "submission_status": review_result.submission.status.value,
                "workspace_status": review_result.workspace.status.value,
            }
        )

    def publish_result(context: OperationStepContext) -> OperationStepOutcome:
        if review_result is None:
            raise RuntimeError("review result must be available before publish")
        ready_payload = _submission_review_ready_payload(
            review_result=review_result,
            review_action=flow_input.review_action,
        )
        return OperationStepOutcome.success(
            value=ready_payload,
            ready_closure_digest=DigestRef.from_payload(ready_payload),
        )

    def cleanup(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(value={"cleanup": "noop"})

    run_result = flow_input.operation_runtime.run_operation(
        operation.operation_id,
        handlers={
            "LOAD_INPUT": load_input,
            "APPLY_REVIEW_ACTION": apply_review_action,
            "PUBLISH_RESULT": publish_result,
            "CLEANUP": cleanup,
        },
        worker_id=flow_input.worker_id,
    )

    if review_result is None:
        raise RuntimeError("submission review operation completed without a review result")

    return SubmissionReviewFlowResult(
        operation=run_result.operation,
        run_result=run_result,
        review_result=review_result,
        review_action=flow_input.review_action,
    )


def _submission_review_request_payload(flow_input: SubmissionReviewFlowInput) -> Mapping[str, object]:
    return {
        "operation_kind": OperationKind.SUBMISSION_REVIEW.value,
        "caller_type": OperationCallerType.FINALIZE_WRITE_CALLER.value,
        "submission_id": flow_input.review_command.submission_id,
        "actor_id": flow_input.review_command.actor_id,
        "review_action": flow_input.review_action.value,
    }


def _submission_review_ready_payload(
    *,
    review_result: SubmissionReviewResult,
    review_action: SubmissionReviewAction,
) -> dict[str, object]:
    return {
        "submission_id": review_result.submission.submission_id,
        "review_action": review_action.value,
        "submission_status": review_result.submission.status.value,
        "workspace_status": review_result.workspace.status.value,
    }
