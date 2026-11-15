"""History compare DTO mapping and result orchestration."""

from __future__ import annotations

from gateway_backend.artifacts.location import parse_artifact_id

from gateway_backend.artifacts.bundle_download import PreparedBundleDownload
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.bundle_download import BundleIntegrityError

import json

from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import ReadyClosureDocument, StepCheckpointEnvelope
from gateway_backend.application.comparison_audit import ComparisonStructureAudit, StructureAuditBinding
from gateway_backend.application.history.compare import (
    HistoryCompareAcceptanceResult as ApplicationHistoryCompareAcceptanceResult,
    accept_history_compare,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HistoryCompareJobError,
    decode_history_compare_payload,
    _history_compare_ready_ref,
    _ready_closure_refs_from_assemble,
    history_compare_assemble_state_from_checkpoint,
    history_compare_step_id,
)
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_VIEW_KIND,
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryNodeRef,
)
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.application.history.errors import HistoryComparePreflightFailure
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.capabilities.bundle_assembly import read_bundle_transport_metadata
from gateway_backend.capabilities.bundle_assembly.contracts import BUNDLE_MANIFEST_MEDIA_TYPE, MAX_BUNDLE_MANIFEST_JSON_BYTES
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.http.dependencies import AdmissionGatePort, BundleReaderPort, acquire_new_work
from gateway_backend.http.errors import ApiError, map_domain_exception
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.schemas.history import (
    HistoryCompareAcceptResponse,
    HistoryCompareDiagnosticResponse,
    HistoryComparePairResultResponse,
    HistoryCompareResultInputResponse,
    HistoryCompareResultResponse,
)
from gateway_backend.http.schemas.operation import OperationDiagnosticDetailResponse
from gateway_backend.operations.contracts import BusinessReference, OperationRecord, OperationStatus


class _SerializedArtifactRef(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str


class _HistoryAssembleState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    pair_ids: list[str]
    structure_audit_bindings: list[StructureAuditBinding]
    pairs: list[HistoryComparePairResultResponse]
    bundle_digest: str
    required_refs: list[_SerializedArtifactRef]


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
    result_retention_seconds: int = 86_400,
    history_scope_active_limit: int = 2,
    operation_queue_limit: int = 32,
    artifact_store: object | None = None,
    bundle_reader: BundleReaderPort | None = None,
    resolve_current_identity: Callable[[], IdentityContext] | None = None,
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
                result_retention_seconds=result_retention_seconds,
                history_scope_active_limit=history_scope_active_limit,
                operation_queue_limit=operation_queue_limit,
                resolve_current_identity=resolve_current_identity,
                preflight=(None if artifact_store is None or bundle_reader is None else
                    lambda operation, acceptance: preflight_history_result(
                        operation=operation, acceptance=acceptance,
                        unit_of_work_factory=unit_of_work_factory,
                        artifact_store=artifact_store, bundle_reader=bundle_reader,
                    )),
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


@contextmanager
def preflight_history_result(
    *, operation: OperationRecord, acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory, artifact_store: object,
    bundle_reader: BundleReaderPort,
) -> Iterator[frozenset[str]]:
    """Keep the root borrowed from metadata reads through the caller's writer check."""
    read_session = getattr(artifact_store, "read_session", None)
    try:
        with read_session() if read_session is not None else nullcontext():
            _load_success_result(operation=operation, acceptance=acceptance,
                                 unit_of_work_factory=unit_of_work_factory, artifact_store=artifact_store)
            with unit_of_work_factory(read_only=True) as uow:
                step = uow.operations.get_step(history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE))
            if step.checkpoint_ref is None:
                raise ApiError(code="ARTIFACT_UNAVAILABLE", message="history checkpoint unavailable", status_code=404)
            envelope = _load_checkpoint_envelope_from_store(artifact_store, step.checkpoint_ref)
            state_ref, _ = history_compare_assemble_state_from_checkpoint(
                envelope.job_state, cast(BoundedArtifactStorePort, artifact_store))
            ready_ref = _history_compare_ready_ref(envelope.job_state)
            closure = ReadyClosureDocument.from_canonical_bytes(_read_metadata_from_store(artifact_store, ready_ref))
            prepared = read_compare_bundle(operation=operation, bundle_reader=bundle_reader,
                                           unit_of_work_factory=unit_of_work_factory, artifact_store=artifact_store)
            try:
                yield frozenset(ref.artifact_id for ref in
                                (step.checkpoint_ref, state_ref, ready_ref, *closure.artifact_refs()))
            finally:
                prepared.close()
    except ApiError as exc:
        raise HistoryComparePreflightFailure(exc) from exc
    except (CheckpointDecodeError, ManifestVerificationError) as exc:
        raise HistoryComparePreflightFailure(ApiError(code="ARTIFACT_UNAVAILABLE", message="history result unavailable", status_code=404)) from exc


