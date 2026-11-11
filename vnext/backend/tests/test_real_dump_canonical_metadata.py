"""Typed metadata proof cannot open IPC, write state or accept broken bindings."""

from __future__ import annotations

from gateway_backend.capabilities.table_presentation.contracts import PresentationMetadata

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import copy
import json
from dataclasses import dataclass, replace
from typing import Any

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from benchmarks.real_dump_canonical_metadata import verify_repeat_canonical_metadata
from gateway_backend.application import preview_jobs as p
from gateway_backend.application.canonical_metadata.binding import _storage_rule_view
from gateway_backend.application.checkpoints import StepCheckpointEnvelope, put_checkpoint_envelope
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.artifacts.canonical_table_store import CANONICAL_IPC_MEDIA_TYPE
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.capabilities.comparison.contracts import ComparisonStorageFacts
from gateway_backend.capabilities.snapshot_materialization._digest import (
    raw_state_digest_of,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    artifact_content_digest_of,
    manifest_from_bytes,
    manifest_to_payload,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ARTIFACT_COMPRESSION_NONE,
    MANIFEST_MEDIA_TYPE,
    ROW_FORMAT_CANONICAL_IPC,
    ROW_MATERIALIZATION_PROFILE,
    MaterializationStage,
    Snapshot,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTableArtifactManifest,
    SourceKind,
    canonical_state_digest_of,
    snapshot_summary_to_document,
    snapshot_to_document,
)
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    compute_manifest_digest,
    canonicalization_manifest_from_bytes,
    durable_manifest_bytes,
)
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_ID,
    RULESET_VERSION,
    CanonicalKeyPolicy,
    OrderedPolicy,
)
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from tests.support.configuration_facts import make_configuration_facts
from tests.support.storage_projection import dummy_digest, int_column, table_descriptor

pytestmark = pytest.mark.unit
REPO, COMMIT, OP = "repo-1", "commit-base", "op-preview-1"
OTHER_DIGEST = "sha256:" + "9" * 64


class MetadataStore(InMemoryArtifactStore):
    """Real ref/hash verification; IPC bytes deliberately do not exist."""

    frozen = False

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        if self.frozen:
            raise AssertionError("metadata proof must not write")
        return super().put(raw_bytes, ref)

    def locate(self, ref: ArtifactRef) -> bytes:
        if ref.media_type == CANONICAL_IPC_MEDIA_TYPE:
            raise AssertionError("metadata proof must not locate IPC")
        return super().locate(ref)

    # Inherited open_buffer delegates to locate, so it also rejects IPC.


@dataclass
class MetadataFixture:
    store: MetadataStore
    payload: p.PreviewJobPayload
    sides: dict[str, Any]
    state: dict[str, Any]
    submission_ref: ArtifactRef
    submission_digest: DigestRef
    serial: int = 0

    def put(self, raw: bytes, media_type: str = "application/jcs") -> ArtifactRef:
        self.serial += 1
        return put_with_built_ref(self.store, raw, artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", f"metadata-{self.serial}"),
                                  media_type=media_type)

    def prove(self, *, envelope_changes: dict[str, Any] | None = None,
              ref_changes: dict[str, Any] | None = None) -> dict[str, Any]:
        document = {"document_type": p.PREVIEW_MATERIALIZED_SIDES_DOCUMENT_TYPE,
                    "contract_version": p.PREVIEW_MATERIALIZED_SIDES_CONTRACT_VERSION,
                    "sides": self.sides}
        self.state["materialized_sides_ref"] = artifact_ref_to_dict(
            self.put(canonicalize_json_value(document)))
        envelope = StepCheckpointEnvelope(p.PREVIEW_JOB_KIND, p.PREVIEW_STEP_MATERIALIZE, OP,
            p.PREVIEW_JOB_CONTRACT_VERSION, 0, (), self.state)
        ref = put_checkpoint_envelope(self.store, envelope)
        if envelope_changes:
            raw = envelope.to_document()
            raw.update(envelope_changes)
            ref = self.put(canonicalize_json_value(raw))
        if ref_changes:
            ref = replace(ref, **ref_changes)
        self.store.frozen = True
        return verify_repeat_canonical_metadata(self.store, checkpoint_ref=ref,
            operation_id=OP, repository_id=REPO, commit_id=COMMIT, payload=self.payload,
            submission_manifest_ref=self.submission_ref,
            submission_manifest_digest=self.submission_digest)


