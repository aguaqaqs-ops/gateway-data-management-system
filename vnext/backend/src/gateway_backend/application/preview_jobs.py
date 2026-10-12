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
from typing import ContextManager, cast

from gateway_shared_kernel import DigestRef, canonicalize_jcs, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.canonical_metadata.binding import canonical_binding_for_commit
from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
    load_ready_closure,
    prepare_ready_closure,
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.job_steps import pinned_checkpoint_builder, unique_artifact_refs
from gateway_backend.application.workspace.ports import WorkspaceControlTransaction as PreviewControlTransaction
from gateway_backend.application.pair_pipeline import (
    PairPipelineError,
    PreviewIdentityStatus,
    PreviewPairPipelineResult as _PairPipelineResult,
    run_preview_pair_pipeline,
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
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.digest import build_artifact_id
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
from gateway_backend.capabilities.comparison import BoundSnapshotInput, ComparisonStorageFacts
from gateway_backend.capabilities.snapshot_materialization import (
    ArtifactPublishError,
    materialize_projected_snapshot,
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    SourceKind,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotTableSet,
    canonical_state_digest_of,
    snapshot_from_document,
    snapshot_summary_from_document,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    SqlSnapshotMaterializationRequest,
)
from gateway_backend.capabilities.snapshot_materialization import materialize_sql_snapshot
from gateway_backend.capabilities.snapshot_materialization import (
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
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    ParseResult,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access import parse_sql
from gateway_backend.capabilities.storage_projection import (
    CanonicalProjectionResult,
    CanonicalizationManifest,
    ProjectionStatus,
    PublicationError,
    open_canonicalization_manifest,
    project_canonical_table_set,
    publish_canonicalization_manifest,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
    resolve_table_rule,
)
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    PreviewArtifactRef,
    PreviewCanonicalBindings,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    Workspace,
)
from gateway_backend.domain.workspace.ports import BaselineHeadReadPort
from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
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

PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION = "backend-vnext/preview/materialize-side/v3"
PREVIEW_ASSEMBLE_CHECKPOINT_CONTRACT_VERSION = "backend-vnext/preview/assemble-checkpoint/v1"
_JCS_MEDIA_TYPE = "application/jcs"

_SIDE_BASELINE = "BASELINE"
_SIDE_INITIAL = "INITIAL"
_SIDE_MODIFIED = "MODIFIED"

_PAIR_BASELINE_TO_INITIAL = "baseline_to_initial"
_PAIR_INITIAL_TO_MODIFIED = "initial_to_modified"

_JOB_STATE_SIDES = "sides"
_JOB_STATE_MATERIALIZED_SIDES_REF = "materialized_sides_ref"
_JOB_STATE_CANONICAL = "canonical_preview"
_JOB_STATE_ASSEMBLE = "assemble_state"
_JOB_STATE_ASSEMBLE_REF = "assemble_state_ref"
_JOB_STATE_READY_CLOSURE = "ready_closure_artifact_id"
_JOB_STATE_READY_CLOSURE_REF = "ready_closure_ref"
_JOB_STATE_BUNDLE_ARTIFACT = "bundle_artifact_id"
_JOB_STATE_BUNDLE_DIGEST = "bundle_digest"
_CANONICAL_TABLE_CLOSURE_CONTRACT = "backend-vnext/preview/canonical-table-set-closure/v1"
PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE = "preview-materialized-sides"
PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION = "backend-vnext/preview/materialized-sides/v1"
PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE = "preview-assemble-state"
PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION = "backend-vnext/preview/assemble-state/v1"

_active_preview_transaction: ContextVar[PreviewControlTransaction | None] = ContextVar(
    "_active_preview_transaction",
    default=None,
)


class PreviewJobError(ValueError):
    """Bounded preview job failure surfaced to the operation runtime."""

    def __init__(self, message: str, *, diagnostic_code: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


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
    comparison_ruleset_digest: str
    capability_contract_versions: Mapping[str, object]
    provider_versions: Mapping[str, str]
    ready_closure_contract_version: str
    idempotency_identity: PreviewIdempotencyIdentity
    options: Mapping[str, object]


PreviewControlTransactionFactory = Callable[[], ContextManager[PreviewControlTransaction]]
RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]


@dataclass(frozen=True, slots=True)
class PreviewRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    baseline_head_read: BaselineHeadReadPort
    control_transaction_factory: PreviewControlTransactionFactory


@dataclass(frozen=True, slots=True)
class _CanonicalPreviewMetadata:
    canonical_table_set_closure_ref: ArtifactRef
    canonicalization_manifest_ref: ArtifactRef
    canonicalization_manifest_digest: DigestRef
    initial_canonicalization_manifest_ref: ArtifactRef | None
    initial_canonicalization_manifest_digest: DigestRef | None
    baseline_canonical_state_digest: DigestRef
    modified_canonical_state_digest: DigestRef
    storage_projection_ruleset_digest: DigestRef

    def __post_init__(self) -> None:
        if type(self.canonical_table_set_closure_ref) is not ArtifactRef:
            raise ValueError("canonical_table_set_closure_ref must be ArtifactRef")
        if type(self.canonicalization_manifest_ref) is not ArtifactRef:
            raise ValueError("canonicalization_manifest_ref must be ArtifactRef")
        for field_name in (
            "canonicalization_manifest_digest",
            "baseline_canonical_state_digest",
            "modified_canonical_state_digest",
            "storage_projection_ruleset_digest",
        ):
            if type(getattr(self, field_name)) is not DigestRef:
                raise ValueError(f"{field_name} must be DigestRef")
        if (self.initial_canonicalization_manifest_ref is None) != (
            self.initial_canonicalization_manifest_digest is None
        ):
            raise ValueError("INITIAL manifest ref and digest must be supplied together")
        if self.initial_canonicalization_manifest_ref is not None and type(
            self.initial_canonicalization_manifest_ref
        ) is not ArtifactRef:
            raise ValueError("initial_canonicalization_manifest_ref must be ArtifactRef or None")
        if self.initial_canonicalization_manifest_digest is not None and type(
            self.initial_canonicalization_manifest_digest
        ) is not DigestRef:
            raise ValueError("initial_canonicalization_manifest_digest must be DigestRef or None")


@dataclass(frozen=True, slots=True)
class _MaterializedPreviewInputs:
    sides: dict[str, BoundSnapshotInput]
    canonical: _CanonicalPreviewMetadata


@dataclass(frozen=True, slots=True)
class _PreviewIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: PreviewIdentityStatus
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
    comparison_ruleset_digest = _require_non_empty_str(payload_object, "comparison_ruleset_digest")
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
        comparison_ruleset_digest=comparison_ruleset_digest,
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
        if _publish_preview_ruleset_mismatch_if_needed(
            payload=payload,
            operation=operation,
            step=step,
            lease_session=lease_session,
            control=control,
        ):
            return ExecutorAcknowledgment.PUBLISHED
        key = definition.key

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the preview materialize JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            inputs = _materialized_preview_inputs_from_checkpoint(
                envelope.job_state,
                deps.artifact_store,
            )
            materialized_sides_ref = artifact_ref_from_dict(
                cast(dict[str, object], envelope.job_state[_JOB_STATE_MATERIALIZED_SIDES_REF])
            )
            _pin_preview_refs(
                deps,
                (
                    step.checkpoint_ref,
                    materialized_sides_ref,
                    *_closed_refs_from_preview_inputs(inputs),
                ),
                owner_kind="preview-checkpoint",
                owner_id=step.step_id,
                intent="materialize-checkpoint",
            )
        else:
            try:
                inputs = _materialize_all_sides(payload, deps)
            except PreviewJobError as exc:
                if exc.diagnostic_code is None:
                    raise
                _publish_preview_materialization_failure(
                    operation=operation,
                    step=step,
                    lease_session=lease_session,
                    diagnostic_code=exc.diagnostic_code,
                    message=str(exc),
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED
            materialized_sides_ref = put_checkpoint_state_artifact(
                deps.artifact_store,
                {
                    "document_type": PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
                    "contract_version": PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
                    _JOB_STATE_SIDES: _serialize_sides(inputs.sides, payload),
                },
                artifact_id_prefix="preview-materialized-sides",
            )
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_MATERIALIZED_SIDES_REF: artifact_ref_to_dict(
                        materialized_sides_ref
                    ),
                    _JOB_STATE_CANONICAL: _canonical_preview_metadata_to_document(inputs.canonical),
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=checkpoint_ref,
                    extra_refs=(
                        materialized_sides_ref,
                        *_closed_refs_from_preview_inputs(inputs),
                    ),
                    owner_kind="preview-checkpoint",
                    intent="materialize-checkpoint",
                    active_transaction=_active_preview_transaction.get,
                    transaction_missing=lambda: PreviewJobError(
                        "preview checkpoint transaction is not bound"
                    ),
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
        active_rules = _active_preview_ruleset()
        if active_rules.ruleset_digest is None or active_rules.ruleset_digest.value != payload.comparison_ruleset_digest:
            _publish_preview_ruleset_mismatch_failure(
                payload=payload,
                operation=operation,
                step=step,
                lease_session=lease_session,
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED
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
        inputs = _materialized_preview_inputs_from_checkpoint(
            materialize_envelope.job_state,
            deps.artifact_store,
        )

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(assemble_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the preview assemble JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            assemble_state_ref, _assemble_state = _assemble_state_from_checkpoint(
                envelope.job_state,
                deps.artifact_store,
            )
            ready_closure_id = envelope.job_state.get(_JOB_STATE_READY_CLOSURE)
            if type(ready_closure_id) is not str or not ready_closure_id:
                raise CheckpointDecodeError(
                    "assemble checkpoint is missing ready_closure_artifact_id",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            ready_closure_ref_raw = envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
            if type(ready_closure_ref_raw) is not dict:
                raise CheckpointDecodeError(
                    "assemble checkpoint is missing ready_closure_ref",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            ready_closure_ref = artifact_ref_from_dict(ready_closure_ref_raw)
            closure = load_ready_closure(deps.artifact_store, ready_closure_ref)
            _pin_preview_refs(
                deps,
                (
                    step.checkpoint_ref,
                    assemble_state_ref,
                    ready_closure_ref,
                    *closure.artifact_refs(),
                ),
                owner_kind="preview-checkpoint",
                owner_id=step.step_id,
                intent="assemble-checkpoint",
            )
        else:
            assemble_state, bundle_manifest_ref, bundle_digest = _assemble_preview(
                payload,
                inputs.sides,
                inputs.canonical,
                deps.artifact_store,
                lease_session,
                control,
                active_rules,
            )
            ready_refs = _ready_closure_refs_from_assemble(assemble_state, bundle_manifest_ref)
            closure_ref = prepare_ready_closure(
                deps.artifact_store,
                ready_refs,
                operation.job_contract_version,
            )
            assemble_state_ref = put_checkpoint_state_artifact(
                deps.artifact_store,
                {
                    "document_type": PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
                    "contract_version": PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
                    _JOB_STATE_ASSEMBLE: assemble_state,
                },
                artifact_id_prefix="preview-assemble-state",
            )
            envelope = envelope_for_step(
                key=assemble_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_ASSEMBLE_REF: artifact_ref_to_dict(assemble_state_ref),
                    _JOB_STATE_READY_CLOSURE: closure_ref.artifact_id,
                    _JOB_STATE_READY_CLOSURE_REF: artifact_ref_to_dict(closure_ref),
                    _JOB_STATE_BUNDLE_ARTIFACT: bundle_manifest_ref.artifact_id,
                    _JOB_STATE_BUNDLE_DIGEST: bundle_digest,
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=checkpoint_ref,
                    extra_refs=(
                        assemble_state_ref,
                        closure_ref,
                        bundle_manifest_ref,
                        *ready_refs,
                    ),
                    owner_kind="preview-checkpoint",
                    intent="assemble-checkpoint",
                    active_transaction=_active_preview_transaction.get,
                    transaction_missing=lambda: PreviewJobError(
                        "preview checkpoint transaction is not bound"
                    ),
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
        if _publish_preview_ruleset_mismatch_if_needed(
            payload=payload,
            operation=operation,
            step=step,
            lease_session=lease_session,
            control=control,
        ):
            return ExecutorAcknowledgment.PUBLISHED
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
        _assemble_state_ref, assemble_state = _assemble_state_from_checkpoint(
            assemble_envelope.job_state,
            deps.artifact_store,
        )
        ready_closure_id = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE)
        ready_closure_ref_raw = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        bundle_artifact_id = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_ARTIFACT)
        bundle_digest = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_DIGEST)
        if (
            type(ready_closure_id) is not str
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
        load_ready_closure(deps.artifact_store, ready_closure_ref)

        preview_result = _build_preview_result(
            payload=payload,
            operation=operation,
            assemble_state=assemble_state,
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
) -> _MaterializedPreviewInputs:
    runtime_ruleset = migrated_table_ruleset_snapshot()
    if runtime_ruleset.ruleset_digest is None:
        raise PreviewJobError("storage projection ruleset digest is missing")
    canonical_binding = _preview_baseline_binding(payload, deps, runtime_ruleset)
    provider = deps.repository_provider_factory(
        payload.repository_id,
        payload.business_baseline_commit_id,
    )
    baseline = _materialize_baseline(
        payload,
        provider,
        deps.artifact_store,
        canonical_binding=canonical_binding,
        ruleset=runtime_ruleset,
    )
    sides: dict[str, BoundSnapshotInput] = {_SIDE_BASELINE: baseline}
    baseline_state_digest = canonical_state_digest_of(baseline.summary.tables)
    if baseline_state_digest is None:
        raise PreviewJobError("baseline canonical state digest is missing")
    initial_manifest_ref: ArtifactRef | None = None
    initial_manifest_digest: DigestRef | None = None
    if payload.input_completeness is InputCompleteness.FULL:
        initial, initial_manifest_ref, initial_manifest_digest = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.INITIAL],
            deps.artifact_store,
            runtime_ruleset,
        )
        sides[_SIDE_INITIAL] = initial
        sides[_SIDE_MODIFIED], manifest_ref, manifest_digest = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.MODIFIED],
            deps.artifact_store,
            runtime_ruleset,
        )
    else:
        sides[_SIDE_INITIAL] = baseline
        sides[_SIDE_MODIFIED], manifest_ref, manifest_digest = _materialize_uploaded_side(
            payload.source_artifacts[SourceArtifactRole.MODIFIED],
            deps.artifact_store,
            runtime_ruleset,
        )
    modified_state_digest = canonical_state_digest_of(sides[_SIDE_MODIFIED].summary.tables)
    if modified_state_digest is None:
        raise PreviewJobError("modified canonical state digest is missing")
    closure_ref = _publish_canonical_table_set_closure(
        sides[_SIDE_MODIFIED],
        deps.artifact_store,
    )
    return _MaterializedPreviewInputs(
        sides=sides,
        canonical=_CanonicalPreviewMetadata(
            canonical_table_set_closure_ref=closure_ref,
            canonicalization_manifest_ref=manifest_ref,
            canonicalization_manifest_digest=manifest_digest,
            initial_canonicalization_manifest_ref=initial_manifest_ref,
            initial_canonicalization_manifest_digest=initial_manifest_digest,
            baseline_canonical_state_digest=baseline_state_digest,
            modified_canonical_state_digest=modified_state_digest,
            storage_projection_ruleset_digest=runtime_ruleset.ruleset_digest,
        ),
    )


def _materialize_baseline_commit(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
    canonical_binding: CanonicalBinding,
    ruleset: TableRulesetSnapshot,
) -> BoundSnapshotInput:
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=repository_id, ref=commit_id),
        provider=provider,
        ruleset=ruleset,
        canonical_binding=canonical_binding,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
        artifact_store=store,
    )
    result = materialize_repository_ref(request)
    return _bound_from_materialization(
        result,
        label="baseline",
        canonical_binding=canonical_binding,
    )


