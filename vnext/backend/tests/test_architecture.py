"""Architecture boundary tests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

BACKEND_SRC = Path(__file__).parents[1] / "src"
CAPABILITIES_ROOT = BACKEND_SRC / "gateway_backend" / "capabilities"
CAPABILITIES_PREFIX = "gateway_backend.capabilities."
OPERATIONS_ROOT = BACKEND_SRC / "gateway_backend" / "operations"
CONTROL_DB_ROOT = BACKEND_SRC / "gateway_backend" / "infrastructure" / "control_db"

OPERATIONS_FORBIDDEN_IMPORT_PREFIXES = (
    "sqlite3",
    "fastapi",
    "uvicorn",
    "httpx",
    "gateway_backend.app",
    "gateway_backend.settings",
    "gateway_backend.infrastructure",
    "gateway_backend.capabilities",
    "gateway_repository",
    "gateway_repository_client",
    "gateway_repository_contracts",
    "gateway_repository_service",
    "gateway_shared_kernel.testing",
)

CAPABILITY_OWNERS = frozenset(
    {
        "canonical_row_hash",
        "table_access",
        "table_rules",
        "source_package_staging",
        "composite_signal",
        "snapshot_materialization",
        "storage_projection",
        "comparison_projection",
        "comparison",
        "risk_evaluation",
        "business_projection",
        "surface_assembly",
        "bundle_assembly",
        "mutation_planning",
        "external_target_sync",
    }
)

ALLOWED_UPSTREAM_OWNERS: dict[str, frozenset[str]] = {
    "canonical_row_hash": frozenset(),
    "table_access": frozenset(),
    "table_rules": frozenset(),
    "source_package_staging": frozenset(),
    "composite_signal": frozenset({"table_access"}),
    "snapshot_materialization": frozenset(
        {"table_access", "table_rules", "source_package_staging", "composite_signal"}
    ),
    "storage_projection": frozenset({"table_rules", "snapshot_materialization"}),
    "comparison_projection": frozenset({"table_rules", "snapshot_materialization"}),
    "comparison": frozenset({"comparison_projection", "snapshot_materialization"}),
    "risk_evaluation": frozenset({"comparison"}),
    "business_projection": frozenset({"comparison"}),
    "surface_assembly": frozenset({"comparison", "risk_evaluation", "business_projection"}),
    "bundle_assembly": frozenset({"surface_assembly"}),
    "mutation_planning": frozenset({"storage_projection"}),
    "external_target_sync": frozenset({"mutation_planning"}),
}

FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "uvicorn",
    "httpx",
    "gateway_backend.app",
    "gateway_backend.settings",
    "gateway_backend.compute",
    "gateway_backend.canonical_row_hash_ipc",
    "gateway_backend.canonicalization_cells",
    "gateway_backend.canonicalization_manifest",
    "gateway_backend.repository_import_artifact",
    "gateway_backend.infrastructure",
    "gateway_backend.synthetic_w2",
    "gateway_repository",
    "gateway_repository_client",
    "gateway_repository_contracts",
    "gateway_repository_service",
    "gateway_shared_kernel.testing",
)

FORBIDDEN_IMPORT_PARTS = frozenset(
    {
        "_internal",
        "workspace",
        "submission",
        "operations",
        "dolt",
    }
)

FORBIDDEN_PROVIDER_BASE_NAMES = frozenset(
    {
        "BaseProvider",
        "GenericProvider",
        "ProviderBase",
    }
)


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
        assert "canonical_row_hash" not in text, source
        assert "gateway_backend.capabilities" not in text, source
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


def test_canonicalization_cells_do_not_call_encode_row() -> None:
    source = Path(__file__).parents[1] / "src" / "gateway_backend" / "canonicalization_cells.py"
    text = source.read_text()
    assert text.count("encode_row") == text.count("encode_row_cells")
    assert "from gateway_shared_kernel import" in text
    assert "encode_typed_scalar" in text
    assert "encode_collection" in text


def test_capability_packages_match_owner_set() -> None:
    owners = _capability_owner_dirs()
    assert owners == CAPABILITY_OWNERS
    assert not owners & {"common", "utils"}
    assert not (CAPABILITIES_ROOT / "common.py").exists()
    assert not (CAPABILITIES_ROOT / "utils.py").exists()
    for owner in sorted(CAPABILITY_OWNERS):
        owner_dir = CAPABILITIES_ROOT / owner
        assert (owner_dir / "__init__.py").is_file(), owner
        assert (owner_dir / "contracts.py").is_file(), owner
        assert not (owner_dir / "_internal").exists(), owner
        assert not (owner_dir / "common.py").exists(), owner
        assert not (owner_dir / "utils.py").exists(), owner


def test_canonical_row_hash_metadata_lives_in_owner_package() -> None:
    backend = BACKEND_SRC / "gateway_backend"
    assert not (backend / "canonical_row_hash_artifact.py").exists()
    assert (backend / "capabilities" / "canonical_row_hash" / "contracts.py").is_file()


def test_capability_modules_respect_import_dag() -> None:
    for source in sorted(CAPABILITIES_ROOT.rglob("*.py")):
        current_module, is_init = _python_module_name(source)
        current_owner = _owner_from_module(current_module)
        imported_modules = _imported_modules(source, current_module, is_init)
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for class_node in ast.walk(tree):
            if isinstance(class_node, ast.ClassDef):
                assert class_node.name not in FORBIDDEN_PROVIDER_BASE_NAMES, source
        for imported in imported_modules:
            _assert_capability_import_allowed(source, current_owner, imported)


def test_capability_contracts_are_importable() -> None:
    importlib.import_module("gateway_backend.capabilities")
    for owner in sorted(CAPABILITY_OWNERS):
        importlib.import_module(f"gateway_backend.capabilities.{owner}")
        importlib.import_module(f"gateway_backend.capabilities.{owner}.contracts")


_TABLE_ACCESS_FORBIDDEN_TOKENS = (
    "Snapshot",
    "gateway_repository",
    "host_path",
    "NotImplementedError",
    "lxml",
    "defusedxml",
)


def test_table_access_source_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "table_access"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _TABLE_ACCESS_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_SOURCE_PACKAGE_FORBIDDEN_TOKENS = (
    "Snapshot",
    "host_path",
    "NotImplementedError",
    "parse_sql",
    "lxml",
    "dolt",
)


def test_source_package_staging_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "source_package_staging"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _SOURCE_PACKAGE_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_COMPOSITE_SIGNAL_FORBIDDEN_TOKENS = (
    "Snapshot",
    "parse_xml",
    "parse_sql",
    "host_path",
    "NotImplementedError",
    "lxml",
    "dolt",
)


def test_composite_signal_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "composite_signal"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _COMPOSITE_SIGNAL_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_TABLE_RULES_FORBIDDEN_TOKENS = (
    "backend_vnext",
    "host_path",
    "fastapi",
    "dolt",
    "NotImplementedError",
    "gateway_repository",
)


def test_table_rules_source_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "table_rules"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _TABLE_RULES_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_STORAGE_PROJECTION_FORBIDDEN_TOKENS = (
    "dolt",
    "host_path",
    "fastapi",
    "legacy",
    "backend_vnext",
    "NotImplementedError",
    "gateway_repository",
)


def test_storage_projection_source_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "storage_projection"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _STORAGE_PROJECTION_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_MUTATION_PLANNING_FORBIDDEN_TOKENS = (
    "dolt",
    "host_path",
    "fastapi",
    "legacy",
    "backend_vnext",
    "NotImplementedError",
    "gateway_repository",
    "sql_text",
    "replay_sql",
)


def test_mutation_planning_source_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "mutation_planning"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _MUTATION_PLANNING_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


_EXTERNAL_TARGET_SYNC_FORBIDDEN_TOKENS = _MUTATION_PLANNING_FORBIDDEN_TOKENS


def test_external_target_sync_source_stays_on_capability_leaf() -> None:
    owner = CAPABILITIES_ROOT / "external_target_sync"
    for source in sorted(owner.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for token in _EXTERNAL_TARGET_SYNC_FORBIDDEN_TOKENS:
            assert token not in text, f"{source} contains forbidden token {token}"


def test_operations_package_is_sole_runtime_owner() -> None:
    backend_root = BACKEND_SRC / "gateway_backend"
    assert OPERATIONS_ROOT.is_dir()
    assert (OPERATIONS_ROOT / "__init__.py").is_file()
    assert (OPERATIONS_ROOT / "contracts.py").is_file()
    assert not (BACKEND_SRC / "backend_vnext").exists()
    operations_packages = [
        path
        for path in backend_root.rglob("operations")
        if path.is_dir() and (path / "__init__.py").is_file()
    ]
    assert operations_packages == [OPERATIONS_ROOT]


def test_operations_module_respects_import_boundary() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        current_module, is_init = _python_module_name(source)
        for imported in _imported_modules(source, current_module, is_init):
            _assert_operations_import_allowed(source, imported)


def test_operations_source_has_no_operation_kind() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        assert "operation_kind" not in source.read_text(encoding="utf-8"), source


def test_operations_source_has_no_deferred_stub() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        assert "NotImplementedError" not in source.read_text(encoding="utf-8"), source


def test_control_db_boundary_exists_and_has_no_application_wiring() -> None:
    assert CONTROL_DB_ROOT.is_dir()
    assert (CONTROL_DB_ROOT / "__init__.py").is_file()
    assert (CONTROL_DB_ROOT / "database.py").is_file()
    assert (CONTROL_DB_ROOT / "migrations.py").is_file()
    assert (CONTROL_DB_ROOT / "sqlite_operations.py").is_file()
    forbidden = (
        "gateway_backend.app",
        "gateway_backend.settings",
        "gateway_backend.capabilities",
        "gateway_backend.compute",
        "gateway_backend.repository_import_artifact",
        "gateway_repository",
        "uvicorn",
        "fastapi",
        "sqlalchemy",
        "alembic",
    )
    for source in sorted(CONTROL_DB_ROOT.rglob("*.py")):
        current_module, is_init = _python_module_name(source)
        for imported in _imported_modules(source, current_module, is_init):
            assert not any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for prefix in forbidden
            ), f"{source} imports forbidden module {imported}"
            if imported.startswith("gateway_backend."):
                assert (
                    imported.startswith("gateway_backend.operations")
                    or imported.startswith("gateway_backend.artifacts")
                    or imported.startswith("gateway_backend.infrastructure.control_db")
                ), f"{source} imports disallowed backend module {imported}"


def _capability_owner_dirs() -> set[str]:
    owners: set[str] = set()
    for path in CAPABILITIES_ROOT.iterdir():
        if path.name in {"__pycache__", "__init__.py"} or path.name.startswith("."):
            continue
        if path.is_dir():
            owners.add(path.name)
    return owners


def _python_module_name(source: Path) -> tuple[str, bool]:
    parts = list(source.relative_to(BACKEND_SRC).with_suffix("").parts)
    is_init = parts[-1] == "__init__"
    if is_init:
        parts = parts[:-1]
    return ".".join(parts), is_init


def _owner_from_module(module_name: str) -> str | None:
    if module_name == "gateway_backend.capabilities":
        return None
    if not module_name.startswith(CAPABILITIES_PREFIX):
        return None
    rest = module_name.removeprefix(CAPABILITIES_PREFIX)
    return rest.split(".", 1)[0]


def _imported_modules(source: Path, current_module: str, is_init: bool) -> list[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 0:
            if node.module is not None:
                imported.append(node.module)
            continue
        imported.extend(_resolve_relative_import(current_module, is_init, node))
    return imported


def _resolve_relative_import(
    current_module: str, is_init: bool, node: ast.ImportFrom
) -> list[str]:
    parts = current_module.split(".")
    if not is_init:
        parts = parts[:-1]
    drop = node.level - 1
    if drop > len(parts):
        raise AssertionError(f"relative import escapes package in {current_module}")
    if drop:
        parts = parts[:-drop]
    if node.module is None:
        return [".".join([*parts, alias.name]) for alias in node.names]
    return [".".join([*parts, *node.module.split(".")])]


def _assert_capability_import_allowed(
    source: Path, current_owner: str | None, imported: str
) -> None:
    if imported == "__future__":
        return
    for prefix in FORBIDDEN_IMPORT_PREFIXES:
        assert imported != prefix and not imported.startswith(f"{prefix}."), (
            f"{source} imports forbidden module {imported}"
        )
    for part in imported.split("."):
        assert part not in FORBIDDEN_IMPORT_PARTS, f"{source} imports {imported}"
    if imported == "gateway_backend.capabilities" or imported.startswith(CAPABILITIES_PREFIX):
        if (
            current_owner == "bundle_assembly"
            and imported == "gateway_backend.capabilities.surface_assembly"
        ):
            # Bundle may consume the Surface owner’s public entrypoints for ref rewrite and
            # digest re-sealing; it must still avoid Surface private modules and all other
            # capability owners.
            return
        _assert_capability_edge_allowed(source, current_owner, imported)
        return
    if imported == "gateway_backend.artifacts" or imported.startswith("gateway_backend.artifacts."):
        return
    if imported == "gateway_shared_kernel" or imported.startswith("gateway_shared_kernel."):
        return
    assert not imported.startswith("gateway_backend."), (
        f"{source} imports disallowed backend module {imported}"
    )


def _assert_capability_edge_allowed(
    source: Path, current_owner: str | None, imported: str
) -> None:
    if imported == "gateway_backend.capabilities":
        assert current_owner is None, f"{source} must not import the capabilities package root"
        return
    target_owner, remainder = _split_capability_import(imported)
    if current_owner is None:
        raise AssertionError(f"{source} must not import capability owner {target_owner}")
    if target_owner == current_owner:
        return
    allowed = ALLOWED_UPSTREAM_OWNERS[current_owner]
    assert target_owner in allowed, (
        f"{source} may not import capability {target_owner}; allowed upstream: {sorted(allowed)}"
    )
    assert remainder == "contracts" or remainder.startswith("contracts."), (
        f"{source} may import only {target_owner}.contracts, not {imported}"
    )


def _split_capability_import(imported: str) -> tuple[str, str]:
    rest = imported.removeprefix(CAPABILITIES_PREFIX)
    owner, separator, remainder = rest.partition(".")
    assert owner in CAPABILITY_OWNERS, f"unknown capability import {imported}"
    if not separator:
        return owner, ""
    return owner, remainder


def _assert_operations_import_allowed(source: Path, imported: str) -> None:
    if imported == "__future__":
        return
    for prefix in OPERATIONS_FORBIDDEN_IMPORT_PREFIXES:
        assert imported != prefix and not imported.startswith(f"{prefix}."), (
            f"{source} imports forbidden module {imported}"
        )
    for part in imported.split("."):
        assert part != "_internal", f"{source} imports {imported}"
    if imported == "gateway_backend.artifacts" or imported.startswith("gateway_backend.artifacts."):
        return
    if imported == "gateway_shared_kernel" or imported.startswith("gateway_shared_kernel."):
        assert not imported.startswith("gateway_shared_kernel.testing"), (
            f"{source} imports forbidden module {imported}"
        )
        return
    if imported.startswith("gateway_backend."):
        assert imported.startswith("gateway_backend.operations"), (
            f"{source} imports disallowed backend module {imported}"
        )
