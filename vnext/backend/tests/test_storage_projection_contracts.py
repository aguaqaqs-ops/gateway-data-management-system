"""Storage Projection public contract tests. Does not project rows or write packages."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import pytest
from gateway_backend.capabilities import storage_projection as storage_projection_public
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    MAX_DIAGNOSTIC_MESSAGE_BYTES,
    MAX_DIAGNOSTICS,
    MAX_MANIFEST_JSON_BYTES,
    MAX_REPLAY_SQL_BYTES,
    PACKAGE_VERSION,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    NeverCancel,
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTable,
    ProjectionTableInput,
    PackageError,
    durable_manifest_bytes,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection import contracts as storage_projection_contracts
from gateway_backend.capabilities.table_rules.contracts import (
    RULESET_ID,
    RULESET_VERSION,
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    StorageRuleView,
    TableRulesetSnapshot,
)
from tests.support.storage_projection import dummy_digest, table_input
from tests.support.table_rules import net_cfg_record, snapshot_from_records

_OWNER = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "gateway_backend"
    / "capabilities"
    / "storage_projection"
)
_MIB = 1024 * 1024
_KIB = 1024
FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "host_path",
        "sql_text",
        "replay_sql",
        "parser_invocation_context",
    }
)


def _projection_request(**overrides: object) -> ProjectionRequest:
    reader, binding = table_input()
    values: dict[str, object] = {
        "ruleset": snapshot_from_records(net_cfg_record()),
        "storage_projection_version": STORAGE_PROJECTION_VERSION,
        "tables": (
            ProjectionTableInput(
                canonical_table="net_cfg",
                reader=reader,
                source_binding=binding,
            ),
        ),
        "context": ProjectionInvocationContext(cancel_requested=NeverCancel()),
    }
    values.update(overrides)
    return ProjectionRequest(**values)  # type: ignore[arg-type]


def _storage_view() -> StorageRuleView:
    return StorageRuleView(
        canonical_table="net_cfg",
        canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
        ordered_policy=OrderedPolicy.NONE,
        dropped_columns=(
            DroppedColumn(name="no", reason="legacy_ignored_column:net_cfg"),
        ),
        retained_columns=("board", "link_no"),
        canonical_key_columns=("board", "link_no"),
    )


def _manifest(ruleset_digest: object) -> CanonicalizationManifest:
    digest = dummy_digest()
    return CanonicalizationManifest(
        contract_version=CANONICALIZATION_MANIFEST_CONTRACT,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=RULESET_ID,
        ruleset_version=RULESET_VERSION,
        ruleset_digest=ruleset_digest,  # type: ignore[arg-type]
        source_artifact_digest=digest,
        tables=(
            CanonicalizationManifestTable(
                name="net_cfg",
                source_row_count=0,
                canonical_row_count=0,
                canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
                ordered_policy=OrderedPolicy.NONE,
                retained_columns=("board", "link_no"),
                structural_columns=(),
                dropped_columns=(
                    DroppedColumn(name="no", reason="legacy_ignored_column:net_cfg"),
                ),
                canonical_key_columns=("board", "link_no"),
            ),
        ),
        manifest_digest=digest,
    )


def _import_input() -> RepositoryImportArtifactInput:
    return RepositoryImportArtifactInput(
        package_version=PACKAGE_VERSION,
        canonicalization_manifest_digest=dummy_digest(),
        tables=(
            RepositoryImportTable(
                name="net_cfg",
                columns=(
                    RepositoryImportColumn(name="board", sql_type="INT", nullable=False),
                    RepositoryImportColumn(name="link_no", sql_type="INT", nullable=False),
                ),
                primary_key=("board", "link_no"),
                row_count=0,
            ),
        ),
    )


def test_versions_and_publication_budgets_match_s0() -> None:
    assert STORAGE_PROJECTION_VERSION == "1"
    assert CANONICALIZATION_MANIFEST_CONTRACT == "3.1.0"
    assert PACKAGE_VERSION == 1
    assert MAX_MANIFEST_JSON_BYTES == 16 * _MIB
    assert MAX_REPLAY_SQL_BYTES == 200 * _MIB
    assert MAX_DIAGNOSTICS == 1024
    assert MAX_DIAGNOSTIC_MESSAGE_BYTES == 4 * _KIB
    assert CANONICALIZATION_MANIFEST_MEDIA_TYPE == "application/json"
    assert REPOSITORY_IMPORT_MEDIA_TYPE == (
        "application/vnd.gateway.repository-import.v1+tar+zstd"
    )
    assert ProjectionStatus.COMPLETE.value == "COMPLETE"
    assert ProjectionStatus.FAILED.value == "FAILED"
    assert "PARTIAL" not in ProjectionStatus.__members__


def test_public_types_have_no_forbidden_fields() -> None:
    for name in dir(storage_projection_contracts):
        candidate = getattr(storage_projection_contracts, name)
        if not is_dataclass(candidate):
            continue
        names = {item.name for item in fields(candidate)}
        assert names.isdisjoint(FORBIDDEN_FIELD_NAMES), name


def test_projection_request_requires_complete_ruleset_identity() -> None:
    with pytest.raises(ValueError, match="projection requires a complete ruleset_digest"):
        _projection_request(ruleset=TableRulesetSnapshot(table_ruleset_version=1))
    with pytest.raises(ValueError, match="storage_projection_version must be 1"):
        _projection_request(storage_projection_version="2")


def test_manifest_model_reads_the_previous_contract_but_writer_requires_current() -> None:
    historical = replace(_manifest(dummy_digest()), contract_version="3.0.0")

    assert historical.contract_version == "3.0.0"
    with pytest.raises(PackageError, match="current contract_version"):
        durable_manifest_bytes(historical)


def test_failed_projection_must_not_publish_partial_import() -> None:
    with pytest.raises(ValueError, match="FAILED projection must not publish"):
        ProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(
                ProjectionTable(
                    canonical_table="net_cfg",
                    storage_view=_storage_view(),
                ),
            ),
            diagnostics=(
                ProjectionDiagnostic(
                    code=ProjectionDiagnosticCode.REQUIRED_TABLE_FAILED,
                    severity=ProjectionDiagnosticSeverity.ERROR,
                    message="projection failed before publication",
                    table_name="net_cfg",
                ),
            ),
            import_input=_import_input(),
        )


def test_complete_projection_binds_opaque_manifest_digest() -> None:
    request = _projection_request()
    assert request.ruleset.ruleset_digest is not None
    result = ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=(
            ProjectionTable(
                canonical_table="net_cfg",
                storage_view=_storage_view(),
                row_count=0,
            ),
        ),
        manifest=_manifest(request.ruleset.ruleset_digest),
        import_input=_import_input(),
    )
    assert result.import_input is not None
    assert result.manifest is not None
    assert result.import_input.canonicalization_manifest_digest == result.manifest.manifest_digest


def test_capability_exports_publication_without_host_path_writer() -> None:
    assert hasattr(storage_projection_public, "project_storage")
    assert hasattr(storage_projection_public, "publish_canonicalization")
    assert hasattr(storage_projection_public, "build_repository_import_package")
    assert hasattr(storage_projection_public, "open_canonicalization_manifest")
    assert hasattr(storage_projection_public, "open_repository_import_package")
    assert not hasattr(storage_projection_public, "project_tables")
    assert not hasattr(storage_projection_public, "write_repository_import_artifact")
    assert not hasattr(storage_projection_public, "write_package")
    for source in _OWNER.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "def write_" not in text, source
        assert "NotImplementedError" not in text, source
        assert "host_path" not in text, source
