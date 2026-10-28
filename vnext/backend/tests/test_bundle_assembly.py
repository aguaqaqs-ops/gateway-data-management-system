"""Deterministic Bundle assembly and final closure tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleAssemblyContext,
    BundleAssemblyInput,
    BundleAssemblyPolicy,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleRefScope,
    BundleTableBinding,
    BundleTableSide,
    assemble_bundle,
    validate_bundle,
)
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonTableFact,
    ComparisonTableStatus,
)
from gateway_backend.capabilities.risk_evaluation import (
    ANNOTATION_MANIFEST_MEDIA_TYPE,
    ANNOTATION_MEDIA_TYPE,
    RiskLevel,
    RiskReasonCode,
)
from gateway_backend.capabilities.surface_assembly import (
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceRiskRefs,
    assemble_surface,
    compute_surface_digest,
    validate_surface,
)

from tests.test_surface_assembly import _facts, _request as _surface_request

pytestmark = pytest.mark.unit
_S1B_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "bundle"
    / "s1b"
    / "snapshot-table-bindings.json"
)


class _TamperStore(InMemoryArtifactStore):
    def __init__(self, tamper_id: str) -> None:
        super().__init__()
        self._tamper_id = tamper_id

    def locate(self, ref: ArtifactRef) -> bytes:
        raw = super().locate(ref)
        return raw + b"tampered" if ref.artifact_id == self._tamper_id else raw


class _FailingDestinationStore(InMemoryArtifactStore):
    def __init__(self, fail_after: int) -> None:
        super().__init__()
        self._puts = 0
        self._fail_after = fail_after

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        if self._puts >= self._fail_after:
            raise RuntimeError("destination publication failure")
        self._puts += 1
        return super().put(raw_bytes, ref)


def _raw_ref(name: str, raw: bytes, media_type: str = "application/json") -> ArtifactRef:
    return ArtifactRef(name, media_type, len(raw), raw_blob_digest(raw))


def _surface_result(
    *, root_ref: ArtifactRef | None = None, table_name: str = "orders"
) -> SurfaceAssemblyResult:
    facts = _facts(ComparisonTableFact(table_name=table_name, status=ComparisonTableStatus.UNCHANGED))
    result = assemble_surface(_surface_request(facts))
    assert result.surface is not None
    if root_ref is None:
        return result
    surface = replace(
        result.surface,
        refs=replace(result.surface.refs, diagnostics_ref=root_ref),
        diagnostics=replace(result.surface.diagnostics, diagnostics_ref=root_ref),
    )
    surface = replace(surface, surface_digest=compute_surface_digest(surface))
    validate_surface(surface)
    return SurfaceAssemblyResult(status=SurfaceAssemblyStatus.READY, surface=surface)


def _request(
    pairs: tuple[BundlePairInput, ...],
    *,
    profile: BundleProfile = BundleProfile.SINGLE_PAIR,
    inputs: tuple[BundleInput, ...] | None = None,
    shared: BundleArtifactClosure = BundleArtifactClosure(),
) -> BundleAssemblyInput:
    return BundleAssemblyInput(
        bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=profile,
        inputs=inputs
        or (
            BundleInput(0, "before", "Before"),
            BundleInput(1, "current", "Current"),
        ),
        pairs=pairs,
        shared_artifacts=shared,
        ref_scope=BundleRefScope.BUNDLE_RELATIVE,
    )


def test_single_pair_bundle_is_replayable_and_does_not_inline_rows() -> None:
    source = InMemoryArtifactStore()
    surface_result = _surface_result()
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, surface_result),)),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    validate_bundle(result.bundle, source)
    assert result.bundle.summary.pair_count == 1
    surface_raw = source.locate(result.bundle.pairs[0].surface_ref)
    assert b"before_values" not in surface_raw
    assert b"current_values" not in surface_raw


def test_input_order_changes_do_not_change_bundle_document_or_digest() -> None:
    surface_result = _surface_result()
    first = _request(
        (BundlePairInput("pair", 0, 1, surface_result),),
        inputs=(BundleInput(0, "before", "Before"), BundleInput(1, "current", "Current")),
    )
    second = _request(
        (BundlePairInput("pair", 0, 1, surface_result),),
        inputs=(BundleInput(1, "current", "Current"), BundleInput(0, "before", "Before")),
    )
    one = assemble_bundle(first, source_store=InMemoryArtifactStore())
    two = assemble_bundle(second, source_store=InMemoryArtifactStore())

    assert one.status is BundleAssemblyStatus.READY
    assert two.status is BundleAssemblyStatus.READY
    assert one.bundle is not None and two.bundle is not None
    assert one.bundle.bundle_digest == two.bundle.bundle_digest
    assert one.bundle.to_document() == two.bundle.to_document()


def test_multi_pair_shared_snapshot_is_published_once() -> None:
    raw = b"snapshot rows"
    snapshot_ref = _raw_ref("snapshot-source", raw, "application/vnd.apache.parquet")
    snapshot_ref_two = _raw_ref("snapshot-source-two", raw, "application/vnd.apache.parquet")
    first = _surface_result(root_ref=snapshot_ref, table_name="orders")
    second = _surface_result(root_ref=snapshot_ref_two, table_name="settings")
    binding_one = BundleArtifactBinding(
        snapshot_ref,
        "pairs/left_to_middle/tables/current/orders.parquet",
        BundleArtifactKind.SNAPSHOT_TABLE,
        pair_id="left_to_middle",
        table_name="orders",
    )
    binding_two = BundleArtifactBinding(
        snapshot_ref_two,
        "pairs/middle_to_right/tables/current/settings.parquet",
        BundleArtifactKind.SNAPSHOT_TABLE,
        pair_id="middle_to_right",
        table_name="settings",
    )
    source = InMemoryArtifactStore()
    source.put(raw, snapshot_ref)
    source.put(raw, snapshot_ref_two)
    result = assemble_bundle(
        _request(
            (
                BundlePairInput("left_to_middle", 0, 1, first, BundleArtifactClosure((binding_one,))),
                BundlePairInput("middle_to_right", 1, 2, second, BundleArtifactClosure((binding_two,))),
            ),
            profile=BundleProfile.MULTI_PAIR,
            inputs=(
                BundleInput(0, "left", "Left"),
                BundleInput(1, "middle", "Middle"),
                BundleInput(2, "right", "Right"),
            ),
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    closure_raw = source.locate(result.bundle.artifact_closure_ref)
    closure = json.loads(closure_raw)
    snapshot_entries = [
        item for item in closure["closure_entries"] if item["kind"] == BundleArtifactKind.SNAPSHOT_TABLE
    ]
    golden = json.loads(_S1B_GOLDEN.read_text(encoding="utf-8"))
    assert golden["contract_version"] == BUNDLE_CONTRACT_VERSION
    expected = golden["cases"]["identical_snapshot_rows_across_pairs"]
    actual = {
        "binding_count": len(snapshot_entries),
        "entries": [
            {
                key: item[key]
                for key in ("kind", "logical_path", "shared", "table_bindings")
            }
            for item in snapshot_entries
        ],
    }
    assert actual == expected


def test_snapshot_table_reference_shared_between_sides_keeps_both_bindings() -> None:
    raw = b"same rows on both sides"
    snapshot_ref = _raw_ref("same-snapshot", raw, "application/vnd.apache.parquet")
    source = InMemoryArtifactStore()
    source.put(raw, snapshot_ref)
    surface = _surface_result()
    closure = BundleArtifactClosure(
        (
            BundleArtifactBinding(
                snapshot_ref,
                "pairs/pair/tables/before/items/rows/000000.parquet",
                BundleArtifactKind.SNAPSHOT_TABLE,
                pair_id="pair",
                table_name="items",
            ),
            BundleArtifactBinding(
                snapshot_ref,
                "pairs/pair/tables/current/items/rows/000000.parquet",
                BundleArtifactKind.SNAPSHOT_TABLE,
                pair_id="pair",
                table_name="items",
            ),
        )
    )

    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, surface, closure),)),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    closure_document = json.loads(source.locate(result.bundle.artifact_closure_ref))
    snapshot_entries = [
        item
        for item in closure_document["closure_entries"]
        if item["kind"] == BundleArtifactKind.SNAPSHOT_TABLE.value
    ]
    assert len(snapshot_entries) == 1
    assert snapshot_entries[0]["shared"] is True
    assert snapshot_entries[0]["logical_path"].startswith("shared/snapshot-tables/")
    assert snapshot_entries[0]["table_bindings"] == [
        {"pair_id": "pair", "side": "before", "table_name": "items"},
        {"pair_id": "pair", "side": "current", "table_name": "items"},
    ]


def test_multi_pair_identical_artifact_refs_are_shared() -> None:
    records_raw = b"shared record bytes"
    records_ref = _raw_ref("records-shared", records_raw, media_type="application/octet-stream")
    first = _surface_result()
    second = _surface_result()
    binding_one = BundleArtifactBinding(
        records_ref,
        "pairs/left_to_middle/comparison/records/orders/rows.bin",
        BundleArtifactKind.RECORDS,
        pair_id="left_to_middle",
    )
    binding_two = BundleArtifactBinding(
        records_ref,
        "pairs/middle_to_right/comparison/records/orders/rows.bin",
        BundleArtifactKind.RECORDS,
        pair_id="middle_to_right",
    )
    source = InMemoryArtifactStore()
    source.put(records_raw, records_ref)
    result = assemble_bundle(
        _request(
            (
                BundlePairInput("left_to_middle", 0, 1, first, BundleArtifactClosure((binding_one,))),
                BundlePairInput("middle_to_right", 1, 2, second, BundleArtifactClosure((binding_two,))),
            ),
            profile=BundleProfile.MULTI_PAIR,
            inputs=(
                BundleInput(0, "left", "Left"),
                BundleInput(1, "middle", "Middle"),
                BundleInput(2, "right", "Right"),
            ),
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    closure_raw = source.locate(result.bundle.artifact_closure_ref)
    closure = json.loads(closure_raw)
    record_entries = [
        item for item in closure["closure_entries"] if item["kind"] == BundleArtifactKind.RECORDS.value
    ]
    assert len(record_entries) == 1
    assert record_entries[0]["logical_path"].startswith("shared/records/")
    assert record_entries[0]["shared"] is True


def test_nested_json_refs_are_rewritten_and_closure_remains_replayable() -> None:
    source = InMemoryArtifactStore()
    child_raw = b"record bytes"
    child_ref = _raw_ref("records-source", child_raw, "application/octet-stream")
    closure_raw = canonicalize_json_value({"records_ref": artifact_ref_to_dict(child_ref)})
    closure_ref = _raw_ref("closure-source", closure_raw)
    source.put(child_raw, child_ref)
    source.put(closure_raw, closure_ref)
    surface_result = _surface_result(root_ref=closure_ref)
    pair_closure = BundleArtifactClosure(
        (
            BundleArtifactBinding(
                child_ref,
                "pairs/pair/comparison/records/rows.bin",
                BundleArtifactKind.RECORDS,
                pair_id="pair",
            ),
            BundleArtifactBinding(
                closure_ref,
                "pairs/pair/comparison/records/closure.json",
                BundleArtifactKind.RECORDS_CLOSURE,
                pair_id="pair",
            ),
        )
    )
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, surface_result, pair_closure),)),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    assert surface_result.surface is not None
    assert result.bundle.pairs[0].surface_digest == surface_result.surface.surface_digest
    closure_document = json.loads(source.locate(result.bundle.artifact_closure_ref))
    rewritten_closure = next(
        item
        for item in closure_document["closure_entries"]
        if item["kind"] == BundleArtifactKind.RECORDS_CLOSURE
    )
    rewritten_raw = source.locate(
        artifact_ref_from_dict(rewritten_closure["artifact_ref"])
    )
    assert b"records-source" not in rewritten_raw
    validate_bundle(result.bundle, source)


def test_missing_nested_ref_diagnostic_identifies_parent_bundle_path() -> None:
    source = InMemoryArtifactStore()
    child_ref = _raw_ref("missing-child", b"child", "application/octet-stream")
    parent_raw = canonicalize_json_value({"records_ref": artifact_ref_to_dict(child_ref)})
    parent_ref = _raw_ref("parent-with-missing-child", parent_raw)
    source.put(parent_raw, parent_ref)
    surface_result = _surface_result(root_ref=parent_ref)
    parent_path = "pairs/pair/diagnostics/surface.json"
    result = assemble_bundle(
        _request(
            (
                BundlePairInput(
                    "pair",
                    0,
                    1,
                    surface_result,
                    BundleArtifactClosure(
                        (
                            BundleArtifactBinding(
                                parent_ref,
                                parent_path,
                                BundleArtifactKind.DIAGNOSTICS,
                                pair_id="pair",
                            ),
                        )
                    ),
                ),
            )
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.diagnostics == (
        f"EMBEDDED_ARTIFACT_REF_MISSING_FROM_CLOSURE:{parent_path}",
    )


def test_missing_closure_ref_fails_closed_without_bundle() -> None:
    missing_ref = _raw_ref("missing", b"missing")
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result(root_ref=missing_ref)),)),
        source_store=InMemoryArtifactStore(),
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.bundle is None
    assert result.manifest_ref is None


def test_tampered_source_artifact_fails_closed() -> None:
    raw = b"diagnostics"
    ref = _raw_ref("tampered-source", raw, "application/octet-stream")
    source = _TamperStore(ref.artifact_id)
    source.put(raw, ref)
    result = assemble_bundle(
        _request(
            (
                BundlePairInput(
                    "pair",
                    0,
                    1,
                    _surface_result(root_ref=ref),
                    BundleArtifactClosure(
                        (
                            BundleArtifactBinding(
                                ref,
                                "pairs/pair/diagnostics/diagnostics.bin",
                                BundleArtifactKind.DIAGNOSTICS,
                                pair_id="pair",
                            ),
                        )
                    ),
                ),
            )
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.bundle is None


def test_placeholder_risk_annotation_artifacts_fail_before_bundle_publication() -> None:
    source = InMemoryArtifactStore()
    placeholder = canonicalize_json_value({})
    annotation_ref = _raw_ref("risk-annotation", placeholder, ANNOTATION_MEDIA_TYPE)
    manifest_ref = _raw_ref(
        "risk-annotation-manifest",
        placeholder,
        ANNOTATION_MANIFEST_MEDIA_TYPE,
    )
    source.put(placeholder, annotation_ref)
    source.put(placeholder, manifest_ref)
    surface_result = _surface_result()
    assert surface_result.surface is not None
    table = surface_result.surface.tables[0]
    surface = replace(
        surface_result.surface,
        tables=(
            replace(
                table,
                risk_refs=SurfaceRiskRefs(
                    risk_level=RiskLevel.UNKNOWN,
                    reason_codes=(RiskReasonCode.KEY_DEGRADED,),
                    annotation_count=1,
                    annotation_ref=annotation_ref,
                    annotation_manifest_ref=manifest_ref,
                ),
            ),
        ),
    )
    surface = replace(surface, surface_digest=compute_surface_digest(surface))
    pair_closure = BundleArtifactClosure(
        (
            BundleArtifactBinding(
                annotation_ref,
                "pairs/pair/risk/annotations/orders.json",
                BundleArtifactKind.RISK_ANNOTATION,
                pair_id="pair",
                table_name="orders",
            ),
            BundleArtifactBinding(
                manifest_ref,
                "pairs/pair/risk/annotations/orders.manifest.json",
                BundleArtifactKind.RISK_ANNOTATION_MANIFEST,
                pair_id="pair",
                table_name="orders",
            ),
        )
    )

    result = assemble_bundle(
        _request(
            (
                BundlePairInput(
                    "pair",
                    0,
                    1,
                    SurfaceAssemblyResult(
                        status=SurfaceAssemblyStatus.READY,
                        surface=surface,
                    ),
                    pair_closure,
                ),
            )
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.bundle is None
    assert result.manifest_ref is None


def test_destination_failure_never_returns_public_bundle() -> None:
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result()),)),
        source_store=InMemoryArtifactStore(),
        destination_store=_FailingDestinationStore(fail_after=1),
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.bundle is None
    assert result.manifest_ref is None
    assert result.artifact_closure_ref is None


def test_required_failed_surface_fails_and_optional_failed_surface_degrades() -> None:
    failed = SurfaceAssemblyResult(status=SurfaceAssemblyStatus.FAILED, diagnostics=("SURFACE_FAILED",))
    required = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, failed),)),
        source_store=InMemoryArtifactStore(),
    )
    assert required.status is BundleAssemblyStatus.FAILED
    assert required.bundle is None

    optional = assemble_bundle(
        _request(
            (
                BundlePairInput("good", 0, 1, _surface_result()),
                BundlePairInput("optional", 1, 2, failed, required=False),
            ),
            profile=BundleProfile.MULTI_PAIR,
            inputs=(BundleInput(0, "a", "A"), BundleInput(1, "b", "B"), BundleInput(2, "c", "C")),
        ),
        source_store=InMemoryArtifactStore(),
    )
    assert optional.status is BundleAssemblyStatus.DEGRADED
    assert optional.bundle is not None
    assert optional.bundle.failed_pairs[0].pair_id == "optional"


def test_cancelled_input_and_context_never_publish_bundle() -> None:
    cancelled_surface = SurfaceAssemblyResult(
        status=SurfaceAssemblyStatus.CANCELLED,
        diagnostics=("SURFACE_CANCELLED",),
    )
    input_cancelled = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, cancelled_surface),)),
        source_store=InMemoryArtifactStore(),
    )
    context_cancelled = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result()),)),
        source_store=InMemoryArtifactStore(),
        context=BundleAssemblyContext(cancel_requested=lambda: True),
    )

    assert input_cancelled.status is BundleAssemblyStatus.CANCELLED
    assert input_cancelled.bundle is None
    assert context_cancelled.status is BundleAssemblyStatus.CANCELLED
    assert context_cancelled.bundle is None


def test_manifest_and_closure_caps_fail_before_publication() -> None:
    destination = InMemoryArtifactStore()
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result()),)),
        source_store=InMemoryArtifactStore(),
        destination_store=destination,
        policy=BundleAssemblyPolicy(max_bundle_manifest_json_bytes=1),
    )

    assert result.status is BundleAssemblyStatus.FAILED
    assert result.bundle is None
    assert destination._artifacts == {}


def test_surface_ref_rewrite_preserves_digest_when_artifact_bytes_are_unchanged() -> None:
    raw = b"diagnostics"
    ref = _raw_ref("diagnostics-source", raw, "application/octet-stream")
    source = InMemoryArtifactStore()
    source.put(raw, ref)
    surface_result = _surface_result(root_ref=ref)
    result = assemble_bundle(
        _request(
            (
                BundlePairInput(
                    "pair",
                    0,
                    1,
                    surface_result,
                    BundleArtifactClosure(
                        (
                            BundleArtifactBinding(
                                ref,
                                "pairs/pair/diagnostics/diagnostics.bin",
                                BundleArtifactKind.DIAGNOSTICS,
                                pair_id="pair",
                            ),
                        )
                    ),
                ),
            )
        ),
        source_store=source,
    )

    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None
    assert surface_result.surface is not None
    assert result.bundle.pairs[0].surface_digest == surface_result.surface.surface_digest


def test_recovery_rejects_manifest_and_closure_semantic_metadata_tampering() -> None:
    source = InMemoryArtifactStore()
    result = assemble_bundle(
        _request((BundlePairInput("pair", 0, 1, _surface_result()),)),
        source_store=source,
    )
    assert result.status is BundleAssemblyStatus.READY
    assert result.bundle is not None

    manifest_ref = result.bundle.manifest_ref
    closure_ref = result.bundle.artifact_closure_ref
    assert manifest_ref is not None
    assert closure_ref is not None
    manifest = json.loads(source.locate(manifest_ref))
    manifest["inputs"][0]["display_name"] = "tampered"
    tampered_manifest = canonicalize_json_value(manifest)
    tampered_manifest_ref = _raw_ref("tampered-manifest", tampered_manifest, manifest_ref.media_type)
    source.put(tampered_manifest, tampered_manifest_ref)
    with pytest.raises(ValueError, match="MANIFEST_SEMANTIC_PAYLOAD_MISMATCH"):
        validate_bundle(replace(result.bundle, manifest_ref=tampered_manifest_ref), source)

    manifest["unexpected"] = True
    unknown_manifest = canonicalize_json_value(manifest)
    unknown_manifest_ref = _raw_ref("unknown-manifest", unknown_manifest, manifest_ref.media_type)
    source.put(unknown_manifest, unknown_manifest_ref)
    with pytest.raises(ValueError, match="MANIFEST_FIELDS_INVALID"):
        validate_bundle(replace(result.bundle, manifest_ref=unknown_manifest_ref), source)

    closure = json.loads(source.locate(closure_ref))
    closure["bundle_manifest_digest"] = "sha256:" + "00" * 32
    tampered_closure = canonicalize_json_value(closure)
    tampered_closure_ref = _raw_ref("tampered-closure", tampered_closure, closure_ref.media_type)
    source.put(tampered_closure, tampered_closure_ref)
    with pytest.raises(ValueError, match="CLOSURE_MANIFEST_DIGEST_MISMATCH"):
        validate_bundle(replace(result.bundle, artifact_closure_ref=tampered_closure_ref), source)

    closure["unexpected"] = True
    unknown_closure = canonicalize_json_value(closure)
    unknown_closure_ref = _raw_ref("unknown-closure", unknown_closure, closure_ref.media_type)
    source.put(unknown_closure, unknown_closure_ref)
    with pytest.raises(ValueError, match="CLOSURE_FIELDS_INVALID"):
        validate_bundle(replace(result.bundle, artifact_closure_ref=unknown_closure_ref), source)

    closure = json.loads(source.locate(closure_ref))
    closure["closure_entries"][0]["unexpected"] = True
    unknown_entry_closure = canonicalize_json_value(closure)
    unknown_entry_closure_ref = _raw_ref(
        "unknown-closure-entry", unknown_entry_closure, closure_ref.media_type
    )
    source.put(unknown_entry_closure, unknown_entry_closure_ref)
    with pytest.raises(ValueError, match="CLOSURE_ENTRY_INVALID"):
        validate_bundle(replace(result.bundle, artifact_closure_ref=unknown_entry_closure_ref), source)

    closure = json.loads(source.locate(closure_ref))
    closure["entries"][0]["logical_path"] = "pairs/pair/tampered.json"
    tampered_semantic_closure = canonicalize_json_value(closure)
    tampered_semantic_closure_ref = _raw_ref(
        "tampered-semantic-closure",
        tampered_semantic_closure,
        closure_ref.media_type,
    )
    source.put(tampered_semantic_closure, tampered_semantic_closure_ref)
    with pytest.raises(ValueError, match="CLOSURE_SEMANTIC_PAYLOAD_MISMATCH"):
        validate_bundle(
            replace(result.bundle, artifact_closure_ref=tampered_semantic_closure_ref),
            source,
        )
