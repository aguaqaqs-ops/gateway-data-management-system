"""Acceptance lookup follows real assembler refs, sharing and table bindings."""

from __future__ import annotations

from dataclasses import replace
import io
import json
from pathlib import Path
import tarfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from gateway_shared_kernel import raw_blob_digest

from benchmarks import comparison_correctness_acceptance as acceptance
from benchmarks.real_dump_journey import JourneyFailure
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.bundle_assembly import (
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleTableSide,
    assemble_bundle,
    read_bundle_transport_metadata,
)
from gateway_backend.capabilities.surface_assembly import compute_surface_digest
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceRecordsFormat
from tests.support.comparison_s3_e_live import native_product, publish_product
from tests.support.surface_navigation import NAVIGATION_BYTES, seed_navigation
from tests.test_bundle_assembly import _request, _surface_result
from tests.test_surface_assembly import _content_binding

pytestmark = pytest.mark.unit
SELECTOR_FAULTS = (
    "missing",
    "ambiguous",
    "ref-id",
    "ref-media",
    "ref-size",
    "ref-digest",
    "kind",
    "pair",
    "side",
    "table",
)
PAYLOAD_FAULTS = ("missing", "duplicate", "directory", "size", "digest")


def _ref(name: str, raw: bytes) -> ArtifactRef:
    return ArtifactRef(
        build_artifact_id(ArtifactLocation.EXPORT, "acceptance-transport", name),
        "application/vnd.apache.parquet",
        len(raw),
        raw_blob_digest(raw),
    )


