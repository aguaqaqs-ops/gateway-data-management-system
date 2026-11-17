"""Submit step 1: freeze and publish canonical import input."""

from __future__ import annotations

from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    load_checkpoint_envelope,
    load_ready_closure,
)
from gateway_backend.application.job_steps import (
    make_successor_builder,
    unique_artifact_refs,
)
from gateway_backend.application.kernel_execution import reserved_artifact_bytes
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.submission.contracts import PrepareImportBuildInput
from gateway_backend.application.submission.errors import (
    PrepareCheckpointPayloadBindingError,
    SubmitImportPublicationError,
)
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    derive_removed_tables,
    publish_prepare_import_package,
    resolve_canonical_snapshot_bindings,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    submit_successor_step_id as _successor_step_id,
)
from gateway_backend.application.submission.ports import RepositoryParentCatalogPort
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.table_access import current_kernel_context
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    StepRecord,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)
from gateway_backend.statistics.metrics import bind_scope

from gateway_backend.application.submit_jobs.checkpoint import (
    _pin_prepare_refs,
    _pin_submit_checkpoint_refs,
    _prepare_checkpoint_extra_refs,
    _prepare_checkpoint_from_job_state,
    _prepare_step_checkpoint,
)
from gateway_backend.application.submit_jobs.failures import (
    _make_cancelled_terminal_builder,
    _publish_prepare_binding_failure,
    _publish_prepare_projection_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.submit_jobs.payload import (
    SubmitControlTransactionFactory,
    SubmitJobError,
    SubmitJobPayload,
    SubmitRuntimeDependencies,
    _assert_payload_matches_attempt,
    _definition_for_step,
    _load_submit_attempt,
    _load_submit_payload,
)


def build_prepare_import_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    prepare_definition = _definition_for_step(SUBMIT_STEP_PREPARE)

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

        payload = _load_submit_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, payload.submit_attempt_id)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
        _assert_payload_matches_attempt(payload, attempt)
        if attempt.state is not SubmitAttemptState.PREPARED:
            raise SubmitJobError("prepare_import requires PREPARED attempt")

        try:
            if step.checkpoint_ref is not None:
                envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
                if not definition_matches_checkpoint(prepare_definition, envelope):
                    raise CheckpointDecodeError(
                        "checkpoint envelope does not match the prepare_import JobDefinition",
                        code="CHECKPOINT_IDENTITY_MISMATCH",
                    )
                prepare_checkpoint = _prepare_checkpoint_from_job_state(
                    envelope.job_state,
                    expected_attempt_id=payload.submit_attempt_id,
                )
                build_input = _build_prepare_import_build_input(
                    payload=payload,
                    attempt=attempt,
                    operation=operation,
                    store=deps.artifact_store,
                    parent_catalog=deps.parent_catalog,
                    control_transaction_factory=deps.control_transaction_factory,
                )
                reuse_prepare_import_checkpoint(
                    build_input=build_input,
                    checkpoint=prepare_checkpoint,
                    publication=deps.publication,
                    store=deps.artifact_store,
                )
                _pin_prepare_refs(
                    deps=deps,
                    attempt=attempt,
                    operation=operation,
                    checkpoint=prepare_checkpoint,
                )
                with deps.control_transaction_factory() as unit_of_work:
                    _pin_submit_checkpoint_refs(
                        unit_of_work,
                        step_id=step.step_id,
                        checkpoint_ref=step.checkpoint_ref,
                        extra_refs=_prepare_checkpoint_extra_refs(prepare_checkpoint),
                        intent="prepare-import-checkpoint",
                    )
            else:
                build_input = _build_prepare_import_build_input(
                    payload=payload,
                    attempt=attempt,
                    operation=operation,
                    store=deps.artifact_store,
                    parent_catalog=deps.parent_catalog,
                    control_transaction_factory=deps.control_transaction_factory,
                )
                publication = publish_prepare_import_package(
                    build_input=build_input,
                    publication=deps.publication,
                    store=deps.artifact_store,
                )
                _prepare_step_checkpoint(
                    deps=deps,
                    definition=prepare_definition,
                    operation=operation,
                    step=step,
                    checkpoint=publication.checkpoint,
                    lease_session=lease_session,
                    attempt=attempt,
                    operation_record=operation,
                )
        except SubmitImportPublicationError as exc:
            context = current_kernel_context()
            if context is not None:
                context.checkpoint()
            _publish_prepare_projection_failure(lease_session, exc)
            return ExecutorAcknowledgment.PUBLISHED
        except PrepareCheckpointPayloadBindingError:
            _publish_prepare_binding_failure(lease_session)
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=SUBMIT_STEP_SUBMIT,
                successor_step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_SUBMIT),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(execute)


