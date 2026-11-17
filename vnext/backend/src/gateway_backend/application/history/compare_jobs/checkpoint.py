"""History compare checkpoint state serialization, restoration, and pin helpers."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from gateway_backend.application.checkpoints import load_checkpoint_state_artifact
from gateway_backend.application.history.ports import (
    HistoryControlTransaction as HistoryCompareControlTransaction,
)
from gateway_backend.application.job_steps import (
    load_step,
    unique_artifact_refs,
)
from gateway_backend.application.pair_pipeline import (
    HistoryPairPipelineResult as _PairPipelineResult,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.location import parse_artifact_id
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonStorageFacts,
)
from gateway_backend.capabilities.comparison.documents import (
    storage_facts_from_documents,
    storage_facts_to_documents,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance,
    CanonicalBinding,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotTable,
    SnapshotTableOrderedMetadata,
    SnapshotTableSet,
    snapshot_from_document,
    snapshot_summary_from_document,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.snapshot_materialization.documents import (
    snapshot_descriptor_from_document,
    snapshot_descriptor_to_document,
)
from gateway_backend.document_fields import document_string
from gateway_backend.operations.contracts import StepRecord
from typing import cast

from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HISTORY_COMPARE_STEP_PUBLISH,
    HistoryCompareInputError,
    HistoryCompareJobError,
    HistoryCompareRuntimeDependencies,
    history_compare_step_id,
)

HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION = (
    "backend-vnext/history-compare/materialize-side/v6"
)

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
    "backend-vnext/history-compare/materialized-sides/v3"
)

HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE = "history-compare-assemble-state"

# The publish step checks this version before consuming the assembled bundle;
# v9 rejects checkpoints containing the previous navigation projection.
HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION = "backend-vnext/history-compare/assemble-state/v10"

_active_history_compare_transaction: ContextVar[HistoryCompareControlTransaction | None] = (
    ContextVar(
        "_active_history_compare_transaction",
        default=None,
    )
)

def _required_ready_refs(
    pair_results: list[_PairPipelineResult],
    bundle_manifest_ref: ArtifactRef,
    bundle_artifacts: tuple[ArtifactRef, ...],
) -> tuple[ArtifactRef, ...]:
    from gateway_backend.capabilities.bundle_assembly import collect_surface_refs

    refs: list[ArtifactRef] = []
    for pair_state in pair_results:
        if pair_state.surface_result.surface is None:
            raise HistoryCompareJobError("pair surface is missing from ready closure")
        refs.extend(collect_surface_refs(pair_state.surface_result.surface))
        if pair_state.structure_audit_ref is not None:
            refs.append(pair_state.structure_audit_ref)
    refs.append(bundle_manifest_ref)
    refs.extend(bundle_artifacts)
    return _unique_refs(tuple(refs))

def ready_closure_refs_from_assemble(
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
    return {
        commit_id: _side_binding_document(bound, commit_id=commit_id)
        for commit_id, bound in sides.items()
    }

def _side_binding_document(bound: BoundSnapshotInput, *, commit_id: str) -> dict[str, object]:
    if bound.table_set is None:
        raise HistoryCompareJobError("snapshot table set is missing closed refs")
    return {
        "contract_version": HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION,
        "commit_id": commit_id,
        "snapshot": snapshot_to_document(bound.snapshot),
        "snapshot_digest": bound.snapshot.snapshot_digest.value,
        "summary": snapshot_summary_to_document(bound.summary),
        "storage_facts": storage_facts_to_documents(bound.storage_facts),
        "tables": [
            {
                "descriptor": snapshot_descriptor_to_document(table.descriptor),
                "ordered_provenance": None
                if table.ordered_metadata is None
                else table.ordered_metadata.blank_provenance.value,
            }
            for table in bound.table_set.tables
        ],
    }

def _sides_from_materialize_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
    *,
    repository_id: str,
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
        if entry.get("commit_id") != commit_id:
            raise CheckpointDecodeError(
                "materialize checkpoint commit key mismatch", code="CHECKPOINT_JOB_STATE_MISMATCH"
            )
        bound = _bound_from_side_document(entry, store, repository_id=repository_id)
        if (
            bound.snapshot.source_context.repository_id != repository_id
            or bound.snapshot.source_context.resolved_commit_hash != commit_id
            or bound.snapshot.source_context.repository_ref != commit_id
        ):
            raise CheckpointDecodeError(
                "materialize checkpoint exact commit binding mismatch",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        sides[commit_id] = bound
    return sides

def _assert_history_bundle_binding(
    job_state: Mapping[str, object], refs: tuple[ArtifactRef, ...]
) -> None:
    if not any(ref.artifact_id == job_state[_JOB_STATE_BUNDLE_ARTIFACT] for ref in refs):
        raise CheckpointDecodeError(
            "history bundle ID is outside its ready closure", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )

def history_compare_ready_ref(job_state: Mapping[str, object]) -> ArtifactRef:
    try:
        ready_id = job_state.get(_JOB_STATE_READY_CLOSURE)
        bundle_id = job_state.get(_JOB_STATE_BUNDLE_ARTIFACT)
        raw_ref = job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        if type(ready_id) is not str or type(bundle_id) is not str or type(raw_ref) is not dict:
            raise ValueError("invalid history compare artifact bindings")
        parse_artifact_id(ready_id)
        parse_artifact_id(bundle_id)
        ref = artifact_ref_from_dict(raw_ref)
        if ref.artifact_id != ready_id:
            raise ValueError("history compare ready ID/ref mismatch")
        return ref
    except (ValueError, TypeError, KeyError) as exc:
        raise CheckpointDecodeError(
            "history compare checkpoint has invalid artifact bindings",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc

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
    history_compare_ready_ref(job_state)
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

def _bound_from_side_document(
    entry: dict[str, object], store: ArtifactStorePort, *, repository_id: str
) -> BoundSnapshotInput:
    if entry.get("contract_version") != HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION:
        raise CheckpointDecodeError(
            "materialize checkpoint side contract version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    tables_raw = entry.get("tables")
    if type(tables_raw) is not list:
        raise CheckpointDecodeError(
            "materialize checkpoint tables are invalid", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )
    opened: list[SnapshotTable] = []
    try:
        for item in tables_raw:
            if type(item) is not dict or set(item) != {"descriptor", "ordered_provenance"}:
                raise ValueError("invalid metadata table")
            descriptor = snapshot_descriptor_from_document(item["descriptor"])
            provenance = item["ordered_provenance"]
            ordered = (
                None
                if provenance is None
                else SnapshotTableOrderedMetadata(BlankRowProvenance(provenance))
            )
            opened.append(SnapshotTable(descriptor, None, ordered_metadata=ordered))
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint table metadata is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH"
        ) from exc
    try:
        snapshot = snapshot_from_document(entry.get("snapshot"))
    except (TypeError, ValueError, KeyError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint snapshot is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    snapshot_digest_raw = entry.get("snapshot_digest")
    if (
        type(snapshot_digest_raw) is not str
        or snapshot.snapshot_digest.value != snapshot_digest_raw
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint digest mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        summary_raw = entry.get("summary")
        if type(summary_raw) is not dict or type(summary_raw.get("tables")) is not list:
            raise ValueError("summary tables are invalid")
        descriptors_by_name = {table.descriptor.table_name: table.descriptor for table in opened}
        raw_summary_tables = summary_raw["tables"]
        ordered_names = tuple(
            document_string(item, "table_name") for item in raw_summary_tables if type(item) is dict
        )
        if len(ordered_names) != len(raw_summary_tables) or set(ordered_names) != set(
            descriptors_by_name
        ):
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
        storage_facts = storage_facts_from_documents(entry.get("storage_facts"))
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
    storage_facts = _storage_facts_for_binding(
        canonical_binding, {item.table_name for item in result.summary.tables}
    )
    return BoundSnapshotInput(result.snapshot, result.summary, result.table_set, storage_facts)

def _storage_facts_for_binding(
    canonical_binding: CanonicalBinding,
    names: set[str],
) -> tuple[ComparisonStorageFacts, ...]:
    if {view.canonical_table for view in canonical_binding.tables} != names:
        raise HistoryCompareInputError("canonical binding table set differs from frozen metadata")
    identities = {item.canonical_table: item for item in canonical_binding.table_identities}
    return tuple(
        ComparisonStorageFacts(
            storage_rule_view=view,
            source_schema_digest=identities[view.canonical_table].source_schema_digest,
            canonical_schema_digest=identities[view.canonical_table].canonical_schema_digest,
            raw_content_digest=identities[view.canonical_table].raw_content_digest,
            storage_projection_version=canonical_binding.storage_projection_version,
        )
        for view in canonical_binding.tables
    )

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
            continue
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

def _release_history_compare_checkpoint_protection(
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

def _release_history_compare_step_protection(
    unit_of_work: HistoryCompareControlTransaction, *, operation_id: str
) -> None:
    _release_history_compare_checkpoint_protection(unit_of_work, operation_id=operation_id)
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
    return load_step(
        deps.control_transaction_factory,
        operation_id=operation_id,
        step_id=step_id,
        mismatch_error=lambda: HistoryCompareJobError(
            "history compare step belongs to a different operation"
        ),
    )


__all__ = [
    "HISTORY_COMPARE_MATERIALIZE_SIDE_CONTRACT_VERSION",
    "HISTORY_COMPARE_MATERIALIZED_SIDES_DOCUMENT_TYPE",
    "HISTORY_COMPARE_MATERIALIZED_SIDES_CONTRACT_VERSION",
    "HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE",
    "HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION",
    "ready_closure_refs_from_assemble",
    "history_compare_ready_ref",
    "history_compare_assemble_state_from_checkpoint",
]
