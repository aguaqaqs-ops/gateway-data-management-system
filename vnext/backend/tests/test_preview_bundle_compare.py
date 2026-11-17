"""Boundaries of the conservative Preview bundle comparator."""

from __future__ import annotations

from pathlib import Path
import io

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from gateway_backend.application.bundle_download import prepare_bundle_download
from tests.test_bundle_download import published_bundle
from benchmarks.preview_bundle_compare import _map_value, _parquet_equal, _role, compare
from gateway_backend.artifacts import ArtifactRef
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.bundle_assembly.contracts import (
    BundleArtifactKind,
    BundleClosureEntry,
    BundleTableBinding,
    BundleTableSide,
)
from gateway_shared_kernel import raw_blob_digest


def test_scope_mapping_retains_business_pair_and_digest_fields() -> None:
    document = {
        "pair_id": "initial_to_modified",
        "risk_digest": "sha256:business",
        "ref": {
            "artifact_id": "runtime-a",
            "media_type": "application/json",
            "size_bytes": 1,
            "raw_sha256": "sha256:raw",
        },
    }
    mapped = _map_value(document, refs={"runtime-a": "surface-role"}, paths={})
    assert mapped["ref"]["artifact_id"] == {"bundle_role": "surface-role"}
    assert mapped["pair_id"] == "initial_to_modified"
    assert mapped["risk_digest"] == "sha256:business"
    assert mapped["ref"]["raw_sha256"] == "sha256:raw"
    assert _map_value(
        {"artifact_id": "runtime-a", "risk": "runtime-a"}, refs={"runtime-a": "x"}, paths={}
    ) == {"artifact_id": "runtime-a", "risk": "runtime-a"}


def test_snapshot_role_keeps_pair_table_and_side_binding() -> None:
    ref = ArtifactRef(
        build_artifact_id(ArtifactLocation.EXPORT, "test", 1),
        "application/octet-stream",
        1,
        raw_blob_digest(b"x"),
    )

    def entry(side: BundleTableSide) -> BundleClosureEntry:
        return BundleClosureEntry(
            "shared/snapshot-tables/x.parquet",
            ref,
            BundleArtifactKind.SNAPSHOT_TABLE,
            1,
            ref.raw_sha256,
            shared=True,
            table_bindings=(BundleTableBinding("pair", "device", side),),
        )

    assert _role(entry(BundleTableSide.BEFORE)) != _role(entry(BundleTableSide.CURRENT))


def test_verified_bundle_compares_equal_to_itself(tmp_path: Path) -> None:
    store, manifest_ref = published_bundle(tmp_path / "source")
    prepared = prepare_bundle_download(store, manifest_ref.artifact_id)
    fixture = tmp_path / "bundle.tar"
    try:
        fixture.write_bytes(b"".join(prepared.stream))
    finally:
        prepared.close()
    result = compare(fixture, fixture, left_repository="repo1", right_repository="repo1")
    assert result["equal"] is True
    assert result["compared_roles"] > 0
    assert result["differences"] == []


def test_repository_footer_mapping_preserves_data_and_all_other_metadata() -> None:
    def payload(repository: str, value: int, extra: bytes = b"fixed") -> io.BytesIO:
        table = pa.table({"gid": [1, 2], "value": [value, 3]}).replace_schema_metadata(
            {b"gdds.client.repository_id": repository.encode(), b"other": extra}
        )
        output = io.BytesIO()
        pq.write_table(table, output)
        output.seek(0)
        return output

    assert _parquet_equal(payload("left", 2), payload("right", 2), "left", "right")
    assert not _parquet_equal(payload("left", 2), payload("right", 9), "left", "right")
    assert not _parquet_equal(payload("left", 2), payload("right", 2, b"changed"), "left", "right")
    assert not _parquet_equal(payload("left", 2), payload("wrong", 2), "left", "right")


def test_cross_repository_bundle_compares_rows_and_bindings(tmp_path: Path) -> None:
    from gateway_backend.artifacts import put_with_built_ref
    from gateway_backend.capabilities.bundle_assembly import (
        BundleArtifactBinding,
        BundleArtifactClosure,
        BundlePairInput,
        assemble_bundle,
    )
    from tests.support.artifact_layout import open_test_store
    from tests.support.surface_navigation import seed_navigation
    from tests.test_bundle_assembly import _request, _surface_result

    def bundle(name: str, repository: str, value: int, side: str = "current") -> Path:
        store = seed_navigation(open_test_store(tmp_path / name))
        table = pa.table({"gid": [1], "name": [value]}).replace_schema_metadata(
            {b"gdds.client.repository_id": repository.encode(), b"layout": b"same"}
        )
        buffer = io.BytesIO()
        pq.write_table(table, buffer)
        ref = put_with_built_ref(
            store,
            buffer.getvalue(),
            artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "scope-test", repository),
            media_type="application/vnd.apache.parquet",
        )
        binding = BundleArtifactBinding(
            ref,
            f"pairs/pair/tables/{side}/device.parquet",
            BundleArtifactKind.SNAPSHOT_TABLE,
            pair_id="pair",
            table_name="device",
        )
        result = assemble_bundle(
            _request(
                (
                    BundlePairInput(
                        "pair",
                        0,
                        1,
                        _surface_result(root_ref=ref),
                        BundleArtifactClosure((binding,)),
                    ),
                )
            ),
            source_store=store,
        )
        assert result.bundle is not None
        prepared = prepare_bundle_download(store, result.bundle.manifest_ref.artifact_id)
        target = tmp_path / f"{name}.tar"
        try:
            target.write_bytes(b"".join(prepared.stream))
        finally:
            prepared.close()
        return target

    left = bundle("left", "repo-left", 7)
    right = bundle("right", "repo-right", 7)
    changed = bundle("changed", "repo-right", 8)
    other_side = bundle("other-side", "repo-right", 7, "before")
    assert (
        compare(left, right, left_repository="repo-left", right_repository="repo-right")["equal"]
        is True
    )
    assert (
        compare(left, left, left_repository="repo-left", right_repository="repo-right")["equal"]
        is False
    )
    assert (
        compare(left, changed, left_repository="repo-left", right_repository="repo-right")["equal"]
        is False
    )
    assert (
        compare(left, other_side, left_repository="repo-left", right_repository="repo-right")[
            "equal"
        ]
        is False
    )


def test_risk_and_navigation_values_are_never_scope_masked() -> None:
    from benchmarks.preview_bundle_compare import _map_proven_refs

    original = {
        "risk": {"level": "HIGH", "reason_codes": ["R1"]},
        "navigation": {"group_key": "DEVICE", "items": [{"table_id": "device_st"}]},
    }
    changed_risk = {
        "risk": {"level": "LOW", "reason_codes": ["R1"]},
        "navigation": original["navigation"],
    }
    changed_navigation = {
        "risk": original["risk"],
        "navigation": {"group_key": "DEVICE", "items": [{"table_id": "device"}]},
    }
    assert _map_proven_refs(original, {}, set()) != _map_proven_refs(changed_risk, {}, set())
    assert _map_proven_refs(original, {}, set()) != _map_proven_refs(changed_navigation, {}, set())
