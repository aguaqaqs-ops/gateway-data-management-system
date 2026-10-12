"""History compare DTO mapping and result orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from pydantic import ValidationError

from gateway_backend.application.checkpoints import StepCheckpointEnvelope
from gateway_backend.application.history.compare import (
    HistoryCompareAcceptanceResult as ApplicationHistoryCompareAcceptanceResult,
    accept_history_compare,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    history_compare_step_id,
)
from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryNodeRef,
)
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.http.dependencies import AdmissionGatePort, BundleReaderPort, acquire_new_work
from gateway_backend.http.errors import ApiError, map_domain_exception
from gateway_backend.http.schemas.history import (
    HistoryCompareAcceptResponse,
    HistoryCompareDiagnosticResponse,
    HistoryComparePairResultResponse,
    HistoryCompareResultInputResponse,
    HistoryCompareResultResponse,
    HistoryNodeRefKindLiteral,
    HistoryNodeRefResponse,
    IntegrityIncidentResponse,
)
from gateway_backend.operations.contracts import OperationRecord, OperationStatus


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptanceResult:
    response: HistoryCompareAcceptResponse
    replay: bool


def accept_compare_operation(
    *,
    command: HistoryCompareAcceptCommand,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    admission_gate: AdmissionGatePort,
    comparison_ruleset_digest: str,
    now: datetime,
) -> HistoryCompareAcceptanceResult:
    try:
        with acquire_new_work(
            admission_gate,
            closed_code="ADMISSION_CONFLICT",
            closed_status=409,
        ):
            result = accept_history_compare(
                command=command,
                unit_of_work_factory=unit_of_work_factory,
                job_registry=job_registry,
                comparison_ruleset_digest=comparison_ruleset_digest,
                now=now,
            )
    except ApiError:
        raise
    except Exception as exc:
        mapped = map_domain_exception(exc)
        if mapped is None:
            raise
        raise mapped from exc
    return HistoryCompareAcceptanceResult(
        response=history_compare_acceptance_to_response(result),
        replay=result.replay,
    )


def history_compare_acceptance_to_response(
    result: ApplicationHistoryCompareAcceptanceResult,
) -> HistoryCompareAcceptResponse:
    return HistoryCompareAcceptResponse(
        operation_id=result.operation_id,
        status=_public_operation_status(result.status),
        replayed=result.replay,
    )


def get_compare_result(
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> HistoryCompareResultResponse:
    integrity = None
    with unit_of_work_factory(read_only=True) as unit_of_work:
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(operation.operation_id)
    if incident is not None and operation.status is OperationStatus.FAILED:
        integrity = IntegrityIncidentResponse.from_record(incident)
    diagnostic = None
    if operation.diagnostic is not None:
        diagnostic = HistoryCompareDiagnosticResponse(
            code=operation.diagnostic.code,
            message=operation.diagnostic.message,
        )
    result = None
    if operation.status is OperationStatus.SUCCEEDED:
        result = _load_success_result(
            operation=operation,
            acceptance=acceptance,
            unit_of_work_factory=unit_of_work_factory,
            artifact_store=artifact_store,
        )
    return HistoryCompareResultResponse(
        operation_id=operation.operation_id,
        status=_public_operation_status(operation.status),
        diagnostic=diagnostic,
        integrity_incident=integrity,
        result=result,
    )


def read_compare_bundle(
    *,
    operation: OperationRecord,
    bundle_reader: BundleReaderPort,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> tuple[str, object]:
    if operation.status is not OperationStatus.SUCCEEDED:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    bundle_artifact_id = _bundle_artifact_id(
        operation=operation,
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=artifact_store,
    )
    try:
        return bundle_reader.read_bundle(bundle_artifact_id)
    except KeyError:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="bundle is not available",
            status_code=404,
        ) from None


def _public_operation_status(
    status: OperationStatus,
) -> Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]:
    if status is OperationStatus.QUEUED:
        return "QUEUED"
    if status is OperationStatus.RUNNING:
        return "RUNNING"
    if status is OperationStatus.SUCCEEDED:
        return "SUCCEEDED"
    if status is OperationStatus.FAILED:
        return "FAILED"
    if status is OperationStatus.CANCELLED:
        return "CANCELLED"
    return cast(Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"], status.value)


def _load_checkpoint_envelope_from_store(
    artifact_store: object,
    ref: ArtifactRef,
) -> StepCheckpointEnvelope:
    try:
        locate = getattr(artifact_store, "locate", None)
        if locate is not None:
            raw_bytes = locate(ref)
        else:
            read_exact = getattr(artifact_store, "read_exact", None)
            if read_exact is None:
                raise TypeError("artifact_store must support read_exact or locate")
            raw_bytes = b"".join(read_exact(ref))
            verify_readable = getattr(artifact_store, "verify_readable", None)
            if verify_readable is None:
                raise ManifestVerificationError("artifact store does not support digest verification")
            verification = verify_readable(
                ref,
                expected_size=ref.size_bytes,
                expected_raw_sha256=ref.raw_sha256,
            )
            if not verification.verified:
                raise ManifestVerificationError(
                    verification.reason or "artifact digest verification failed"
                )
    except (ManifestVerificationError, KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc
    try:
        return StepCheckpointEnvelope.from_canonical_bytes(raw_bytes)
    except CheckpointDecodeError as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc


def _load_success_result(
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> HistoryCompareResultInputResponse:
    with unit_of_work_factory(read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    if assemble_step.checkpoint_ref is None:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        )
    envelope = _load_checkpoint_envelope_from_store(artifact_store, assemble_step.checkpoint_ref)
    assemble_state = envelope.job_state.get("assemble_state")
    if type(assemble_state) is not dict:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        )
    pairs_raw = assemble_state.get("pairs")
    if type(pairs_raw) is not list:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        )
    try:
        pairs: list[HistoryComparePairResultResponse] = []
        for item in pairs_raw:
            if type(item) is not dict:
                raise TypeError("pair entry must be an object")
            before_ref_raw = item["before_ref"]
            current_ref_raw = item["current_ref"]
            if type(before_ref_raw) is not dict or type(current_ref_raw) is not dict:
                raise TypeError("pair refs must be objects")
            pairs.append(
                HistoryComparePairResultResponse(
                    pair_id=str(item["pair_id"]),
                    before_ref=HistoryNodeRefResponse(
                        ref_kind=cast(HistoryNodeRefKindLiteral, str(before_ref_raw["ref_kind"])),
                        ref_id=str(before_ref_raw["ref_id"]),
                    ),
                    before_commit=str(item["before_commit"]),
                    current_ref=HistoryNodeRefResponse(
                        ref_kind=cast(HistoryNodeRefKindLiteral, str(current_ref_raw["ref_kind"])),
                        ref_id=str(current_ref_raw["ref_id"]),
                    ),
                    current_commit=str(item["current_commit"]),
                    comparison_digest=str(item["comparison_digest"]),
                    risk_digest=str(item["risk_digest"]),
                    surface_digest=str(item["surface_digest"]),
                    record_count=int(item["record_count"]),
                )
            )
        bundle_digest = str(assemble_state["bundle_digest"])
        return HistoryCompareResultInputResponse(
            input={
                "nodes": [
                    {
                        "ref_kind": node.ref_kind.value,
                        "ref_id": node.ref_id,
                        "commit_id": node.commit_id,
                    }
                    for node in acceptance.nodes
                ],
                "commits": [node.commit_id for node in acceptance.nodes],
            },
            pairs=pairs,
            bundle_digest=bundle_digest,
            completed_at=operation.completed_at,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc


def _bundle_artifact_id(
    *,
    operation: OperationRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> str:
    with unit_of_work_factory(read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    if assemble_step.checkpoint_ref is None:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="bundle is not available",
            status_code=404,
        )
    envelope = _load_checkpoint_envelope_from_store(artifact_store, assemble_step.checkpoint_ref)
    bundle_artifact_id = envelope.job_state.get("bundle_artifact_id")
    if type(bundle_artifact_id) is not str or not bundle_artifact_id:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="bundle is not available",
            status_code=404,
        )
    return bundle_artifact_id


def build_history_compare_accept_command(
    *,
    context: object,
    idempotency_key: str,
    node_refs: tuple[HistoryNodeRef, ...],
) -> HistoryCompareAcceptCommand:
    from gateway_backend.domain.workspace.models import IdentityContext

    if type(context) is not IdentityContext:
        raise TypeError("context must be IdentityContext")
    return HistoryCompareAcceptCommand(
        context=context,
        idempotency_key=idempotency_key,
        node_refs=node_refs,
    )
