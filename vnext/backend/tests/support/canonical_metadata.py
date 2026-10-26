"""Test metadata ports for Repository-ref use cases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadata,
    CommitCanonicalMetadataPort,
    CommitCanonicalScope,
)
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.storage_projection._digest import compute_schema_digest
from gateway_backend.capabilities.storage_projection.project import _retained_schema
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    RepositoryTableCatalog,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    TableRulesetSnapshot,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    canonical_binding_for_catalog,
    materialize_ref,
)


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
    rows_by_table: Mapping[str, Sequence[Sequence[object | None]]] | None = None,
    ruleset: TableRulesetSnapshot | None = None,
    manifest_override: CanonicalizationManifest | None = None,
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
    snapshot_digest: DigestRef | None = None
    if not is_initial:
        provider = FakeRepositoryTableAccessProvider(
            catalog=catalog,
            rows=rows_by_table or {},
            current_commit=catalog.resolved_commit_hash,
        )
        materialized = materialize_ref(
            provider,
            policy=MaterializationPolicy.READERS_REQUIRED,
            ruleset=active,
            canonical_binding=canonical_binding,
        )
        if (
            materialized.status.value != "COMPLETE"
            or materialized.summary is None
            or materialized.snapshot is None
        ):
            raise AssertionError("test Repository catalog did not materialize completely")
        descriptors = {item.table_name: item for item in materialized.summary.tables}
        tables_by_name = {table.table_name.casefold(): table for table in catalog.tables}
        manifest_tables = []
        for view in canonical_binding.tables:
            catalog_table = tables_by_name[view.canonical_table.casefold()]
            retained = view.retained_columns
            rows = (rows_by_table or {}).get(view.canonical_table)
            row_count = len(rows) if rows is not None else catalog_table.row_count or 0
            descriptor = descriptors[view.canonical_table]
            if descriptor.raw_content_digest is None:
                raise AssertionError("test Repository descriptor is missing the raw digest")
            schema_columns, _, _ = _retained_schema(view, descriptor)
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
                    source_schema_digest=descriptor.compare_schema_digest,
                    canonical_schema_digest=compute_schema_digest(
                        columns=schema_columns,
                        primary_key=view.canonical_key_columns,
                    ),
                    content_digest=descriptor.raw_content_digest,
                )
            )
        if active.ruleset_digest is None:
            raise ValueError("test ruleset digest is missing")
        manifest = CanonicalizationManifest(
            contract_version=CANONICALIZATION_MANIFEST_CONTRACT,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
            ruleset_id=active.ruleset_id,
            ruleset_version=active.ruleset_version,
            ruleset_digest=active.ruleset_digest,
            source_artifact_digest=raw_blob_digest(b"test-source-artifact"),
            tables=tuple(manifest_tables),
        )
        if manifest_override is not None:
            manifest = manifest_override
        snapshot_digest = materialized.snapshot.snapshot_digest
    return CommitCanonicalMetadata(
        repository_id=catalog.repository_id,
        commit_id=catalog.resolved_commit_hash,
        scope=scope or CommitCanonicalScope("device-1", "project-1"),
        initial=is_initial,
        manifest=manifest,
        snapshot_digest=snapshot_digest,
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