def _materialize_baseline(
    payload: PreviewJobPayload,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
    *,
    canonical_binding: CanonicalBinding,
    ruleset: TableRulesetSnapshot,
) -> BoundSnapshotInput:
    return _materialize_baseline_commit(
        repository_id=payload.repository_id,
        commit_id=payload.business_baseline_commit_id,
        provider=provider,
        store=store,
        canonical_binding=canonical_binding,
        ruleset=ruleset,
    )


def _preview_baseline_binding(
    payload: PreviewJobPayload,
    deps: PreviewRuntimeDependencies,
    runtime_ruleset: TableRulesetSnapshot,
) -> CanonicalBinding:
    with deps.control_transaction_factory() as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(payload.workspace_id)
        if workspace is None or workspace.repository_id != payload.repository_id:
            raise PreviewJobError("preview workspace scope is unavailable")
        try:
            metadata = unit_of_work.commit_canonical_metadata.resolve(
                repository_id=payload.repository_id,
                commit_id=payload.business_baseline_commit_id,
                scope=CommitCanonicalScope(
                    gateway_device_external_key=workspace.gateway_device_external_key,
                    business_project_id=workspace.business_project_id,
                ),
            )
        except CommitCanonicalMetadataError as exc:
            raise PreviewJobError(
                exc.diagnostic,
                diagnostic_code=exc.code.value,
            ) from exc
    return canonical_binding_for_commit(metadata, runtime_ruleset=runtime_ruleset)


