"""History compare JobDefinition, decoder, and fixed three-step handler topology."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import ContextManager, cast

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
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HistoryCompareDiagnosticCode,
    HistoryCompareNodeBinding,
)
from gateway_backend.application.history.ports import (
    HistoryControlTransaction as HistoryCompareControlTransaction,
)
from gateway_backend.application.job_steps import pinned_checkpoint_builder, unique_artifact_refs
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.application.pair_pipeline import (
    HistoryPairPipelineResult as _PairPipelineResult,
    PairPipelineCancelled,
    PairPipelineError,
    run_history_pair_pipeline,
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
from gateway_backend.application.preview_jobs import (
    _document_string,
    _snapshot_descriptor_from_document,
    _snapshot_descriptor_to_document,
    _storage_facts_from_documents,
    _storage_facts_to_documents,
    surface_artifact_closure,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    assemble_bundle,
)
from gateway_backend.capabilities.comparison import BoundSnapshotInput, ComparisonStorageFacts
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.capabilities.snapshot_materialization import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryProviderError,
    RepositoryTableAccessProvider,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotTableSet,
    snapshot_from_document,
    snapshot_summary_from_document,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.snapshot_materialization import (
    materialize_repository_ref,
)
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
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
from gateway_backend.operations.recovery import HandlerExecutionFailure
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
)

HISTORY_COMPARE_STEP_MATERIALIZE = "materialize_inputs"
HISTORY_COMPARE_STEP_ASSEMBLE = "assemble_comparison"
HISTORY_COMPARE_STEP_PUBLISH = "publish_result"

HISTORY_COMPARE_MATERIALIZE_DECODER = "backend-vnext/history-compare/materialize/decoder/v1"
HISTORY_COMPARE_ASSEMBLE_DECODER = "backend-vnext/history-compare/assemble/decoder/v1"
HISTORY_COMPARE_PUBLISH_DECODER = "backend-vnext/history-compare/publish/decoder/v1"
HISTORY_COMPARE_MATERIALIZE_HANDLER = "backend-vnext/history-compare/materialize/handler/v1"
HISTORY_COMPARE_ASSEMBLE_HANDLER = "backend-vnext/history-compare/assemble/handler/v1"
HISTORY_COMPARE_PUBLISH_HANDLER = "backend-vnext/history-compare/publish/handler/v1"

HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION = "backend-vnext/history-compare/materialize-side/v4"

_JOB_STATE_SIDES = "sides"
_JOB_STATE_MATERIALIZED_SIDES_REF = "materialized_sides_ref"
_JOB_STATE_ASSEMBLE = "assemble_state"
_JOB_STATE_ASSEMBLE_REF = "assemble_state_ref"
_JOB_STATE_READY_CLOSURE = "ready_closure_artifact_id"
_JOB_STATE_READY_CLOSURE_REF = "ready_closure_ref"
_JOB_STATE_BUNDLE_ARTIFACT = "bundle_artifact_id"
_JOB_STATE_BUNDLE_DIGEST = "bundle_digest"
HISTORY_COMPARE_MATERIALIZED_SIDES_DOCUMENT_TYPE = "history-compare-materialized-sides"
HISTORY_COMPARE_MATERIALIZED_SIDES_CONTRACT_VERSION = (
    "backend-vnext/history-compare/materialized-sides/v1"
)
HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE = "history-compare-assemble-state"
HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION = (
    "backend-vnext/history-compare/assemble-state/v1"
)

_active_history_compare_transaction: ContextVar[HistoryCompareControlTransaction | None] = ContextVar(
    "_active_history_compare_transaction",
    default=None,
)


class HistoryCompareJobError(ValueError):
    """Bounded history compare job failure surfaced to the operation runtime."""

    def __init__(self, message: str, *, diagnostic_code: str | None = None) -> None:
        super().__init__(message)
        self.diagnostic_code = diagnostic_code


class HistoryCompareRulesetVersionMismatch(HistoryCompareJobError):
    """Raised when frozen compare ruleset version does not match runtime."""


@dataclass(frozen=True, slots=True)
class HistoryCompareJobPayload:
    gateway_device_external_key: str
    business_project_id: str
    repository_id: str
    acceptance_id: str
    idempotency_key: str
    request_fingerprint: str
    comparison_ruleset_digest: str
    comparison_contract_version: str
    view_kind: str
    pair_count: int
    nodes: tuple[HistoryCompareNodeBinding, ...]


HistoryCompareControlTransactionFactory = Callable[[], ContextManager[HistoryCompareControlTransaction]]
RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]


@dataclass(frozen=True, slots=True)
class HistoryCompareRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    control_transaction_factory: HistoryCompareControlTransactionFactory
    snapshot_export_cache: SnapshotTableExportCachePort | None = None


def history_compare_job_definitions() -> tuple[JobDefinition, ...]:
    return (
        history_compare_materialize_job_definition(),
        history_compare_assemble_job_definition(),
        history_compare_publish_job_definition(),
    )


def history_compare_materialize_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_MATERIALIZE),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_MATERIALIZE_DECODER,
        handler_identity=HISTORY_COMPARE_MATERIALIZE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def history_compare_assemble_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_ASSEMBLE),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_ASSEMBLE_DECODER,
        handler_identity=HISTORY_COMPARE_ASSEMBLE_HANDLER,
        publication_capability=NormalPublicationCapability.SINGLE_SUCCESSOR,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def history_compare_publish_job_definition() -> JobDefinition:
    return JobDefinition(
        key=JobStepKey(job_kind=HISTORY_COMPARE_JOB_KIND, step_name=HISTORY_COMPARE_STEP_PUBLISH),
        supported_payload_versions=frozenset({HISTORY_COMPARE_JOB_CONTRACT_VERSION}),
        decoder_identity=HISTORY_COMPARE_PUBLISH_DECODER,
        handler_identity=HISTORY_COMPARE_PUBLISH_HANDLER,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def decode_history_compare_payload(payload_object: dict[str, object]) -> HistoryCompareJobPayload:
    gateway_device_external_key = _require_non_empty_str(payload_object, "gateway_device_external_key")
    business_project_id = _require_non_empty_str(payload_object, "business_project_id")
    repository_id = _require_non_empty_str(payload_object, "repository_id")
    acceptance_id = _require_non_empty_str(payload_object, "acceptance_id")
    idempotency_key = _require_non_empty_str(payload_object, "idempotency_key")
    request_fingerprint = _require_non_empty_str(payload_object, "request_fingerprint")
    comparison_ruleset_digest = _require_non_empty_str(payload_object, "comparison_ruleset_digest")
    comparison_contract_version = _require_non_empty_str(payload_object, "comparison_contract_version")
    view_kind = _require_non_empty_str(payload_object, "view_kind")
    pair_count = _require_positive_int(payload_object, "pair_count")
    nodes = _decode_nodes(payload_object.get("nodes"))
    return HistoryCompareJobPayload(
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
        repository_id=repository_id,
        acceptance_id=acceptance_id,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        comparison_ruleset_digest=comparison_ruleset_digest,
        comparison_contract_version=comparison_contract_version,
        view_kind=view_kind,
        pair_count=pair_count,
        nodes=nodes,
    )


def history_compare_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_history_compare_payload
    return {
        HISTORY_COMPARE_MATERIALIZE_DECODER: decoder,
        HISTORY_COMPARE_ASSEMBLE_DECODER: decoder,
        HISTORY_COMPARE_PUBLISH_DECODER: decoder,
    }


def bind_history_compare_transaction_factory(
    inner: HistoryCompareControlTransactionFactory,
) -> HistoryCompareControlTransactionFactory:
    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[HistoryCompareControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> HistoryCompareControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_history_compare_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_history_compare_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[HistoryCompareControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory


def history_compare_composition_bundle(
    deps: HistoryCompareRuntimeDependencies,
) -> tuple[
    tuple[JobDefinition, ...],
    Mapping[str, ClaimedExecutor],
    Mapping[str, PayloadDecoder],
    HistoryCompareRuntimeDependencies,
]:
    bound_deps = HistoryCompareRuntimeDependencies(
        artifact_store=deps.artifact_store,
        repository_provider_factory=deps.repository_provider_factory,
        control_transaction_factory=bind_history_compare_transaction_factory(
            deps.control_transaction_factory
        ),
        snapshot_export_cache=deps.snapshot_export_cache,
    )
    return (
        history_compare_job_definitions(),
        {
            HISTORY_COMPARE_MATERIALIZE_HANDLER: build_materialize_inputs_handler(bound_deps),
            HISTORY_COMPARE_ASSEMBLE_HANDLER: build_assemble_comparison_handler(bound_deps),
            HISTORY_COMPARE_PUBLISH_HANDLER: build_publish_result_handler(bound_deps),
        },
        dict(history_compare_payload_decoders()),
        bound_deps,
    )


def build_materialize_inputs_handler(deps: HistoryCompareRuntimeDependencies) -> ClaimedExecutor:
    definition = history_compare_materialize_job_definition()

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

        payload = _load_history_compare_payload(operation, deps.artifact_store)
        try:
            _assert_runtime_ruleset(payload)
        except HistoryCompareRulesetVersionMismatch as exc:
            _publish_ruleset_mismatch_failure(
                lease_session=lease_session,
                operation=operation,
                step=step,
                message=str(exc),
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED
        key = definition.key

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the history compare materialize JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            sides = _sides_from_materialize_checkpoint(
                envelope.job_state,
                deps.artifact_store,
            )
            sides_ref = _materialized_sides_ref_from_checkpoint(envelope.job_state)
            _pin_history_compare_refs(
                deps,
                (step.checkpoint_ref, sides_ref, *_closed_refs_from_sides(sides)),
                owner_kind="history-compare-checkpoint",
                owner_id=step.step_id,
                intent="materialize-checkpoint",
            )
        else:
            try:
                sides = _materialize_distinct_commits(payload, deps)
            except HistoryCompareRulesetVersionMismatch as exc:
                _publish_ruleset_mismatch_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=str(exc),
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED
            except RepositoryProviderError as exc:
                assert exc.retryable, "repository_ref must return deterministic provider errors as diagnostics"
                raise HandlerExecutionFailure(
                    retryable=True,
                    diagnostic_code=f"repository.{exc.code.value.lower()}",
                    reason=exc.message,
                ) from exc
            except HistoryCompareJobError as exc:
                _publish_commit_unavailable_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=str(exc),
                    diagnostic_code=exc.diagnostic_code,
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED

            sides_ref = put_checkpoint_state_artifact(
                deps.artifact_store,
                {
                    "document_type": HISTORY_COMPARE_MATERIALIZED_SIDES_DOCUMENT_TYPE,
                    "contract_version": HISTORY_COMPARE_MATERIALIZED_SIDES_CONTRACT_VERSION,
                    _JOB_STATE_SIDES: _serialize_sides(sides),
                },
                artifact_id_prefix="history-compare-materialized-sides",
            )
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_MATERIALIZED_SIDES_REF: artifact_ref_to_dict(sides_ref),
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=checkpoint_ref,
                    extra_refs=(sides_ref, *_closed_refs_from_sides(sides)),
                    owner_kind="history-compare-checkpoint",
                    intent="materialize-checkpoint",
                    active_transaction=_active_history_compare_transaction.get,
                    transaction_missing=lambda: HistoryCompareJobError(
                        "history compare checkpoint transaction is not bound"
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
                successor_step_name=HISTORY_COMPARE_STEP_ASSEMBLE,
                successor_step_id=history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def build_assemble_comparison_handler(deps: HistoryCompareRuntimeDependencies) -> ClaimedExecutor:
    materialize_definition = history_compare_materialize_job_definition()
    assemble_definition = history_compare_assemble_job_definition()

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

        payload = _load_history_compare_payload(operation, deps.artifact_store)
        try:
            rule_set = _assert_runtime_ruleset(payload)
        except HistoryCompareRulesetVersionMismatch as exc:
            _publish_ruleset_mismatch_failure(
                lease_session=lease_session,
                operation=operation,
                step=step,
                message=str(exc),
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED
        materialize_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE),
        )
        if materialize_step.checkpoint_ref is None:
            raise HistoryCompareJobError("materialize checkpoint is missing")
        materialize_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            materialize_step.checkpoint_ref,
        )
        if not definition_matches_checkpoint(materialize_definition, materialize_envelope):
            raise CheckpointDecodeError(
                "materialize checkpoint does not match the history compare JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        sides = _sides_from_materialize_checkpoint(materialize_envelope.job_state, deps.artifact_store)

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(assemble_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the history compare assemble JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            assemble_state_ref, _assemble_state = history_compare_assemble_state_from_checkpoint(
                envelope.job_state,
                deps.artifact_store,
            )
            ready_closure_ref_raw = envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
            if type(ready_closure_ref_raw) is not dict:
                raise CheckpointDecodeError(
                    "history compare assemble checkpoint is missing ready_closure_ref",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            ready_closure_ref = artifact_ref_from_dict(ready_closure_ref_raw)
            closure = load_ready_closure(deps.artifact_store, ready_closure_ref)
            _pin_history_compare_refs(
                deps,
                (
                    step.checkpoint_ref,
                    assemble_state_ref,
                    ready_closure_ref,
                    *closure.artifact_refs(),
                ),
                owner_kind="history-compare-checkpoint",
                owner_id=step.step_id,
                intent="assemble-checkpoint",
            )
        else:
            def publish_cancelled() -> None:
                lease_session.publish_operation(_make_cancelled_terminal_builder())

            try:
                assemble_state, bundle_manifest_ref, bundle_digest = _assemble_comparison(
                    payload=payload,
                    operation_id=operation.operation_id,
                    sides=sides,
                    rule_set=rule_set,
                    store=deps.artifact_store,
                    lease_session=lease_session,
                    control=control,
                    on_cancel=publish_cancelled,
                )
            except PairPipelineCancelled:
                return ExecutorAcknowledgment.PUBLISHED
            ready_refs = _ready_closure_refs_from_assemble(assemble_state, bundle_manifest_ref)
            closure_ref = prepare_ready_closure(
                deps.artifact_store,
                ready_refs,
                operation.job_contract_version,
            )
            assemble_state_ref = put_checkpoint_state_artifact(
                deps.artifact_store,
                {
                    "document_type": HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
                    "contract_version": HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
                    _JOB_STATE_ASSEMBLE: assemble_state,
                },
                artifact_id_prefix="history-compare-assemble-state",
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
                    owner_kind="history-compare-checkpoint",
                    intent="assemble-checkpoint",
                    active_transaction=_active_history_compare_transaction.get,
                    transaction_missing=lambda: HistoryCompareJobError(
                        "history compare checkpoint transaction is not bound"
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
                successor_step_name=HISTORY_COMPARE_STEP_PUBLISH,
                successor_step_id=history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_PUBLISH),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def build_publish_result_handler(deps: HistoryCompareRuntimeDependencies) -> ClaimedExecutor:
    assemble_definition = history_compare_assemble_job_definition()

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

        payload = _load_history_compare_payload(operation, deps.artifact_store)
        try:
            _assert_runtime_ruleset(payload)
        except HistoryCompareRulesetVersionMismatch as exc:
            _publish_ruleset_mismatch_failure(
                lease_session=lease_session,
                operation=operation,
                step=step,
                message=str(exc),
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED

        assemble_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE),
        )
        if assemble_step.checkpoint_ref is None:
            raise HistoryCompareJobError("assemble checkpoint is missing")
        assemble_checkpoint_ref: ArtifactRef = assemble_step.checkpoint_ref
        assemble_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            assemble_checkpoint_ref,
        )
        if not definition_matches_checkpoint(assemble_definition, assemble_envelope):
            raise CheckpointDecodeError(
                "assemble checkpoint does not match the history compare JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        ready_closure_ref_raw = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        if type(ready_closure_ref_raw) is not dict:
            raise CheckpointDecodeError(
                "assemble checkpoint is incomplete for history compare publication",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        ready_closure_ref = artifact_ref_from_dict(ready_closure_ref_raw)
        try:
            deps.artifact_store.locate(ready_closure_ref)
        except ManifestVerificationError as exc:
            raise CheckpointDecodeError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc

        def builder(
            current_operation: OperationRecord,
            current_step: StepRecord,
            transaction_now: datetime,
        ) -> tuple[StepRecord, OperationRecord]:
            transaction = _active_history_compare_transaction.get()
            if transaction is None:
                raise HistoryCompareJobError("history compare publication transaction is not bound")
            closure_output_refs = load_ready_closure(
                deps.artifact_store,
                ready_closure_ref,
            ).artifact_refs()
            _release_history_compare_step_protection(
                transaction,
                operation_id=current_operation.operation_id,
            )
            terminal_step = _terminal_step(current_step, transaction_now, status=StepStatus.SUCCEEDED)
            terminal_operation = dataclasses.replace(
                current_operation,
                status=OperationStatus.SUCCEEDED,
                ready_closure_ref=ready_closure_ref,
                updated_at=transaction_now,
                completed_at=transaction_now,
                optimistic_version=current_operation.optimistic_version + 1,
            )
            transaction.set_artifact_protection(
                _unique_refs(
                    (
                        ready_closure_ref,
                        assemble_checkpoint_ref,
                        *closure_output_refs,
                    )
                ),
                owner_kind="history-compare-operation",
                owner_id=current_operation.operation_id,
                intent="history-compare-result",
            )
            return terminal_step, terminal_operation

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED
        lease_session.publish_operation(builder)
        return ExecutorAcknowledgment.PUBLISHED

    return cast(ClaimedExecutor, execute)


def _materialize_distinct_commits(
    payload: HistoryCompareJobPayload,
    deps: HistoryCompareRuntimeDependencies,
) -> dict[str, BoundSnapshotInput]:
    distinct_commits = tuple(dict.fromkeys(node.commit_id for node in payload.nodes))
    sides: dict[str, BoundSnapshotInput] = {}
    runtime_ruleset = _assert_runtime_ruleset(payload).snapshot
    bindings: dict[str, CanonicalBinding] = {}
    providers: dict[str, RepositoryTableAccessProvider] = {}
    for commit_id in distinct_commits:
        providers[commit_id] = deps.repository_provider_factory(payload.repository_id, commit_id)
        with deps.control_transaction_factory() as unit_of_work:
            try:
                metadata = unit_of_work.commit_canonical_metadata.resolve(
                    repository_id=payload.repository_id,
                    commit_id=commit_id,
                    scope=CommitCanonicalScope(
                        gateway_device_external_key=payload.gateway_device_external_key,
                        business_project_id=payload.business_project_id,
                    ),
                )
            except CommitCanonicalMetadataError as exc:
                raise HistoryCompareJobError(
                    exc.diagnostic,
                    diagnostic_code=exc.code.value,
                ) from exc
        binding = canonical_binding_for_commit(metadata, runtime_ruleset=runtime_ruleset)
        bindings[commit_id] = binding

    for commit_id in distinct_commits:
        bound = _materialize_commit(
            repository_id=payload.repository_id,
            commit_id=commit_id,
            provider=providers[commit_id],
            store=deps.artifact_store,
            canonical_binding=bindings[commit_id],
            ruleset=runtime_ruleset,
            export_cache=deps.snapshot_export_cache,
        )
        sides[commit_id] = bound

    return sides


def _assert_runtime_ruleset(payload: HistoryCompareJobPayload) -> ComparisonRuleSet:
    active_rules = comparison_rule_set(migrated_table_ruleset_snapshot())
    digest = active_rules.ruleset_digest
    if digest is None:
        raise HistoryCompareRulesetVersionMismatch("runtime comparison ruleset digest is missing")
    if digest.value != payload.comparison_ruleset_digest:
        raise HistoryCompareRulesetVersionMismatch(
            "frozen comparison ruleset digest does not match runtime ruleset"
        )
    return active_rules


def _materialize_commit(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
    canonical_binding: CanonicalBinding,
    ruleset: TableRulesetSnapshot,
    requested_tables: tuple[str, ...] | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
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
        requested_tables=requested_tables,
        artifact_store=store,
        export_cache=export_cache,
    )
    result = materialize_repository_ref(request)
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        diagnostic = result.diagnostics[0] if result.diagnostics else None
        code = None if diagnostic is None else diagnostic.code.value
        raise HistoryCompareJobError(
            "commit materialization failed" if diagnostic is None else diagnostic.message,
            diagnostic_code=code,
        )
    return _bound_from_materialization(result, canonical_binding=canonical_binding)


def _assemble_comparison(
    *,
    payload: HistoryCompareJobPayload,
    operation_id: str,
    sides: dict[str, BoundSnapshotInput],
    rule_set: ComparisonRuleSet,
    store: ArtifactStorePort,
    lease_session: LeaseSession,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
) -> tuple[dict[str, object], ArtifactRef, str]:
    pair_specs: list[tuple[str, HistoryCompareNodeBinding, HistoryCompareNodeBinding]] = []
    for index in range(payload.pair_count):
        before_node = payload.nodes[index]
        current_node = payload.nodes[index + 1]
        pair_specs.append((f"{operation_id}-p{index}", before_node, current_node))

    pair_results: list[_PairPipelineResult] = []
    bundle_pairs: list[BundlePairInput] = []
    bundle_inputs: tuple[BundleInput, ...]
    if payload.pair_count == 1:
        bundle_profile = BundleProfile.SINGLE_PAIR
        bundle_inputs = (
            BundleInput(0, payload.nodes[0].ref_id, "node-0"),
            BundleInput(1, payload.nodes[1].ref_id, "node-1"),
        )
        bundle_indexes = {pair_specs[0][0]: (0, 1)}
    else:
        bundle_profile = BundleProfile.MULTI_PAIR
        bundle_inputs = tuple(
            BundleInput(index, node.ref_id, f"node-{index}") for index, node in enumerate(payload.nodes)
        )
        bundle_indexes = {
            pair_specs[0][0]: (0, 1),
            pair_specs[1][0]: (1, 2),
        }

    for pair_id, before_node, current_node in pair_specs:
        lease_session.refresh_control()
        if control.cancel_requested:
            on_cancel()
            raise PairPipelineCancelled
        before = sides[before_node.commit_id]
        current = sides[current_node.commit_id]
        pair_state = _run_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            rule_set=rule_set,
            store=store,
            control=control,
            on_cancel=on_cancel,
        )
        pair_results.append(pair_state)
        before_index, current_index = bundle_indexes[pair_id]
        bundle_pairs.append(
            BundlePairInput(
                pair_id,
                before_index,
                current_index,
                pair_state.surface_result,
                surface_artifact_closure(
                    pair_state.surface_result.surface,
                    pair_id,
                    pair_state.records_closure,
                    before=before,
                    current=current,
                    include_all_tables=True,
                ),
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
        raise HistoryCompareJobError("bundle assembly failed")

    assemble_state: dict[str, object] = {
        "pair_ids": [item.pair_id for item in pair_results],
        "pairs": [
            {
                "pair_id": pair_state.pair_id,
                "before_ref": {
                    "ref_kind": before.ref_kind.value,
                    "ref_id": before.ref_id,
                },
                "before_commit": before.commit_id,
                "current_ref": {
                    "ref_kind": current.ref_kind.value,
                    "ref_id": current.ref_id,
                },
                "current_commit": current.commit_id,
                "comparison_digest": pair_state.comparison_digest,
                "risk_digest": pair_state.risk_digest,
                "surface_digest": pair_state.surface_digest,
                "record_count": pair_state.record_count,
            }
            for pair_state, (_, before, current) in zip(pair_results, pair_specs, strict=True)
        ],
        "bundle_digest": bundle_result.bundle.bundle_digest.value,
        "required_refs": [
            artifact_ref_to_dict(item)
            for item in _required_ready_refs(pair_results, bundle_result.bundle.manifest_ref)
        ],
    }
    return assemble_state, bundle_result.bundle.manifest_ref, bundle_result.bundle.bundle_digest.value


def _run_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    rule_set: ComparisonRuleSet,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
) -> _PairPipelineResult:
    try:
        return run_history_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            rule_set=rule_set,
            store=store,
            control=control,
            on_cancel=on_cancel,
        )
    except PairPipelineCancelled:
        raise
    except PairPipelineError as exc:
        raise HistoryCompareJobError(str(exc)) from exc


def _publish_ruleset_mismatch_failure(
    *,
    lease_session: LeaseSession,
    operation: OperationRecord,
    step: StepRecord,
    message: str,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare ruleset transaction is not bound")
        _release_history_compare_step_protection(transaction, operation_id=current_operation.operation_id)
        diagnostic = OperationDiagnostic(
            code=HistoryCompareDiagnosticCode.HISTORY_RULESET_VERSION_MISMATCH.value,
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


def _publish_commit_unavailable_failure(
    *,
    lease_session: LeaseSession,
    operation: OperationRecord,
    step: StepRecord,
    message: str,
    diagnostic_code: str | None = None,
    control: ExecutionControl,
) -> None:
    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare failure transaction is not bound")
        _release_history_compare_step_protection(transaction, operation_id=current_operation.operation_id)
        diagnostic = OperationDiagnostic(
            code=diagnostic_code or HistoryCompareDiagnosticCode.HISTORY_COMMIT_UNAVAILABLE.value,
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


def _required_ready_refs(
    pair_results: list[_PairPipelineResult],
    bundle_manifest_ref: ArtifactRef,
) -> tuple[ArtifactRef, ...]:
    from gateway_backend.capabilities.bundle_assembly import collect_surface_refs

    refs: list[ArtifactRef] = []
    for pair_state in pair_results:
        if pair_state.surface_result.surface is None:
            raise HistoryCompareJobError("pair surface is missing from ready closure")
        refs.extend(collect_surface_refs(pair_state.surface_result.surface))
    refs.append(bundle_manifest_ref)
    return _unique_refs(tuple(refs))


def _ready_closure_refs_from_assemble(
    assemble_state: dict[str, object],
    bundle_manifest_ref: ArtifactRef,
) -> tuple[ArtifactRef, ...]:
    raw_refs = assemble_state.get("required_refs")
    if type(raw_refs) is not list or not raw_refs:
        raise HistoryCompareJobError("assemble state is missing required ready-closure refs")
    refs: list[ArtifactRef] = []
    for item in raw_refs:
        if type(item) is not dict:
            raise HistoryCompareJobError("assemble required ref is invalid")
        refs.append(artifact_ref_from_dict(item))
    refs.append(bundle_manifest_ref)
    return _unique_refs(tuple(refs))


def _serialize_sides(sides: dict[str, BoundSnapshotInput]) -> dict[str, object]:
    return {commit_id: _side_binding_document(bound, commit_id=commit_id) for commit_id, bound in sides.items()}


def _side_binding_document(bound: BoundSnapshotInput, *, commit_id: str) -> dict[str, object]:
    if bound.table_set is None:
        raise HistoryCompareJobError("snapshot table set is missing closed refs")
    tables: list[dict[str, object]] = []
    materialized_names: set[str] = set()
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise HistoryCompareJobError(f"table {table.descriptor.table_name} is missing artifact refs")
        tables.append(
            {
                "table_name": table.descriptor.table_name,
                "manifest_ref": artifact_ref_to_dict(table.artifact.manifest_ref),
                "row_file_refs": [
                    artifact_ref_to_dict(item) for item in table.artifact.manifest.row_file_refs
                ],
            }
        )
        materialized_names.add(table.descriptor.table_name)
    unmaterialized_descriptors = [
        _snapshot_descriptor_to_document(table)
        for table in bound.summary.tables
        if table.table_name not in materialized_names
    ]
    return {
        "contract_version": HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION,
        "commit_id": commit_id,
        "snapshot": snapshot_to_document(bound.snapshot),
        "snapshot_digest": bound.snapshot.snapshot_digest.value,
        "summary": snapshot_summary_to_document(bound.summary),
        "unmaterialized_descriptors": unmaterialized_descriptors,
        "storage_facts": _storage_facts_to_documents(bound.storage_facts),
        "tables": tables,
    }


def _sides_from_materialize_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
) -> dict[str, BoundSnapshotInput]:
    sides_ref = _materialized_sides_ref_from_checkpoint(job_state)
    document = load_checkpoint_state_artifact(
        store,
        sides_ref,
        document_type=HISTORY_COMPARE_MATERIALIZED_SIDES_DOCUMENT_TYPE,
        contract_version=HISTORY_COMPARE_MATERIALIZED_SIDES_CONTRACT_VERSION,
    )
    if set(document) != {"document_type", "contract_version", _JOB_STATE_SIDES}:
        raise CheckpointDecodeError(
            "history compare materialized sides artifact fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    raw_sides = document.get(_JOB_STATE_SIDES)
    if type(raw_sides) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint sides are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    sides: dict[str, BoundSnapshotInput] = {}
    for commit_id, entry in raw_sides.items():
        if type(commit_id) is not str or type(entry) is not dict:
            raise CheckpointDecodeError(
                "materialize checkpoint side entry is invalid",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        sides[commit_id] = _bound_from_side_document(entry, store)
    return sides


def history_compare_assemble_state_from_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort | BoundedArtifactStorePort,
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
            "history compare assemble checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    raw_ref = job_state.get(_JOB_STATE_ASSEMBLE_REF)
    if type(raw_ref) is not dict:
        raise CheckpointDecodeError(
            "history compare assemble state ref is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        assemble_state_ref = artifact_ref_from_dict(raw_ref)
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "history compare assemble state ref is invalid",
            code="CHECKPOINT_REF_INVALID",
        ) from exc
    document = load_checkpoint_state_artifact(
        store,
        assemble_state_ref,
        document_type=HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
        contract_version=HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
    )
    if set(document) != {"document_type", "contract_version", _JOB_STATE_ASSEMBLE}:
        raise CheckpointDecodeError(
            "history compare assemble state artifact fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    assemble_state = document.get(_JOB_STATE_ASSEMBLE)
    if type(assemble_state) is not dict:
        raise CheckpointDecodeError(
            "history compare assemble state artifact is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return assemble_state_ref, cast(dict[str, object], assemble_state)


def _materialized_sides_ref_from_checkpoint(job_state: Mapping[str, object]) -> ArtifactRef:
    if set(job_state) != {_JOB_STATE_MATERIALIZED_SIDES_REF}:
        raise CheckpointDecodeError(
            "history compare materialize checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    raw_ref = job_state.get(_JOB_STATE_MATERIALIZED_SIDES_REF)
    if type(raw_ref) is not dict:
        raise CheckpointDecodeError(
            "history compare materialized sides ref is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        return artifact_ref_from_dict(raw_ref)
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "history compare materialized sides ref is invalid",
            code="CHECKPOINT_REF_INVALID",
        ) from exc


def _bound_from_side_document(entry: dict[str, object], store: ArtifactStorePort) -> BoundSnapshotInput:
    if entry.get("contract_version") != HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION:
        raise CheckpointDecodeError(
            "materialize checkpoint side contract version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    tables_raw = entry.get("tables")
    if type(tables_raw) is not list:
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
        except (TypeError, ValueError, KeyError, ManifestVerificationError) as exc:
            raise HistoryCompareJobError("materialize checkpoint table artifact is unreadable") from exc
    try:
        snapshot = snapshot_from_document(entry.get("snapshot"))
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint snapshot is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    snapshot_digest_raw = entry.get("snapshot_digest")
    if type(snapshot_digest_raw) is not str or snapshot.snapshot_digest.value != snapshot_digest_raw:
        raise CheckpointDecodeError(
            "materialize checkpoint digest mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        summary_raw = entry.get("summary")
        if type(summary_raw) is not dict or type(summary_raw.get("tables")) is not list:
            raise ValueError("summary tables are invalid")
        descriptors_by_name = {table.descriptor.table_name: table.descriptor for table in opened}
        raw_unmaterialized = entry.get("unmaterialized_descriptors")
        if type(raw_unmaterialized) is not list:
            raise ValueError("unmaterialized_descriptors must be a list")
        for raw_descriptor in raw_unmaterialized:
            descriptor = _snapshot_descriptor_from_document(raw_descriptor)
            if descriptor.table_name in descriptors_by_name:
                raise ValueError("unmaterialized descriptor repeats a materialized table")
            descriptors_by_name[descriptor.table_name] = descriptor
        raw_summary_tables = summary_raw["tables"]
        ordered_names = tuple(
            _document_string(item, "table_name")
            for item in raw_summary_tables
            if type(item) is dict
        )
        if len(ordered_names) != len(raw_summary_tables) or set(ordered_names) != set(descriptors_by_name):
            raise ValueError("summary and materialized descriptors do not match")
        summary = snapshot_summary_from_document(
            summary_raw,
            snapshot=snapshot,
            tables=tuple(descriptors_by_name[name] for name in ordered_names),
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint summary does not match its snapshot and tables",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    try:
        storage_facts = _storage_facts_from_documents(entry.get("storage_facts"))
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    descriptors = {table.table_name: table for table in summary.tables}
    facts_by_table = {fact.storage_rule_view.canonical_table: fact for fact in storage_facts}
    if len(facts_by_table) != len(storage_facts) or set(facts_by_table) != set(descriptors):
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts do not match its snapshot tables",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if any(
        facts_by_table[name].raw_content_digest != descriptor.raw_content_digest
        or facts_by_table[name].canonical_schema_digest is None
        or facts_by_table[name].storage_projection_version is None
        for name, descriptor in descriptors.items()
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts do not match table identities",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    table_set = SnapshotTableSet(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        table_ruleset_version=snapshot.table_ruleset_version,
        tables=tuple(opened),
    )
    return BoundSnapshotInput(snapshot, summary, table_set, storage_facts)


def _bound_from_materialization(
    result: SnapshotMaterializationResult,
    *,
    canonical_binding: CanonicalBinding,
) -> BoundSnapshotInput:
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        raise HistoryCompareJobError("materialization failed")
    if result.snapshot is None or result.summary is None:
        raise HistoryCompareJobError("materialization is incomplete")
    descriptors = {item.table_name: item for item in result.summary.tables}
    identities = {item.canonical_table: item for item in canonical_binding.table_identities}
    storage_facts = tuple(
        ComparisonStorageFacts(
            storage_rule_view=view,
            source_schema_digest=identities[view.canonical_table].source_schema_digest,
            canonical_schema_digest=identities[view.canonical_table].canonical_schema_digest,
            raw_content_digest=identities[view.canonical_table].raw_content_digest,
            storage_projection_version=canonical_binding.storage_projection_version,
        )
        for view in canonical_binding.tables
        if view.canonical_table in descriptors
    )
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set, storage_facts)


def _closed_refs_from_sides(sides: dict[str, BoundSnapshotInput]) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for bound in sides.values():
        refs.extend(_side_input_refs(bound))
    return tuple(refs)


def _side_input_refs(bound: BoundSnapshotInput) -> tuple[ArtifactRef, ...]:
    if bound.table_set is None:
        raise HistoryCompareJobError("snapshot table set is missing closed refs")
    refs: list[ArtifactRef] = []
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise HistoryCompareJobError(f"table {table.descriptor.table_name} is missing artifact refs")
        refs.append(table.artifact.manifest_ref)
        refs.extend(table.artifact.manifest.row_file_refs)
    return tuple(refs)


def _unique_refs(refs: tuple[ArtifactRef, ...]) -> tuple[ArtifactRef, ...]:
    return unique_artifact_refs(refs)


def _pin_history_compare_refs(
    deps: HistoryCompareRuntimeDependencies,
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


def _release_history_compare_step_protection(
    unit_of_work: HistoryCompareControlTransaction,
    *,
    operation_id: str,
) -> None:
    for step_name in (
        HISTORY_COMPARE_STEP_MATERIALIZE,
        HISTORY_COMPARE_STEP_ASSEMBLE,
        HISTORY_COMPARE_STEP_PUBLISH,
    ):
        unit_of_work.clear_artifact_protection(
            owner_kind="history-compare-checkpoint",
            owner_id=history_compare_step_id(operation_id, step_name),
        )
    unit_of_work.clear_artifact_protection(
        owner_kind="history-compare-operation",
        owner_id=operation_id,
    )


def _load_step(
    deps: HistoryCompareRuntimeDependencies,
    *,
    operation_id: str,
    step_id: str,
) -> StepRecord:
    with deps.control_transaction_factory() as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
    if step.operation_id != operation_id:
        raise HistoryCompareJobError("history compare step belongs to a different operation")
    return step


def _load_history_compare_payload(operation: OperationRecord, store: ArtifactStorePort) -> HistoryCompareJobPayload:
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
    return decode_history_compare_payload(cast(dict[str, object], payload_object))


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
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare cancellation transaction is not bound")
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        _release_history_compare_step_protection(transaction, operation_id=operation.operation_id)
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


_HISTORY_COMPARE_STEP_SUFFIX: dict[str, str] = {
    HISTORY_COMPARE_STEP_MATERIALIZE: "1",
    HISTORY_COMPARE_STEP_ASSEMBLE: "2",
    HISTORY_COMPARE_STEP_PUBLISH: "3",
}


def history_compare_step_id(operation_id: str, step_name: str) -> str:
    from gateway_backend.application.job_steps import successor_step_id

    return successor_step_id(operation_id, step_name, _HISTORY_COMPARE_STEP_SUFFIX)


def _require_non_empty_str(payload_object: dict[str, object], key: str) -> str:
    value = payload_object.get(key)
    if type(value) is not str or not value:
        raise PayloadDecodeError(f"{key} must be a non-empty string", code="PAYLOAD_SHAPE_INVALID")
    return value


def _require_positive_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise PayloadDecodeError(f"{key} must be a positive int", code="PAYLOAD_SHAPE_INVALID")
    return value


def _decode_nodes(value: object) -> tuple[HistoryCompareNodeBinding, ...]:
    from gateway_backend.application.history.contracts import HistoryNodeRefKind

    if type(value) is not list or not value:
        raise PayloadDecodeError("nodes must be a non-empty list", code="PAYLOAD_SHAPE_INVALID")
    nodes: list[HistoryCompareNodeBinding] = []
    for item in value:
        if type(item) is not dict:
            raise PayloadDecodeError("node entry must be an object", code="PAYLOAD_SHAPE_INVALID")
        try:
            ref_kind = HistoryNodeRefKind(str(item["ref_kind"]))
            ref_id = str(item["ref_id"])
            commit_id = str(item["commit_id"])
        except KeyError as exc:
            raise PayloadDecodeError(
                f"node entry is missing required field: {exc.args[0]}",
                code="PAYLOAD_SHAPE_INVALID",
            ) from exc
        nodes.append(
            HistoryCompareNodeBinding(
                ref_kind=ref_kind,
                ref_id=ref_id,
                commit_id=commit_id,
            )
        )
    return tuple(nodes)


__all__ = [
    "HISTORY_COMPARE_ASSEMBLE_DECODER",
    "HISTORY_COMPARE_ASSEMBLE_HANDLER",
    "HISTORY_COMPARE_JOB_CONTRACT_VERSION",
    "HISTORY_COMPARE_JOB_KIND",
    "HISTORY_COMPARE_MATERIALIZE_DECODER",
    "HISTORY_COMPARE_MATERIALIZE_HANDLER",
    "HISTORY_COMPARE_PUBLISH_DECODER",
    "HISTORY_COMPARE_PUBLISH_HANDLER",
    "HISTORY_COMPARE_STEP_ASSEMBLE",
    "HISTORY_COMPARE_STEP_MATERIALIZE",
    "HISTORY_COMPARE_STEP_PUBLISH",
    "HistoryCompareControlTransaction",
    "HistoryCompareControlTransactionFactory",
    "HistoryCompareJobPayload",
    "HistoryCompareRuntimeDependencies",
    "RepositoryProviderFactory",
    "bind_history_compare_transaction_factory",
    "build_assemble_comparison_handler",
    "build_materialize_inputs_handler",
    "build_publish_result_handler",
    "decode_history_compare_payload",
    "history_compare_composition_bundle",
    "history_compare_job_definitions",
    "history_compare_payload_decoders",
    "history_compare_step_id",
]
