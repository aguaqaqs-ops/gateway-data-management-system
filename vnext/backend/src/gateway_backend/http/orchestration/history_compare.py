"""History compare accept and result orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from pydantic import ValidationError
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import StepCheckpointEnvelope
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.application.history.compare import validate_history_compare_binding
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    history_compare_step_id,
)
from gateway_backend.application.history.compare_registry import assert_compare_registry_ready
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HISTORY_COMPARE_VIEW_KIND,
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryCompareValidationResult,
    HistoryNodeRef,
)
from gateway_backend.application.history.errors import (
    HistoryCompareBindingConflict,
    HistoryCompareIdempotencyConflict,
    HistoryCompareNodeNotFound,
    HistoryIntegrityUnresolved,
    HistoryRequestValidation,
)
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.submission.ports import (
    WorkspaceControlTransaction,
    WorkspaceControlUnitOfWorkFactory,
)
from gateway_backend.domain.workspace.errors import PermissionDenied
from gateway_backend.http.dependencies import AdmissionGatePort, BundleReaderPort
from gateway_backend.http.errors import ApiError
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
from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)


@dataclass(frozen=True, slots=True)
class HistoryCompareAcceptanceResult:
    response: HistoryCompareAcceptResponse
    replay: bool


def build_history_compare_job_payload(
    *,
    validation: HistoryCompareValidationResult,
    acceptance_id: str,
    idempotency_key: str,
) -> bytes:
    payload = {
        "gateway_device_external_key": validation.gateway_device_external_key,
        "business_project_id": validation.business_project_id,
        "repository_id": validation.repository_id,
        "acceptance_id": acceptance_id,
        "idempotency_key": idempotency_key,
        "request_fingerprint": validation.request_fingerprint,
        "table_ruleset_version": validation.table_ruleset_version,
        "comparison_contract_version": HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        "view_kind": HISTORY_COMPARE_VIEW_KIND,
        "pair_count": max(len(validation.nodes) - 1, 1),
        "nodes": [
            {
                "ref_kind": node.ref_kind.value,
                "ref_id": node.ref_id,
                "commit_id": node.commit_id,
            }
            for node in validation.nodes
        ],
    }
    return canonicalize_json_value(payload)


def accept_compare_operation(
    *,
    command: HistoryCompareAcceptCommand,
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
    job_registry: JobDefinitionRegistry,
    admission_gate: AdmissionGatePort,
    table_ruleset_version: str,
    now: datetime,
) -> HistoryCompareAcceptanceResult:
    try:
        assert_compare_registry_ready(job_registry)
    except ValueError as exc:
        raise ApiError(
            code="SERVICE_NOT_READY",
            message="history compare job definition is not registered",
            status_code=503,
        ) from exc
    if not admission_gate.try_acquire():
        if not admission_gate.allows_new_work():
            raise ApiError(
                code="ADMISSION_CONFLICT",
                message="gateway admission is closed",
                status_code=409,
            )
        raise ApiError(
            code="ADMISSION_LIMIT_REACHED",
            message="gateway admission limit reached",
            status_code=429,
        )
    replay_result: HistoryCompareAcceptanceResult | None = None
    operation_id: str | None = None
    try:
        with unit_of_work_factory() as unit_of_work:
            validation = _validate_accept(
                command,
                unit_of_work,
                table_ruleset_version=table_ruleset_version,
            )
            if validation.replay and validation.prior_acceptance is not None:
                operation = unit_of_work.operations.get_operation(validation.prior_acceptance.operation_id)
                replay_result = HistoryCompareAcceptanceResult(
                    response=HistoryCompareAcceptResponse(
                        operation_id=operation.operation_id,
                        status=_public_operation_status(operation.status),
                        replayed=True,
                    ),
                    replay=True,
                )
            else:
                operation_id = validation.operation_id
                acceptance_id = validation.acceptance_id
                if operation_id is None or acceptance_id is None:
                    raise ApiError(
                        code="SERVICE_NOT_READY",
                        message="history compare acceptance is incomplete",
                        status_code=503,
                    )
                job_payload = build_history_compare_job_payload(
                    validation=validation,
                    acceptance_id=acceptance_id,
                    idempotency_key=command.idempotency_key,
                )
                operation = OperationRecord(
                    contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
                    operation_id=operation_id,
                    job_kind=HISTORY_COMPARE_JOB_KIND,
                    job_contract_version=HISTORY_COMPARE_JOB_CONTRACT_VERSION,
                    job_payload=job_payload,
                    job_payload_ref=None,
                    business_refs=(BusinessReference(kind="history_compare", value=acceptance_id),),
                    artifact_refs=(),
                    repository_operation_id=None,
                    checkpoint_ref=None,
                    ready_closure_ref=None,
                    status=OperationStatus.QUEUED,
                    diagnostic=None,
                    cancel_requested=False,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,
                    optimistic_version=0,
                )
                step = StepRecord(
                    contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
                    step_id=history_compare_step_id(operation_id, HISTORY_COMPARE_STEP_MATERIALIZE),
                    operation_id=operation_id,
                    step_name=HISTORY_COMPARE_STEP_MATERIALIZE,
                    status=StepStatus.PENDING,
                    attempt_count=0,
                    diagnostic=None,
                    cancel_requested=False,
                    retry_not_before=None,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    checkpoint_ref=None,
                    prior_output_refs=(),
                    created_at=now,
                    updated_at=now,
                    started_at=None,
                    completed_at=None,
                    optimistic_version=0,
                )
                unit_of_work.history_compare.save_acceptance(
                    HistoryCompareAcceptanceRecord(
                        acceptance_id=acceptance_id,
                        gateway_device_external_key=validation.gateway_device_external_key,
                        business_project_id=validation.business_project_id,
                        repository_id=validation.repository_id,
                        idempotency_key=command.idempotency_key,
                        request_fingerprint=validation.request_fingerprint,
                        table_ruleset_version=validation.table_ruleset_version,
                        nodes=validation.nodes,
                        operation_id=operation_id,
                        created_at=now,
                    )
                )
                unit_of_work.operations.insert_operation_with_initial_step(operation, step)
    finally:
        admission_gate.release()
    if replay_result is not None:
        return replay_result
    if operation_id is None:
        raise ApiError(
            code="SERVICE_NOT_READY",
            message="history compare acceptance is incomplete",
            status_code=503,
        )
    return HistoryCompareAcceptanceResult(
        response=HistoryCompareAcceptResponse(
            operation_id=operation_id,
            status="QUEUED",
            replayed=False,
        ),
        replay=False,
    )


def get_compare_result(
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
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
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
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


def _validate_accept(
    command: HistoryCompareAcceptCommand,
    unit_of_work: WorkspaceControlTransaction,
    *,
    table_ruleset_version: str,
) -> HistoryCompareValidationResult:
    try:
        return validate_history_compare_binding(
            command=command,
            unit_of_work=unit_of_work,
            table_ruleset_version=table_ruleset_version,
        )
    except HistoryRequestValidation as exc:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message=str(exc),
            status_code=422,
        ) from exc
    except PermissionDenied:
        raise ApiError(
            code="SCOPE_FORBIDDEN",
            message="scope forbidden",
            status_code=403,
        ) from None
    except HistoryCompareNodeNotFound:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        ) from None
    except HistoryCompareIdempotencyConflict as exc:
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message="idempotency conflict",
            status_code=409,
            details={"idempotency_key": exc.idempotency_key},
        ) from exc
    except HistoryCompareBindingConflict as exc:
        raise ApiError(
            code="IDEMPOTENCY_CONFLICT",
            message=str(exc),
            status_code=409,
        ) from exc
    except HistoryIntegrityUnresolved:
        raise ApiError(
            code="HISTORY_INTEGRITY_UNRESOLVED",
            message="history integrity incident is unresolved",
            status_code=409,
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
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
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
    unit_of_work_factory: WorkspaceControlUnitOfWorkFactory,
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
