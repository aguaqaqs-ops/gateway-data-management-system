"""History compare step 2: pair comparison, demands, and bundle assembly."""

from __future__ import annotations

import dataclasses
import json
import logging

from collections.abc import (
    Callable,
    Mapping,
)
from gateway_backend.application.business_presentation import navigation_row_demands
from gateway_backend.application.canonical_metadata.binding import (
    canonical_binding_for_commit,
    presentation_for_commit,
)
from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.canonical_metadata.table_access import build_committed_table_access
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_ready_closure,
    prepare_ready_closure,
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.comparison_audit import (
    structure_audit_binding,
    verify_structure_audit_bindings,
)
from gateway_backend.application.history.contracts import HistoryCompareNodeBinding
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    make_successor_builder,
    pinned_checkpoint_builder,
)
from gateway_backend.application.kernel_execution import (
    assemble_operation_bundle as assemble_bundle,
)
from gateway_backend.application.pair_pipeline import (
    ComparisonTaskSession,
    PairPipelineCancelled,
    PairPipelineError,
    HistoryPairPipelineResult as _PairPipelineResult,
    declare_pair_comparison_session,
    run_history_pair_pipeline,
    same_complete_table_identity,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.preview_jobs.assemble import surface_artifact_closure
from gateway_backend.artifacts.computation_cache import CacheOperationOwner
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import (
    ArtifactBufferStorePort,
    ArtifactRepairBusyError,
    ArtifactStorePort,
)
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
)
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonMode,
    ComparisonPlan,
    ComparisonRequest,
    comparison_row_demands,
    plan_comparison,
)
from gateway_backend.capabilities.snapshot_materialization import (
    current_kernel_context,
    ensure_committed_tables,
    export_snapshot_table_parquet,
    lookup_snapshot_table_parquet,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    RepositoryProviderError,
    RepositoryRef,
)
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from gateway_backend.capabilities.table_presentation.contracts import PresentationMetadata
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.operations.contracts import (
    OperationRecord,
    StepRecord,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.recovery import HandlerExecutionFailure
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
)
from gateway_backend.statistics.metrics import (
    bind_scope,
    input_shape,
    timed,
)
from typing import cast