def _fixture() -> MetadataFixture:
    store = MetadataStore()
    source = SourceArtifactBinding("a1:durable:ba818a521fed3b2757a17badbc09fd4393d77f7c1c1887a65a74edb8905fe303", "application/gzip", 1, dummy_digest().value)
    payload = p.PreviewJobPayload("ws-1", "ur-1", 1, REPO, "node-1", COMMIT, 1,
        InputCompleteness.MODIFIED_ONLY, {SourceArtifactRole.MODIFIED: source},
        {"MODIFIED": source.raw_sha256}, dummy_digest().value, "v1", dummy_digest().value,
        {}, {}, "v1", p.PreviewIdempotencyIdentity("ws-1", "key-1"), {})
    descriptors = tuple(table_descriptor(f"t_{i:03d}", (int_column("id"),),
        primary_key_columns=("id",), row_count=1) for i in range(312))
    canonical_tables = tuple(CanonicalizationManifestTable(d.table_name, 1, 1,
        CanonicalKeyPolicy.EXPLICIT, OrderedPolicy.NONE, ("id",), (), (), ("id",),
        dummy_digest(), dummy_digest(), d.raw_content_digest) for d in descriptors)
    manifest = CanonicalizationManifest(CANONICALIZATION_MANIFEST_CONTRACT,
        STORAGE_PROJECTION_VERSION, RULESET_ID, RULESET_VERSION, dummy_digest(),
        dummy_digest(), canonical_tables,
        PresentationMetadata().project((t.name, t.retained_columns) for t in canonical_tables))
    manifest = replace(manifest, manifest_digest=compute_manifest_digest(manifest))
    assert manifest.manifest_digest is not None
    f = MetadataFixture(store, payload, {}, {}, ArtifactRef('a1:durable:8137c58af077cafc2702c843d5e79b85e00bc871674dcc5867a64f36f27f3588', "application/jcs", 0,
        raw_blob_digest(b"")), manifest.manifest_digest)
    f.submission_ref = f.put(durable_manifest_bytes(manifest), CANONICALIZATION_MANIFEST_MEDIA_TYPE)
    tables_digest = canonical_state_digest_of(descriptors)
    assert tables_digest is not None
    snapshot_digest = snapshot_digest_of(stage=MaterializationStage.FINAL, parser_version=1,
        table_ruleset_version=1, tables=descriptors)
    base_context = SnapshotSourceContext(SourceKind.IMMUTABLE_REPOSITORY_REF,
        repository_id=REPO, repository_ref=COMMIT, resolved_commit_hash=COMMIT)
    facts = make_configuration_facts(modified_digest=tables_digest.value,
        baseline_digest=tables_digest.value, rules_digest=dummy_digest().value,
        uploaded_initial=False)
    modified_context = SnapshotSourceContext(SourceKind.SQL_DUMP_SOURCE,
        sql_source_digest=DigestRef(facts.modified.sql_source_digest or ""))
    storage_facts = tuple(ComparisonStorageFacts(_storage_rule_view(t), dummy_digest(),
        dummy_digest(), t.content_digest, STORAGE_PROJECTION_VERSION) for t in canonical_tables)
    for role, context in ((p._SIDE_BASELINE, base_context), (p._SIDE_MODIFIED, modified_context)):
        snapshot = Snapshot(f"snapshot-{role}", context.source_kind, 1, 1, 1, 1,
            ROW_MATERIALIZATION_PROFILE, MaterializationStage.FINAL, snapshot_digest,
            raw_state_digest_of(descriptors), "2026-11-09T00:00:00Z", context)
        summary = SnapshotSummary(snapshot.snapshot_id, snapshot.snapshot_digest,
            snapshot.raw_state_digest, snapshot.materialization_stage, 1, 1, 1,
            len(descriptors), descriptors, context, (), len(descriptors))
        entries = []
        for d in (() if role == p._SIDE_BASELINE else descriptors):
            # Metadata references absent IPC, not a dummy row-reader implementation.
            row_ref = ArtifactRef(build_artifact_id(ArtifactLocation.CANONICAL, "test-fixture",
                ["ipc", d.table_name]), CANONICAL_IPC_MEDIA_TYPE, 17,
                                  raw_blob_digest(b"IPC not opened by metadata proof"))
            table = SnapshotTableArtifactManifest(1, snapshot_digest, d.table_name, d,
                (row_ref,), ROW_FORMAT_CANONICAL_IPC, ARTIFACT_COMPRESSION_NONE,
                ROW_MATERIALIZATION_PROFILE, artifact_content_digest_of(row_file_refs=(row_ref,),
                    descriptor=d, row_format=ROW_FORMAT_CANONICAL_IPC, repository_id=REPO),
                "2026-11-09T00:00:00Z", REPO)
            ref = f.put(canonicalize_json_value(manifest_to_payload(table)), MANIFEST_MEDIA_TYPE)
            entries.append({"table_name": d.table_name, "manifest_ref": artifact_ref_to_dict(ref),
                            "row_file_refs": [artifact_ref_to_dict(row_ref)]})
        f.sides[role] = {"contract_version": p.PREVIEW_MATERIALIZE_SIDE_CONTRACT_VERSION,
            "snapshot": snapshot_to_document(snapshot), "summary": snapshot_summary_to_document(summary),
            "snapshot_digest": snapshot.snapshot_digest.value,
            "raw_state_digest": snapshot.raw_state_digest.value,
            "unmaterialized_descriptors": [p._snapshot_descriptor_to_document(d) for d in descriptors]
                if role == p._SIDE_BASELINE else [],
            "storage_facts": p._storage_facts_to_documents(storage_facts),
            "tables": entries, "source_ref": None if role == p._SIDE_BASELINE else
                artifact_ref_to_dict(p._artifact_ref_from_binding(source)),
            "repository_identity": {"repository_id": REPO, "repository_ref": COMMIT,
                "resolved_commit_hash": COMMIT} if role == p._SIDE_BASELINE else None}
    f.sides[p._SIDE_INITIAL] = copy.deepcopy(f.sides[p._SIDE_BASELINE])
    f.sides["initial_reuses_baseline"] = True
    closure = canonicalize_json_value({"contract_version": p._CANONICAL_TABLE_CLOSURE_CONTRACT,
        "tables": [{"table_name": t["table_name"], "manifest_ref": t["manifest_ref"]}
                   for t in f.sides[p._SIDE_MODIFIED]["tables"]]})
    canonical = p._CanonicalPreviewMetadata(tables_digest, facts, f.put(closure),
        f.submission_ref, manifest.manifest_digest, None, None, tables_digest, tables_digest,
        dummy_digest(), False)
    f.state["canonical_preview"] = p._canonical_preview_metadata_to_document(canonical)
    return f


