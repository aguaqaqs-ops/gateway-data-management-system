"""Preview JobDefinition, decoder, and fixed three-step handler topology."""

from __future__ import annotations

import dataclasses
import json
import uuid
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import ContextManager, Protocol, cast, runtime_checkable

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_ready_closure,
    make_checkpoint_step_builder,
    prepare_ready_closure,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_definitions import (
    JobDefinition,
    NormalPublicationCapability,
)
from gateway_backend.application.payloads import (
    CheckpointDecodeError,
    PayloadDecodeError,
    PayloadDecoder,
    load_job_payload_bytes,
)
from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.store import ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    assemble_bundle,
    collect_surface_refs,
)
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BaselineReconstructionResult,
    BaselineReconstructionStatus,
    BoundSnapshotInput,
    ComparisonPlan,
    DetailedFactsResult,
    FailedResult,
    PairRole,
    PairViewKind,
    bind_pair_input,
    compare_plan,
    plan_pair,
    publish_records_closure,
)
from gateway_backend.capabilities.comparison.contracts import (
    IdentityStatus,
    InputCompleteness as ComparisonInputCompleteness,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskOptions,
    V1_RISK_RULE_SPECS,
    RiskRulesetSnapshot,
    evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SourceKind,
    Snapshot,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTableSet,
    SUMMARY_CONTRACT_VERSION,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SqlSnapshotMaterializationRequest,
)
from gateway_backend.capabilities.snapshot_materialization.materialize import (
    materialize_sql_snapshot,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import (
    materialize_repository_ref,
)
from gateway_backend.capabilities.source_package_staging import (
    PackageKind,
    SourcePackageInput,
    StagingInvocationContext,
    StagingStatus,
    StagingTransport,
    resolve_sql_dump_source,
    stage_source_package,
)
from gateway_backend.capabilities.source_package_staging.contracts import NeverCancel
from gateway_backend.capabilities.surface_assembly import (
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    ParseResult,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_VERSION,
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    InputCompleteness,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    Workspace,
)
from gateway_backend.domain.workspace.ports import BaselineHeadReadPort, WorkspaceRepository
from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.store import OperationStore
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
)

PREVIEW_JOB_KIND = "backend-vnext/preview"
PREVIEW_JOB_CONTRACT_VERSION = "backend-vnext/preview/v1"
PREVIEW_STEP_MATERIALIZE = "materialize_inputs"
PREVIEW_STEP_ASSEMBLE = "assemble_preview"
PREVIEW_STEP_PUBLISH = "publish_preview"

PREVIEW_MATERIALIZE_DECODER = "backend-vnext/preview/materialize/decoder/v1"
PREVIEW_ASSEMBLE_DECODER = "backend-vnext/preview/assemble/decoder/v1"
PREVIEW_PUBLISH_DECODER = "backend-vnext/preview/publish/decoder/v1"
PREVIEW_MATERIALIZE_HANDLER = "backend-vnext/preview/materialize/handler/v1"
PREVIEW_ASSEMBLE_HANDLER = "backend-vnext/preview/assemble/handler/v1"
PREVIEW_PUBLISH_HANDLER = "backend-vnext/preview/publish/handler/v1"

PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION = "backend-vnext/preview/materialize-side/v1"
PREVIEW_ASSEMBLE_CHECKPOINT_CONTRACT_VERSION = "backend-vnext/preview/assemble-checkpoint/v1"
_JCS_MEDIA_TYPE = "application/jcs"

_SIDE_BASELINE = "BASELINE"
_SIDE_INITIAL = "INITIAL"
_SIDE_MODIFIED = "MODIFIED"

_PAIR_BASELINE_TO_INITIAL = "baseline_to_initial"
_PAIR_INITIAL_TO_MODIFIED = "initial_to_modified"

_JOB_STATE_SIDES = "sides"
_JOB_STATE_INPUT_COMPLETENESS = "input_completeness"
_JOB_STATE_BASELINE_COMMIT = "baseline_commit_id"
_JOB_STATE_ASSEMBLE = "assemble_state"
_JOB_STATE_READY_CLOSURE = "ready_closure_artifact_id"
_JOB_STATE_READY_CLOSURE_REF = "ready_closure_ref"
_JOB_STATE_BUNDLE_ARTIFACT = "bundle_artifact_id"
_JOB_STATE_BUNDLE_DIGEST = "bundle_digest"

_active_preview_transaction: ContextVar[PreviewControlTransaction | None] = ContextVar(
    "_active_preview_transaction",
    default=None,
)


class PreviewJobError(ValueError):
    """Bounded preview job failure surfaced to the operation runtime."""


@dataclass(frozen=True, slots=True)
class PreviewIdempotencyIdentity:
    workspace_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PreviewJobPayload:
    workspace_id: str
    upload_revision_id: str
    generation: int
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    input_completeness: InputCompleteness
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding]
    source_digests: Mapping[str, str]
    input_digest: str
    ruleset_version: str
    capability_contract_versions: Mapping[str, object]
    provider_versions: Mapping[str, str]
    ready_closure_contract_version: str
    idempotency_identity: PreviewIdempotencyIdentity
    options: Mapping[str, object]


@runtime_checkable
class PreviewControlTransaction(Protocol):
    @property
    def operations(self) -> OperationStore: ...

    @property
    def workspace(self) -> WorkspaceRepository: ...

    @property
    def transaction_now(self) -> datetime: ...

    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool: ...

    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int: ...


PreviewControlTransactionFactory = Callable[[], ContextManager[PreviewControlTransaction]]
RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]


@dataclass(frozen=True, slots=True)
class PreviewRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    baseline_head_read: BaselineHeadReadPort
    control_transaction_factory: PreviewControlTransactionFactory


@dataclass(frozen=True, slots=True)
class _PreviewIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: IdentityStatus
    assessment_digest: DigestRef
    comparable_columns: tuple[str, ...] = ()
    before_row_count: int = 0
    current_row_count: int = 0
    before_distinct_entry_count: int = 0
    current_distinct_entry_count: int = 0
    matched_entry_count: int = 0
    before_entry_set_digest: DigestRef | None = None
    current_entry_set_digest: DigestRef | None = None
    diagnostics: tuple[object, ...] = ()
    requires_continuation_confirmation: bool = False
    requires_submit_confirmation: bool = False


def preview_job_definitions() -> tuple[JobDefinition, ...]:
    return (
        preview_materialize_job_definition(),
        preview_assemble_job_definition(),
        preview_publish_job_definition(),
    )


def preview_materialize_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_MATERIALIZE),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_MATERIALIZE_DECODER,
        handler_identity=PREVIEW_MATERIALIZE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def preview_assemble_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_ASSEMBLE),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_ASSEMBLE_DECODER,
        handler_identity=PREVIEW_ASSEMBLE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def preview_publish_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_PUBLISH),
        supported_payload_versions=frozenset({PREVIEW_JOB_CONTRACT_VERSION}),
        decoder_identity=PREVIEW_PUBLISH_DECODER,
        handler_identity=PREVIEW_PUBLISH_HANDLER,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def decode_preview_payload(payload_object: dict[str, object]) -> PreviewJobPayload:
    _reject_unknown_top_level_keys(payload_object)
    workspace_id = _require_non_empty_str(payload_object, "workspace_id")
    upload_revision_id = _require_non_empty_str(payload_object, "upload_revision_id")
    generation = _require_non_negative_int(payload_object, "generation")
    repository_id = _require_non_empty_str(payload_object, "repository_id")
    business_baseline_node_id = _require_non_empty_str(payload_object, "business_baseline_node_id")
    business_baseline_commit_id = _require_non_empty_str(payload_object, "business_baseline_commit_id")
    baseline_head_version = _require_non_negative_int(payload_object, "baseline_head_version")
    input_completeness = _decode_input_completeness(payload_object.get("input_completeness"))
    source_artifacts = _decode_source_artifacts(payload_object.get("source_artifacts"))
    source_digests = _decode_string_map(payload_object.get("source_digests"), label="source_digests")
    input_digest = _require_non_empty_str(payload_object, "input_digest")
    ruleset_version = _require_non_empty_str(payload_object, "ruleset_version")
    capability_contract_versions = _decode_object_map(
        payload_object.get("capability_contract_versions"),
        label="capability_contract_versions",
    )
    provider_versions = _decode_string_map(payload_object.get("provider_versions"), label="provider_versions")
    ready_closure_contract_version = _require_non_empty_str(
        payload_object,
        "ready_closure_contract_version",
    )
    idempotency_identity = _decode_idempotency_identity(payload_object.get("idempotency_identity"))
    options = _decode_object_map(payload_object.get("options"), label="options")
    _validate_role_closure(input_completeness, source_artifacts)
    return PreviewJobPayload(
        workspace_id=workspace_id,
        upload_revision_id=upload_revision_id,
        generation=generation,
        repository_id=repository_id,
        business_baseline_node_id=business_baseline_node_id,
        business_baseline_commit_id=business_baseline_commit_id,
        baseline_head_version=baseline_head_version,
        input_completeness=input_completeness,
        source_artifacts=source_artifacts,
        source_digests=source_digests,
        input_digest=input_digest,
        ruleset_version=ruleset_version,
        capability_contract_versions=capability_contract_versions,
        provider_versions=dict(provider_versions),
        ready_closure_contract_version=ready_closure_contract_version,
        idempotency_identity=idempotency_identity,
        options=options,
    )