from gateway_backend.application.history.compare_jobs.checkpoint import (
    HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
    HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
    _JOB_STATE_ASSEMBLE,
    _JOB_STATE_ASSEMBLE_REF,
    _JOB_STATE_BUNDLE_ARTIFACT,
    _JOB_STATE_BUNDLE_DIGEST,
    _JOB_STATE_READY_CLOSURE,
    _JOB_STATE_READY_CLOSURE_REF,
    _active_history_compare_transaction,
    _assert_history_bundle_binding,
    _load_step,
    _pin_history_compare_refs,
    _required_ready_refs,
    _sides_from_materialize_checkpoint,
    _storage_facts_for_binding,
    history_compare_assemble_state_from_checkpoint,
    history_compare_ready_ref,
    ready_closure_refs_from_assemble,
)
from gateway_backend.application.history.compare_jobs.failures import (
    _assert_runtime_ruleset,
    _make_cancelled_terminal_builder,
    _publish_commit_unavailable_failure,
    _publish_ruleset_mismatch_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.history.compare_jobs.materialize import (
    _validate_described_sides,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
    HistoryCompareInputError,
    HistoryCompareJobError,
    HistoryCompareJobPayload,
    HistoryCompareRulesetVersionMismatch,
    HistoryCompareRuntimeDependencies,
    _load_history_compare_payload,
    history_compare_assemble_job_definition,
    history_compare_materialize_job_definition,
    history_compare_step_id,
)

_LOG = logging.getLogger(__name__)


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
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
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
            step_id=history_compare_step_id(
                operation.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE
            ),
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
        sides = _sides_from_materialize_checkpoint(
            materialize_envelope.job_state, deps.artifact_store, repository_id=payload.repository_id
        )

        def publish_cancelled() -> None:
            lease_session.publish_operation(_make_cancelled_terminal_builder())

        assembled_result: tuple[dict[str, object], ArtifactRef, str] | None = None
        try:
            _validate_described_sides(payload, deps, sides)
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
            if exc.retryable:
                raise HandlerExecutionFailure(
                    retryable=True,
                    diagnostic_code=f"repository.{exc.code.value.lower()}",
                    reason=exc.message,
                ) from exc
            _publish_commit_unavailable_failure(
                lease_session=lease_session,
                operation=operation,
                step=step,
                message=exc.message,
                diagnostic_code=exc.code.value,
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED
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

        if step.checkpoint_ref is None:
            try:
                assembled_result = _assemble_comparison(
                    payload=payload,
                    operation_id=operation.operation_id,
                    sides=sides,
                    rule_set=rule_set,
                    store=deps.artifact_store,
                    lease_session=lease_session,
                    control=control,
                    on_cancel=publish_cancelled,
                    export_cache=deps.snapshot_export_cache,
                    dependencies=deps,
                )
            except PairPipelineCancelled:
                return ExecutorAcknowledgment.PUBLISHED
            except RepositoryProviderError as exc:
                if exc.retryable:
                    raise HandlerExecutionFailure(
                        retryable=True,
                        diagnostic_code=f"repository.{exc.code.value.lower()}",
                        reason=exc.message,
                    ) from exc
                _publish_commit_unavailable_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=exc.message,
                    diagnostic_code=exc.code.value,
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED
            except HistoryCompareInputError as exc:
                _publish_commit_unavailable_failure(
                    lease_session=lease_session,
                    operation=operation,
                    step=step,
                    message=str(exc),
                    diagnostic_code=exc.diagnostic_code,
                    control=control,
                )
                return ExecutorAcknowledgment.PUBLISHED

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
            ready_closure_ref = history_compare_ready_ref(envelope.job_state)
            closure = load_ready_closure(deps.artifact_store, ready_closure_ref)
            _assert_history_bundle_binding(envelope.job_state, closure.artifact_refs())
            verify_structure_audit_bindings(
                deps.artifact_store,
                _assemble_state.get("structure_audit_bindings"),
                closure.artifact_refs(),
                _assemble_state.get("pair_ids"),
            )
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
            assert assembled_result is not None
            assemble_state, bundle_manifest_ref, bundle_digest = assembled_result
            ready_refs = ready_closure_refs_from_assemble(assemble_state, bundle_manifest_ref)
            verify_structure_audit_bindings(
                deps.artifact_store,
                assemble_state.get("structure_audit_bindings"),
                ready_refs,
                assemble_state.get("pair_ids"),
            )
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
                checkpoint_generation=checkpoint_generation(step),
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
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=HISTORY_COMPARE_STEP_PUBLISH,
                successor_step_id=history_compare_step_id(
                    operation.operation_id, HISTORY_COMPARE_STEP_PUBLISH
                ),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


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
    export_cache: SnapshotTableExportCachePort | None = None,
    dependencies: HistoryCompareRuntimeDependencies | None = None,
) -> tuple[dict[str, object], ArtifactRef, str]:
    pair_specs: list[tuple[str, HistoryCompareNodeBinding, HistoryCompareNodeBinding]] = []
    for index in range(payload.pair_count):
        before_node = payload.nodes[index]
        current_node = payload.nodes[index + 1]
        pair_id = (
            "left_to_right"
            if payload.pair_count == 1
            else ("left_to_middle", "middle_to_right")[index]
        )
        pair_specs.append((pair_id, before_node, current_node))

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
            BundleInput(index, node.ref_id, f"node-{index}")
            for index, node in enumerate(payload.nodes)
        )
        bundle_indexes = {
            pair_specs[0][0]: (0, 1),
            pair_specs[1][0]: (1, 2),
        }

    presentations = (
        _history_presentations(payload, dependencies) if dependencies is not None else {}
    )
    if set(presentations) != set(sides):
        raise HistoryCompareJobError("comparison requires frozen presentation for every commit")
    sides = {
        commit: dataclasses.replace(bound, presentation=presentations[commit])
        for commit, bound in sides.items()
    }
    dedup_session = declare_pair_comparison_session(
        tuple(
            ComparisonRequest(
                pair_id=pair_id,
                before=sides[before_node.commit_id],
                current=sides[current_node.commit_id],
                rule_set=rule_set,
                mode=ComparisonMode.DETAILED,
            )
            for pair_id, before_node, current_node in pair_specs
        ),
        computation_cache=None if dependencies is None else dependencies.computation_cache,
        cache_owner=CacheOperationOwner("history-compare-operation", operation_id),
        repository_id=payload.repository_id,
    )
    table_exports: dict[str, dict[str, ArtifactRef]] = {}
    try:
        if dependencies is not None:
            sides, table_exports = _ensure_history_demands(
                payload, dependencies, sides, pair_specs, rule_set, dedup_session
            )
        for pair_id, before_node, current_node in pair_specs:
            lease_session.refresh_control()
            if control.cancel_requested:
                on_cancel()
                raise PairPipelineCancelled
            before = sides[before_node.commit_id]
            current = sides[current_node.commit_id]
            descriptors = current.summary.tables
            input_shape(
                current.snapshot.snapshot_digest.value,
                table_count=len(descriptors),
                total_rows=sum(item.row_count for item in descriptors),
                max_table_rows=max((item.row_count for item in descriptors), default=0),
            )
            pair_state = _run_pair_pipeline(
                pair_id=pair_id,
                before=before,
                current=current,
                before_presentation=presentations[before_node.commit_id],
                current_presentation=presentations[current_node.commit_id],
                rule_set=rule_set,
                store=store,
                control=control,
                on_cancel=on_cancel,
                repository_id=payload.repository_id,
                export_cache=export_cache,
                dedup_session=dedup_session,
                table_exports=table_exports or None,
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
                        store=store,
                        repository_id=payload.repository_id,
                        export_cache=export_cache,
                        table_exports=table_exports or None,
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
            "structure_audit_bindings": [
                structure_audit_binding(
                    item.pair_id, item.comparison_digest, item.structure_audit_ref
                )
                for item in pair_results
            ],
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
                for item in _required_ready_refs(
                    pair_results,
                    bundle_result.bundle.manifest_ref,
                    bundle_result.referenced_artifacts,
                )
            ],
        }
        return (
            assemble_state,
            bundle_result.bundle.manifest_ref,
            bundle_result.bundle.bundle_digest.value,
        )

    finally:
        if dedup_session is not None:
            dedup_session.close()
        if dependencies is not None and dependencies.computation_cache is not None:
            dependencies.computation_cache.release_operation_pins(
                CacheOperationOwner("history-compare-operation", operation_id)
            )


