"""Architecture boundary tests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from tests.architecture_baseline import (
    IMPORT_RULE_BASELINE,
    RUNTIME_CYCLE_BASELINE,
    UNREACHABLE_MODULE_BASELINE,
)
from tests.support.import_rules import (
    RULE_CAPABILITY_SURFACE,
    RULE_CONTRACTS_LEAF,
    RULE_LAYER,
    RULE_PRIVATE,
    ImportEdge,
    backend_modules,
    classify_edge,
    collect_edges,
    find_violations,
    package_names,
    runtime_cycles,
    unreachable_modules,
)

BACKEND_SRC = Path(__file__).parents[1] / "src"
CAPABILITIES_ROOT = BACKEND_SRC / "gateway_backend" / "capabilities"
CAPABILITIES_PREFIX = "gateway_backend.capabilities."
OPERATIONS_ROOT = BACKEND_SRC / "gateway_backend" / "operations"
CONTROL_DB_ROOT = BACKEND_SRC / "gateway_backend" / "infrastructure" / "control_db"
BOOTSTRAP_ROOT = BACKEND_SRC / "gateway_backend" / "bootstrap"
APPLICATION_ROOT = BACKEND_SRC / "gateway_backend" / "application"

CAPABILITY_OWNERS = frozenset(
    {
        "canonical_row_hash",
        "table_access",
        "table_rules",
        "source_package_staging",
        "composite_signal",
        "snapshot_materialization",
        "storage_projection",
        "comparison",
        "risk_evaluation",
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
    "comparison": frozenset({"snapshot_materialization"}),
    "risk_evaluation": frozenset({"comparison"}),
    "surface_assembly": frozenset({"comparison", "risk_evaluation"}),
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
    "gateway_backend.capabilities.canonical_row_hash.compute",
    "gateway_backend.capabilities.canonical_row_hash.canonical_row_hash_ipc",
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
    compute_source = (
        Path(__file__).parents[1]
        / "src"
        / "gateway_backend"
        / "capabilities"
        / "canonical_row_hash"
        / "compute.py"
    )
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
    ipc_source = (
        Path(__file__).parents[1]
        / "src"
        / "gateway_backend"
        / "capabilities"
        / "canonical_row_hash"
        / "canonical_row_hash_ipc.py"
    )
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
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for class_node in ast.walk(tree):
            if isinstance(class_node, ast.ClassDef):
                assert class_node.name not in FORBIDDEN_PROVIDER_BASE_NAMES, source
    for edge in _backend_edges():
        if edge.source == "gateway_backend.capabilities" or edge.source.startswith(CAPABILITIES_PREFIX):
            _assert_capability_import_allowed(edge.path, _owner_from_module(edge.source), edge.target)


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


def test_http_runtime_does_not_duplicate_surface_artifact_closure() -> None:
    dependencies_source = BACKEND_SRC / "gateway_backend" / "http" / "dependencies.py"
    text = dependencies_source.read_text(encoding="utf-8")
    assert "_surface_artifact_closure" not in text


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


def test_operations_source_has_no_operation_kind() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        assert "operation_kind" not in source.read_text(encoding="utf-8"), source


def test_operations_source_has_no_deferred_stub() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        assert "NotImplementedError" not in source.read_text(encoding="utf-8"), source


def test_application_package_exists_and_exports_job_definition_contract() -> None:
    assert APPLICATION_ROOT.is_dir()
    assert (APPLICATION_ROOT / "__init__.py").is_file()
    assert (APPLICATION_ROOT / "job_definitions.py").is_file()
    application = importlib.import_module("gateway_backend.application")
    assert frozenset(application.__all__) == frozenset(
        {
            "JobDefinition",
            "JobDefinitionLookupError",
            "JobDefinitionRegistry",
            "NormalPublicationCapability",
            "RecoveryCapability",
            "RecoveryDecision",
            "RecoveryDecisionDisposition",
            "RecoveryOutcome",
            "RecoveryOutcomeDisposition",
            "RecoveryPort",
            "build_worker_registry",
        }
    )


def test_job_definitions_stays_memory_only() -> None:
    source = APPLICATION_ROOT / "job_definitions.py"
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), source


def test_recovery_module_io_boundary() -> None:
    source = APPLICATION_ROOT / "recovery.py"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), source
    assert "gateway_backend.infrastructure" not in text


def test_payloads_module_io_boundary() -> None:
    source = APPLICATION_ROOT / "payloads.py"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), source
    assert "ArtifactStorePort" in text


def test_checkpoints_module_io_boundary() -> None:
    source = APPLICATION_ROOT / "checkpoints.py"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), source
    assert "ArtifactStorePort" in text
    assert "gateway_backend.infrastructure" not in text


TESTS_SUPPORT_ROOT = Path(__file__).parents[1] / "tests" / "support"


def test_synthetic_jobs_module_io_boundary() -> None:
    source = TESTS_SUPPORT_ROOT / "synthetic_jobs.py"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), source
    assert "ArtifactStorePort" in text
    assert "gateway_backend.infrastructure" not in text


def test_external_effect_stub_module_io_boundary() -> None:
    source = TESTS_SUPPORT_ROOT / "external_effect_stub.py"
    assert source.is_file()
    text = source.read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "subprocess",
        "threading",
        "signal",
        "socket",
        "httpx",
        "open(",
        "pathlib",
    )
    assert not any(token in text for token in forbidden), source
    assert "gateway_backend.infrastructure" not in text


def test_worker_contract_module_stays_runtime_neutral() -> None:
    worker_source = OPERATIONS_ROOT / "worker.py"
    assert worker_source.is_file()
    text = worker_source.read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "gateway_backend.infrastructure" not in text
    assert "gateway_backend.settings" not in text
    assert "gateway_repository" not in text
    assert "subprocess" not in text
    assert "threading" not in text
    assert "NotImplementedError" not in text
    assert "class WorkerError" not in text


def test_lease_session_uses_only_operations_ports_and_atomic_actions() -> None:
    lease_session_source = OPERATIONS_ROOT / "lease_session.py"
    assert lease_session_source.is_file()
    text = lease_session_source.read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "gateway_backend.infrastructure" not in text
    assert "gateway_backend.settings" not in text
    assert "gateway_repository" not in text
    assert "subprocess" not in text
    assert "compare_and_set_" not in text
    assert "insert_successor_step" not in text
    assert "OperationLifecycleActions" in text
    assert "NotImplementedError" not in text


def test_worker_startup_stays_runtime_neutral_and_uses_injected_ports() -> None:
    worker_startup_source = OPERATIONS_ROOT / "worker_startup.py"
    assert worker_startup_source.is_file()
    text = worker_startup_source.read_text(encoding="utf-8")
    assert "sqlite3" not in text
    assert "gateway_backend.infrastructure" not in text
    assert "gateway_backend.settings" not in text
    assert "gateway_repository" not in text
    assert "subprocess" not in text
    assert "threading" not in text
    assert "signal" not in text
    assert "NotImplementedError" not in text
    assert "OperationLifecycleActions" in text
    assert "read_uow_factory" in text
    assert "write_uow_factory" in text


def test_worker_lifecycle_stays_process_local_and_runtime_neutral() -> None:
    lifecycle_source = OPERATIONS_ROOT / "worker_lifecycle.py"
    assert lifecycle_source.is_file()
    text = lifecycle_source.read_text(encoding="utf-8")
    forbidden = (
        "import sqlite3",
        "from sqlite3",
        "import signal",
        "from signal",
        "import subprocess",
        "from subprocess",
        "gateway_backend.infrastructure",
        "gateway_backend.settings",
        "gateway_repository",
        "NotImplementedError",
    )
    assert not any(token in text for token in forbidden), lifecycle_source


def test_http_bootstrap_owns_uvicorn_entry() -> None:
    entrypoint = BOOTSTRAP_ROOT / "http_server.py"
    assert entrypoint.is_file()
    text = entrypoint.read_text(encoding="utf-8")
    assert "AdmissionFirstUvicornServer" in text
    assert "begin_http_pre_drain" in text
    assert "SIGTERM" not in text
    assert "handle_exit" in text
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    assert 'CMD ["python", "-m", "gateway_backend.bootstrap.http_server"]' in dockerfile.read_text(
        encoding="utf-8"
    )


def test_worker_bootstrap_owns_concrete_process_composition() -> None:
    assert (BOOTSTRAP_ROOT / "__init__.py").is_file()
    entrypoint = BOOTSTRAP_ROOT / "operation_worker.py"
    assert entrypoint.is_file()
    text = entrypoint.read_text(encoding="utf-8")
    forbidden = (
        "gateway_backend.app",
        "gateway_backend.capabilities",
        "gateway_backend.repository_import_artifact",
        "gateway_repository",
        "uvicorn",
        "fastapi",
        "socket",
        "pidfile",
        "SIGHUP",
    )
    for token in forbidden:
        if token == "gateway_backend.app":
            assert "gateway_backend.app." not in text
            assert "from gateway_backend.app import" not in text
            continue
        assert token not in text, f"{token} must not appear in {entrypoint}"
    assert "initialize_and_verify_control_db" in text
    assert "SIGTERM" in text
    assert "SIGINT" in text
    assert "build_job_worker_composition" in text
    assert "build_http_repository_provider_factory" in text
    assert "build_production_preview_dependencies" in text
    assert "build_production_submit_dependencies" in text

    for edge in _backend_edges():
        if edge.source.startswith("gateway_backend.bootstrap"):
            imported = edge.target
            if imported.startswith("gateway_backend."):
                assert imported.startswith(
                    (
                        "gateway_backend.application",
                        "gateway_backend.artifacts",
                        "gateway_backend.capabilities",
                        "gateway_backend.domain",
                        "gateway_backend.http",
                        "gateway_backend.bootstrap",
                        "gateway_backend.bootstrap.composition",
                        "gateway_backend.http.shutdown",
                        "gateway_backend.infrastructure.artifact_store",
                        "gateway_backend.infrastructure.control_db",
                        "gateway_backend.infrastructure.repository_read",
                        "gateway_backend.infrastructure.repository_write",
                        "gateway_backend.operations",
                        "gateway_backend.repository_import_artifact",
                        "gateway_backend.settings",
                    )
                ), f"{edge.path} imports disallowed module {imported}"


def test_operation_worker_settings_have_an_independent_environment_prefix() -> None:
    settings_source = BACKEND_SRC / "gateway_backend" / "settings.py"
    text = settings_source.read_text(encoding="utf-8")
    assert "class BackendSettings" in text
    assert "class OperationWorkerSettings" in text
    assert 'env_prefix="GATEWAY_BACKEND_OPERATION_WORKER_"' in text
    assert 'env_prefix="GATEWAY_BACKEND_"' in text


def test_control_db_boundary_exists() -> None:
    assert CONTROL_DB_ROOT.is_dir()
    assert (CONTROL_DB_ROOT / "__init__.py").is_file()
    assert (CONTROL_DB_ROOT / "database.py").is_file()
    assert (CONTROL_DB_ROOT / "migrations.py").is_file()
    assert (CONTROL_DB_ROOT / "sqlite_operations.py").is_file()


def test_control_db_uow_binds_operations_without_expanding_operations_owner() -> None:
    database_source = (CONTROL_DB_ROOT / "database.py").read_text(encoding="utf-8")
    adapter_source = (CONTROL_DB_ROOT / "sqlite_operations.py").read_text(encoding="utf-8")
    operations_root = Path(__file__).parents[1] / "src" / "gateway_backend" / "operations"

    assert "def operations(" in database_source
    assert "SQLiteOperationStore" in database_source
    assert "class SQLiteOperationStore" in adapter_source
    assert "commit(" not in adapter_source
    assert "rollback(" not in adapter_source
    for source in sorted(operations_root.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        assert "sqlite3" not in text
        assert "gateway_backend.infrastructure" not in text


def _capability_owner_dirs() -> set[str]:
    owners: set[str] = set()
    for path in CAPABILITIES_ROOT.iterdir():
        if path.name in {"__pycache__", "__init__.py"} or path.name.startswith("."):
            continue
        if path.is_dir():
            owners.add(path.name)
    return owners


def _owner_from_module(module_name: str) -> str | None:
    if module_name == "gateway_backend.capabilities":
        return None
    if not module_name.startswith(CAPABILITIES_PREFIX):
        return None
    rest = module_name.removeprefix(CAPABILITIES_PREFIX)
    return rest.split(".", 1)[0]


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
    permitted = remainder == "" or remainder == "contracts" or remainder.startswith("contracts.")
    assert permitted, f"{source} may import only approved {target_owner} modules, not {imported}"


def _split_capability_import(imported: str) -> tuple[str, str]:
    rest = imported.removeprefix(CAPABILITIES_PREFIX)
    owner, separator, remainder = rest.partition(".")
    assert owner in CAPABILITY_OWNERS, f"unknown capability import {imported}"
    if not separator:
        return owner, ""
    return owner, remainder


# ---------------------------------------------------------------------------
# Unified import-boundary gate (P5 §2A.2). Rules live in tests/support/import_rules.py; known
# violations are frozen in tests/architecture_baseline.py and may only shrink.
# ---------------------------------------------------------------------------

_BACKEND_EDGES: list[ImportEdge] = []


def _backend_edges() -> list[ImportEdge]:
    if not _BACKEND_EDGES:
        _BACKEND_EDGES.extend(collect_edges(backend_modules()))
    return _BACKEND_EDGES


_BASELINE_HINT = (
    "Fix the import instead of extending tests/architecture_baseline.py; an entry may be added only "
    "with an explicit, reviewed justification. Stale entries must be deleted once fixed. Run "
    "`python -m tests.support.import_rules` from vnext/backend to print the current state."
)


def test_import_rules_match_frozen_baseline() -> None:
    violations = find_violations(_backend_edges(), backend_modules())
    new = sorted(
        {violation.describe() for violation in violations if violation.key not in IMPORT_RULE_BASELINE}
    )
    current_keys = {violation.key for violation in violations}
    stale = sorted(str(key) for key in IMPORT_RULE_BASELINE - current_keys)
    assert not new and not stale, (
        "Import boundary drift.\nNew violations:\n  "
        + "\n  ".join(new or ["(none)"])
        + "\nStale baseline entries:\n  "
        + "\n  ".join(stale or ["(none)"])
        + f"\n{_BASELINE_HINT}"
    )


def test_runtime_import_cycles_match_frozen_baseline() -> None:
    current = set(runtime_cycles(_backend_edges(), backend_modules()))
    frozen = set(RUNTIME_CYCLE_BASELINE)
    new = sorted(sorted(component) for component in current - frozen)
    stale = sorted(sorted(component) for component in frozen - current)
    assert not new and not stale, (
        "Runtime import cycles (module and function-local imports) changed.\n"
        f"New or grown cycles: {new}\nStale baseline cycles: {stale}\n{_BASELINE_HINT}"
    )


def test_production_reachability_matches_frozen_baseline() -> None:
    current = unreachable_modules(_backend_edges(), backend_modules())
    new = sorted(current - UNREACHABLE_MODULE_BASELINE)
    stale = sorted(UNREACHABLE_MODULE_BASELINE - current)
    assert not new and not stale, (
        "Production code without a production consumer changed.\n"
        f"Newly unreachable from app/http_server/operation_worker: {new}\n"
        f"Stale baseline entries (now reachable or deleted): {stale}\n{_BASELINE_HINT}"
    )


REACHABILITY_MODULE_SHAPES: tuple[tuple[str, bool], ...] = (
    ("gateway_backend.capabilities.snapshot_materialization.compose", True),
    ("gateway_backend.capabilities.table_access._xml_parser", True),
    ("gateway_backend.bootstrap.operation_worker", False),
    ("gateway_backend.application.submit_jobs", False),
)


@pytest.mark.parametrize(("module_name", "expect_unreachable"), REACHABILITY_MODULE_SHAPES)
def test_production_reachability_classifies_module_shapes(
    module_name: str,
    expect_unreachable: bool,
) -> None:
    current = unreachable_modules(_backend_edges(), backend_modules())
    assert (module_name in current) is expect_unreachable


COMPOSITE_FACADE_MODULES = (
    "gateway_backend.capabilities.composite_signal._ast",
    "gateway_backend.capabilities.composite_signal._bind",
    "gateway_backend.capabilities.composite_signal._digest",
    "gateway_backend.capabilities.composite_signal.materialize",
)
FACADE_REACHABILITY_SHAPES: tuple[tuple[bool, bool], ...] = (
    (False, True),
    (True, False),
)


@pytest.mark.parametrize(
    ("production_imports_facade_symbol", "expect_composite_unreachable"),
    FACADE_REACHABILITY_SHAPES,
)
def test_facade_lazy_import_reachability_depends_on_imported_symbol(
    production_imports_facade_symbol: bool,
    expect_composite_unreachable: bool,
) -> None:
    modules = backend_modules()
    edges = _backend_edges()
    assert any(
        edge.source == "gateway_backend.capabilities.composite_signal"
        and edge.context == "function"
        and edge.function == "materialize_composite_signal"
        and edge.target == "gateway_backend.capabilities.composite_signal.materialize"
        for edge in edges
    )
    if production_imports_facade_symbol:
        edges = [
            *edges,
            ImportEdge(
                source="gateway_backend.app",
                target="gateway_backend.capabilities.composite_signal",
                names=("materialize_composite_signal",),
                context="module",
                path=BACKEND_SRC / "gateway_backend" / "app.py",
                line=1,
            ),
        ]

    current = unreachable_modules(edges, modules)
    assert all((name in current) is expect_composite_unreachable for name in COMPOSITE_FACADE_MODULES)


# Each row: source module, imported module, imported names, expected rule (None = allowed).
IMPORT_RULE_SHAPES: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    ("gateway_backend.domain.workspace.models", "gateway_backend.application.workspace.contracts", (), RULE_LAYER),
    ("gateway_backend.domain.workspace.models", "gateway_backend.artifacts.types", (), RULE_LAYER),
    ("gateway_backend.artifacts.types", "gateway_backend.domain.submission.models", (), RULE_LAYER),
    ("gateway_backend.operations.contracts", "gateway_backend.capabilities.comparison", (), RULE_LAYER),
    ("gateway_backend.operations.contracts", "gateway_backend.artifacts.types", (), None),
    ("gateway_backend.capabilities.comparison.standard", "gateway_backend.application.payloads", (), RULE_LAYER),
    ("gateway_backend.capabilities.comparison.standard", "gateway_backend.settings", (), RULE_LAYER),
    ("gateway_backend.application.preview_jobs", "gateway_backend.capabilities.comparison", (), None),
    ("gateway_backend.application.preview_jobs", "gateway_backend.capabilities.comparison.contracts", (), None),
    (
        "gateway_backend.application.preview_jobs",
        "gateway_backend.capabilities.comparison.standard",
        (),
        RULE_CAPABILITY_SURFACE,
    ),
    ("gateway_backend.application.preview_jobs", "gateway_backend.infrastructure.control_db.database", (), RULE_LAYER),
    ("gateway_backend.application.preview_jobs", "gateway_repository_contracts", (), RULE_LAYER),
    ("gateway_backend.application.preview_jobs", "gateway_backend.settings", (), RULE_LAYER),
    ("gateway_backend.application.preview_jobs", "gateway_backend.operations.contracts", ("_validate_opaque_id",), RULE_PRIVATE),
    ("gateway_backend.http.routes.history", "gateway_backend.infrastructure.control_db.sqlite_history", (), RULE_LAYER),
    ("gateway_backend.http.routes.history", "gateway_backend.capabilities.comparison.contracts", (), RULE_LAYER),
    ("gateway_backend.http.routes.history", "gateway_backend.application.history.queries", (), None),
    ("gateway_backend.http.routes.history", "fastapi", (), None),
    (
        "gateway_backend.infrastructure.repository_read.http_arrow",
        "gateway_backend.capabilities.snapshot_materialization._digest",
        (),
        RULE_PRIVATE,
    ),
    ("gateway_backend.infrastructure.repository_read.http_arrow", "gateway_repository_client", (), None),
    ("gateway_backend.infrastructure.control_db.database", "gateway_repository_client", (), RULE_LAYER),
    ("gateway_backend.infrastructure.control_db.database", "gateway_backend.application.history.ports", (), None),
    (
        "gateway_backend.infrastructure.control_db.database",
        "gateway_backend.application.history.compare_bindings",
        (),
        RULE_LAYER,
    ),
    ("gateway_backend.infrastructure.control_db.database", "sqlalchemy", (), RULE_LAYER),
    (
        "gateway_backend.capabilities.table_rules.contracts",
        "gateway_backend.capabilities.table_rules.resolver",
        (),
        RULE_CONTRACTS_LEAF,
    ),
    ("gateway_backend.capabilities.comparison.ordered", "gateway_backend.capabilities.comparison.standard", ("_row_digest",), None),
    ("gateway_backend.bootstrap.operation_worker", "gateway_backend.infrastructure.control_db", (), None),
    (
        "gateway_backend.capabilities.canonical_row_hash.compute",
        "gateway_compute",
        (),
        None,
    ),
    ("gateway_backend.bootstrap.operation_worker", "gateway_shared_kernel.testing", (), RULE_LAYER),
)


@pytest.mark.parametrize(("source", "target", "names", "expected"), IMPORT_RULE_SHAPES)
def test_import_rule_engine_classifies_edge_shapes(
    source: str, target: str, names: tuple[str, ...], expected: str | None
) -> None:
    edge = ImportEdge(source, target, names, "module", BACKEND_SRC / "gateway_backend", 1)
    found = classify_edge(edge, package_names(backend_modules()))
    assert (None if found is None else found[0]) == expected