def _materialize_uploaded_side(
    binding: SourceArtifactBinding,
    store: ArtifactStorePort,
    ruleset: TableRulesetSnapshot,
) -> tuple[BoundSnapshotInput, ArtifactRef, DigestRef]:
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
    raw_result = materialize_sql_snapshot(
        _sql_materialization_request(parsed, dump.sql_source_digest, ruleset),
    )
    if raw_result.status is not SnapshotMaterializationStatus.COMPLETE:
        diagnostic = raw_result.diagnostics[0] if raw_result.diagnostics else None
        raise PreviewJobError(
            "uploaded SQL materialization failed",
            diagnostic_code=None if diagnostic is None else diagnostic.code.value,
        )
    if raw_result.snapshot is None or raw_result.table_set is None:
        raise PreviewJobError("uploaded SQL materialization is incomplete")
    projected: CanonicalProjectionResult = project_canonical_table_set(
        raw_result.table_set,
        ruleset,
    )
    if projected.status is not ProjectionStatus.COMPLETE or projected.manifest is None:
        projection_diagnostic = projected.diagnostics[0] if projected.diagnostics else None
        raise PreviewJobError(
            "uploaded canonical projection failed"
            + ("" if projection_diagnostic is None else f": {projection_diagnostic.message}"),
            diagnostic_code=(
                None if projection_diagnostic is None else projection_diagnostic.code.value
            ),
        )
    try:
        canonical_result = materialize_projected_snapshot(
            raw_result.snapshot,
            projected.tables,
            artifact_store=store,
            context=ParserInvocationContext(NeverCancel()),
        )
    finally:
        for table in projected.tables:
            if table.reader is not None:
                table.reader.close()
        for table in raw_result.table_set.tables:
            if table.reader is not None:
                table.reader.close()
    bound = _bound_from_materialization(
        canonical_result,
        label="uploaded canonical",
        storage_facts=_comparison_storage_facts(projected.manifest),
    )
    try:
        manifest_ref = publish_canonicalization_manifest(projected.manifest, store)
    except PublicationError as exc:
        raise PreviewJobError("canonicalization manifest publication failed") from exc
    manifest_digest = projected.manifest.manifest_digest
    if manifest_digest is None:
        raise PreviewJobError("canonicalization manifest digest is missing")
    return bound, manifest_ref, manifest_digest


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
    canonical: _CanonicalPreviewMetadata,
    store: ArtifactStorePort,
    lease_session: LeaseSession,
    control: ExecutionControl,
    rule_set: ComparisonRuleSet,
) -> tuple[dict[str, object], ArtifactRef, str]:
    pair_results: list[_PairPipelineResult] = []
    bundle_pairs: list[BundlePairInput] = []
    if payload.input_completeness is InputCompleteness.FULL:
        pair_specs: tuple[tuple[str, BoundSnapshotInput, BoundSnapshotInput], ...] = (
            (_PAIR_BASELINE_TO_INITIAL, sides[_SIDE_BASELINE], sides[_SIDE_INITIAL]),
            (_PAIR_INITIAL_TO_MODIFIED, sides[_SIDE_INITIAL], sides[_SIDE_MODIFIED]),
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
            ),
        )
        bundle_profile = BundleProfile.SINGLE_PAIR
        bundle_inputs = (
            BundleInput(0, "baseline", "Baseline"),
            BundleInput(1, "modified", "Modified"),
        )
        bundle_indexes = {_PAIR_INITIAL_TO_MODIFIED: (0, 1)}

    for pair_id, before, current in pair_specs:
        lease_session.refresh_control()
        if control.cancel_requested:
            raise PreviewJobError("preview assembly cancelled")
        pair_state = _run_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=control,
            rule_set=rule_set,
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
        canonical=canonical,
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
        _JOB_STATE_CANONICAL: _canonical_preview_metadata_to_document(canonical),
        "required_refs": [artifact_ref_to_dict(item) for item in required_refs],
    }
    return assemble_state, bundle_result.bundle.manifest_ref, bundle_result.bundle.bundle_digest.value