@timed("materialize")
def _ensure_history_demands(
    payload: HistoryCompareJobPayload,
    deps: HistoryCompareRuntimeDependencies,
    sides: dict[str, BoundSnapshotInput],
    pair_specs: list[tuple[str, HistoryCompareNodeBinding, HistoryCompareNodeBinding]],
    rule_set: ComparisonRuleSet,
    session: ComparisonTaskSession | None,
) -> tuple[dict[str, BoundSnapshotInput], dict[str, dict[str, ArtifactRef]]]:
    try:
        return _ensure_history_demands_once(payload, deps, sides, pair_specs, rule_set, session)
    except (MemoryError, ArtifactRepairBusyError) as exc:
        # Hits are optional until row admission/repair succeeds. Releasing them also
        # removes the reason these tables had no row demand; rebuild that
        # demand from the same planner once, against the same exact commits.
        if session is None or (isinstance(exc, MemoryError) and not session.persistent_ready):
            raise
        session.close_persistent()
        session.evict_local()
        context = current_kernel_context()
        if context is not None:
            context.checkpoint()
        return _ensure_history_demands_once(payload, deps, sides, pair_specs, rule_set, session)


def _ensure_history_demands_once(
    payload: HistoryCompareJobPayload,
    deps: HistoryCompareRuntimeDependencies,
    sides: dict[str, BoundSnapshotInput],
    pair_specs: list[tuple[str, HistoryCompareNodeBinding, HistoryCompareNodeBinding]],
    rule_set: ComparisonRuleSet,
    session: ComparisonTaskSession | None,
) -> tuple[dict[str, BoundSnapshotInput], dict[str, dict[str, ArtifactRef]]]:
    context = current_kernel_context()
    if context is None:
        raise HistoryCompareJobError("history rows require the operation context")
    demands: dict[str, set[str]] = {commit: set() for commit in sides}
    table_commit = {
        id(table): commit
        for commit, bound in sides.items()
        if bound.table_set is not None
        for table in bound.table_set.tables
    }
    for pair_id, before_node, current_node in pair_specs:
        plan = plan_comparison(
            ComparisonRequest(
                pair_id=pair_id,
                before=sides[before_node.commit_id],
                current=sides[current_node.commit_id],
                rule_set=rule_set,
                mode=ComparisonMode.DETAILED,
            )
        )
        if not isinstance(plan, ComparisonPlan):
            raise HistoryCompareJobError("history comparison planning failed")
        for table in (
            *comparison_row_demands(plan, session),
            *navigation_row_demands(plan, same_complete_table_identity),
        ):
            demands[table_commit[id(table)]].add(table.descriptor.table_name)
    exports: dict[str, dict[str, ArtifactRef]] = {}
    for commit, bound in sides.items():
        assert bound.table_set is not None
        refs = exports.setdefault(bound.snapshot.snapshot_id, {})
        for table in bound.table_set.tables:
            ref = lookup_snapshot_table_parquet(
                table,
                store=deps.artifact_store,
                repository_id=payload.repository_id,
                export_cache=deps.snapshot_export_cache,
            )
            if ref is None:
                demands[commit].add(table.descriptor.table_name)
            else:
                refs[table.descriptor.table_name] = ref
    export_hits = sum(len(refs) for refs in exports.values())
    loaded: dict[str, BoundSnapshotInput] = {}
    existing_readers = {
        id(table.reader)
        for bound in sides.values()
        if bound.table_set is not None
        for table in bound.table_set.tables
        if table.reader is not None
    }
    existing_batches = {
        id(table.batch_reader)
        for bound in sides.values()
        if bound.table_set is not None
        for table in bound.table_set.tables
        if table.batch_reader is not None
    }
    control_metadata_resolves = 0
    access = build_committed_table_access(
        store=cast(ArtifactBufferStorePort, deps.artifact_store),
        unit_of_work_factory=deps.control_transaction_factory,
        repository_provider_factory=deps.repository_provider_factory,
        repository_id=payload.repository_id,
    )
    bindings: dict[str, CanonicalBinding] = {}
    try:
        for commit, bound in sides.items():
            context.checkpoint()
            assert bound.table_set is not None
            with deps.control_transaction_factory() as uow:
                control_metadata_resolves += 1
                try:
                    metadata = uow.commit_canonical_metadata.resolve(
                        repository_id=payload.repository_id,
                        commit_id=commit,
                        scope=CommitCanonicalScope(
                            gateway_device_external_key=payload.gateway_device_external_key,
                            business_project_id=payload.business_project_id,
                        ),
                    )
                except CommitCanonicalMetadataError as exc:
                    raise HistoryCompareInputError(
                        exc.diagnostic, diagnostic_code=exc.code.value
                    ) from exc
            binding = canonical_binding_for_commit(metadata, runtime_ruleset=rule_set.snapshot)
            if (
                _storage_facts_for_binding(
                    binding, {table.table_name for table in bound.summary.tables}
                )
                != bound.storage_facts
            ):
                raise HistoryCompareInputError(
                    "exact commit storage binding differs from frozen metadata"
                )
            bindings[commit] = binding
        # Cross-commit preparation also precedes the first retained row reader.
        for commit, bound in sides.items():
            assert bound.table_set is not None
            binding = bindings[commit]
            views = {view.canonical_table: view for view in binding.tables}
            identities = {
                identity.canonical_table: identity for identity in binding.table_identities
            }
            for table in bound.table_set.tables:
                name = table.descriptor.table_name
                if name in demands[commit] and table.reader is None:
                    access.prepare_table(
                        commit_id=commit,
                        descriptor=table.descriptor,
                        identity=identities[name],
                        storage_view=views[name],
                        context=ParserInvocationContext(
                            context.cancel_probe, context.deadline_monotonic
                        ),
                        timeout_policy=None,
                    )
        for commit, bound in sides.items():
            assert bound.table_set is not None
            binding = bindings[commit]
            tables = ensure_committed_tables(
                bound.table_set,
                repository_ref=RepositoryRef(repository_id=payload.repository_id, ref=commit),
                canonical_binding=binding,
                committed_tables=access,
                requested_tables=tuple(sorted(demands[commit])),
                context=ParserInvocationContext(context.cancel_probe, context.deadline_monotonic),
            )
            loaded[commit] = dataclasses.replace(bound, table_set=tables)
            refs = exports[bound.snapshot.snapshot_id]
            for table in tables.tables:
                if table.descriptor.table_name not in refs:
                    refs[table.descriptor.table_name] = export_snapshot_table_parquet(
                        table,
                        store=deps.artifact_store,
                        repository_id=payload.repository_id,
                        export_cache=deps.snapshot_export_cache,
                    )
    except BaseException:
        for completed in loaded.values():
            if completed.table_set is not None:
                for table in completed.table_set.tables:
                    if table.reader is not None and id(table.reader) not in existing_readers:
                        table.reader.close()
                    if (
                        table.batch_reader is not None
                        and id(table.batch_reader) not in existing_batches
                    ):
                        table.batch_reader.close()
        raise
    _LOG.info(
        "s5_history_demands %s",
        json.dumps(
            {
                "demanded_tables": sum(map(len, demands.values())),
                "export_cache_hits": export_hits,
                "control_metadata_resolves": control_metadata_resolves,
            }
        ),
    )
    return loaded, exports


