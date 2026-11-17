"""History compare result reading, verification, and bundle preflight use cases."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from typing import Annotated, Literal, cast

from gateway_shared_kernel.jcs import canonicalize_json_value
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, Strict, ValidationError

from gateway_backend.application.bundle_download import decode_bundle_manifest
from gateway_backend.application.checkpoints import ReadyClosureDocument, StepCheckpointEnvelope
from gateway_backend.application.comparison_audit import (
    ComparisonStructureAudit,
    StructureAuditBinding,
)
from gateway_backend.application.history.compare_jobs.checkpoint import (
    history_compare_assemble_state_from_checkpoint,
    history_compare_ready_ref,
    ready_closure_refs_from_assemble,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HistoryCompareJobError,
    decode_history_compare_payload,
    history_compare_step_id,
)
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_VIEW_KIND,
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryCompareAcceptanceRecord,
    HistoryComparePairResult,
    HistoryCompareResultData,
    HistoryCompareResultRead,
    HistoryNodeRef,
    HistoryNodeRefKind,
)
from gateway_backend.application.history.errors import (
    HistoryArtifactUnavailable,
    HistoryBundleIntegrityFailure,
    HistoryComparePreflightFailure,
    HistoryCompareResultExpired,
    HistoryIntegrityFailure,
)
from gateway_backend.application.history.ports import (
    BundleReaderPort,
    HistoryControlUnitOfWorkFactory,
)
from gateway_backend.application.operation_reads import (
    OperationReaderPort,
    authorize_history_compare_operation_read,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.bundle_download import BundleIntegrityError, PreparedBundleDownload
from gateway_backend.artifacts.location import parse_artifact_id
from gateway_backend.artifacts.store import ArtifactUnavailableError, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.operations.contracts import (
    IJSON_MAX_SAFE_INTEGER,
    MAX_OPAQUE_ID_BYTES,
    BusinessReference,
    OperationRecord,
    OperationStatus,
)
from gateway_backend.operations.store import RecordNotFound

_NonNegativeIJsonInt = Annotated[int, Strict(), Field(ge=0, le=IJSON_MAX_SAFE_INTEGER)]


def _coerce_opaque_id(value: object) -> str:
    if type(value) is not str:
        raise ValueError("id must be a string")
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= MAX_OPAQUE_ID_BYTES:
        raise ValueError("id exceeds bounded opaque identifier size")
    return value


def _coerce_sha256_digest(value: object) -> str:
    if type(value) is not str:
        raise ValueError("digest must be a string")
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("digest must be sha256:<64 hex chars>")
    hex_part = value[7:]
    if len(hex_part) != 64 or any(char not in "0123456789abcdef" for char in hex_part):
        raise ValueError("digest must be sha256:<64 hex chars>")
    return value


_BoundedOpaqueId = Annotated[str, BeforeValidator(_coerce_opaque_id)]
_Sha256Digest = Annotated[str, BeforeValidator(_coerce_sha256_digest)]
_CommitIdString = Annotated[str, Field(min_length=1, max_length=1024)]


class _SerializedArtifactRef(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str


class _HistoryAssembleNodeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref_kind: Literal["baseline_node", "submission"]
    ref_id: _BoundedOpaqueId


class _HistoryAssemblePair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pair_id: str
    before_ref: _HistoryAssembleNodeRef
    before_commit: _CommitIdString
    current_ref: _HistoryAssembleNodeRef
    current_commit: _CommitIdString
    comparison_digest: _Sha256Digest
    risk_digest: _Sha256Digest
    surface_digest: _Sha256Digest
    record_count: _NonNegativeIJsonInt


class _HistoryAssembleState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    pair_ids: list[str]
    structure_audit_bindings: list[StructureAuditBinding]
    pairs: list[_HistoryAssemblePair]
    bundle_digest: _Sha256Digest
    required_refs: list[_SerializedArtifactRef]


@contextmanager
def preflight_history_result(
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
    bundle_reader: BundleReaderPort,
) -> Iterator[frozenset[str]]:
    """Keep the root borrowed from metadata reads through the caller's writer check."""
    read_session = getattr(artifact_store, "read_session", None)
    try:
        with read_session() if read_session is not None else nullcontext():
            _load_success_result(
                operation=operation,
                acceptance=acceptance,
                unit_of_work_factory=unit_of_work_factory,
                artifact_store=artifact_store,
            )
            with unit_of_work_factory(read_only=True) as uow:
                step = uow.operations.get_step(
                    history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
                )
            if step.checkpoint_ref is None:
                raise HistoryArtifactUnavailable("history checkpoint unavailable")
            envelope = _load_checkpoint_envelope_from_store(artifact_store, step.checkpoint_ref)
            state_ref, _ = history_compare_assemble_state_from_checkpoint(
                envelope.job_state, cast(BoundedArtifactStorePort, artifact_store)
            )
            ready_ref = history_compare_ready_ref(envelope.job_state)
            closure = ReadyClosureDocument.from_canonical_bytes(
                _read_metadata_from_store(artifact_store, ready_ref)
            )
            prepared = read_compare_bundle(
                operation=operation,
                bundle_reader=bundle_reader,
                unit_of_work_factory=unit_of_work_factory,
                artifact_store=artifact_store,
            )
            try:
                yield frozenset(
                    ref.artifact_id
                    for ref in (step.checkpoint_ref, state_ref, ready_ref, *closure.artifact_refs())
                )
            finally:
                prepared.close()
    except (
        HistoryArtifactUnavailable,
        HistoryBundleIntegrityFailure,
        HistoryIntegrityFailure,
        ScopeForbidden,
    ) as exc:
        raise HistoryComparePreflightFailure(exc) from exc
    except (CheckpointDecodeError, ManifestVerificationError) as exc:
        raise HistoryComparePreflightFailure(
            HistoryArtifactUnavailable("history result unavailable")
        ) from exc