def preview_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_preview_payload
    return {
        PREVIEW_MATERIALIZE_DECODER: decoder,
        PREVIEW_ASSEMBLE_DECODER: decoder,
        PREVIEW_PUBLISH_DECODER: decoder,
    }


def bind_control_transaction_factory(
    inner: PreviewControlTransactionFactory,
) -> PreviewControlTransactionFactory:
    """Bind the active preview transaction for publish-time workspace writes."""

    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[PreviewControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> PreviewControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_preview_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_preview_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[PreviewControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory


def preview_composition_bundle(
    deps: PreviewRuntimeDependencies,
) -> tuple[tuple[JobDefinition, ...], Mapping[str, ClaimedExecutor], Mapping[str, PayloadDecoder]]:
    bound_deps = PreviewRuntimeDependencies(
        artifact_store=deps.artifact_store,
        repository_provider_factory=deps.repository_provider_factory,
        baseline_head_read=deps.baseline_head_read,
        control_transaction_factory=bind_control_transaction_factory(
            deps.control_transaction_factory
        ),
    )
    return (
        preview_job_definitions(),
        {
            PREVIEW_MATERIALIZE_HANDLER: build_materialize_inputs_handler(bound_deps),
            PREVIEW_ASSEMBLE_HANDLER: build_assemble_preview_handler(bound_deps),
            PREVIEW_PUBLISH_HANDLER: build_publish_preview_handler(bound_deps),
        },
        dict(preview_payload_decoders()),
    )


def build_preview_recovery_port(deps: PreviewRuntimeDependencies) -> RecoveryPort:
    class _PreviewRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            if (
                operation.status is OperationStatus.SUCCEEDED
                and step.status is StepStatus.SUCCEEDED
                and operation.ready_closure_ref is not None
            ):
                return RecoveryOutcome(
                    disposition=RecoveryOutcomeDisposition.PUBLISHED,
                    diagnostic_code=None,
                    reason=None,
                )
            if step.step_name == PREVIEW_STEP_PUBLISH:
                handler = build_publish_preview_handler(deps)
                try:
                    acknowledgment = handler(operation, step, control, lease_session)
                except (PreviewJobError, CheckpointDecodeError, PayloadDecodeError) as exc:
                    return RecoveryOutcome(
                        disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                        diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                        reason=str(exc),
                    )
                if acknowledgment is ExecutorAcknowledgment.PUBLISHED:
                    return RecoveryOutcome(
                        disposition=RecoveryOutcomeDisposition.PUBLISHED,
                        diagnostic_code=None,
                        reason=None,
                    )
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="preview recovery requires a runnable handler replay",
            )

    return cast(RecoveryPort, _PreviewRecoveryPort())


def build_materialize_inputs_handler(deps: PreviewRuntimeDependencies) -> ClaimedExecutor:
    definition = preview_materialize_job_definition()

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_preview_payload(operation, deps.artifact_store)
        key = definition.key

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the preview materialize JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            sides = _sides_from_materialize_checkpoint(envelope.job_state, deps.artifact_store)
            _pin_preview_refs(
                deps,
                (step.checkpoint_ref, *_closed_refs_from_sides(sides)),
                owner_kind="preview-checkpoint",
                owner_id=step.step_id,
                intent="materialize-checkpoint",
            )
        else:
            sides = _materialize_all_sides(payload, deps)
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_INPUT_COMPLETENESS: payload.input_completeness.value,
                    _JOB_STATE_BASELINE_COMMIT: payload.business_baseline_commit_id,
                    _JOB_STATE_SIDES: _serialize_sides(sides, payload),
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                _pinned_checkpoint_builder(
                    checkpoint_ref=checkpoint_ref,
                    extra_refs=_closed_refs_from_sides(sides),
                    intent="materialize-checkpoint",
                )
            )

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            _make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=PREVIEW_STEP_ASSEMBLE,
                successor_step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_ASSEMBLE),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def build_assemble_preview_handler(deps: PreviewRuntimeDependencies) -> ClaimedExecutor:
    materialize_definition = preview_materialize_job_definition()
    assemble_definition = preview_assemble_job_definition()

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_preview_payload(operation, deps.artifact_store)
        materialize_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_MATERIALIZE),
        )
        if materialize_step.checkpoint_ref is None:
            raise PreviewJobError("materialize checkpoint is missing")
        materialize_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            materialize_step.checkpoint_ref,
        )
        if not definition_matches_checkpoint(materialize_definition, materialize_envelope):
            raise CheckpointDecodeError(
                "materialize checkpoint does not match the preview JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        sides = _sides_from_materialize_checkpoint(materialize_envelope.job_state, deps.artifact_store)

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(assemble_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the preview assemble JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            assemble_state = envelope.job_state.get(_JOB_STATE_ASSEMBLE)
            if type(assemble_state) is not dict:
                raise CheckpointDecodeError(
                    "assemble checkpoint is missing assemble_state",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            ready_closure_id = envelope.job_state.get(_JOB_STATE_READY_CLOSURE)
            if type(ready_closure_id) is not str or not ready_closure_id:
                raise CheckpointDecodeError(
                    "assemble checkpoint is missing ready_closure_artifact_id",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            resume_refs: list[ArtifactRef] = [step.checkpoint_ref]
            ready_closure_ref_raw = envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
            if type(ready_closure_ref_raw) is dict:
                resume_refs.append(artifact_ref_from_dict(ready_closure_ref_raw))
            _pin_preview_refs(
                deps,
                tuple(resume_refs),
                owner_kind="preview-checkpoint",
                owner_id=step.step_id,
                intent="assemble-checkpoint",
            )
        else:
            assemble_state, bundle_manifest_ref, bundle_digest = _assemble_preview(
                payload,
                sides,
                deps.artifact_store,
                lease_session,
                control,
            )
            ready_refs = _ready_closure_refs_from_assemble(assemble_state, bundle_manifest_ref)
            closure_ref = prepare_ready_closure(
                deps.artifact_store,
                ready_refs,
                operation.job_contract_version,
            )
            envelope = envelope_for_step(
                key=assemble_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_ASSEMBLE: assemble_state,
                    _JOB_STATE_READY_CLOSURE: closure_ref.artifact_id,
                    _JOB_STATE_READY_CLOSURE_REF: artifact_ref_to_dict(closure_ref),
                    _JOB_STATE_BUNDLE_ARTIFACT: bundle_manifest_ref.artifact_id,
                    _JOB_STATE_BUNDLE_DIGEST: bundle_digest,
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                _pinned_checkpoint_builder(
                    checkpoint_ref=checkpoint_ref,
                    extra_refs=(closure_ref, bundle_manifest_ref, *ready_refs),
                    intent="assemble-checkpoint",
                )
            )

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            _make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=PREVIEW_STEP_PUBLISH,
                successor_step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_PUBLISH),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def build_publish_preview_handler(deps: PreviewRuntimeDependencies) -> ClaimedExecutor:
    assemble_definition = preview_assemble_job_definition()

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_preview_payload(operation, deps.artifact_store)
        assemble_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_ASSEMBLE),
        )
        if assemble_step.checkpoint_ref is None:
            raise PreviewJobError("assemble checkpoint is missing")
        assemble_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            assemble_step.checkpoint_ref,
        )
        if not definition_matches_checkpoint(assemble_definition, assemble_envelope):
            raise CheckpointDecodeError(
                "assemble checkpoint does not match the preview JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        assemble_state = assemble_envelope.job_state.get(_JOB_STATE_ASSEMBLE)
        ready_closure_id = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE)
        ready_closure_ref_raw = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        bundle_artifact_id = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_ARTIFACT)
        bundle_digest = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_DIGEST)
        if (
            type(assemble_state) is not dict
            or type(ready_closure_id) is not str
            or not ready_closure_id
            or type(ready_closure_ref_raw) is not dict
            or type(bundle_artifact_id) is not str
            or not bundle_artifact_id
            or type(bundle_digest) is not str
            or not bundle_digest
        ):
            raise CheckpointDecodeError(
                "assemble checkpoint is incomplete for preview publication",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )

        ready_closure_ref = artifact_ref_from_dict(ready_closure_ref_raw)
        try:
            deps.artifact_store.locate(ready_closure_ref)
        except ManifestVerificationError as exc:
            raise CheckpointDecodeError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc

        preview_result = _build_preview_result(
            payload=payload,
            operation=operation,
            assemble_state=cast(dict[str, object], assemble_state),
            bundle_artifact_id=bundle_artifact_id,
            bundle_digest=bundle_digest,
            ready_closure_artifact_id=ready_closure_id,
            transaction_now=datetime.now(UTC),
        )

        _atomic_publish_preview(
            lease_session=lease_session,
            deps=deps,
            payload=payload,
            preview_result=preview_result,
            ready_closure_ref=ready_closure_ref,
            control=control,
        )
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def _atomic_publish_preview(
    *,
    lease_session: LeaseSession,
    deps: PreviewRuntimeDependencies,
    payload: PreviewJobPayload,
    preview_result: PreviewResult,
    ready_closure_ref: ArtifactRef,
    control: ExecutionControl,
) -> None:
    pending_result = preview_result

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview publication transaction is not bound")
        workspace = transaction.workspace.get_workspace(payload.workspace_id)
        if workspace is None:
            raise PreviewJobError("workspace is missing at preview publication")
        baseline_head = deps.baseline_head_read.get_current_head(payload.repository_id)
        if _publication_drift(payload, workspace, baseline_head):
            _release_preview_step_protection(
                transaction,
                operation_id=operation.operation_id,
                clear_operation_owner=True,
            )
            terminal_step = _terminal_step(step, transaction_now, status=StepStatus.SUCCEEDED)
            terminal_operation = dataclasses.replace(
                operation,
                status=OperationStatus.SUPERSEDED,
                updated_at=transaction_now,
                completed_at=transaction_now,
                optimistic_version=operation.optimistic_version + 1,
            )
            return terminal_step, terminal_operation

        _persist_preview_business_state(
            transaction,
            workspace=workspace,
            payload=payload,
            preview_result=pending_result,
            ready_closure_ref=ready_closure_ref,
            closure_output_refs=closure_output_refs,
            transaction_now=transaction_now,
        )
        terminal_step = _terminal_step(step, transaction_now, status=StepStatus.SUCCEEDED)
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.SUCCEEDED,
            ready_closure_ref=ready_closure_ref,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    closure_output_refs = load_ready_closure(deps.artifact_store, ready_closure_ref).artifact_refs()
    lease_session.publish_operation(builder)


