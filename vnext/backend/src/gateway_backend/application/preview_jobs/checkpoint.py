"""Preview job checkpoint state serialization, restoration, and pin helpers."""

from __future__ import annotations

import uuid

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from gateway_backend.application.canonical_metadata.binding import presentation_for_commit
from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.checkpoints import load_checkpoint_state_artifact
from gateway_backend.application.job_steps import (
    load_step,
    unique_artifact_refs,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.preview_job_identity import PREVIEW_STEP_MATERIALIZE
from gateway_backend.application.workspace.ports import (
    WorkspaceControlTransaction as PreviewControlTransaction,
)
from gateway_backend.artifacts.digest import build_artifact_id
from gateway_backend.artifacts.location import (
    ArtifactLocation,
    parse_artifact_id,
)
from gateway_backend.artifacts.serialize import (
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonStorageFacts,
)
from gateway_backend.capabilities.comparison.documents import (
    storage_facts_from_documents,
    storage_facts_to_documents,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArtifactPublishError,
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotTableSet,
    SourceKind,
    canonical_state_digest_of,
    snapshot_from_document,
    snapshot_summary_from_document,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.snapshot_materialization.documents import (
    snapshot_descriptor_from_document,
    snapshot_descriptor_to_document,
)
from gateway_backend.capabilities.storage_projection import (
    CanonicalizationManifest,
    PublicationError,
    open_canonicalization_manifest,
)
from gateway_backend.capabilities.table_presentation.contracts import PresentationMetadata
from gateway_backend.capabilities.table_rules import (
    comparison_rule_set,
    migrated_table_ruleset_snapshot,
    resolve_comparison_rule_view,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    StorageRuleView,
    TableRulesetSnapshot,
)
from gateway_backend.document_fields import document_string
from gateway_backend.domain.configuration_facts import ConfigurationFacts
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactRole,
)
from gateway_backend.operations.contracts import StepRecord
from gateway_shared_kernel import (
    DigestRef,
    canonicalize_jcs,
)
from gateway_shared_kernel.jcs import canonicalize_json_value
from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
)
from typing import cast

from gateway_backend.application.preview_jobs.payload import (
    PREVIEW_STEP_ASSEMBLE,
    PREVIEW_STEP_PUBLISH,
    PreviewJobError,
    PreviewJobPayload,
    PreviewRuntimeDependencies,
    _JCS_MEDIA_TYPE,
    _SIDE_BASELINE,
    _SIDE_INITIAL,
    _SIDE_MODIFIED,
    _artifact_ref_from_binding,
    _successor_step_id,
)

PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION = "backend-vnext/preview/materialize-side/v6"

PREVIEW_ASSEMBLE_CHECKPOINT_CONTRACT_VERSION = "backend-vnext/preview/assemble-checkpoint/v2"

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

PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION = "backend-vnext/preview/materialized-sides/v3"

PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE = "preview-assemble-state"

# The publish step verifies this version before consuming bundle refs; v12
# excludes checkpoints whose navigation projection predates v5.
PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION = "backend-vnext/preview/assemble-state/v13"

_active_preview_transaction: ContextVar[PreviewControlTransaction | None] = ContextVar(
    "_active_preview_transaction",
    default=None,
)