def _bundle(tmp_path: Path, *, shared: bool) -> tuple[Path, dict[str, Any]]:
    sink = io.BytesIO()
    pq.write_table(pa.table({"value": [10, 20, 30]}), sink)
    raw = sink.getvalue()
    store = seed_navigation(InMemoryArtifactStore())
    schema = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8));"
    product = native_product(
        schema + " INSERT INTO t VALUES(1,'before');",
        schema + " INSERT INTO t VALUES(1,'current');",
    )
    try:
        published = publish_product(product, store)
        assert published.records_closure is not None
        (record_entry,) = published.records_closure.records
    finally:
        product.close()
    records = record_entry.records_ref
    records_manifest = record_entry.records_manifest_ref
    pairs = []
    for index, pair in enumerate(("first", "second") if shared else ("first",)):
        # Different source IDs with identical snapshot bytes exercise the
        # assembler's content-sharing rewrite, not only duplicate ref sharing.
        snapshot = _ref("snapshot-" + str(index), raw)
        store.put(raw, snapshot)
        result = _surface_result(table_name="t")
        assert result.surface is not None
        table = result.surface.tables[0]
        table = replace(
            table,
            table_refs=replace(table.table_refs, current_table_ref=snapshot),
            table_content_bindings=replace(
                table.table_content_bindings, current=_content_binding("three-row-snapshot")
            ),
            records_refs=replace(
                table.records_refs,
                records_ref=records,
                records_manifest_ref=records_manifest,
                records_format=SurfaceRecordsFormat.PARQUET,
            ),
        )
        surface = replace(result.surface, tables=(table,))
        surface = replace(surface, surface_digest=compute_surface_digest(surface))
        result = replace(result, surface=surface)
        closure = BundleArtifactClosure(
            (
                BundleArtifactBinding(
                    snapshot,
                    f"pairs/{pair}/tables/current/t.parquet",
                    BundleArtifactKind.SNAPSHOT_TABLE,
                    pair_id=pair,
                    table_name="t",
                ),
                BundleArtifactBinding(
                    records,
                    f"pairs/{pair}/comparison/records/t/rows.bin",
                    BundleArtifactKind.RECORDS,
                    pair_id=pair,
                    table_name="t",
                ),
                BundleArtifactBinding(
                    records_manifest,
                    f"pairs/{pair}/comparison/records/t/manifest.json",
                    BundleArtifactKind.RECORDS_MANIFEST,
                    pair_id=pair,
                    table_name="t",
                ),
            )
        )
        pairs.append(BundlePairInput(pair, index, index + 1, result, closure))
    request = _request(
        tuple(pairs),
        profile=BundleProfile.MULTI_PAIR if shared else BundleProfile.SINGLE_PAIR,
        inputs=tuple(
            BundleInput(i, role, role)
            for i, role in enumerate(("left", "middle", "right") if shared else ("left", "right"))
        ),
    )
    bundle_result = assemble_bundle(request, source_store=store)
    assert bundle_result.status is BundleAssemblyStatus.READY and bundle_result.bundle is not None
    manifest_raw = store.locate(bundle_result.bundle.manifest_ref)
    metadata = read_bundle_transport_metadata(manifest_raw)
    path = tmp_path / "bundle.tar"
    with tarfile.open(path, "w") as archive:
        for name, payload in (
            ("manifest.json", manifest_raw),
            ("artifact-closure.json", metadata.expected_closure_bytes),
            *((entry.logical_path, store.locate(entry.artifact_ref)) for entry in metadata.entries),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return path, json.loads(manifest_raw)


@pytest.mark.parametrize("shared", (False, True))
def test_acceptance_reads_real_assembler_snapshot_records_and_navigation(
    tmp_path: Path, shared: bool
) -> None:
    path, manifest = _bundle(tmp_path, shared=shared)
    metadata = read_bundle_transport_metadata(acceptance._member(path, "manifest.json"))
    for pair, surface in acceptance._surfaces(path, manifest).items():
        table = surface.tables[0]
        assert acceptance._browse_count(path, pair, table) == 3
        for kind, ref in (
            (BundleArtifactKind.SNAPSHOT_TABLE, table.table_refs["current_table_ref"]),
            (BundleArtifactKind.RECORDS, table.records_refs["records_ref"]),
        ):
            entry = acceptance._payload_entry(
                metadata,
                acceptance._ArtifactReference.model_validate(ref).to_ref(),
                kind,
                pair,
                table="t",
                side=BundleTableSide.CURRENT if kind is BundleArtifactKind.SNAPSHOT_TABLE else None,
            )
            assert entry.shared is shared
            assert entry.logical_path.startswith("shared/" if shared else f"pairs/{pair}/")
            with acceptance._payload_file(
                path,
                ref,
                kind,
                pair,
                table="t",
                side=BundleTableSide.CURRENT if kind is BundleArtifactKind.SNAPSHOT_TABLE else None,
            ) as payload:
                rows = pq.read_table(payload)
                if kind is BundleArtifactKind.SNAPSHOT_TABLE:
                    assert rows.column("value").to_pylist() == [10, 20, 30]
                else:
                    assert rows.column("table_name").to_pylist() == ["t"]
                    assert rows.column("record_kind").to_pylist() == ["ROW_MODIFIED"]
        assert acceptance._navigation(path, pair, surface) == json.loads(NAVIGATION_BYTES)
        navigation_ref = surface.projections[0]["projection_ref"]
        navigation_entry = acceptance._payload_entry(
            metadata,
            acceptance._ArtifactReference.model_validate(navigation_ref).to_ref(),
            BundleArtifactKind.PROJECTION,
            pair,
        )
        assert navigation_entry.shared is shared


@pytest.mark.parametrize("fault", SELECTOR_FAULTS)
def test_acceptance_rejects_wrong_or_ambiguous_snapshot_selector(
    tmp_path: Path, fault: str
) -> None:
    path, manifest = _bundle(tmp_path, shared=True)
    surface = acceptance._surfaces(path, manifest)["first"]
    ref = acceptance._ArtifactReference.model_validate(
        surface.tables[0].table_refs["current_table_ref"]
    ).to_ref()
    metadata = read_bundle_transport_metadata(acceptance._member(path, "manifest.json"))
    entry = next(entry for entry in metadata.entries if entry.artifact_ref == ref)
    pair, table, side, kind = (
        "first",
        "t",
        BundleTableSide.CURRENT,
        BundleArtifactKind.SNAPSHOT_TABLE,
    )
    if fault == "missing":
        metadata = replace(
            metadata, entries=tuple(item for item in metadata.entries if item != entry)
        )
    elif fault == "ambiguous":
        metadata = replace(
            metadata, entries=(*metadata.entries, replace(entry, logical_path="other.parquet"))
        )
    elif fault == "ref-id":
        ref = replace(
            ref,
            artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "acceptance-transport", "wrong"),
        )
    elif fault == "ref-media":
        ref = replace(ref, media_type="application/octet-stream")
    elif fault == "ref-size":
        ref = replace(ref, size_bytes=ref.size_bytes + 1)
    elif fault == "ref-digest":
        ref = replace(ref, raw_sha256=raw_blob_digest(b"wrong"))
    elif fault == "kind":
        kind = BundleArtifactKind.RECORDS
    elif fault == "pair":
        pair = "absent"
    elif fault == "side":
        side = BundleTableSide.BEFORE
    else:
        table = "other"
    with pytest.raises(JourneyFailure, match="missing or ambiguous|binding mismatch"):
        acceptance._payload_entry(metadata, ref, kind, pair, table=table, side=side)