def _persist_preview_business_state(
    unit_of_work: PreviewControlTransaction,
    *,
    workspace: Workspace,
    payload: PreviewJobPayload,
    preview_result: PreviewResult,
    ready_closure_ref: ArtifactRef,
    closure_output_refs: tuple[ArtifactRef, ...],
    transaction_now: datetime,
) -> None:
    unit_of_work.workspace.save_preview_result(preview_result)
    updated_workspace = dataclasses.replace(
        workspace,
        current_preview_result_id=preview_result.preview_result_id,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=transaction_now,
    )
    unit_of_work.workspace.save_workspace(updated_workspace, expected_version=workspace.optimistic_version)
    unit_of_work.set_artifact_protection(
        _unique_refs((ready_closure_ref, *closure_output_refs, *_payload_source_refs(payload))),
        owner_kind="current-preview",
        owner_id=workspace.workspace_id,
        intent="current-preview",
    )
    _release_preview_step_protection(
        unit_of_work,
        operation_id=preview_result.operation_id,
        clear_operation_owner=False,
    )


def _publication_drift(
    payload: PreviewJobPayload,
    workspace: Workspace,
    baseline_head: object,
) -> bool:
    from gateway_backend.domain.workspace.models import BaselineHead

    if workspace.generation != payload.generation:
        return True
    if workspace.current_upload_revision_id != payload.upload_revision_id:
        return True
    if type(baseline_head) is not BaselineHead:
        return True
    if baseline_head.business_baseline_node_id != payload.business_baseline_node_id:
        return True
    if baseline_head.business_baseline_commit_id != payload.business_baseline_commit_id:
        return True
    if baseline_head.baseline_head_version != payload.baseline_head_version:
        return True
    return False


def _materialize_all_sides(
    payload: PreviewJobPayload,
    deps: PreviewRuntimeDependencies,
) -> dict[str, BoundSnapshotInput]:
    provider = deps.repository_provider_factory(
        payload.repository_id,
        payload.business_baseline_commit_id,
    )
    baseline = _materialize_baseline(payload, provider, deps.artifact_store)
    sides: dict[str, BoundSnapshotInput] = {_SIDE_BASELINE: baseline}
    if payload.input_completeness is InputCompleteness.FULL:
        sides[_SIDE_INITIAL] = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.INITIAL],
            deps.artifact_store,
        )
        sides[_SIDE_MODIFIED] = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.MODIFIED],
            deps.artifact_store,
        )
    else:
        sides[_SIDE_INITIAL] = baseline
        sides[_SIDE_MODIFIED] = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.MODIFIED],
            deps.artifact_store,
        )
    return sides


def _materialize_baseline_commit(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
) -> BoundSnapshotInput:
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=repository_id, ref=commit_id),
        provider=provider,
        ruleset=TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION),
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=store,
    )
    result = materialize_repository_ref(request)
    return _bound_from_materialization(result, label="baseline")


def _materialize_baseline(
    payload: PreviewJobPayload,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
) -> BoundSnapshotInput:
    return _materialize_baseline_commit(
        repository_id=payload.repository_id,
        commit_id=payload.business_baseline_commit_id,
        provider=provider,
        store=store,
    )


def _materialize_uploaded_side(binding: SourceArtifactBinding, store: ArtifactStorePort) -> BoundSnapshotInput:
    artifact_ref = _artifact_ref_from_binding(binding)
    raw_bytes = store.locate(artifact_ref)
    staged = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=StagingInvocationContext(NeverCancel()),
            payload=raw_bytes,
            expected_required_sql_digest=None,
        ),
        store,
    )
    if staged.status is not StagingStatus.COMPLETE or staged.required_sql_document_ref is None:
        raise PreviewJobError("uploaded source package staging failed")
    dump = resolve_sql_dump_source(staged.required_sql_document_ref)
    sql_bytes = store.locate(staged.required_sql_document_ref.artifact_ref)
    parsed = parse_sql(_sql_request_from_bytes(sql_bytes))
    result = materialize_sql_snapshot(
        _sql_materialization_request(parsed, dump.sql_source_digest, store),
    )
    return _bound_from_materialization(result, label="uploaded")


@dataclass(frozen=True, slots=True)
class _PairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    surface_result: SurfaceAssemblyResult