@dataclass(frozen=True, slots=True)
class _CanonicalPreviewMetadata:
    initial_canonical_state_digest: DigestRef
    configuration_facts: ConfigurationFacts
    canonical_table_set_closure_ref: ArtifactRef
    canonicalization_manifest_ref: ArtifactRef
    canonicalization_manifest_digest: DigestRef
    initial_canonicalization_manifest_ref: ArtifactRef | None
    initial_canonicalization_manifest_digest: DigestRef | None
    baseline_canonical_state_digest: DigestRef
    modified_canonical_state_digest: DigestRef
    storage_projection_ruleset_digest: DigestRef
    baseline_is_initial: bool
    rules_semantically_equal: bool

    def __post_init__(self) -> None:
        if type(self.canonical_table_set_closure_ref) is not ArtifactRef:
            raise ValueError("canonical_table_set_closure_ref must be ArtifactRef")
        if type(self.canonicalization_manifest_ref) is not ArtifactRef:
            raise ValueError("canonicalization_manifest_ref must be ArtifactRef")
        for field_name in (
            "canonicalization_manifest_digest",
            "baseline_canonical_state_digest",
            "initial_canonical_state_digest",
            "modified_canonical_state_digest",
            "storage_projection_ruleset_digest",
        ):
            if type(getattr(self, field_name)) is not DigestRef:
                raise ValueError(f"{field_name} must be DigestRef")
        if (self.initial_canonicalization_manifest_ref is None) != (
            self.initial_canonicalization_manifest_digest is None
        ):
            raise ValueError("INITIAL manifest ref and digest must be supplied together")
        if (
            self.initial_canonicalization_manifest_ref is not None
            and type(self.initial_canonicalization_manifest_ref) is not ArtifactRef
        ):
            raise ValueError("initial_canonicalization_manifest_ref must be ArtifactRef or None")
        if (
            self.initial_canonicalization_manifest_digest is not None
            and type(self.initial_canonicalization_manifest_digest) is not DigestRef
        ):
            raise ValueError("initial_canonicalization_manifest_digest must be DigestRef or None")
        if type(self.configuration_facts) is not ConfigurationFacts:
            raise ValueError("canonical Preview configuration facts are required")
        facts = self.configuration_facts
        if (
            facts.initial.content_identity.canonical_state_digest
            != self.initial_canonical_state_digest.value
            or facts.modified.content_identity.canonical_state_digest
            != self.modified_canonical_state_digest.value
            or facts.baseline_content_identity.canonical_state_digest
            != self.baseline_canonical_state_digest.value
            or facts.modified.content_identity.storage_projection_ruleset_digest
            != self.storage_projection_ruleset_digest.value
            or facts.baseline_is_initial != self.baseline_is_initial
        ):
            raise ValueError("canonical Preview configuration facts do not match metadata")
        if type(self.baseline_is_initial) is not bool:
            raise ValueError("baseline_is_initial must be bool")


class _CanonicalPreviewDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    canonical_table_set_closure_ref: dict[str, JsonValue]
    canonicalization_manifest_ref: dict[str, JsonValue]
    canonicalization_manifest_digest: str
    initial_canonicalization_manifest_ref: dict[str, JsonValue] | None
    initial_canonicalization_manifest_digest: str | None
    baseline_canonical_state_digest: str
    initial_canonical_state_digest: str
    configuration_facts: dict[str, JsonValue]
    modified_canonical_state_digest: str
    storage_projection_ruleset_digest: str
    baseline_is_initial: bool
    rules_semantically_equal: bool


@dataclass(frozen=True, slots=True)
class _MaterializedPreviewInputs:
    sides: dict[str, BoundSnapshotInput]
    canonical: _CanonicalPreviewMetadata
    presentations: dict[str, PresentationMetadata]


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
    return load_step(
        deps.control_transaction_factory,
        operation_id=operation_id,
        step_id=step_id,
        mismatch_error=lambda: PreviewJobError("preview step belongs to a different operation"),
    )


def _serialize_sides(
    sides: dict[str, BoundSnapshotInput],
    payload: PreviewJobPayload,
) -> dict[str, object]:
    document: dict[str, object] = {}
    for role, bound in sides.items():
        document[role] = _side_binding_document(bound, role=role, payload=payload)
    document["initial_reuses_baseline"] = (
        payload.input_completeness is InputCompleteness.MODIFIED_ONLY
    )
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
    materialized_names: set[str] = set()
    for table in bound.table_set.tables:
        if table.artifact is None:
            raise PreviewJobError(
                f"{role} table {table.descriptor.table_name} is missing artifact refs"
            )
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
        snapshot_descriptor_to_document(table)
        for table in bound.summary.tables
        if table.table_name not in materialized_names
    ]
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
        "unmaterialized_descriptors": unmaterialized_descriptors,
        "storage_facts": storage_facts_to_documents(bound.storage_facts),
        "tables": tables,
    }