def _run_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: ArtifactStorePort,
    control: ExecutionControl,
    rule_set: ComparisonRuleSet,
) -> _PairPipelineResult:
    try:
        return run_preview_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=control,
            view_id=_PAIR_INITIAL_TO_MODIFIED,
            rule_set=rule_set,
        )
    except PairPipelineError as exc:
        raise PreviewJobError(str(exc)) from exc


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
    canonical_payload = assemble_state.get(_JOB_STATE_CANONICAL)
    if type(canonical_payload) is not dict:
        raise PreviewJobError("assemble checkpoint canonical Preview bindings are missing")
    canonical = _canonical_preview_metadata_from_document(canonical_payload)
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
        canonical=PreviewCanonicalBindings(
            canonical_table_set_closure_ref=_workspace_artifact_ref(
                canonical.canonical_table_set_closure_ref
            ),
            canonical_table_set_closure_digest=canonical.canonical_table_set_closure_ref.raw_sha256,
            canonicalization_manifest_ref=_workspace_artifact_ref(
                canonical.canonicalization_manifest_ref
            ),
            canonicalization_manifest_digest=canonical.canonicalization_manifest_digest,
            baseline_canonical_state_digest=canonical.baseline_canonical_state_digest,
            modified_canonical_state_digest=canonical.modified_canonical_state_digest,
            storage_projection_ruleset_digest=canonical.storage_projection_ruleset_digest,
        ),
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
    canonical: _CanonicalPreviewMetadata,
    pair_results: list[_PairPipelineResult],
    bundle_manifest_ref: ArtifactRef,
) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    refs.extend(
        (
            canonical.canonical_table_set_closure_ref,
            canonical.canonicalization_manifest_ref,
        )
    )
    if canonical.initial_canonicalization_manifest_ref is not None:
        refs.append(canonical.initial_canonicalization_manifest_ref)
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
    return unique_artifact_refs(refs)


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


