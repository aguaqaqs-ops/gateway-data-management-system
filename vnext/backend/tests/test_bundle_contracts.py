"""ComparisonBundle v3 public contract tests."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import ArtifactRef
from gateway_backend.capabilities.bundle_assembly import (
    BUNDLE_CONTRACT_VERSION,
    BundleArtifactBinding,
    BundleArtifactClosure,
    BundleArtifactKind,
    BundleAssemblyInput,
    BundleAssemblyResult,
    BundleAssemblyStatus,
    BundleInput,
    BundlePairInput,
    BundleProfile,
    BundleTableBinding,
    BundleTableSide,
    validate_logical_path,
)
from gateway_backend.capabilities.surface_assembly import SurfaceAssemblyResult, SurfaceAssemblyStatus

pytestmark = pytest.mark.unit


def _ref(name: str) -> ArtifactRef:
    raw = name.encode()
    return ArtifactRef(name, "application/json", len(raw), raw_blob_digest(raw))


def test_bundle_contract_normalizes_input_and_pair_order() -> None:
    failed_surface = SurfaceAssemblyResult(
        status=SurfaceAssemblyStatus.FAILED,
        diagnostics=("FAILED",),
    )
    request = BundleAssemblyInput(
        bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        bundle_profile=BundleProfile.MULTI_PAIR,
        inputs=(BundleInput(1, "current", "Current"), BundleInput(0, "before", "Before")),
        pairs=(
            BundlePairInput("z_pair", 0, 1, failed_surface, required=False),
            BundlePairInput("a_pair", 0, 1, failed_surface, required=False),
        ),
    )

    assert tuple(item.input_index for item in request.inputs) == (0, 1)
    assert tuple(item.pair_id for item in request.pairs) == ("a_pair", "z_pair")


@pytest.mark.parametrize(
    "path",
    (
        "/tmp/bundle.json",
        "../bundle.json",
        "pairs/../bundle.json",
        "pairs\\bundle.json",
        "cache/local.json",
        "repository/internal.json",
        "flow/state.json",
        "https://example.invalid/bundle.json",
    ),
)
def test_logical_path_rejects_host_cache_repository_and_flow_identity(path: str) -> None:
    with pytest.raises(ValueError):
        validate_logical_path(path)


def test_closure_rejects_duplicate_source_ref_and_path() -> None:
    ref = _ref("same")
    first = BundleArtifactBinding(
        source_ref=ref,
        logical_path="pairs/pair/a.json",
        kind=BundleArtifactKind.OTHER,
        pair_id="pair",
    )
    second = BundleArtifactBinding(
        source_ref=ref,
        logical_path="pairs/pair/b.json",
        kind=BundleArtifactKind.OTHER,
        pair_id="pair",
    )

    with pytest.raises(ValueError, match="source refs"):
        BundleArtifactClosure(entries=(first, second))


def test_snapshot_closure_keeps_all_table_side_bindings_for_shared_source() -> None:
    raw = b"parquet rows"
    ref = ArtifactRef(
        "same-snapshot-table",
        "application/vnd.apache.parquet",
        len(raw),
        raw_blob_digest(raw),
    )
    before = BundleArtifactBinding(
        source_ref=ref,
        logical_path="pairs/pair/tables/before/items/rows/000000.parquet",
        kind=BundleArtifactKind.SNAPSHOT_TABLE,
        pair_id="pair",
        table_name="items",
    )
    current = BundleArtifactBinding(
        source_ref=ref,
        logical_path="pairs/pair/tables/current/items/rows/000000.parquet",
        kind=BundleArtifactKind.SNAPSHOT_TABLE,
        pair_id="pair",
        table_name="items",
    )

    closure = BundleArtifactClosure(entries=(before, current))

    assert tuple(item.table_bindings for item in closure.entries) == (
        (BundleTableBinding("pair", "items", BundleTableSide.BEFORE),),
        (BundleTableBinding("pair", "items", BundleTableSide.CURRENT),),
    )


def test_failed_result_cannot_publish_bundle_refs() -> None:
    with pytest.raises(ValueError, match="must not publish"):
        BundleAssemblyResult(
            status=BundleAssemblyStatus.FAILED,
            manifest_ref=_ref("manifest"),
        )


def test_bundle_contract_version_is_v3() -> None:
    assert BUNDLE_CONTRACT_VERSION == "backend-vnext/comparison-bundle/v3"
    assert isinstance(DigestRef("sha256:" + "00" * 32), DigestRef)
