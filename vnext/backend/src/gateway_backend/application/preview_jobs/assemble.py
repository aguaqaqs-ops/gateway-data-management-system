"""Preview step 2: pair comparison, surface closure, and bundle assembly."""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid

from collections.abc import (
    Callable,
    Mapping,
)
from datetime import datetime
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
    PreviewPairPipelineResult as _PairPipelineResult,
    declare_pair_comparison_session,
    preview_identity_assessment,
    run_preview_pair_pipeline,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.preview_job_identity import (
    PREVIEW_JOB_CONTRACT_VERSION,
    PREVIEW_STEP_MATERIALIZE,
)
from gateway_backend.artifacts.computation_cache import (
    CacheOperationOwner,
    ComputationCachePort,
)
from gateway_backend.artifacts.serialize import (
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.artifacts.store import ArtifactStorePort
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
    BundleTableBinding,
    BundleTableSide,
    PreviewBundleInputRole,
    collect_surface_refs,
    preview_bundle_input,
)
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonMode,
    ComparisonRecordsClosure,
    ComparisonRequest,
)
from gateway_backend.capabilities.project_identity import (
    ProjectIdentityStatus as AssessmentProjectIdentityStatus,
)
from gateway_backend.capabilities.snapshot_materialization import export_snapshot_table_parquet
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableSet
from gateway_backend.capabilities.surface_assembly.contracts import ComparisonSurface
from gateway_backend.capabilities.table_presentation.contracts import PresentationMetadata
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    PreviewArtifactRef,
    PreviewCanonicalBindings,
    PreviewComparisonPair,
    PreviewIdentityPair,
    PreviewResult,
    PreviewResultDigests,
    ProjectIdentityApplicability,
    ProjectIdentityMode,
    ProjectIdentityStatus,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    StepRecord,
)
from gateway_backend.operations.lease_session import LeaseSession
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
from gateway_shared_kernel.jcs import canonicalize_json_value
from pydantic import TypeAdapter
from time import perf_counter
from typing import cast

