"""Metadata-only proof for the fixed MODIFIED_ONLY, noninitial W2 journey.

This verifier checks metadata bindings, never IPC bytes. Production Preview
owns physical row validation. Missing or contradictory metadata fails closed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.application import preview_jobs as p
from gateway_backend.application.canonical_metadata.binding import _storage_rule_view
from gateway_backend.application.checkpoints import (
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
)
from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, artifact_ref_from_dict
from gateway_backend.artifacts.canonical_table_store import CANONICAL_IPC_MEDIA_TYPE
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
from gateway_backend.capabilities.comparison.contracts import ComparisonStorageFacts
from gateway_backend.capabilities.snapshot_materialization import canonical_state_digest_of
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    artifact_content_digest_of,
    manifest_from_bytes,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MANIFEST_MEDIA_TYPE,
    ROW_FORMAT_CANONICAL_IPC,
    Snapshot,
    SnapshotSummary,
    SnapshotTableDescriptor,
    SourceKind,
    snapshot_from_document,
    snapshot_summary_from_document,
)
from gateway_backend.capabilities.storage_projection import (
    CanonicalizationManifest,
    open_canonicalization_manifest,
)
from gateway_backend.domain.workspace.models import InputCompleteness, SourceArtifactRole


def _require(value: object, message: str) -> None:
    if not value:
        raise ValueError(message)


@dataclass(frozen=True)
class _MetadataSide:
    snapshot: Snapshot
    summary: SnapshotSummary
    facts: tuple[ComparisonStorageFacts, ...]
    table_refs: tuple[tuple[str, ArtifactRef], ...]


def _side(raw: Any, store: ArtifactStorePort, repository_id: str) -> _MetadataSide:
    _require(type(raw) is dict, "side metadata must be an object")
    _require(set(raw) == {"contract_version", "snapshot", "source_ref", "repository_identity",
             "snapshot_digest", "raw_state_digest", "summary", "unmaterialized_descriptors",
             "storage_facts", "tables"}, "side metadata fields mismatch")
    _require(raw.get("contract_version") == p.PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION,
             "side contract version mismatch")
    snapshot = snapshot_from_document(raw.get("snapshot"))
    _require(snapshot.snapshot_digest.value == raw.get("snapshot_digest")
             and snapshot.raw_state_digest.value == raw.get("raw_state_digest"),
             "side snapshot digest mismatch")
    _require(type(raw.get("tables")) is list
             and type(raw.get("unmaterialized_descriptors")) is list,
             "side table metadata must be lists")
    descriptors: dict[str, SnapshotTableDescriptor] = {}
    refs: list[tuple[str, ArtifactRef]] = []
    manifest_ids: set[str] = set()
    for item in raw["tables"]:
        _require(type(item) is dict and set(item) == {"table_name", "manifest_ref", "row_file_refs"},
                 "side table entry fields mismatch")
        ref = artifact_ref_from_dict(item["manifest_ref"])
        _require(ref.media_type == MANIFEST_MEDIA_TYPE and ref.artifact_id not in manifest_ids,
                 "side manifest ref type or uniqueness mismatch")
        manifest_ids.add(ref.artifact_id)
        manifest = manifest_from_bytes(store.locate(ref))
        _require(manifest.repository_id == repository_id
                 and manifest.row_format == ROW_FORMAT_CANONICAL_IPC
                 and len(manifest.row_file_refs) == 1
                 and manifest.row_file_refs[0].media_type == CANONICAL_IPC_MEDIA_TYPE,
                 "canonical IPC metadata repository/format/ref mismatch")
        _require(type(item["row_file_refs"]) is list
                 and tuple(artifact_ref_from_dict(r) for r in item["row_file_refs"])
                 == manifest.row_file_refs, "side row refs differ from manifest")
        _require(manifest.artifact_content_digest == artifact_content_digest_of(
            row_file_refs=manifest.row_file_refs, descriptor=manifest.descriptor,
            row_format=manifest.row_format, repository_id=repository_id),
            "canonical IPC metadata artifact content digest mismatch")
        _require(item["table_name"] == manifest.table_name
                 and manifest.snapshot_digest == snapshot.snapshot_digest,
                 "table manifest snapshot/name binding mismatch")
        _require(manifest.table_name not in descriptors, "duplicate materialized table")
        descriptors[manifest.table_name] = manifest.descriptor
        refs.append((manifest.table_name, ref))
    for item in raw["unmaterialized_descriptors"]:
        descriptor = p._snapshot_descriptor_from_document(item)
        _require(descriptor.table_name not in descriptors, "duplicate unmaterialized table")
        descriptors[descriptor.table_name] = descriptor
    summary_raw = raw.get("summary")
    _require(type(summary_raw) is dict and type(summary_raw.get("tables")) is list,
             "side summary tables missing")
    names = [item.get("table_name") for item in summary_raw["tables"] if type(item) is dict]
    _require(len(names) == len(summary_raw["tables"]) == len(set(names))
             and set(names) == set(descriptors), "summary descriptor set/uniqueness mismatch")
    summary = snapshot_summary_from_document(
        summary_raw, snapshot=snapshot, tables=tuple(descriptors[name] for name in names))
    facts = p._storage_facts_from_documents(raw.get("storage_facts"))
    fact_names = [f.storage_rule_view.canonical_table for f in facts]
    _require(len(fact_names) == len(set(fact_names)) and set(fact_names) == set(descriptors),
             "storage fact set/uniqueness mismatch")
    by_name = {f.storage_rule_view.canonical_table: f for f in facts}
    for name, descriptor in descriptors.items():
        fact = by_name[name]
        _require(descriptor.raw_content_digest is not None
                 and descriptor.raw_content_digest == fact.raw_content_digest
                 and fact.canonical_schema_digest is not None
                 and fact.storage_projection_version is not None,
                 "storage facts do not match descriptor identities")
    return _MetadataSide(snapshot, summary, facts, tuple(refs))


def _identities(manifest: CanonicalizationManifest, side: _MetadataSide) -> dict[str, Any]:
    descriptors = {t.table_name: t for t in side.summary.tables}
    facts = {t.storage_rule_view.canonical_table: t for t in side.facts}
    _require(set(descriptors) == set(facts) == {t.name for t in manifest.tables},
             "canonical manifest and side table sets differ")
    identities: dict[str, Any] = {}
    for table in manifest.tables:
        descriptor, fact = descriptors[table.name], facts[table.name]
        if (table.content_digest is None or table.source_schema_digest is None
                or table.canonical_schema_digest is None):
            raise ValueError("missing canonical identity")
        view = _storage_rule_view(table)
        _require(descriptor.row_count == table.canonical_row_count
                 and descriptor.raw_content_digest == table.content_digest
                 and fact.raw_content_digest == table.content_digest
                 and fact.source_schema_digest == table.source_schema_digest
                 and fact.canonical_schema_digest == table.canonical_schema_digest
                 and fact.storage_rule_view == view
                 and fact.storage_projection_version == manifest.storage_projection_version,
                 "canonical manifest and side identities differ")
        identities[table.name] = {
            "row_count": descriptor.row_count,
            "raw_content_digest": table.content_digest.value,
            "business_schema_digest": descriptor.business_schema_digest.value,
            "source_schema_digest": table.source_schema_digest.value,
            "canonical_schema_digest": table.canonical_schema_digest.value,
            "storage_rule_view": asdict(view),
            "storage_projection_version": manifest.storage_projection_version,
        }
    return identities


def verify_repeat_canonical_metadata(
    store: ArtifactStorePort, *, checkpoint_ref: ArtifactRef,
    operation_id: str, repository_id: str, commit_id: str,
    payload: p.PreviewJobPayload, submission_manifest_ref: ArtifactRef,
    submission_manifest_digest: DigestRef,
) -> dict[str, Any]:
    """Prove U312/XAD-empty from exact checkpoint and Submission metadata only.

    The caller owns SQL success/step/operation/payload-version bindings and the
    stable read transaction/read_session. No row ref is located or opened here.
    """
    _require(payload.repository_id == repository_id
             and payload.business_baseline_commit_id == commit_id
             and payload.input_completeness is InputCompleteness.MODIFIED_ONLY,
             "fixed W2 repository/commit/MODIFIED_ONLY payload binding mismatch")
    _require(checkpoint_ref.media_type == "application/jcs", "checkpoint ref media type mismatch")
    envelope = load_checkpoint_envelope(store, checkpoint_ref)
    _require((envelope.operation_id, envelope.step_name, envelope.job_kind,
              envelope.job_contract_version) == (operation_id, p.PREVIEW_STEP_MATERIALIZE,
              p.PREVIEW_JOB_KIND, p.PREVIEW_JOB_CONTRACT_VERSION), "checkpoint scope mismatch")
    state = envelope.job_state
    _require(set(state) == {p._JOB_STATE_MATERIALIZED_SIDES_REF, p._JOB_STATE_CANONICAL},
             "materialize checkpoint fields mismatch")
    canonical = p._canonical_preview_metadata_from_document(state[p._JOB_STATE_CANONICAL])  # type: ignore[arg-type]
    p._assert_configuration_payload(canonical.configuration_facts, payload, operation_id)
    _require(not canonical.baseline_is_initial and canonical.initial_canonicalization_manifest_ref is None
             and canonical.initial_canonicalization_manifest_digest is None,
             "fixed W2 must reuse noninitial baseline without INITIAL manifest")
    sides_ref = artifact_ref_from_dict(state[p._JOB_STATE_MATERIALIZED_SIDES_REF])  # type: ignore[arg-type]
    _require(sides_ref.media_type == "application/jcs", "sides ref media type mismatch")
    document = load_checkpoint_state_artifact(
        store, sides_ref, document_type=p.PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
        contract_version=p.PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION)
    _require(set(document) == {"document_type", "contract_version", p._JOB_STATE_SIDES},
             "materialized sides document fields mismatch")
    raw = document[p._JOB_STATE_SIDES]
    _require(type(raw) is dict and set(raw) == {p._SIDE_BASELINE, p._SIDE_INITIAL,
             p._SIDE_MODIFIED, "initial_reuses_baseline"}, "three-side metadata fields mismatch")
    # Narrow fixed-scope proof; no general FULL restore and no fake row readers.
    raw_sides: Any = raw
    _require(raw_sides["initial_reuses_baseline"] is True
             and raw_sides[p._SIDE_INITIAL] == raw_sides[p._SIDE_BASELINE],
             "INITIAL must reuse exact BASELINE metadata")
    baseline = _side(raw_sides[p._SIDE_BASELINE], store, repository_id)
    current = _side(raw_sides[p._SIDE_MODIFIED], store, repository_id)
    source = baseline.snapshot.source_context
    _require(source.source_kind is SourceKind.IMMUTABLE_REPOSITORY_REF
             and source.repository_id == repository_id and source.resolved_commit_hash == commit_id
             and raw_sides[p._SIDE_BASELINE].get("repository_identity") == {
                 "repository_id": repository_id, "repository_ref": source.repository_ref,
                 "resolved_commit_hash": commit_id}, "baseline exact Repository commit binding mismatch")
    modified_source = payload.source_artifacts[SourceArtifactRole.MODIFIED]
    _require(current.snapshot.source_kind is SourceKind.SQL_DUMP_SOURCE
             and raw_sides[p._SIDE_MODIFIED].get("source_ref")
             == artifact_ref_to_dict(p._artifact_ref_from_binding(modified_source))
             and current.snapshot.source_context.sql_source_digest is not None
             and current.snapshot.source_context.sql_source_digest.value
             == canonical.configuration_facts.modified.sql_source_digest,
             "modified source/configuration binding mismatch")
    for side, digest in ((baseline, canonical.baseline_canonical_state_digest),
                         (baseline, canonical.initial_canonical_state_digest),
                         (current, canonical.modified_canonical_state_digest)):
        _require(canonical_state_digest_of(side.summary.tables) == digest,
                 "three-side canonical state digest mismatch")
    closure = canonicalize_jcs(canonicalize_json_value({
        "contract_version": p._CANONICAL_TABLE_CLOSURE_CONTRACT,
        "tables": [{"table_name": name, "manifest_ref": artifact_ref_to_dict(ref)}
                   for name, ref in sorted(current.table_refs, key=lambda item: item[0].encode("utf-8"))],
    }))
    _require(canonical.canonical_table_set_closure_ref.media_type == "application/jcs"
             and store.locate(canonical.canonical_table_set_closure_ref) == closure,
             "MODIFIED canonical table closure bytes mismatch")
    before_manifest = open_canonicalization_manifest(store, submission_manifest_ref)
    after_manifest = open_canonicalization_manifest(store, canonical.canonicalization_manifest_ref)
    _require(before_manifest.manifest_digest == submission_manifest_digest
             and after_manifest.manifest_digest == canonical.canonicalization_manifest_digest
             and before_manifest.ruleset_digest == after_manifest.ruleset_digest
             == canonical.storage_projection_ruleset_digest,
             "Submission/checkpoint manifest digest/ruleset binding mismatch")
    before, after = _identities(before_manifest, baseline), _identities(after_manifest, current)
    u = sorted(name for name in before.keys() & after.keys() if before[name] == after[name])
    x = sorted(name for name in before.keys() & after.keys() if before[name] != after[name])
    added, deleted = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    _require(len(u) == 312 and not x and not added and not deleted
             and canonical.baseline_canonical_state_digest == canonical.modified_canonical_state_digest,
             "fixed W2 requires full U312 and empty X/A/D")
    return {"repository_id": repository_id, "operation_id": operation_id, "exact_commit": commit_id,
            "checkpoint_ref": artifact_ref_to_dict(checkpoint_ref),
            "baseline_manifest_ref": artifact_ref_to_dict(submission_manifest_ref),
            "current_manifest_ref": artifact_ref_to_dict(canonical.canonicalization_manifest_ref),
            "U": u, "X": x, "A": added, "D": deleted, "logical_baseline_row_demand": 0,
            "before_identities": before, "current_identities": after,
            "policy": "owning typed metadata/ref bindings only; IPC physical reads remain Preview-owned; independent of HTTP count"}