def assert_history_result_not_expired(
    *, operation: OperationRecord, acceptance: HistoryCompareAcceptanceRecord, now: datetime
) -> None:
    if operation.status is OperationStatus.SUCCEEDED:
        if operation.completed_at is None:
            raise HistoryIntegrityFailure("history result has no completion time")
        if now >= operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds):
            raise HistoryCompareResultExpired("history result has expired")


def read_history_compare_result(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
    now: datetime,
) -> HistoryCompareResultRead:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    try:
        operation = operation_reader.get_operation(operation_id)
    except RecordNotFound:
        raise ScopeForbidden from None
    acceptance = authorize_history_compare_operation_read(
        context=context,
        operation=operation,
        unit_of_work_factory=unit_of_work_factory,
    )
    assert_history_result_not_expired(operation=operation, acceptance=acceptance, now=now)
    return get_compare_result(
        operation=operation,
        acceptance=acceptance,
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=artifact_store,
    )


def read_history_compare_bundle(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    bundle_reader: BundleReaderPort,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
    now: datetime,
) -> PreparedBundleDownload:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    try:
        operation = operation_reader.get_operation(operation_id)
    except RecordNotFound:
        raise ScopeForbidden from None
    acceptance = authorize_history_compare_operation_read(
        context=context,
        operation=operation,
        unit_of_work_factory=unit_of_work_factory,
    )
    assert_history_result_not_expired(operation=operation, acceptance=acceptance, now=now)
    return read_compare_bundle(
        operation=operation,
        bundle_reader=bundle_reader,
        unit_of_work_factory=unit_of_work_factory,
        artifact_store=artifact_store,
    )