from gateway_backend.application.preview_jobs.checkpoint import (
    PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION,
    PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE,
    _CanonicalPreviewMetadata,
    _JOB_STATE_ASSEMBLE,
    _JOB_STATE_ASSEMBLE_REF,
    _JOB_STATE_BUNDLE_ARTIFACT,
    _JOB_STATE_BUNDLE_DIGEST,
    _JOB_STATE_CANONICAL,
    _JOB_STATE_READY_CLOSURE,
    _JOB_STATE_READY_CLOSURE_REF,
    _active_preview_transaction,
    _assemble_state_from_checkpoint,
    _assert_configuration_payload,
    _assert_preview_bundle_binding,
    _canonical_preview_metadata_from_document,
    _canonical_preview_metadata_to_document,
    _checkpoint_string,
    _load_step,
    _pin_preview_refs,
    _preview_ready_ref,
    _side_input_refs,
    _unique_refs,
)
from gateway_backend.application.preview_jobs.failures import (
    _active_preview_ruleset,
    _make_cancelled_terminal_builder,
    _publish_preview_ruleset_mismatch_failure,
    _restore_preview_inputs_or_publish_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.preview_jobs.payload import (
    PREVIEW_STEP_PUBLISH,
    PreviewJobError,
    PreviewJobPayload,
    PreviewRuntimeDependencies,
    _PAIR_BASELINE_TO_INITIAL,
    _PAIR_INITIAL_TO_MODIFIED,
    _SIDE_BASELINE,
    _SIDE_INITIAL,
    _SIDE_MODIFIED,
    _load_preview_payload,
    _successor_step_id,
    preview_assemble_job_definition,
    preview_materialize_job_definition,
)

_LOG = logging.getLogger(__name__)


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
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
        active_rules = _active_preview_ruleset()
        if (
            active_rules.ruleset_digest is None
            or active_rules.ruleset_digest.value != payload.comparison_ruleset_digest
        ):
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
        inputs = _restore_preview_inputs_or_publish_failure(
            materialize_envelope.job_state,
            repository_id=payload.repository_id,
            deps=deps,
            operation=operation,
            step=step,
            lease_session=lease_session,
            control=control,
        )
        if inputs is None:
            return ExecutorAcknowledgment.PUBLISHED

        _assert_configuration_payload(
            inputs.canonical.configuration_facts, payload, operation.operation_id
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
            ready_closure_ref = _preview_ready_ref(envelope.job_state)
            closure = load_ready_closure(deps.artifact_store, ready_closure_ref)
            _assert_preview_bundle_binding(envelope.job_state, closure.artifact_refs())
            verify_structure_audit_bindings(
                deps.artifact_store,
                _assemble_state.get("structure_audit_bindings"),
                closure.artifact_refs(),
                _assemble_state.get("pair_ids"),
            )
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

            def publish_cancelled() -> None:
                lease_session.publish_operation(_make_cancelled_terminal_builder())

            try:
                assemble_state, bundle_manifest_ref, bundle_digest = _assemble_preview(
                    payload,
                    inputs.sides,
                    inputs.canonical,
                    deps.artifact_store,
                    lease_session,
                    control,
                    active_rules,
                    operation_id=operation.operation_id,
                    on_cancel=publish_cancelled,
                    export_cache=deps.snapshot_export_cache,
                    computation_cache=deps.computation_cache,
                    presentations=inputs.presentations,
                )
            except PairPipelineCancelled:
                return ExecutorAcknowledgment.PUBLISHED
            ready_refs = _ready_closure_refs_from_assemble(assemble_state, bundle_manifest_ref)
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
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=PREVIEW_STEP_PUBLISH,
                successor_step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_PUBLISH),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


def surface_artifact_closure(
    surface: ComparisonSurface | None,
    pair_id: str,
    records_closure: ComparisonRecordsClosure | None = None,
    *,
    before: BoundSnapshotInput | None = None,
    current: BoundSnapshotInput | None = None,
    include_all_tables: bool = False,
    store: ArtifactStorePort | None = None,
    repository_id: str | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> BundleArtifactClosure:
    if surface is None:
        raise PreviewJobError("surface assembly did not produce a surface for bundle closure")
    bindings: list[BundleArtifactBinding] = []
    added_refs: set[ArtifactRef] = set()
    snapshot_bindings: dict[BundleTableBinding, ArtifactRef] = {}
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
        table_binding: BundleTableBinding | None = None
        if kind is BundleArtifactKind.SNAPSHOT_TABLE:
            if table_name is None:
                raise PreviewJobError("snapshot table ref is missing its table name")
            parts = logical_path.split("/")
            try:
                table_index = parts.index("tables")
                side = BundleTableSide(parts[table_index + 1])
            except (ValueError, IndexError) as exc:
                raise PreviewJobError("snapshot table ref path is missing its side") from exc
            table_binding = BundleTableBinding(pair_id, table_name, side)
            previous_ref = snapshot_bindings.get(table_binding)
            if previous_ref is not None:
                if previous_ref != ref:
                    raise PreviewJobError("snapshot table binding points to multiple artifacts")
                return
            snapshot_bindings[table_binding] = ref
        if ref in added_refs and kind is not BundleArtifactKind.SNAPSHOT_TABLE:
            return
        added_refs.add(ref)
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
    add(
        surface.refs.diagnostics_ref,
        f"{prefix}/diagnostics/surface.json",
        BundleArtifactKind.DIAGNOSTICS,
    )
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
            table.row_locator_ref,
            f"{prefix}/comparison/locators/{table_name}.parquet",
            BundleArtifactKind.ROW_LOCATOR,
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
    if records_closure is not None:
        closure_ref = surface.refs.records_closure_ref
        if (
            closure_ref is None
            or closure_ref.raw_sha256 != records_closure.closure_manifest_digest
            or surface.comparison_digest != records_closure.comparison_digest
        ):
            raise PreviewJobError("records closure does not match pair surface")
        covered_refs = {binding.source_ref for binding in bindings}
        for entry in records_closure.records:
            family_path = entry.family.value.lower()
            records_path = f"{prefix}/comparison/records/{entry.table_name}/{family_path}"
            if entry.records_ref not in covered_refs:
                add(
                    entry.records_ref,
                    f"{records_path}/rows.bin",
                    BundleArtifactKind.RECORDS,
                    table_name=entry.table_name,
                )
                covered_refs.add(entry.records_ref)
            if entry.records_manifest_ref not in covered_refs:
                add(
                    entry.records_manifest_ref,
                    f"{records_path}/manifest.json",
                    BundleArtifactKind.RECORDS_MANIFEST,
                    table_name=entry.table_name,
                )
                covered_refs.add(entry.records_manifest_ref)
    if surface.comparison_mode is ComparisonMode.DATASET_REPLACEMENT:
        if before is None or current is None:
            raise PreviewJobError("replacement bundle closure requires both canonical table sets")
        for role, bound in (("before", before), ("current", current)):
            if bound.table_set is None:
                raise PreviewJobError("replacement bundle closure is missing a canonical table set")
            for snapshot_table in bound.table_set.tables:
                artifact = snapshot_table.artifact
                if artifact is None:
                    raise PreviewJobError(
                        f"replacement table {snapshot_table.descriptor.table_name} is missing its artifact"
                    )
                table_name = snapshot_table.descriptor.table_name
                for index, ref in enumerate(
                    (
                        export_snapshot_table_parquet(
                            snapshot_table,
                            store=store,
                            repository_id=repository_id,
                            export_cache=export_cache,
                        ),
                    )
                ):
                    add(
                        ref,
                        f"{prefix}/tables/{role}/{table_name}/rows/{index:06d}.parquet",
                        BundleArtifactKind.SNAPSHOT_TABLE,
                        table_name=table_name,
                    )
    if include_all_tables:
        if before is None or current is None:
            raise PreviewJobError("complete table bundle requires both canonical table sets")
        for role, side, bound in (
            ("before", "before", before),
            ("current", "current", current),
        ):
            if bound.table_set is None:
                raise PreviewJobError("complete table bundle is missing a canonical table set")
            for snapshot_table in bound.table_set.tables:
                table_name = snapshot_table.descriptor.table_name
                export_ref = (
                    None
                    if table_exports is None
                    else table_exports.get(bound.snapshot.snapshot_id, {}).get(table_name)
                )
                if export_ref is None:
                    export_ref = export_snapshot_table_parquet(
                        snapshot_table,
                        store=store,
                        repository_id=repository_id,
                        export_cache=export_cache,
                    )
                for export_index, required_export_ref in enumerate((export_ref,)):
                    add(
                        required_export_ref,
                        f"{prefix}/tables/{side}/{table_name}/rows/{export_index:06d}.parquet",
                        BundleArtifactKind.SNAPSHOT_TABLE,
                        table_name=table_name,
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
    operation_id: str,
    on_cancel: Callable[[], None],
    export_cache: SnapshotTableExportCachePort | None = None,
    computation_cache: ComputationCachePort | None = None,
    presentations: Mapping[str, PresentationMetadata] | None = None,
) -> tuple[dict[str, object], ArtifactRef, str]:
    current_summary = sides[_SIDE_MODIFIED].summary.tables
    input_shape(
        sides[_SIDE_MODIFIED].snapshot.snapshot_digest.value,
        table_count=len(current_summary),
        total_rows=sum(item.row_count for item in current_summary),
        max_table_rows=max((item.row_count for item in current_summary), default=0),
    )
    display_inputs = dict(presentations or {})
    if set(display_inputs) != set(sides):
        raise PreviewJobError("comparison requires frozen presentation for every side")
    sides = {
        name: dataclasses.replace(bound, presentation=display_inputs[name])
        for name, bound in sides.items()
    }
    pair_results: list[_PairPipelineResult] = []
    bundle_pairs: list[BundlePairInput] = []
    if payload.input_completeness is InputCompleteness.FULL:
        pair_specs: tuple[tuple[str, BoundSnapshotInput, BoundSnapshotInput, bool, bool], ...] = (
            (
                _PAIR_BASELINE_TO_INITIAL,
                sides[_SIDE_BASELINE],
                sides[_SIDE_INITIAL],
                not canonical.baseline_is_initial,
                True,
            ),
            (_PAIR_INITIAL_TO_MODIFIED, sides[_SIDE_INITIAL], sides[_SIDE_MODIFIED], True, False),
        )
        bundle_profile = BundleProfile.MULTI_PAIR
        bundle_inputs = _preview_bundle_inputs(payload.input_completeness)
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
                not canonical.baseline_is_initial,
                True,
            ),
        )
        bundle_profile = BundleProfile.SINGLE_PAIR
        bundle_inputs = _preview_bundle_inputs(payload.input_completeness)
        bundle_indexes = {_PAIR_INITIAL_TO_MODIFIED: (0, 1)}

    dedup_requests: list[ComparisonRequest] = []
    for pair_id, before, current, assess_identity, reuse_identity in pair_specs:
        assessment = (
            preview_identity_assessment(
                before,
                current,
                before_table_set=(
                    _unchanged_baseline_identity_table_set(before, current)
                    if reuse_identity
                    else None
                ),
            )
            if assess_identity
            else None
        )
        dedup_requests.append(
            ComparisonRequest(
                pair_id=pair_id,
                before=before,
                current=current,
                rule_set=rule_set,
                mode=(
                    ComparisonMode.DATASET_REPLACEMENT
                    if assessment is not None
                    and assessment.status is AssessmentProjectIdentityStatus.DIFFERENT_PROJECT
                    else ComparisonMode.DETAILED
                ),
            )
        )
    dedup_session = declare_pair_comparison_session(
        tuple(dedup_requests),
        computation_cache=computation_cache,
        cache_owner=CacheOperationOwner("preview-operation", operation_id),
        repository_id=payload.repository_id,
    )
    try:
        for (
            pair_id,
            before,
            current,
            assess_identity,
            reuse_unchanged_baseline_identity,
        ) in pair_specs:
            lease_session.refresh_control()
            if control.cancel_requested:
                on_cancel()
                raise PairPipelineCancelled
            pair_state = _run_pair_pipeline(
                pair_id=pair_id,
                before=before,
                current=current,
                initial_baseline=_initial_baseline_pair(
                    canonical.baseline_is_initial, payload.input_completeness, pair_id
                ),
                before_presentation=display_inputs[
                    _SIDE_BASELINE
                    if pair_id == _PAIR_BASELINE_TO_INITIAL
                    or payload.input_completeness is InputCompleteness.MODIFIED_ONLY
                    else _SIDE_INITIAL
                ],
                current_presentation=display_inputs[
                    _SIDE_INITIAL if pair_id == _PAIR_BASELINE_TO_INITIAL else _SIDE_MODIFIED
                ],
                store=store,
                control=control,
                rule_set=rule_set,
                on_cancel=on_cancel,
                assess_identity=assess_identity,
                repository_id=payload.repository_id,
                export_cache=export_cache,
                dedup_session=dedup_session,
                identity_before_table_set=(
                    _unchanged_baseline_identity_table_set(before, current)
                    if assess_identity and reuse_unchanged_baseline_identity
                    else None
                ),
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
                        store=store,
                        repository_id=payload.repository_id,
                        export_cache=export_cache,
                    ),
                )
            )

        bundle_started = perf_counter()
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
        _LOG.info(
            "s3_preview_stage_metrics %s",
            json.dumps(
                {
                    "operation_id": operation_id,
                    "stage": "bundle_assembly",
                    "input_completeness": payload.input_completeness.value,
                    "pair_count": len(bundle_pairs),
                    "bundle_assembly_seconds": perf_counter() - bundle_started,
                },
                sort_keys=True,
            ),
        )
        if bundle_result.status is not BundleAssemblyStatus.READY or bundle_result.bundle is None:
            diagnostic = bundle_result.diagnostics[0] if bundle_result.diagnostics else "unknown"
            raise PreviewJobError(f"bundle assembly failed: {diagnostic}")
        required_refs = _required_ready_refs(
            payload=payload,
            sides=sides,
            canonical=canonical,
            pair_results=pair_results,
            bundle_manifest_ref=bundle_result.bundle.manifest_ref,
            bundle_artifacts=bundle_result.referenced_artifacts,
        )
        final_bundle_pairs = {pair.pair_id: pair for pair in bundle_result.bundle.pairs}
        assemble_state: dict[str, object] = {
            "pair_ids": [item.pair_id for item in pair_results],
            "structure_audit_bindings": [
                structure_audit_binding(
                    item.pair_id, item.comparison_digest, item.structure_audit_ref
                )
                for item in pair_results
            ],
            "comparison_pairs": [
                PreviewComparisonPair(
                    pair_id=item.pair_id,
                    before_snapshot_digest=spec[1].snapshot.snapshot_digest.value,
                    current_snapshot_digest=spec[2].snapshot.snapshot_digest.value,
                    comparison_digest=item.comparison_digest,
                    risk_digest=item.risk_digest,
                    surface_digest=final_bundle_pairs[item.pair_id].surface_digest.value,
                    ruleset_digest=payload.comparison_ruleset_digest,
                    structure_audit_artifact_id=(
                        None
                        if item.structure_audit_ref is None
                        else item.structure_audit_ref.artifact_id
                    ),
                ).model_dump(mode="json")
                for spec, item in zip(pair_specs, pair_results, strict=True)
            ],
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
            "identity_assessment_set_digest": _identity_assessment_set_digest(pair_results).value,
            "identity_pairs": [_identity_pair_to_document(item) for item in pair_results],
            "required_refs": [artifact_ref_to_dict(item) for item in required_refs],
        }
        return (
            assemble_state,
            bundle_result.bundle.manifest_ref,
            bundle_result.bundle.bundle_digest.value,
        )

    finally:
        if dedup_session is not None:
            dedup_session.close()
        if computation_cache is not None:
            computation_cache.release_operation_pins(
                CacheOperationOwner("preview-operation", operation_id)
            )


