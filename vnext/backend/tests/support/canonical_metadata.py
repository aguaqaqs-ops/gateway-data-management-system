"""Test metadata ports for Repository-ref use cases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadata,
    CommitCanonicalMetadataPort,
    CommitCanonicalScope,
)
from gateway_backend.capabilities.storage_projection import (
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    TableRulesetSnapshot,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryTableCatalog
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from tests.support.repository_ref_materialization import canonical_binding_for_catalog


class CatalogCommitCanonicalMetadataPort(CommitCanonicalMetadataPort):
    def __init__(
        self,
        metadata: Mapping[tuple[str, str], CommitCanonicalMetadata],
    ) -> None:
        self._metadata = dict(metadata)

    def resolve(
        self,
        *,
        repository_id: str,
        commit_id: str,
        scope: CommitCanonicalScope,
    ) -> CommitCanonicalMetadata:
        try:
            entry = self._metadata[(repository_id, commit_id)]
        except KeyError as exc:
            raise ValueError("test commit canonical metadata is missing") from exc
        return replace(entry, scope=scope)


class MetadataControlDbUnitOfWork(ControlDbUnitOfWork):
    def __init__(self, db_path: Path, metadata_port: CommitCanonicalMetadataPort) -> None:
        super().__init__(db_path)
        self._test_metadata_port = metadata_port

    @property
    def commit_canonical_metadata(self) -> CommitCanonicalMetadataPort:
        return self._test_metadata_port


def metadata_for_catalog(
    catalog: RepositoryTableCatalog,
    *,
    rows_by_table: Mapping[str, int] | None = None,
    ruleset: TableRulesetSnapshot | None = None,
    initial: bool | None = None,
    scope: CommitCanonicalScope | None = None,
) -> CommitCanonicalMetadata:
    active = ruleset or migrated_table_ruleset_snapshot()
    is_initial = (not catalog.tables) if initial is None else initial
    canonical_binding = canonical_binding_for_catalog(
        catalog,
        ruleset=active,
        is_initial=is_initial,
    )
    manifest = None
    if not is_initial:
        tables_by_name = {table.table_name.casefold(): table for table in catalog.tables}
        manifest_tables = []
        for view in canonical_binding.tables:
            catalog_table = tables_by_name[view.canonical_table.casefold()]
            retained = tuple(sorted(column.name.casefold() for column in catalog_table.columns))
            row_count = (rows_by_table or {}).get(view.canonical_table, catalog_table.row_count or 0)
            manifest_tables.append(
                CanonicalizationManifestTable(
                    name=view.canonical_table,
                    source_row_count=row_count,
                    canonical_row_count=row_count,
                    canonical_key_policy=view.canonical_key_policy,
                    ordered_policy=view.ordered_policy,
                    retained_columns=retained,
                    structural_columns=view.structural_columns,
                    dropped_columns=view.dropped_columns,
                    canonical_key_columns=(
                        view.canonical_key_columns
                        if view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
                        else ()
                    ),
                )
            )
        if active.ruleset_digest is None:
            raise ValueError("test ruleset digest is missing")
        manifest = CanonicalizationManifest(
            contract_version="test-canonicalization-manifest",
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            ruleset_id=active.ruleset_id,
            ruleset_version=active.ruleset_version,
            ruleset_digest=active.ruleset_digest,
            source_artifact_digest=raw_blob_digest(b"test-source-artifact"),
            tables=tuple(manifest_tables),
        )
    return CommitCanonicalMetadata(
        repository_id=catalog.repository_id,
        commit_id=catalog.resolved_commit_hash,
        scope=scope or CommitCanonicalScope("device-1", "project-1"),
        initial=is_initial,
        manifest=manifest,
    )


def metadata_port_for_catalogs(
    catalogs: Mapping[tuple[str, str], RepositoryTableCatalog],
) -> CatalogCommitCanonicalMetadataPort:
    return CatalogCommitCanonicalMetadataPort(
        {
            key: metadata_for_catalog(catalog)
            for key, catalog in catalogs.items()
        }
    )