def test_repeat_metadata_proves_all_312_without_ipc_or_writes() -> None:
    f = _fixture()
    result = f.prove()
    assert len(result["U"]) == 312
    assert result["X"] == result["A"] == result["D"] == []
    assert result["logical_baseline_row_demand"] == 0
    assert result["before_identities"] == result["current_identities"]


# Shared meaningful edges, not a per-table matrix. All paths run the real helper
# against owning serialized metadata and a ref/hash-verifying read-only store.
FAULTS = (
    ("checkpoint operation", "checkpoint scope"),
    ("checkpoint version", "unsupported checkpoint"),
    ("checkpoint ref", "stored artifact identity mismatch"),
    ("checkpoint media", "checkpoint ref media type"),
    ("FULL", "MODIFIED_ONLY"),
    ("wrong commit", "repository/commit"),
    ("configuration operation", "configuration facts"),
    ("initial reuse", "INITIAL must reuse"),
    ("duplicate summary", "summary descriptor"),
    ("duplicate fact", "storage fact set"),
    ("source schema", "side identities"),
    ("projection", "side identities"),
    ("row refs", "side row refs"),
    ("missing current ref", "complete MODIFIED manifest ref set"),
    ("artifact content", "artifact content digest"),
    ("closure", "closure bytes"),
    ("persisted manifest digest", "manifest digest/ruleset"),
    ("missing identity", "missing canonical identity"),
)