@pytest.mark.parametrize("fault", ("pair", "table", "ref-id"))
def test_acceptance_records_selector_keeps_surface_table_identity(
    tmp_path: Path, fault: str
) -> None:
    path, manifest = _bundle(tmp_path, shared=False)
    table = acceptance._surfaces(path, manifest)["first"].tables[0]
    ref = acceptance._ArtifactReference.model_validate(table.records_refs["records_ref"]).to_ref()
    metadata = read_bundle_transport_metadata(acceptance._member(path, "manifest.json"))
    if fault == "ref-id":
        ref = replace(
            ref,
            artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "acceptance-transport", "wrong"),
        )
    with pytest.raises(JourneyFailure, match="missing or ambiguous|binding mismatch"):
        acceptance._payload_entry(
            metadata,
            ref,
            BundleArtifactKind.RECORDS,
            "other" if fault == "pair" else "first",
            table="other" if fault == "table" else "t",
        )


@pytest.mark.parametrize("fault", PAYLOAD_FAULTS)
def test_acceptance_rejects_missing_ambiguous_and_corrupt_tar_payload(
    tmp_path: Path, fault: str
) -> None:
    path, manifest = _bundle(tmp_path, shared=True)
    table = acceptance._surfaces(path, manifest)["first"].tables[0]
    ref = acceptance._ArtifactReference.model_validate(
        table.table_refs["current_table_ref"]
    ).to_ref()
    metadata = read_bundle_transport_metadata(acceptance._member(path, "manifest.json"))
    target = acceptance._payload_entry(
        metadata,
        ref,
        BundleArtifactKind.SNAPSHOT_TABLE,
        "first",
        table="t",
        side=BundleTableSide.CURRENT,
    ).logical_path
    damaged = tmp_path / "damaged.tar"
    with tarfile.open(path, "r:") as source, tarfile.open(damaged, "w") as destination:
        for member in source:
            stream = source.extractfile(member)
            assert stream is not None
            raw = stream.read()
            if member.name == target:
                if fault == "missing":
                    continue
                if fault == "directory":
                    member.type, member.size, raw = tarfile.DIRTYPE, 0, b""
                elif fault == "size":
                    raw += b"x"
                    member.size += 1
                elif fault == "digest":
                    raw = bytes([raw[0] ^ 1]) + raw[1:]
            destination.addfile(member, io.BytesIO(raw))
            if member.name == target and fault == "duplicate":
                destination.addfile(member, io.BytesIO(raw))
    with pytest.raises(JourneyFailure, match="payload member"):
        acceptance._browse_count(damaged, "first", table)


@pytest.mark.parametrize("fault", ("missing", "ambiguous"))
def test_acceptance_rejects_missing_or_ambiguous_navigation_projection(
    tmp_path: Path, fault: str
) -> None:
    path, manifest = _bundle(tmp_path, shared=True)
    surface = acceptance._surfaces(path, manifest)["first"]
    projections = [] if fault == "missing" else [*surface.projections, surface.projections[0]]
    surface = surface.model_copy(update={"projections": projections})
    with pytest.raises(JourneyFailure, match="navigation projection is missing or ambiguous"):
        acceptance._navigation(path, "first", surface)