def _read_prepare_manifest(store: ArtifactStorePort, ref: ArtifactRef) -> bytes:
    context = current_kernel_context()
    if context is None:
        raise SubmitJobError("prepare manifest read requires an operation context")
    # Frozen closure/schema JSON and returned bytes remain conservatively charged
    # through the execution; discarded READY row-file verification is short-lived.
    context.resources.enter_context(context.memory.reserve(ref.size_bytes * 32 + 4096))
    with reserved_artifact_bytes(store, ref) as payload:
        return payload


def _build_prepare_import_build_input(
    *,
    payload: SubmitJobPayload,
    attempt: SubmitAttempt,
    operation: OperationRecord,
    store: ArtifactStorePort,
    parent_catalog: RepositoryParentCatalogPort,
    control_transaction_factory: SubmitControlTransactionFactory,
) -> PrepareImportBuildInput:
    try:
        ready_closure_ref = next(
            (
                ref
                for ref in operation.artifact_refs
                if ref.artifact_id == attempt.preview_ready_closure_ref
            ),
            None,
        )
        if ready_closure_ref is None:
            raise SubmitImportBuilderError("operation is missing the preview ready closure ref")
        ready_closure_refs = load_ready_closure(store, ready_closure_ref).artifact_refs()
        snapshot_tables, canonical_refs = resolve_canonical_snapshot_bindings(
            operation_artifact_refs=unique_artifact_refs(
                (*operation.artifact_refs, *ready_closure_refs)
            ),
            canonical_table_set_closure_ref=attempt.canonical_table_set_closure_ref,
            canonical_table_set_closure_digest=attempt.canonical_table_set_closure_digest,
            canonicalization_manifest_ref=attempt.canonicalization_manifest_ref,
            canonicalization_manifest_digest=attempt.canonicalization_manifest_digest,
            read_artifact=lambda ref: _read_prepare_manifest(store, ref),
        )
        canonical_refs_by_id = {ref.artifact_id: ref for ref in canonical_refs}
        closure_ref = canonical_refs_by_id[attempt.canonical_table_set_closure_ref]
        manifest_ref = canonical_refs_by_id[attempt.canonicalization_manifest_ref]
        with control_transaction_factory() as unit_of_work:
            workspace = unit_of_work.workspace.get_workspace(attempt.workspace_id)
            if workspace is None or workspace.repository_id != attempt.repository_id:
                raise SubmitImportBuilderError("submit parent canonical scope is unavailable")
            try:
                parent_metadata = unit_of_work.commit_canonical_metadata.resolve(
                    repository_id=attempt.repository_id,
                    commit_id=attempt.repository_expected_commit_id,
                    scope=CommitCanonicalScope(
                        gateway_device_external_key=workspace.gateway_device_external_key,
                        business_project_id=workspace.business_project_id,
                    ),
                )
            except CommitCanonicalMetadataError as exc:
                raise SubmitImportBuilderError(exc.diagnostic) from exc
        parent_manifest = parent_metadata.manifest
        parent_is_initial = parent_metadata.initial
        parent_manifest_digest = (
            None
            if parent_manifest is None or parent_manifest.manifest_digest is None
            else parent_manifest.manifest_digest.value
        )
        if not parent_is_initial and parent_manifest_digest is None:
            raise SubmitImportBuilderError("parent canonical manifest digest is missing")
        parent_table_names = parent_catalog.get_table_names(
            repository_id=attempt.repository_id,
            commit_id=attempt.repository_expected_commit_id,
        )
        if parent_is_initial:
            if parent_table_names:
                raise SubmitImportBuilderError("INITIAL parent catalog is not empty")
        elif parent_manifest is None or set(parent_table_names) != {
            table.name for table in parent_manifest.tables
        }:
            raise SubmitImportBuilderError("parent catalog and canonical manifest disagree")
        removed_tables = derive_removed_tables(
            parent_table_names=parent_table_names,
            snapshot_tables=snapshot_tables,
        )
    except CheckpointPublicationError as exc:
        raise SubmitImportPublicationError(
            "frozen canonical input is unavailable or corrupt: " + str(exc)
        ) from exc
    except SubmitImportBuilderError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc
    return PrepareImportBuildInput(
        submit_attempt_id=payload.submit_attempt_id,
        builder_mutation_policy=payload.builder_mutation_policy,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=payload.canonical_table_set_closure_digest,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=payload.canonicalization_manifest_digest,
        expected_parent_commit_id=payload.repository_expected_commit_id,
        repository_id=attempt.repository_id,
        parent_manifest=parent_manifest,
        parent_manifest_digest=parent_manifest_digest,
        parent_is_initial=parent_is_initial,
        removed_tables=removed_tables,
        source_artifact_digest=attempt.snapshot_digest,
        snapshot_tables=snapshot_tables,
    )


__all__ = [
    "build_prepare_import_handler",
]