def surface_artifact_closure(surface: ComparisonSurface | None, pair_id: str) -> BundleArtifactClosure:
    if surface is None:
        raise PreviewJobError("surface assembly did not produce a surface for bundle closure")
    bindings: list[BundleArtifactBinding] = []
    prefix = f"pairs/{pair_id}"

    def add(
        ref: ArtifactRef | None,
        logical_path: str,
        kind: BundleArtifactKind,
        *,
        table_name: str | None = None,
    ) -> None:
        if ref is None:
            return
        bindings.append(
            BundleArtifactBinding(
                source_ref=ref,
                logical_path=logical_path,
                kind=kind,
                pair_id=pair_id,
                table_name=table_name,
            )
        )

    add(
        surface.refs.records_closure_ref,
        f"{prefix}/comparison/records/closure.json",
        BundleArtifactKind.RECORDS_CLOSURE,
    )
    add(surface.refs.risk_report_ref, f"{prefix}/risk/report.json", BundleArtifactKind.RISK_REPORT)
    add(
        surface.refs.risk_annotation_closure_ref,
        f"{prefix}/risk/annotations/closure.json",
        BundleArtifactKind.RISK_ANNOTATION_CLOSURE,
    )
    add(
        surface.refs.project_identity_assessment_ref,
        f"{prefix}/identity/assessment.json",
        BundleArtifactKind.OTHER,
    )
    add(surface.refs.diagnostics_ref, f"{prefix}/diagnostics/surface.json", BundleArtifactKind.DIAGNOSTICS)
    for table in surface.tables:
        table_name = table.table_name
        add(
            table.table_refs.before_table_ref,
            f"{prefix}/tables/before/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.table_refs.current_table_ref,
            f"{prefix}/tables/current/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.table_refs.browse_table_ref,
            f"{prefix}/tables/browse/{table_name}.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            table_name=table_name,
        )
        add(
            table.records_refs.records_ref,
            f"{prefix}/comparison/records/{table_name}/rows.bin",
            BundleArtifactKind.RECORDS,
            table_name=table_name,
        )
        add(
            table.records_refs.records_manifest_ref,
            f"{prefix}/comparison/records/{table_name}/manifest.json",
            BundleArtifactKind.RECORDS_MANIFEST,
            table_name=table_name,
        )
        add(
            table.risk_refs.report_ref,
            f"{prefix}/risk/tables/{table_name}/report.json",
            BundleArtifactKind.RISK_REPORT,
            table_name=table_name,
        )
        add(
            table.risk_refs.annotation_ref,
            f"{prefix}/risk/tables/{table_name}/annotations.bin",
            BundleArtifactKind.RISK_ANNOTATION,
            table_name=table_name,
        )
        add(
            table.risk_refs.annotation_manifest_ref,
            f"{prefix}/risk/tables/{table_name}/annotations/manifest.json",
            BundleArtifactKind.RISK_ANNOTATION_MANIFEST,
            table_name=table_name,
        )
        add(
            table.diagnostics.diagnostics_ref,
            f"{prefix}/diagnostics/tables/{table_name}.json",
            BundleArtifactKind.DIAGNOSTICS,
            table_name=table_name,
        )
        if table.ordered_extension is not None:
            for key, value in table.ordered_extension.items():
                if key.endswith("_ref") and isinstance(value, ArtifactRef):
                    add(
                        value,
                        f"{prefix}/ordered/{table_name}/{key}.json",
                        BundleArtifactKind.OTHER,
                        table_name=table_name,
                    )
    for projection in surface.projections:
        add(
            projection.projection_ref,
            f"{prefix}/projections/{projection.projection_id}.json",
            BundleArtifactKind.PROJECTION,
        )
        add(
            projection.risk_summary_ref,
            f"{prefix}/projections/{projection.projection_id}/risk-summary.json",
            BundleArtifactKind.RISK_REPORT,
        )
        add(
            projection.diagnostics_ref,
            f"{prefix}/projections/{projection.projection_id}/diagnostics.json",
            BundleArtifactKind.DIAGNOSTICS,
        )
    covered = {binding.source_ref for binding in bindings}
    for ref in collect_surface_refs(surface):
        if ref not in covered:
            raise PreviewJobError(f"surface ref {ref.artifact_id} is not mapped for bundle closure")
    return BundleArtifactClosure(tuple(bindings))


def _assemble_preview(
    payload: PreviewJobPayload,
    sides: dict[str, BoundSnapshotInput],
    store: ArtifactStorePort,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> tuple[dict[str, object], ArtifactRef, str]:
    pair_results: list[_PairPipelineResult] = []
    bundle_pairs: list[BundlePairInput] = []
    if payload.input_completeness is InputCompleteness.FULL:
        pair_specs: tuple[tuple[str, BoundSnapshotInput, BoundSnapshotInput, PairRole], ...] = (
            (_PAIR_BASELINE_TO_INITIAL, sides[_SIDE_BASELINE], sides[_SIDE_INITIAL], PairRole.BASELINE_TO_INITIAL),
            (_PAIR_INITIAL_TO_MODIFIED, sides[_SIDE_INITIAL], sides[_SIDE_MODIFIED], PairRole.INITIAL_TO_MODIFIED),
        )
        bundle_profile = BundleProfile.MULTI_PAIR
        bundle_inputs: tuple[BundleInput, ...] = (
            BundleInput(0, "baseline", "Baseline"),
            BundleInput(1, "initial", "Initial"),
            BundleInput(2, "modified", "Modified"),
        )
        bundle_indexes: dict[str, tuple[int, int]] = {
            _PAIR_BASELINE_TO_INITIAL: (0, 1),
            _PAIR_INITIAL_TO_MODIFIED: (1, 2),
        }
    else:
        pair_specs = (
            (
                _PAIR_INITIAL_TO_MODIFIED,
                sides[_SIDE_BASELINE],
                sides[_SIDE_MODIFIED],
                PairRole.INITIAL_TO_MODIFIED,
            ),
        )
        bundle_profile = BundleProfile.SINGLE_PAIR
        bundle_inputs = (
            BundleInput(0, "baseline", "Baseline"),
            BundleInput(1, "modified", "Modified"),
        )
        bundle_indexes = {_PAIR_INITIAL_TO_MODIFIED: (0, 1)}

    for pair_id, before, current, pair_role in pair_specs:
        lease_session.refresh_control()
        if control.cancel_requested:
            raise PreviewJobError("preview assembly cancelled")
        pair_state = _run_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            pair_role=pair_role,
            input_completeness=payload.input_completeness,
            baseline=sides[_SIDE_BASELINE] if payload.input_completeness is InputCompleteness.MODIFIED_ONLY else None,
            store=store,
            control=control,
        )
        pair_results.append(pair_state)
        before_index, current_index = bundle_indexes[pair_id]
        bundle_pairs.append(
            BundlePairInput(
                pair_id,
                before_index,
                current_index,
                pair_state.surface_result,
                surface_artifact_closure(pair_state.surface_result.surface, pair_id),
            )
        )

    bundle_result = assemble_bundle(
        BundleAssemblyInput(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_profile=bundle_profile,
            inputs=bundle_inputs,
            pairs=tuple(bundle_pairs),
            ref_scope=BundleRefScope.BUNDLE_RELATIVE,
        ),
        source_store=store,
        context=BundleAssemblyContext(
            checkpoint=lease_session.refresh_control,
            cancel_requested=lambda: control.cancel_requested,
        ),
    )
    if bundle_result.status is not BundleAssemblyStatus.READY or bundle_result.bundle is None:
        raise PreviewJobError("bundle assembly failed")
    required_refs = _required_ready_refs(
        payload=payload,
        sides=sides,
        pair_results=pair_results,
        bundle_manifest_ref=bundle_result.bundle.manifest_ref,
    )
    assemble_state: dict[str, object] = {
        "pair_ids": [item.pair_id for item in pair_results],
        "default_view": _PAIR_INITIAL_TO_MODIFIED,
        "input_completeness": payload.input_completeness.value,
        "digests": {
            "source_digest": payload.input_digest,
            "input_digest": payload.input_digest,
            "snapshot_digest": sides[_SIDE_MODIFIED].snapshot.snapshot_digest.value,
            "comparison_digest": pair_results[-1].comparison_digest,
            "risk_digest": pair_results[-1].risk_digest,
            "surface_digest": pair_results[-1].surface_digest,
            "bundle_digest": bundle_result.bundle.bundle_digest.value,
        },
        "required_refs": [artifact_ref_to_dict(item) for item in required_refs],
    }
    return assemble_state, bundle_result.bundle.manifest_ref, bundle_result.bundle.bundle_digest.value