def _preview_bundle_inputs(completeness: InputCompleteness) -> tuple[BundleInput, ...]:
    if completeness is InputCompleteness.FULL:
        return (
            preview_bundle_input(0, PreviewBundleInputRole.BASELINE, "Baseline"),
            preview_bundle_input(1, PreviewBundleInputRole.INITIAL, "Initial"),
            preview_bundle_input(2, PreviewBundleInputRole.MODIFIED, "Modified"),
        )
    return (
        preview_bundle_input(0, PreviewBundleInputRole.BASELINE, "Baseline"),
        preview_bundle_input(1, PreviewBundleInputRole.MODIFIED, "Modified"),
    )


def _initial_baseline_pair(
    baseline_is_initial: bool, completeness: InputCompleteness, pair_id: str
) -> bool:
    return baseline_is_initial and (
        (completeness is InputCompleteness.FULL and pair_id == _PAIR_BASELINE_TO_INITIAL)
        or (
            completeness is InputCompleteness.MODIFIED_ONLY and pair_id == _PAIR_INITIAL_TO_MODIFIED
        )
    )


def _run_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: ArtifactStorePort,
    control: ExecutionControl,
    rule_set: ComparisonRuleSet,
    on_cancel: Callable[[], None],
    assess_identity: bool,
    identity_before_table_set: SnapshotTableSet | None = None,
    repository_id: str | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
    dedup_session: ComparisonTaskSession | None = None,
    before_presentation: PresentationMetadata,
    current_presentation: PresentationMetadata,
    initial_baseline: bool = False,
) -> _PairPipelineResult:
    try:
        return run_preview_pair_pipeline(
            before_presentation=before_presentation,
            current_presentation=current_presentation,
            initial_baseline=initial_baseline,
            pair_id=pair_id,
            before=before,
            current=current,
            store=store,
            control=control,
            on_cancel=on_cancel,
            view_id=pair_id,
            rule_set=rule_set,
            assess_identity=assess_identity,
            identity_before_table_set=identity_before_table_set,
            repository_id=repository_id,
            export_cache=export_cache,
            dedup_session=dedup_session,
        )
    except PairPipelineCancelled:
        raise
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
    _assert_configuration_payload(canonical.configuration_facts, payload, operation.operation_id)
    identity_pairs = _identity_pairs_from_assemble_state(assemble_state)
    identity_set_digest = DigestRef(
        _checkpoint_string(assemble_state, "identity_assessment_set_digest")
    )
    if _identity_assessment_set_digest(identity_pairs) != identity_set_digest:
        raise PreviewJobError("assemble checkpoint identity assessment set digest does not match")
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
            initial_canonical_state_digest=canonical.initial_canonical_state_digest,
            configuration_facts=canonical.configuration_facts,
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
            rules_semantically_equal=canonical.rules_semantically_equal,
        ),
        identity_assessment_set_digest=identity_set_digest,
        identity_pairs=identity_pairs,
        comparison_pairs=TypeAdapter(tuple[PreviewComparisonPair, ...]).validate_json(
            canonicalize_json_value(assemble_state["comparison_pairs"])
        ),
        bundle_artifact_id=bundle_artifact_id,
        ready_closure_artifact_id=ready_closure_artifact_id,
        operation_id=operation.operation_id,
        created_at=transaction_now,
    )


