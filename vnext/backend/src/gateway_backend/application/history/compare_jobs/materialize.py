"""History compare step 1: distinct commit snapshot materialization."""

from __future__ import annotations

import dataclasses
import json
import logging

from gateway_backend.application.canonical_metadata.binding import canonical_binding_for_commit
from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.canonical_metadata.table_access import build_committed_table_access
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    make_successor_builder,
    pinned_checkpoint_builder,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import (
    ArtifactBufferStorePort,
    ArtifactStorePort,
)
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.snapshot_materialization import (
    current_kernel_context,
    describe_repository_ref,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    CommittedCanonicalTablesPort,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryProviderError,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
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
from gateway_backend.statistics.metrics import bind_scope
from typing import cast

from gateway_backend.application.history.compare_jobs.checkpoint import (
    HISTORY_COMPARE_MATERIALIZED_SIDES_CONTRACT_VERSION,
    HISTORY_COMPARE_MATERIALIZED_SIDES_DOCUMENT_TYPE,
    _JOB_STATE_MATERIALIZED_SIDES_REF,
    _JOB_STATE_SIDES,
    _active_history_compare_transaction,
    _bound_from_materialization,
    _closed_refs_from_sides,
    _materialized_sides_ref_from_checkpoint,
    _pin_history_compare_refs,
    _serialize_sides,
    _sides_from_materialize_checkpoint,
)
from gateway_backend.application.history.compare_jobs.failures import (
    _assert_runtime_ruleset,
    _make_cancelled_terminal_builder,
    _publish_commit_unavailable_failure,
    _publish_ruleset_mismatch_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HistoryCompareJobError,
    HistoryCompareJobPayload,
    HistoryCompareRulesetVersionMismatch,
    HistoryCompareRuntimeDependencies,
    _load_history_compare_payload,
    history_compare_materialize_job_definition,
    history_compare_step_id,
)

_LOG = logging.getLogger(__name__)


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
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
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
                repository_id=payload.repository_id,
            )
        try:
            if step.checkpoint_ref is None:
                sides = _materialize_distinct_commits(payload, deps)
            else:
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
            assert exc.retryable, (
                "repository_ref must return deterministic provider errors as diagnostics"
            )
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

        if step.checkpoint_ref is not None:
            sides_ref = _materialized_sides_ref_from_checkpoint(envelope.job_state)
            _pin_history_compare_refs(
                deps,
                (step.checkpoint_ref, sides_ref, *_closed_refs_from_sides(sides)),
                owner_kind="history-compare-checkpoint",
                owner_id=step.step_id,
                intent="materialize-checkpoint",
            )
        else:
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
                checkpoint_generation=checkpoint_generation(step),
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
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=HISTORY_COMPARE_STEP_ASSEMBLE,
                successor_step_id=history_compare_step_id(
                    operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE
                ),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


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
            committed_tables=build_committed_table_access(
                store=cast(ArtifactBufferStorePort, deps.artifact_store),
                unit_of_work_factory=deps.control_transaction_factory,
                repository_provider_factory=deps.repository_provider_factory,
                repository_id=payload.repository_id,
            ),
        )
        sides[commit_id] = bound
    _LOG.info(
        "s5_history_metadata %s",
        json.dumps(
            {
                "distinct_commits": len(distinct_commits),
                "canonical_metadata_reads": len(distinct_commits),
                "catalog_reads": len(distinct_commits),
            }
        ),
    )
    return sides


def _materialize_commit(
    *,
    repository_id: str,
    commit_id: str,
    provider: RepositoryTableAccessProvider,
    store: ArtifactStorePort,
    canonical_binding: CanonicalBinding,
    ruleset: TableRulesetSnapshot,
    requested_tables: tuple[str, ...] | None = None,
    export_tables: tuple[str, ...] | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
    committed_tables: CommittedCanonicalTablesPort | None = None,
) -> BoundSnapshotInput:
    operation_context = current_kernel_context()
    if operation_context is None:
        raise ValueError("repository materialization requires an operation kernel context")
    request = RepositoryRefMaterializationRequest(
        repository_ref=RepositoryRef(repository_id=repository_id, ref=commit_id),
        provider=provider,
        ruleset=ruleset,
        canonical_binding=canonical_binding,
        table_ruleset_version=TABLE_RULESET_VERSION,
        materialization_stage=MaterializationStage.FINAL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        context=ParserInvocationContext(
            operation_context.cancel_probe, operation_context.deadline_monotonic
        ),
        requested_tables=requested_tables,
        committed_tables=committed_tables,
        export_tables=export_tables,
        artifact_store=store,
        export_cache=export_cache,
    )
    result = describe_repository_ref(request)
    if result.status is not SnapshotMaterializationStatus.COMPLETE:
        diagnostic = result.diagnostics[0] if result.diagnostics else None
        code = None if diagnostic is None else diagnostic.code.value
        raise HistoryCompareJobError(
            "commit materialization failed" if diagnostic is None else diagnostic.message,
            diagnostic_code=code,
        )
    return _bound_from_materialization(result, canonical_binding=canonical_binding)


def _validate_described_sides(
    payload: HistoryCompareJobPayload,
    deps: HistoryCompareRuntimeDependencies,
    sides: dict[str, BoundSnapshotInput],
) -> None:
    fresh = _materialize_distinct_commits(payload, deps)
    # created_at records when this operation described the same authority;
    # it is not an exact-commit identity or a digest input.
    comparable = {
        commit: dataclasses.replace(
            bound,
            snapshot=dataclasses.replace(
                bound.snapshot, created_at=sides[commit].snapshot.created_at
            ),
        )
        for commit, bound in fresh.items()
        if commit in sides
    }
    if set(fresh) != set(sides) or _serialize_sides(comparable) != _serialize_sides(sides):
        raise CheckpointDecodeError(
            "history metadata checkpoint differs from exact commit authority",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )


__all__ = [
    "build_materialize_inputs_handler",
]