@pytest.mark.parametrize(("fault", "message"), FAULTS)
def test_repeat_metadata_rejects_incomplete_or_contradictory_bindings(fault: str, message: str) -> None:
    f = _fixture()
    current = f.sides[p._SIDE_MODIFIED]
    canonical = f.state["canonical_preview"]
    envelope = None
    ref_changes: dict[str, Any] | None = None
    if fault == "checkpoint operation":
        envelope = {"operation_id": "other-op"}
    elif fault == "checkpoint version":
        envelope = {"checkpoint_contract_version": "unsupported"}
    elif fault == "checkpoint ref":
        ref_changes = {"raw_sha256": DigestRef(OTHER_DIGEST)}
    elif fault == "checkpoint media":
        ref_changes = {"media_type": "application/octet-stream"}
    elif fault == "FULL":
        f.payload = replace(f.payload, input_completeness=InputCompleteness.FULL)
    elif fault == "wrong commit":
        f.payload = replace(f.payload, business_baseline_commit_id="other-commit")
    elif fault == "configuration operation":
        f.payload = replace(f.payload, workspace_id="other-workspace")
    elif fault == "initial reuse":
        f.sides["initial_reuses_baseline"] = False
    elif fault == "duplicate summary":
        current["summary"]["tables"].append(copy.deepcopy(current["summary"]["tables"][0]))
    elif fault == "duplicate fact":
        current["storage_facts"].append(copy.deepcopy(current["storage_facts"][0]))
    elif fault in {"source schema", "projection"}:
        key = "source_schema_digest" if fault == "source schema" else "storage_projection_version"
        current["storage_facts"][0][key] = OTHER_DIGEST if fault == "source schema" else "unsupported"
    elif fault == "row refs":
        current["tables"][0]["row_file_refs"] = []
    elif fault == "missing current ref":
        entry = current["tables"].pop(0)
        table_manifest = manifest_from_bytes(f.store.locate(artifact_ref_from_dict(entry["manifest_ref"])))
        current["unmaterialized_descriptors"].append(p._snapshot_descriptor_to_document(table_manifest.descriptor))
        closure = canonicalize_json_value({"contract_version": p._CANONICAL_TABLE_CLOSURE_CONTRACT,
            "tables": [{"table_name": t["table_name"], "manifest_ref": t["manifest_ref"]}
                       for t in current["tables"]]})
        canonical["canonical_table_set_closure_ref"] = artifact_ref_to_dict(f.put(closure))
    elif fault == "artifact content":
        entry = current["tables"][0]
        raw = json.loads(f.store.locate(artifact_ref_from_dict(entry["manifest_ref"])))
        raw["artifact_content_digest"] = OTHER_DIGEST
        entry["manifest_ref"] = artifact_ref_to_dict(f.put(canonicalize_json_value(raw), MANIFEST_MEDIA_TYPE))
    elif fault == "closure":
        canonical["canonical_table_set_closure_ref"] = artifact_ref_to_dict(f.put(b"{}"))
    elif fault == "persisted manifest digest":
        f.submission_digest = DigestRef(OTHER_DIGEST)
    elif fault == "missing identity":
        canonical_manifest = canonicalization_manifest_from_bytes(f.store.locate(f.submission_ref))
        canonical_manifest = replace(canonical_manifest,
            tables=(replace(canonical_manifest.tables[0], source_schema_digest=None),
                    *canonical_manifest.tables[1:]), manifest_digest=None)
        canonical_manifest = replace(canonical_manifest,
            manifest_digest=compute_manifest_digest(canonical_manifest))
        assert canonical_manifest.manifest_digest is not None
        f.submission_digest = canonical_manifest.manifest_digest
        f.submission_ref = f.put(durable_manifest_bytes(canonical_manifest), CANONICALIZATION_MANIFEST_MEDIA_TYPE)
    else:
        raise AssertionError(fault)
    with pytest.raises(ValueError, match=message):
        f.prove(envelope_changes=envelope, ref_changes=ref_changes)