def get_compare_result(
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> HistoryCompareResultRead:
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
    return HistoryCompareResultRead(
        operation_id=operation.operation_id,
        status=operation.status,
        diagnostic=operation.diagnostic,
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
        raise ScopeForbidden
    try:
        read_session = getattr(artifact_store, "read_session", None)
        # The bundle's own prepared session remains held after this outer borrow
        # closes; the outer borrow also protects checkpoint/state reads.
        with read_session() if read_session is not None else nullcontext():
            with unit_of_work_factory(read_only=True) as unit_of_work:
                acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(
                    operation.operation_id
                )
            if acceptance is None:
                raise HistoryIntegrityFailure("history acceptance is missing")
            _load_success_result(
                operation=operation,
                acceptance=acceptance,
                unit_of_work_factory=unit_of_work_factory,
                artifact_store=artifact_store,
            )
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
        raise HistoryArtifactUnavailable("bundle is not available") from None
    except BundleIntegrityError:
        raise HistoryBundleIntegrityFailure("bundle failed integrity verification") from None


def _read_metadata_from_store(
    artifact_store: object, ref: ArtifactRef, *, bundle_manifest: bool = False
) -> bytes:
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
                raise ManifestVerificationError(
                    "artifact store does not support digest verification"
                )
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
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    except ManifestVerificationError as exc:
        if bundle_manifest:
            raise HistoryBundleIntegrityFailure("bundle failed integrity verification") from exc
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    return cast(bytes, raw_bytes)


def _load_checkpoint_envelope_from_store(
    artifact_store: object,
    ref: ArtifactRef,
) -> StepCheckpointEnvelope:
    raw_bytes = _read_metadata_from_store(artifact_store, ref)
    try:
        return StepCheckpointEnvelope.from_canonical_bytes(raw_bytes)
    except CheckpointDecodeError as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc


# Legacy complexity 34 > 30 (result verification pipeline); exempted in J5 baseline.
def _load_success_result(  # noqa: C901
    *,
    operation: OperationRecord,
    acceptance: HistoryCompareAcceptanceRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    artifact_store: object,
) -> HistoryCompareResultData:
    with unit_of_work_factory(read_only=True) as unit_of_work:
        assemble_step = unit_of_work.operations.get_step(
            history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE)
        )
    if assemble_step.checkpoint_ref is None:
        raise HistoryArtifactUnavailable("compare result is not available")
    envelope = _load_checkpoint_envelope_from_store(artifact_store, assemble_step.checkpoint_ref)
    try:
        if operation.job_payload is None or operation.job_payload_ref is not None:
            raise ValueError("history payload must be inline")
        payload_object = json.loads(operation.job_payload)
        if not isinstance(payload_object, dict):
            raise ValueError("history payload must be an object")
        payload = decode_history_compare_payload(payload_object)
        if (
            payload.acceptance_id != acceptance.acceptance_id
            or payload.gateway_device_external_key != acceptance.gateway_device_external_key
            or payload.business_project_id != acceptance.business_project_id
            or payload.repository_id != acceptance.repository_id
            or payload.idempotency_key != acceptance.idempotency_key
            or payload.request_fingerprint != acceptance.request_fingerprint
            or payload.comparison_ruleset_digest != acceptance.comparison_ruleset_digest
            or payload.nodes != acceptance.nodes
            or payload.pair_count != len(acceptance.nodes) - 1
            or payload.comparison_contract_version != HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION
            or payload.view_kind != HISTORY_COMPARE_VIEW_KIND
            or operation.job_contract_version != HISTORY_COMPARE_JOB_CONTRACT_VERSION
            or operation.business_refs
            != (BusinessReference(kind="history_compare", value=acceptance.acceptance_id),)
        ):
            raise ValueError("history operation and acceptance disagree")
    except (ValueError, TypeError, HistoryCompareJobError) as exc:
        raise HistoryIntegrityFailure("history operation binding disagrees") from exc
    if (
        acceptance.operation_id != operation.operation_id
        or envelope.operation_id != operation.operation_id
        or envelope.step_name != HISTORY_COMPARE_STEP_ASSEMBLE
        or envelope.job_kind != operation.job_kind
        or envelope.job_contract_version != operation.job_contract_version
    ):
        raise HistoryIntegrityFailure("history checkpoint binding disagrees")
    try:
        assemble_state_ref, assemble_state = history_compare_assemble_state_from_checkpoint(
            envelope.job_state,
            cast(BoundedArtifactStorePort, artifact_store),
        )
    except CheckpointDecodeError as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    try:
        state = _HistoryAssembleState.model_validate_json(
            canonicalize_json_value(assemble_state), strict=True
        )
    except (ValueError, ValidationError) as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    try:
        ready_ref = history_compare_ready_ref(envelope.job_state)
        if operation.ready_closure_ref != ready_ref:
            raise HistoryIntegrityFailure("history READY binding disagrees")
        closure = ReadyClosureDocument.from_canonical_bytes(
            _read_metadata_from_store(artifact_store, ready_ref)
        )
        if closure.job_contract_version != operation.job_contract_version:
            raise HistoryIntegrityFailure("history READY version disagrees")
        bundle_id = envelope.job_state.get("bundle_artifact_id")
        bundle_ref = next(
            (ref for ref in closure.artifact_refs() if ref.artifact_id == bundle_id), None
        )
        if bundle_ref is None:
            raise HistoryBundleIntegrityFailure("bundle is outside history READY")
        if set(ready_closure_refs_from_assemble(assemble_state, bundle_ref)) != set(
            closure.artifact_refs()
        ):
            raise HistoryIntegrityFailure("history READY outputs disagree")
    except (CheckpointDecodeError, ManifestVerificationError) as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc
    except (HistoryCompareJobError, ValueError, TypeError, KeyError) as exc:
        raise HistoryIntegrityFailure("history READY outputs disagree") from exc
    try:
        pairs = state.pairs
        expected_ids = (
            ("left_to_right",)
            if len(acceptance.nodes) == 2
            else ("left_to_middle", "middle_to_right")
        )
        if len(pairs) != len(expected_ids) or state.pair_ids != list(expected_ids):
            raise HistoryIntegrityFailure("history pair count disagrees")
        for index, pair in enumerate(pairs):
            before, current = acceptance.nodes[index : index + 2]
            if (
                pair.pair_id != expected_ids[index]
                or pair.before_ref.ref_kind != before.ref_kind.value
                or pair.before_ref.ref_id != before.ref_id
                or pair.before_commit != before.commit_id
                or pair.current_ref.ref_kind != current.ref_kind.value
                or pair.current_ref.ref_id != current.ref_id
                or pair.current_commit != current.commit_id
            ):
                raise HistoryIntegrityFailure("history pair binding disagrees")
        try:
            bindings = state.structure_audit_bindings
            if len(bindings) != len(pairs) or {item.pair_id for item in bindings} != set(
                expected_ids
            ):
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
                    audit = ComparisonStructureAudit.model_validate_json(
                        _read_metadata_from_store(artifact_store, ref), strict=True
                    )
                    if (
                        audit.pair_id != binding.pair_id
                        or audit.comparison_digest != binding.comparison_digest
                        or not audit.tables
                    ):
                        raise ValueError("structure audit document binding disagrees")
        except (ValueError, TypeError, ValidationError) as exc:
            raise HistoryIntegrityFailure("history structure audit disagrees") from exc
        try:
            bundle_metadata = decode_bundle_manifest(
                bundle_ref,
                lambda: _read_metadata_from_store(artifact_store, bundle_ref, bundle_manifest=True),
            )
        except BundleIntegrityError as exc:
            raise HistoryBundleIntegrityFailure("bundle failed integrity verification") from exc
        expected_input_roles = tuple(
            (index, node.ref_id) for index, node in enumerate(acceptance.nodes)
        )
        expected_pair_indices = tuple(
            (pair_id, index, index + 1) for index, pair_id in enumerate(expected_ids)
        )
        if (
            bundle_metadata.input_roles != expected_input_roles
            or bundle_metadata.pair_input_indices != expected_pair_indices
        ):
            raise HistoryIntegrityFailure("history bundle input binding disagrees")
        ready_by_id = {ref.artifact_id: ref for ref in closure.artifact_refs()}
        bundle_refs = (
            bundle_metadata.closure_ref,
            *(entry.artifact_ref for entry in bundle_metadata.entries),
        )
        if any(ready_by_id.get(ref.artifact_id) != ref for ref in bundle_refs):
            raise HistoryIntegrityFailure("history READY omits bundle members")
        expected_pair_digests = tuple(
            (pair.pair_id, pair.surface_digest, pair.comparison_digest) for pair in pairs
        )
        expected_risk_digests = tuple((pair.pair_id, pair.risk_digest) for pair in pairs)
        if (
            bundle_metadata.pair_digests != expected_pair_digests
            or bundle_metadata.pair_risk_digests != expected_risk_digests
        ):
            raise HistoryIntegrityFailure("history pair and bundle digests disagree")
        bundle_digest = state.bundle_digest
        result = HistoryCompareResultData(
            nodes=acceptance.nodes,
            pairs=tuple(
                HistoryComparePairResult(
                    pair_id=pair.pair_id,
                    before_ref=HistoryNodeRef(
                        ref_kind=HistoryNodeRefKind(pair.before_ref.ref_kind),
                        ref_id=pair.before_ref.ref_id,
                    ),
                    before_commit=pair.before_commit,
                    current_ref=HistoryNodeRef(
                        ref_kind=HistoryNodeRefKind(pair.current_ref.ref_kind),
                        ref_id=pair.current_ref.ref_id,
                    ),
                    current_commit=pair.current_commit,
                    comparison_digest=pair.comparison_digest,
                    risk_digest=pair.risk_digest,
                    surface_digest=pair.surface_digest,
                    record_count=pair.record_count,
                )
                for pair in pairs
            ),
            bundle_digest=bundle_digest,
            completed_at=operation.completed_at,
        )
        if bundle_metadata.bundle_digest != bundle_digest:
            raise HistoryBundleIntegrityFailure("bundle digest disagrees")
        if bundle_digest != envelope.job_state.get("bundle_digest"):
            raise HistoryIntegrityFailure("history bundle binding disagrees")
        if operation.completed_at is None:
            raise HistoryIntegrityFailure("history completion time is missing")
        expected_refs = frozenset(
            ref.artifact_id
            for ref in (
                assemble_step.checkpoint_ref,
                assemble_state_ref,
                ready_ref,
                *closure.artifact_refs(),
            )
        )
        with unit_of_work_factory(read_only=True) as uow:
            if not uow.history_compare.result_protection_matches(
                operation.operation_id,
                expected_refs,
                operation.completed_at + timedelta(seconds=acceptance.result_retention_seconds),
            ):
                raise HistoryIntegrityFailure("history result protection disagrees")
        return result
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HistoryArtifactUnavailable("compare result is not available") from exc


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
        raise HistoryArtifactUnavailable("bundle is not available")
    envelope = _load_checkpoint_envelope_from_store(artifact_store, assemble_step.checkpoint_ref)
    bundle_artifact_id = envelope.job_state.get("bundle_artifact_id")
    if type(bundle_artifact_id) is not str or not bundle_artifact_id:
        raise HistoryArtifactUnavailable("bundle is not available")
    try:
        parse_artifact_id(bundle_artifact_id)
    except ValueError as exc:
        raise BundleIntegrityError("history checkpoint has an invalid bundle ID") from exc
    expected_digest = envelope.job_state.get("bundle_digest")
    if type(expected_digest) is not str or not expected_digest:
        raise BundleIntegrityError("history checkpoint has no expected bundle digest")
    return bundle_artifact_id, expected_digest
