"""Preview step 1: three-side snapshot materialization."""

from __future__ import annotations

import dataclasses
import json
import logging

from collections.abc import Callable
from contextlib import ExitStack
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
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    make_successor_builder,
    pinned_checkpoint_builder,
)
from gateway_backend.application.kernel_execution import (
    reserved_artifact_bytes,
    stage_operation_source,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.canonical_table_store import CanonicalTableKey
from gateway_backend.artifacts.serialize import (
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import (
    ArtifactBufferStorePort,
    ArtifactStorePort,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.comparison import BoundSnapshotInput
from gateway_backend.capabilities.composite_signal.contracts import (
    empty_composite_logic_source,
    present_composite_logic_source,
)
from gateway_backend.capabilities.snapshot_materialization import (
    materialize_business_snapshot,
    materialize_canonical_snapshot,
    materialize_repository_ref,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BusinessSnapshotMaterializationRequest,
    CanonicalBinding,
    CommittedCanonicalTablesPort,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryProviderError,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    SCALAR_ENCODING_VERSION,
    SnapshotMaterializationStatus,
    SqlSnapshotMaterializationRequest,
    canonical_state_digest_of,
)
from gateway_backend.capabilities.source_package_staging import (
    PackageKind,
    SourcePackageInput,
    StagingInvocationContext,
    StagingStatus,
    StagingTransport,
    resolve_sql_dump_source,
)
from gateway_backend.capabilities.source_package_staging.contracts import NeverCancel
from gateway_backend.capabilities.storage_projection import (
    CanonicalProjectionResult,
    ProjectionStatus,
    PublicationError,
    open_canonicalization_manifest,
    project_canonical_arrow_table_set,
    publish_canonicalization_manifest,
)
from gateway_backend.capabilities.storage_projection.contracts import STORAGE_PROJECTION_VERSION
from gateway_backend.capabilities.table_access import (
    KernelMemoryLimit,
    current_kernel_context,
    parse_arrow_sql,
    parse_xml,
)
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    ParseResult,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
    XmlParseRequest,
    XmlSourceInput,
)
from gateway_backend.capabilities.table_presentation.contracts import PresentationMetadata
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
from gateway_backend.domain.baseline.models import BaselineNodeKind
from gateway_backend.domain.configuration_facts import (
    CONFIGURATION_FACTS_SCHEMA,
    CanonicalContentIdentity,
    ConfigurationFacts,
    ConfigurationGeneratedTime,
    ConfigurationSideFacts,
)
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from gateway_backend.operations.contracts import (
    OperationDiagnosticDetail,
    OperationDiagnosticSide,
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
)
from gateway_shared_kernel import (
    DigestRef,
    raw_blob_digest,
)
from time import perf_counter
from typing import cast

from gateway_backend.application.preview_jobs.checkpoint import (
    PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
    PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
    _CanonicalPreviewMetadata,
    _JOB_STATE_CANONICAL,
    _JOB_STATE_MATERIALIZED_SIDES_REF,
    _JOB_STATE_SIDES,
    _MaterializedPreviewInputs,
    _active_preview_transaction,
    _assert_configuration_payload,
    _bound_from_materialization,
    _canonical_preview_metadata_to_document,
    _closed_refs_from_preview_inputs,
    _comparison_storage_facts,
    _pin_preview_refs,
    _publish_canonical_table_set_closure,
    _same_resolved_rules,
    _serialize_sides,
)
from gateway_backend.application.preview_jobs.failures import (
    _make_cancelled_terminal_builder,
    _publish_preview_materialization_failure,
    _publish_preview_ruleset_mismatch_if_needed,
    _restore_preview_inputs_or_publish_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.preview_jobs.payload import (
    PREVIEW_STEP_ASSEMBLE,
    PreviewJobError,
    PreviewJobPayload,
    PreviewRuntimeDependencies,
    _SIDE_BASELINE,
    _SIDE_INITIAL,
    _SIDE_MODIFIED,
    _artifact_ref_from_binding,
    _load_preview_payload,
    _successor_step_id,
    preview_materialize_job_definition,
)

_LOG = logging.getLogger(__name__)


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
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
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
            inputs = _restore_preview_inputs_or_publish_failure(
                envelope.job_state,
                repository_id=payload.repository_id,
                deps=deps,
                operation=operation,
                step=step,
                lease_session=lease_session,
                control=control,
            )
            if inputs is None:
                return ExecutorAcknowledgment.PUBLISHED
            materialized_sides_ref = artifact_ref_from_dict(
                cast(dict[str, object], envelope.job_state[_JOB_STATE_MATERIALIZED_SIDES_REF])
            )
            _assert_configuration_payload(
                inputs.canonical.configuration_facts, payload, operation.operation_id
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
                inputs = _materialize_all_sides(payload, deps, operation_id=operation.operation_id)
            except RepositoryProviderError as exc:
                assert exc.retryable, (
                    "repository_ref must return deterministic provider errors as diagnostics"
                )
                raise HandlerExecutionFailure(
                    retryable=True,
                    diagnostic_code=f"repository.{exc.code.value.lower()}",
                    reason=exc.message,
                ) from exc
            except PreviewJobError as exc:
                if exc.diagnostic_code is None:
                    raise
                _publish_preview_materialization_failure(
                    operation=operation,
                    step=step,
                    lease_session=lease_session,
                    diagnostic_code=exc.diagnostic_code,
                    message=str(exc),
                    diagnostic_details=exc.diagnostic_details,
                    diagnostic_omitted_count=exc.diagnostic_omitted_count,
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
                checkpoint_generation=checkpoint_generation(step),
                job_state={
                    _JOB_STATE_MATERIALIZED_SIDES_REF: artifact_ref_to_dict(materialized_sides_ref),
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
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=PREVIEW_STEP_ASSEMBLE,
                successor_step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_ASSEMBLE),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


def _materialize_all_sides(
    payload: PreviewJobPayload,
    deps: PreviewRuntimeDependencies,
    *,
    operation_id: str,
) -> _MaterializedPreviewInputs:
    runtime_ruleset = migrated_table_ruleset_snapshot()
    if runtime_ruleset.ruleset_digest is None:
        raise PreviewJobError("storage projection ruleset digest is missing")
    canonical_binding = _preview_baseline_binding(payload, deps, runtime_ruleset)
    provider = deps.repository_provider_factory(
        payload.repository_id,
        payload.business_baseline_commit_id,
    )
    uploaded_side_specs: list[tuple[OperationDiagnosticSide, SourceArtifactBinding]] = []
    if payload.input_completeness is InputCompleteness.FULL:
        uploaded_side_specs.append(
            (OperationDiagnosticSide.INITIAL, payload.source_artifacts[SourceArtifactRole.INITIAL])
        )
    uploaded_side_specs.append(
        (OperationDiagnosticSide.MODIFIED, payload.source_artifacts[SourceArtifactRole.MODIFIED])
    )
    uploaded_sides: dict[
        OperationDiagnosticSide,
        tuple[BoundSnapshotInput, ArtifactRef, DigestRef, ConfigurationGeneratedTime, str],
    ] = {}
    upload_errors: list[PreviewJobError] = []

    def lookup_canonical(key: CanonicalTableKey) -> ArtifactRef | None:
        with deps.control_transaction_factory() as unit_of_work:
            return unit_of_work.canonical_tables.lookup(key)

    def register_canonical(key: CanonicalTableKey, ref: ArtifactRef) -> None:
        # This is derived content/TTL registration. Checkpoint/READY/Attempt
        # references are still published only by the existing LeaseSession.
        with deps.control_transaction_factory() as unit_of_work:
            unit_of_work.canonical_tables.register(key, ref)

    for side, binding in uploaded_side_specs:
        try:
            uploaded_sides[side] = _materialize_uploaded_side(
                binding,
                deps.artifact_store,
                runtime_ruleset,
                repository_id=payload.repository_id,
                export_cache=deps.snapshot_export_cache,
                side=side,
                operation_id=operation_id,
                canonical_lookup=lookup_canonical,
                canonical_before_write=register_canonical,
            )
        except PreviewJobError as exc:
            upload_errors.append(exc)
    if upload_errors:
        projection_errors = [error for error in upload_errors if error.diagnostic_details]
        if not projection_errors:
            raise upload_errors[0]
        details = tuple(
            detail for error in projection_errors for detail in (error.diagnostic_details or ())
        )
        source_omitted_count = sum(error.diagnostic_omitted_count for error in projection_errors)
        diagnostic_count = len(details) + source_omitted_count
        first_projection_error = projection_errors[0]
        message = (
            f"uploaded canonical projection failed ({diagnostic_count} diagnostic(s)); "
            f"{first_projection_error}"
        )
        other_error = next(
            (error for error in upload_errors if error.diagnostic_details is None),
            None,
        )
        if other_error is not None:
            message += f"; other upload failure: {other_error}"
        raise PreviewJobError(
            message,
            diagnostic_code=first_projection_error.diagnostic_code,
            diagnostic_details=details,
            diagnostic_omitted_count=source_omitted_count,
        )

    initial_manifest_ref: ArtifactRef | None = None
    initial_manifest_digest: DigestRef | None = None
    sides: dict[str, BoundSnapshotInput] = {}
    if payload.input_completeness is InputCompleteness.FULL:
        initial, initial_manifest_ref, initial_manifest_digest, _, _ = uploaded_sides[
            OperationDiagnosticSide.INITIAL
        ]
        sides[_SIDE_INITIAL] = initial
    else:
        initial = None
    sides[_SIDE_MODIFIED], manifest_ref, manifest_digest, modified_time, modified_sql_digest = (
        uploaded_sides[OperationDiagnosticSide.MODIFIED]
    )
    baseline_compare_current = initial if initial is not None else sides[_SIDE_MODIFIED]
    requested_baseline_tables = _changed_canonical_tables(
        canonical_binding,
        baseline_compare_current,
    )
    baseline = _materialize_baseline(
        payload,
        provider,
        deps.artifact_store,
        canonical_binding=canonical_binding,
        ruleset=runtime_ruleset,
        export_cache=deps.snapshot_export_cache,
        requested_tables=requested_baseline_tables,
        committed_tables=build_committed_table_access(
            store=cast(ArtifactBufferStorePort, deps.artifact_store),
            unit_of_work_factory=deps.control_transaction_factory,
            repository_provider_factory=deps.repository_provider_factory,
            repository_id=payload.repository_id,
        ),
    )
    sides[_SIDE_BASELINE] = baseline
    if payload.input_completeness is InputCompleteness.MODIFIED_ONLY:
        sides[_SIDE_INITIAL] = baseline
    baseline_state_digest = canonical_state_digest_of(baseline.summary.tables)
    if baseline_state_digest is None:
        raise PreviewJobError("baseline canonical state digest is missing")
    modified_state_digest = canonical_state_digest_of(sides[_SIDE_MODIFIED].summary.tables)
    if modified_state_digest is None:
        raise PreviewJobError("modified canonical state digest is missing")
    initial_state_digest = canonical_state_digest_of(sides[_SIDE_INITIAL].summary.tables)
    if initial_state_digest is None:
        raise PreviewJobError("initial canonical state digest is missing")
    rules_digest = runtime_ruleset.ruleset_digest

    def content(digest: DigestRef) -> CanonicalContentIdentity:
        assert rules_digest is not None
        return CanonicalContentIdentity(
            digest.value, rules_digest.value, STORAGE_PROJECTION_VERSION, SCALAR_ENCODING_VERSION
        )

    baseline_identity = content(baseline_state_digest)
    baseline_presentation = PresentationMetadata()
    with deps.control_transaction_factory() as unit_of_work:
        node = unit_of_work.baseline.get_node(payload.business_baseline_node_id)
        if (
            node is None
            or node.repository_id != payload.repository_id
            or node.commit_id != payload.business_baseline_commit_id
        ):
            raise PreviewJobError(
                "configuration baseline source binding is missing or inconsistent"
            )
        if (node.kind is BaselineNodeKind.INITIAL) != canonical_binding.is_initial:
            raise PreviewJobError("configuration baseline applicability is inconsistent")
        baseline_source_id = node.source_submission_id
        if node.kind is BaselineNodeKind.INITIAL:
            baseline_side = ConfigurationSideFacts(baseline_identity, None, None, None)
        else:
            source = (
                None
                if baseline_source_id is None
                else unit_of_work.submission.get_submission(baseline_source_id)
            )
            if (
                source is None
                or source.repository_id != payload.repository_id
                or source.repository_commit_id != node.commit_id
            ):
                raise PreviewJobError(
                    "configuration baseline source Submission is missing or inconsistent"
                )
            baseline_side = source.configuration_facts.modified
            if baseline_side.content_identity.canonical_state_digest != baseline_state_digest.value:
                raise PreviewJobError("configuration baseline content identity mismatch")
            workspace = unit_of_work.workspace.get_workspace(payload.workspace_id)
            if workspace is None:
                raise PreviewJobError("configuration baseline workspace scope is missing")
            metadata = unit_of_work.commit_canonical_metadata.resolve(
                repository_id=payload.repository_id,
                commit_id=payload.business_baseline_commit_id,
                scope=CommitCanonicalScope(
                    gateway_device_external_key=workspace.gateway_device_external_key,
                    business_project_id=workspace.business_project_id,
                ),
            )
            if (
                metadata.manifest is None
                or metadata.manifest.manifest_digest is None
                or metadata.manifest.manifest_digest.value
                != source.canonicalization_manifest_digest
            ):
                raise PreviewJobError("configuration baseline source manifest binding mismatch")
            if (
                baseline_side.content_identity.storage_projection_ruleset_digest
                != metadata.manifest.ruleset_digest.value
                or baseline_side.content_identity.storage_projection_version
                != metadata.manifest.storage_projection_version
            ):
                raise PreviewJobError(
                    "configuration baseline facts identity does not match source manifest"
                )
            baseline_identity = baseline_side.content_identity
            baseline_presentation = presentation_for_commit(metadata)
    if payload.input_completeness is InputCompleteness.FULL:
        initial_values = uploaded_sides[OperationDiagnosticSide.INITIAL]
        initial_side = ConfigurationSideFacts(
            content(initial_state_digest),
            initial_values[3],
            payload.source_artifacts[SourceArtifactRole.INITIAL].artifact_id,
            initial_values[4],
        )
        initial_origin = "UPLOADED"
    else:
        initial_side = baseline_side
        initial_origin = "INITIAL_EMPTY" if canonical_binding.is_initial else "BASELINE_REUSED"
    configuration_facts = ConfigurationFacts(
        schema=CONFIGURATION_FACTS_SCHEMA,
        operation_id=operation_id,
        workspace_id=payload.workspace_id,
        upload_revision_id=payload.upload_revision_id,
        generation=payload.generation,
        repository_id=payload.repository_id,
        business_baseline_node_id=payload.business_baseline_node_id,
        business_baseline_commit_id=payload.business_baseline_commit_id,
        baseline_head_version=payload.baseline_head_version,
        baseline_is_initial=canonical_binding.is_initial,
        baseline_source_submission_id=baseline_source_id,
        initial_origin=initial_origin,
        baseline_content_identity=baseline_identity,
        initial=initial_side,
        modified=ConfigurationSideFacts(
            content(modified_state_digest),
            modified_time,
            payload.source_artifacts[SourceArtifactRole.MODIFIED].artifact_id,
            modified_sql_digest,
        ),
    )
    closure_ref = _publish_canonical_table_set_closure(
        sides[_SIDE_MODIFIED],
        deps.artifact_store,
    )
    presentations = {
        _SIDE_BASELINE: baseline_presentation,
        _SIDE_INITIAL: (
            baseline_presentation
            if initial_manifest_ref is None
            else open_canonicalization_manifest(
                deps.artifact_store, initial_manifest_ref
            ).presentation
        ),
        _SIDE_MODIFIED: open_canonicalization_manifest(
            deps.artifact_store, manifest_ref
        ).presentation,
    }
    return _MaterializedPreviewInputs(
        sides=sides,
        presentations=presentations,
        canonical=_CanonicalPreviewMetadata(
            initial_canonical_state_digest=initial_state_digest,
            configuration_facts=configuration_facts,
            canonical_table_set_closure_ref=closure_ref,
            canonicalization_manifest_ref=manifest_ref,
            canonicalization_manifest_digest=manifest_digest,
            initial_canonicalization_manifest_ref=initial_manifest_ref,
            initial_canonicalization_manifest_digest=initial_manifest_digest,
            baseline_canonical_state_digest=baseline_state_digest,
            modified_canonical_state_digest=modified_state_digest,
            storage_projection_ruleset_digest=runtime_ruleset.ruleset_digest,
            baseline_is_initial=canonical_binding.is_initial,
            rules_semantically_equal=_same_resolved_rules(
                sides[_SIDE_BASELINE],
                sides[_SIDE_MODIFIED],
                presentations[_SIDE_BASELINE],
                presentations[_SIDE_MODIFIED],
                runtime_ruleset,
            ),
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
    export_cache: SnapshotTableExportCachePort | None = None,
    requested_tables: tuple[str, ...] | None = None,
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
        artifact_store=store,
        export_cache=export_cache,
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
    export_cache: SnapshotTableExportCachePort | None = None,
    requested_tables: tuple[str, ...] | None = None,
    committed_tables: CommittedCanonicalTablesPort | None = None,
) -> BoundSnapshotInput:
    return _materialize_baseline_commit(
        repository_id=payload.repository_id,
        commit_id=payload.business_baseline_commit_id,
        provider=provider,
        store=store,
        canonical_binding=canonical_binding,
        ruleset=ruleset,
        export_cache=export_cache,
        requested_tables=requested_tables,
        committed_tables=committed_tables,
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


def _changed_canonical_tables(
    before_binding: CanonicalBinding,
    current: BoundSnapshotInput,
) -> tuple[str, ...]:
    """Select only parent tables whose full manifest identity differs from current."""

    if before_binding.is_initial:
        return ()
    identities = {item.canonical_table: item for item in before_binding.table_identities}
    views = {item.canonical_table: item for item in before_binding.tables}
    descriptors = {item.table_name: item for item in current.summary.tables}
    facts = {item.storage_rule_view.canonical_table: item for item in current.storage_facts}
    changed: list[str] = []
    for name in sorted(views, key=lambda item: item.encode("utf-8")):
        identity = identities[name]
        descriptor = descriptors.get(name)
        fact = facts.get(name)
        unchanged = (
            descriptor is not None
            and fact is not None
            and descriptor.row_count == identity.row_count
            and descriptor.raw_content_digest == identity.raw_content_digest
            and fact.raw_content_digest == identity.raw_content_digest
            and fact.source_schema_digest == identity.source_schema_digest
            and fact.canonical_schema_digest == identity.canonical_schema_digest
            and fact.storage_rule_view == views[name]
            and fact.storage_projection_version == before_binding.storage_projection_version
        )
        if not unchanged:
            changed.append(name)
    return tuple(changed)


def _materialize_uploaded_side(
    binding: SourceArtifactBinding,
    store: ArtifactStorePort,
    ruleset: TableRulesetSnapshot,
    *,
    repository_id: str,
    export_cache: SnapshotTableExportCachePort | None,
    side: OperationDiagnosticSide,
    operation_id: str,
    canonical_lookup: Callable[[CanonicalTableKey], ArtifactRef | None] | None = None,
    canonical_before_write: Callable[[CanonicalTableKey, ArtifactRef], None] | None = None,
) -> tuple[BoundSnapshotInput, ArtifactRef, DigestRef, ConfigurationGeneratedTime, str]:
    context = current_kernel_context()
    if context is None:
        raise ValueError("uploaded materialization requires an operation kernel context")
    invocation = ParserInvocationContext(context.cancel_probe, context.deadline_monotonic)
    with ExitStack() as resources:
        artifact_ref = _artifact_ref_from_binding(binding)
        raw_bytes = resources.enter_context(reserved_artifact_bytes(store, artifact_ref))
        staged = stage_operation_source(
            SourcePackageInput(
                package_kind=PackageKind.TAR_GZ,
                transport=StagingTransport.IDENTITY,
                context=StagingInvocationContext(context.cancel_probe, context.deadline_monotonic),
                payload=raw_bytes,
                expected_required_sql_digest=None,
            ),
            store,
        )
        if staged.status is not StagingStatus.COMPLETE or staged.required_sql_document_ref is None:
            raise PreviewJobError("uploaded source package staging failed")
        dump = resolve_sql_dump_source(staged.required_sql_document_ref)
        sql_bytes = resources.enter_context(
            reserved_artifact_bytes(store, staged.required_sql_document_ref.artifact_ref)
        )
        parsed = parse_arrow_sql(_sql_request_from_bytes(sql_bytes))
        sql_request = dataclasses.replace(
            _sql_materialization_request(parsed, dump.sql_source_digest, ruleset),
            context=invocation,
        )
        xml_ref = staged.optional_xml_document_ref
        if xml_ref is None:
            logic = empty_composite_logic_source()
            xml_result = None
        else:
            xml_bytes = resources.enter_context(
                reserved_artifact_bytes(store, xml_ref.artifact_ref)
            )
            logic = present_composite_logic_source(xml_bytes)
            xml_digest = logic.document_content_digest
            if xml_digest is None:
                raise PreviewJobError("uploaded logics.xml content digest is missing")
            try:
                xml_request = XmlParseRequest(
                    source=XmlSourceInput(
                        document_content_digest=xml_digest,
                        xml_source_digest=xml_digest,
                        parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
                        encoding="utf-8",
                        source_size_bytes=len(xml_bytes),
                    ),
                    xml_utf8=xml_bytes,
                    context=invocation,
                )
            except ValueError as exc:
                raise PreviewJobError(
                    "uploaded /comps/logic/logics.xml failed parser input validation",
                    diagnostic_code=MaterializationDiagnosticCode.XML_DOCUMENT_FAILED.value,
                ) from exc
            # Expat has no external entities/DTD. Element/event/AST objects are
            # bounded by both source bytes and the existing node quota. Keep the
            # conservative parser/composite envelope until those locals die.
            from gateway_backend.capabilities.table_access.contracts import RESOURCE_BUDGETS

            nodes = min(RESOURCE_BUDGETS.max_xml_nodes, len(xml_bytes) // 3 + 1)
            xml_peak = nodes * 1024 + len(xml_bytes) * 16 + 512 * 1024
            if xml_peak > context.memory.available_bytes:
                raise KernelMemoryLimit("XML/composite operation memory reservation exceeded")
            context.memory.record_stage_admission("xml-parser-composite", xml_peak)
            resources.enter_context(context.memory.reserve(xml_peak))
            xml_result = parse_xml(xml_request)
            context.checkpoint()
        business_result = materialize_business_snapshot(
            BusinessSnapshotMaterializationRequest(
                sql=sql_request,
                logic=logic,
                xml=xml_result,
            )
        )
        context.checkpoint()
        if business_result.status is not SnapshotMaterializationStatus.COMPLETE:
            diagnostic = business_result.diagnostics[0] if business_result.diagnostics else None
            raise PreviewJobError(
                "uploaded business materialization failed"
                + ("" if diagnostic is None else f": {diagnostic.message}"),
                diagnostic_code=None if diagnostic is None else diagnostic.code.value,
            )
        if business_result.snapshot is None or business_result.table_set is None:
            raise PreviewJobError("uploaded business materialization is incomplete")
        if parsed.configuration_generated_time is None:
            raise PreviewJobError("uploaded source time facts are missing")
        generated_time = ConfigurationGeneratedTime.from_document(
            dict(parsed.configuration_generated_time)
        )
        projection_started = perf_counter()
        projected: CanonicalProjectionResult = project_canonical_arrow_table_set(
            business_result.table_set,
            ruleset,
            presentation=business_result.presentation,
        )
        _LOG.info(
            "s3_preview_stage_metrics %s",
            json.dumps(
                {
                    "operation_id": operation_id,
                    "stage": "uploaded_projection",
                    "side": side.value,
                    "upstream_projection_seconds": perf_counter() - projection_started,
                },
                sort_keys=True,
            ),
        )
        if projected.status is not ProjectionStatus.COMPLETE or projected.manifest is None:
            ordered_diagnostics = tuple(
                sorted(
                    projected.diagnostics,
                    key=lambda item: (
                        "" if item.table_name is None else item.table_name,
                        "" if item.column_name is None else item.column_name,
                        item.code.value,
                    ),
                )
            )
            projection_diagnostic = ordered_diagnostics[0] if ordered_diagnostics else None
            complete_diagnostic_count = (
                len(ordered_diagnostics) + projected.omitted_diagnostic_count
            )
            diagnostic_details = (
                tuple(
                    OperationDiagnosticDetail(
                        code=item.code.value,
                        side=side,
                        table_name=item.table_name,
                        column_name=item.column_name,
                    )
                    for item in ordered_diagnostics
                )
                if ordered_diagnostics
                else None
            )
            location = "projection"
            if projection_diagnostic is not None and projection_diagnostic.table_name is not None:
                location = projection_diagnostic.table_name
                if projection_diagnostic.column_name is not None:
                    location += f".{projection_diagnostic.column_name}"
            raise PreviewJobError(
                f"uploaded canonical projection failed on {side.value}"
                + (
                    ""
                    if projection_diagnostic is None
                    else f" ({complete_diagnostic_count} diagnostic(s)); first "
                    f"{projection_diagnostic.code.value} at {location}: {projection_diagnostic.message}"
                ),
                diagnostic_code=(
                    None if projection_diagnostic is None else projection_diagnostic.code.value
                ),
                diagnostic_details=diagnostic_details,
                diagnostic_omitted_count=projected.omitted_diagnostic_count,
            )
        try:
            canonical_result = materialize_canonical_snapshot(
                business_result.snapshot,
                projected.tables,
                artifact_store=store,
                context=invocation,
                repository_id=repository_id,
                lookup=canonical_lookup,
                before_write=canonical_before_write,
            )
        finally:
            for table in (*projected.tables, *business_result.table_set.tables):
                if table.reader is not None:
                    table.reader.close()
                if table.batch_reader is not None:
                    table.batch_reader.close()
        bound = _bound_from_materialization(
            canonical_result,
            label="uploaded canonical",
            storage_facts=_comparison_storage_facts(projected.manifest),
        )
        if side is OperationDiagnosticSide.MODIFIED:
            descriptors = bound.summary.tables
            input_shape(
                bound.snapshot.snapshot_digest.value,
                table_count=len(descriptors),
                total_rows=sum(item.row_count for item in descriptors),
                max_table_rows=max((item.row_count for item in descriptors), default=0),
                sql_bytes=staged.required_sql_document_ref.size_bytes,
            )
        try:
            manifest_ref = publish_canonicalization_manifest(projected.manifest, store)
        except PublicationError as exc:
            raise PreviewJobError("canonicalization manifest publication failed") from exc
        manifest_digest = projected.manifest.manifest_digest
        if manifest_digest is None:
            raise PreviewJobError("canonicalization manifest digest is missing")
        return bound, manifest_ref, manifest_digest, generated_time, dump.sql_source_digest.value


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


__all__ = [
    "build_materialize_inputs_handler",
]