def _materialized_preview_inputs_from_checkpoint(
    job_state: Mapping[str, object],
    store: ArtifactStorePort,
    *,
    repository_id: str,
    dependencies: PreviewRuntimeDependencies | None = None,
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
        sides[role] = _bound_from_side_document(entry, store, repository_id=repository_id)
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
        or canonical_state_digest_of(sides[_SIDE_INITIAL].summary.tables)
        != canonical.initial_canonical_state_digest
        or modified_digest != canonical.modified_canonical_state_digest
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint canonical state digest does not match its tables",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if dependencies is None:
        raise CheckpointDecodeError(
            "materialize checkpoint presentation resolver is unavailable",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    facts = canonical.configuration_facts
    baseline_presentation = _preview_baseline_presentation(
        workspace_id=facts.workspace_id,
        repository_id=repository_id,
        commit_id=facts.business_baseline_commit_id,
        deps=dependencies,
    )
    runtime_ruleset = migrated_table_ruleset_snapshot()
    if (
        runtime_ruleset.ruleset_digest != canonical.storage_projection_ruleset_digest
        or _same_resolved_rules(
            sides[_SIDE_BASELINE],
            sides[_SIDE_MODIFIED],
            baseline_presentation,
            manifest.presentation,
            runtime_ruleset,
        )
        != canonical.rules_semantically_equal
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint resolved rules do not match",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return _MaterializedPreviewInputs(
        sides=sides,
        canonical=canonical,
        presentations={
            _SIDE_BASELINE: baseline_presentation,
            _SIDE_MODIFIED: manifest.presentation,
            _SIDE_INITIAL: baseline_presentation
            if initial_manifest is None
            else initial_manifest.presentation,
        },
    )


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


def _bound_from_side_document(
    entry: dict[str, object], store: ArtifactStorePort, *, repository_id: str
) -> BoundSnapshotInput:
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
            opened.append(
                open_snapshot_table_artifact(
                    store, manifest_ref, repository_id=repository_id, canonical_required=True
                )
            )
        except (
            TypeError,
            ValueError,
            KeyError,
            ManifestVerificationError,
            ArtifactPublishError,
        ) as exc:
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
        summary_raw = entry.get("summary")
        if type(summary_raw) is not dict or type(summary_raw.get("tables")) is not list:
            raise ValueError("summary tables are invalid")
        descriptors_by_name = {table.descriptor.table_name: table.descriptor for table in opened}
        raw_unmaterialized = entry.get("unmaterialized_descriptors")
        if type(raw_unmaterialized) is not list:
            raise ValueError("unmaterialized_descriptors must be a list")
        for raw_descriptor in raw_unmaterialized:
            descriptor = snapshot_descriptor_from_document(raw_descriptor)
            if descriptor.table_name in descriptors_by_name:
                raise ValueError("unmaterialized descriptor repeats a materialized table")
            descriptors_by_name[descriptor.table_name] = descriptor
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
    table_set = SnapshotTableSet(
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        table_ruleset_version=snapshot.table_ruleset_version,
        tables=tuple(opened),
    )
    try:
        storage_facts = storage_facts_from_documents(entry.get("storage_facts"))
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    descriptors_by_name = {item.table_name: item for item in summary.tables}
    facts_by_name = {item.storage_rule_view.canonical_table: item for item in storage_facts}
    if set(facts_by_name) != set(descriptors_by_name) or any(
        facts_by_name[name].raw_content_digest != descriptor.raw_content_digest
        or facts_by_name[name].canonical_schema_digest is None
        or facts_by_name[name].storage_projection_version is None
        for name, descriptor in descriptors_by_name.items()
    ):
        raise CheckpointDecodeError(
            "materialize checkpoint storage facts do not match table identities",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
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
        message = f"{label} materialization failed"
        if diagnostic is not None and diagnostic.message:
            message = f"{message}: {diagnostic.message}"
        raise PreviewJobError(
            message,
            diagnostic_code=None if diagnostic is None else diagnostic.code.value,
        )
    if result.snapshot is None or result.summary is None:
        raise PreviewJobError(f"{label} materialization is incomplete")
    if canonical_binding is not None:
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


def _comparison_storage_facts(
    manifest: CanonicalizationManifest,
) -> tuple[ComparisonStorageFacts, ...]:
    facts: list[ComparisonStorageFacts] = []
    for table in manifest.tables:
        if (
            table.source_schema_digest is None
            or table.canonical_schema_digest is None
            or table.content_digest is None
        ):
            raise PreviewJobError("canonical manifest is missing table identity facts")
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
                canonical_schema_digest=table.canonical_schema_digest,
                raw_content_digest=table.content_digest,
                storage_projection_version=manifest.storage_projection_version,
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
        artifact_id=build_artifact_id(
            ArtifactLocation.DURABLE, "canonical-table-set-closure", uuid.uuid4().hex
        ),
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


def _assert_configuration_payload(
    facts: ConfigurationFacts, payload: PreviewJobPayload, operation_id: str
) -> None:
    facts.assert_binding(
        workspace_id=payload.workspace_id,
        upload_revision_id=payload.upload_revision_id,
        generation=payload.generation,
        repository_id=payload.repository_id,
        business_baseline_node_id=payload.business_baseline_node_id,
        business_baseline_commit_id=payload.business_baseline_commit_id,
        baseline_head_version=payload.baseline_head_version,
        operation_id=operation_id,
    )
    if (
        facts.modified.source_artifact_id
        != payload.source_artifacts[SourceArtifactRole.MODIFIED].artifact_id
    ):
        raise PreviewJobError("configuration modified source artifact binding mismatch")
    if payload.input_completeness is InputCompleteness.FULL:
        if (
            facts.initial_origin != "UPLOADED"
            or facts.initial.source_artifact_id
            != payload.source_artifacts[SourceArtifactRole.INITIAL].artifact_id
        ):
            raise PreviewJobError("configuration initial source artifact binding mismatch")
    elif facts.initial_origin == "UPLOADED":
        raise PreviewJobError("configuration initial origin does not match input completeness")


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
        "initial_canonical_state_digest": canonical.initial_canonical_state_digest.value,
        "configuration_facts": canonical.configuration_facts.to_document(),
        "baseline_canonical_state_digest": canonical.baseline_canonical_state_digest.value,
        "modified_canonical_state_digest": canonical.modified_canonical_state_digest.value,
        "storage_projection_ruleset_digest": canonical.storage_projection_ruleset_digest.value,
        "baseline_is_initial": canonical.baseline_is_initial,
        "rules_semantically_equal": canonical.rules_semantically_equal,
    }


def _canonical_preview_metadata_from_document(
    raw: dict[str, object],
) -> _CanonicalPreviewMetadata:
    try:
        raw = _CanonicalPreviewDocument.model_validate(raw, strict=True).model_dump()
    except ValueError as exc:
        raise CheckpointDecodeError(
            "canonical preview checkpoint fields are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc
    closure_ref = raw["canonical_table_set_closure_ref"]
    manifest_ref = raw["canonicalization_manifest_ref"]
    initial_manifest_ref = raw["initial_canonicalization_manifest_ref"]
    initial_manifest_digest = raw["initial_canonicalization_manifest_digest"]
    if (
        type(closure_ref) is not dict
        or type(manifest_ref) is not dict
        or (initial_manifest_ref is not None and type(initial_manifest_ref) is not dict)
        or (initial_manifest_digest is not None and type(initial_manifest_digest) is not str)
        or type(raw["baseline_is_initial"]) is not bool
        or type(raw["rules_semantically_equal"]) is not bool
    ):
        raise CheckpointDecodeError(
            "canonical preview checkpoint artifact refs are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    try:
        return _CanonicalPreviewMetadata(
            initial_canonical_state_digest=DigestRef(
                _checkpoint_string(raw, "initial_canonical_state_digest")
            ),
            configuration_facts=ConfigurationFacts.from_document(raw["configuration_facts"]),
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
                None if initial_manifest_digest is None else DigestRef(initial_manifest_digest)
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
            baseline_is_initial=raw["baseline_is_initial"],
            rules_semantically_equal=raw["rules_semantically_equal"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CheckpointDecodeError(
            "canonical preview checkpoint bindings are invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        ) from exc


def _checkpoint_string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _preview_ready_ref(job_state: Mapping[str, object]) -> ArtifactRef:
    try:
        ready_id = job_state.get(_JOB_STATE_READY_CLOSURE)
        bundle_id = job_state.get(_JOB_STATE_BUNDLE_ARTIFACT)
        raw_ref = job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        if type(ready_id) is not str or type(bundle_id) is not str or type(raw_ref) is not dict:
            raise ValueError("invalid preview artifact bindings")
        parse_artifact_id(ready_id)
        parse_artifact_id(bundle_id)
        ref = artifact_ref_from_dict(raw_ref)
        if ref.artifact_id != ready_id:
            raise ValueError("preview ready ID/ref mismatch")
        return ref
    except (ValueError, TypeError, KeyError) as exc:
        raise CheckpointDecodeError(
            "preview checkpoint has invalid artifact bindings", code="CHECKPOINT_JOB_STATE_MISMATCH"
        ) from exc


def _assert_preview_bundle_binding(
    job_state: Mapping[str, object], refs: tuple[ArtifactRef, ...]
) -> None:
    if not any(ref.artifact_id == job_state[_JOB_STATE_BUNDLE_ARTIFACT] for ref in refs):
        raise CheckpointDecodeError(
            "preview bundle ID is outside its ready closure", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )


def _same_resolved_rules(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    before_presentation: PresentationMetadata,
    current_presentation: PresentationMetadata,
    ruleset: TableRulesetSnapshot,
) -> bool:
    def projection(
        bound: BoundSnapshotInput, presentation: PresentationMetadata
    ) -> dict[str, object]:
        comments = {table.table_name: table.comment for table in presentation.tables}
        facts = {
            item.storage_rule_view.canonical_table: item.storage_rule_view
            for item in bound.storage_facts
        }
        if set(facts) != {descriptor.table_name for descriptor in bound.summary.tables}:
            raise PreviewJobError("resolved rule comparison requires complete storage facts")
        rules = comparison_rule_set(ruleset)
        result: dict[str, object] = {}
        for descriptor in bound.summary.tables:
            view = resolve_comparison_rule_view(
                rules,
                descriptor.table_name,
                table_comment=comments.get(descriptor.table_name),
                primary_key_columns=descriptor.primary_key_columns,
            )
            result[descriptor.table_name] = (
                facts.get(descriptor.table_name),
                None if view is None else view.comparison_rule_digest,
            )
        return result

    return projection(before, before_presentation) == projection(current, current_presentation)


def _preview_baseline_presentation(
    *,
    workspace_id: str,
    repository_id: str,
    commit_id: str,
    deps: PreviewRuntimeDependencies,
) -> PresentationMetadata:
    with deps.control_transaction_factory() as unit_of_work:
        workspace = unit_of_work.workspace.get_workspace(workspace_id)
        if workspace is None or workspace.repository_id != repository_id:
            raise PreviewJobError("preview workspace scope is unavailable")
        try:
            metadata = unit_of_work.commit_canonical_metadata.resolve(
                repository_id=repository_id,
                commit_id=commit_id,
                scope=CommitCanonicalScope(
                    gateway_device_external_key=workspace.gateway_device_external_key,
                    business_project_id=workspace.business_project_id,
                ),
            )
        except CommitCanonicalMetadataError as exc:
            raise PreviewJobError(exc.diagnostic, diagnostic_code=exc.code.value) from exc
    return presentation_for_commit(metadata)


__all__ = [
    "PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION",
    "PREVIEW_ASSEMBLE_CHECKPOINT_CONTRACT_VERSION",
    "PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE",
    "PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION",
    "PREVIEW_ASSEMBLE_STATE_DOCUMENT_TYPE",
    "PREVIEW_ASSEMBLE_STATE_CONTRACT_VERSION",
]