def compute_baseline_canonical_bundle_digest(
    *,
    repository_id: str,
    baseline_head: BaselineHead,
    input_completeness: InputCompleteness,
    ruleset_version: str,
    provider_factory: Callable[[str, str], RepositoryTableAccessProvider],
    store: ArtifactStorePort,
) -> str:
    """Compute business-base canonical digest using preview-isomorphic bundle topology."""

    if type(ruleset_version) is not str or not ruleset_version:
        raise PreviewJobError("ruleset_version must be a non-empty string")
    if ruleset_version != RULESET_VERSION:
        raise PreviewJobError("ruleset_version is not supported by this implementation")
    provider = provider_factory(repository_id, baseline_head.business_baseline_commit_id)
    baseline = _materialize_baseline_commit(
        repository_id=repository_id,
        commit_id=baseline_head.business_baseline_commit_id,
        provider=provider,
        store=store,
    )
    sides: dict[str, BoundSnapshotInput] = {_SIDE_BASELINE: baseline}
    if input_completeness is InputCompleteness.FULL:
        sides[_SIDE_INITIAL] = baseline
        sides[_SIDE_MODIFIED] = baseline
    else:
        sides[_SIDE_MODIFIED] = baseline

    control = ExecutionControl()
    bundle_pairs: list[BundlePairInput] = []
    if input_completeness is InputCompleteness.FULL:
        pair_specs: tuple[tuple[str, BoundSnapshotInput, BoundSnapshotInput, PairRole], ...] = (
            (_PAIR_BASELINE_TO_INITIAL, sides[_SIDE_BASELINE], sides[_SIDE_INITIAL], PairRole.BASELINE_TO_INITIAL),
            (_PAIR_INITIAL_TO_MODIFIED, sides[_SIDE_INITIAL], sides[_SIDE_MODIFIED], PairRole.INITIAL_TO_MODIFIED),
        )
        bundle_profile = BundleProfile.MULTI_PAIR
        bundle_inputs: tuple[BundleInput, ...] = (
            BundleInput(0, "baseline", "Baseline"),
            BundleInput(1, "initial", "Initial"),
            BundleInput(2, "modified", "Modified"),
        )
        bundle_indexes: dict[str, tuple[int, int]] = {
            _PAIR_BASELINE_TO_INITIAL: (0, 1),
            _PAIR_INITIAL_TO_MODIFIED: (1, 2),
        }
    else:
        pair_specs = (
            (
                _PAIR_INITIAL_TO_MODIFIED,
                sides[_SIDE_BASELINE],
                sides[_SIDE_MODIFIED],
                PairRole.INITIAL_TO_MODIFIED,
            ),
        )
        bundle_profile = BundleProfile.SINGLE_PAIR
        bundle_inputs = (
            BundleInput(0, "baseline", "Baseline"),
            BundleInput(1, "modified", "Modified"),
        )
        bundle_indexes = {_PAIR_INITIAL_TO_MODIFIED: (0, 1)}

    for pair_id, before, current, pair_role in pair_specs:
        if control.cancel_requested:
            raise PreviewJobError("baseline canonical digest assembly cancelled")
        pair_state = _run_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            pair_role=pair_role,
            input_completeness=input_completeness,
            baseline=sides[_SIDE_BASELINE] if input_completeness is InputCompleteness.MODIFIED_ONLY else None,
            store=store,
            control=control,
        )
        before_index, current_index = bundle_indexes[pair_id]
        bundle_pairs.append(
            BundlePairInput(
                pair_id,
                before_index,
                current_index,
                pair_state.surface_result,
                surface_artifact_closure(pair_state.surface_result.surface, pair_id),
            )
        )

    bundle_result = assemble_bundle(
        BundleAssemblyInput(
            bundle_contract_version=BUNDLE_CONTRACT_VERSION,
            bundle_profile=bundle_profile,
            inputs=bundle_inputs,
            pairs=tuple(bundle_pairs),
            ref_scope=BundleRefScope.BUNDLE_RELATIVE,
        ),
        source_store=store,
        context=BundleAssemblyContext(
            checkpoint=lambda: None,
            cancel_requested=lambda: control.cancel_requested,
        ),
    )
    if bundle_result.status is not BundleAssemblyStatus.READY or bundle_result.bundle is None:
        raise PreviewJobError("baseline bundle assembly failed")
    return bundle_result.bundle.bundle_digest.value


def _run_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    pair_role: PairRole,
    input_completeness: InputCompleteness,
    baseline: BoundSnapshotInput | None,
    store: ArtifactStorePort,
    control: ExecutionControl,
) -> _PairPipelineResult:
    assessment_digest = raw_blob_digest(
        f"{before.snapshot.snapshot_digest.value}:{current.snapshot.snapshot_digest.value}".encode()
    )
    assessment = _PreviewIdentityAssessment(
        schema_version="project-identity-assessment/v1",
        rule_version="version-manager-overlap/v1",
        before_snapshot_digest=before.snapshot.snapshot_digest,
        current_snapshot_digest=current.snapshot.snapshot_digest,
        status=IdentityStatus.SAME_PROJECT,
        assessment_digest=assessment_digest,
    )
    baseline_reconstruction = None
    if input_completeness is InputCompleteness.MODIFIED_ONLY and baseline is not None:
        baseline_reconstruction = BaselineReconstructionResult(
            status=BaselineReconstructionStatus.AVAILABLE,
            baseline=baseline,
        )
    bound = bind_pair_input(
        pair_id=pair_id,
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=pair_role,
        before=before if input_completeness is InputCompleteness.FULL else None,
        current=current,
        input_completeness=(
            ComparisonInputCompleteness.FULL
            if input_completeness is InputCompleteness.FULL
            else ComparisonInputCompleteness.MODIFIED_ONLY
        ),
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
        baseline_reconstruction=baseline_reconstruction,
    )
    if isinstance(bound, FailedResult):
        raise PreviewJobError(f"pair binding failed: {bound.diagnostics}")
    plan = plan_pair(bound)
    if isinstance(plan, FailedResult):
        raise PreviewJobError(f"pair planning failed: {plan.diagnostics}")
    if not isinstance(plan, ComparisonPlan):
        raise PreviewJobError("pair planning did not produce a comparison plan")
    compared = compare_plan(plan)
    if isinstance(compared, FailedResult):
        raise PreviewJobError(f"pair comparison failed: {compared.diagnostics}")
    if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
        raise PreviewJobError("pair comparison did not produce facts")
    published = publish_records_closure(compared, store)
    if isinstance(published, FailedResult):
        raise PreviewJobError(f"records closure failed: {published.diagnostics}")
    if not isinstance(published, DetailedFactsResult) or published.facts is None:
        raise PreviewJobError("records publication did not produce facts")
    if control.cancel_requested:
        raise PreviewJobError("preview pair pipeline cancelled")
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=published.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=store,
    )
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise PreviewJobError("risk evaluation failed")
    surface = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=published.facts,
            surface_id=f"surface-{pair_id}",
            view_id=_PAIR_INITIAL_TO_MODIFIED,
            before_role="before",
            current_role="current",
            records_closure=published.records_closure,
            risk_report=risk.risk_report,
            risk_annotation_closure=risk.risk_closure,
            ref_scope=SurfaceRefScope.OPERATION_RELATIVE,
        ),
        context=SurfaceAssemblyContext(cancel_requested=lambda: control.cancel_requested),
    )
    if surface.status is not SurfaceAssemblyStatus.READY or surface.surface is None:
        raise PreviewJobError("surface assembly failed")
    return _PairPipelineResult(
        pair_id=pair_id,
        comparison_digest=published.facts.comparison_digest.value,
        risk_digest=risk.risk_evaluation.risk_evaluation_digest.value if risk.risk_evaluation else "",
        surface_digest=surface.surface.surface_digest.value,
        surface_result=surface,
    )