def assert_history_result_not_expired(
    *, operation: OperationRecord, acceptance: HistoryCompareAcceptanceRecord, now: datetime
) -> None:
    if operation.status is OperationStatus.SUCCEEDED:
        if operation.completed_at is None:
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history result has no completion time", status_code=503)
        if now >= operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds):
            raise ApiError(code="HISTORY_COMPARE_RESULT_EXPIRED", message="history result has expired", status_code=410)


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
    diagnostic = None
    if operation.diagnostic is not None:
        diagnostic = HistoryCompareDiagnosticResponse(
            code=operation.diagnostic.code,
            message=operation.diagnostic.message,
            details=(
                None
                if operation.diagnostic.details is None
                else [
                    OperationDiagnosticDetailResponse(
                        code=item.code,
                        side=item.side.value,
                        table_name=item.table_name,
                        column_name=item.column_name,
                    )
                    for item in operation.diagnostic.details
                ]
            ),
            omitted_count=operation.diagnostic.omitted_count,
        )
    result = None
    if operation.status is OperationStatus.SUCCEEDED:
        read_session = getattr(artifact_store, "read_session", None)
        with read_session() if read_session is not None else nullcontext():
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
        result=result,
    )


def read_compare_bundle(
    *,
    operation: OperationRecord,
    bundle_reader: BundleReaderPort,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> PreparedBundleDownload:
    if operation.status is not OperationStatus.SUCCEEDED:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    try:
        read_session = getattr(artifact_store, "read_session", None)
        # The bundle's own prepared session remains held after this outer borrow
        # closes; the outer borrow also protects checkpoint/state reads.
        with read_session() if read_session is not None else nullcontext():
            with unit_of_work_factory(read_only=True) as unit_of_work:
                acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(operation.operation_id)
            if acceptance is None:
                raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history acceptance is missing", status_code=503)
            _load_success_result(operation=operation, acceptance=acceptance,
                                 unit_of_work_factory=unit_of_work_factory, artifact_store=artifact_store)
            bundle_artifact_id, expected_digest = _bundle_binding(
                operation=operation,
                unit_of_work_factory=unit_of_work_factory,
                artifact_store=artifact_store,
            )
            prepared = bundle_reader.prepare_bundle(bundle_artifact_id)
            if prepared.bundle_digest != expected_digest:
                prepared.close()
                raise BundleIntegrityError("bundle digest disagrees with its history result")
            return prepared
    except ArtifactUnavailableError:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="bundle is not available",
            status_code=404,
        ) from None
    except BundleIntegrityError:
        raise ApiError(
            code="BUNDLE_INTEGRITY_FAILURE",
            message="bundle failed integrity verification",
            status_code=503,
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


def _read_metadata_from_store(artifact_store: object, ref: ArtifactRef, *, bundle_manifest: bool = False) -> bytes:
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
    except ArtifactUnavailableError as exc:
        raise ApiError(code="ARTIFACT_UNAVAILABLE", message="compare result is not available", status_code=404) from exc
    except ManifestVerificationError as exc:
        if bundle_manifest:
            raise ApiError(code="BUNDLE_INTEGRITY_FAILURE", message="bundle failed integrity verification", status_code=503) from exc
        raise ApiError(code="ARTIFACT_UNAVAILABLE", message="compare result is not available", status_code=404) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc
    return cast(bytes, raw_bytes)


def _load_checkpoint_envelope_from_store(
    artifact_store: object, ref: ArtifactRef,
) -> StepCheckpointEnvelope:
    raw_bytes = _read_metadata_from_store(artifact_store, ref)
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
    try:
        if operation.job_payload is None or operation.job_payload_ref is not None:
            raise ValueError("history payload must be inline")
        payload_object = json.loads(operation.job_payload)
        if not isinstance(payload_object, dict):
            raise ValueError("history payload must be an object")
        payload = decode_history_compare_payload(payload_object)
        if (payload.acceptance_id != acceptance.acceptance_id
                or payload.gateway_device_external_key != acceptance.gateway_device_external_key
                or payload.business_project_id != acceptance.business_project_id
                or payload.repository_id != acceptance.repository_id
                or payload.idempotency_key != acceptance.idempotency_key
                or payload.request_fingerprint != acceptance.request_fingerprint
                or payload.comparison_ruleset_digest != acceptance.comparison_ruleset_digest
                or payload.nodes != acceptance.nodes or payload.pair_count != len(acceptance.nodes) - 1
                or payload.comparison_contract_version != HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION
                or payload.view_kind != HISTORY_COMPARE_VIEW_KIND
                or operation.job_contract_version != HISTORY_COMPARE_JOB_CONTRACT_VERSION
                or operation.business_refs != (BusinessReference(kind="history_compare", value=acceptance.acceptance_id),)):
            raise ValueError("history operation and acceptance disagree")
    except (ValueError, TypeError, HistoryCompareJobError) as exc:
        raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history operation binding disagrees", status_code=503) from exc
    if (acceptance.operation_id != operation.operation_id
            or envelope.operation_id != operation.operation_id
            or envelope.step_name != HISTORY_COMPARE_STEP_ASSEMBLE
            or envelope.job_kind != operation.job_kind
            or envelope.job_contract_version != operation.job_contract_version):
        raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history checkpoint binding disagrees", status_code=503)
    try:
        assemble_state_ref, assemble_state = history_compare_assemble_state_from_checkpoint(
            envelope.job_state,
            cast(BoundedArtifactStorePort, artifact_store),
        )
    except CheckpointDecodeError as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc
    try:
        state = _HistoryAssembleState.model_validate_json(canonicalize_json_value(assemble_state), strict=True)
    except (ValueError, ValidationError) as exc:
        raise ApiError(code="ARTIFACT_UNAVAILABLE", message="compare result is not available", status_code=404) from exc
    try:
        ready_ref = _history_compare_ready_ref(envelope.job_state)
        if operation.ready_closure_ref != ready_ref:
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history READY binding disagrees", status_code=503)
        closure = ReadyClosureDocument.from_canonical_bytes(_read_metadata_from_store(artifact_store, ready_ref))
        if closure.job_contract_version != operation.job_contract_version:
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history READY version disagrees", status_code=503)
        bundle_id = envelope.job_state.get("bundle_artifact_id")
        bundle_ref = next((ref for ref in closure.artifact_refs() if ref.artifact_id == bundle_id), None)
        if bundle_ref is None:
            raise ApiError(code="BUNDLE_INTEGRITY_FAILURE", message="bundle is outside history READY", status_code=503)
        if set(_ready_closure_refs_from_assemble(assemble_state, bundle_ref)) != set(closure.artifact_refs()):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history READY outputs disagree", status_code=503)
    except (CheckpointDecodeError, ManifestVerificationError) as exc:
        raise ApiError(code="ARTIFACT_UNAVAILABLE", message="compare result is not available", status_code=404) from exc
    except (HistoryCompareJobError, ValueError, TypeError, KeyError) as exc:
        raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history READY outputs disagree", status_code=503) from exc
    try:
        pairs = state.pairs
        expected_ids = ("left_to_right",) if len(acceptance.nodes) == 2 else ("left_to_middle", "middle_to_right")
        if len(pairs) != len(expected_ids) or state.pair_ids != list(expected_ids):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history pair count disagrees", status_code=503)
        for index, pair in enumerate(pairs):
            before, current = acceptance.nodes[index:index + 2]
            if (pair.pair_id != expected_ids[index]
                    or pair.before_ref.ref_kind != before.ref_kind.value or pair.before_ref.ref_id != before.ref_id
                    or pair.before_commit != before.commit_id
                    or pair.current_ref.ref_kind != current.ref_kind.value or pair.current_ref.ref_id != current.ref_id
                    or pair.current_commit != current.commit_id):
                raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history pair binding disagrees", status_code=503)
        try:
            bindings = state.structure_audit_bindings
            if len(bindings) != len(pairs) or {item.pair_id for item in bindings} != set(expected_ids):
                raise ValueError("incomplete structure audit bindings")
            refs_by_id = {ref.artifact_id: ref for ref in closure.artifact_refs()}
            pairs_by_id = {pair.pair_id: pair for pair in pairs}
            for binding in bindings:
                if binding.comparison_digest != pairs_by_id[binding.pair_id].comparison_digest:
                    raise ValueError("structure audit comparison binding disagrees")
                if binding.audit_artifact_id is not None:
                    ref = refs_by_id.get(binding.audit_artifact_id)
                    if ref is None:
                        raise ValueError("structure audit is missing from READY")
                    audit = ComparisonStructureAudit.model_validate_json(_read_metadata_from_store(artifact_store, ref), strict=True)
                    if audit.pair_id != binding.pair_id or audit.comparison_digest != binding.comparison_digest or not audit.tables:
                        raise ValueError("structure audit document binding disagrees")
        except (ValueError, TypeError, ValidationError) as exc:
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history structure audit disagrees", status_code=503) from exc
        try:
            if bundle_ref.media_type != BUNDLE_MANIFEST_MEDIA_TYPE or bundle_ref.size_bytes > MAX_BUNDLE_MANIFEST_JSON_BYTES:
                raise BundleIntegrityError("invalid history bundle manifest")
            bundle_metadata = read_bundle_transport_metadata(_read_metadata_from_store(artifact_store, bundle_ref, bundle_manifest=True))
        except BundleIntegrityError as exc:
            raise ApiError(code="BUNDLE_INTEGRITY_FAILURE", message="bundle failed integrity verification", status_code=503) from exc
        expected_input_roles = tuple((index, node.ref_id) for index, node in enumerate(acceptance.nodes))
        expected_pair_indices = tuple((pair_id, index, index + 1) for index, pair_id in enumerate(expected_ids))
        if (bundle_metadata.input_roles != expected_input_roles
                or bundle_metadata.pair_input_indices != expected_pair_indices):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history bundle input binding disagrees", status_code=503)
        ready_by_id = {ref.artifact_id: ref for ref in closure.artifact_refs()}
        bundle_refs = (bundle_metadata.closure_ref, *(entry.artifact_ref for entry in bundle_metadata.entries))
        if any(ready_by_id.get(ref.artifact_id) != ref for ref in bundle_refs):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history READY omits bundle members", status_code=503)
        expected_pair_digests = tuple((pair.pair_id, pair.surface_digest, pair.comparison_digest) for pair in pairs)
        expected_risk_digests = tuple((pair.pair_id, pair.risk_digest) for pair in pairs)
        if (bundle_metadata.pair_digests != expected_pair_digests
                or bundle_metadata.pair_risk_digests != expected_risk_digests):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history pair and bundle digests disagree", status_code=503)
        bundle_digest = state.bundle_digest
        result = HistoryCompareResultInputResponse(
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
        if bundle_metadata.bundle_digest != bundle_digest:
            raise ApiError(code="BUNDLE_INTEGRITY_FAILURE", message="bundle digest disagrees", status_code=503)
        if bundle_digest != envelope.job_state.get("bundle_digest"):
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history bundle binding disagrees", status_code=503)
        if operation.completed_at is None:
            raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history completion time is missing", status_code=503)
        expected_refs = frozenset(ref.artifact_id for ref in
                                  (assemble_step.checkpoint_ref, assemble_state_ref, ready_ref, *closure.artifact_refs()))
        with unit_of_work_factory(read_only=True) as uow:
            if not uow.history_compare.result_protection_matches(
                operation.operation_id, expected_refs,
                operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds),
            ):
                raise ApiError(code="HISTORY_INTEGRITY_FAILURE", message="history result protection disagrees", status_code=503)
        return result
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise ApiError(
            code="ARTIFACT_UNAVAILABLE",
            message="compare result is not available",
            status_code=404,
        ) from exc


def _bundle_binding(
    *,
    operation: OperationRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> tuple[str, str]:
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
    try:
        parse_artifact_id(bundle_artifact_id)
    except ValueError as exc:
        raise BundleIntegrityError("history checkpoint has an invalid bundle ID") from exc
    expected_digest = envelope.job_state.get("bundle_digest")
    if type(expected_digest) is not str or not expected_digest:
        raise BundleIntegrityError("history checkpoint has no expected bundle digest")
    return bundle_artifact_id, expected_digest


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