def _history_presentations(
    payload: HistoryCompareJobPayload, deps: HistoryCompareRuntimeDependencies
) -> dict[str, PresentationMetadata]:
    presentations = {}
    for commit_id in dict.fromkeys(node.commit_id for node in payload.nodes):
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
                raise HistoryCompareInputError(
                    exc.diagnostic, diagnostic_code=exc.code.value
                ) from exc
        presentations[commit_id] = presentation_for_commit(metadata)
    return presentations


def _run_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    rule_set: ComparisonRuleSet,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
    repository_id: str | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
    dedup_session: ComparisonTaskSession | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
    before_presentation: PresentationMetadata,
    current_presentation: PresentationMetadata,
) -> _PairPipelineResult:
    try:
        return run_history_pair_pipeline(
            before_presentation=before_presentation,
            current_presentation=current_presentation,
            pair_id=pair_id,
            before=before,
            current=current,
            rule_set=rule_set,
            store=store,
            control=control,
            on_cancel=on_cancel,
            repository_id=repository_id,
            export_cache=export_cache,
            dedup_session=dedup_session,
            table_exports=table_exports,
        )
    except PairPipelineCancelled:
        raise
    except PairPipelineError as exc:
        raise HistoryCompareJobError(str(exc)) from exc


__all__ = [
    "build_assemble_comparison_handler",
]