def _active_preview_ruleset() -> ComparisonRuleSet:
    return comparison_rule_set(migrated_table_ruleset_snapshot())


def _publish_preview_ruleset_mismatch_if_needed(
    *,
    payload: PreviewJobPayload,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> bool:
    active_rules = _active_preview_ruleset()
    if active_rules.ruleset_digest is not None and active_rules.ruleset_digest.value == payload.comparison_ruleset_digest:
        return False
    _publish_preview_ruleset_mismatch_failure(
        payload=payload,
        operation=operation,
        step=step,
        lease_session=lease_session,
        control=control,
    )
    return True


def _publish_preview_ruleset_mismatch_failure(
    *,
    payload: PreviewJobPayload,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> None:
    del payload

    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview ruleset transaction is not bound")
        _release_preview_step_protection(
            transaction,
            operation_id=current_operation.operation_id,
            clear_operation_owner=True,
        )
        diagnostic = OperationDiagnostic(
            code="PREVIEW_RULESET_VERSION_MISMATCH",
            message="frozen comparison ruleset digest does not match runtime ruleset",
        )
        terminal_step = _terminal_step(
            current_step,
            transaction_now,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            current_operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=current_operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    lease_session.publish_operation(builder)


def _publish_preview_materialization_failure(
    *,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    diagnostic_code: str,
    message: str,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview materialization transaction is not bound")
        _release_preview_step_protection(
            transaction,
            operation_id=current_operation.operation_id,
            clear_operation_owner=True,
        )
        diagnostic = OperationDiagnostic(
            code=diagnostic_code,
            message=message[:255],
        )
        terminal_step = _terminal_step(
            current_step,
            transaction_now,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            current_operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=current_operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    lease_session.publish_operation(builder)


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


def _closed_refs_from_preview_inputs(
    inputs: _MaterializedPreviewInputs,
) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for bound in inputs.sides.values():
        refs.extend(_side_input_refs(bound))
    refs.extend(
        (
            inputs.canonical.canonical_table_set_closure_ref,
            inputs.canonical.canonicalization_manifest_ref,
        )
    )
    if inputs.canonical.initial_canonicalization_manifest_ref is not None:
        refs.append(inputs.canonical.initial_canonicalization_manifest_ref)
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
        "snapshot": snapshot_to_document(bound.snapshot),
        "source_ref": source_ref,
        "repository_identity": repository_identity,
        "snapshot_digest": bound.snapshot.snapshot_digest.value,
        "raw_state_digest": bound.snapshot.raw_state_digest.value,
        "summary": snapshot_summary_to_document(bound.summary),
        "storage_facts": _storage_facts_to_documents(bound.storage_facts),
        "tables": tables,
    }


def _materialized_preview_inputs_from_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
) -> _MaterializedPreviewInputs:
    if set(job_state) != {_JOB_STATE_MATERIALIZED_SIDES_REF, _JOB_STATE_CANONICAL}:
        raise CheckpointDecodeError(
            "materialize checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    sides_ref_raw = job_state.get(_JOB_STATE_MATERIALIZED_SIDES_REF)
    if type(sides_ref_raw) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint sides ref is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        sides_ref = artifact_ref_from_dict(sides_ref_raw)
        sides_document = load_checkpoint_state_artifact(
            store,
            sides_ref,
            document_type=PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
            contract_version=PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
        )
    except (TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, CheckpointDecodeError):
            raise
        raise CheckpointDecodeError(
            "materialize checkpoint sides artifact ref is invalid",
            code="CHECKPOINT_REF_INVALID",
        ) from exc
    if set(sides_document) != {"document_type", "contract_version", _JOB_STATE_SIDES}:
        raise CheckpointDecodeError(
            "materialized sides artifact fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    raw_sides = sides_document.get(_JOB_STATE_SIDES)
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
    canonical_raw = job_state.get(_JOB_STATE_CANONICAL)
    if type(canonical_raw) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint canonical bindings are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    canonical = _canonical_preview_metadata_from_document(canonical_raw)
    try:
        closure_bytes = store.locate(canonical.canonical_table_set_closure_ref)
        manifest = open_canonicalization_manifest(
            store,
            canonical.canonicalization_manifest_ref,
        )
        initial_manifest = (
            None
            if canonical.initial_canonicalization_manifest_ref is None
            else open_canonicalization_manifest(
                store,
                canonical.initial_canonicalization_manifest_ref,
            )
        )
    except (ManifestVerificationError, PublicationError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint canonical artifacts are unreadable",
            code="CHECKPOINT_REF_UNREADABLE",
        ) from exc
    expected_closure = _canonical_table_set_closure_bytes(sides[_SIDE_MODIFIED])
    if closure_bytes != expected_closure:
        raise CheckpointDecodeError(
            "materialize checkpoint canonical table closure does not match MODIFIED",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if (
        manifest.manifest_digest != canonical.canonicalization_manifest_digest
        or manifest.ruleset_digest != canonical.storage_projection_ruleset_digest
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint canonical manifest binding does not match",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    modified_facts = _comparison_storage_facts(manifest)
    if sides[_SIDE_MODIFIED].storage_facts != modified_facts:
        raise CheckpointDecodeError(
            "materialize checkpoint MODIFIED storage facts do not match its manifest",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    initial_reuses_baseline = raw_sides.get("initial_reuses_baseline") is True
    if initial_reuses_baseline:
        if initial_manifest is not None:
            raise CheckpointDecodeError(
                "MODIFIED_ONLY checkpoint must not include an INITIAL manifest",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
    elif initial_manifest is None:
        raise CheckpointDecodeError(
            "FULL checkpoint is missing the INITIAL canonical manifest",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    else:
        if (
            initial_manifest.manifest_digest != canonical.initial_canonicalization_manifest_digest
            or initial_manifest.ruleset_digest != canonical.storage_projection_ruleset_digest
            or sides[_SIDE_INITIAL].storage_facts != _comparison_storage_facts(initial_manifest)
        ):
            raise CheckpointDecodeError(
                "materialize checkpoint INITIAL storage facts do not match its manifest",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
    baseline_digest = canonical_state_digest_of(sides[_SIDE_BASELINE].summary.tables)
    modified_digest = canonical_state_digest_of(sides[_SIDE_MODIFIED].summary.tables)
    if (
        baseline_digest != canonical.baseline_canonical_state_digest
        or modified_digest != canonical.modified_canonical_state_digest
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint canonical state digest does not match its tables",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return _MaterializedPreviewInputs(sides=sides, canonical=canonical)


def _assemble_state_from_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
) -> tuple[ArtifactRef, dict[str, object]]:
    expected_fields = {
        _JOB_STATE_ASSEMBLE_REF,
        _JOB_STATE_READY_CLOSURE,
        _JOB_STATE_READY_CLOSURE_REF,
        _JOB_STATE_BUNDLE_ARTIFACT,
        _JOB_STATE_BUNDLE_DIGEST,
    }
    if set(job_state) != expected_fields:
        raise CheckpointDecodeError(
            "preview assemble checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    raw_ref = job_state.get(_JOB_STATE_ASSEMBLE_REF)
    if type(raw_ref) is not dict:
        raise CheckpointDecodeError(
            "preview assemble state ref is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        assemble_state_ref = artifact_ref_from_dict(raw_ref)
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "preview assemble state ref is invalid",
            code="CHECKPOINT_REF_INVALID",
        ) from exc
    document = load_checkpoint_state_artifact(
        store,
        assemble_state_ref,
        document_type=PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
        contract_version=PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
    )
    if set(document) != {"document_type", "contract_version", _JOB_STATE_ASSEMBLE}:
        raise CheckpointDecodeError(
            "preview assemble state artifact fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    assemble_state = document.get(_JOB_STATE_ASSEMBLE)
    if type(assemble_state) is not dict:
        raise CheckpointDecodeError(
            "preview assemble state artifact is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return assemble_state_ref, cast(dict[str, object], assemble_state)


def _bound_from_side_document(entry: dict[str, object], store: ArtifactStorePort) -> BoundSnapshotInput:
    if entry.get("contract_version") != PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION:
        raise CheckpointDecodeError(
            "materialize checkpoint side contract version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    tables_raw = entry.get("tables")
    if type(tables_raw) is not list:
        raise CheckpointDecodeError(
            "materialize checkpoint table refs must be a list",
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
    try:
        snapshot = snapshot_from_document(entry.get("snapshot"))
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint snapshot is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    if snapshot.snapshot_digest.value != str(entry.get("snapshot_digest")):
        raise CheckpointDecodeError(
            "materialize checkpoint digest mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        summary = snapshot_summary_from_document(
            entry.get("summary"),
            snapshot=snapshot,
            tables=tuple(table.descriptor for table in opened),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint summary does not match its snapshot and tables",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    table_set = SnapshotTableSet(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        table_ruleset_version=snapshot.table_ruleset_version,
        tables=tuple(opened),
    )
    try:
        storage_facts = _storage_facts_from_documents(entry.get("storage_facts"))
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    return BoundSnapshotInput(snapshot, summary, table_set, storage_facts)


def _bound_from_materialization(
    result: SnapshotMaterializationResult,
    *,
    label: str,
    canonical_binding: CanonicalBinding | None = None,
    storage_facts: tuple[ComparisonStorageFacts, ...] = (),
) -> BoundSnapshotInput:
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        diagnostic = result.diagnostics[0] if result.diagnostics else None
        raise PreviewJobError(
            f"{label} materialization failed",
            diagnostic_code=None if diagnostic is None else diagnostic.code.value,
        )
    if result.snapshot is None or result.summary is None:
        raise PreviewJobError(f"{label} materialization is incomplete")
    if canonical_binding is not None:
        descriptors = {item.table_name: item for item in result.summary.tables}
        storage_facts = tuple(
            ComparisonStorageFacts(
                storage_rule_view=view,
                source_schema_digest=descriptors[view.canonical_table].business_schema_digest,
            )
            for view in canonical_binding.tables
            if view.canonical_table in descriptors
        )
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set, storage_facts)


def _comparison_storage_facts(
    manifest: CanonicalizationManifest,
) -> tuple[ComparisonStorageFacts, ...]:
    facts: list[ComparisonStorageFacts] = []
    for table in manifest.tables:
        if table.source_schema_digest is None:
            raise PreviewJobError("canonical manifest is missing source schema facts")
        view = StorageRuleView(
            canonical_table=table.name,
            canonical_key_policy=table.canonical_key_policy,
            ordered_policy=table.ordered_policy,
            dropped_columns=table.dropped_columns,
            structural_columns=table.structural_columns,
            retained_columns=table.retained_columns,
            canonical_key_columns=(
                table.canonical_key_columns
                if table.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
                else ()
            ),
        )
        facts.append(
            ComparisonStorageFacts(
                storage_rule_view=view,
                source_schema_digest=table.source_schema_digest,
            )
        )
    return tuple(facts)


def _publish_canonical_table_set_closure(
    bound: BoundSnapshotInput,
    store: ArtifactStorePort,
) -> ArtifactRef:
    raw_bytes = _canonical_table_set_closure_bytes(bound)
    return put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=build_artifact_id("canonical-table-set-closure", uuid.uuid4().hex),
        media_type=_JCS_MEDIA_TYPE,
    )


def _canonical_table_set_closure_bytes(bound: BoundSnapshotInput) -> bytes:
    if bound.table_set is None:
        raise PreviewJobError("canonical table set is missing")
    tables: list[dict[str, object]] = []
    for table in sorted(
        bound.table_set.tables,
        key=lambda item: item.descriptor.table_name.encode("utf-8"),
    ):
        if table.artifact is None:
            raise PreviewJobError(
                f"canonical table {table.descriptor.table_name} is missing artifact refs"
            )
        tables.append(
            {
                "table_name": table.descriptor.table_name,
                "manifest_ref": artifact_ref_to_dict(table.artifact.manifest_ref),
            }
        )
    payload = {
        "contract_version": _CANONICAL_TABLE_CLOSURE_CONTRACT,
        "tables": tables,
    }
    return canonicalize_jcs(canonicalize_json_value(payload))


def _canonical_preview_metadata_to_document(
    canonical: _CanonicalPreviewMetadata,
) -> dict[str, object]:
    return {
        "canonical_table_set_closure_ref": artifact_ref_to_dict(
            canonical.canonical_table_set_closure_ref
        ),
        "canonicalization_manifest_ref": artifact_ref_to_dict(
            canonical.canonicalization_manifest_ref
        ),
        "canonicalization_manifest_digest": canonical.canonicalization_manifest_digest.value,
        "initial_canonicalization_manifest_ref": (
            None
            if canonical.initial_canonicalization_manifest_ref is None
            else artifact_ref_to_dict(canonical.initial_canonicalization_manifest_ref)
        ),
        "initial_canonicalization_manifest_digest": (
            None
            if canonical.initial_canonicalization_manifest_digest is None
            else canonical.initial_canonicalization_manifest_digest.value
        ),
        "baseline_canonical_state_digest": canonical.baseline_canonical_state_digest.value,
        "modified_canonical_state_digest": canonical.modified_canonical_state_digest.value,
        "storage_projection_ruleset_digest": canonical.storage_projection_ruleset_digest.value,
    }


def _canonical_preview_metadata_from_document(
    raw: dict[str, object],
) -> _CanonicalPreviewMetadata:
    expected_keys = {
        "canonical_table_set_closure_ref",
        "canonicalization_manifest_ref",
        "canonicalization_manifest_digest",
        "initial_canonicalization_manifest_ref",
        "initial_canonicalization_manifest_digest",
        "baseline_canonical_state_digest",
        "modified_canonical_state_digest",
        "storage_projection_ruleset_digest",
    }
    if set(raw) != expected_keys:
        raise CheckpointDecodeError(
            "canonical preview checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    closure_ref = raw["canonical_table_set_closure_ref"]
    manifest_ref = raw["canonicalization_manifest_ref"]
    initial_manifest_ref = raw["initial_canonicalization_manifest_ref"]
    initial_manifest_digest = raw["initial_canonicalization_manifest_digest"]
    if (
        type(closure_ref) is not dict
        or type(manifest_ref) is not dict
        or (initial_manifest_ref is not None and type(initial_manifest_ref) is not dict)
        or (initial_manifest_digest is not None and type(initial_manifest_digest) is not str)
    ):
        raise CheckpointDecodeError(
            "canonical preview checkpoint artifact refs are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        return _CanonicalPreviewMetadata(
            canonical_table_set_closure_ref=artifact_ref_from_dict(closure_ref),
            canonicalization_manifest_ref=artifact_ref_from_dict(manifest_ref),
            canonicalization_manifest_digest=DigestRef(
                _checkpoint_string(raw, "canonicalization_manifest_digest")
            ),
            initial_canonicalization_manifest_ref=(
                None
                if initial_manifest_ref is None
                else artifact_ref_from_dict(initial_manifest_ref)
            ),
            initial_canonicalization_manifest_digest=(
                None
                if initial_manifest_digest is None
                else DigestRef(initial_manifest_digest)
            ),
            baseline_canonical_state_digest=DigestRef(
                _checkpoint_string(raw, "baseline_canonical_state_digest")
            ),
            modified_canonical_state_digest=DigestRef(
                _checkpoint_string(raw, "modified_canonical_state_digest")
            ),
            storage_projection_ruleset_digest=DigestRef(
                _checkpoint_string(raw, "storage_projection_ruleset_digest")
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckpointDecodeError(
            "canonical preview checkpoint bindings are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc


def _storage_facts_to_documents(
    facts: tuple[ComparisonStorageFacts, ...],
) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for fact in facts:
        view = fact.storage_rule_view
        documents.append(
            {
                "canonical_table": view.canonical_table,
                "source_schema_digest": fact.source_schema_digest.value,
                "canonical_key_policy": view.canonical_key_policy.value,
                "ordered_policy": view.ordered_policy.value,
                "dropped_columns": [
                    {"name": item.name, "reason": item.reason}
                    for item in view.dropped_columns
                ],
                "structural_columns": list(view.structural_columns),
                "retained_columns": list(view.retained_columns),
                "canonical_key_columns": list(view.canonical_key_columns),
                "storage_rule_digest": (
                    None if view.storage_rule_digest is None else view.storage_rule_digest.value
                ),
            }
        )
    return documents


def _storage_facts_from_documents(raw: object) -> tuple[ComparisonStorageFacts, ...]:
    if type(raw) is not list:
        raise ValueError("storage_facts must be a list")
    facts: list[ComparisonStorageFacts] = []
    expected_keys = {
        "canonical_table",
        "source_schema_digest",
        "canonical_key_policy",
        "ordered_policy",
        "dropped_columns",
        "structural_columns",
        "retained_columns",
        "canonical_key_columns",
        "storage_rule_digest",
    }
    for item in raw:
        if type(item) is not dict or set(item) != expected_keys:
            raise ValueError("storage fact document fields are invalid")
        dropped_raw = item["dropped_columns"]
        if type(dropped_raw) is not list:
            raise ValueError("dropped_columns must be a list")
        dropped: list[DroppedColumn] = []
        for dropped_item in dropped_raw:
            if type(dropped_item) is not dict or set(dropped_item) != {"name", "reason"}:
                raise ValueError("dropped column fields are invalid")
            dropped.append(
                DroppedColumn(
                    name=_document_string(dropped_item, "name"),
                    reason=_document_string(dropped_item, "reason"),
                )
            )
        canonical_table = _document_string(item, "canonical_table")
        key_policy = CanonicalKeyPolicy(_document_string(item, "canonical_key_policy"))
        ordered_policy = OrderedPolicy(_document_string(item, "ordered_policy"))
        storage_rule_digest_raw = item["storage_rule_digest"]
        if storage_rule_digest_raw is not None and type(storage_rule_digest_raw) is not str:
            raise ValueError("storage_rule_digest must be a string or null")
        view = StorageRuleView(
            canonical_table=canonical_table,
            canonical_key_policy=key_policy,
            ordered_policy=ordered_policy,
            dropped_columns=tuple(dropped),
            structural_columns=_document_string_tuple(item, "structural_columns"),
            retained_columns=_document_string_tuple(item, "retained_columns"),
            canonical_key_columns=_document_string_tuple(item, "canonical_key_columns"),
            storage_rule_digest=(
                None
                if storage_rule_digest_raw is None
                else DigestRef(storage_rule_digest_raw)
            ),
        )
        facts.append(
            ComparisonStorageFacts(
                storage_rule_view=view,
                source_schema_digest=DigestRef(
                    _document_string(item, "source_schema_digest")
                ),
            )
        )
    return tuple(facts)


def _document_string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _document_string_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    value = raw[key]
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"{key} must be a string list")
    return tuple(value)


def _checkpoint_string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _workspace_artifact_ref(ref: ArtifactRef) -> PreviewArtifactRef:
    return PreviewArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256,
    )


def _runtime_binding_from_provider(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    ruleset: TableRulesetSnapshot,
) -> CanonicalBinding:
    if ruleset.ruleset_digest is None:
        raise PreviewJobError("runtime ruleset digest is missing")
    session = provider.open_ref(RepositoryRef(repository_id=repository_id, ref=commit_id), None)
    try:
        catalog = session.get_catalog()
        if catalog.resolved_commit_hash != session.pinned_commit_hash():
            raise PreviewJobError("Repository catalog is not pinned to the requested commit")
        views: list[StorageRuleView] = []
        for table in catalog.tables:
            resolved = resolve_table_rule(
                ruleset,
                table.table_name,
                primary_key_columns=table.primary_key_columns,
            )
            record = resolved.record
            explicit_key = (
                record.compare_key_columns
                if record.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
                else ()
            )
            views.append(
                StorageRuleView(
                    canonical_table=resolved.canonical_table,
                    canonical_key_policy=record.canonical_key_policy,
                    ordered_policy=record.ordered_policy,
                    dropped_columns=record.dropped_columns,
                    structural_columns=record.structural_columns,
                    canonical_key_columns=explicit_key,
                )
            )
    finally:
        session.close()
    return CanonicalBinding(
        storage_projection_version=ruleset.storage_projection_version,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest,
        tables=tuple(sorted(views, key=lambda item: item.canonical_table.encode("utf-8"))),
    )


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
    ruleset: TableRulesetSnapshot,
) -> SqlSnapshotMaterializationRequest:
    return SqlSnapshotMaterializationRequest(
        parse_result=parsed,
        sql_source_digest=digest,
        ruleset=ruleset,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.READERS_REQUIRED,
        context=ParserInvocationContext(NeverCancel()),
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


def _terminal_step(
    step: StepRecord,
    transaction_now: datetime,
    *,
    status: StepStatus,
    diagnostic: OperationDiagnostic | None = None,
) -> StepRecord:
    return dataclasses.replace(
        step,
        status=status,
        diagnostic=diagnostic,
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


_PREVIEW_STEP_SUFFIX: dict[str, str] = {
    PREVIEW_STEP_MATERIALIZE: "1",
    PREVIEW_STEP_ASSEMBLE: "2",
    PREVIEW_STEP_PUBLISH: "3",
}


def _successor_step_id(operation_id: str, step_name: str) -> str:
    from gateway_backend.application.job_steps import successor_step_id

    return successor_step_id(operation_id, step_name, _PREVIEW_STEP_SUFFIX)


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
        "comparison_ruleset_digest",
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
    "decode_preview_payload",
    "surface_artifact_closure",
    "preview_composition_bundle",
    "preview_job_definitions",
    "preview_payload_decoders",
]
