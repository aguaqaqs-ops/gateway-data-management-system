"""Architecture boundary tests."""

from pathlib import Path


def test_vnext_source_does_not_import_legacy_code() -> None:
    source_root = Path(__file__).parents[1] / "src"
    forbidden = ("import legacy", "from legacy", "import backend_vnext", "from backend_vnext")

    for source in source_root.rglob("*.py"):
        assert not any(marker in source.read_text() for marker in forbidden), source


def test_artifacts_module_does_not_import_gateway_compute() -> None:
    artifacts_root = Path(__file__).parents[1] / "src" / "gateway_backend" / "artifacts"
    for source in artifacts_root.rglob("*.py"):
        text = source.read_text()
        assert "gateway_compute" not in text, source
        assert "canonical_row_hash_artifact" not in text, source
        assert "gateway_shared_kernel.testing" not in text, source
        assert "LocalArtifactStore" not in text, source


def test_local_artifact_store_lives_in_infrastructure_only() -> None:
    artifacts_root = Path(__file__).parents[1] / "src" / "gateway_backend" / "artifacts"
    infrastructure_root = Path(__file__).parents[1] / "src" / "gateway_backend" / "infrastructure"
    assert not any(artifacts_root.rglob("local_store.py"))
    assert list(infrastructure_root.rglob("local_store.py"))
    local_store_source = (infrastructure_root / "artifact_store" / "local_store.py").read_text()
    assert "class LocalArtifactStore" in local_store_source


def test_compute_facade_does_not_reference_artifact_identity() -> None:
    compute_source = Path(__file__).parents[1] / "src" / "gateway_backend" / "compute.py"
    text = compute_source.read_text()
    forbidden = ("ArtifactRef", "artifact_ref", "logical_ref", "ArtifactStore", "artifact_root")
    assert not any(marker in text for marker in forbidden), compute_source


def test_compute_python_extension_has_no_artifact_ref_types() -> None:
    compute_python_root = Path(__file__).resolve().parents[2] / "rust" / "gateway-compute-python"
    forbidden = ("ArtifactRef", "artifact_ref", "logical_ref", "artifact_root")
    for source in list(compute_python_root.rglob("*.py")) + list(compute_python_root.rglob("*.rs")):
        text = source.read_text()
        assert not any(marker in text for marker in forbidden), source


def test_rust_core_has_no_artifact_or_infrastructure_boundary() -> None:
    rust_root = Path(__file__).resolve().parents[2] / "rust"
    forbidden = (
        "ArtifactRef",
        "ArtifactManifest",
        "logical_ref",
        "retention_class",
        "artifact_root",
        "object_store",
        "std::fs",
        "std::path",
        "std::env",
    )
    for crate_name in ("gateway-compute-core", "gateway-compute-python"):
        for source in (rust_root / crate_name / "src").rglob("*.rs"):
            text = source.read_text()
            assert not any(marker in text for marker in forbidden), source


def test_r2_ipc_module_avoids_bulk_python_materialization() -> None:
    ipc_source = Path(__file__).parents[1] / "src" / "gateway_backend" / "canonical_row_hash_ipc.py"
    text = ipc_source.read_text()
    forbidden = (
        "to_pylist(",
        "to_pydict(",
        ".as_py()",
        "_row_hashes_from_batch",
        "combine_chunks(",
    )
    assert not any(marker in text for marker in forbidden), ipc_source
    assert "unordered_row_hashes_content_digest_from_sorted_row_buffer" in text
    assert "unordered_row_hashes_content_digest_from_row_buffer" not in text
    assert "_collect_row_hash_buffer_from_ipc" in text


def test_r2_production_modules_have_no_deferred_stub() -> None:
    source_root = Path(__file__).parents[1] / "src" / "gateway_backend"
    for source in source_root.rglob("*.py"):
        text = source.read_text()
        assert "NotImplementedError" not in text, source