def _build_preview_result(
    *,
    payload: PreviewJobPayload,
    operation: OperationRecord,
    assemble_state: dict[str, object],
    bundle_artifact_id: str,
    bundle_digest: str,
    ready_closure_artifact_id: str,
    transaction_now: datetime,
) -> PreviewResult:
    digests_payload = assemble_state.get("digests")
    if type(digests_payload) is not dict:
        raise PreviewJobError("assemble checkpoint digests are missing")
    digests = PreviewResultDigests(
        source_digest=str(digests_payload["source_digest"]),
        input_digest=str(digests_payload["input_digest"]),
        snapshot_digest=str(digests_payload["snapshot_digest"]),
        comparison_digest=str(digests_payload["comparison_digest"]),
        risk_digest=str(digests_payload["risk_digest"]),
        surface_digest=str(digests_payload["surface_digest"]),
        bundle_digest=str(digests_payload["bundle_digest"]),
    )
    return PreviewResult(
        preview_result_id=f"pr-{uuid.uuid4()}",
        workspace_id=payload.workspace_id,
        upload_revision_id=payload.upload_revision_id,
        generation=payload.generation,
        repository_id=payload.repository_id,
        business_baseline_node_id=payload.business_baseline_node_id,
        business_baseline_commit_id=payload.business_baseline_commit_id,
        baseline_head_version=payload.baseline_head_version,
        ruleset_version=payload.ruleset_version,
        contract_version=PREVIEW_JOB_CONTRACT_VERSION,
        provider_versions=dict(payload.provider_versions),
        digests=digests,
        bundle_artifact_id=bundle_artifact_id,
        ready_closure_artifact_id=ready_closure_artifact_id,
        operation_id=operation.operation_id,
        created_at=transaction_now,
    )


def _ready_closure_refs_from_assemble(
    assemble_state: dict[str, object],
    bundle_manifest_ref: ArtifactRef,
) -> tuple[ArtifactRef, ...]:
    raw_refs = assemble_state.get("required_refs")
    if type(raw_refs) is not list or not raw_refs:
        raise PreviewJobError("assemble state is missing required ready-closure refs")
    refs: list[ArtifactRef] = []
    for item in raw_refs:
        if type(item) is not dict:
            raise PreviewJobError("assemble required ref is invalid")
        refs.append(artifact_ref_from_dict(item))
    refs.append(bundle_manifest_ref)
    return _unique_refs(tuple(refs))


def _required_ready_refs(
    *,
    payload: PreviewJobPayload,
    sides: dict[str, BoundSnapshotInput],
    pair_results: list[_PairPipelineResult],
    bundle_manifest_ref: ArtifactRef,
) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    refs.extend(_side_input_refs(sides[_SIDE_BASELINE]))
    if payload.input_completeness is InputCompleteness.FULL:
        refs.extend(_side_input_refs(sides[_SIDE_INITIAL]))
        refs.extend(_side_input_refs(sides[_SIDE_MODIFIED]))
    else:
        refs.extend(_side_input_refs(sides[_SIDE_MODIFIED]))
    for pair_state in pair_results:
        if pair_state.surface_result.surface is None:
            raise PreviewJobError("pair surface is missing from ready closure")
        refs.extend(collect_surface_refs(pair_state.surface_result.surface))
    refs.append(bundle_manifest_ref)
    return _unique_refs(tuple(refs))


def _side_input_refs(bound: BoundSnapshotInput) -> tuple[ArtifactRef, ...]:
    if bound.table_set is None:
        raise PreviewJobError("snapshot table set is missing closed refs")
    refs: list[ArtifactRef] = []
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise PreviewJobError(f"table {table.descriptor.table_name} is missing artifact refs")
        refs.append(table.artifact.manifest_ref)
        refs.extend(table.artifact.manifest.row_file_refs)
    return tuple(refs)


def _unique_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    seen: set[str] = set()
    unique: list[ArtifactRef] = []
    for ref in refs:
        if ref.artifact_id in seen:
            continue
        seen.add(ref.artifact_id)
        unique.append(ref)
    return tuple(unique)


