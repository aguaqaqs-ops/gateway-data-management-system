from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..contracts.submit import (
    PreviewInputBinding,
    SubmitAccepted,
    SubmitOperationStatus,
    SubmitSourcePackage,
    validate_submit_source_package_binding,
)
from ..operations import (
    OperationCallerType,
    OperationKind,
    OperationParallelPolicy,
    OperationPlan,
    OperationRecord,
    OperationRuntime,
    OperationStepPlan,
)
from ..submissions.store import SubmissionIdentityStore


@dataclass(frozen=True, slots=True)
class SubmitAcceptanceFlowInput:
    submit_source_package: SubmitSourcePackage
    preview_input_binding: PreviewInputBinding
    submission_identity_store: SubmissionIdentityStore
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "submit-acceptance-worker"
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.submit_source_package, SubmitSourcePackage):
            raise TypeError("submit_source_package must be a SubmitSourcePackage")
        if not isinstance(self.preview_input_binding, PreviewInputBinding):
            raise TypeError("preview_input_binding must be a PreviewInputBinding")
        if not hasattr(self.submission_identity_store, "next_identity"):
            raise TypeError("submission_identity_store must implement next_identity()")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")


@dataclass(frozen=True, slots=True)
class SubmitAcceptanceFlowResult:
    accepted: SubmitAccepted
    operation: OperationRecord
    submit_source_package: SubmitSourcePackage
    preview_input_binding: PreviewInputBinding

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, SubmitAccepted):
            raise TypeError("accepted must be a SubmitAccepted")
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.submit_source_package, SubmitSourcePackage):
            raise TypeError("submit_source_package must be a SubmitSourcePackage")
        if not isinstance(self.preview_input_binding, PreviewInputBinding):
            raise TypeError("preview_input_binding must be a PreviewInputBinding")

    @property
    def submission_id(self) -> str:
        return self.accepted.submission_id


def _submit_finalize_request_payload(
    submit_source_package: SubmitSourcePackage,
    preview_input_binding: PreviewInputBinding,
    *,
    submission_id: str,
) -> dict[str, object]:
    return {
        "submit_operation_status": SubmitOperationStatus.ACCEPTED.value,
        "submission_id": submission_id,
        "source_package_id": submit_source_package.source_package_id,
        "source_kind": submit_source_package.source_kind,
        "package_kind": submit_source_package.package_kind,
        "source_package_digest": submit_source_package.source_package_digest.to_payload(),
        "package_manifest_digest": submit_source_package.package_manifest_digest.to_payload(),
        "required_entries_manifest_digest": submit_source_package.required_entries_manifest_digest.to_payload(),
        "parser_version": submit_source_package.parser_version,
        "table_ruleset_version": submit_source_package.table_ruleset_version,
        "artifact_ref": submit_source_package.artifact_ref.to_payload(),
        "size_bytes": submit_source_package.size_bytes,
        "retention_policy": submit_source_package.retention_policy,
        "binding_id": preview_input_binding.binding_id,
        "workspace_id": preview_input_binding.workspace_id,
        "upload_generation": preview_input_binding.upload_generation,
        "preview_source_digest": preview_input_binding.preview_source_digest.to_payload(),
        "preview_required_entries_manifest_digest": preview_input_binding.required_entries_manifest_digest.to_payload(),
        "before_snapshot_digest": preview_input_binding.before_snapshot_digest.to_payload()
        if preview_input_binding.before_snapshot_digest is not None
        else None,
        "current_snapshot_digest": preview_input_binding.current_snapshot_digest.to_payload()
        if preview_input_binding.current_snapshot_digest is not None
        else None,
        "comparison_digest": preview_input_binding.comparison_digest.to_payload()
        if preview_input_binding.comparison_digest is not None
        else None,
        "accepted_binding_contract_version": preview_input_binding.binding_contract_version,
        "generated_at": preview_input_binding.generated_at.astimezone(timezone.utc).isoformat(),
    }


def _build_submit_finalize_operation_plan(
    submit_source_package: SubmitSourcePackage,
    preview_input_binding: PreviewInputBinding,
    *,
    submission_id: str,
) -> OperationPlan:
    return OperationPlan(
        operation_kind=OperationKind.SUBMIT_FINALIZE,
        caller_type=OperationCallerType.FINALIZE_WRITE_CALLER,
        parallel_policy=OperationParallelPolicy.SERIAL,
        request_payload=_submit_finalize_request_payload(
            submit_source_package,
            preview_input_binding,
            submission_id=submission_id,
        ),
        generation=preview_input_binding.upload_generation,
        steps=(
            OperationStepPlan(step_name="LOAD_INPUT"),
            OperationStepPlan(step_name="RUN_REPOSITORY_IMPORT", retryable=True),
            OperationStepPlan(step_name="PUBLISH_RESULT"),
            OperationStepPlan(step_name="CLEANUP"),
        ),
    )


def run_submit_acceptance(flow_input: SubmitAcceptanceFlowInput) -> SubmitAcceptanceFlowResult:
    if not isinstance(flow_input, SubmitAcceptanceFlowInput):
        raise TypeError("flow_input must be a SubmitAcceptanceFlowInput")

    validate_submit_source_package_binding(
        flow_input.submit_source_package,
        flow_input.preview_input_binding,
    )
    now = datetime.now(timezone.utc)
    submission_id = flow_input.submission_identity_store.next_identity()
    plan = _build_submit_finalize_operation_plan(
        flow_input.submit_source_package,
        flow_input.preview_input_binding,
        submission_id=submission_id,
    )
    operation = flow_input.operation_runtime.create_operation(
        plan,
        operation_id=flow_input.operation_id,
        now=now,
    )
    accepted = SubmitAccepted(
        operation_id=operation.operation_id,
        submission_id=submission_id,
        source_package_id=flow_input.submit_source_package.source_package_id,
        binding_id=flow_input.preview_input_binding.binding_id,
        accepted_at=now,
        submit_source_package_digest=flow_input.submit_source_package.source_package_digest,
        required_entries_manifest_digest=flow_input.submit_source_package.required_entries_manifest_digest,
        parser_version=flow_input.submit_source_package.parser_version,
        table_ruleset_version=flow_input.submit_source_package.table_ruleset_version,
        preview_source_digest=flow_input.preview_input_binding.preview_source_digest,
    )
    return SubmitAcceptanceFlowResult(
        accepted=accepted,
        operation=operation,
        submit_source_package=flow_input.submit_source_package,
        preview_input_binding=flow_input.preview_input_binding,
    )


__all__ = [
    "SubmitAcceptanceFlowInput",
    "SubmitAcceptanceFlowResult",
    "run_submit_acceptance",
]