def _identity_pair_model(pair: _PairPipelineResult) -> PreviewIdentityPair:
    surface = pair.surface_result.surface
    if surface is None:
        raise PreviewJobError("pair surface is missing identity applicability")
    assessment = pair.identity_assessment
    if assessment is None:
        return PreviewIdentityPair(
            pair_id=pair.pair_id,
            applicability=ProjectIdentityApplicability.NOT_APPLICABLE,
            status=ProjectIdentityStatus.NOT_APPLICABLE,
            mode=ProjectIdentityMode.DETAILED,
            assessment_ref=None,
            assessment_digest=None,
        )
    ref = pair.identity_assessment_ref
    if ref is None:
        raise PreviewJobError("applicable identity assessment is missing its artifact ref")
    return PreviewIdentityPair(
        pair_id=pair.pair_id,
        applicability=ProjectIdentityApplicability.APPLICABLE,
        status=ProjectIdentityStatus(assessment.status.value),
        mode=ProjectIdentityMode(surface.comparison_mode.value),
        assessment_ref=_workspace_artifact_ref(ref),
        assessment_digest=assessment.assessment_digest,
    )


def _identity_pair_to_document(pair: _PairPipelineResult) -> dict[str, object]:
    model = _identity_pair_model(pair)
    return {
        "applicability": model.applicability.value,
        "assessment_digest": (
            None if model.assessment_digest is None else model.assessment_digest.value
        ),
        "assessment_ref": (
            None
            if model.assessment_ref is None
            else {
                "artifact_id": model.assessment_ref.artifact_id,
                "media_type": model.assessment_ref.media_type,
                "size_bytes": model.assessment_ref.size_bytes,
                "raw_sha256": model.assessment_ref.raw_sha256.value,
            }
        ),
        "mode": model.mode.value,
        "pair_id": model.pair_id,
        "status": model.status.value,
    }