def _pinned_checkpoint_builder(
    *,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    intent: str,
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    inner = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        candidate = inner(operation, step, transaction_now)
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview checkpoint transaction is not bound")
        transaction.set_artifact_protection(
            _unique_refs((checkpoint_ref, *extra_refs)),
            owner_kind="preview-checkpoint",
            owner_id=step.step_id,
            intent=intent,
        )
        return candidate

    return builder


def _payload_source_refs(payload: PreviewJobPayload) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for binding in payload.source_artifacts.values():
        refs.append(
            ArtifactRef(
                artifact_id=binding.artifact_id,
                media_type=binding.media_type,
                size_bytes=binding.size_bytes,
                raw_sha256=DigestRef(binding.raw_sha256),
            )
        )
    return tuple(refs)


def _release_preview_step_protection(
    unit_of_work: PreviewControlTransaction,
    *,
    operation_id: str,
    clear_operation_owner: bool,
) -> None:
    for step_name in (PREVIEW_STEP_MATERIALIZE, PREVIEW_STEP_ASSEMBLE, PREVIEW_STEP_PUBLISH):
        unit_of_work.clear_artifact_protection(
            owner_kind="preview-checkpoint",
            owner_id=_successor_step_id(operation_id, step_name),
        )
    if clear_operation_owner:
        unit_of_work.clear_artifact_protection(
            owner_kind="preview-operation",
            owner_id=operation_id,
        )


def _pin_preview_refs(
    deps: PreviewRuntimeDependencies,
    refs: tuple[ArtifactRef, ...],
    *,
    owner_kind: str,
    owner_id: str,
    intent: str,
) -> None:
    unique = _unique_refs(refs)
    if not unique:
        return
    with deps.control_transaction_factory() as unit_of_work:
        unit_of_work.set_artifact_protection(
            unique,
            owner_kind=owner_kind,
            owner_id=owner_id,
            intent=intent,
        )


def _closed_refs_from_sides(sides: dict[str, BoundSnapshotInput]) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for bound in sides.values():
        refs.extend(_side_input_refs(bound))
    return tuple(refs)


def _load_step(
    deps: PreviewRuntimeDependencies,
    *,
    operation_id: str,
    step_id: str,
) -> StepRecord:
    with deps.control_transaction_factory() as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
    if step.operation_id != operation_id:
        raise PreviewJobError("preview step belongs to a different operation")
    return step


def _serialize_sides(
    sides: dict[str, BoundSnapshotInput],
    payload: PreviewJobPayload,
) -> dict[str, object]:
    document: dict[str, object] = {}
    for role, bound in sides.items():
        document[role] = _side_binding_document(bound, role=role, payload=payload)
    document["initial_reuses_baseline"] = payload.input_completeness is InputCompleteness.MODIFIED_ONLY
    return document


def _side_binding_document(
    bound: BoundSnapshotInput,
    *,
    role: str,
    payload: PreviewJobPayload,
) -> dict[str, object]:
    if bound.table_set is None:
        raise PreviewJobError(f"{role} table set is missing closed refs")
    tables: list[dict[str, object]] = []
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise PreviewJobError(f"{role} table {table.descriptor.table_name} is missing artifact refs")
        tables.append(
            {
                "table_name": table.descriptor.table_name,
                "manifest_ref": artifact_ref_to_dict(table.artifact.manifest_ref),
                "row_file_refs": [
                    artifact_ref_to_dict(item) for item in table.artifact.manifest.row_file_refs
                ],
            }
        )
    source_ref: dict[str, object] | None = None
    repository_identity: dict[str, object] | None = None
    context = bound.snapshot.source_context
    if context.source_kind is SourceKind.IMMUTABLE_REPOSITORY_REF:
        repository_identity = {
            "repository_id": context.repository_id,
            "repository_ref": context.repository_ref,
            "resolved_commit_hash": context.resolved_commit_hash,
        }
    elif role == _SIDE_INITIAL and payload.input_completeness is InputCompleteness.FULL:
        source_ref = artifact_ref_to_dict(
            _artifact_ref_from_binding(payload.source_artifacts[SourceArtifactRole.INITIAL])
        )
    elif role == _SIDE_MODIFIED:
        source_ref = artifact_ref_to_dict(
            _artifact_ref_from_binding(payload.source_artifacts[SourceArtifactRole.MODIFIED])
        )
    return {
        "contract_version": PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION,
        "snapshot": _snapshot_payload(bound.snapshot),
        "source_ref": source_ref,
        "repository_identity": repository_identity,
        "snapshot_digest": bound.snapshot.snapshot_digest.value,
        "raw_state_digest": bound.snapshot.raw_state_digest.value,
        "summary": _summary_payload(bound.summary),
        "tables": tables,
    }


def _snapshot_payload(snapshot: Snapshot) -> dict[str, object]:
    context = snapshot.source_context
    return {
        "snapshot_id": snapshot.snapshot_id,
        "source_kind": snapshot.source_kind.value,
        "parser_version": snapshot.parser_version,
        "table_ruleset_version": snapshot.table_ruleset_version,
        "scalar_encoding_version": snapshot.scalar_encoding_version,
        "snapshot_materialization_contract_version": snapshot.snapshot_materialization_contract_version,
        "row_materialization_profile": snapshot.row_materialization_profile,
        "materialization_stage": snapshot.materialization_stage.value,
        "snapshot_digest": snapshot.snapshot_digest.value,
        "raw_state_digest": snapshot.raw_state_digest.value,
        "created_at": snapshot.created_at,
        "source_context": {
            "source_kind": context.source_kind.value,
            "sql_source_digest": None if context.sql_source_digest is None else context.sql_source_digest.value,
            "composite_logic_source_digest": (
                None
                if context.composite_logic_source_digest is None
                else context.composite_logic_source_digest.value
            ),
            "repository_id": context.repository_id,
            "repository_ref": context.repository_ref,
            "resolved_commit_hash": context.resolved_commit_hash,
        },
    }


def _sides_from_materialize_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
) -> dict[str, BoundSnapshotInput]:
    raw_sides = job_state.get(_JOB_STATE_SIDES)
    if type(raw_sides) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint sides are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    sides: dict[str, BoundSnapshotInput] = {}
    for role in (_SIDE_BASELINE, _SIDE_INITIAL, _SIDE_MODIFIED):
        if role == _SIDE_INITIAL and raw_sides.get("initial_reuses_baseline") is True:
            baseline = sides.get(_SIDE_BASELINE)
            if baseline is None:
                raise CheckpointDecodeError(
                    "modified-only checkpoint must reuse baseline for initial",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            sides[role] = baseline
            continue
        entry = raw_sides.get(role)
        if type(entry) is not dict:
            raise CheckpointDecodeError(
                f"materialize checkpoint side {role} is invalid",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        sides[role] = _bound_from_side_document(entry, store)
    return sides


def _bound_from_side_document(entry: dict[str, object], store: ArtifactStorePort) -> BoundSnapshotInput:
    tables_raw = entry.get("tables")
    if type(tables_raw) is not list or not tables_raw:
        raise CheckpointDecodeError(
            "materialize checkpoint is missing closed table refs",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    opened = []
    for item in tables_raw:
        if type(item) is not dict:
            raise CheckpointDecodeError(
                "materialize checkpoint table entry is invalid",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        manifest_raw = item.get("manifest_ref")
        if type(manifest_raw) is not dict:
            raise CheckpointDecodeError(
                "materialize checkpoint table is missing manifest_ref",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        try:
            manifest_ref = artifact_ref_from_dict(manifest_raw)
            opened.append(open_snapshot_table_artifact(store, manifest_ref))
        except (TypeError, ValueError, KeyError, ManifestVerificationError, ArtifactPublishError) as exc:
            raise PreviewJobError("materialize checkpoint table artifact is unreadable") from exc
    snapshot = _snapshot_from_payload(entry.get("snapshot"))
    if snapshot.snapshot_digest.value != str(entry.get("snapshot_digest")):
        raise CheckpointDecodeError(
            "materialize checkpoint digest mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    summary = SnapshotSummary(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        raw_state_digest=snapshot.raw_state_digest,
        materialization_stage=snapshot.materialization_stage,
        parser_version=snapshot.parser_version,
        table_ruleset_version=snapshot.table_ruleset_version,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        table_count=len(opened),
        tables=tuple(table.descriptor for table in opened),
        source_context=snapshot.source_context,
        diagnostics=(),
        row_count_total=sum(table.descriptor.row_count for table in opened),
    )
    table_set = SnapshotTableSet(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        table_ruleset_version=snapshot.table_ruleset_version,
        tables=tuple(opened),
    )
    return BoundSnapshotInput(snapshot, summary, table_set)


def _snapshot_from_payload(raw: object) -> Snapshot:
    if type(raw) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint snapshot is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    context_raw = raw.get("source_context")
    if type(context_raw) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint source_context is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    source_kind = SourceKind(str(raw["source_kind"]))
    context_kind = SourceKind(str(context_raw["source_kind"]))
    sql_digest = context_raw.get("sql_source_digest")
    composite_digest = context_raw.get("composite_logic_source_digest")
    source_context = SnapshotSourceContext(
        source_kind=context_kind,
        sql_source_digest=None if sql_digest is None else DigestRef(str(sql_digest)),
        composite_logic_source_digest=(
            None if composite_digest is None else DigestRef(str(composite_digest))
        ),
        repository_id=None if context_raw.get("repository_id") is None else str(context_raw["repository_id"]),
        repository_ref=None if context_raw.get("repository_ref") is None else str(context_raw["repository_ref"]),
        resolved_commit_hash=(
            None
            if context_raw.get("resolved_commit_hash") is None
            else str(context_raw["resolved_commit_hash"])
        ),
    )
    del source_kind
    return Snapshot(
        snapshot_id=str(raw["snapshot_id"]),
        source_kind=context_kind,
        parser_version=int(raw["parser_version"]),
        table_ruleset_version=int(raw["table_ruleset_version"]),
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        snapshot_materialization_contract_version=SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        materialization_stage=MaterializationStage(str(raw["materialization_stage"])),
        snapshot_digest=DigestRef(str(raw["snapshot_digest"])),
        raw_state_digest=DigestRef(str(raw["raw_state_digest"])),
        created_at=str(raw["created_at"]),
        source_context=source_context,
    )


def _summary_payload(summary: object) -> dict[str, object]:
    if type(summary) is not SnapshotSummary:
        raise PreviewJobError("summary payload type is invalid")
    tables = []
    for table in summary.tables:
        tables.append(
            {
                "table_name": table.table_name,
                "display_table_name": table.display_table_name,
                "row_count": table.row_count,
                "primary_key_columns": list(table.primary_key_columns),
                "compare_key_columns": list(table.compare_key_columns),
                "compare_schema_digest": table.compare_schema_digest.value,
                "raw_content_digest": (
                    None if table.raw_content_digest is None else table.raw_content_digest.value
                ),
                "fast_row_digest": None if table.fast_row_digest is None else table.fast_row_digest.value,
            }
        )
    return {
        "snapshot_id": summary.snapshot_id,
        "snapshot_digest": summary.snapshot_digest.value,
        "table_count": summary.table_count,
        "row_count_total": summary.row_count_total,
        "tables": tables,
    }


def _bound_from_materialization(result: SnapshotMaterializationResult, *, label: str) -> BoundSnapshotInput:
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        raise PreviewJobError(f"{label} materialization failed")
    if result.snapshot is None or result.summary is None:
        raise PreviewJobError(f"{label} materialization is incomplete")
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


def _load_preview_payload(operation: OperationRecord, store: ArtifactStorePort) -> PreviewJobPayload:
    payload_bytes = load_job_payload_bytes(operation, store)
    try:
        payload_object = json.loads(payload_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PayloadDecodeError(
            "job_payload must be canonical JSON bytes",
            code="PAYLOAD_SHAPE_INVALID",
        ) from exc
    if type(payload_object) is not dict:
        raise PayloadDecodeError("job_payload must be a JSON object", code="PAYLOAD_SHAPE_INVALID")
    return decode_preview_payload(cast(dict[str, object], payload_object))


def _artifact_ref_from_binding(binding: SourceArtifactBinding) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=binding.artifact_id,
        media_type=binding.media_type,
        size_bytes=binding.size_bytes,
        raw_sha256=DigestRef(binding.raw_sha256),
    )


def _sql_request_from_bytes(sql_bytes: bytes) -> SqlParseRequest:
    digest = raw_blob_digest(sql_bytes)
    source = SqlSourceInput(
        document_content_digest=digest,
        sql_source_digest=digest,
        parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
        encoding="utf-8",
        source_size_bytes=len(sql_bytes),
    )
    return SqlParseRequest(
        source=source,
        sql_utf8=sql_bytes,
        context=ParserInvocationContext(NeverCancel()),
    )


def _sql_materialization_request(
    parsed: ParseResult,
    digest: DigestRef,
    store: ArtifactStorePort,
) -> SqlSnapshotMaterializationRequest:
    return SqlSnapshotMaterializationRequest(
        parse_result=parsed,
        sql_source_digest=digest,
        ruleset=TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION),
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=store,
    )


def _make_successor_builder(
    *,
    operation_id: str,
    successor_step_name: str,
    successor_step_id: str,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, StepRecord]]:
    def builder(
        operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, StepRecord]:
        terminal_step = _terminal_step(current_step, transaction_now, status=StepStatus.SUCCEEDED)
        successor = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=successor_step_id,
            operation_id=operation_id,
            step_name=successor_step_name,
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
            created_at=transaction_now,
            updated_at=transaction_now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        return terminal_step, successor

    return builder


def _terminal_step(step: StepRecord, transaction_now: datetime, *, status: StepStatus) -> StepRecord:
    return dataclasses.replace(
        step,
        status=status,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        completed_at=transaction_now,
        updated_at=transaction_now,
        optimistic_version=step.optimistic_version + 1,
    )


def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview cancellation transaction is not bound")
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        _release_preview_step_protection(
            transaction,
            operation_id=operation.operation_id,
            clear_operation_owner=True,
        )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.CANCELLED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.CANCELLED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _checkpoint_generation(step: StepRecord) -> int:
    attempt_count = step.attempt_count
    if type(attempt_count) is not int or isinstance(attempt_count, bool) or attempt_count < 1:
        raise ValueError("attempt_count must be a positive int for checkpoint generation")
    return attempt_count


def _successor_step_id(operation_id: str, step_name: str) -> str:
    suffix = {
        PREVIEW_STEP_MATERIALIZE: "1",
        PREVIEW_STEP_ASSEMBLE: "2",
        PREVIEW_STEP_PUBLISH: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workspace_id",
        "upload_revision_id",
        "generation",
        "repository_id",
        "business_baseline_node_id",
        "business_baseline_commit_id",
        "baseline_head_version",
        "input_completeness",
        "source_artifacts",
        "source_digests",
        "input_digest",
        "ruleset_version",
        "capability_contract_versions",
        "provider_versions",
        "ready_closure_contract_version",
        "idempotency_identity",
        "options",
    }
)


def _reject_unknown_top_level_keys(payload_object: dict[str, object]) -> None:
    unknown = sorted(set(payload_object) - _ALLOWED_PAYLOAD_KEYS)
    if unknown:
        raise PayloadDecodeError(
            f"unknown preview payload keys: {', '.join(unknown)}",
            code="PAYLOAD_SHAPE_INVALID",
        )


def _require_non_empty_str(payload_object: dict[str, object], key: str) -> str:
    value = payload_object.get(key)
    if type(value) is not str or not value:
        raise PayloadDecodeError(f"{key} must be a non-empty string", code="PAYLOAD_SHAPE_INVALID")
    return value


def _require_non_negative_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise PayloadDecodeError(f"{key} must be a non-negative int", code="PAYLOAD_SHAPE_INVALID")
    return value


def _decode_input_completeness(value: object) -> InputCompleteness:
    if type(value) is not str:
        raise PayloadDecodeError("input_completeness must be a string", code="PAYLOAD_SHAPE_INVALID")
    try:
        return InputCompleteness(value)
    except ValueError as exc:
        raise PayloadDecodeError("input_completeness is invalid", code="PAYLOAD_SHAPE_INVALID") from exc


def _decode_source_artifacts(value: object) -> dict[SourceArtifactRole, SourceArtifactBinding]:
    if type(value) is not dict:
        raise PayloadDecodeError("source_artifacts must be an object", code="PAYLOAD_SHAPE_INVALID")
    decoded: dict[SourceArtifactRole, SourceArtifactBinding] = {}
    for role_name, binding_payload in value.items():
        if type(role_name) is not str:
            raise PayloadDecodeError("source_artifacts role must be a string", code="PAYLOAD_SHAPE_INVALID")
        if type(binding_payload) is not dict:
            raise PayloadDecodeError("source artifact binding must be an object", code="PAYLOAD_SHAPE_INVALID")
        decoded[SourceArtifactRole(role_name)] = SourceArtifactBinding(
            artifact_id=str(binding_payload["artifact_id"]),
            media_type=str(binding_payload["media_type"]),
            size_bytes=int(binding_payload["size_bytes"]),
            raw_sha256=str(binding_payload["raw_sha256"]),
        )
    return decoded


def _decode_string_map(value: object, *, label: str) -> dict[str, str]:
    if type(value) is not dict:
        raise PayloadDecodeError(f"{label} must be an object", code="PAYLOAD_SHAPE_INVALID")
    decoded: dict[str, str] = {}
    for key, item in value.items():
        if type(key) is not str or type(item) is not str:
            raise PayloadDecodeError(f"{label} must be a string map", code="PAYLOAD_SHAPE_INVALID")
        decoded[key] = item
    return decoded


def _decode_object_map(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PayloadDecodeError(f"{label} must be an object", code="PAYLOAD_SHAPE_INVALID")
    return dict(value)


def _decode_idempotency_identity(value: object) -> PreviewIdempotencyIdentity:
    if type(value) is not dict:
        raise PayloadDecodeError("idempotency_identity must be an object", code="PAYLOAD_SHAPE_INVALID")
    return PreviewIdempotencyIdentity(
        workspace_id=_require_non_empty_str(value, "workspace_id"),
        idempotency_key=_require_non_empty_str(value, "idempotency_key"),
    )


def _validate_role_closure(
    input_completeness: InputCompleteness,
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding],
) -> None:
    if input_completeness is InputCompleteness.FULL:
        if SourceArtifactRole.INITIAL not in source_artifacts or SourceArtifactRole.MODIFIED not in source_artifacts:
            raise PayloadDecodeError(
                "FULL preview requires INITIAL and MODIFIED source artifacts",
                code="PAYLOAD_SHAPE_INVALID",
            )
    elif input_completeness is InputCompleteness.MODIFIED_ONLY:
        if SourceArtifactRole.INITIAL in source_artifacts:
            raise PayloadDecodeError(
                "MODIFIED_ONLY preview forbids INITIAL source artifact",
                code="PAYLOAD_SHAPE_INVALID",
            )
        if SourceArtifactRole.MODIFIED not in source_artifacts:
            raise PayloadDecodeError(
                "MODIFIED_ONLY preview requires MODIFIED source artifact",
                code="PAYLOAD_SHAPE_INVALID",
            )


__all__ = [
    "PREVIEW_ASSEMBLE_DECODER",
    "PREVIEW_ASSEMBLE_HANDLER",
    "PREVIEW_JOB_CONTRACT_VERSION",
    "PREVIEW_JOB_KIND",
    "PREVIEW_MATERIALIZE_DECODER",
    "PREVIEW_MATERIALIZE_HANDLER",
    "PREVIEW_PUBLISH_DECODER",
    "PREVIEW_PUBLISH_HANDLER",
    "PREVIEW_STEP_ASSEMBLE",
    "PREVIEW_STEP_MATERIALIZE",
    "PREVIEW_STEP_PUBLISH",
    "PreviewControlTransaction",
    "PreviewControlTransactionFactory",
    "PreviewJobPayload",
    "PreviewRuntimeDependencies",
    "RepositoryProviderFactory",
    "build_assemble_preview_handler",
    "build_materialize_inputs_handler",
    "build_preview_recovery_port",
    "build_publish_preview_handler",
    "compute_baseline_canonical_bundle_digest",
    "decode_preview_payload",
    "surface_artifact_closure",
    "preview_composition_bundle",
    "preview_job_definitions",
    "preview_payload_decoders",
]
