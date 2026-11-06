"""Small test fixtures built by the real Rust projection, never an oracle."""

from __future__ import annotations

from dataclasses import replace

from gateway_shared_kernel import DigestRef
from gateway_backend.capabilities.snapshot_materialization import (
    operation_business_budgets, snapshot_arrow_input, snapshot_table_from_arrow,
    source_descriptor_from_arrow,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotColumnDescriptor, SnapshotTable, SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT, PACKAGE_VERSION, STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest, CanonicalizationManifestTable, ImportReplayTableSnapshot, CanonicalProjectionResult,
    ProjectionDiagnostic, ProjectionDiagnosticCode, ProjectionDiagnosticSeverity,
    ProjectionRequest, ProjectionResult, ProjectionStatus, ProjectionTable,
    RepositoryImportArtifactInput, RepositoryImportColumn, RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest, compute_schema_digest
from gateway_backend.capabilities.storage_projection.native import project_arrow_table
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view, StorageViewError
from gateway_backend.capabilities.table_rules import resolve_table_rule
from tests.support.snapshot_materialization import snapshot_table_as_arrow
from gateway_backend.capabilities.table_rules.contracts import TableRulesetSnapshot


def projected_fixture_tables(request: ProjectionRequest) -> tuple[ProjectionResult, tuple[SnapshotTable, ...]]:
    tables: list[SnapshotTable] = []
    projected = []
    manifest_tables = []
    imports = []
    diagnostics = []
    omitted = 0
    for item in sorted(request.tables, key=lambda item: item.canonical_table.encode("utf-8")):
        if request.requested_tables is not None and item.canonical_table not in request.requested_tables:
            continue
        descriptor = item.source_binding.descriptor
        record = resolve_table_rule(request.ruleset, item.canonical_table,
                                    primary_key_columns=descriptor.primary_key_columns).record
        try:
            view = derive_storage_rule_view(record, descriptor)
        except StorageViewError as exc:
            diagnostics.append(ProjectionDiagnostic(exc.code, ProjectionDiagnosticSeverity.ERROR,
                                                   exc.message, item.canonical_table))
            continue
        if view is None:
            continue
        arrow = snapshot_table_as_arrow(SnapshotTable(descriptor, item.reader))
        try:
            with snapshot_arrow_input(arrow) as (metadata, control):
                result = project_arrow_table(metadata, descriptor, view,
                    canonicalized_input=item.canonicalized_input,
                    cancel_probe=control.cancel_probe, budgets=operation_business_budgets(),
                    deadline_monotonic=control.deadline_monotonic, pool_threads=control.threads)
        finally:
            if arrow.reader is not None:
                arrow.reader.close()
            if arrow.batch_reader is not None:
                arrow.batch_reader.close()
            item.reader.close()
        for diagnostic in result['diagnostics']:
            diagnostics.append(ProjectionDiagnostic(ProjectionDiagnosticCode(diagnostic['code']),
                ProjectionDiagnosticSeverity(diagnostic['severity']), diagnostic['message'],
                diagnostic['table'], diagnostic['column']))
        omitted += result['omitted_diagnostic_count']
        output = result['output']
        if output is None:
            continue
        native = output['tables'][0]
        with native['arrow_stream'] as stream:
            backing = stream.read_all()
        columns = tuple(SnapshotColumnDescriptor(c['canonical_name'], c['display_name'], c['nullable'], c['sql_type'])
                        for c in native['columns'])
        digest = DigestRef(output['raw_content_digest'])
        schema = compute_schema_digest(columns=[{'name': c.name, 'nullable': c.nullable, 'sql_type': c.scalar_type}
                                                for c in columns], primary_key=view.canonical_key_columns)
        bound = replace(descriptor, columns=columns, row_count=backing.num_rows,
            primary_key_columns=view.canonical_key_columns, compare_key_columns=view.canonical_key_columns,
            raw_content_digest=digest, degraded_reason=None, diagnostics=())
        tables.append(snapshot_table_from_arrow(bound, backing, source_descriptor_from_arrow(native)))
        projected.append(ProjectionTable(item.canonical_table, view, row_count=backing.num_rows, schema_digest=schema, content_digest=digest))
        manifest_tables.append(CanonicalizationManifestTable(item.canonical_table, descriptor.row_count,
            backing.num_rows, view.canonical_key_policy, view.ordered_policy, view.retained_columns,
            view.structural_columns, view.dropped_columns, view.canonical_key_columns,
            descriptor.compare_schema_digest, schema, digest, output['gid_real_count'], output['gid_pseudo_count']))
        imports.append(RepositoryImportTable(item.canonical_table,
            tuple(RepositoryImportColumn(c.name, c.scalar_type or '', c.nullable) for c in columns),
            view.canonical_key_columns, backing.num_rows))
    if diagnostics:
        return ProjectionResult(ProjectionStatus.FAILED, (), omitted, diagnostics=tuple(diagnostics)), ()
    assert request.ruleset.ruleset_digest is not None
    manifest = CanonicalizationManifest(CANONICALIZATION_MANIFEST_CONTRACT, STORAGE_PROJECTION_VERSION,
        request.ruleset.ruleset_id, request.ruleset.ruleset_version, request.ruleset.ruleset_digest,
        request.tables[0].source_binding.snapshot_digest, tuple(manifest_tables))
    manifest = replace(manifest, manifest_digest=compute_manifest_digest(manifest))
    assert manifest.manifest_digest is not None
    return ProjectionResult(ProjectionStatus.COMPLETE, tuple(projected), 0, manifest=manifest,
        import_input=RepositoryImportArtifactInput(PACKAGE_VERSION, manifest.manifest_digest, tuple(imports))), tuple(tables)


def project_storage(request: ProjectionRequest) -> ProjectionResult:
    """Construct a valid ProjectionResult for the publication/replay test owner."""
    result, tables = projected_fixture_tables(request)
    for table in tables:
        if table.reader is not None:
            table.reader.close()
        if table.batch_reader is not None:
            table.batch_reader.close()
    return result


def build_import_projection_snapshots(request: ProjectionRequest, result: ProjectionResult) -> tuple[ImportReplayTableSnapshot, ...]:
    """Build typed images through the actual Submit consumer after Rust projection."""
    from gateway_backend.infrastructure.repository_write.import_publication import _keyed_rows_from_frozen_artifact
    _, tables = projected_fixture_tables(request)
    assert result.manifest is not None
    manifests = {t.name: t for t in result.manifest.tables}
    views = {t.canonical_table: t.storage_view for t in result.tables}
    snapshots = []
    for table in tables:
        assert table.reader is not None
        manifest = manifests[table.descriptor.table_name]
        try:
            rows = _keyed_rows_from_frozen_artifact(table.reader, descriptor=table.descriptor, manifest_table=manifest)
            snapshots.append(ImportReplayTableSnapshot(manifest, views[manifest.name], rows))
        finally:
            table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
    return tuple(snapshots)


def project_canonical_fixture(raw: SnapshotTableSet, ruleset: TableRulesetSnapshot) -> CanonicalProjectionResult:
    from gateway_backend.capabilities.storage_projection import project_canonical_arrow_table_set
    return project_canonical_arrow_table_set(replace(raw, tables=tuple(snapshot_table_as_arrow(t) for t in raw.tables)), ruleset)