def _identity_assessment_set_digest(
    pairs: tuple[PreviewIdentityPair, ...] | list[_PairPipelineResult],
) -> DigestRef:
    if not pairs:
        models: tuple[PreviewIdentityPair, ...] = ()
    elif isinstance(pairs[0], PreviewIdentityPair):
        models = pairs
    else:
        models = tuple(_identity_pair_model(item) for item in pairs)
    return raw_blob_digest(
        canonicalize_json_value(
            {
                "schema": "project-identity-assessment-set/v1",
                "pairs": [
                    [
                        item.pair_id,
                        item.applicability.value,
                        item.status.value,
                        None if item.assessment_digest is None else item.assessment_digest.value,
                    ]
                    for item in models
                ],
            }
        )
    )


def _identity_pairs_from_assemble_state(
    assemble_state: dict[str, object],
) -> tuple[PreviewIdentityPair, ...]:
    raw_pairs = assemble_state.get("identity_pairs")
    if type(raw_pairs) is not list or not raw_pairs:
        raise CheckpointDecodeError(
            "assemble checkpoint identity pairs are missing",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    pairs: list[PreviewIdentityPair] = []
    expected_keys = {
        "applicability",
        "assessment_digest",
        "assessment_ref",
        "mode",
        "pair_id",
        "status",
    }
    try:
        for raw in raw_pairs:
            if type(raw) is not dict or set(raw) != expected_keys:
                raise ValueError("identity pair fields are invalid")
            raw_ref = raw["assessment_ref"]
            if raw_ref is not None and type(raw_ref) is not dict:
                raise ValueError("identity assessment ref is invalid")
            raw_digest = raw["assessment_digest"]
            if raw_digest is not None and type(raw_digest) is not str:
                raise ValueError("identity assessment digest is invalid")
            pairs.append(
                PreviewIdentityPair(
                    pair_id=_checkpoint_string(raw, "pair_id"),
                    applicability=ProjectIdentityApplicability(
                        _checkpoint_string(raw, "applicability")
                    ),
                    status=ProjectIdentityStatus(_checkpoint_string(raw, "status")),
                    mode=ProjectIdentityMode(_checkpoint_string(raw, "mode")),
                    assessment_ref=(
                        None
                        if raw_ref is None
                        else _workspace_artifact_ref(artifact_ref_from_dict(raw_ref))
                    ),
                    assessment_digest=(None if raw_digest is None else DigestRef(raw_digest)),
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckpointDecodeError(
            "assemble checkpoint identity pairs are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    return tuple(pairs)


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
    bundle_artifacts: tuple[ArtifactRef, ...],
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
        if pair_state.structure_audit_ref is not None:
            refs.append(pair_state.structure_audit_ref)
    refs.append(bundle_manifest_ref)
    refs.extend(bundle_artifacts)
    return _unique_refs(tuple(refs))


def _workspace_artifact_ref(ref: ArtifactRef) -> PreviewArtifactRef:
    return PreviewArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256,
    )


def _unchanged_baseline_identity_table_set(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
) -> SnapshotTableSet | None:
    """Reuse current version_manager rows for identity when its full table identity matches."""

    if before.table_set is None or current.table_set is None:
        return None
    before_descriptor = next(
        (item for item in before.summary.tables if item.table_name == "version_manager"),
        None,
    )
    current_descriptor = next(
        (item for item in current.summary.tables if item.table_name == "version_manager"),
        None,
    )
    before_fact = next(
        (
            item
            for item in before.storage_facts
            if item.storage_rule_view.canonical_table == "version_manager"
        ),
        None,
    )
    current_fact = next(
        (
            item
            for item in current.storage_facts
            if item.storage_rule_view.canonical_table == "version_manager"
        ),
        None,
    )
    if (
        before_descriptor is None
        or current_descriptor is None
        or before_fact is None
        or current_fact is None
        or before_descriptor.row_count != current_descriptor.row_count
        or before_descriptor.raw_content_digest != current_descriptor.raw_content_digest
        or before_fact.raw_content_digest != current_fact.raw_content_digest
        or before_fact.source_schema_digest != current_fact.source_schema_digest
        or before_fact.canonical_schema_digest != current_fact.canonical_schema_digest
        or before_fact.storage_rule_view != current_fact.storage_rule_view
        or before_fact.storage_projection_version != current_fact.storage_projection_version
    ):
        return None
    current_table = next(
        (
            item
            for item in current.table_set.tables
            if item.descriptor.table_name == "version_manager"
        ),
        None,
    )
    if current_table is None:
        return None
    return SnapshotTableSet(
        snapshot_id=before.snapshot.snapshot_id,
        snapshot_digest=before.snapshot.snapshot_digest,
        table_ruleset_version=current.table_set.table_ruleset_version,
        tables=(current_table,),
        diagnostics=current.table_set.diagnostics,
    )


__all__ = [
    "build_assemble_preview_handler",
    "surface_artifact_closure",
]
