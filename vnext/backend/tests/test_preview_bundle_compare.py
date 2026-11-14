"""Boundaries of the conservative Preview bundle comparator."""
from __future__ import annotations

from pathlib import Path

from benchmarks.bundle_interop_fixture import generate
from benchmarks.preview_bundle_compare import _map_value, _role, compare
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.bundle_assembly.contracts import (
    BundleArtifactKind, BundleClosureEntry, BundleTableBinding, BundleTableSide,
)
from gateway_shared_kernel import raw_blob_digest


def test_scope_mapping_retains_business_pair_and_digest_fields() -> None:
    document = {"pair_id": "initial_to_modified", "risk_digest": "sha256:business",
        "ref": {"artifact_id": "runtime-a", "media_type": "application/json", "size_bytes": 1, "raw_sha256": "sha256:raw"}}
    mapped = _map_value(document, refs={"runtime-a": "surface-role"}, paths={})
    assert mapped["ref"]["artifact_id"] == {"bundle_role": "surface-role"}
    assert mapped["pair_id"] == "initial_to_modified"
    assert mapped["risk_digest"] == "sha256:business"
    assert mapped["ref"]["raw_sha256"] == "sha256:raw"
    assert _map_value({"artifact_id": "runtime-a", "risk": "runtime-a"}, refs={"runtime-a": "x"}, paths={}) == {
        "artifact_id": "runtime-a", "risk": "runtime-a"}


def test_snapshot_role_keeps_pair_table_and_side_binding() -> None:
    ref = ArtifactRef(build_artifact_id(ArtifactLocation.EXPORT, "test", 1), "application/octet-stream", 1, raw_blob_digest(b"x"))
    def entry(side: BundleTableSide) -> BundleClosureEntry:
        return BundleClosureEntry("shared/snapshot-tables/x.parquet", ref, BundleArtifactKind.SNAPSHOT_TABLE,
            1, ref.raw_sha256, shared=True, table_bindings=(BundleTableBinding("pair", "device", side),))
    assert _role(entry(BundleTableSide.BEFORE)) != _role(entry(BundleTableSide.CURRENT))


def test_verified_bundle_compares_equal_to_itself(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    generate(fixture)
    result = compare(fixture / "bundle.tar", fixture / "bundle.tar")
    assert result["equal"] is True
    assert result["compared_roles"] > 0
    assert result["differences"] == []
