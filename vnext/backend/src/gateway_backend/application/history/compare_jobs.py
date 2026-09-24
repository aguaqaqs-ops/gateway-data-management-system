"""History compare JobDefinition, decoder, and fixed three-step handler topology."""

from __future__ import annotations

import dataclasses
import hashlib
import json
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
from gateway_backend.application.history.compare_bindings import compute_compare_binding_digest
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HISTORY_INTEGRITY_FAILURE_CLASS,
    HISTORY_INTEGRITY_RECOMMENDED_ACTION,
    HistoryCompareDiagnosticCode,
    HistoryCompareIntegrityRecord,
    HistoryCompareNodeBinding,
    IntegrityAcknowledgementStatus,
)
from gateway_backend.application.history.ports import HistoryComparePort
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
from gateway_backend.application.preview_jobs import surface_artifact_closure
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
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
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BoundSnapshotInput,
    ComparisonPlan,
    DetailedFactsResult,
    FailedResult,
    PairRole,
    PairViewKind,
    TrustedFlowApplicabilityBinding,
    bind_pair_input,
    compare_plan,
    plan_pair,
    publish_records_closure,
)
from gateway_backend.capabilities.comparison.contracts import (
    BlankRowPolicy,
    ComparisonTablePolicy,
    InputCompleteness as ComparisonInputCompleteness,
    OrderedTablePolicy,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskEvaluationStatus,
    RiskOptions,
    V1_RISK_RULE_SPECS,
    RiskRulesetSnapshot,
    evaluate_risk,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import open_snapshot_table_artifact
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    Snapshot,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTableSet,
    SourceKind,
    SUMMARY_CONTRACT_VERSION,
)
from gateway_backend.capabilities.snapshot_materialization.repository_ref import (
    materialize_repository_ref,
)
from gateway_backend.capabilities.surface_assembly import (
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.capabilities.table_access.contracts import NeverCancel, ParserInvocationContext
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
    TableStaticRole,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.resolver import resolve_table_rule
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
from gateway_backend.operations.store import OperationStore
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

HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION = "backend-vnext/history-compare/materialize-side/v1"
HISTORY_COMPARE_COMPARE_BINDING_CONTRACT_VERSION = "backend-vnext/history-compare/compare-binding/v1"

_JOB_STATE_SIDES = "sides"
_JOB_STATE_COMPARE_BINDING_PREIMAGE = "compare_binding_preimage"
_JOB_STATE_COMPARE_BINDING_DIGEST = "compare_binding_digest"
_JOB_STATE_TABLE_POLICIES = "table_policies"
_JOB_STATE_ASSEMBLE = "assemble_state"
_JOB_STATE_READY_CLOSURE = "ready_closure_artifact_id"
_JOB_STATE_READY_CLOSURE_REF = "ready_closure_ref"
_JOB_STATE_BUNDLE_ARTIFACT = "bundle_artifact_id"
_JOB_STATE_BUNDLE_DIGEST = "bundle_digest"

_INTEGRITY_CANDIDATE_CODES = frozenset(
    {
        MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT,
        MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
    }
)

_active_history_compare_transaction: ContextVar[HistoryCompareControlTransaction | None] = ContextVar(
    "_active_history_compare_transaction",
    default=None,
)


class HistoryCompareJobError(ValueError):
    """Bounded history compare job failure surfaced to the operation runtime."""


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
    table_ruleset_version: str
    comparison_contract_version: str
    view_kind: str
    pair_count: int
    nodes: tuple[HistoryCompareNodeBinding, ...]


@runtime_checkable
class HistoryCompareControlTransaction(Protocol):
    @property
    def operations(self) -> OperationStore: ...

    @property
    def history_compare(self) -> HistoryComparePort: ...

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


HistoryCompareControlTransactionFactory = Callable[[], ContextManager[HistoryCompareControlTransaction]]
RepositoryProviderFactory = Callable[[str, str], RepositoryTableAccessProvider]


@dataclass(frozen=True, slots=True)
class HistoryCompareRuntimeDependencies:
    artifact_store: ArtifactStorePort
    repository_provider_factory: RepositoryProviderFactory
    control_transaction_factory: HistoryCompareControlTransactionFactory


@dataclass(frozen=True, slots=True)
class _PairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    record_count: int
    surface_result: SurfaceAssemblyResult


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
    table_ruleset_version = _require_non_empty_str(payload_object, "table_ruleset_version")
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
        table_ruleset_version=table_ruleset_version,
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
        key = definition.key

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the history compare materialize JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            _pin_history_compare_refs(
                deps,
                (step.checkpoint_ref,),
                owner_kind="history-compare-checkpoint",
                owner_id=step.step_id,
                intent="materialize-checkpoint",
            )
        else:
            try:
                sides, compare_binding_preimage, compare_binding_digest, table_policies = (
                    _materialize_distinct_commits(payload, deps)
                )
            except _IntegrityConfirmed as confirmed:
                _publish_integrity_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    payload=payload,
                    confirmed=confirmed,
                )
                return ExecutorAcknowledgment.PUBLISHED
            except HistoryCompareRulesetVersionMismatch as exc:
                _publish_ruleset_mismatch_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=str(exc),
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED
            except HistoryCompareJobError as exc:
                _publish_commit_unavailable_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=str(exc),
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED

            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_SIDES: _serialize_sides(sides),
                    _JOB_STATE_COMPARE_BINDING_PREIMAGE: compare_binding_preimage,
                    _JOB_STATE_COMPARE_BINDING_DIGEST: compare_binding_digest,
                    _JOB_STATE_TABLE_POLICIES: table_policies,
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
        compare_binding_digest = materialize_envelope.job_state.get(_JOB_STATE_COMPARE_BINDING_DIGEST)
        table_policies_raw = materialize_envelope.job_state.get(_JOB_STATE_TABLE_POLICIES)
        if type(compare_binding_digest) is not str or not compare_binding_digest:
            raise CheckpointDecodeError(
                "materialize checkpoint is missing compare_binding_digest",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        if type(table_policies_raw) is not list:
            raise CheckpointDecodeError(
                "materialize checkpoint is missing table_policies",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        table_policies = _table_policies_from_checkpoint(table_policies_raw)

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(assemble_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the history compare assemble JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            _pin_history_compare_refs(
                deps,
                (step.checkpoint_ref,),
                owner_kind="history-compare-checkpoint",
                owner_id=step.step_id,
                intent="assemble-checkpoint",
            )
        else:
            assemble_state, bundle_manifest_ref, bundle_digest = _assemble_comparison(
                payload=payload,
                operation_id=operation.operation_id,
                sides=sides,
                table_policies=table_policies,
                compare_binding_digest=compare_binding_digest,
                store=deps.artifact_store,
                lease_session=lease_session,
                control=control,
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


@dataclass(frozen=True, slots=True)
class _IntegrityConfirmed(Exception):
    expected_digest: str
    observed_digest: str
    affected_tables: tuple[str, ...]
    commit_id: str
    first_observed_at: datetime
    last_observed_at: datetime


def _materialize_distinct_commits(
    payload: HistoryCompareJobPayload,
    deps: HistoryCompareRuntimeDependencies,
) -> tuple[
    dict[str, BoundSnapshotInput],
    dict[str, object],
    str,
    list[dict[str, object]],
]:
    runtime_ruleset_version = str(TABLE_RULESET_VERSION)

    if payload.table_ruleset_version != runtime_ruleset_version:
        raise HistoryCompareRulesetVersionMismatch("frozen table_ruleset_version does not match runtime ruleset")
    distinct_commits = tuple(dict.fromkeys(node.commit_id for node in payload.nodes))
    sides: dict[str, BoundSnapshotInput] = {}
    table_sets: list[SnapshotTableSet] = []
    for commit_id in distinct_commits:
        provider = deps.repository_provider_factory(payload.repository_id, commit_id)
        bound, result = _materialize_commit_with_integrity(
            repository_id=payload.repository_id,
            commit_id=commit_id,
            provider=provider,
            store=deps.artifact_store,
        )
        sides[commit_id] = bound
        if bound.table_set is not None:
            table_sets.append(bound.table_set)

    ruleset = migrated_table_ruleset_snapshot()
    if str(ruleset.table_ruleset_version) != runtime_ruleset_version:
        raise HistoryCompareRulesetVersionMismatch("ruleset snapshot version mismatch")

    table_names: dict[str, tuple[str, ...]] = {}
    for table_set in table_sets:
        for table in table_set.tables:
            descriptor = table.descriptor
            if descriptor.table_name not in table_names:
                # First-seen PK is used only for ruleset policy projection; capability
                # compares per-side descriptors and degrades on key_changed (design §5.4).
                table_names[descriptor.table_name] = descriptor.primary_key_columns

    policies = [
        _policy_to_checkpoint_dict(_project_table_policy(resolve_table_rule(
            ruleset,
            table_name,
            primary_key_columns=primary_key_columns,
        )))
        for table_name, primary_key_columns in sorted(table_names.items())
    ]
    compare_binding_preimage = {
        "gateway_device_external_key": payload.gateway_device_external_key,
        "business_project_id": payload.business_project_id,
        "repository_id": payload.repository_id,
        "nodes": [
            {"ref_kind": node.ref_kind.value, "ref_id": node.ref_id, "commit_id": node.commit_id}
            for node in payload.nodes
        ],
        "table_ruleset_version": payload.table_ruleset_version,
        "comparison_contract_version": payload.comparison_contract_version,
        "view_kind": payload.view_kind,
        "pair_count": payload.pair_count,
        "table_policies": policies,
    }
    compare_binding_digest = compute_compare_binding_digest(
        gateway_device_external_key=payload.gateway_device_external_key,
        business_project_id=payload.business_project_id,
        repository_id=payload.repository_id,
        nodes=payload.nodes,
        table_ruleset_version=payload.table_ruleset_version,
        table_policies=policies,
        comparison_contract_version=payload.comparison_contract_version,
        view_kind=payload.view_kind,
        pair_count=payload.pair_count,
    )
    return sides, compare_binding_preimage, compare_binding_digest, policies


def _materialize_commit_with_integrity(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
) -> tuple[BoundSnapshotInput, SnapshotMaterializationResult]:
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
    first_observed_at = datetime.now(UTC)
    first = materialize_repository_ref(request)
    if first.status is SnapshotMaterializationStatus.COMPLETE:
        return _bound_from_materialization(first), first
    first_diag = _candidate_diagnostic(first)
    if first_diag is None:
        raise HistoryCompareJobError("commit materialization failed")
    second = materialize_repository_ref(request)
    last_observed_at = datetime.now(UTC)
    if second.status is SnapshotMaterializationStatus.COMPLETE:
        raise HistoryCompareJobError("commit materialization recovered on retry")
    second_diag = _candidate_diagnostic(second)
    if second_diag is None or second_diag.code != first_diag.code:
        raise HistoryCompareJobError("commit materialization failed")
    if not _integrity_confirmed(first_diag, second_diag):
        has_public_facts = any(
            diagnostic.expected_digest_ref is not None or diagnostic.observed_digest_ref is not None
            for diagnostic in (first_diag, second_diag)
        )
        if not has_public_facts:
            raise HistoryCompareJobError("integrity candidate diagnostic is missing digest refs")
        raise HistoryCompareJobError("commit materialization failed")
    expected = first_diag.expected_digest_ref
    observed = first_diag.observed_digest_ref
    if expected is None or observed is None:
        raise HistoryCompareJobError("integrity diagnostic is missing digest refs")
    tables = tuple(
        sorted(
            {
                item
                for item in (first_diag.table, second_diag.table)
                if type(item) is str and item
            }
        )
    )
    raise _IntegrityConfirmed(
        expected_digest=expected.value,
        observed_digest=observed.value,
        affected_tables=tables,
        commit_id=commit_id,
        first_observed_at=first_observed_at,
        last_observed_at=last_observed_at,
    )


def _integrity_confirmed(first: MaterializationDiagnostic, second: MaterializationDiagnostic) -> bool:
    if first.code != second.code:
        return False
    if (
        first.expected_digest_ref is None
        or first.observed_digest_ref is None
        or second.expected_digest_ref is None
        or second.observed_digest_ref is None
    ):
        return False
    if first.expected_digest_ref != second.expected_digest_ref:
        return False
    if _is_structural_integrity_diagnostic(first):
        return first.observed_digest_ref == second.observed_digest_ref
    # Content-track: stable expected; both observed disagree with expected (drift allowed).
    return (
        first.observed_digest_ref != first.expected_digest_ref
        and second.observed_digest_ref != second.expected_digest_ref
    )


def _is_structural_integrity_diagnostic(diagnostic: MaterializationDiagnostic) -> bool:
    expected = diagnostic.expected_digest_ref
    observed = diagnostic.observed_digest_ref
    if expected is None or observed is None:
        return False
    structural_labels: tuple[bytes, ...] = (b"catalog-table:missing",)
    if type(diagnostic.table) is str and diagnostic.table:
        structural_labels += (
            f"catalog-table:{diagnostic.table}".encode(),
            f"hidden-summary-table:missing:{diagnostic.table}".encode(),
        )
    return any(
        expected == raw_blob_digest(label) or observed == raw_blob_digest(label)
        for label in structural_labels
    )


def _candidate_diagnostic(result: SnapshotMaterializationResult) -> MaterializationDiagnostic | None:
    for diagnostic in result.diagnostics:
        if diagnostic.code in _INTEGRITY_CANDIDATE_CODES:
            return diagnostic
    return None


def _project_table_policy(resolved: object) -> ComparisonTablePolicy:
    from gateway_backend.capabilities.table_rules.contracts import ResolvedTableRule

    if type(resolved) is not ResolvedTableRule:
        raise HistoryCompareJobError("table rule resolution failed")
    decision = resolved.decision
    ignored_columns = decision.ignored_columns
    if decision.static_role is TableStaticRole.ORDERED_DIFF:
        position_column = decision.position_column or "no"
        stable_candidates = decision.stable_key_candidates
        row_identity_key = (stable_candidates[0],) if len(stable_candidates) == 1 else None
        return ComparisonTablePolicy(
            table_name=resolved.canonical_table,
            ignored_columns=ignored_columns,
            ordered_policy=OrderedTablePolicy(
                order_key=(position_column,),
                row_identity_key=row_identity_key,
                stable_key_candidates=stable_candidates,
                ignored_columns=ignored_columns if ignored_columns else ("no",),
                blank_row_policy=BlankRowPolicy.PSEUDO_BLANK_BY_MISSING_STABLE_KEY,
            ),
        )
    return ComparisonTablePolicy(
        table_name=resolved.canonical_table,
        ignored_columns=ignored_columns,
    )


def _policy_to_checkpoint_dict(policy: ComparisonTablePolicy) -> dict[str, object]:
    payload: dict[str, object] = {
        "table_name": policy.table_name,
        "ignored_columns": list(policy.ignored_columns),
        "keyless_policy": policy.keyless_policy.value,
        "policy_version": policy.policy_version,
    }
    if policy.ordered_policy is not None:
        ordered = policy.ordered_policy
        payload["ordered_policy"] = {
            "policy_id": ordered.policy_id,
            "policy_version": ordered.policy_version,
            "order_key": list(ordered.order_key),
            "row_identity_key": None if ordered.row_identity_key is None else list(ordered.row_identity_key),
            "stable_key_candidates": list(ordered.stable_key_candidates),
            "value_columns": list(ordered.value_columns),
            "ignored_columns": list(ordered.ignored_columns),
            "blank_row_policy": ordered.blank_row_policy.value,
            "move_policy": ordered.move_policy,
            "ambiguity_policy": ordered.ambiguity_policy,
            "tail_change_policy": ordered.tail_change_policy,
            "table_processing_mode_policy": ordered.table_processing_mode_policy,
        }
    return payload


def _table_policies_from_checkpoint(raw: list[object]) -> tuple[ComparisonTablePolicy, ...]:
    policies: list[ComparisonTablePolicy] = []
    for item in raw:
        if type(item) is not dict:
            raise CheckpointDecodeError("table policy entry is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH")
        ordered_raw = item.get("ordered_policy")
        ordered_policy = None
        if type(ordered_raw) is dict:
            row_identity_key_raw = ordered_raw.get("row_identity_key")
            row_identity_key = None
            if type(row_identity_key_raw) is list:
                row_identity_key = tuple(str(column) for column in row_identity_key_raw)
            ordered_policy = OrderedTablePolicy(
                policy_id=str(ordered_raw["policy_id"]),
                policy_version=str(ordered_raw["policy_version"]),
                order_key=tuple(str(column) for column in ordered_raw["order_key"]),
                row_identity_key=row_identity_key,
                stable_key_candidates=tuple(
                    str(column) for column in ordered_raw["stable_key_candidates"]
                ),
                value_columns=tuple(str(column) for column in ordered_raw["value_columns"]),
                ignored_columns=tuple(str(column) for column in ordered_raw["ignored_columns"]),
                blank_row_policy=BlankRowPolicy(str(ordered_raw["blank_row_policy"])),
                move_policy=str(ordered_raw["move_policy"]),
                ambiguity_policy=str(ordered_raw["ambiguity_policy"]),
                tail_change_policy=str(ordered_raw["tail_change_policy"]),
                table_processing_mode_policy=str(ordered_raw["table_processing_mode_policy"]),
            )
        from gateway_backend.capabilities.comparison.contracts import KeylessPolicy

        policies.append(
            ComparisonTablePolicy(
                table_name=str(item["table_name"]),
                ignored_columns=tuple(str(column) for column in item["ignored_columns"]),
                keyless_policy=KeylessPolicy(str(item["keyless_policy"])),
                policy_version=str(item["policy_version"]),
                ordered_policy=ordered_policy,
            )
        )
    return tuple(policies)


def _assemble_comparison(
    *,
    payload: HistoryCompareJobPayload,
    operation_id: str,
    sides: dict[str, BoundSnapshotInput],
    table_policies: tuple[ComparisonTablePolicy, ...],
    compare_binding_digest: str,
    store: ArtifactStorePort,
    lease_session: LeaseSession,
    control: ExecutionControl,
) -> tuple[dict[str, object], ArtifactRef, str]:
    trusted_flow_binding = TrustedFlowApplicabilityBinding(
        view_kind=PairViewKind.HISTORY,
        binding_digest=DigestRef(compare_binding_digest),
    )
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
            raise HistoryCompareJobError("history compare assembly cancelled")
        before = sides[before_node.commit_id]
        current = sides[current_node.commit_id]
        pair_state = _run_pair_pipeline(
            pair_id=pair_id,
            before=before,
            current=current,
            table_policies=table_policies,
            trusted_flow_binding=trusted_flow_binding,
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
    table_policies: tuple[ComparisonTablePolicy, ...],
    trusted_flow_binding: TrustedFlowApplicabilityBinding,
    store: ArtifactStorePort,
    control: ExecutionControl,
) -> _PairPipelineResult:
    bound = bind_pair_input(
        pair_id=pair_id,
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        input_completeness=ComparisonInputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=trusted_flow_binding,
        table_policies=table_policies,
    )
    if isinstance(bound, FailedResult):
        raise HistoryCompareJobError(f"pair binding failed: {bound.diagnostics}")
    plan = plan_pair(bound)
    if isinstance(plan, FailedResult):
        raise HistoryCompareJobError(f"pair planning failed: {plan.diagnostics}")
    if not isinstance(plan, ComparisonPlan):
        raise HistoryCompareJobError("pair planning did not produce a comparison plan")
    compared = compare_plan(plan)
    if isinstance(compared, FailedResult):
        raise HistoryCompareJobError(f"pair comparison failed: {compared.diagnostics}")
    if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
        raise HistoryCompareJobError("pair comparison did not produce facts")
    published = publish_records_closure(compared, store)
    if isinstance(published, FailedResult):
        raise HistoryCompareJobError(f"records closure failed: {published.diagnostics}")
    if not isinstance(published, DetailedFactsResult) or published.facts is None:
        raise HistoryCompareJobError("records publication did not produce facts")
    if control.cancel_requested:
        raise HistoryCompareJobError("history compare pair pipeline cancelled")
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=published.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=store,
    )
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise HistoryCompareJobError("risk evaluation failed")
    surface = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=published.facts,
            surface_id=f"surface-{pair_id}",
            view_id=pair_id,
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
        raise HistoryCompareJobError("surface assembly failed")
    records_closure = published.records_closure
    if records_closure is None:
        raise HistoryCompareJobError("records closure is missing")
    record_count = sum(entry.record_count for entry in records_closure.records)
    if record_count < 0:
        raise HistoryCompareJobError("records closure record_count is invalid")
    if risk.risk_evaluation is None:
        raise HistoryCompareJobError("risk evaluation digest is missing")
    return _PairPipelineResult(
        pair_id=pair_id,
        comparison_digest=published.facts.comparison_digest.value,
        risk_digest=risk.risk_evaluation.risk_evaluation_digest.value,
        surface_digest=surface.surface.surface_digest.value,
        record_count=int(record_count),
        surface_result=surface,
    )


def _publish_integrity_failure(
    *,
    lease_session: LeaseSession,
    operation: OperationRecord,
    step: StepRecord,
    payload: HistoryCompareJobPayload,
    confirmed: _IntegrityConfirmed,
) -> None:
    incident_id = f"hci-{hashlib.sha256(operation.operation_id.encode()).hexdigest()[:24]}"

    def builder(
        current_operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare integrity transaction is not bound")
        record = HistoryCompareIntegrityRecord(
            incident_id=incident_id,
            operation_id=current_operation.operation_id,
            repository_id=payload.repository_id,
            commit_refs=({"commit_id": confirmed.commit_id},),
            failure_class=HISTORY_INTEGRITY_FAILURE_CLASS,
            expected_digest=confirmed.expected_digest,
            observed_digest=confirmed.observed_digest,
            affected_tables=confirmed.affected_tables,
            recommended_action=HISTORY_INTEGRITY_RECOMMENDED_ACTION,
            first_seen_at=confirmed.first_observed_at,
            last_seen_at=confirmed.last_observed_at,
            acknowledgement_status=IntegrityAcknowledgementStatus.PENDING,
            resolution_reference=None,
            created_at=transaction_now,
            updated_at=transaction_now,
        )
        transaction.history_compare.save_integrity_record(record)
        _release_history_compare_step_protection(transaction, operation_id=current_operation.operation_id)
        diagnostic = OperationDiagnostic(
            code=HistoryCompareDiagnosticCode.HISTORY_REPOSITORY_INTEGRITY.value,
            message=f"repository integrity incident {incident_id}",
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

    lease_session.publish_operation(builder)


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
            code=HistoryCompareDiagnosticCode.HISTORY_COMMIT_UNAVAILABLE.value,
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
    return {
        "contract_version": HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION,
        "commit_id": commit_id,
        "snapshot": _snapshot_payload(bound.snapshot),
        "snapshot_digest": bound.snapshot.snapshot_digest.value,
        "summary": _summary_payload(bound.summary),
        "tables": tables,
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
    for commit_id, entry in raw_sides.items():
        if type(commit_id) is not str or type(entry) is not dict:
            raise CheckpointDecodeError(
                "materialize checkpoint side entry is invalid",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        sides[commit_id] = _bound_from_side_document(entry, store)
    return sides


def _bound_from_side_document(entry: dict[str, object], store: ArtifactStorePort) -> BoundSnapshotInput:
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
    snapshot = _snapshot_from_payload(entry.get("snapshot"))
    snapshot_digest_raw = entry.get("snapshot_digest")
    if type(snapshot_digest_raw) is not str or snapshot.snapshot_digest.value != snapshot_digest_raw:
        raise CheckpointDecodeError(
            "materialize checkpoint digest mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    summary_payload = entry.get("summary")
    if type(summary_payload) is not dict:
        raise CheckpointDecodeError(
            "materialize checkpoint summary is invalid",
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


def _bound_from_materialization(result: SnapshotMaterializationResult) -> BoundSnapshotInput:
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        raise HistoryCompareJobError("materialization failed")
    if result.snapshot is None or result.summary is None:
        raise HistoryCompareJobError("materialization is incomplete")
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set)


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
        raise HistoryCompareJobError("summary payload type is invalid")
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
            }
        )
    return {
        "snapshot_id": summary.snapshot_id,
        "snapshot_digest": summary.snapshot_digest.value,
        "table_count": summary.table_count,
        "row_count_total": summary.row_count_total,
        "tables": tables,
    }


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
        transaction = _active_history_compare_transaction.get()
        if transaction is None:
            raise HistoryCompareJobError("history compare checkpoint transaction is not bound")
        transaction.set_artifact_protection(
            _unique_refs((checkpoint_ref, *extra_refs)),
            owner_kind="history-compare-checkpoint",
            owner_id=step.step_id,
            intent=intent,
        )
        return candidate

    return builder


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


def history_compare_step_id(operation_id: str, step_name: str) -> str:
    suffix = {
        HISTORY_COMPARE_STEP_MATERIALIZE: "1",
        HISTORY_COMPARE_STEP_ASSEMBLE: "2",
        HISTORY_COMPARE_STEP_PUBLISH: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


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
